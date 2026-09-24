"""Lead listing (server-side filtering, sorting, pagination) and detail assembly."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field
from sqlalchemy import Select, and_, func, not_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import (
    GOOGLE_OPPORTUNITIES,
    WEBSITE_PROBLEM_OPPORTUNITIES,
    JobStatus,
    LeadStatus,
    OpportunityType,
    Priority,
)
from app.core.opening_hours import is_open_during, python_weekday_to_places
from app.models import (
    Business,
    BusinessContact,
    BusinessSource,
    CallAttempt,
    Job,
    JobBusiness,
    LeadEvent,
    Note,
    User,
    WebsiteAudit,
)
from app.schemas.leads import (
    AuditOut,
    CallOut,
    ContactOut,
    EventOut,
    LeadDetail,
    LeadSummary,
    NoteOut,
    PitchOut,
    SortField,
    SourceOut,
    UserRef,
)
from app.scoring.data_quality import data_quality
from app.services.presets import load_niches, resolve_niche
from app.services.scoring_service import pitch_for
from app.services.settings import RuntimeSettings

WEBSITE_PROBLEM_HEALTH = 60
_DETAIL_COMPUTED = {
    "top_reason",
    "niche_label",
    "data_quality_checklist",
    "contacts",
    "audit",
    "pitches",
    "calls",
    "notes",
    "events",
    "sources",
    "assigned_to",
    "created_by",
    "last_contacted_by",
    "open_today_in_window",
    "active_job_id",
}


class LeadFilters(BaseModel):
    q: str | None = Field(default=None, max_length=200)
    priority: list[Priority] = Field(default_factory=list)
    status: list[LeadStatus] = Field(default_factory=list)
    opportunity: list[OpportunityType] = Field(default_factory=list)
    category: str | None = None
    niche_key: str | None = None
    city: str | None = None
    has_phone: bool | None = None
    has_website: bool | None = None
    website_problems: bool | None = None
    google_opportunity: bool | None = None
    contacted: bool | None = None
    min_rating: float | None = Field(default=None, ge=0, le=5)
    min_reviews: int | None = Field(default=None, ge=0)
    max_reviews: int | None = Field(default=None, ge=0)
    min_score: int | None = Field(default=None, ge=0, le=100)
    open_in_window: bool | None = None
    callback_due: bool | None = None
    assigned_to: str | None = None
    job_id: int | None = None
    job_matched_only: bool = True
    include_suppressed: bool = True
    include_demo: bool = True


class LeadExportQuery(LeadFilters):
    sort: SortField = "priority"
    order: Literal["asc", "desc"] = "desc"


class LeadListQuery(LeadExportQuery):
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=50, ge=1, le=200)


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def apply_filters(stmt: Select[Any], f: LeadFilters, user_id: int | None = None) -> Select[Any]:
    conditions: list[Any] = []
    if f.q:
        term = f.q.strip()
        like = f"%{_escape_like(term)}%"
        digits = "".join(ch for ch in term if ch.isdigit())
        options = [
            Business.name.ilike(like, escape="\\"),
            Business.address.ilike(like, escape="\\"),
            Business.website_domain.ilike(like, escape="\\"),
            Business.category.ilike(like, escape="\\"),
        ]
        if len(digits) >= 4:
            options.append(Business.normalized_phone.like(f"%{digits.lstrip('0')}%"))
        conditions.append(or_(*options))
    if f.priority:
        conditions.append(Business.priority.in_([p.value for p in f.priority]))
    if f.status:
        conditions.append(Business.status.in_([s.value for s in f.status]))
    if f.opportunity:
        conditions.append(Business.opportunity_types.overlap([o.value for o in f.opportunity]))
    if f.category:
        conditions.append(Business.category == f.category)
    if f.niche_key:
        conditions.append(Business.niche_key == f.niche_key)
    if f.city:
        conditions.append(func.lower(Business.city) == f.city.strip().lower())
    if f.has_phone is not None:
        conditions.append(
            Business.normalized_phone.is_not(None) if f.has_phone else Business.normalized_phone.is_(None)
        )
    own_site = and_(Business.website_url.is_not(None), Business.website_kind == "own")
    if f.has_website is not None:
        conditions.append(own_site if f.has_website else not_(own_site))
    if f.website_problems:
        conditions.append(
            or_(
                Business.website_status == "broken",
                Business.website_health_score < WEBSITE_PROBLEM_HEALTH,
                Business.opportunity_types.overlap([o.value for o in WEBSITE_PROBLEM_OPPORTUNITIES]),
            )
        )
    if f.google_opportunity:
        conditions.append(Business.opportunity_types.overlap([o.value for o in GOOGLE_OPPORTUNITIES]))
    if f.contacted is not None:
        conditions.append(Business.call_count > 0 if f.contacted else Business.call_count == 0)
    if f.min_rating is not None:
        conditions.append(Business.rating >= f.min_rating)
    if f.min_reviews is not None:
        conditions.append(Business.review_count >= f.min_reviews)
    if f.max_reviews is not None:
        conditions.append(func.coalesce(Business.review_count, 0) <= f.max_reviews)
    if f.min_score is not None:
        conditions.append(Business.opportunity_score >= f.min_score)
    if f.open_in_window is not None:
        conditions.append(Business.open_in_calling_window.is_(f.open_in_window))
    if f.callback_due:
        conditions.append(
            and_(Business.next_callback_at.is_not(None), Business.next_callback_at <= datetime.now(UTC))
        )
    if f.assigned_to:
        if f.assigned_to == "me" and user_id is not None:
            conditions.append(Business.assigned_to_id == user_id)
        elif f.assigned_to == "unassigned":
            conditions.append(Business.assigned_to_id.is_(None))
        elif f.assigned_to.isdigit():
            conditions.append(Business.assigned_to_id == int(f.assigned_to))
    if f.job_id is not None:
        sub = select(JobBusiness.business_id).where(JobBusiness.job_id == f.job_id)
        if f.job_matched_only:
            sub = sub.where(JobBusiness.matched_filters.is_(True))
        conditions.append(Business.id.in_(sub))
    if not f.include_suppressed:
        conditions.append(Business.suppressed.is_(False))
    if not f.include_demo:
        conditions.append(Business.is_demo.is_(False))
    return stmt.where(*conditions) if conditions else stmt


def apply_sort(stmt: Select[Any], sort: str, order: str) -> Select[Any]:
    desc = order == "desc"
    columns: dict[str, Any] = {
        "opportunity_score": Business.opportunity_score,
        "website_score": Business.website_health_score,
        "review_count": Business.review_count,
        "rating": Business.rating,
        "name": func.lower(Business.name),
        "created_at": Business.created_at,
        "last_contacted_at": Business.last_contacted_at,
        "next_callback_at": Business.next_callback_at,
    }
    if sort == "priority":
        # "desc" = most important first: HOT, then highest score.
        if desc:
            return stmt.order_by(
                Business.priority_rank.asc(), Business.opportunity_score.desc(), Business.id.desc()
            )
        return stmt.order_by(
            Business.priority_rank.desc(), Business.opportunity_score.asc(), Business.id.asc()
        )
    column = columns.get(sort, Business.opportunity_score)
    ordered = column.desc().nulls_last() if desc else column.asc().nulls_last()
    return stmt.order_by(ordered, Business.id.desc() if desc else Business.id.asc())


def to_summary(business: Business) -> LeadSummary:
    summary = LeadSummary.model_validate(business)
    top = next((r for r in business.score_reasons or [] if r.get("opportunity")), None)
    summary.top_reason = top.get("text") if top else None
    return summary


async def list_leads(
    session: AsyncSession,
    filters: LeadFilters,
    *,
    sort: str,
    order: str,
    page: int,
    page_size: int,
    user_id: int | None,
) -> tuple[list[LeadSummary], int]:
    base = apply_filters(select(Business), filters, user_id)
    total = (
        await session.execute(select(func.count()).select_from(base.order_by(None).subquery()))
    ).scalar_one()
    rows = (
        (await session.execute(apply_sort(base, sort, order).offset((page - 1) * page_size).limit(page_size)))
        .scalars()
        .all()
    )
    return [to_summary(b) for b in rows], int(total)


def open_today(
    business: Business,
    runtime: RuntimeSettings,
    window: tuple[str, str] | None = None,
    now: datetime | None = None,
) -> bool | None:
    periods = (business.opening_hours or {}).get("periods") if business.opening_hours else None
    if not periods:
        return None
    tz = ZoneInfo(runtime.general.timezone)
    local = (now or datetime.now(UTC)).astimezone(tz)
    start, end = window or (runtime.calling.window_start, runtime.calling.window_end)
    return is_open_during(periods, python_weekday_to_places(local.weekday()), start, end)


async def _users(session: AsyncSession, ids: set[int | None]) -> dict[int, User]:
    wanted = {i for i in ids if i is not None}
    if not wanted:
        return {}
    return {u.id: u for u in (await session.execute(select(User).where(User.id.in_(wanted)))).scalars()}


async def lead_detail(session: AsyncSession, business: Business, runtime: RuntimeSettings) -> LeadDetail:
    audit = await session.get(WebsiteAudit, business.last_audit_id) if business.last_audit_id else None
    contacts = (
        (
            await session.execute(
                select(BusinessContact)
                .where(BusinessContact.business_id == business.id)
                .order_by(BusinessContact.is_primary.desc(), BusinessContact.id)
            )
        )
        .scalars()
        .all()
    )
    calls = (
        (
            await session.execute(
                select(CallAttempt)
                .where(CallAttempt.business_id == business.id)
                .order_by(CallAttempt.created_at.desc())
                .limit(100)
            )
        )
        .scalars()
        .all()
    )
    notes = (
        (
            await session.execute(
                select(Note)
                .where(Note.business_id == business.id)
                .order_by(Note.created_at.desc())
                .limit(200)
            )
        )
        .scalars()
        .all()
    )
    events = (
        (
            await session.execute(
                select(LeadEvent)
                .where(LeadEvent.business_id == business.id)
                .order_by(LeadEvent.created_at.desc())
                .limit(100)
            )
        )
        .scalars()
        .all()
    )
    sources = (
        (await session.execute(select(BusinessSource).where(BusinessSource.business_id == business.id)))
        .scalars()
        .all()
    )
    active_job = (
        await session.execute(
            select(Job.id)
            .where(
                Job.kind == "audit",
                Job.status.in_([JobStatus.QUEUED.value, JobStatus.RUNNING.value]),
                Job.params["business_ids"].contains([business.id]),
            )
            .order_by(Job.id.desc())
            .limit(1)
        )
    ).scalar()

    users = await _users(
        session,
        {business.assigned_to_id, business.created_by_id, business.last_contacted_by_id}
        | {c.user_id for c in calls}
        | {n.user_id for n in notes},
    )
    niches = await load_niches(session)
    niche = resolve_niche(business, niches)
    pitches: dict[str, PitchOut] = {}
    for language in ("en", "bg"):
        pitch, _ = pitch_for(
            business, audit if business.website_status != "unaudited" else None, niches, runtime, language
        )
        pitches[language] = PitchOut(**pitch.to_dict())
    _, checklist = data_quality(
        has_phone=bool(business.normalized_phone),
        website_url=business.website_url,
        address=business.address,
        rating=business.rating,
        opening_hours=business.opening_hours,
    )

    detail = LeadDetail.model_validate(
        {k: getattr(business, k) for k in LeadDetail.model_fields if k not in _DETAIL_COMPUTED}
    )
    detail.top_reason = to_summary(business).top_reason
    detail.niche_label = niche.label if niche else None
    detail.data_quality_checklist = checklist
    detail.contacts = [ContactOut.model_validate(c) for c in contacts]
    detail.audit = AuditOut.model_validate(audit) if audit else None
    detail.pitches = pitches
    detail.calls = [
        CallOut.model_validate(c).model_copy(
            update={"user_name": users[c.user_id].name if c.user_id in users else None}
        )
        for c in calls
    ]
    detail.notes = [
        NoteOut.model_validate(n).model_copy(
            update={"user_name": users[n.user_id].name if n.user_id in users else None}
        )
        for n in notes
    ]
    detail.events = [EventOut.model_validate(e) for e in events]
    detail.sources = [SourceOut.model_validate(s) for s in sources]
    detail.assigned_to = (
        UserRef.model_validate(users[business.assigned_to_id]) if business.assigned_to_id in users else None
    )
    detail.created_by = (
        UserRef.model_validate(users[business.created_by_id]) if business.created_by_id in users else None
    )
    detail.last_contacted_by = (
        UserRef.model_validate(users[business.last_contacted_by_id])
        if business.last_contacted_by_id in users
        else None
    )
    detail.open_today_in_window = open_today(business, runtime)
    detail.active_job_id = int(active_job) if active_job else None
    return detail
