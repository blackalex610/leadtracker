"""Database-backed tests: dedupe/upsert, search jobs, audits, suppression."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import httpx
import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.audit.fetcher import SafeFetcher
from app.audit.service import AuditOptions, WebsiteAuditor
from app.core.enums import JobKind, JobStatus, LeadStatus
from app.models import ApiUsage, Business, BusinessContact, BusinessSource, Job, JobBusiness, SearchQuery
from app.providers.base import ProviderAuthError, ProviderUnavailableError
from app.services import search as search_service
from app.services.businesses import BusinessRecord, record_from_place, upsert_business
from app.services.suppression import suppress
from app.worker.queue import enqueue
from app.worker.runner import Worker
from tests.conftest import FakeProvider, make_place

SITE_HTML = {
    "modern.bg": """<html><head><meta name=viewport content="width=device-width"><title>Modern</title>
        <meta name=description content=x></head><body><h1>Modern Gym</h1><a href="https://fresha.com/x">Book now</a>
        <p>Тел: <a href="tel:+359888000111">0888 000 111</a> ул. Шипка 1. Работно време 07:00–22:00. Цени от 30 €</p>
        </body></html>""",
    "old.bg": """<html><head><title>Old</title></head><body><center><font>Welcome to our website</font>
        <table width=900><tr><td>© 2012</td></tr></table></center></body></html>""",
}


def fake_auditor_factory(calls: list[str]) -> Callable[[Any], WebsiteAuditor]:
    def handler(request: httpx.Request) -> httpx.Response:
        host = request.headers["host"]
        calls.append(f"{host}{request.url.path}")
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        if host == "down.bg":
            raise httpx.ConnectError("refused", request=request)
        return httpx.Response(200, html=SITE_HTML.get(host, "<html><body>hi</body></html>"))

    async def resolver(host: str, port: int) -> list[str]:
        return ["93.184.216.34"]

    def factory(_audit_settings: Any) -> WebsiteAuditor:
        fetcher = SafeFetcher(transport=httpx.MockTransport(handler), resolver=resolver)
        return WebsiteAuditor(fetcher, AuditOptions(check_assets=False))

    return factory


async def run_job(
    sessionmaker: async_sessionmaker[AsyncSession], params: dict[str, Any], kind: JobKind = JobKind.SEARCH
) -> Job:
    async with sessionmaker() as session:
        job = await enqueue(session, kind, params)
        await session.commit()
        job_id = job.id
    assert await Worker(sessionmaker).run_once()
    async with sessionmaker() as session:
        result = await session.get(Job, job_id)
        assert result is not None
        return result


async def count(session: AsyncSession, model: Any) -> int:
    return int((await session.execute(select(func.count()).select_from(model))).scalar_one())


# --- upsert / dedupe ------------------------------------------------------------------------------


async def test_same_place_twice_creates_one_business(session: AsyncSession) -> None:
    first = await upsert_business(session, record_from_place(make_place(1)))
    second = await upsert_business(session, record_from_place(make_place(1, rating=4.9, review_count=130)))
    await session.commit()
    assert first.created and not second.created
    assert second.match_reason == "provider_place_id"
    assert await count(session, Business) == 1
    business = await session.get(Business, first.business.id)
    assert business is not None and business.rating == 4.9 and business.review_count == 130
    assert business.normalized_phone == "+359880011234"


async def test_phone_and_similar_name_merge_across_places(session: AsyncSession) -> None:
    await upsert_business(session, record_from_place(make_place(1, name="Pulse Fitness Lozenets")))
    other = await upsert_business(
        session,
        record_from_place(make_place(2, name="Pulse Fitness", international_phone="+359 88 001 1234")),
    )
    await session.commit()
    assert not other.created and other.match_reason == "phone"
    assert await count(session, Business) == 1
    assert await count(session, BusinessSource) == 2  # both Google listings are kept as sources


async def test_same_phone_different_business_is_not_merged(session: AsyncSession) -> None:
    await upsert_business(session, record_from_place(make_place(1, name="Pulse Fitness")))
    other = await upsert_business(
        session,
        record_from_place(make_place(2, name="Sunrise Dental", international_phone="+359 88 001 1234")),
    )
    await session.commit()
    assert other.created


async def test_domain_and_name_address_matching(session: AsyncSession) -> None:
    await upsert_business(session, record_from_place(make_place(1, website_url="https://bella.bg/")))
    by_domain = await upsert_business(
        session,
        BusinessRecord(name="Test Gym 1", provider="import", website_url="http://www.bella.bg/contact"),
    )
    await upsert_business(session, record_from_place(make_place(5, international_phone=None)))
    by_address = await upsert_business(
        session,
        BusinessRecord(
            name="TEST GYM 5 ЕООД",
            provider="import",
            address="ul. Test 5, 1000 Sofia, Bulgaria",
            city="Sofia",
        ),
    )
    await session.commit()
    assert by_domain.match_reason == "website_domain"
    assert by_address.match_reason == "name_address"


async def test_social_domains_are_not_used_for_matching(session: AsyncSession) -> None:
    await upsert_business(
        session,
        record_from_place(make_place(1, website_url="https://facebook.com/a", international_phone=None)),
    )
    other = await upsert_business(
        session,
        record_from_place(make_place(2, website_url="https://facebook.com/b", international_phone=None)),
    )
    assert other.created
    business = other.business
    assert business.website_kind == "social" and business.website_status == "none"


async def test_import_fill_only_never_overwrites(session: AsyncSession) -> None:
    created = await upsert_business(session, record_from_place(make_place(1, rating=4.1)))
    merged = await upsert_business(
        session,
        BusinessRecord(
            name="Test Gym 1",
            provider="import",
            phones=["0880011234"],
            rating=2.0,
            website_url="https://new.bg",
        ),
        fill_only=True,
    )
    await session.commit()
    assert merged.business.id == created.business.id
    assert merged.business.rating == 4.1
    assert merged.business.website_url == "https://new.bg"  # was empty, so it is filled


async def test_duplicate_numbers_are_stored_once(session: AsyncSession) -> None:
    await upsert_business(session, record_from_place(make_place(1)))
    await upsert_business(session, record_from_place(make_place(1)))
    await session.commit()
    assert await count(session, BusinessContact) == 1


async def test_suppressed_number_is_flagged_on_discovery(session: AsyncSession) -> None:
    await suppress(session, normalized_phone="+359880011234", business_id=None, reason="asked", user_id=None)
    outcome = await upsert_business(session, record_from_place(make_place(1)))
    await session.commit()
    assert outcome.business.suppressed
    assert outcome.business.status == LeadStatus.DO_NOT_CONTACT.value


# --- search jobs ----------------------------------------------------------------------------------


async def test_search_job_end_to_end_and_rerun_is_idempotent(
    sessionmaker: async_sessionmaker[AsyncSession],
    fake_provider: Callable[..., FakeProvider],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    audits: list[str] = []
    monkeypatch.setattr(search_service, "build_auditor", fake_auditor_factory(audits))
    places = [
        make_place(1, website_url=None),
        make_place(2, website_url="https://modern.bg/"),
        make_place(3, website_url="https://old.bg/"),
        make_place(4, website_url="https://down.bg/"),
        make_place(5, website_url="https://www.facebook.com/five"),
    ]
    provider = fake_provider(pages={"gyms in Sofia": [places[:3], places[3:]]})
    params = {
        "category": "gyms",
        "location": "Sofia",
        "preset_key": "gyms",
        "max_results": 60,
        "min_rating": 4.0,
    }

    job = await run_job(sessionmaker, params)
    assert job.status == JobStatus.COMPLETED.value, job.errors
    assert job.progress_processed == job.progress_total == 5
    assert job.counters["new"] == 5
    assert job.counters["audited"] == 3
    assert job.counters["audit_failed"] == 1
    assert len(provider.calls) == 2  # two pages

    async with sessionmaker() as session:
        rows = {b.name: b for b in (await session.execute(select(Business))).scalars()}
        assert rows["Test Gym 1"].opportunity_types[:1] == ["NO_WEBSITE"]
        assert rows["Test Gym 1"].priority == "HOT"
        assert (
            rows["Test Gym 2"].website_status == "ok" and (rows["Test Gym 2"].website_health_score or 0) > 60
        )
        assert "BROKEN_WEBSITE" in rows["Test Gym 4"].opportunity_types
        assert rows["Test Gym 4"].website_status == "broken"
        assert "OUTDATED_WEBSITE" in rows["Test Gym 3"].opportunity_types or rows["Test Gym 3"].outdated_score
        assert rows["Test Gym 5"].opportunity_types[:1] == ["NO_WEBSITE"]
        assert all(b.niche_key == "gyms" for b in rows.values())
        assert await count(session, JobBusiness) == 5
        usage = (await session.execute(select(ApiUsage))).scalars().all()
        assert [u.cached for u in usage] == [False, False]

    audits.clear()
    rerun = await run_job(sessionmaker, params)
    assert rerun.status == JobStatus.COMPLETED.value
    assert rerun.counters["existing"] == 5 and "new" not in rerun.counters
    assert rerun.counters["cached_requests"] == 2
    assert len(provider.calls) == 2  # served from cache, no new provider calls
    assert rerun.counters.get("audit_cached", 0) >= 2
    async with sessionmaker() as session:
        assert await count(session, Business) == 5


async def test_filters_mark_non_matching_results(
    sessionmaker: async_sessionmaker[AsyncSession],
    fake_provider: Callable[..., FakeProvider],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(search_service, "build_auditor", fake_auditor_factory([]))
    fake_provider(
        pages={
            "gyms in Sofia": [
                [
                    make_place(1),
                    make_place(2, review_count=5),
                    make_place(3, website_url="https://modern.bg/"),
                ]
            ]
        }
    )
    job = await run_job(
        sessionmaker,
        {"category": "gyms", "location": "Sofia", "min_reviews": 10, "has_website": "no", "min_rating": None},
    )
    assert job.counters["matched"] == 1
    assert job.counters["filtered_out"] == 2


async def test_neighborhood_expansion_and_partial_failure(
    sessionmaker: async_sessionmaker[AsyncSession],
    fake_provider: Callable[..., FakeProvider],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(search_service, "build_auditor", fake_auditor_factory([]))
    fake_provider(
        pages={
            "barbers in Lozenets, Sofia": [[make_place(1), make_place(2)]],
            "barbers in Mladost, Sofia": [[make_place(2), make_place(3)]],
        },
        errors={"barbers in Center, Sofia": ProviderUnavailableError()},
    )
    job = await run_job(
        sessionmaker,
        {
            "category": "barbers",
            "location": "Sofia",
            "min_rating": None,
            "neighborhoods": ["Lozenets", "Mladost", "Center"],
        },
    )
    assert job.status == JobStatus.PARTIAL.value
    assert job.progress_total == 3  # place 2 appeared twice but was stored once
    async with sessionmaker() as session:
        queries = (await session.execute(select(SearchQuery).order_by(SearchQuery.id))).scalars().all()
        assert [q.status for q in queries] == ["ok", "ok", "failed"]
        assert await count(session, Business) == 3


async def test_fatal_provider_error_fails_job_with_code(
    sessionmaker: async_sessionmaker[AsyncSession],
    fake_provider: Callable[..., FakeProvider],
) -> None:
    fake_provider(errors={"gyms in Sofia": ProviderAuthError()})
    job = await run_job(sessionmaker, {"category": "gyms", "location": "Sofia"})
    assert job.status == JobStatus.FAILED.value
    assert job.error_code == "invalid_api_key"


async def test_cancelled_job_keeps_saved_businesses(
    sessionmaker: async_sessionmaker[AsyncSession],
    fake_provider: Callable[..., FakeProvider],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_provider(pages={"gyms in Sofia": [[make_place(1)], [make_place(2)]]})
    original = search_service._save_page

    async def save_then_cancel(ctx: Any, *args: Any, **kwargs: Any) -> None:
        await original(ctx, *args, **kwargs)
        async with sessionmaker() as session:
            job = await session.get(Job, ctx.job_id)
            assert job is not None
            job.cancel_requested = True
            await session.commit()

    monkeypatch.setattr(search_service, "_save_page", save_then_cancel)
    job = await run_job(sessionmaker, {"category": "gyms", "location": "Sofia", "min_rating": None})
    assert job.status == JobStatus.CANCELLED.value
    async with sessionmaker() as session:
        assert await count(session, Business) == 1


async def test_audit_job_for_single_lead(
    sessionmaker: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(search_service, "build_auditor", fake_auditor_factory([]))
    async with sessionmaker() as session:
        outcome = await upsert_business(
            session, record_from_place(make_place(1, website_url="https://old.bg/"))
        )
        await session.commit()
        business_id = outcome.business.id
    job = await run_job(sessionmaker, {"business_ids": [business_id], "force": True}, kind=JobKind.AUDIT)
    assert job.status == JobStatus.COMPLETED.value
    async with sessionmaker() as session:
        business = await session.get(Business, business_id)
        assert business is not None and business.last_audit_id is not None
        assert business.website_health_score is not None and business.website_health_score < 60
