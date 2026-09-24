from __future__ import annotations

from typing import Any

import pytest

from app.core.enums import OpportunityType as O
from app.core.enums import Priority
from app.scoring.config import RuleKey, ScoringConfig, ScoringRule
from app.scoring.data_quality import data_quality
from app.scoring.engine import calculate_opportunity_score
from app.scoring.google_profile import analyze_google_profile
from app.scoring.inputs import AuditSnapshot, NicheInfo, ScoringInput
from app.scoring.pitch import build_pitch

NAILS = NicheInfo(
    key="nail_salons",
    label="Nail salons",
    label_bg="маникюрни салони",
    booking_oriented=True,
    match_types=["nail_salon"],
)
CAFES = NicheInfo(key="cafes", label="Cafes", booking_oriented=False, match_types=["cafe"])
HOURS = {
    "periods": [
        {"open": {"day": d, "hour": 9, "minute": 0}, "close": {"day": d, "hour": 21, "minute": 0}}
        for d in range(1, 6)
    ]
}


def make_input(**overrides: Any) -> ScoringInput:
    base: dict[str, Any] = {
        "name": "Bella Nails",
        "category": "Nail salon",
        "primary_type": "nail_salon",
        "types": ["nail_salon"],
        "city": "Sofia",
        "niche": NAILS,
        "has_phone": True,
        "website_url": None,
        "rating": 4.8,
        "review_count": 217,
        "opening_hours": HOURS,
        "address": "ul. Vitosha 1",
        "business_status": "OPERATIONAL",
        "photo_count": 10,
        "open_in_calling_window": True,
    }
    base.update(overrides)
    return ScoringInput(**base)


def audit(
    health: int = 80, outdated: int = 10, codes: list[str] | None = None, **facts: Any
) -> AuditSnapshot:
    signals = [{"code": c, "penalty": 5, "label": c.replace("_", " ")} for c in (codes or [])]
    return AuditSnapshot(
        status="success",
        health_score=health,
        outdated_score=outdated,
        outdated_band="x",
        response_time_ms=900,
        signals=signals,
        facts={"booking_detected": False, **facts},
    )


def test_spec_example_no_website_nail_salon_is_hot() -> None:
    result = calculate_opportunity_score(make_input(), ScoringConfig())
    assert result.priority == Priority.HOT
    assert result.opportunities[:2] == [O.NO_WEBSITE, O.NO_BOOKING]
    assert result.score == 35 + 15 + 5 + 5 + 5
    texts = [r.text for r in result.reasons]
    assert "No website listed" in texts
    assert result.priority_reason.startswith("HOT:")


def test_score_is_capped_at_100() -> None:
    inp = make_input(
        website_url="http://old.bg",
        website_kind="own",
        website_status="ok",
        audit=audit(
            health=10,
            outdated=90,
            codes=["no_viewport", "no_contact_cta", "no_phone", "no_hours", "no_contact_form", "very_slow"],
        ),
        review_count=3,
        photo_count=0,
        opening_hours=None,
    )
    result = calculate_opportunity_score(inp, ScoringConfig())
    assert result.score == 100


def test_social_page_counts_as_no_website() -> None:
    inp = make_input(website_url="https://facebook.com/bella", website_kind="social")
    result = calculate_opportunity_score(inp, ScoringConfig())
    assert O.NO_WEBSITE in result.opportunities
    assert "social media page" in result.reasons[0].text


def test_booking_platform_link_is_no_own_website_but_has_booking() -> None:
    inp = make_input(website_url="https://booksy.com/x", website_kind="booking_platform")
    result = calculate_opportunity_score(inp, ScoringConfig())
    assert O.NO_WEBSITE in result.opportunities
    assert O.NO_BOOKING not in result.opportunities


def test_unreachable_website_is_broken() -> None:
    snap = AuditSnapshot(status="failed", error_code="dns_failure", error_message="Domain does not resolve")
    inp = make_input(website_url="http://gone.bg", website_kind="own", website_status="broken", audit=snap)
    result = calculate_opportunity_score(inp, ScoringConfig())
    assert result.opportunities[0] == O.BROKEN_WEBSITE
    assert "Domain does not resolve" in result.reasons[0].text
    assert result.priority == Priority.HOT


def test_parked_domain_is_broken() -> None:
    inp = make_input(
        website_url="http://p.bg",
        website_kind="own",
        website_status="broken",
        audit=audit(health=5, codes=["parked_domain"]),
    )
    result = calculate_opportunity_score(inp, ScoringConfig())
    assert O.BROKEN_WEBSITE in result.opportunities
    assert O.WEBSITE_REDESIGN not in result.opportunities


def test_healthy_site_with_booking_is_not_hot() -> None:
    inp = make_input(
        website_url="https://bella.bg",
        website_kind="own",
        website_status="ok",
        audit=audit(health=92, outdated=0, booking_detected=True),
    )
    result = calculate_opportunity_score(inp, ScoringConfig())
    assert result.opportunities == []
    assert result.priority != Priority.HOT


def test_no_booking_only_for_booking_oriented_categories() -> None:
    site = {
        "website_url": "https://cafe.bg",
        "website_kind": "own",
        "website_status": "ok",
        "audit": audit(health=85, codes=["no_booking"]),
    }
    cafe = calculate_opportunity_score(make_input(niche=CAFES, primary_type="cafe", **site), ScoringConfig())
    nails = calculate_opportunity_score(make_input(**site), ScoringConfig())
    assert O.NO_BOOKING not in cafe.opportunities
    assert O.NO_BOOKING in nails.opportunities
    assert "No online booking mechanism detected" in next(r.text for r in nails.reasons)


def test_low_health_and_mobile_and_outdated() -> None:
    inp = make_input(
        website_url="http://x.bg",
        website_kind="own",
        website_status="ok",
        audit=audit(health=30, outdated=70, codes=["no_viewport"]),
    )
    result = calculate_opportunity_score(inp, ScoringConfig())
    assert {O.WEBSITE_REDESIGN, O.MOBILE_PROBLEM, O.OUTDATED_WEBSITE} <= set(result.opportunities)


def test_unaudited_website_is_noted_not_scored() -> None:
    inp = make_input(website_url="https://x.bg", website_kind="own", website_status="unaudited", audit=None)
    result = calculate_opportunity_score(inp, ScoringConfig())
    assert "Website not audited yet" in result.notes
    assert O.WEBSITE_REDESIGN not in result.opportunities


def test_no_phone_is_never_hot_or_warm() -> None:
    result = calculate_opportunity_score(make_input(has_phone=False), ScoringConfig())
    assert result.priority == Priority.COLD
    assert result.priority_reason == "COLD: no phone number"


def test_closed_business_is_cold() -> None:
    result = calculate_opportunity_score(make_input(business_status="CLOSED_PERMANENTLY"), ScoringConfig())
    assert result.priority == Priority.COLD


def test_weak_category_caps_at_warm() -> None:
    weak = NicheInfo(key="x", label="Warehouses", booking_oriented=False, discovery_dependent=False)
    result = calculate_opportunity_score(make_input(niche=weak), ScoringConfig())
    assert result.priority == Priority.WARM
    assert "category not discovery-dependent" in result.priority_reason


def test_rules_are_configurable() -> None:
    cfg = ScoringConfig()
    cfg.rules[RuleKey.NO_WEBSITE] = ScoringRule(points=50)
    cfg.rules[RuleKey.PHONE_AVAILABLE] = ScoringRule(points=5, enabled=False)
    result = calculate_opportunity_score(make_input(), cfg)
    assert result.score == 50 + 15 + 5 + 5
    assert "Phone number available" not in [r.text for r in result.reasons]


def test_missing_rules_are_filled_with_defaults() -> None:
    cfg = ScoringConfig.model_validate({"rules": {"no_website": {"points": 40}}})
    assert cfg.points(RuleKey.NO_WEBSITE) == 40
    assert cfg.points(RuleKey.PHONE_AVAILABLE) == 5


def test_reasons_are_observations_not_assumptions() -> None:
    inp = make_input(
        website_url="http://x.bg",
        website_kind="own",
        website_status="ok",
        audit=audit(health=20, codes=["no_booking", "no_contact_cta", "no_viewport"]),
    )
    result = calculate_opportunity_score(inp, ScoringConfig())
    for reason in result.reasons:
        lowered = reason.text.lower()
        assert "cannot" not in lowered and "needs" not in lowered and "customers" not in lowered


def test_google_profile_low_reviews_is_an_opportunity_not_a_verdict() -> None:
    analysis = analyze_google_profile(
        make_input(review_count=4, photo_count=1, opening_hours=None), ScoringConfig()
    )
    codes = analysis.codes
    assert {"low_review_volume", "few_photos", "missing_hours"} <= codes
    label = next(s["label"] for s in analysis.signals if s["code"] == "low_review_volume")
    assert "visibility opportunity" in label
    assert analysis.score is not None and analysis.score < 100


def test_description_only_flagged_when_requested() -> None:
    not_requested = analyze_google_profile(make_input(description=None), ScoringConfig())
    requested = analyze_google_profile(
        make_input(description=None, description_requested=True), ScoringConfig()
    )
    assert "missing_description" not in not_requested.codes
    assert "missing_description" in requested.codes


def test_category_mismatch() -> None:
    analysis = analyze_google_profile(
        make_input(primary_type="store", types=["store"], category="Store"), ScoringConfig()
    )
    assert "category_mismatch" in analysis.codes


@pytest.mark.parametrize(
    ("fields", "grade"),
    [
        (
            {"has_phone": True, "website_url": "x", "address": "a", "rating": 4.0, "opening_hours": HOURS},
            "EXCELLENT",
        ),
        (
            {"has_phone": True, "website_url": None, "address": "a", "rating": 4.0, "opening_hours": HOURS},
            "GOOD",
        ),
        (
            {"has_phone": True, "website_url": None, "address": "a", "rating": None, "opening_hours": None},
            "PARTIAL",
        ),
        (
            {"has_phone": False, "website_url": None, "address": None, "rating": None, "opening_hours": None},
            "POOR",
        ),
    ],
)
def test_data_quality(fields: dict[str, Any], grade: str) -> None:
    result, checklist = data_quality(**fields)
    assert result.value == grade
    assert set(checklist) == {"phone", "website", "address", "rating", "hours"}


def test_pitch_mentions_only_verified_signals() -> None:
    inp = make_input()
    result = calculate_opportunity_score(inp, ScoringConfig())
    pitch = build_pitch(inp, result, "en")
    assert "doesn't include a website" in pitch.text
    assert "217 Google reviews" in pitch.text
    assert "nail salons in Sofia" in pitch.text
    assert pitch.primary_opportunity == "NO_WEBSITE"


def test_pitch_skips_review_line_for_few_reviews_and_supports_bulgarian() -> None:
    inp = make_input(review_count=12)
    result = calculate_opportunity_score(inp, ScoringConfig())
    en = build_pitch(inp, result, "en")
    bg = build_pitch(inp, result, "bg")
    assert "reviews" not in en.text.split(".")[1]
    assert "София" in bg.text and "уебсайт" in bg.text


def test_pitch_for_booking_opportunity() -> None:
    inp = make_input(
        website_url="https://bella.bg",
        website_kind="own",
        website_status="ok",
        audit=audit(health=75, codes=["no_booking"]),
    )
    result = calculate_opportunity_score(inp, ScoringConfig())
    pitch = build_pitch(inp, result, "en")
    assert pitch.primary_opportunity == "NO_BOOKING"
    assert "online booking option" in pitch.text
