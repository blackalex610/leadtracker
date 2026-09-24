"""Small in-memory sliding-window rate limiter for expensive endpoints.

Per process; for multi-instance deployments put a shared limiter (e.g. at the
reverse proxy) in front as well.
"""

from __future__ import annotations

import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request, status


class SlidingWindowLimiter:
    def __init__(self, limit: int, window_seconds: float) -> None:
        self.limit = limit
        self.window = window_seconds
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def hit(self, key: str) -> bool:
        now = time.monotonic()
        bucket = self._hits[key]
        while bucket and now - bucket[0] > self.window:
            bucket.popleft()
        if len(bucket) >= self.limit:
            return False
        bucket.append(now)
        if len(self._hits) > 10_000:
            for k in [k for k, v in self._hits.items() if not v][:5000]:
                del self._hits[k]
        return True

    def reset(self) -> None:
        self._hits.clear()


def client_key(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def rate_limit(limiter: SlidingWindowLimiter, scope: str):  # type: ignore[no-untyped-def]
    async def dependency(request: Request) -> None:
        if not limiter.hit(f"{scope}:{client_key(request)}"):
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail={"code": "rate_limited", "message": "Too many requests, slow down."},
            )

    return dependency


search_limiter = SlidingWindowLimiter(limit=20, window_seconds=60)
audit_limiter = SlidingWindowLimiter(limit=120, window_seconds=60)
login_limiter = SlidingWindowLimiter(limit=10, window_seconds=60)
import_limiter = SlidingWindowLimiter(limit=20, window_seconds=60)
ALL_LIMITERS = (search_limiter, audit_limiter, login_limiter, import_limiter)
