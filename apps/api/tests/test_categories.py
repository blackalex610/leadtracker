"""Lead categories (what to sell, price, odds), chain detection and query planning."""

from __future__ import annotations

from typing import Any

from app.core.chains import chain_brand
from app.core.enums import LeadCategory as C
from app.data.targets import TARGETS, TARGETS_BY_KEY, target_for
from app.scoring.category import CATEGORY_INFO, DEFAULT_OFFERS, SELLABLE, OfferConfig, categorize
from app.scoring.config import ScoringConfig
from app.scoring.engine import calculate_opportunity_score
from app.scoring.inputs import AuditSnapshot, ScoringInput
from app.scoring.pitch import build_pitch
from app.services.search import SearchRequest, candidate_queries

PLUMBERS = TARGETS_BY_KEY["plumbers"]  # value tier 3 -> premium price
BARBERS = TARGETS_BY_KEY["barbers"]  # value tier 1, booking


def make(**overrides: Any) -> ScoringInput:
    base: dict[str, Any] = {
        "name": "Майстор Иван",
        "category": "Plumber",
        "primary_type": "plumber",
        "types": ["plumber"],
        "city": "Sofia",
        "target": PLUMBERS,
        "has_phone": True,
        "phone_type": "mobile",
        "website_url": None,
        "rating": 4.7,
        "review_count": 45,
        "address": "ul. Test 1",
        "business_status": "OPERATIONAL",
        "photo_count": 8,
        "opening_hours": {"periods": [{"open": {"day": 1, "hour": 8, "minute": 0}}]},
    }
    base.update(overrides)
    return ScoringInput(**base)


def cat(inp: ScoringInput, chain: str | None = None):  # type: ignore[no-untyped-def]
    result = calculate_opportunity_score(inp, ScoringConfig())
    return categorize(inp, result, OfferConfig(), inp.target, chain), result


def ok_audit(codes: list[str] | None = None, health: int = 85, **facts: Any) -> AuditSnapshot:
    signals = [{"code": c, "penalty": 5, "label": c.replace("_", " ")} for c in (codes or [])]
    return AuditSnapshot(
        status="success", health_score=health, outdated_score=10, signals=signals, facts=facts
    )


def test_no_website_established_business() -> None:
    offer, _ = cat(make())
    assert offer.category == C.NO_SITE
    assert offer.deal_value == DEFAULT_OFFERS[C.NO_SITE].premium_price  # plumbers are tier 3
    # base odds + established (30+ reviews) + 4.5★ + mobile number
    assert offer.close_odds == DEFAULT_OFFERS[C.NO_SITE].odds + 4 + 2 + 4
    assert offer.expected_value == round(offer.deal_value * offer.close_odds / 100)


def test_few_reviews_and_no_site_is_a_new_business() -> None:
    offer, _ = cat(make(review_count=3))
    assert offer.category == C.NEW_BUSINESS


def test_social_and_platform_pages_are_not_websites() -> None:
    social, _ = cat(make(website_url="https://facebook.com/x", website_kind="social"))
    platform, _ = cat(
        make(website_url="https://fresha.com/x", website_kind="booking_platform", target=BARBERS)
    )
    assert social.category == C.SOCIAL_ONLY
    assert platform.category == C.PLATFORM_ONLY
    assert platform.deal_value == DEFAULT_OFFERS[C.PLATFORM_ONLY].price  # barbers: standard price


def test_broken_site_beats_everything() -> None:
    offer, _ = cat(
        make(
            website_url="https://x.bg",
            website_kind="own",
            website_status="broken",
            audit=AuditSnapshot(status="failed", error_code="dns", error_message="DNS lookup failed"),
        )
    )
    assert offer.category == C.BROKEN_SITE
    assert "DNS" in offer.reason


def test_site_categories_after_audit() -> None:
    site = {"website_url": "https://x.bg", "website_kind": "own", "website_status": "ok"}
    weak, _ = cat(make(**site, audit=ok_audit(["no_viewport"], health=30)))
    booking, _ = cat(make(**site, target=BARBERS, audit=ok_audit(["no_booking"])))
    google, _ = cat(make(**site, review_count=4, audit=ok_audit()))
    fine, _ = cat(make(**site, audit=ok_audit()))
    unchecked, _ = cat(make(**{**site, "website_status": "unaudited"}))
    assert weak.category == C.WEAK_SITE
    assert booking.category == C.NO_BOOKING
    assert google.category == C.WEAK_GOOGLE
    assert fine.category == C.NOT_A_FIT and fine.expected_value == 0
    assert unchecked.category == C.UNCHECKED


def test_not_a_fit_blockers() -> None:
    chain, _ = cat(make(), chain="vianor")
    closed, _ = cat(make(business_status="CLOSED_PERMANENTLY"))
    badly_rated, _ = cat(make(rating=2.9, review_count=40))
    for offer in (chain, closed, badly_rated):
        assert offer.category == C.NOT_A_FIT
        assert offer.deal_value == 0
    assert "chain" in chain.reason


def test_landline_and_few_reviews_lower_the_odds() -> None:
    mobile, _ = cat(make(review_count=40))
    landline, _ = cat(make(review_count=40, phone_type="fixed_line"))
    assert landline.close_odds == mobile.close_odds - 6


def test_offer_prices_are_configurable() -> None:
    config = OfferConfig()
    config.offers[C.NO_SITE].premium_price = 450
    inp = make()
    result = calculate_opportunity_score(inp, ScoringConfig())
    assert categorize(inp, result, config, inp.target).deal_value == 450
    # Partial settings keep defaults for the other categories.
    assert (
        OfferConfig.model_validate(
            {"offers": {"NO_SITE": {"price": 1, "premium_price": 2, "odds": 3}}}
        ).offer(C.BROKEN_SITE)
        == DEFAULT_OFFERS[C.BROKEN_SITE]
    )


def test_pitch_names_the_offer_price_and_a_free_preview() -> None:
    inp = make()
    offer, result = cat(inp)
    en = build_pitch(inp, result, "en", offer)
    bg = build_pitch(inp, result, "bg", offer)
    assert f"€{offer.deal_value}" in en.text and "free" in en.text
    assert f"{offer.deal_value} €" in bg.text and "безплатна" in bg.text
    assert "ВиК услуги" in bg.text  # target label in the opener
    assert en.offer == CATEGORY_INFO[C.NO_SITE].offer and en.price == offer.deal_value


def test_every_category_has_copy() -> None:
    for category in C:
        info = CATEGORY_INFO[category]
        assert info.label and info.label_bg and info.description
        if category in SELLABLE:
            assert info.offer_line and info.offer_line_bg and info.ask and info.ask_bg


def test_chain_detection_is_whole_word_and_avoids_common_names() -> None:
    assert chain_brand("Vianor Люлин") == "Vianor"
    assert chain_brand("Билла / BILLA Младост") == "BILLA"
    assert chain_brand("Сервиз Шелл") is None
    assert chain_brand("Happy Nails studio") is None  # 'Happy' alone is not a brand
    assert chain_brand("Лили Козметик") is None


def test_targets_are_unique_and_resolvable() -> None:
    assert len({t.key for t in TARGETS}) == len(TARGETS)
    assert len({t.query for t in TARGETS}) == len(TARGETS)
    assert target_for("plumbers", None, None) is PLUMBERS
    assert target_for(None, "barber_shop", None) is BARBERS
    assert target_for(None, None, ["establishment"]) is None


def test_query_plan_city_first_then_neighborhoods() -> None:
    plan = candidate_queries(SearchRequest(location="sofia"))
    assert plan[0].text == f"{TARGETS[0].query} в Sofia"
    assert {q.location for q in plan[: len(TARGETS)]} == {"Sofia"}
    assert plan[len(TARGETS)].location.endswith(", Sofia")
    assert len(candidate_queries(SearchRequest(location="Sofia", use_neighborhoods=False))) == len(TARGETS)
    # Unknown places still work as free text.
    assert candidate_queries(SearchRequest(location="Банско"))[0].location == "Банско"
