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
from app.data.targets import TARGETS
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

# The planner runs ICP targets in order, city-wide first.
Q1, Q2, Q3 = (f"{t.query} в Sofia" for t in TARGETS[:3])
CITY_ONLY = {"location": "Sofia", "use_neighborhoods": False}


async def test_search_job_end_to_end_categorizes_and_audits(
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
    provider = fake_provider(pages={Q1: [places[:3], places[3:]]})
    params = {**CITY_ONLY, "max_queries": 1}

    job = await run_job(sessionmaker, params)
    assert job.status == JobStatus.COMPLETED.value, job.errors
    assert job.progress_processed == job.progress_total == 5
    assert job.counters["new"] == 5
    assert job.counters["audited"] == 3
    assert job.counters["audit_failed"] == 1
    assert len(provider.calls) == 2  # two pages
    assert provider.calls[0].text_query == Q1

    async with sessionmaker() as session:
        rows = {b.name: b for b in (await session.execute(select(Business))).scalars()}
        assert {name: b.lead_category for name, b in rows.items()} == {
            "Test Gym 1": "NO_SITE",
            "Test Gym 2": "NOT_A_FIT",  # good site with booking, prices, hours
            "Test Gym 3": "WEAK_SITE",
            "Test Gym 4": "BROKEN_SITE",
            "Test Gym 5": "SOCIAL_ONLY",
        }
        assert rows["Test Gym 1"].priority == "HOT"
        assert rows["Test Gym 1"].deal_value == 390  # plumbers: premium price
        assert (
            rows["Test Gym 4"].expected_value > rows["Test Gym 1"].expected_value
        )  # broken site closes best
        assert rows["Test Gym 2"].priority == "COLD"
        assert all(b.target_key == TARGETS[0].key for b in rows.values())
        matched = set(
            (
                await session.execute(
                    select(JobBusiness.business_id).where(JobBusiness.matched_filters.is_(True))
                )
            ).scalars()
        )
        assert {b.name for b in rows.values() if b.id in matched} == {
            "Test Gym 1",
            "Test Gym 3",
            "Test Gym 4",
            "Test Gym 5",
        }
        usage = (await session.execute(select(ApiUsage))).scalars().all()
        assert [u.cached for u in usage] == [False, False]
    assert job.counters["dropped_after_audit"] == 1

    # Clicking again never repeats a query from the last 30 days: it moves on to the next target.
    rerun = await run_job(sessionmaker, params)
    assert rerun.status == JobStatus.COMPLETED.value
    assert [c.text_query for c in provider.calls[2:]] == [Q2]
    async with sessionmaker() as session:
        assert await count(session, Business) == 5


async def test_no_fresh_queries_left(
    sessionmaker: async_sessionmaker[AsyncSession],
    fake_provider: Callable[..., FakeProvider],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(search_service, "TARGETS", TARGETS[:1])
    provider = fake_provider(pages={Q1: [[make_place(1)]]})
    await run_job(sessionmaker, CITY_ONLY)
    again = await run_job(sessionmaker, CITY_ONLY)
    assert again.status == JobStatus.COMPLETED.value
    assert again.errors[0]["code"] == "no_fresh_queries"
    assert len(provider.calls) == 1


async def test_rotation_moves_on_to_the_next_target(
    sessionmaker: async_sessionmaker[AsyncSession],
    fake_provider: Callable[..., FakeProvider],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(search_service, "build_auditor", fake_auditor_factory([]))
    provider = fake_provider(pages={Q1: [[make_place(1)]], Q2: [[make_place(1), make_place(2)]]})
    await run_job(sessionmaker, {**CITY_ONLY, "max_queries": 1})
    second = await run_job(sessionmaker, {**CITY_ONLY, "max_queries": 1})
    assert [c.text_query for c in provider.calls] == [Q1, Q2]
    # Place 1 is already a lead: only the new business counts as a fresh lead.
    assert second.counters["matched"] == 1
    assert second.counters["rejected_already_known"] == 1


async def test_icp_gate_and_stop_at_target(
    sessionmaker: async_sessionmaker[AsyncSession],
    fake_provider: Callable[..., FakeProvider],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(search_service, "build_auditor", fake_auditor_factory([]))
    provider = fake_provider(
        pages={
            Q1: [
                [
                    make_place(1),  # no website -> lead
                    make_place(2, international_phone=None),  # can't be called
                    make_place(3, name="Vianor Люлин"),  # chain branch
                    make_place(4, rating=2.6, review_count=50),  # badly rated
                    make_place(5, business_status="CLOSED_PERMANENTLY"),
                ]
            ],
            Q2: [[make_place(6), make_place(7), make_place(8)]],
            Q3: [[make_place(9)]],
        }
    )
    job = await run_job(sessionmaker, {**CITY_ONLY, "target_leads": 2, "max_queries": 5})
    assert job.status == JobStatus.COMPLETED.value
    assert job.counters["matched"] == 2
    assert job.counters["rejected_no_phone"] == 1
    assert job.counters["rejected_not_a_fit"] == 3
    assert [c.text_query for c in provider.calls] == [Q1, Q2]  # stopped once 2 leads were found
    async with sessionmaker() as session:
        assert await count(session, Business) == 6  # places 7 and 8 were never saved
        chain = (await session.execute(select(Business).where(Business.name == "Vianor Люлин"))).scalar_one()
        assert chain.lead_category == "NOT_A_FIT" and "chain" in (chain.category_reason or "")


async def test_unaudited_websites_count_half_toward_the_target(
    sessionmaker: async_sessionmaker[AsyncSession],
    fake_provider: Callable[..., FakeProvider],
) -> None:
    sites = [make_place(i, website_url=f"https://site{i}.bg/") for i in range(1, 5)]
    fake_provider(pages={Q1: [sites]})
    job = await run_job(sessionmaker, {**CITY_ONLY, "target_leads": 2, "audit_websites": False})
    assert job.counters["matched"] == 4  # 4 x 0.5 = 2


async def test_partial_failure_and_dedupe_across_queries(
    sessionmaker: async_sessionmaker[AsyncSession],
    fake_provider: Callable[..., FakeProvider],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(search_service, "build_auditor", fake_auditor_factory([]))
    fake_provider(
        pages={Q1: [[make_place(1), make_place(2)]], Q3: [[make_place(2), make_place(3)]]},
        errors={Q2: ProviderUnavailableError()},
    )
    job = await run_job(sessionmaker, {**CITY_ONLY, "max_queries": 3})
    assert job.status == JobStatus.PARTIAL.value
    assert job.progress_total == 3  # place 2 appeared twice but was stored once
    assert job.counters["duplicates_in_job"] == 1
    async with sessionmaker() as session:
        queries = (await session.execute(select(SearchQuery).order_by(SearchQuery.id))).scalars().all()
        assert [q.status for q in queries] == ["ok", "failed", "ok"]
        assert await count(session, Business) == 3
    # The failed query is not "used up": the next search retries it.
    async with sessionmaker() as session:
        retry_plan = await search_service.plan_queries(
            session, search_service.SearchRequest(**CITY_ONLY, max_queries=1)
        )
    assert [q.text for q in retry_plan] == [Q2]


async def test_fatal_provider_error_fails_job_with_code(
    sessionmaker: async_sessionmaker[AsyncSession],
    fake_provider: Callable[..., FakeProvider],
) -> None:
    fake_provider(errors={Q1: ProviderAuthError()})
    job = await run_job(sessionmaker, CITY_ONLY)
    assert job.status == JobStatus.FAILED.value
    assert job.error_code == "invalid_api_key"


async def test_cancelled_job_keeps_saved_businesses(
    sessionmaker: async_sessionmaker[AsyncSession],
    fake_provider: Callable[..., FakeProvider],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_provider(pages={Q1: [[make_place(1)], [make_place(2)]]})
    original = search_service._save_page

    async def save_then_cancel(ctx: Any, *args: Any, **kwargs: Any) -> float:
        leads = await original(ctx, *args, **kwargs)
        async with sessionmaker() as session:
            job = await session.get(Job, ctx.job_id)
            assert job is not None
            job.cancel_requested = True
            await session.commit()
        return leads

    monkeypatch.setattr(search_service, "_save_page", save_then_cancel)
    job = await run_job(sessionmaker, CITY_ONLY)
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
