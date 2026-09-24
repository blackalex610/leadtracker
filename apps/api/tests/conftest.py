"""Test fixtures.

DB tests run against a real PostgreSQL database (TEST_DATABASE_URL). The schema
is created by running the Alembic migrations, so migrations are tested too.
"""

from __future__ import annotations

import os

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+asyncpg://leadtracker:leadtracker@localhost:5432/leadtracker_test"
)
os.environ.update(
    {
        "DATABASE_URL": TEST_DATABASE_URL,
        "ENVIRONMENT": "test",
        "DEMO_MODE": "false",
        "AUTH_MODE": "none",
        "RUN_WORKER": "false",
        "PROVIDER_API_KEY": "",
        "PAGESPEED_API_KEY": "",
        "LOG_LEVEL": "WARNING",
    }
)

import asyncio  # noqa: E402
from collections.abc import AsyncIterator, Callable  # noqa: E402
from typing import Any  # noqa: E402

import httpx  # noqa: E402
import pytest  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine  # noqa: E402
from sqlalchemy.pool import NullPool  # noqa: E402

from app.config import get_settings  # noqa: E402

get_settings.cache_clear()

from app import db as app_db  # noqa: E402
from app.core.ratelimit import ALL_LIMITERS  # noqa: E402
from app.log import configure_logging  # noqa: E402
from app.models import Base  # noqa: E402
from app.providers.base import BusinessSearchResult, ProviderPlace, SearchParams  # noqa: E402
from app.providers.registry import set_provider  # noqa: E402
from app.services import settings as settings_service  # noqa: E402

configure_logging("WARNING")


def _assert_test_database(url: str) -> None:
    """The suite drops and recreates the schema — never run it against a real database."""
    name = url.rsplit("/", 1)[-1].split("?", 1)[0]
    if not name.endswith("_test") and os.environ.get("ALLOW_TEST_DB_RESET") != "1":
        raise RuntimeError(
            f"Refusing to reset database '{name}': TEST_DATABASE_URL must point to a *_test database"
        )


def _run_migrations() -> None:
    _assert_test_database(TEST_DATABASE_URL)
    from alembic.config import Config

    from alembic import command

    async def reset() -> None:
        engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)
        async with engine.begin() as conn:
            await conn.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
            await conn.execute(text("CREATE SCHEMA public"))
        await engine.dispose()

    asyncio.run(reset())
    cfg = Config(os.path.join(os.path.dirname(__file__), "..", "alembic.ini"))
    os.environ["ALEMBIC_DATABASE_URL"] = TEST_DATABASE_URL
    command.upgrade(cfg, "head")


@pytest.fixture(scope="session")
def migrated() -> None:
    _run_migrations()


@pytest.fixture(scope="session")
async def engine(migrated: None) -> AsyncIterator[Any]:
    eng = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)
    app_db.set_engine(eng)
    yield eng
    await eng.dispose()


@pytest.fixture
async def sessionmaker(engine: Any) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    tables = ", ".join(t.name for t in reversed(Base.metadata.sorted_tables))
    async with engine.begin() as conn:
        await conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
    settings_service.invalidate_cache()
    for limiter in ALL_LIMITERS:
        limiter.reset()
    app_db.set_engine(engine)
    maker = app_db.get_sessionmaker()
    async with maker() as session:
        from app.api.deps import ensure_default_user
        from app.services.presets import seed_builtin_presets

        await seed_builtin_presets(session)
        await ensure_default_user(session)
    yield maker
    set_provider(None)


@pytest.fixture
async def session(sessionmaker: async_sessionmaker[AsyncSession]) -> AsyncIterator[AsyncSession]:
    async with sessionmaker() as s:
        yield s


@pytest.fixture
async def client(sessionmaker: async_sessionmaker[AsyncSession]) -> AsyncIterator[httpx.AsyncClient]:
    from app.main import create_app

    app = create_app(with_lifespan=False)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


def make_place(index: int, **overrides: Any) -> ProviderPlace:
    base: dict[str, Any] = {
        "provider": "google_places",
        "external_id": f"place-{index}",
        "name": f"Test Gym {index}",
        "primary_type": "gym",
        "primary_type_label": "Gym",
        "types": ["gym", "establishment"],
        "formatted_address": f"ul. Test {index}, 1000 Sofia, Bulgaria",
        "city": "Sofia",
        "country_code": "BG",
        "international_phone": f"+359 88 {index:03d} 1234" if index < 1000 else None,
        "website_url": None,
        "maps_url": f"https://maps.google.com/?cid={index}",
        "rating": 4.6,
        "review_count": 120,
        "opening_hours": {
            "periods": [
                {"open": {"day": d, "hour": 7, "minute": 0}, "close": {"day": d, "hour": 22, "minute": 0}}
                for d in range(0, 7)
            ],
            "weekday_descriptions": ["Monday: 7:00 AM – 10:00 PM"],
        },
        "business_status": "OPERATIONAL",
        "photo_count": 10,
    }
    base.update(overrides)
    return ProviderPlace(**base)


class FakeProvider:
    """In-memory provider: ``pages`` maps a text query to a list of result pages."""

    name = "google_places"
    search_sku = "text_search_enterprise"
    details_sku = "place_details_enterprise"

    def __init__(
        self,
        pages: dict[str, list[list[ProviderPlace]]] | None = None,
        errors: dict[str, Exception] | None = None,
    ) -> None:
        self.pages = pages or {}
        self.errors = errors or {}
        self.calls: list[SearchParams] = []
        self.details: dict[str, ProviderPlace] = {}

    def is_configured(self) -> bool:
        return True

    async def aclose(self) -> None:
        return None

    async def search_businesses(self, params: SearchParams) -> BusinessSearchResult:
        self.calls.append(params)
        if params.text_query in self.errors:
            raise self.errors[params.text_query]
        pages = self.pages.get(params.text_query, [[]])
        index = int(params.page_token) if params.page_token else 0
        next_token = str(index + 1) if index + 1 < len(pages) else None
        return BusinessSearchResult(places=pages[index], next_page_token=next_token, sku=self.search_sku)

    async def get_business_details(
        self, external_id: str, *, language_code: str | None = None, region_code: str | None = None
    ) -> ProviderPlace:
        return self.details[external_id]


@pytest.fixture
def fake_provider() -> Callable[..., FakeProvider]:
    def factory(**kwargs: Any) -> FakeProvider:
        provider = FakeProvider(**kwargs)
        set_provider(provider)  # type: ignore[arg-type]
        return provider

    return factory
