"""Postgres-backed job queue.

Jobs are claimed with ``SELECT ... FOR UPDATE SKIP LOCKED`` so any number of
worker processes can run safely. Running jobs send heartbeats; jobs whose
worker died are re-queued (or failed after ``max_attempts``).
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.enums import JobKind, JobStatus
from app.log import get_logger
from app.models import Job

log = get_logger(__name__)

STALE_AFTER = timedelta(minutes=3)


async def enqueue(
    session: AsyncSession,
    kind: JobKind,
    params: dict[str, Any],
    *,
    created_by_id: int | None = None,
    retry_of_id: int | None = None,
    max_attempts: int = 2,
) -> Job:
    job = Job(
        kind=kind.value,
        status=JobStatus.QUEUED.value,
        params=params,
        stage="queued",
        counters={},
        errors=[],
        created_by_id=created_by_id,
        retry_of_id=retry_of_id,
        max_attempts=max_attempts,
        run_after=datetime.now(UTC),
    )
    session.add(job)
    await session.flush()
    return job


async def claim_next(session: AsyncSession, worker_id: str) -> Job | None:
    stmt = (
        select(Job)
        .where(Job.status == JobStatus.QUEUED.value, Job.run_after <= datetime.now(UTC))
        .order_by(Job.created_at)
        .with_for_update(skip_locked=True)
        .limit(1)
    )
    job = (await session.execute(stmt)).scalar_one_or_none()
    if job is None:
        return None
    now = datetime.now(UTC)
    job.status = JobStatus.RUNNING.value
    job.locked_by = worker_id
    job.started_at = job.started_at or now
    job.heartbeat_at = now
    job.attempts = (job.attempts or 0) + 1
    await session.commit()
    return job


async def recover_stale(session: AsyncSession) -> int:
    cutoff = datetime.now(UTC) - STALE_AFTER
    stale = (
        (
            await session.execute(
                select(Job)
                .where(Job.status == JobStatus.RUNNING.value, Job.heartbeat_at < cutoff)
                .with_for_update(skip_locked=True)
            )
        )
        .scalars()
        .all()
    )
    for job in stale:
        if job.cancel_requested:
            job.status = JobStatus.CANCELLED.value
            job.finished_at = datetime.now(UTC)
        elif job.attempts < job.max_attempts:
            job.status = JobStatus.QUEUED.value
            job.locked_by = None
            job.stage = "requeued"
            log.warning("job_requeued", job_id=job.id, attempts=job.attempts)
        else:
            job.status = JobStatus.FAILED.value
            job.error_code = "worker_lost"
            job.error_message = "The worker processing this job stopped unexpectedly."
            job.finished_at = datetime.now(UTC)
    await session.commit()
    return len(stale)


@dataclass(slots=True)
class JobOutcome:
    status: JobStatus
    result: dict[str, Any] = field(default_factory=dict)
    error_code: str | None = None
    error_message: str | None = None


class JobCancelled(Exception):
    pass


class JobYield(Exception):
    """The run's time budget is spent; the job goes back to the queue and resumes
    from ``JobContext.checkpoint`` on its next run."""


class JobContext:
    """Handle given to job handlers for progress reporting and cancellation."""

    def __init__(
        self,
        job: Job,
        sessionmaker: async_sessionmaker[AsyncSession],
        *,
        deadline: float | None = None,
    ) -> None:
        self.job_id = job.id
        self.kind = job.kind
        self.params: dict[str, Any] = dict(job.params or {})
        self.created_by_id = job.created_by_id
        self.sessionmaker = sessionmaker
        self.counters: dict[str, Any] = dict(job.counters or {})
        self.errors: list[dict[str, Any]] = list(job.errors or [])
        self.processed = job.progress_processed or 0
        self.total = job.progress_total or 0
        self.stage = job.stage or "starting"
        self.checkpoint: dict[str, Any] = dict(job.checkpoint or {})
        self.resumed = bool(job.checkpoint)
        self.deadline = deadline  # time.monotonic() value; None = no time limit

    def out_of_time(self) -> bool:
        return self.deadline is not None and time.monotonic() >= self.deadline

    def check_time(self) -> None:
        if self.out_of_time():
            raise JobYield()

    def incr(self, key: str, amount: int = 1) -> None:
        self.counters[key] = int(self.counters.get(key, 0)) + amount

    def add_error(self, code: str, message: str, **extra: Any) -> None:
        if len(self.errors) < 100:
            self.errors.append({"code": code, "message": message, **extra})

    async def flush(self, stage: str | None = None) -> None:
        if stage:
            self.stage = stage
        async with self.sessionmaker() as session:
            await session.execute(
                update(Job)
                .where(Job.id == self.job_id)
                .values(
                    stage=self.stage,
                    progress_processed=self.processed,
                    progress_total=self.total,
                    counters=self.counters,
                    errors=self.errors,
                    checkpoint=self.checkpoint or None,
                    heartbeat_at=datetime.now(UTC),
                )
            )
            await session.commit()

    async def cancelled(self) -> bool:
        async with self.sessionmaker() as session:
            value = (
                await session.execute(select(Job.cancel_requested).where(Job.id == self.job_id))
            ).scalar()
            return bool(value)

    async def check_cancelled(self) -> None:
        if await self.cancelled():
            raise JobCancelled()


async def heartbeat(sessionmaker: async_sessionmaker[AsyncSession], job_id: int) -> None:
    async with sessionmaker() as session:
        await session.execute(update(Job).where(Job.id == job_id).values(heartbeat_at=datetime.now(UTC)))
        await session.commit()


async def release(sessionmaker: async_sessionmaker[AsyncSession], ctx: JobContext) -> None:
    """Put a job that yielded back in the queue (a yield does not count as an attempt)."""
    now = datetime.now(UTC)
    async with sessionmaker() as session:
        job = await session.get(Job, ctx.job_id, with_for_update=True)
        if job is None:
            return
        job.progress_processed = ctx.processed
        job.progress_total = ctx.total
        job.counters = ctx.counters
        job.errors = ctx.errors
        job.checkpoint = ctx.checkpoint or None
        job.heartbeat_at = now
        job.locked_by = None
        if job.cancel_requested:
            job.status = JobStatus.CANCELLED.value
            job.stage = "cancelled"
            job.finished_at = now
        else:
            job.status = JobStatus.QUEUED.value
            job.attempts = max(0, (job.attempts or 1) - 1)
            job.run_after = now
            job.stage = ctx.stage
        await session.commit()


async def finish(
    sessionmaker: async_sessionmaker[AsyncSession], ctx: JobContext, outcome: JobOutcome
) -> None:
    async with sessionmaker() as session:
        await session.execute(
            update(Job)
            .where(Job.id == ctx.job_id)
            .values(
                status=outcome.status.value,
                stage="done" if outcome.status != JobStatus.FAILED else "failed",
                progress_processed=ctx.processed,
                progress_total=ctx.total,
                counters={**ctx.counters, **outcome.result},
                errors=ctx.errors,
                checkpoint=None,
                error_code=outcome.error_code,
                error_message=outcome.error_message,
                finished_at=datetime.now(UTC),
                heartbeat_at=datetime.now(UTC),
            )
        )
        await session.commit()
