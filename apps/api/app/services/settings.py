"""Runtime (database-backed) application settings.

Each group is stored as one JSON row in ``app_settings``. Defaults come from
the models below, seeded from environment variables where it makes sense.
Secrets are never part of runtime settings.
"""

from __future__ import annotations

import time
from typing import Any, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.opening_hours import parse_hhmm
from app.data.pricing import DEFAULT_PRICING_CURRENCY, DEFAULT_SKU_PRICES
from app.models import AppSetting
from app.scoring.config import ScoringConfig


class SettingsModel(BaseModel):
    model_config = ConfigDict(json_schema_serialization_defaults_required=True)


def _hhmm(value: str) -> str:
    parse_hhmm(value)
    return value.strip().zfill(5)


class GeneralSettings(SettingsModel):
    default_country: str = Field(
        default_factory=lambda: get_settings().default_country, min_length=2, max_length=2
    )
    default_city: str = Field(default_factory=lambda: get_settings().default_city, max_length=120)
    timezone: str = Field(default_factory=lambda: get_settings().timezone)
    provider_language: str = Field(default_factory=lambda: get_settings().default_language, max_length=10)
    pitch_language: Literal["en", "bg"] = "en"

    @field_validator("default_country")
    @classmethod
    def _upper(cls, v: str) -> str:
        return v.upper()

    @field_validator("timezone")
    @classmethod
    def _tz(cls, v: str) -> str:
        try:
            ZoneInfo(v)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError(f"Unknown timezone '{v}'") from exc
        return v


class CallingSettings(SettingsModel):
    window_start: str = "19:00"
    window_end: str = "21:00"
    recall_cooldown_hours: int = Field(default=20, ge=0, le=24 * 30)
    include_unknown_hours: bool = True
    default_session_limit: int = Field(default=50, ge=1, le=500)

    @field_validator("window_start", "window_end")
    @classmethod
    def _times(cls, v: str) -> str:
        return _hhmm(v)


class AuditSettings(SettingsModel):
    timeout_ms: int = Field(default_factory=lambda: get_settings().website_audit_timeout, ge=1000, le=60000)
    max_pages: int = Field(default=4, ge=1, le=10)
    max_concurrent: int = Field(default_factory=lambda: get_settings().max_concurrent_audits, ge=1, le=20)
    respect_robots: bool = True
    max_response_kb: int = Field(default=2048, ge=64, le=10240)
    slow_threshold_ms: int = Field(default=2500, ge=100)
    very_slow_threshold_ms: int = Field(default=5000, ge=200)
    cache_days: int = Field(default=14, ge=0, le=365)
    check_assets: bool = True
    max_asset_checks: int = Field(default=6, ge=0, le=20)
    pagespeed_enabled: bool = False


class SearchSettings(SettingsModel):
    default_max_results: int = Field(default=60, ge=1, le=1000)
    max_results_limit: int = Field(default=500, ge=1, le=2000)
    provider_concurrency: int = Field(default=2, ge=1, le=10)
    provider_requests_per_second: float = Field(default=5.0, gt=0, le=50)
    cache_ttl_hours: int = Field(default=24, ge=0, le=24 * 30)
    audit_after_search: bool = True


class CsvSettings(SettingsModel):
    delimiter: Literal[",", ";", "\t"] = ","
    include_bom: bool = True


class SkuPrice(SettingsModel):
    price_per_1000: float = Field(ge=0)
    free_per_month: int = Field(default=0, ge=0)


class PricingSettings(SettingsModel):
    currency: str = DEFAULT_PRICING_CURRENCY
    display_currency: str = "EUR"
    exchange_rate: float = Field(default=0.86, gt=0, description="Display-currency units per 1 pricing unit")
    skus: dict[str, SkuPrice] = Field(
        default_factory=lambda: {k: SkuPrice.model_validate(v) for k, v in DEFAULT_SKU_PRICES.items()}
    )


class RuntimeSettings(SettingsModel):
    general: GeneralSettings = Field(default_factory=GeneralSettings)
    calling: CallingSettings = Field(default_factory=CallingSettings)
    audit: AuditSettings = Field(default_factory=AuditSettings)
    search: SearchSettings = Field(default_factory=SearchSettings)
    csv: CsvSettings = Field(default_factory=CsvSettings)
    pricing: PricingSettings = Field(default_factory=PricingSettings)
    scoring: ScoringConfig = Field(default_factory=ScoringConfig)


GROUPS: tuple[str, ...] = tuple(RuntimeSettings.model_fields.keys())

_cache: tuple[float, RuntimeSettings] | None = None
_CACHE_SECONDS = 5.0


def invalidate_cache() -> None:
    global _cache
    _cache = None


async def load_settings(session: AsyncSession, use_cache: bool = True) -> RuntimeSettings:
    global _cache
    now = time.monotonic()
    if use_cache and _cache and now - _cache[0] < _CACHE_SECONDS:
        return _cache[1]
    rows = (await session.execute(select(AppSetting))).scalars().all()
    data: dict[str, Any] = {row.key: row.value for row in rows if row.key in GROUPS}
    settings = RuntimeSettings.model_validate(data)
    _cache = (now, settings)
    return settings


async def update_settings(
    session: AsyncSession, patch: dict[str, dict[str, Any]], user_id: int | None
) -> RuntimeSettings:
    """Deep-merge a partial update per group, validate the result, then persist."""
    current = await load_settings(session, use_cache=False)
    merged = current.model_dump(mode="json")
    for group, values in patch.items():
        if group not in GROUPS:
            raise ValueError(f"Unknown settings group '{group}'")
        merged[group] = _deep_merge(merged[group], values)
    validated = RuntimeSettings.model_validate(merged)
    dumped = validated.model_dump(mode="json")
    for group in patch:
        row = await session.get(AppSetting, group)
        if row is None:
            session.add(AppSetting(key=group, value=dumped[group], updated_by_id=user_id))
        else:
            row.value = dumped[group]
            row.updated_by_id = user_id
    await session.commit()
    invalidate_cache()
    return validated


def _deep_merge(base: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    out = dict(base)
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out
