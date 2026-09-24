"""Search job pipeline:

    provider search (paged, cached) → save/dedupe businesses → phone normalization
    → score → website audits (bounded concurrency) → re-score → done

One failing website or query never fails the whole job; the job ends
``completed``, ``partial`` (some errors), ``failed`` (nothing usable) or
``cancelled``.
"""

from __future__ import annotations

import asyncio
import contextlib
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.factory import build_auditor
from app.core.enums import JobStatus
from app.core.opening_hours import open_in_window_on_weekdays, parse_hhmm
from app.log import get_logger
from app.models import Business, JobBusiness, NichePreset, SearchQuery
from app.providers.base import (
    ProviderAuthError,
    ProviderError,
    ProviderNotConfiguredError,
    ProviderPermissionError,
    ProviderQuotaError,
    SearchParams,
)
from app.providers.registry import get_provider
from app.scoring.inputs import NicheInfo
from app.services.audits import needs_audit, persist_audit, run_audit
from app.services.businesses import record_from_place, upsert_business
from app.services.presets import load_niches
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


class SearchRequest(BaseModel):
    """Parameters of a search job (also the POST /api/search body)."""

    category: str = Field(min_length=2, max_length=120)
    location: str = Field(min_length=2, max_length=120)
    neighborhoods: list[str] = Field(default_factory=list, max_length=60)
    keywords: str | None = Field(default=None, max_length=120)
    preset_key: str | None = Field(default=None, max_length=64)
    min_rating: float | None = Field(default=4.0, ge=0, le=5)
    min_reviews: int | None = Field(default=None, ge=0)
    max_reviews: int | None = Field(default=None, ge=0)
    has_website: Literal["any", "yes", "no"] = "any"
    open_in_window: bool = False
    window_start: str | None = None
    window_end: str | None = None
    lead_quality: Literal["any", "high", "medium", "low"] = "any"
    max_results: int = Field(default=60, ge=1, le=2000)
    audit_websites: bool = True
    country: str | None = Field(default=None, min_length=2, max_length=2)
    language: str | None = Field(default=None, max_length=10)

    @field_validator("category", "location", "keywords")
    @classmethod
    def _strip(cls, v: str | None) -> str | None:
        return v.strip() if isinstance(v, str) else v

    @field_validator("neighborhoods")
    @classmethod
    def _clean_neighborhoods(cls, v: list[str]) -> list[str]:
        return list(dict.fromkeys(n.strip() for n in v if n and n.strip()))

    @field_validator("window_start", "window_end")
    @classmethod
    def _time(cls, v: str | None) -> str | None:
        if v:
            parse_hhmm(v)
        return v

    @model_validator(mode="after")
    def _reviews_range(self) -> SearchRequest:
        if (
            self.min_reviews is not None
            and self.max_reviews is not None
            and self.min_reviews > self.max_reviews
        ):
            raise ValueError("min_reviews cannot be greater than max_reviews")
        return self


@dataclass(slots=True)
class PlannedQuery:
    text: str
    location: str


def plan_queries(req: SearchRequest) -> list[PlannedQuery]:
    base = req.category if not req.keywords else f"{req.category} {req.keywords}"
    locations = [f"{n}, {req.location}" for n in req.neighborhoods] or [req.location]
    seen: dict[str, PlannedQuery] = {}
    for loc in locations:
        text = f"{base} in {loc}"
        seen.setdefault(text.lower(), PlannedQuery(text=text, location=loc))
    return list(seen.values())


def estimate_requests(req: SearchRequest) -> dict[str, int]:
    queries = plan_queries(req)
    per_query_pages = min(3, -(-req.max_results // PAGE_SIZE))  # Text Search returns at most 60 results
    max_requests = min(len(queries) * per_query_pages, -(-req.max_results // PAGE_SIZE) + len(queries) - 1)
    return {"queries": len(queries), "max_requests": max(1, max_requests)}


def matches_filters(business: Business, req: SearchRequest, window: tuple[str, str]) -> bool:
    if (
        req.min_rating is not None
        and req.min_rating > 0
        and (business.rating is None or business.rating < req.min_rating)
    ):
        return False
    if req.min_reviews is not None and (business.review_count or 0) < req.min_reviews:
        return False
    if req.max_reviews is not None and (business.review_count or 0) > req.max_reviews:
        return False
    has_own_site = bool(business.website_url) and business.website_kind == "own"
    if req.has_website == "yes" and not has_own_site:
        return False
    if req.has_website == "no" and has_own_site:
        return False
    if req.open_in_window:
        periods = (business.opening_hours or {}).get("periods")
        if not open_in_window_on_weekdays(periods, window[0], window[1], min_days=1):
            return False
    return True


async def _preset(session: AsyncSession, key: str | None) -> NichePreset | None:
    if not key:
        return None
    return (await session.execute(select(NichePreset).where(NichePreset.key == key))).scalar_one_or_none()


def _search_checkpoint(ctx: JobContext, next_query: int, found_ids: set[int], to_audit: list[int]) -> None:
    ctx.checkpoint = {
        "phase": "search",
        "next_query": next_query,
        "found_ids": sorted(found_ids),
        "to_audit": list(to_audit),
    }


async def run_search_job(ctx: JobContext) -> JobOutcome:
    """Resumable: a time-boxed run stops between queries (search phase) or between
    audits (audit phase) and continues from ``ctx.checkpoint`` on the next run."""
    req = SearchRequest.model_validate(ctx.params)
    async with ctx.sessionmaker() as session:
        runtime = await load_settings(session, use_cache=False)
        niches = await load_niches(session)
        preset = await _preset(session, req.preset_key)
    window = (
        req.window_start or (preset.calling_window_start if preset else None) or runtime.calling.window_start,
        req.window_end or (preset.calling_window_end if preset else None) or runtime.calling.window_end,
    )
    queries = plan_queries(req)
    checkpoint = dict(ctx.checkpoint)
    phase = checkpoint.get("phase", "search")
    next_query = int(checkpoint.get("next_query", 0))
    found_ids: set[int] = {int(i) for i in checkpoint.get("found_ids", [])}
    to_audit: list[int] = [int(i) for i in checkpoint.get("to_audit", [])]
    if ctx.resumed:
        log.info("search_job_resumed", job_id=ctx.job_id, phase=phase, next_query=next_query)
    else:
        log.info("search_job_started", job_id=ctx.job_id, category=req.category, location=req.location)
        ctx.counters.update({"queries_planned": len(queries)})
        ctx.total = 0

    fatal: ProviderError | None = None
    try:
        if phase == "search":
            provider = get_provider(runtime.search.provider_requests_per_second)
            gateway = ProviderGateway(provider, ctx.sessionmaker)
            _search_checkpoint(ctx, next_query, found_ids, to_audit)
            await ctx.flush("searching")
            for index in range(next_query, len(queries)):
                planned = queries[index]
                if len(found_ids) >= req.max_results:
                    break
                await ctx.check_cancelled()
                _search_checkpoint(ctx, index, found_ids, to_audit)
                if index > next_query:
                    ctx.check_time()
                try:
                    await _run_query(
                        ctx, gateway, planned, req, runtime, niches, preset, window, found_ids, to_audit
                    )
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
            await audit_businesses(ctx, to_audit, runtime, niches, force=False)
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
    niches: list[NicheInfo],
    preset: NichePreset | None,
    window: tuple[str, str],
    found_ids: set[int],
    to_audit: list[int],
) -> None:
    params = SearchParams(
        text_query=planned.text,
        region_code=(req.country or runtime.general.default_country).upper(),
        language_code=req.language or runtime.general.provider_language,
        min_rating=req.min_rating,
        included_type=preset.included_type if preset else None,
        page_size=PAGE_SIZE,
    )
    remaining = req.max_results - len(found_ids)
    pages = 0
    results = 0
    cached = False
    error: ProviderError | None = None
    region = (req.country or runtime.general.default_country).upper()
    try:
        async with contextlib.aclosing(
            gateway.iter_search(
                params,
                max_results=min(60, max(remaining, 1)),
                cache_ttl_hours=runtime.search.cache_ttl_hours,
                job_id=ctx.job_id,
            )
        ) as pages_iter:
            async for page in pages_iter:
                pages += 1
                cached = page.cached
                results += len(page.places)
                if page.cached:
                    ctx.incr("cached_requests")
                else:
                    ctx.incr("api_requests")
                await _save_page(
                    ctx,
                    page.places,
                    req,
                    runtime,
                    niches,
                    preset,
                    window,
                    region,
                    planned.text,
                    found_ids,
                    to_audit,
                )
                ctx.checkpoint["found_ids"] = sorted(found_ids)
                ctx.checkpoint["to_audit"] = list(to_audit)
                await ctx.flush()
                if len(found_ids) >= req.max_results:
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


async def _save_page(
    ctx: JobContext,
    places: list[Any],
    req: SearchRequest,
    runtime: RuntimeSettings,
    niches: list[NicheInfo],
    preset: NichePreset | None,
    window: tuple[str, str],
    region: str,
    query_text: str,
    found_ids: set[int],
    to_audit: list[int],
) -> None:
    async with ctx.sessionmaker() as session:
        for place in places:
            if len(found_ids) >= req.max_results:
                break
            outcome = await upsert_business(
                session,
                record_from_place(place),
                default_region=region,
                niche_key=preset.key if preset else None,
                user_id=ctx.created_by_id,
            )
            business = outcome.business
            if business.id in found_ids:
                ctx.incr("duplicates_in_job")
                continue
            found_ids.add(business.id)
            ctx.total += 1
            ctx.incr("new" if outcome.created else "existing")
            matched = matches_filters(business, req, window)
            ctx.incr("matched" if matched else "filtered_out")
            await session.execute(
                pg_insert(JobBusiness)
                .values(
                    job_id=ctx.job_id,
                    business_id=business.id,
                    is_new=outcome.created,
                    matched_filters=matched,
                    query=query_text[:500],
                )
                .on_conflict_do_nothing()
            )
            await rescore_business(session, business, runtime, niches)
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


async def audit_businesses(
    ctx: JobContext,
    business_ids: list[int],
    runtime: RuntimeSettings,
    niches: list[NicheInfo],
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
                expected = booking_expected(business, niches, runtime)
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
                    await rescore_business(session, business, runtime, niches, audit=audit)
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
        niches = await load_niches(session)
    if not ctx.resumed:
        ctx.total = len(ids)
    ctx.checkpoint = {"to_audit": ids}
    await ctx.flush("auditing")
    try:
        await audit_businesses(ctx, ids, runtime, niches, force=force)
    except JobCancelled:
        return JobOutcome(JobStatus.CANCELLED)
    return JobOutcome(JobStatus.COMPLETED)


async def run_rescore_job(ctx: JobContext) -> JobOutcome:
    ids: list[int] | None = ctx.params.get("business_ids")
    after_id = int(ctx.checkpoint.get("after_id", 0))
    async with ctx.sessionmaker() as session:
        runtime = await load_settings(session, use_cache=False)
        niches = await load_niches(session)
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
                await rescore_business(session, business, runtime, niches)
            await session.commit()
        ctx.processed += len(batch)
        ctx.checkpoint = {"after_id": batch[-1]}
        await ctx.flush()
    return JobOutcome(JobStatus.COMPLETED)
