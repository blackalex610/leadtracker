"""Permanent do-not-contact list.

A suppressed number is never surfaced by the calling workflow again, for any
business that uses it, until someone explicitly re-enables it.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import LeadStatus
from app.models import Business, BusinessContact, LeadEvent, SuppressionEntry


async def is_suppressed(session: AsyncSession, normalized_phone: str | None) -> bool:
    if not normalized_phone:
        return False
    found = await session.execute(
        select(SuppressionEntry.id).where(
            SuppressionEntry.normalized_phone == normalized_phone, SuppressionEntry.active.is_(True)
        )
    )
    return found.first() is not None


def _businesses_with_phone(phone: str):  # type: ignore[no-untyped-def]
    contact_ids = select(BusinessContact.business_id).where(BusinessContact.normalized_phone == phone)
    return or_(Business.normalized_phone == phone, Business.id.in_(contact_ids))


async def suppress(
    session: AsyncSession,
    *,
    normalized_phone: str | None,
    business_id: int | None,
    reason: str | None,
    user_id: int | None,
) -> SuppressionEntry:
    """Add a number (and/or a business) to the do-not-contact list and flag every
    business sharing that number."""
    entry: SuppressionEntry | None = None
    if normalized_phone:
        entry = (
            await session.execute(
                select(SuppressionEntry).where(
                    SuppressionEntry.normalized_phone == normalized_phone, SuppressionEntry.active.is_(True)
                )
            )
        ).scalar_one_or_none()
    if entry is None:
        entry = SuppressionEntry(
            normalized_phone=normalized_phone, business_id=business_id, reason=reason, created_by_id=user_id
        )
        session.add(entry)
        await session.flush()

    conditions = []
    if normalized_phone:
        conditions.append(_businesses_with_phone(normalized_phone))
    if business_id:
        conditions.append(Business.id == business_id)
    if conditions:
        affected = (await session.execute(select(Business.id).where(or_(*conditions)))).scalars().all()
        await session.execute(
            update(Business)
            .where(Business.id.in_(affected))
            .values(suppressed=True, status=LeadStatus.DO_NOT_CONTACT.value, next_callback_at=None)
        )
        for bid in affected:
            session.add(
                LeadEvent(
                    business_id=bid,
                    user_id=user_id,
                    type="suppressed",
                    data={"phone": normalized_phone, "reason": reason},
                )
            )
    return entry


async def reenable(session: AsyncSession, entry: SuppressionEntry, user_id: int | None) -> list[int]:
    """Explicitly re-enable a suppressed number. Returns the affected business ids."""
    entry.active = False
    entry.deactivated_by_id = user_id
    entry.deactivated_at = datetime.now(UTC)
    conditions = []
    if entry.normalized_phone:
        conditions.append(_businesses_with_phone(entry.normalized_phone))
    if entry.business_id:
        conditions.append(Business.id == entry.business_id)
    if not conditions:
        return []
    businesses = (await session.execute(select(Business).where(or_(*conditions)))).scalars().all()
    changed: list[int] = []
    for business in businesses:
        # Still suppressed through another active entry?
        if await is_suppressed(session, business.normalized_phone):
            continue
        business.suppressed = False
        if business.status == LeadStatus.DO_NOT_CONTACT.value:
            business.status = (LeadStatus.CALLED if business.call_count else LeadStatus.NEW).value
        session.add(
            LeadEvent(
                business_id=business.id,
                user_id=user_id,
                type="unsuppressed",
                data={"phone": entry.normalized_phone},
            )
        )
        changed.append(business.id)
    return changed
