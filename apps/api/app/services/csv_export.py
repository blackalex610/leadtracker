"""CSV export of filtered leads (UTF-8, optional BOM for Excel, proper quoting,
spreadsheet formula-injection protection)."""

from __future__ import annotations

import csv
import io
import re
from collections.abc import AsyncIterator
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import OPPORTUNITY_LABELS, OpportunityType
from app.models import Business, Note
from app.services.leads import LeadFilters, apply_filters, apply_sort

EXPORT_COLUMNS = [
    "Business", "Category", "Phone", "International Phone", "Address", "City", "Rating", "Reviews", "Website",
    "Website Score", "Opportunity Score", "Priority", "Opportunity Types", "Google Maps URL", "Status", "Notes",
]  # fmt: skip

_FORMULA_START = ("=", "+", "-", "@", "\t", "\r")
_PHONE_LIKE = re.compile(r"^\+?[\d\s().\-/]{5,}$")
BATCH = 500


def csv_safe(value: Any) -> str:
    """Neutralize values a spreadsheet would execute as a formula. Phone numbers
    such as ``+359 888 123 456`` are left untouched."""
    if value is None:
        return ""
    text = str(value)
    if text and text[0] in _FORMULA_START and not _PHONE_LIKE.match(text):
        return "'" + text
    return text


def business_row(b: Business, notes: list[str]) -> list[str]:
    opportunities = ", ".join(
        OPPORTUNITY_LABELS.get(OpportunityType(o), o) if o in OpportunityType.__members__ else o
        for o in b.opportunity_types or []
    )
    values: list[Any] = [
        b.name,
        b.category,
        b.national_phone or b.phone_raw,
        b.international_phone,
        b.address,
        b.city,
        f"{b.rating:.1f}" if b.rating is not None else "",
        b.review_count,
        b.website_url,
        b.website_health_score,
        b.opportunity_score,
        b.priority,
        opportunities,
        b.google_maps_url,
        b.status,
        " | ".join(notes),
    ]
    return [csv_safe(v) for v in values]


async def _notes_for(session: AsyncSession, ids: list[int]) -> dict[int, list[str]]:
    rows = (
        await session.execute(
            select(Note.business_id, Note.body)
            .where(Note.business_id.in_(ids))
            .order_by(Note.created_at.desc())
        )
    ).all()
    out: dict[int, list[str]] = {}
    for business_id, body in rows:
        out.setdefault(business_id, []).append(" ".join(body.split()))
    return out


async def export_rows(
    session: AsyncSession,
    filters: LeadFilters,
    *,
    sort: str,
    order: str,
    delimiter: str = ",",
    include_bom: bool = True,
    user_id: int | None = None,
    limit: int = 100_000,
) -> AsyncIterator[bytes]:
    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=delimiter, quoting=csv.QUOTE_MINIMAL, lineterminator="\r\n")

    def flush() -> bytes:
        data = buffer.getvalue().encode("utf-8")
        buffer.seek(0)
        buffer.truncate(0)
        return data

    writer.writerow(EXPORT_COLUMNS)
    header = flush()
    yield (b"\xef\xbb\xbf" + header) if include_bom else header

    stmt = apply_sort(apply_filters(select(Business), filters, user_id), sort, order)
    offset = 0
    while offset < limit:
        batch = (await session.execute(stmt.offset(offset).limit(BATCH))).scalars().all()
        if not batch:
            break
        notes = await _notes_for(session, [b.id for b in batch])
        for business in batch:
            writer.writerow(business_row(business, notes.get(business.id, [])))
        yield flush()
        offset += BATCH
