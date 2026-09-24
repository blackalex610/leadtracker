"""Standalone worker process: ``python -m app.worker``."""

from __future__ import annotations

import asyncio
import signal

from app.config import get_settings
from app.db import dispose_engine, get_sessionmaker
from app.log import configure_logging, register_secret
from app.providers.registry import close_provider
from app.worker.runner import Worker


async def main() -> None:
    settings = get_settings()
    configure_logging(settings.log_level, settings.use_json_logs)
    if settings.provider_api_key:
        register_secret(settings.provider_api_key.get_secret_value())
    worker = Worker(
        get_sessionmaker(),
        concurrency=settings.worker_concurrency,
        poll_interval=settings.worker_poll_interval_seconds,
    )
    loop = asyncio.get_running_loop()
    stop = asyncio.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)
    await worker.start()
    await stop.wait()
    await worker.stop()
    await close_provider()
    await dispose_engine()


if __name__ == "__main__":
    asyncio.run(main())
