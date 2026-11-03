"""Find-leads job pipeline. There are no niches to pick - the ICP target list decides:

    plan (ICP targets x city, then neighborhoods, minus queries run recently)
    → provider search (paged, cached) → save/dedupe businesses → phone normalization
    → score + categorize → ICP gate → website audits (bounded concurrency)
    → re-score/re-categorize → done

The job stops as soon as it has the requested number of fresh, callable ICP
leads. One failing website or query never fails the whole job; the job ends
``completed``, ``partial`` (some errors), ``failed`` (nothing usable) or
``cancelled``.
"""

from __future__ import annotations

import asyncio
import contextlib
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.factory import build_auditor
from app.core.enums import JobStatus, LeadCategory, LeadStatus
from app.data.locations import CITIES
from app.data.targets import TARGETS, TARGETS_BY_KEY
from app.log import get_logger
from app.models import Business, JobBusiness, SearchQuery
from app.providers.base import (
    ProviderAuthError,
    ProviderError,
    ProviderNotConfiguredError,
    ProviderPermissionError,
    ProviderQuotaError,
    SearchParams,
)
from app.providers.registry import get_provider
from app.services.audits import needs_audit, persist_audit, run_audit
from app.services.businesses import record_from_place, upsert_business
from app.services.provider_gateway import ProviderGateway
from app.services.scoring_service import booking_expected, rescore_business
from app.services.settings import RuntimeSettings, load_settings
from app.worker.queue import JobCancelled, JobContext, JobOutcome, JobYield

log = get_logger(__name__)

FATAL_PROVIDER_ERRORS = (
    ProviderNotConfiguredError,
    ProviderAuthError,
    ProviderPermissionError,
    ProviderQuotaError,
)
PAGE_SIZE = 20
PAGES_PER_QUERY = 3  # Text Search returns at most 60 results per query
# A query that ran this recently would return the same businesses again: skip it.
ROTATION_DAYS = 30


class SearchRequest(BaseModel):
    """Parameters of a find-leads job (also the POST /api/search body)."""

    location: str = Field(default="Sofia", min_length=2, max_length=120)
    target_leads: int = Field(default=150, ge=1, le=2000, description="Fresh ICP leads to find")
    max_queries: int = Field(default=30, ge=1, le=200, description="Cost cap: provider queries at most")
    use_neighborhoods: bool = Field(
        default=True, description="Search neighborhood by neighborhood once city-wide queries are used up"
    )
    audit_websites: bool = True
    country: str | None = Field(default=None, min_length=2, max_length=2)
    language: str | None = Field(default=None, max_length=10)

    @field_validator("location")
    @classmethod
    def _strip(cls, v: str) -> str:
        return v.strip()


@dataclass(slots=True)
class PlannedQuery:
    text: str
    location: str
    target_key: str


def canonical_city(location: str) -> str:
    return next((c for c in CITIES if c.lower() == location.strip().lower()), location.strip())


def candidate_queries(req: SearchRequest) -> list[PlannedQuery]:
    """Every ICP target city-wide first, then neighborhood by neighborhood."""
    city = canonical_city(req.location)
    areas = [city]
    if req.use_neighborhoods:
        areas += [f"{n}, {city}" for n in CITIES.get(city, [])]
    return [PlannedQuery(f"{t.query} в {area}", area, t.key) for area in areas for t in TARGETS]


async def recent_query_texts(session: AsyncSession, now: datetime | None = None) -> set[str]:
    since = (now or datetime.now(UTC)) - timedelta(days=ROTATION_DAYS)
    rows = await session.execute(
        select(func.lower(SearchQuery.text_query)).where(
            SearchQuery.status == "ok", SearchQuery.created_at >= since
        )
    )
    return set(rows.scalars())


async def plan_queries(session: AsyncSession, req: SearchRequest) -> list[PlannedQuery]:
    recent = await recent_query_texts(session)
    fresh = [q for q in candidate_queries(req) if q.text.lower() not in recent]
    return fresh[: req.max_queries]


def estimate_requests(planned: int) -> dict[str, int]:
    return {"queries": planned, "max_requests": planned * PAGES_PER_QUERY}


def icp_reject_reason(business: Business) -> str | None:
    """Why a business is not a callable ICP lead (None = it is one)."""
    if not business.normalized_phone or business.phone_invalid:
        return "no_phone"
    if business.suppressed or business.status == LeadStatus.DO_NOT_CONTACT.value:
        return "do_not_contact"
    if business.lead_category == LeadCategory.NOT_A_FIT.value:
        return "not_a_fit"
    return None


def _lead_weight(business: Business) -> float:
    """How surely a lead counts toward the target before its website is audited:
    a site still to be checked often turns out fine, so it counts half."""
    return 0.5 if business.lead_category == LeadCategory.UNCHECKED.value else 1.0


def _search_checkpoint(
    ctx: JobContext,
    plan: list[PlannedQuery],
    next_query: int,
    found_ids: set[int],
    to_audit: list[int],
    leads: float,
) -> None:
    ctx.checkpoint = {
        "phase": "search",
        "plan": [asdict(q) for q in plan],
        "next_query": next_query,
        "found_ids": sorted(found_ids),
        "to_audit": list(to_audit),
        "leads": leads,
    }


async def run_search_job(ctx: JobContext) -> JobOutcome:
    """Resumable: a time-boxed run stops between queries (search phase) or between
    audits (audit phase) and continues from ``ctx.checkpoint`` on the next run."""
    req = SearchRequest.model_validate(ctx.params)
    checkpoint = dict(ctx.checkpoint)
    async with ctx.sessionmaker() as session:
        runtime = await load_settings(session, use_cache=False)
        if "plan" in checkpoint:
            plan = [PlannedQuery(**q) for q in checkpoint["plan"]]
        else:
            plan = await plan_queries(session, req)
    phase = checkpoint.get("phase", "search")
    next_query = int(checkpoint.get("next_query", 0))
    found_ids: set[int] = {int(i) for i in checkpoint.get("found_ids", [])}
    to_audit: list[int] = [int(i) for i in checkpoint.get("to_audit", [])]
    leads = float(checkpoint.get("leads", 0))
    if ctx.resumed:
        log.info("search_job_resumed", job_id=ctx.job_id, phase=phase, next_query=next_query)
    else:
        log.info("search_job_started", job_id=ctx.job_id, location=req.location, planned=len(plan))
        ctx.counters.update({"queries_planned": len(plan), "target_leads": req.target_leads})
        ctx.total = 0
        if not plan:
            ctx.add_error(
                "no_fresh_queries",
                f"Every search for {req.location} already ran in the last {ROTATION_DAYS} days. "
                "Try another city, or call the leads you already have.",
            )
            return JobOutcome(JobStatus.COMPLETED, {"found": 0})

    fatal: ProviderError | None = None
    try:
        if phase == "search":
            provider = get_provider(runtime.search.provider_requests_per_second)
            gateway = ProviderGateway(provider, ctx.sessionmaker)
            _search_checkpoint(ctx, plan, next_query, found_ids, to_audit, leads)
            await ctx.flush("searching")
            for index in range(next_query, len(plan)):
                planned = plan[index]
                if leads >= req.target_leads:
                    break
                await ctx.check_cancelled()
                _search_checkpoint(ctx, plan, index, found_ids, to_audit, leads)
                if index > next_query:
                    ctx.check_time()
                try:
                    leads = await _run_query(ctx, gateway, planned, req, runtime, found_ids, to_audit, leads)
                except FATAL_PROVIDER_ERRORS as exc:
                    fatal = exc
                    break
                except ProviderError as exc:
                    ctx.add_error(exc.code, exc.message, query=planned.text)
                    log.warning("provider_error", job_id=ctx.job_id, code=exc.code, query=planned.text)
            found_count = len(found_ids)
        else:
            found_count = int(checkpoint.get("found", 0))

        if fatal is None and to_audit and req.audit_websites and runtime.search.audit_after_search:
            ctx.checkpoint = {"phase": "audit", "found": found_count, "to_audit": to_audit}
            await ctx.flush("auditing")
            await audit_businesses(ctx, to_audit, runtime, force=False)
    except JobCancelled:
        await ctx.flush("cancelled")
        return JobOutcome(JobStatus.CANCELLED, {"found": len(found_ids) or int(checkpoint.get("found", 0))})

    result = {"found": found_count}
    if fatal is not None:
        ctx.add_error(fatal.code, fatal.message)
        status = JobStatus.PARTIAL if found_count else JobStatus.FAILED
        return JobOutcome(status, result, fatal.code, fatal.message)
    if ctx.errors and not found_count and not ctx.counters.get("queries_ok"):
        first = ctx.errors[0]
        return JobOutcome(JobStatus.FAILED, result, first.get("code"), first.get("message"))
    provider_errors = [e for e in ctx.errors if e.get("query")]
    return JobOutcome(JobStatus.PARTIAL if provider_errors else JobStatus.COMPLETED, result)


async def _run_query(
    ctx: JobContext,
    gateway: ProviderGateway,
    planned: PlannedQuery,
    req: SearchRequest,
    runtime: RuntimeSettings,
    found_ids: set[int],
    to_audit: list[int],
    leads: float,
) -> float:
    target = TARGETS_BY_KEY.get(planned.target_key)
    region = (req.country or runtime.general.default_country).upper()
    params = SearchParams(
        text_query=planned.text,
        region_code=region,
        language_code=req.language or runtime.general.provider_language,
        included_type=target.included_type if target else None,
        page_size=PAGE_SIZE,
    )
    pages = 0
    results = 0
    cached = False
    error: ProviderError | None = None
    try:
        async with contextlib.aclosing(
            gateway.iter_search(
                params,
                max_results=PAGE_SIZE * PAGES_PER_QUERY,
                cache_ttl_hours=runtime.search.cache_ttl_hours,
                job_id=ctx.job_id,
            )
        ) as pages_iter:
            async for page in pages_iter:
                pages += 1
                cached = page.cached
                results += len(page.places)
                ctx.incr("cached_requests" if page.cached else "api_requests")
                leads = await _save_page(
                    ctx, page.places, req, runtime, planned, region, found_ids, to_audit, leads
                )
                ctx.checkpoint["found_ids"] = sorted(found_ids)
                ctx.checkpoint["to_audit"] = list(to_audit)
                ctx.checkpoint["leads"] = leads
                await ctx.flush()
                if leads >= req.target_leads:
                    break
                await ctx.check_cancelled()
        ctx.incr("queries_ok")
    except ProviderError as exc:
        error = exc
        raise
    finally:
        async with ctx.sessionmaker() as session:
            session.add(
                SearchQuery(
                    job_id=ctx.job_id,
                    text_query=planned.text[:500],
                    params=params.cache_identity(),
                    pages_fetched=pages,
                    results_count=results,
                    cached=cached,
                    status="failed" if error else "ok",
                    error_code=error.code if error else None,
                    error_message=error.message if error else None,
                )
            )
            await session.commit()
    return leads


async def _save_page(
    ctx: JobContext,
    places: list[Any],
    req: SearchRequest,
    runtime: RuntimeSettings,
    planned: PlannedQuery,
    region: str,
    found_ids: set[int],
    to_audit: list[int],
    leads: float,
) -> float:
    async with ctx.sessionmaker() as session:
        for place in places:
            if leads >= req.target_leads:
                break
            outcome = await upsert_business(
                session,
                record_from_place(place),
                default_region=region,
                target_key=planned.target_key,
                user_id=ctx.created_by_id,
            )
            business = outcome.business
            if business.id in found_ids:
                ctx.incr("duplicates_in_job")
                continue
            found_ids.add(business.id)
            ctx.total += 1
            await rescore_business(session, business, runtime)
            # Only businesses new to the database count: known ones are already in the lead list.
            reject = icp_reject_reason(business) if outcome.created else "already_known"
            matched = reject is None
            ctx.incr("new" if outcome.created else "existing")
            if matched:
                ctx.incr("matched")
                leads += _lead_weight(business)
            else:
                ctx.incr("filtered_out")
                ctx.incr(f"rejected_{reject}")
            await session.execute(
                pg_insert(JobBusiness)
                .values(
                    job_id=ctx.job_id,
                    business_id=business.id,
                    is_new=outcome.created,
                    matched_filters=matched,
                    query=planned.text[:500],
                )
                .on_conflict_do_nothing()
            )
            if (
                matched
                and req.audit_websites
                and runtime.search.audit_after_search
                and needs_audit(business, runtime.audit.cache_days)
            ):
                to_audit.append(business.id)
            else:
                if business.website_url and business.website_kind == "own" and matched:
                    ctx.incr("audit_cached")
                ctx.processed += 1
        await session.commit()
    return leads


async def _drop_if_out(session: AsyncSession, ctx: JobContext, business: Business) -> None:
    """After an audit: a lead whose site turned out fine leaves the job's results."""
    if icp_reject_reason(business) is None:
        return
    dropped = await session.execute(
        update(JobBusiness)
        .where(
            JobBusiness.job_id == ctx.job_id,
            JobBusiness.business_id == business.id,
            JobBusiness.matched_filters.is_(True),
        )
        .values(matched_filters=False)
    )
    if getattr(dropped, "rowcount", 0):
        ctx.incr("dropped_after_audit")


async def audit_businesses(
    ctx: JobContext,
    business_ids: list[int],
    runtime: RuntimeSettings,
    *,
    force: bool,
) -> None:
    """Audit concurrently. Once the run is out of time no new audit starts; the ones
    not started stay in ``ctx.checkpoint["to_audit"]`` and the job yields."""
    auditor = build_auditor(runtime.audit)
    semaphore = asyncio.Semaphore(runtime.audit.max_concurrent)
    lock = asyncio.Lock()
    done: set[int] = set()

    def remember_remaining() -> None:
        ctx.checkpoint["to_audit"] = [i for i in business_ids if i not in done]

    async def one(business_id: int) -> None:
        async with semaphore:
            # Each run audits at least one batch, so a short time budget still makes progress.
            if (done and ctx.out_of_time()) or await ctx.cancelled():
                return
            async with ctx.sessionmaker() as session:
                business = await session.get(Business, business_id)
                if business is None or not needs_audit(business, runtime.audit.cache_days, force=force):
                    async with lock:
                        done.add(business_id)
                        ctx.processed += 1
                        ctx.incr("audit_cached")
                    return
                expected = booking_expected(business, runtime)
                website = business.website_url
                country = business.country_code or runtime.general.default_country
            try:
                # Network work happens outside any DB session/connection.
                assert website
                result = await run_audit(auditor, website, booking_expected=expected, country_code=country)
                async with ctx.sessionmaker() as session:
                    business = await session.get(Business, business_id)
                    if business is None:
                        return
                    audit = await persist_audit(session, business, result, job_id=ctx.job_id)
                    await rescore_business(session, business, runtime, audit=audit)
                    await _drop_if_out(session, ctx, business)
                    await session.commit()
                async with lock:
                    ctx.incr("audited")
                    if result.status.value != "success":
                        ctx.incr("audit_failed" if result.status.value == "failed" else "audit_skipped")
            except Exception as exc:  # never let one site kill the job
                log.exception("website_audit_failed", business_id=business_id, error=type(exc).__name__)
                async with lock:
                    ctx.incr("audit_failed")
                    ctx.add_error(
                        "audit_error", f"Audit failed for business {business_id}: {type(exc).__name__}"
                    )
            finally:
                async with lock:
                    done.add(business_id)
                    ctx.processed += 1
                    remember_remaining()
                    await ctx.flush()

    try:
        await asyncio.gather(*(one(bid) for bid in business_ids))
    finally:
        await auditor.fetcher.aclose()
    remember_remaining()
    await ctx.check_cancelled()
    if ctx.checkpoint["to_audit"]:
        raise JobYield()


async def run_audit_job(ctx: JobContext) -> JobOutcome:
    ids = [int(i) for i in ctx.checkpoint.get("to_audit", ctx.params.get("business_ids", []))]
    force = bool(ctx.params.get("force", True))
    async with ctx.sessionmaker() as session:
        runtime = await load_settings(session, use_cache=False)
    if not ctx.resumed:
        ctx.total = len(ids)
    ctx.checkpoint = {"to_audit": ids}
    await ctx.flush("auditing")
    try:
        await audit_businesses(ctx, ids, runtime, force=force)
    except JobCancelled:
        return JobOutcome(JobStatus.CANCELLED)
    return JobOutcome(JobStatus.COMPLETED)


async def run_rescore_job(ctx: JobContext) -> JobOutcome:
    ids: list[int] | None = ctx.params.get("business_ids")
    after_id = int(ctx.checkpoint.get("after_id", 0))
    async with ctx.sessionmaker() as session:
        runtime = await load_settings(session, use_cache=False)
        query = select(Business.id).where(Business.id > after_id).order_by(Business.id)
        if ids:
            query = query.where(Business.id.in_(ids))
        all_ids = list((await session.execute(query)).scalars())
    if not ctx.resumed:
        ctx.total = len(all_ids)
    await ctx.flush("scoring")
    for start in range(0, len(all_ids), 200):
        if await ctx.cancelled():
            return JobOutcome(JobStatus.CANCELLED)
        if start > 0:
            ctx.check_time()
        batch = all_ids[start : start + 200]
        async with ctx.sessionmaker() as session:
            businesses = (
                (await session.execute(select(Business).where(Business.id.in_(batch)))).scalars().all()
            )
            for business in businesses:
                await rescore_business(session, business, runtime)
            await session.commit()
        ctx.processed += len(batch)
        ctx.checkpoint = {"after_id": batch[-1]}
        await ctx.flush()
    return JobOutcome(JobStatus.COMPLETED)
