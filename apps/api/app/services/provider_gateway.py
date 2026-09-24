"""Wraps a provider with result caching, request de-duplication and usage tracking.

A text search is cached as a whole result set (all pages fetched), keyed by the
parameters that define it. Concurrent identical searches wait on a per-key lock
and are then served from the cache, so the provider is only paid once.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import weakref
from collections.abc import AsyncGenerator, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.log import get_logger
from app.models import ProviderCache
from app.providers.base import BusinessSearchProvider, ProviderError, ProviderPlace, SearchParams
from app.services.usage import record_usage

log = get_logger(__name__)

_locks: weakref.WeakValueDictionary[str, asyncio.Lock] = weakref.WeakValueDictionary()


def _lock_for(key: str) -> asyncio.Lock:
    lock = _locks.get(key)
    if lock is None:
        lock = asyncio.Lock()
        _locks[key] = lock
    return lock


def cache_key(provider: str, operation: str, identity: dict[str, Any]) -> str:
    blob = json.dumps({"p": provider, "o": operation, "i": identity}, sort_keys=True, default=str)
    return hashlib.sha256(blob.encode()).hexdigest()


@dataclass(slots=True)
class SearchPage:
    places: list[ProviderPlace]
    page_number: int
    cached: bool


class ProviderGateway:
    def __init__(
        self,
        provider: BusinessSearchProvider,
        session_factory: async_sessionmaker[AsyncSession] | Callable[[], AsyncSession],
    ) -> None:
        self.provider = provider
        self._session_factory = session_factory

    async def _get_cached(self, key: str) -> dict[str, Any] | None:
        async with self._session_factory() as session:
            row = await session.get(ProviderCache, key)
            if row is None or row.expires_at <= datetime.now(UTC):
                return None
            return row.payload

    async def _put_cached(self, key: str, operation: str, payload: dict[str, Any], ttl_hours: int) -> None:
        if ttl_hours <= 0:
            return
        async with self._session_factory() as session:
            await session.merge(
                ProviderCache(
                    key=key,
                    provider=self.provider.name,
                    operation=operation,
                    payload=payload,
                    created_at=datetime.now(UTC),
                    expires_at=datetime.now(UTC) + timedelta(hours=ttl_hours),
                )
            )
            await session.commit()

    async def _record(self, **kwargs: Any) -> None:
        async with self._session_factory() as session:
            await record_usage(session, provider=self.provider.name, **kwargs)
            await session.commit()

    async def iter_search(
        self,
        params: SearchParams,
        *,
        max_results: int,
        cache_ttl_hours: int,
        job_id: int | None = None,
    ) -> AsyncGenerator[SearchPage, None]:
        """Yield result pages for a text search, from cache when possible.

        Raises :class:`ProviderError` if the first page fails. If a later page
        fails, pages already yielded stand and the error propagates.
        """
        max_pages = max(1, -(-max_results // max(1, params.page_size)))
        identity = params.cache_identity()
        key = cache_key(self.provider.name, "text_search", identity)

        async with _lock_for(key):
            cached = await self._get_cached(key) if cache_ttl_hours > 0 else None
            if cached is not None:
                pages: list[list[dict[str, Any]]] = cached.get("pages", [])
                if cached.get("exhausted") or len(pages) >= max_pages:
                    served = pages[:max_pages]
                    await self._record(
                        operation="text_search",
                        sku=self.provider.search_sku,
                        cached=True,
                        units=len(served),
                        job_id=job_id,
                    )
                    for index, page in enumerate(served, start=1):
                        yield SearchPage([ProviderPlace.from_cache(p) for p in page], index, cached=True)
                    return

            fetched: list[list[dict[str, Any]]] = []
            token: str | None = None
            exhausted = False
            for page_number in range(1, max_pages + 1):
                page_params = SearchParams(**{**_params_dict(params), "page_token": token})
                try:
                    result = await self.provider.search_businesses(page_params)
                except ProviderError as exc:
                    await self._record(
                        operation="text_search",
                        sku=self.provider.search_sku,
                        success=False,
                        status_code=exc.status_code,
                        error_code=exc.code,
                        job_id=job_id,
                    )
                    raise
                await self._record(operation="text_search", sku=result.sku, job_id=job_id)
                fetched.append([p.to_cache() for p in result.places])
                yield SearchPage(result.places, page_number, cached=False)
                token = result.next_page_token
                if not token or not result.places:
                    exhausted = True
                    break

            await self._put_cached(
                key, "text_search", {"pages": fetched, "exhausted": exhausted}, cache_ttl_hours
            )

    async def get_details(
        self,
        external_id: str,
        *,
        language_code: str | None,
        region_code: str | None,
        job_id: int | None = None,
    ) -> ProviderPlace:
        try:
            place = await self.provider.get_business_details(
                external_id, language_code=language_code, region_code=region_code
            )
        except ProviderError as exc:
            await self._record(
                operation="place_details",
                sku=self.provider.details_sku,
                success=False,
                status_code=exc.status_code,
                error_code=exc.code,
                job_id=job_id,
            )
            raise
        await self._record(operation="place_details", sku=self.provider.details_sku, job_id=job_id)
        return place


def _params_dict(params: SearchParams) -> dict[str, Any]:
    return {
        "text_query": params.text_query,
        "region_code": params.region_code,
        "language_code": params.language_code,
        "min_rating": params.min_rating,
        "included_type": params.included_type,
        "open_now": params.open_now,
        "page_size": params.page_size,
    }


async def purge_expired_cache(session: AsyncSession) -> int:
    result = await session.execute(delete(ProviderCache).where(ProviderCache.expires_at <= datetime.now(UTC)))
    return int(result.rowcount or 0)  # type: ignore[attr-defined]
