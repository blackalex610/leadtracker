"""Job processing for serverless deployments: no resident worker, so queued jobs run
in time-boxed slices when the app calls ``POST /api/worker/run`` (and from a cron)."""

from __future__ import annotations

import time
import uuid
from typing import TypedDict

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.enums import JobStatus
from app.log import get_logger
from app.models import Job
from app.worker.queue import recover_stale
from app.worker.runner import Worker, run_maintenance

log = get_logger(__name__)

# Do not start a job with less time than this left in the slice.
MIN_SLICE_SECONDS = 8.0
MAINTENANCE_EVERY_SECONDS = 3600.0
_last_maintenance = 0.0


class QueueCounts(TypedDict):
    queued: int
    running: int


class DrainResult(QueueCounts):
    ran: int


async def queue_counts(sessionmaker: async_sessionmaker[AsyncSession]) -> QueueCounts:
    async with sessionmaker() as session:
        rows = (
            await session.execute(
                select(Job.status, func.count())
                .where(Job.status.in_((JobStatus.QUEUED.value, JobStatus.RUNNING.value)))
                .group_by(Job.status)
            )
        ).all()
    counts = {status: int(n) for status, n in rows}
    return {
        "queued": counts.get(JobStatus.QUEUED.value, 0),
        "running": counts.get(JobStatus.RUNNING.value, 0),
    }


async def drain(sessionmaker: async_sessionmaker[AsyncSession], budget_seconds: float) -> DrainResult:
    """Run queued jobs until the queue is empty or the budget is spent. A job still
    unfinished at the deadline is checkpointed and re-queued."""
    global _last_maintenance
    deadline = time.monotonic() + budget_seconds
    if time.monotonic() - _last_maintenance > MAINTENANCE_EVERY_SECONDS:
        _last_maintenance = time.monotonic()
        try:
            await run_maintenance(sessionmaker)
        except Exception:
            log.exception("maintenance_failed")
    else:
        async with sessionmaker() as session:
            await recover_stale(session)

    worker = Worker(sessionmaker, concurrency=1)
    worker.worker_id = f"fn-{uuid.uuid4().hex[:12]}"
    ran = 0
    while deadline - time.monotonic() > MIN_SLICE_SECONDS:
        if not await worker.run_once(deadline=deadline):
            break
        ran += 1
    counts = await queue_counts(sessionmaker)
    return {"ran": ran, **counts}
