"""Infrastructure configuration loaded from environment variables.

Runtime-editable preferences (scoring weights, calling hours, audit limits, ...)
live in the database and are managed by ``app.services.settings``. Values here
act as their initial defaults where relevant. Secrets (provider API keys, the
session secret) are only ever read from the environment.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

_API_DIR = Path(__file__).resolve().parent.parent
_REPO_ROOT = _API_DIR.parent.parent

INSECURE_DEFAULT_SECRET = "dev-insecure-secret-change-me"  # noqa: S105 - sentinel, rejected in token mode


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(str(_REPO_ROOT / ".env"), str(_API_DIR / ".env")),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    environment: Literal["development", "test", "production"] = "development"
    app_version: str = "1.0.0"

    database_url: str = "postgresql+asyncpg://leadtracker:leadtracker@localhost:5432/leadtracker"
    database_pool_size: int = 10

    # --- Business data provider -------------------------------------------------
    provider: Literal["google_places"] = "google_places"
    provider_api_key: SecretStr | None = Field(default=None)
    provider_base_url: str = "https://places.googleapis.com/v1"
    provider_timeout_seconds: float = 20.0
    # "enterprise" returns phone/website/rating/hours in the Text Search call itself.
    # "enterprise_atmosphere" additionally requests the editorial description (more expensive).
    places_field_tier: Literal["enterprise", "enterprise_atmosphere"] = "enterprise"
    demo_mode: bool = False

    default_country: str = "BG"
    default_city: str = "Sofia"
    default_language: str = "bg"
    timezone: str = "Europe/Sofia"

    # --- Website auditing -------------------------------------------------------
    website_audit_timeout: int = 10000  # milliseconds, per request
    max_concurrent_audits: int = 5
    audit_user_agent: str = "LeadTrackerAudit/1.0 (+website-audit; respects robots.txt)"
    pagespeed_api_key: SecretStr | None = None

    # --- Server -----------------------------------------------------------------
    cors_origins: Annotated[list[str], NoDecode] = ["http://localhost:5173", "http://127.0.0.1:5173"]
    run_worker: bool = True
    worker_concurrency: int = 2
    worker_poll_interval_seconds: float = 1.0

    auth_mode: Literal["none", "token"] = "none"
    secret_key: SecretStr = SecretStr(INSECURE_DEFAULT_SECRET)
    session_cookie_name: str = "lt_session"
    session_cookie_secure: bool = False
    session_cookie_samesite: Literal["lax", "strict", "none"] = "lax"
    session_max_age_hours: int = 24 * 14

    log_level: str = "INFO"
    log_json: bool | None = None

    # Google Maps Platform terms allow caching lat/lng for at most 30 days.
    google_latlng_retention_days: int = 30

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [part.strip() for part in value.split(",") if part.strip()]
        return value

    @field_validator("provider_api_key", "pagespeed_api_key", mode="before")
    @classmethod
    def _empty_secret_is_none(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator("database_url")
    @classmethod
    def _asyncpg_url(cls, value: str) -> str:
        """Accept the plain URLs managed providers hand out (postgres://, ?sslmode=...)."""
        for prefix in ("postgres://", "postgresql://"):
            if value.startswith(prefix):
                value = "postgresql+asyncpg://" + value[len(prefix) :]
        return value.replace("sslmode=", "ssl=")

    @field_validator("secret_key", mode="before")
    @classmethod
    def _empty_secret_key(cls, value: object) -> object:
        if value is None or (isinstance(value, str) and not value.strip()):
            return INSECURE_DEFAULT_SECRET
        return value

    @field_validator("default_country")
    @classmethod
    def _upper_country(cls, value: str) -> str:
        return value.strip().upper()

    @model_validator(mode="after")
    def _check_security(self) -> Settings:
        secret = self.secret_key.get_secret_value()
        if self.auth_mode == "token" and (secret == INSECURE_DEFAULT_SECRET or len(secret) < 32):
            raise ValueError(
                "SECRET_KEY must be a random value of at least 32 characters when AUTH_MODE=token"
            )
        if self.session_cookie_samesite == "none" and not self.session_cookie_secure:
            raise ValueError("SESSION_COOKIE_SECURE must be true when SESSION_COOKIE_SAMESITE=none")
        return self

    @property
    def provider_configured(self) -> bool:
        return self.provider_api_key is not None

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def use_json_logs(self) -> bool:
        return self.log_json if self.log_json is not None else self.is_production


@lru_cache
def get_settings() -> Settings:
    return Settings()
