"""Recording call outcomes and the resulting lead status transitions."""

from __future__ import annotations

from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import CallOutcome, LeadStatus
from app.core.opening_hours import parse_hhmm
from app.log import get_logger
from app.models import Business, BusinessContact, CallAttempt, LeadEvent, Note
from app.services.settings import RuntimeSettings
from app.services.suppression import suppress

log = get_logger(__name__)

EARLY = {LeadStatus.NEW, LeadStatus.CALLED, LeadStatus.NO_ANSWER, LeadStatus.CALLBACK}
ANSWERED = {
    CallOutcome.INTERESTED,
    CallOutcome.CALLBACK,
    CallOutcome.NOT_INTERESTED,
    CallOutcome.ALREADY_HAS_PROVIDER,
    CallOutcome.DO_NOT_CONTACT,
}


class LeadSuppressedError(Exception):
    pass


def status_after_call(current: LeadStatus, outcome: CallOutcome) -> LeadStatus:
    """Never downgrades a lead that has progressed further in the pipeline."""
    if outcome == CallOutcome.DO_NOT_CONTACT:
        return LeadStatus.DO_NOT_CONTACT
    if current == LeadStatus.DO_NOT_CONTACT:
        return current
    if outcome in (CallOutcome.NOT_INTERESTED, CallOutcome.ALREADY_HAS_PROVIDER):
        return current if current == LeadStatus.WON else LeadStatus.LOST
    if outcome == CallOutcome.INTERESTED:
        return LeadStatus.INTERESTED if current in EARLY | {LeadStatus.LOST} else current
    if outcome == CallOutcome.CALLBACK:
        return LeadStatus.CALLBACK if current in EARLY else current
    if outcome == CallOutcome.NO_ANSWER:
        return LeadStatus.NO_ANSWER if current in EARLY else current
    if outcome == CallOutcome.WRONG_NUMBER:
        return LeadStatus.CALLED if current in EARLY else current
    return current


def default_callback_time(runtime: RuntimeSettings, now: datetime | None = None) -> datetime:
    tz = ZoneInfo(runtime.general.timezone)
    local = (now or datetime.now(UTC)).astimezone(tz)
    minutes = parse_hhmm(runtime.calling.window_start)
    target = datetime.combine(local.date() + timedelta(days=1), time(minutes // 60, minutes % 60), tz)
    return target.astimezone(UTC)


async def record_call(
    session: AsyncSession,
    business: Business,
    *,
    outcome: CallOutcome,
    user_id: int | None,
    runtime: RuntimeSettings,
    note: str | None = None,
    callback_at: datetime | None = None,
    session_id: int | None = None,
) -> CallAttempt:
    if business.suppressed and outcome != CallOutcome.DO_NOT_CONTACT:
        raise LeadSuppressedError("This lead is on the do-not-contact list.")

    now = datetime.now(UTC)
    if outcome == CallOutcome.CALLBACK and callback_at is None:
        callback_at = default_callback_time(runtime, now)
    call = CallAttempt(
        business_id=business.id,
        user_id=user_id,
        session_id=session_id,
        outcome=outcome.value,
        phone_dialed=business.normalized_phone,
        note=note.strip() if note and note.strip() else None,
        callback_at=callback_at,
    )
    session.add(call)

    previous = LeadStatus(business.status)
    new_status = status_after_call(previous, outcome)
    business.status = new_status.value
    business.call_count = (business.call_count or 0) + 1
    business.last_contacted_at = now
    business.last_contacted_by_id = user_id

    if outcome == CallOutcome.CALLBACK:
        business.next_callback_at = callback_at
    elif outcome != CallOutcome.NO_ANSWER:
        business.next_callback_at = None

    if outcome in ANSWERED and business.normalized_phone:
        business.phone_verified = True
        await session.execute(
            update(BusinessContact)
            .where(
                BusinessContact.business_id == business.id,
                BusinessContact.normalized_phone == business.normalized_phone,
            )
            .values(phone_verified=True, verified_at=now, verification_method="call_connected")
        )
    if outcome == CallOutcome.WRONG_NUMBER:
        business.phone_invalid = True
        business.phone_verified = False
        if business.normalized_phone:
            await session.execute(
                update(BusinessContact)
                .where(
                    BusinessContact.business_id == business.id,
                    BusinessContact.normalized_phone == business.normalized_phone,
                )
                .values(invalid=True, phone_verified=False)
            )
    if call.note:
        session.add(Note(business_id=business.id, user_id=user_id, body=call.note))
    session.add(
        LeadEvent(
            business_id=business.id,
            user_id=user_id,
            type="call",
            data={"outcome": outcome.value, "from": previous.value, "to": new_status.value},
        )
    )
    if outcome == CallOutcome.DO_NOT_CONTACT:
        await suppress(
            session,
            normalized_phone=business.normalized_phone,
            business_id=business.id,
            reason=call.note or "Marked do-not-contact during a call",
            user_id=user_id,
        )
        business.suppressed = True
    await session.flush()
    log.info("call_recorded", business_id=business.id, outcome=outcome.value, status=new_status.value)
    return call


async def last_calls(session: AsyncSession, business_ids: list[int]) -> dict[int, CallAttempt]:
    if not business_ids:
        return {}
    rows = (
        (
            await session.execute(
                select(CallAttempt)
                .where(CallAttempt.business_id.in_(business_ids))
                .order_by(CallAttempt.business_id, CallAttempt.created_at.desc())
                .distinct(CallAttempt.business_id)
            )
        )
        .scalars()
        .all()
    )
    return {c.business_id: c for c in rows}
