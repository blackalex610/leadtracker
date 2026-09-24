"""HTTP API tests (ASGI in-process, real Postgres)."""

from __future__ import annotations

import csv
import io
from collections.abc import Callable
from typing import Any

import httpx
import pytest
from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import get_settings
from app.models import Business, SuppressionEntry
from app.services.businesses import record_from_place, upsert_business
from app.services.presets import load_niches
from app.services.scoring_service import rescore_business
from app.services.settings import load_settings
from tests.conftest import FakeProvider, make_place


async def seed(sessionmaker: async_sessionmaker[AsyncSession], places: list[Any]) -> list[int]:
    ids: list[int] = []
    async with sessionmaker() as session:
        runtime = await load_settings(session, use_cache=False)
        niches = await load_niches(session)
        for place in places:
            outcome = await upsert_business(session, record_from_place(place), niche_key="gyms")
            await rescore_business(session, outcome.business, runtime, niches)
            ids.append(outcome.business.id)
        await session.commit()
    return ids


@pytest.fixture
async def leads(sessionmaker: async_sessionmaker[AsyncSession]) -> list[int]:
    return await seed(
        sessionmaker,
        [
            make_place(1, name="Alpha Gym"),  # no website, phone -> HOT
            make_place(2, name="Бета Фитнес", website_url="https://facebook.com/beta"),  # social only
            make_place(3, name="Gamma Gym", international_phone=None, review_count=3),  # no phone -> COLD
            make_place(4, name="Delta Gym", website_url="https://delta.bg", rating=3.9),  # unaudited site
        ],
    )


async def test_list_leads_default_sort_and_pagination(client: httpx.AsyncClient, leads: list[int]) -> None:
    response = await client.get("/api/leads", params={"page_size": 2})
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 4 and len(data["items"]) == 2
    first = data["items"][0]
    assert first["priority"] == "HOT"
    assert first["top_reason"]
    page2 = (await client.get("/api/leads", params={"page_size": 2, "page": 2})).json()
    assert {i["id"] for i in page2["items"]}.isdisjoint({i["id"] for i in data["items"]})


async def test_filters(client: httpx.AsyncClient, leads: list[int]) -> None:
    async def names(**params: Any) -> list[str]:
        response = await client.get("/api/leads", params=params)
        assert response.status_code == 200, response.text
        return sorted(i["name"] for i in response.json()["items"])

    assert await names(has_phone="false") == ["Gamma Gym"]
    assert await names(opportunity="NO_WEBSITE") == ["Alpha Gym", "Gamma Gym", "Бета Фитнес"]
    assert await names(has_website="true") == ["Delta Gym"]
    assert await names(priority=["HOT", "WARM"], has_phone="true") == ["Alpha Gym", "Бета Фитнес"]
    assert await names(q="бета") == ["Бета Фитнес"]
    assert await names(q="0011234") == ["Alpha Gym"]
    assert await names(min_rating=4.0) == ["Alpha Gym", "Gamma Gym", "Бета Фитнес"]
    assert await names(contacted="false") == ["Alpha Gym", "Delta Gym", "Gamma Gym", "Бета Фитнес"]
    assert await names(google_opportunity="true") == ["Gamma Gym"]


async def test_sorting(client: httpx.AsyncClient, leads: list[int]) -> None:
    by_name = (await client.get("/api/leads", params={"sort": "name", "order": "asc"})).json()["items"]
    assert [i["name"] for i in by_name] == ["Alpha Gym", "Delta Gym", "Gamma Gym", "Бета Фитнес"]
    by_reviews = (await client.get("/api/leads", params={"sort": "review_count", "order": "asc"})).json()[
        "items"
    ]
    assert by_reviews[0]["name"] == "Gamma Gym"
    bad = await client.get("/api/leads", params={"sort": "drop table"})
    assert bad.status_code == 422
    assert bad.json()["detail"]["code"] == "validation_error"


async def test_lead_detail(client: httpx.AsyncClient, leads: list[int]) -> None:
    response = await client.get(f"/api/leads/{leads[0]}")
    assert response.status_code == 200
    lead = response.json()
    assert lead["name"] == "Alpha Gym"
    assert lead["google_maps_url"] == "https://maps.google.com/?cid=1"
    assert lead["contacts"][0]["normalized_phone"] == "+359880011234"
    assert lead["data_quality_checklist"]["website"] is False
    assert "doesn't include a website" in lead["pitches"]["en"]["text"]
    assert lead["pitches"]["bg"]["language"] == "bg"
    assert any(r["opportunity"] == "NO_WEBSITE" for r in lead["score_reasons"])
    assert (await client.get("/api/leads/99999")).status_code == 404


async def test_call_outcomes_update_status(client: httpx.AsyncClient, leads: list[int]) -> None:
    lead_id = leads[0]
    r = await client.post(f"/api/leads/{lead_id}/call", json={"outcome": "NO_ANSWER"})
    assert r.status_code == 200 and r.json()["status"] == "NO_ANSWER"
    r = await client.post(
        f"/api/leads/{lead_id}/call", json={"outcome": "CALLBACK", "note": "Call after 19h"}
    )
    body = r.json()
    assert body["status"] == "CALLBACK" and body["next_callback_at"]
    r = await client.post(f"/api/leads/{lead_id}/call", json={"outcome": "INTERESTED"})
    assert r.json()["status"] == "INTERESTED"
    detail = (await client.get(f"/api/leads/{lead_id}")).json()
    assert detail["call_count"] == 3
    assert detail["phone_verified"] is True
    assert detail["notes"][0]["body"] == "Call after 19h"
    assert [c["outcome"] for c in detail["calls"]] == ["INTERESTED", "CALLBACK", "NO_ANSWER"]


async def test_wrong_number_removes_lead_from_calling(client: httpx.AsyncClient, leads: list[int]) -> None:
    await client.post(f"/api/leads/{leads[0]}/call", json={"outcome": "WRONG_NUMBER"})
    detail = (await client.get(f"/api/leads/{leads[0]}")).json()
    assert detail["phone_invalid"] is True
    preview = (await client.post("/api/calling-sessions/preview", json={"priorities": []})).json()
    assert leads[0] not in [lead["id"] for lead in preview["sample"]]


async def test_do_not_contact_is_permanent_until_explicitly_reenabled(
    client: httpx.AsyncClient, leads: list[int], sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    lead_id = leads[0]
    r = await client.post(f"/api/leads/{lead_id}/call", json={"outcome": "DO_NOT_CONTACT", "note": "Asked"})
    assert r.json()["status"] == "DO_NOT_CONTACT" and r.json()["suppressed"] is True

    # Never surfaced by calling sessions, recording further calls is refused.
    preview = (
        await client.post("/api/calling-sessions/preview", json={"priorities": [], "statuses": []})
    ).json()
    assert lead_id not in [lead["id"] for lead in preview["sample"]]
    refused = await client.post(f"/api/leads/{lead_id}/call", json={"outcome": "INTERESTED"})
    assert refused.status_code == 409 and refused.json()["detail"]["code"] == "do_not_contact"

    # A new listing with the same number is suppressed on discovery.
    async with sessionmaker() as session:
        dup = await upsert_business(
            session,
            record_from_place(make_place(50, name="Other Name Co", international_phone="+359880011234")),
        )
        await session.commit()
        assert dup.business.suppressed

    # Re-enabling requires explicit confirmation.
    blocked = await client.patch(f"/api/leads/{lead_id}", json={"status": "NEW"})
    assert blocked.status_code == 409
    assert blocked.json()["detail"]["code"] == "reenable_confirmation_required"
    ok = await client.patch(f"/api/leads/{lead_id}", json={"status": "CALLED", "confirm_reenable": True})
    assert ok.status_code == 200 and ok.json()["suppressed"] is False
    async with sessionmaker() as session:
        entries = (await session.execute(select(SuppressionEntry))).scalars().all()
        assert entries and not any(e.active for e in entries)  # kept for audit, deactivated


async def test_suppression_list_blocks_calling_even_if_flag_is_stale(
    client: httpx.AsyncClient, leads: list[int], sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    async with sessionmaker() as session:
        session.add(SuppressionEntry(normalized_phone="+359880011234", reason="direct insert", active=True))
        await session.commit()
    preview = (await client.post("/api/calling-sessions/preview", json={"priorities": []})).json()
    assert leads[0] not in [lead["id"] for lead in preview["sample"]]


async def test_calling_session_flow(client: httpx.AsyncClient, leads: list[int]) -> None:
    r = await client.post("/api/calling-sessions", json={"priorities": ["HOT", "WARM"], "limit": 10})
    assert r.status_code == 201, r.text
    session = r.json()
    assert session["lead_ids"]
    card = session["cards"][0]
    assert card["lead"]["normalized_phone"]
    assert card["reasons"] and card["pitch"]["text"]
    assert card["callable"] is True
    lead_id = card["lead"]["id"]
    await client.post(
        f"/api/leads/{lead_id}/call", json={"outcome": "NOT_INTERESTED", "session_id": session["id"]}
    )
    updated = (await client.get(f"/api/calling-sessions/{session['id']}")).json()
    assert updated["stats"]["NOT_INTERESTED"] == 1
    assert (await client.patch(f"/api/calling-sessions/{session['id']}", json={"position": 1})).json()[
        "position"
    ] == 1
    ended = (await client.post(f"/api/calling-sessions/{session['id']}/end")).json()
    assert ended["ended_at"]
    # Recently called leads respect the cooldown
    preview = (await client.post("/api/calling-sessions/preview", json={"priorities": []})).json()
    assert lead_id not in [lead["id"] for lead in preview["sample"]]


async def test_empty_calling_session_is_rejected(client: httpx.AsyncClient) -> None:
    r = await client.post("/api/calling-sessions", json={"priorities": ["HOT"]})
    assert r.status_code == 422 and r.json()["detail"]["code"] == "empty_queue"


async def test_csv_export(client: httpx.AsyncClient, leads: list[int]) -> None:
    await client.post(f"/api/leads/{leads[1]}/notes", json={"body": "=cmd|' /C calc'!A0 dangerous note"})
    response = await client.get("/api/export", params={"has_phone": "true", "sort": "name", "order": "asc"})
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert "attachment" in response.headers["content-disposition"]
    raw = response.content
    assert raw.startswith(b"\xef\xbb\xbf")  # BOM so Excel shows Cyrillic correctly
    rows = list(csv.reader(io.StringIO(raw.decode("utf-8-sig"))))
    assert rows[0][:3] == ["Business", "Category", "Phone"]
    assert len(rows) == 1 + 3  # header + leads with phones
    names = [r[0] for r in rows[1:]]
    assert "Бета Фитнес" in names
    beta = next(r for r in rows[1:] if r[0] == "Бета Фитнес")
    assert beta[3] == "+359 88 002 1234"  # phone left intact
    assert beta[15].startswith("'=")  # formula neutralized
    assert "No website" in beta[12]


async def test_csv_import_preview_and_commit(client: httpx.AsyncClient, leads: list[int]) -> None:
    content = (
        "Име;Телефон;Уебсайт;Адрес;Град;Бележки\n"
        "Alpha Gym;0880011234;;ul. Test 1;Sofia;already known\n"
        "Нов Салон;0899 555 111;novsalon.bg;ул. Шипка 3;София;warm intro\n"
        ";0899555222;;;;\n"
        "Нов Салон;0899 555 111;;;;duplicate row\n"
    ).encode("cp1251")
    preview = await client.post("/api/import/preview", files={"file": ("leads.csv", content, "text/csv")})
    assert preview.status_code == 200, preview.text
    data = preview.json()
    assert data["mapping"]["name"] == "Име" and data["mapping"]["phone"] == "Телефон"
    assert data["mapping"]["website"] == "Уебсайт" and data["mapping"]["notes"] == "Бележки"
    assert data["counts"] == {"new": 1, "duplicate": 2, "invalid": 1}
    statuses = [r["status"] for r in data["rows"]]
    assert statuses == ["duplicate", "new", "invalid", "duplicate"]
    assert data["rows"][0]["duplicate_of"] == leads[0]

    commit = await client.post("/api/import", json={"batch_id": data["batch_id"], "audit_websites": True})
    assert commit.status_code == 200, commit.text
    result = commit.json()
    assert result["created"] == 1 and result["skipped_duplicates"] == 2 and result["invalid"] == 1
    assert result["audit_job_id"] is not None
    found = (await client.get("/api/leads", params={"q": "Нов Салон"})).json()["items"]
    assert len(found) == 1 and found[0]["normalized_phone"] == "+359899555111"
    again = await client.post("/api/import", json={"batch_id": data["batch_id"]})
    assert again.status_code == 404  # a batch can only be committed once


async def test_settings_roundtrip_and_validation(client: httpx.AsyncClient) -> None:
    current = (await client.get("/api/settings")).json()
    assert current["runtime"]["calling"]["window_start"] == "19:00"
    assert current["environment"]["provider_api_key_set"] is False
    r = await client.patch(
        "/api/settings",
        json={"calling": {"window_start": "18:30"}, "scoring": {"rules": {"no_website": {"points": 40}}}},
    )
    assert r.status_code == 200
    runtime = r.json()["runtime"]
    assert runtime["calling"]["window_start"] == "18:30"
    assert runtime["scoring"]["rules"]["no_website"]["points"] == 40
    assert runtime["scoring"]["rules"]["phone_available"]["points"] == 5
    bad = await client.patch("/api/settings", json={"calling": {"window_start": "25:99"}})
    assert bad.status_code == 422
    secret = await client.patch("/api/settings", json={"general": {"provider_api_key": "x"}})
    assert secret.status_code == 422
    job = await client.post("/api/settings/rescore")
    assert job.status_code == 202


async def test_search_requires_provider(client: httpx.AsyncClient) -> None:
    r = await client.post("/api/search", json={"category": "gyms", "location": "Sofia"})
    assert r.status_code == 503
    assert r.json()["detail"]["code"] == "provider_not_configured"
    estimate = (
        await client.post("/api/search/estimate", json={"category": "gyms", "location": "Sofia"})
    ).json()
    assert estimate["provider_configured"] is False


async def test_search_job_creation_and_cancel(
    client: httpx.AsyncClient, fake_provider: Callable[..., FakeProvider], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(get_settings(), "provider_api_key", SecretStr("test-key"))
    fake_provider()
    body = {
        "category": "gyms",
        "location": "Sofia",
        "neighborhoods": ["Lozenets", "Mladost"],
        "max_results": 100,
    }
    estimate = (await client.post("/api/search/estimate", json=body)).json()
    assert estimate["queries"] == 2 and estimate["max_requests"] >= 2
    assert estimate["sku"] == "text_search_enterprise"
    created = await client.post("/api/search", json=body)
    assert created.status_code == 202
    job = created.json()
    assert job["status"] == "queued"
    cancelled = (await client.post(f"/api/search-jobs/{job['id']}/cancel")).json()
    assert cancelled["status"] == "cancelled"
    retried = await client.post(f"/api/search-jobs/{job['id']}/retry")
    assert retried.status_code == 202 and retried.json()["retry_of_id"] == job["id"]
    listed = (await client.get("/api/search-jobs")).json()
    assert listed["total"] == 2
    invalid = await client.post("/api/search", json={"category": "g", "location": "Sofia"})
    assert invalid.status_code == 422


async def test_presets_crud(client: httpx.AsyncClient) -> None:
    presets = (await client.get("/api/presets")).json()
    assert {p["key"] for p in presets} >= {"gyms", "beauty", "barbers", "restaurants", "dentists"}
    created = await client.post(
        "/api/presets",
        json={
            "key": "florists",
            "label": "Florists",
            "category_query": "florists",
            "match_types": ["florist"],
            "calling_window_start": "10:00",
            "calling_window_end": "12:00",
            "booking_oriented": False,
        },
    )
    assert created.status_code == 201
    preset_id = created.json()["id"]
    updated = await client.patch(f"/api/presets/{preset_id}", json={"label": "Flower shops"})
    assert updated.json()["label"] == "Flower shops"
    assert (await client.post("/api/presets", json={**created.json(), "key": "florists"})).status_code == 409
    assert (await client.delete(f"/api/presets/{preset_id}")).status_code == 200


async def test_dashboard(client: httpx.AsyncClient, leads: list[int]) -> None:
    await client.post(f"/api/leads/{leads[0]}/call", json={"outcome": "INTERESTED"})
    data = (await client.get("/api/dashboard")).json()
    kpis = data["kpis"]
    assert kpis["total_leads"] == 4
    assert kpis["phones_found"] == 3
    assert kpis["calls_today"] == 1
    assert kpis["interested"] == 1
    assert kpis["no_website"] == 3
    assert any(o["key"] == "NO_WEBSITE" for o in data["by_opportunity"])
    assert data["calls_by_outcome"] == [{"key": "INTERESTED", "count": 1}]
    assert "cost" in data["month"]


async def test_bulk_update_skips_suppressed(client: httpx.AsyncClient, leads: list[int]) -> None:
    await client.post(f"/api/leads/{leads[0]}/call", json={"outcome": "DO_NOT_CONTACT"})
    r = await client.post("/api/leads/bulk", json={"ids": leads, "status": "QUALIFIED"})
    assert r.json() == {"updated": 3, "skipped": 1}


async def test_manual_phone_and_website(client: httpx.AsyncClient, leads: list[int]) -> None:
    lead_id = leads[2]  # Gamma: no phone
    bad = await client.patch(f"/api/leads/{lead_id}", json={"add_phone": "123"})
    assert bad.status_code == 422
    ok = await client.patch(
        f"/api/leads/{lead_id}", json={"add_phone": "0888 777 666", "website_url": "gamma.bg"}
    )
    data = ok.json()
    assert data["normalized_phone"] == "+359888777666"
    assert data["website_status"] == "unaudited"
    assert data["active_job_id"] is not None  # audit queued


async def test_token_auth_mode(
    client: httpx.AsyncClient, sessionmaker: async_sessionmaker[AsyncSession], monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.core.security import generate_token, hash_token
    from app.models import User

    token = generate_token()
    async with sessionmaker() as session:
        session.add(User(email="sales@example.com", name="Sales", role="sales", token_hash=hash_token(token)))
        await session.commit()
    settings = get_settings()
    monkeypatch.setattr(settings, "auth_mode", "token")
    monkeypatch.setattr(settings, "secret_key", SecretStr("a-strong-test-secret-value"))

    assert (await client.get("/api/leads")).status_code == 401
    assert (await client.post("/api/auth/login", json={"token": "lt_wrong-token-value"})).status_code == 401
    login = await client.post("/api/auth/login", json={"token": token})
    assert login.status_code == 200
    assert "httponly" in login.headers["set-cookie"].lower()
    me = await client.get("/api/auth/me")
    assert me.json()["user"]["email"] == "sales@example.com"
    bearer = await client.get("/api/leads", headers={"Authorization": f"Bearer {token}"}, cookies={})
    assert bearer.status_code == 200
    client.cookies.clear()
    assert (await client.get("/api/leads")).status_code == 401


async def test_security_headers(client: httpx.AsyncClient) -> None:
    r = await client.get("/api/health")
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["x-frame-options"] == "DENY"


async def test_rescore_after_settings_change(
    client: httpx.AsyncClient, leads: list[int], sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    await client.patch(
        "/api/settings", json={"scoring": {"rules": {"no_website": {"points": 0, "enabled": False}}}}
    )
    r = await client.post(f"/api/leads/{leads[0]}/rescore")
    assert r.status_code == 200
    assert "NO_WEBSITE" not in r.json()["opportunity_types"]
    async with sessionmaker() as session:
        business = await session.get(Business, leads[0])
        assert business is not None and "NO_WEBSITE" not in business.opportunity_types


async def test_cross_origin_writes_are_blocked(client: httpx.AsyncClient, leads: list[int]) -> None:
    evil = await client.post(
        f"/api/leads/{leads[0]}/notes", json={"body": "x"}, headers={"Origin": "https://evil.example"}
    )
    assert evil.status_code == 403
    assert evil.json()["detail"]["code"] == "origin_not_allowed"
    same = await client.post(
        f"/api/leads/{leads[0]}/notes", json={"body": "x"}, headers={"Origin": "http://test"}
    )
    assert same.status_code == 201
    allowed = await client.post(
        f"/api/leads/{leads[0]}/notes", json={"body": "x"}, headers={"Origin": "http://localhost:5173"}
    )
    assert allowed.status_code == 201
    reads = await client.get("/api/leads", headers={"Origin": "https://evil.example"})
    assert reads.status_code == 200  # CORS governs reads; no state change


def test_logs_redact_secrets() -> None:
    from app.log import redact_processor, register_secret

    register_secret("AIzaSyTEST-secret-key-123")
    event = redact_processor(
        None,
        "info",
        {
            "event": "provider_error",
            "url": "https://example.com/?key=AIzaSyTEST-secret-key-123&x=1",
            "headers": {"X-Goog-Api-Key": "AIzaSyTEST-secret-key-123", "accept": "json"},
            "api_key": "anything",
            "message": "failed with AIzaSyTEST-secret-key-123",
        },
    )
    text = str(event)
    assert "AIzaSyTEST-secret-key-123" not in text
    assert event["api_key"] == "[REDACTED]"
    assert event["headers"]["accept"] == "json"


async def test_bulk_assign_validates_user(client: httpx.AsyncClient, leads: list[int]) -> None:
    r = await client.post("/api/leads/bulk", json={"ids": leads, "assigned_to_id": 9999})
    assert r.status_code == 422 and r.json()["detail"]["code"] == "unknown_user"
