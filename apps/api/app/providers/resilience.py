"""Rate limiting and retry with exponential backoff for provider calls."""

from __future__ import annotations

import asyncio
import random
import time
from collections.abc import Awaitable, Callable
from typing import TypeVar

from app.log import get_logger
from app.providers.base import ProviderError

T = TypeVar("T")
log = get_logger(__name__)

SleepFn = Callable[[float], Awaitable[None]]


class AsyncRateLimiter:
    """Token bucket: at most ``rate`` acquisitions per second (bursts up to ``burst``)."""

    def __init__(
        self,
        rate: float,
        burst: int = 1,
        clock: Callable[[], float] = time.monotonic,
        sleep: SleepFn = asyncio.sleep,
    ) -> None:
        if rate <= 0:
            raise ValueError("rate must be positive")
        self.rate = rate
        self.burst = max(1, burst)
        self._tokens = float(self.burst)
        self._clock = clock
        self._sleep = sleep
        self._updated = clock()
        self._lock = asyncio.Lock()

    def set_rate(self, rate: float) -> None:
        if rate > 0:
            self.rate = rate

    async def acquire(self) -> None:
        async with self._lock:
            while True:
                now = self._clock()
                self._tokens = min(self.burst, self._tokens + (now - self._updated) * self.rate)
                self._updated = now
                if self._tokens >= 1:
                    self._tokens -= 1
                    return
                await self._sleep((1 - self._tokens) / self.rate)


async def with_retries(
    operation: Callable[[], Awaitable[T]],
    *,
    attempts: int = 4,
    base_delay: float = 1.0,
    max_delay: float = 16.0,
    sleep: SleepFn = asyncio.sleep,
    op_name: str = "provider_call",
) -> T:
    """Retry ``operation`` on retryable :class:`ProviderError` with exponential backoff + jitter."""
    attempt = 0
    while True:
        attempt += 1
        try:
            return await operation()
        except ProviderError as exc:
            if not exc.retryable or attempt >= attempts:
                raise
            delay = min(max_delay, base_delay * (2 ** (attempt - 1)))
            if exc.retry_after:
                delay = min(max_delay, max(delay, exc.retry_after))
            delay *= 0.8 + random.random() * 0.4
            log.warning("provider_retry", op=op_name, attempt=attempt, error=exc.code, delay=round(delay, 2))
            await sleep(delay)
