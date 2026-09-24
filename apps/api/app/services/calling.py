"""Night-calling sessions: build a queue of callable leads and serve call cards.

Suppression is enforced twice: when the queue is built (suppressed flag, DNC
status AND the suppression list itself) and again every time a card is served,
so a number marked do-not-contact by a colleague mid-session is never shown as
callable.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import ColumnElement, and_, exists, func, not_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import LeadStatus, OpportunityType, Priority
from app.core.opening_hours import is_open_during, python_weekday_to_places
from app.models import Business, CallAttempt, CallingSession, SuppressionEntry
from app.schemas.leads import PitchOut, ScoreReason
from app.schemas.misc import CallingCard, CallingFilters
from app.services.calls import last_calls
from app.services.leads import to_summary
from app.services.presets import load_niches
from app.services.scoring_service import load_last_audit, pitch_for
from app.services.settings import RuntimeSettings

POOR_WEBSITE = [
    OpportunityType.BROKEN_WEBSITE.value,
    OpportunityType.WEBSITE_REDESIGN.value,
    OpportunityType.OUTDATED_WEBSITE.value,
    OpportunityType.MOBILE_PROBLEM.value,
]
DAY_NAMES = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]


def callable_conditions() -> list[ColumnElement[bool]]:
    suppressed_number = exists().where(
        SuppressionEntry.active.is_(True), SuppressionEntry.normalized_phone == Business.normalized_phone
    )
    return [
        Business.normalized_phone.is_not(None),
        Business.phone_invalid.is_(False),
        Business.suppressed.is_(False),
        Business.status != LeadStatus.DO_NOT_CONTACT.value,
        or_(Business.business_status.is_(None), Business.business_status != "CLOSED_PERMANENTLY"),
        not_(suppressed_number),
    ]


def _base_query(filters: CallingFilters, runtime: RuntimeSettings, user_id: int | None, now: datetime):  # type: ignore[no-untyped-def]
    cooldown = now - timedelta(hours=runtime.calling.recall_cooldown_hours)
    callback_due = and_(Business.next_callback_at.is_not(None), Business.next_callback_at <= now)
    stmt = select(Business).where(*callable_conditions())
    if filters.statuses:
        stmt = stmt.where(Business.status.in_([s.value for s in filters.statuses]))
    stmt = stmt.where(
        or_(callback_due, Business.last_contacted_at.is_(None), Business.last_contacted_at < cooldown)
    )
    # A scheduled callback in the future is not due yet.
    stmt = stmt.where(or_(Business.next_callback_at.is_(None), Business.next_callback_at <= now))
    if filters.priorities:
        stmt = stmt.where(or_(Business.priority.in_([p.value for p in filters.priorities]), callback_due))
    if filters.niche_key:
        stmt = stmt.where(Business.niche_key == filters.niche_key)
    if filters.category:
        stmt = stmt.where(Business.category == filters.category)
    if filters.city:
        stmt = stmt.where(func.lower(Business.city) == filters.city.strip().lower())
    if filters.website == "none":
        stmt = stmt.where(Business.opportunity_types.overlap([OpportunityType.NO_WEBSITE.value]))
    elif filters.website == "poor":
        stmt = stmt.where(
            or_(Business.opportunity_types.overlap(POOR_WEBSITE), Business.website_health_score < 50)
        )
    if filters.opportunity_types:
        stmt = stmt.where(Business.opportunity_types.overlap([o.value for o in filters.opportunity_types]))
    if filters.min_score is not None:
        stmt = stmt.where(Business.opportunity_score >= filters.min_score)
    if filters.assigned_to_me and user_id is not None:
        stmt = stmt.where(Business.assigned_to_id == user_id)
    return stmt.order_by(
        callback_due.desc(),
        Business.priority_rank.asc(),
        Business.opportunity_score.desc(),
        Business.id.asc(),
    )


async def build_queue(
    session: AsyncSession,
    filters: CallingFilters,
    runtime: RuntimeSettings,
    user_id: int | None,
    now: datetime | None = None,
) -> list[Business]:
    now = now or datetime.now(UTC)
    candidates = (
        (
            await session.execute(
                _base_query(filters, runtime, user_id, now).limit(min(filters.limit * 10, 3000))
            )
        )
        .scalars()
        .all()
    )

    window = (
        (filters.window_start, filters.window_end) if filters.window_start and filters.window_end else None
    )
    include_unknown = (
        filters.include_unknown_hours
        if filters.include_unknown_hours is not None
        else runtime.calling.include_unknown_hours
    )
    day = python_weekday_to_places(now.astimezone(ZoneInfo(runtime.general.timezone)).weekday())

    known: list[Business] = []
    unknown: list[Business] = []
    seen_phones: set[str] = set()
    for business in candidates:
        if business.normalized_phone in seen_phones:
            continue
        periods = (business.opening_hours or {}).get("periods") if business.opening_hours else None
        if window and filters.open_today:
            if not periods:
                if not include_unknown:
                    continue
                unknown.append(business)
                seen_phones.add(business.normalized_phone or "")
                continue
            if not is_open_during(periods, day, window[0], window[1]):
                continue
        known.append(business)
        seen_phones.add(business.normalized_phone or "")
        if len(known) >= filters.limit:
            break
    return (known + unknown)[: filters.limit]


async def session_stats(session: AsyncSession, calling_session_id: int) -> dict[str, int]:
    rows = await session.execute(
        select(CallAttempt.outcome, func.count())
        .where(CallAttempt.session_id == calling_session_id)
        .group_by(CallAttempt.outcome)
    )
    stats = {str(outcome): int(count) for outcome, count in rows.all()}
    stats["total_calls"] = sum(stats.values())
    return stats


def _hours_today(business: Business, runtime: RuntimeSettings, now: datetime) -> str | None:
    descriptions = (
        (business.opening_hours or {}).get("weekday_descriptions") if business.opening_hours else None
    )
    if not descriptions:
        return None
    today = DAY_NAMES[python_weekday_to_places(now.astimezone(ZoneInfo(runtime.general.timezone)).weekday())]
    return next((d for d in descriptions if d.lower().startswith(today.lower())), None)


def _website_summary(business: Business) -> str | None:
    if not business.website_url:
        return "No website"
    if business.website_kind == "social":
        return "Social media page only"
    if business.website_kind == "booking_platform":
        return "Booking-platform profile only"
    if business.website_kind == "link_hub":
        return "Link page only"
    if business.website_status == "broken":
        return "Website broken / unreachable"
    if business.website_status == "unaudited":
        return "Website not audited yet"
    if business.website_health_score is not None:
        return f"Website Health {business.website_health_score}/100"
    return None


async def build_cards(
    session: AsyncSession,
    lead_ids: list[int],
    runtime: RuntimeSettings,
    filters: CallingFilters | None = None,
    now: datetime | None = None,
) -> list[CallingCard]:
    now = now or datetime.now(UTC)
    if not lead_ids:
        return []
    businesses = {
        b.id: b for b in (await session.execute(select(Business).where(Business.id.in_(lead_ids)))).scalars()
    }
    active_suppressed = set(
        (
            await session.execute(
                select(SuppressionEntry.normalized_phone).where(
                    SuppressionEntry.active.is_(True),
                    SuppressionEntry.normalized_phone.in_(
                        [b.normalized_phone for b in businesses.values() if b.normalized_phone]
                    ),
                )
            )
        ).scalars()
    )
    niches = await load_niches(session)
    latest = await last_calls(session, lead_ids)
    window = (
        (filters.window_start, filters.window_end)
        if filters and filters.window_start and filters.window_end
        else (runtime.calling.window_start, runtime.calling.window_end)
    )
    day = python_weekday_to_places(now.astimezone(ZoneInfo(runtime.general.timezone)).weekday())
    cards: list[CallingCard] = []
    for lead_id in lead_ids:
        business = businesses.get(lead_id)
        if business is None:
            continue
        reason: str | None = None
        if (
            business.suppressed
            or business.status == LeadStatus.DO_NOT_CONTACT.value
            or (business.normalized_phone in active_suppressed)
        ):
            reason = "On the do-not-contact list"
        elif not business.normalized_phone:
            reason = "No phone number"
        elif business.phone_invalid:
            reason = "Phone marked as wrong number"
        elif business.is_demo:
            reason = "Demo record — dialing disabled"
        audit = await load_last_audit(session, business)
        pitch, _ = pitch_for(
            business,
            audit if business.website_status != "unaudited" else None,
            niches,
            runtime,
            runtime.general.pitch_language,
        )
        periods = (business.opening_hours or {}).get("periods") if business.opening_hours else None
        last = latest.get(business.id)
        cards.append(
            CallingCard(
                lead=to_summary(business),
                reasons=[ScoreReason(**r) for r in (business.score_reasons or []) if r.get("opportunity")][
                    :6
                ],
                pitch=PitchOut(**pitch.to_dict()),
                hours_today=_hours_today(business, runtime, now),
                open_in_window_today=is_open_during(periods, day, window[0], window[1]) if periods else None,
                website_summary=_website_summary(business),
                last_call_outcome=last.outcome if last else None,
                last_call_at=last.created_at if last else None,
                last_note=last.note if last else None,
                callable=reason is None or reason.startswith("Demo"),
                not_callable_reason=reason,
            )
        )
    return cards


async def create_session(
    session: AsyncSession, filters: CallingFilters, runtime: RuntimeSettings, user_id: int | None
) -> CallingSession:
    queue = await build_queue(session, filters, runtime, user_id)
    calling = CallingSession(
        user_id=user_id, filters=filters.model_dump(mode="json"), lead_ids=[b.id for b in queue], position=0
    )
    session.add(calling)
    await session.flush()
    return calling


PRIORITY_DEFAULT = [Priority.HOT, Priority.WARM]
