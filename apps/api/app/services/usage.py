"""API usage tracking and cost estimation.

Every provider request (and every cache hit) is recorded with its SKU. Costs are
estimated at read time from the configurable pricing table, including the
monthly free allowance per SKU.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ApiUsage
from app.services.settings import PricingSettings


async def record_usage(
    session: AsyncSession,
    *,
    provider: str,
    operation: str,
    sku: str | None,
    cached: bool = False,
    success: bool = True,
    units: int = 1,
    status_code: int | None = None,
    error_code: str | None = None,
    job_id: int | None = None,
) -> None:
    session.add(
        ApiUsage(
            provider=provider,
            operation=operation,
            sku=sku,
            units=units,
            cached=cached,
            success=success,
            status_code=status_code,
            error_code=error_code,
            job_id=job_id,
        )
    )


def month_start(now: datetime | None = None) -> datetime:
    now = now or datetime.now(UTC)
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def estimate_cost(units_by_sku: dict[str, int], pricing: PricingSettings) -> dict[str, Any]:
    lines = []
    total = 0.0
    for sku, units in sorted(units_by_sku.items()):
        price = pricing.skus.get(sku)
        if price is None:
            lines.append({"sku": sku, "units": units, "billable_units": units, "cost": None, "priced": False})
            continue
        billable = max(0, units - price.free_per_month)
        cost = billable * price.price_per_1000 / 1000
        total += cost
        lines.append(
            {
                "sku": sku,
                "units": units,
                "free_units": price.free_per_month,
                "billable_units": billable,
                "price_per_1000": price.price_per_1000,
                "cost": round(cost, 4),
                "priced": True,
            }
        )
    return {
        "currency": pricing.currency,
        "total": round(total, 4),
        "display_currency": pricing.display_currency,
        "display_total": round(total * pricing.exchange_rate, 4),
        "exchange_rate": pricing.exchange_rate,
        "lines": lines,
    }


async def monthly_usage(
    session: AsyncSession, pricing: PricingSettings, now: datetime | None = None
) -> dict[str, Any]:
    start = month_start(now)
    rows = (
        await session.execute(
            select(ApiUsage.sku, ApiUsage.operation, ApiUsage.cached, func.sum(ApiUsage.units), func.count())
            .where(ApiUsage.created_at >= start)
            .group_by(ApiUsage.sku, ApiUsage.operation, ApiUsage.cached)
        )
    ).all()
    billable_by_sku: dict[str, int] = {}
    api_calls = 0
    cached_calls = 0
    by_operation: dict[str, int] = {}
    for sku, operation, cached, units, count in rows:
        if cached:
            cached_calls += int(count)
            continue
        api_calls += int(count)
        by_operation[operation] = by_operation.get(operation, 0) + int(count)
        if sku:
            billable_by_sku[sku] = billable_by_sku.get(sku, 0) + int(units or 0)
    return {
        "period_start": start.isoformat(),
        "api_calls": api_calls,
        "cached_calls": cached_calls,
        "calls_by_operation": by_operation,
        "cost": estimate_cost(billable_by_sku, pricing),
    }
