"""Background worker. Runs embedded in the API process (RUN_WORKER=true) or as
a separate process (``python -m app.worker``). Several workers can run at once."""

from __future__ import annotations

import asyncio
import contextlib
import os
import socket
import time
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, text, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import get_settings
from app.core.enums import JobKind, JobStatus
from app.log import get_logger
from app.models import Business, ImportBatch
from app.providers.base import ProviderError
from app.services.provider_gateway import purge_expired_cache
from app.services.search import run_audit_job, run_rescore_job, run_search_job
from app.worker.queue import (
    JobContext,
    JobOutcome,
    JobYield,
    claim_next,
    finish,
    heartbeat,
    recover_stale,
    release,
)

log = get_logger(__name__)

Handler = Callable[[JobContext], Awaitable[JobOutcome]]

HANDLERS: dict[str, Handler] = {
    JobKind.SEARCH.value: run_search_job,
    JobKind.AUDIT.value: run_audit_job,
    JobKind.RESCORE.value: run_rescore_job,
}

MAINTENANCE_INTERVAL_S = 30 * 60
_MAINTENANCE_LOCK_ID = 7_345_001


async def run_maintenance(sessionmaker: async_sessionmaker[AsyncSession]) -> dict[str, int]:
    settings = get_settings()
    out: dict[str, int] = {}
    async with sessionmaker() as session:
        locked = (
            await session.execute(text("SELECT pg_try_advisory_lock(:id)"), {"id": _MAINTENANCE_LOCK_ID})
        ).scalar()
        if not locked:
            return out
        try:
            out["stale_jobs"] = await recover_stale(session)
            out["cache_purged"] = await purge_expired_cache(session)
            if settings.google_latlng_retention_days > 0:
                cutoff = datetime.now(UTC) - timedelta(days=settings.google_latlng_retention_days)
                result = await session.execute(
                    update(Business)
                    .where(
                        Business.provider == "google_places",
                        Business.latlng_fetched_at < cutoff,
                        Business.latitude.is_not(None),
                    )
                    .values(latitude=None, longitude=None)
                )
                out["latlng_cleared"] = int(result.rowcount or 0)  # type: ignore[attr-defined]
            result = await session.execute(
                delete(ImportBatch).where(ImportBatch.created_at < datetime.now(UTC) - timedelta(days=7))
            )
            out["import_batches_deleted"] = int(result.rowcount or 0)  # type: ignore[attr-defined]
            await session.commit()
        finally:
            await session.execute(text("SELECT pg_advisory_unlock(:id)"), {"id": _MAINTENANCE_LOCK_ID})
            await session.commit()
    if any(out.values()):
        log.info("maintenance_done", **out)
    return out


class Worker:
    def __init__(
        self,
        sessionmaker: async_sessionmaker[AsyncSession],
        *,
        concurrency: int = 2,
        poll_interval: float = 1.0,
    ) -> None:
        self.sessionmaker = sessionmaker
        self.concurrency = max(1, concurrency)
        self.poll_interval = poll_interval
        self.worker_id = f"{socket.gethostname()}:{os.getpid()}"
        self._stop = asyncio.Event()
        self._tasks: list[asyncio.Task[None]] = []

    async def start(self) -> None:
        log.info("worker_started", worker=self.worker_id, concurrency=self.concurrency)
        self._tasks = [asyncio.create_task(self._slot(i)) for i in range(self.concurrency)]
        self._tasks.append(asyncio.create_task(self._maintenance_loop()))

    async def stop(self) -> None:
        self._stop.set()
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        log.info("worker_stopped", worker=self.worker_id)

    async def run_forever(self) -> None:
        await self.start()
        await self._stop.wait()

    async def _maintenance_loop(self) -> None:
        last = 0.0
        while not self._stop.is_set():
            if time.monotonic() - last > MAINTENANCE_INTERVAL_S:
                try:
                    await run_maintenance(self.sessionmaker)
                except Exception:
                    log.exception("maintenance_failed")
                last = time.monotonic()
            await asyncio.sleep(30)

    async def _slot(self, index: int) -> None:
        while not self._stop.is_set():
            try:
                ran = await self.run_once()
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("worker_loop_error", slot=index)
                ran = False
            if not ran:
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(self._stop.wait(), timeout=self.poll_interval)

    async def run_once(self, *, deadline: float | None = None) -> bool:
        """Claim and run a single job. Returns False when the queue is empty.

        With a ``deadline`` (``time.monotonic()``) the job stops at its next safe point
        after the deadline and is re-queued with a checkpoint."""
        async with self.sessionmaker() as session:
            job = await claim_next(session, self.worker_id)
        if job is None:
            return False
        ctx = JobContext(job, self.sessionmaker, deadline=deadline)
        handler = HANDLERS.get(job.kind)
        log.info("job_started", job_id=job.id, kind=job.kind, attempt=job.attempts, resumed=ctx.resumed)
        beat = asyncio.create_task(self._heartbeat(job.id))
        try:
            if handler is None:
                outcome = JobOutcome(
                    JobStatus.FAILED, error_code="unknown_job", error_message=f"Unknown job {job.kind}"
                )
            else:
                outcome = await handler(ctx)
        except JobYield:
            beat.cancel()
            await release(self.sessionmaker, ctx)
            log.info("job_yielded", job_id=job.id, kind=job.kind, processed=ctx.processed, total=ctx.total)
            return True
        except ProviderError as exc:
            outcome = JobOutcome(JobStatus.FAILED, error_code=exc.code, error_message=exc.message)
        except Exception as exc:
            log.exception("job_crashed", job_id=job.id)
            outcome = JobOutcome(
                JobStatus.FAILED,
                error_code="internal_error",
                error_message=f"Unexpected error ({type(exc).__name__})",
            )
        finally:
            beat.cancel()
        await finish(self.sessionmaker, ctx, outcome)
        log.info(
            "job_finished",
            job_id=job.id,
            kind=job.kind,
            status=outcome.status.value,
            error=outcome.error_code,
            processed=ctx.processed,
            total=ctx.total,
        )
        return True

    async def _heartbeat(self, job_id: int) -> None:
        while True:
            await asyncio.sleep(15)
            try:
                await heartbeat(self.sessionmaker, job_id)
            except Exception:
                log.warning("heartbeat_failed", job_id=job_id)
