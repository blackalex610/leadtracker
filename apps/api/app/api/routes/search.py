"""Search jobs: create, estimate cost, monitor, cancel, retry."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select

from app.api.deps import CurrentUser, SessionDep
from app.config import get_settings
from app.core.enums import TERMINAL_JOB_STATUSES, JobKind, JobStatus
from app.core.ratelimit import rate_limit, search_limiter
from app.models import Job, SearchQuery
from app.providers.base import ProviderNotConfiguredError
from app.providers.registry import get_provider, provider_status
from app.schemas.common import Page
from app.schemas.jobs import JobOut, SearchEstimate, SearchJobDetail, SearchQueryOut
from app.services.search import SearchRequest, estimate_requests
from app.services.settings import load_settings
from app.services.usage import monthly_usage
from app.worker.queue import enqueue

router = APIRouter(tags=["search"])


async def _job_or_404(session: SessionDep, job_id: int, kind: str | None = None) -> Job:
    job = await session.get(Job, job_id)
    if job is None or (kind and job.kind != kind):
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": "Job not found"})
    return job


def _require_provider() -> None:
    settings = get_settings()
    if not settings.demo_mode and not settings.provider_configured:
        raise ProviderNotConfiguredError()


@router.post("/search/estimate", response_model=SearchEstimate)
async def estimate(body: SearchRequest, session: SessionDep, _user: CurrentUser) -> SearchEstimate:
    runtime = await load_settings(session)
    status_info = provider_status()
    counts = estimate_requests(body)
    sku: str | None = None
    try:
        sku = get_provider().search_sku if status_info["configured"] else None
    except ProviderNotConfiguredError:
        sku = None
    price = runtime.pricing.skus.get(sku) if sku else None
    usage = await monthly_usage(session, runtime.pricing)
    used = next((line["units"] for line in usage["cost"]["lines"] if line["sku"] == sku), 0)
    free_remaining = max(0, price.free_per_month - used) if price else None
    cost = None
    if price is not None:
        billable = max(0, counts["max_requests"] - (free_remaining or 0))
        cost = round(billable * price.price_per_1000 / 1000, 4)
    return SearchEstimate(
        queries=counts["queries"],
        max_requests=counts["max_requests"],
        sku=sku,
        estimated_max_cost=cost,
        currency=runtime.pricing.currency,
        display_currency=runtime.pricing.display_currency,
        estimated_max_cost_display=round(cost * runtime.pricing.exchange_rate, 4)
        if cost is not None
        else None,
        free_units_remaining=free_remaining,
        provider_configured=bool(status_info["configured"]),
        demo_mode=bool(status_info["demo_mode"]),
    )


@router.post(
    "/search",
    response_model=JobOut,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(rate_limit(search_limiter, "search"))],
)
async def create_search(body: SearchRequest, session: SessionDep, user: CurrentUser) -> JobOut:
    _require_provider()
    runtime = await load_settings(session)
    if body.max_results > runtime.search.max_results_limit:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "max_results_exceeded",
                "message": f"max_results is limited to {runtime.search.max_results_limit} (Settings → Search)",
            },
        )
    job = await enqueue(session, JobKind.SEARCH, body.model_dump(mode="json"), created_by_id=user.id)
    await session.commit()
    await session.refresh(job)
    return JobOut.model_validate(job)


@router.get("/search-jobs", response_model=Page[JobOut])
async def list_search_jobs(
    session: SessionDep,
    _user: CurrentUser,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> Page[JobOut]:
    base = select(Job).where(Job.kind == JobKind.SEARCH.value)
    total = (await session.execute(select(func.count()).select_from(base.subquery()))).scalar_one()
    rows = (
        (
            await session.execute(
                base.order_by(Job.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
            )
        )
        .scalars()
        .all()
    )
    return Page(items=[JobOut.model_validate(j) for j in rows], total=total, page=page, page_size=page_size)


@router.get("/search-jobs/{job_id}", response_model=SearchJobDetail)
async def get_search_job(job_id: int, session: SessionDep, _user: CurrentUser) -> SearchJobDetail:
    job = await _job_or_404(session, job_id, JobKind.SEARCH.value)
    queries = (
        (
            await session.execute(
                select(SearchQuery).where(SearchQuery.job_id == job_id).order_by(SearchQuery.id)
            )
        )
        .scalars()
        .all()
    )
    detail = SearchJobDetail.model_validate(job)
    detail.queries = [SearchQueryOut.model_validate(q) for q in queries]
    return detail


@router.post("/search-jobs/{job_id}/cancel", response_model=JobOut)
@router.post("/jobs/{job_id}/cancel", response_model=JobOut, include_in_schema=False)
async def cancel_job(job_id: int, session: SessionDep, _user: CurrentUser) -> JobOut:
    job = await _job_or_404(session, job_id)
    if job.status in {s.value for s in TERMINAL_JOB_STATUSES}:
        raise HTTPException(
            status_code=409, detail={"code": "job_finished", "message": "Job already finished"}
        )
    job.cancel_requested = True
    if job.status == JobStatus.QUEUED.value:
        job.status = JobStatus.CANCELLED.value
        job.stage = "cancelled"
    await session.commit()
    await session.refresh(job)
    return JobOut.model_validate(job)


@router.post(
    "/search-jobs/{job_id}/retry",
    response_model=JobOut,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(rate_limit(search_limiter, "search"))],
)
async def retry_job(job_id: int, session: SessionDep, user: CurrentUser) -> JobOut:
    job = await _job_or_404(session, job_id, JobKind.SEARCH.value)
    if job.status not in (JobStatus.FAILED.value, JobStatus.PARTIAL.value, JobStatus.CANCELLED.value):
        raise HTTPException(
            status_code=409,
            detail={
                "code": "not_retryable",
                "message": "Only failed, partial or cancelled jobs can be retried",
            },
        )
    _require_provider()
    new_job = await enqueue(
        session, JobKind.SEARCH, dict(job.params), created_by_id=user.id, retry_of_id=job.id
    )
    await session.commit()
    await session.refresh(new_job)
    return JobOut.model_validate(new_job)


@router.get("/jobs/{job_id}", response_model=JobOut)
async def get_job(job_id: int, session: SessionDep, _user: CurrentUser) -> JobOut:
    return JobOut.model_validate(await _job_or_404(session, job_id))
