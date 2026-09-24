"""Background-job processing endpoints for serverless deployments."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request

from app.api.deps import CurrentUser
from app.config import get_settings
from app.core.ratelimit import rate_limit, worker_limiter
from app.core.security import tokens_equal
from app.db import get_sessionmaker
from app.schemas.misc import WorkerRunOut
from app.worker.on_demand import drain, queue_counts
from app.worker.runner import run_maintenance

router = APIRouter(tags=["worker"])

# Time kept free after the budget for audits already in flight to finish.
IN_FLIGHT_RESERVE_SECONDS = 90.0
MIN_BUDGET_SECONDS = 5.0


def slice_budget(request: Request, configured: float) -> float:
    """The configured budget, shortened when the platform reports an earlier
    invocation deadline (Vercel: ``x-vercel-internal-deadline``, RFC 3339)."""
    raw = request.headers.get("x-vercel-internal-deadline")
    if not raw:
        return configured
    try:
        deadline = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return configured
    if deadline.tzinfo is None:
        return configured
    remaining = (deadline - datetime.now(UTC)).total_seconds() - IN_FLIGHT_RESERVE_SECONDS
    return max(MIN_BUDGET_SECONDS, min(configured, remaining))


@router.post(
    "/worker/run",
    response_model=WorkerRunOut,
    dependencies=[Depends(rate_limit(worker_limiter, "worker"))],
)
async def run_jobs(request: Request, _user: CurrentUser) -> WorkerRunOut:
    """Process queued jobs for up to WORKER_RUN_BUDGET_SECONDS (serverless mode only;
    otherwise a resident worker does the work and this just reports the queue)."""
    settings = get_settings()
    sessionmaker = get_sessionmaker()
    if not settings.on_demand_worker:
        return WorkerRunOut(ran=0, on_demand=False, **await queue_counts(sessionmaker))
    budget = slice_budget(request, settings.worker_run_budget_seconds)
    return WorkerRunOut(on_demand=True, **await drain(sessionmaker, budget))


@router.get("/worker/cron", include_in_schema=False)
async def cron(request: Request) -> dict[str, Any]:
    """Daily safety net (Vercel Cron): maintenance plus any jobs nobody picked up.
    Vercel sends ``Authorization: Bearer $CRON_SECRET``."""
    settings = get_settings()
    secret = settings.cron_secret
    header = request.headers.get("authorization", "")
    if secret is None or not tokens_equal(header, f"Bearer {secret.get_secret_value()}"):
        raise HTTPException(
            status_code=401, detail={"code": "unauthorized", "message": "Invalid cron secret"}
        )
    sessionmaker = get_sessionmaker()
    maintenance = await run_maintenance(sessionmaker)
    jobs = (
        await drain(sessionmaker, slice_budget(request, settings.worker_run_budget_seconds))
        if settings.on_demand_worker
        else await queue_counts(sessionmaker)
    )
    return {"maintenance": maintenance, "jobs": jobs}
