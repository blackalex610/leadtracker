"""Start over: delete every lead and everything hanging off it.

Kept on purpose:
* users and settings (prices, scoring, calling hours),
* the do-not-contact list - people who asked not to be called stay suppressed
  when the same numbers are found again,
* API usage records (they drive the monthly free-tier/cost numbers),
* the provider response cache (re-running a search within its TTL is free).
"""

from __future__ import annotations

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.log import get_logger
from app.models import (
    Business,
    CallAttempt,
    CallingSession,
    ImportBatch,
    Job,
    LeadEvent,
    Note,
    SearchQuery,
    WebsiteAudit,
)

log = get_logger(__name__)

RESET_CONFIRMATION = "DELETE ALL LEADS"


async def reset_lead_data(session: AsyncSession) -> dict[str, int]:
    counts: dict[str, int] = {}
    for label, model in (
        ("leads", Business),
        ("calls", CallAttempt),
        ("jobs", Job),
        ("search_queries", SearchQuery),
    ):
        counts[label] = int((await session.execute(select(func.count()).select_from(model))).scalar_one())
    # Children first (most also cascade, but explicit deletes keep this independent of FK rules).
    for child in (CallAttempt, Note, LeadEvent, CallingSession):
        await session.execute(delete(child))
    await session.execute(delete(Business))  # contacts, sources, job links cascade
    await session.execute(delete(WebsiteAudit))
    await session.execute(delete(Job))  # search queries cascade
    await session.execute(delete(SearchQuery))
    await session.execute(delete(ImportBatch))
    await session.commit()
    log.warning("lead_data_reset", **counts)
    return counts
