"""Serverless (Vercel) mode: configuration, startup, time-boxed resumable jobs."""

from __future__ import annotations

import time
from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest
from pydantic import SecretStr, ValidationError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.api.routes.worker import slice_budget
from app.config import Settings, get_settings, normalize_database_url
from app.core.enums import JobKind, JobStatus, UserRole
from app.core.security import hash_token
from app.db import engine_options
from app.models import Business, Job, SearchQuery, User
from app.serverless import build_app
from app.services import search as search_service
from app.services.settings import update_settings
from app.startup import initialise, migrate_to_head, reset_ready_state
from app.worker.queue import enqueue
from app.worker.runner import Worker
from tests.conftest import FakeProvider, make_place
from tests.test_pipeline import fake_auditor_factory

SPENT = -1.0  # a deadline already in the past: every run does the minimum and yields


def spent_deadline() -> float:
    return time.monotonic() + SPENT


# --- configuration -----------------------------------------------------------------------------


def test_database_url_normalisation() -> None:
    neon = (
        "postgresql://u:p@ep-x-pooler.eu-central-1.aws.neon.tech/neondb"
        "?sslmode=require&channel_binding=require"
    )
    assert normalize_database_url(neon) == (
        "postgresql+asyncpg://u:p@ep-x-pooler.eu-central-1.aws.neon.tech/neondb?ssl=require"
    )
    assert normalize_database_url("postgres://u:p@h:5432/db") == "postgresql+asyncpg://u:p@h:5432/db"


def test_unpooled_url_is_preferred(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@ep-1-pooler.example/db?sslmode=require")
    monkeypatch.setenv("DATABASE_URL_UNPOOLED", "postgresql://u:p@ep-1.example/db?sslmode=require")
    assert Settings(_env_file=None).database_url == "postgresql+asyncpg://u:p@ep-1.example/db?ssl=require"


def test_engine_options() -> None:
    serverless = engine_options("postgresql+asyncpg://u:p@db.example/db", serverless=True, pool_size=5)
    assert serverless["pool_size"] == 2 and serverless["pool_recycle"] == 240
    assert serverless["pool_pre_ping"] and "connect_args" not in serverless
    pooled = engine_options(
        "postgresql+asyncpg://u:p@ep-1-pooler.neon.tech/db", serverless=False, pool_size=5
    )
    assert pooled["pool_size"] == 5 and pooled["connect_args"]["statement_cache_size"] == 0
    name = pooled["connect_args"]["prepared_statement_name_func"]
    assert name() != name()


def test_slice_budget_respects_platform_deadline() -> None:
    def request(headers: dict[str, str]) -> Any:
        return httpx.Request("POST", "http://t/api/worker/run", headers=headers)

    assert slice_budget(request({}), 40) == 40  # type: ignore[arg-type]
    soon = (datetime.now(UTC) + timedelta(seconds=100)).isoformat().replace("+00:00", "Z")
    assert 5 <= slice_budget(request({"x-vercel-internal-deadline": soon}), 40) <= 10  # type: ignore[arg-type]
    late = (datetime.now(UTC) + timedelta(seconds=300)).isoformat()
    assert slice_budget(request({"x-vercel-internal-deadline": late}), 40) == 40  # type: ignore[arg-type]
    assert slice_budget(request({"x-vercel-internal-deadline": "garbage"}), 40) == 40  # type: ignore[arg-type]


def test_serverless_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("RUN_WORKER")
    monkeypatch.setenv("VERCEL", "1")
    settings = Settings(_env_file=None)
    assert settings.serverless and not settings.embedded_worker
    assert settings.on_demand_worker and settings.migrate_on_startup
    monkeypatch.delenv("VERCEL")
    local = Settings(_env_file=None)
    assert not local.serverless and local.embedded_worker and not local.on_demand_worker


def test_public_deployment_requires_auth(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VERCEL_ENV", "production")
    assert any("AUTH_MODE" in p for p in Settings(_env_file=None, auth_mode="none").setup_problems())
    assert Settings(_env_file=None, auth_mode="none", allow_open_access=True).setup_problems() == []
    secured = Settings(_env_file=None, auth_mode="token", secret_key="s" * 40, admin_token="a" * 30)
    assert secured.setup_problems() == []
    monkeypatch.delenv("VERCEL_ENV")
    assert Settings(_env_file=None, auth_mode="none").setup_problems() == []


def test_admin_token_minimum_length() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, admin_token="too-short")


async def test_configuration_errors_are_explained_without_values(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AUTH_MODE", "token")
    monkeypatch.setenv("SECRET_KEY", "tooshort-secret-value")
    get_settings.cache_clear()
    try:
        app = build_app()
    finally:
        monkeypatch.undo()
        get_settings.cache_clear()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as client:
        response = await client.get("/api/meta")
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "setup_required"
    assert "SECRET_KEY" in response.text and "tooshort-secret-value" not in response.text


# --- startup -----------------------------------------------------------------------------------


async def test_migrations_are_skipped_at_head(engine: Any, sessionmaker: Any) -> None:
    assert await migrate_to_head(engine) is False


async def test_admin_token_bootstrap(sessionmaker: async_sessionmaker[AsyncSession]) -> None:
    base: dict[str, Any] = {"_env_file": None, "auth_mode": "token", "secret_key": "s" * 40}
    problems = await initialise(Settings(**base), sessionmaker)
    assert any("ADMIN_TOKEN" in p for p in problems)

    settings = Settings(**base, admin_token="a" * 30, admin_email="Boss@Example.com")
    assert await initialise(settings, sessionmaker) == []
    async with sessionmaker() as session:
        user = (await session.execute(select(User).where(User.email == "boss@example.com"))).scalar_one()
        assert user.token_hash == hash_token("a" * 30) and user.role == UserRole.ADMIN.value

    # Changing ADMIN_TOKEN rotates the stored token; re-running is idempotent.
    rotated = Settings(**base, admin_token="b" * 30, admin_email="boss@example.com")
    assert await initialise(rotated, sessionmaker) == []
    assert await initialise(rotated, sessionmaker) == []
    async with sessionmaker() as session:
        users = (await session.execute(select(User).where(User.email == "boss@example.com"))).scalars().all()
        assert len(users) == 1 and users[0].token_hash == hash_token("b" * 30)


# --- time-boxed, resumable jobs ----------------------------------------------------------------


async def _run_until_done(sessionmaker: async_sessionmaker[AsyncSession], job_id: int) -> tuple[Job, int]:
    worker = Worker(sessionmaker)
    runs = 0
    while True:
        assert await worker.run_once(deadline=spent_deadline())
        runs += 1
        async with sessionmaker() as session:
            job = await session.get(Job, job_id)
            assert job is not None
        if job.status != JobStatus.QUEUED.value:
            return job, runs
        # A yield re-queues the job with a checkpoint and does not use up an attempt.
        assert job.checkpoint and job.attempts == 0 and job.locked_by is None
        assert runs < 30


async def test_time_boxed_search_job_resumes_between_queries(
    sessionmaker: async_sessionmaker[AsyncSession],
    fake_provider: Callable[..., FakeProvider],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    audits: list[str] = []
    monkeypatch.setattr(search_service, "build_auditor", fake_auditor_factory(audits))
    p1, p2, p3, p4, p5 = (
        make_place(1),
        make_place(2, website_url="https://modern.bg/"),
        make_place(3, website_url="https://old.bg/"),
        make_place(4, website_url="https://down.bg/"),
        make_place(5),
    )
    provider = fake_provider(
        pages={
            "gyms in Lozenets, Sofia": [[p1, p2]],
            "gyms in Mladost, Sofia": [[p3], [p4]],
            "gyms in Center, Sofia": [[p5, p1]],
        }
    )
    params = {
        "category": "gyms",
        "location": "Sofia",
        "neighborhoods": ["Lozenets", "Mladost", "Center"],
        "preset_key": "gyms",
        "max_results": 60,
    }
    async with sessionmaker() as session:
        job = await enqueue(session, JobKind.SEARCH, params)
        await session.commit()

    done, runs = await _run_until_done(sessionmaker, job.id)
    assert done.status == JobStatus.COMPLETED.value, done.errors
    assert runs >= 3  # one query per run, then the audits
    assert done.checkpoint is None
    assert done.progress_processed == done.progress_total == 5
    assert done.counters["new"] == 5 and done.counters["duplicates_in_job"] == 1
    assert done.counters["found"] == 5 and done.counters["queries_ok"] == 3
    assert done.counters["audited"] == 3 and done.counters["audit_failed"] == 1
    assert len(provider.calls) == 4  # every page fetched exactly once
    async with sessionmaker() as session:
        assert (await session.execute(select(func.count()).select_from(SearchQuery))).scalar_one() == 3
        assert (await session.execute(select(func.count()).select_from(Business))).scalar_one() == 5


async def test_time_boxed_audit_job_resumes_between_audits(
    sessionmaker: async_sessionmaker[AsyncSession],
    fake_provider: Callable[..., FakeProvider],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    audits: list[str] = []
    monkeypatch.setattr(search_service, "build_auditor", fake_auditor_factory(audits))
    async with sessionmaker() as session:
        await update_settings(session, {"audit": {"max_concurrent": 1}}, None)
    places = [make_place(i, website_url=f"https://site{i}.bg/") for i in range(1, 4)]
    fake_provider(pages={"gyms in Sofia": [places]})
    async with sessionmaker() as session:
        search = await enqueue(
            session,
            JobKind.SEARCH,
            {"category": "gyms", "location": "Sofia", "audit_websites": False, "max_results": 60},
        )
        await session.commit()
    assert await Worker(sessionmaker).run_once()
    async with sessionmaker() as session:
        ids = list((await session.execute(select(Business.id).order_by(Business.id))).scalars())
        job = await enqueue(session, JobKind.AUDIT, {"business_ids": ids, "force": True})
        await session.commit()
    assert search.id != job.id

    done, runs = await _run_until_done(sessionmaker, job.id)
    assert done.status == JobStatus.COMPLETED.value
    assert runs == 3  # one audit per run with a single audit slot
    assert done.progress_processed == done.progress_total == 3
    assert done.counters["audited"] == 3
    assert sorted({a.split("/")[0] for a in audits}) == ["site1.bg", "site2.bg", "site3.bg"]


async def test_time_boxed_rescore_job(sessionmaker: async_sessionmaker[AsyncSession]) -> None:
    async with sessionmaker() as session:
        session.add_all(Business(name=f"Biz {i}", name_key=f"biz {i}", provider="import") for i in range(450))
        await session.commit()
        job = await enqueue(session, JobKind.RESCORE, {})
        await session.commit()
    done, runs = await _run_until_done(sessionmaker, job.id)
    assert done.status == JobStatus.COMPLETED.value
    assert runs == 3  # batches of 200
    assert done.progress_processed == done.progress_total == 450


# --- HTTP: on-demand worker, cron, setup checks ------------------------------------------------


@pytest.fixture
def serverless_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("SERVERLESS", "true")
    monkeypatch.setenv("CRON_SECRET", "c" * 32)
    get_settings.cache_clear()
    reset_ready_state()
    yield
    monkeypatch.undo()
    get_settings.cache_clear()
    reset_ready_state()


def _client() -> httpx.AsyncClient:
    from app.main import create_app

    app = create_app(with_lifespan=False)
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


async def test_worker_run_processes_the_queue(
    serverless_env: None,
    sessionmaker: async_sessionmaker[AsyncSession],
    fake_provider: Callable[..., FakeProvider],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(search_service, "build_auditor", fake_auditor_factory([]))
    monkeypatch.setattr(get_settings(), "provider_api_key", SecretStr("test-key"))
    fake_provider(pages={"gyms in Sofia": [[make_place(1), make_place(2, website_url="https://modern.bg/")]]})
    async with _client() as client:
        assert (await client.get("/api/meta")).json()["on_demand_worker"] is True
        job = (await client.post("/api/search", json={"category": "gyms", "location": "Sofia"})).json()
        assert job["status"] == "queued"
        run = (await client.post("/api/worker/run")).json()
        assert run == {"ran": 1, "queued": 0, "running": 0, "on_demand": True}
        detail = (await client.get(f"/api/search-jobs/{job['id']}")).json()
        assert detail["status"] == "completed" and detail["progress_total"] == 2
        idle = (await client.post("/api/worker/run")).json()
        assert idle["ran"] == 0 and idle["queued"] == 0


async def test_worker_run_only_reports_with_a_resident_worker(client: httpx.AsyncClient) -> None:
    run = (await client.post("/api/worker/run")).json()
    assert run == {"ran": 0, "queued": 0, "running": 0, "on_demand": False}
    assert (await client.get("/api/meta")).json()["on_demand_worker"] is False


async def test_cron_requires_the_secret(
    serverless_env: None, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    async with _client() as client:
        assert (await client.get("/api/worker/cron")).status_code == 401
        wrong = await client.get("/api/worker/cron", headers={"Authorization": "Bearer nope"})
        assert wrong.status_code == 401
        ok = await client.get("/api/worker/cron", headers={"Authorization": f"Bearer {'c' * 32}"})
        assert ok.status_code == 200
        assert ok.json()["jobs"] == {"ran": 0, "queued": 0, "running": 0}


async def test_open_public_deployment_is_refused(
    serverless_env: None, sessionmaker: async_sessionmaker[AsyncSession], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("VERCEL_ENV", "production")
    get_settings.cache_clear()
    async with _client() as client:
        assert (await client.get("/api/health")).status_code == 200
        response = await client.get("/api/meta")
        assert response.status_code == 503
        body = response.json()["detail"]
        assert body["code"] == "setup_required" and "AUTH_MODE" in body["message"]
