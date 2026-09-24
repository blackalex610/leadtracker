"""Leads: list/filter/sort, detail, updates, audits, calls, notes, refresh."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import distinct, func, select

from app.api.deps import CurrentUser, SessionDep
from app.core.enums import JobKind, LeadStatus, PhoneSource
from app.core.phone import normalize_phone
from app.core.ratelimit import audit_limiter, rate_limit
from app.db import get_sessionmaker
from app.models import Business, BusinessContact, LeadEvent, Note, SuppressionEntry, User
from app.providers.registry import get_provider
from app.schemas.common import Page
from app.schemas.leads import (
    AuditRequest,
    BulkLeadUpdate,
    BulkResult,
    CallCreate,
    CallOut,
    CallResult,
    JobRef,
    LeadDetail,
    LeadSummary,
    LeadUpdate,
    NoteCreate,
    NoteOut,
)
from app.services.businesses import record_from_place, set_website, upsert_business
from app.services.calls import LeadSuppressedError, record_call
from app.services.leads import LeadListQuery, lead_detail, list_leads
from app.services.presets import load_niches
from app.services.provider_gateway import ProviderGateway
from app.services.scoring_service import rescore_business
from app.services.settings import load_settings
from app.services.suppression import is_suppressed, reenable, suppress
from app.worker.queue import enqueue

router = APIRouter(prefix="/leads", tags=["leads"])


async def _lead_or_404(session: SessionDep, lead_id: int) -> Business:
    business = await session.get(Business, lead_id)
    if business is None:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": "Lead not found"})
    return business


@router.get("", response_model=Page[LeadSummary])
async def get_leads(
    session: SessionDep, user: CurrentUser, query: Annotated[LeadListQuery, Query()]
) -> Page[LeadSummary]:
    items, total = await list_leads(
        session,
        query,
        sort=query.sort,
        order=query.order,
        page=query.page,
        page_size=query.page_size,
        user_id=user.id,
    )
    return Page(items=items, total=total, page=query.page, page_size=query.page_size)


@router.get("/facets")
async def facets(session: SessionDep, _user: CurrentUser) -> dict[str, Any]:
    categories = (
        await session.execute(
            select(Business.category, func.count())
            .where(Business.category.is_not(None))
            .group_by(Business.category)
            .order_by(func.count().desc())
            .limit(100)
        )
    ).all()
    cities = (
        await session.execute(
            select(Business.city, func.count())
            .where(Business.city.is_not(None))
            .group_by(Business.city)
            .order_by(func.count().desc())
            .limit(100)
        )
    ).all()
    niches = (
        await session.execute(select(distinct(Business.niche_key)).where(Business.niche_key.is_not(None)))
    ).scalars()
    return {
        "categories": [{"value": c, "count": n} for c, n in categories],
        "cities": [{"value": c, "count": n} for c, n in cities],
        "niches": sorted(niches),
    }


@router.get("/{lead_id}", response_model=LeadDetail)
async def get_lead(lead_id: int, session: SessionDep, _user: CurrentUser) -> LeadDetail:
    business = await _lead_or_404(session, lead_id)
    runtime = await load_settings(session)
    return await lead_detail(session, business, runtime)


@router.patch("/{lead_id}", response_model=LeadDetail)
async def update_lead(lead_id: int, body: LeadUpdate, session: SessionDep, user: CurrentUser) -> LeadDetail:
    business = await _lead_or_404(session, lead_id)
    runtime = await load_settings(session)
    changes: dict[str, Any] = {}
    needs_rescore = False
    audit_needed = False

    if body.status is not None and body.status.value != business.status:
        leaving_dnc = business.status == LeadStatus.DO_NOT_CONTACT.value or business.suppressed
        if leaving_dnc and body.status != LeadStatus.DO_NOT_CONTACT:
            if not body.confirm_reenable:
                raise HTTPException(
                    status_code=409,
                    detail={
                        "code": "reenable_confirmation_required",
                        "message": "This lead is on the do-not-contact list. Confirm re-enabling it explicitly.",
                    },
                )
            entries = (
                (
                    await session.execute(
                        select(SuppressionEntry).where(
                            SuppressionEntry.active.is_(True),
                            (SuppressionEntry.business_id == business.id)
                            | (SuppressionEntry.normalized_phone == business.normalized_phone),
                        )
                    )
                )
                .scalars()
                .all()
            )
            for entry in entries:
                await reenable(session, entry, user.id)
            business.suppressed = False
        changes["status"] = {"from": business.status, "to": body.status.value}
        business.status = body.status.value
        if body.status == LeadStatus.DO_NOT_CONTACT:
            await suppress(
                session,
                normalized_phone=business.normalized_phone,
                business_id=business.id,
                reason="Marked do-not-contact",
                user_id=user.id,
            )
            business.suppressed = True

    if body.unassign:
        changes["assigned_to"] = None
        business.assigned_to_id = None
    elif body.assigned_to_id is not None:
        if await session.get(User, body.assigned_to_id) is None:
            raise HTTPException(status_code=422, detail={"code": "unknown_user", "message": "Unknown user"})
        changes["assigned_to"] = body.assigned_to_id
        business.assigned_to_id = body.assigned_to_id

    if body.next_callback_at is not None:
        business.next_callback_at = body.next_callback_at
        changes["next_callback_at"] = body.next_callback_at.isoformat()

    if body.niche_key is not None:
        business.niche_key = body.niche_key or None
        changes["niche_key"] = business.niche_key
        needs_rescore = True

    if body.website_url is not None and set_website(business, body.website_url or None):
        changes["website_url"] = business.website_url
        needs_rescore = True
        audit_needed = business.website_kind == "own" and bool(business.website_url)

    if body.add_phone:
        normalized = normalize_phone(body.add_phone, business.country_code or runtime.general.default_country)
        if normalized is None:
            raise HTTPException(
                status_code=422, detail={"code": "invalid_phone", "message": "Phone number is not valid"}
            )
        exists = (
            await session.execute(
                select(BusinessContact).where(
                    BusinessContact.business_id == business.id,
                    BusinessContact.normalized_phone == normalized.e164,
                )
            )
        ).scalar_one_or_none()
        if exists is None:
            session.add(
                BusinessContact(
                    business_id=business.id,
                    raw_phone=normalized.raw,
                    normalized_phone=normalized.e164,
                    national_format=normalized.national,
                    international_format=normalized.international,
                    country_code=normalized.country_code,
                    phone_type=normalized.phone_type,
                    phone_source=PhoneSource.MANUAL.value,
                    is_primary=True,
                )
            )
        if not business.normalized_phone or business.phone_invalid or exists is None:
            business.phone_raw = normalized.raw
            business.normalized_phone = normalized.e164
            business.national_phone = normalized.national
            business.international_phone = normalized.international
            business.phone_country_code = normalized.country_code
            business.phone_type = normalized.phone_type
            business.phone_source = PhoneSource.MANUAL.value
            business.phone_invalid = False
            business.phone_verified = False
        if await is_suppressed(session, normalized.e164):
            business.suppressed = True
            business.status = LeadStatus.DO_NOT_CONTACT.value
        changes["phone"] = normalized.e164
        needs_rescore = True

    if changes:
        session.add(LeadEvent(business_id=business.id, user_id=user.id, type="updated", data=changes))
    if needs_rescore:
        await session.flush()
        await rescore_business(session, business, runtime, await load_niches(session))
    if audit_needed:
        await enqueue(
            session, JobKind.AUDIT, {"business_ids": [business.id], "force": True}, created_by_id=user.id
        )
    await session.commit()
    await session.refresh(business)
    return await lead_detail(session, business, runtime)


@router.post("/bulk", response_model=BulkResult)
async def bulk_update(body: BulkLeadUpdate, session: SessionDep, user: CurrentUser) -> BulkResult:
    businesses = (await session.execute(select(Business).where(Business.id.in_(body.ids)))).scalars().all()
    updated = skipped = 0
    for business in businesses:
        changed = False
        if body.status is not None and body.status.value != business.status:
            if business.suppressed or business.status == LeadStatus.DO_NOT_CONTACT.value:
                skipped += 1  # re-enabling requires an explicit per-lead confirmation
                continue
            if body.status == LeadStatus.DO_NOT_CONTACT:
                await suppress(
                    session,
                    normalized_phone=business.normalized_phone,
                    business_id=business.id,
                    reason="Marked do-not-contact (bulk)",
                    user_id=user.id,
                )
                business.suppressed = True
            session.add(
                LeadEvent(
                    business_id=business.id,
                    user_id=user.id,
                    type="updated",
                    data={"status": {"from": business.status, "to": body.status.value}, "bulk": True},
                )
            )
            business.status = body.status.value
            changed = True
        if body.unassign:
            business.assigned_to_id = None
            changed = True
        elif body.assigned_to_id is not None:
            business.assigned_to_id = body.assigned_to_id
            changed = True
        updated += int(changed)
    await session.commit()
    return BulkResult(updated=updated, skipped=skipped)


@router.post(
    "/{lead_id}/audit",
    response_model=JobRef,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(rate_limit(audit_limiter, "audit"))],
)
async def audit_lead(lead_id: int, session: SessionDep, user: CurrentUser) -> JobRef:
    business = await _lead_or_404(session, lead_id)
    if not business.website_url or business.website_kind != "own":
        raise HTTPException(
            status_code=422,
            detail={"code": "no_auditable_website", "message": "This lead has no own website to audit"},
        )
    job = await enqueue(
        session, JobKind.AUDIT, {"business_ids": [business.id], "force": True}, created_by_id=user.id
    )
    await session.commit()
    return JobRef(job_id=job.id, status=job.status)


@router.post(
    "/audit",
    response_model=JobRef,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(rate_limit(audit_limiter, "audit"))],
)
async def audit_many(body: AuditRequest, session: SessionDep, user: CurrentUser) -> JobRef:
    ids = (
        (
            await session.execute(
                select(Business.id).where(
                    Business.id.in_(body.ids),
                    Business.website_url.is_not(None),
                    Business.website_kind == "own",
                )
            )
        )
        .scalars()
        .all()
    )
    if not ids:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "no_auditable_website",
                "message": "None of the selected leads has an own website",
            },
        )
    job = await enqueue(
        session, JobKind.AUDIT, {"business_ids": list(ids), "force": body.force}, created_by_id=user.id
    )
    await session.commit()
    return JobRef(job_id=job.id, status=job.status)


@router.post("/{lead_id}/rescore", response_model=LeadDetail)
async def rescore_lead(lead_id: int, session: SessionDep, _user: CurrentUser) -> LeadDetail:
    business = await _lead_or_404(session, lead_id)
    runtime = await load_settings(session)
    await rescore_business(session, business, runtime, await load_niches(session))
    await session.commit()
    return await lead_detail(session, business, runtime)


@router.post("/{lead_id}/refresh", response_model=LeadDetail)
async def refresh_lead(lead_id: int, session: SessionDep, user: CurrentUser) -> LeadDetail:
    """Re-fetch provider data for one lead (one Place Details request)."""
    business = await _lead_or_404(session, lead_id)
    if business.provider != "google_places" or not business.provider_place_id:
        raise HTTPException(
            status_code=422,
            detail={"code": "not_refreshable", "message": "Only Google-sourced leads can be refreshed"},
        )
    runtime = await load_settings(session)
    gateway = ProviderGateway(get_provider(), get_sessionmaker())
    place = await gateway.get_details(
        business.provider_place_id,
        language_code=runtime.general.provider_language,
        region_code=runtime.general.default_country,
    )
    outcome = await upsert_business(
        session, record_from_place(place), default_region=runtime.general.default_country, user_id=user.id
    )
    await rescore_business(session, outcome.business, runtime, await load_niches(session))
    if outcome.website_changed and outcome.business.website_kind == "own":
        await enqueue(
            session, JobKind.AUDIT, {"business_ids": [business.id], "force": True}, created_by_id=user.id
        )
    session.add(LeadEvent(business_id=business.id, user_id=user.id, type="refreshed", data={}))
    await session.commit()
    await session.refresh(outcome.business)
    return await lead_detail(session, outcome.business, runtime)


@router.post("/{lead_id}/call", response_model=CallResult)
async def call_lead(lead_id: int, body: CallCreate, session: SessionDep, user: CurrentUser) -> CallResult:
    business = await _lead_or_404(session, lead_id)
    runtime = await load_settings(session)
    try:
        call = await record_call(
            session,
            business,
            outcome=body.outcome,
            user_id=user.id,
            runtime=runtime,
            note=body.note,
            callback_at=body.callback_at,
            session_id=body.session_id,
        )
    except LeadSuppressedError as exc:
        raise HTTPException(status_code=409, detail={"code": "do_not_contact", "message": str(exc)}) from exc
    if body.outcome.value == "WRONG_NUMBER":
        await rescore_business(session, business, runtime, await load_niches(session))
    await session.commit()
    await session.refresh(call)
    await session.refresh(business)
    return CallResult(
        call=CallOut.model_validate(call).model_copy(update={"user_name": user.name}),
        status=LeadStatus(business.status),
        suppressed=business.suppressed,
        next_callback_at=business.next_callback_at,
    )


@router.post("/{lead_id}/notes", response_model=NoteOut, status_code=status.HTTP_201_CREATED)
async def add_note(lead_id: int, body: NoteCreate, session: SessionDep, user: CurrentUser) -> NoteOut:
    business = await _lead_or_404(session, lead_id)
    note = Note(business_id=business.id, user_id=user.id, body=body.body.strip())
    session.add(note)
    await session.commit()
    await session.refresh(note)
    return NoteOut.model_validate(note).model_copy(update={"user_name": user.name})
