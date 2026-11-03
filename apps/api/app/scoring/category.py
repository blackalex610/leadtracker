"""Lead categories: what to sell each lead, for how much, and how likely it is to close.

Every scraped business lands in exactly one category, chosen from what was
observed (website kind, audit result, Google listing). The category decides the
offer the caller pitches, its price, and the business's place in the calling
queue: leads are called in order of **expected value** = price x close odds,
so the hour spent dialing goes to the deals most likely to pay.

Prices are EUR, set for Bulgarian small businesses (a one-page business site
there typically costs €150-1,200; ongoing care €50-200/month) and pitched low
enough to say yes to on the first or second call. Close odds are relative
planning weights, not promises; tune both in Settings → Offers once real call
results come in.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.enums import LeadCategory, OpportunityType
from app.data.targets import Target
from app.scoring.engine import ScoreResult
from app.scoring.inputs import ScoringInput

WEBSITE_PROBLEMS = {
    OpportunityType.WEBSITE_REDESIGN,
    OpportunityType.OUTDATED_WEBSITE,
    OpportunityType.MOBILE_PROBLEM,
    OpportunityType.NO_CONTACT_CTA,
    OpportunityType.WEAK_CONVERSION,
    OpportunityType.SLOW_WEBSITE,
}
GOOGLE_GAPS = {
    OpportunityType.GOOGLE_PROFILE,
    OpportunityType.LOW_REVIEWS,
    OpportunityType.MISSING_BUSINESS_INFO,
}
NEW_BUSINESS_MAX_REVIEWS = 10
MIN_GOOD_RATING = 3.5


@dataclass(frozen=True, slots=True)
class CategoryInfo:
    label: str
    label_bg: str
    offer: str
    offer_bg: str
    description: str
    # What the caller says the offer is, in one breath.
    offer_line: str
    offer_line_bg: str
    # Low-friction next step to ask for at the end of the call.
    ask: str
    ask_bg: str


CATEGORY_INFO: dict[LeadCategory, CategoryInfo] = {
    LeadCategory.BROKEN_SITE: CategoryInfo(
        "Broken website", "Счупен сайт", "Website rescue", "Спасяване на сайта",
        "The website on the listing does not load, shows a parked domain or an 'under construction' page. "
        "Customers who click it from Google hit a dead end - urgent, easy to show, highest close rate.",
        "We rebuild it as a fast, mobile site on your domain and have it live within a week",
        "Правим го наново - бърз сайт, удобен за телефон, на вашия домейн, готов до седмица",
        "Can I send you a free preview of the fixed site tomorrow?",
        "Да ви пратя ли утре безплатна чернова на оправения сайт?",
    ),
    LeadCategory.NO_SITE: CategoryInfo(
        "No website", "Няма сайт", "Starter website", "Сайт визитка",
        "Established on Google (reviews, phone) but no website at all. The biggest pool of buyers: customers "
        "who search for them can't see services, prices or photos and call a competitor instead.",
        "A one-page site with your services, photos, a call button and map, live in 5 days",
        "Сайт с услугите, снимки, бутон за обаждане и карта - готов за 5 дни",
        "Can I put together a free draft of your site and send it to you tomorrow, no obligation?",
        "Мога ли да ви подготвя безплатна чернова на сайта и да ви я пратя утре, без ангажимент?",
    ),
    LeadCategory.SOCIAL_ONLY: CategoryInfo(
        "Facebook/Instagram only", "Само Facebook/Instagram", "Own website", "Собствен сайт",
        "The Google listing links to a social page or link hub instead of a website. They already put effort "
        "into marketing - they get why it matters - but Google sends clicks to a page they don't control.",
        "Your own site built from your Facebook/Instagram content, linked from Google, live in 5 days",
        "Собствен сайт от съдържанието ви във Facebook/Instagram, свързан с Google, готов за 5 дни",
        "Can I build a free preview from your page and send it over tomorrow?",
        "Да направя ли безплатна чернова от страницата ви и да ви я пратя утре?",
    ),
    LeadCategory.NEW_BUSINESS: CategoryInfo(
        "New business", "Нов бизнес", "Launch package", "Стартов пакет",
        "Few reviews and no website: a business that is just starting. They are actively spending to get "
        "known, so a site plus a properly set-up Google profile is exactly what they need now.",
        "A website plus a fully set-up Google profile with photos and a review card, so new customers find you",
        "Сайт плюс изцяло настроен профил в Google със снимки и карта за отзиви, за да ви намират нови клиенти",
        "Can I send you a free preview of the site and a checklist for your Google profile?",
        "Да ви пратя ли безплатна чернова на сайта и списък какво да подобрим в Google профила?",
    ),
    LeadCategory.PLATFORM_ONLY: CategoryInfo(
        "Booking-platform page only", "Само профил в платформа", "Own site with direct booking",
        "Собствен сайт с директни резервации",
        "The listing points to a booking platform profile (Fresha, Booksy, Booking.com...). Every customer "
        "Google sends them pays the platform's commission or sees competitors next to them.",
        "Your own site with direct booking, so Google customers book with you, not through a platform",
        "Собствен сайт с директни резервации, така че клиентите от Google резервират при вас, не през платформа",
        "Can I show you a free preview of what your own booking page would look like?",
        "Да ви покажа ли безплатна чернова на собствената ви страница за резервации?",
    ),
    LeadCategory.WEAK_SITE: CategoryInfo(
        "Weak / outdated site", "Слаб / остарял сайт", "Website redesign", "Нов сайт",
        "Own website, but the audit found real problems: not mobile-friendly, outdated, slow, or no clear "
        "way to call/contact. They have paid for a site before, so the sale is an upgrade, not a convincing job.",
        "A modern, fast, mobile site that turns visitors into calls, keeping your domain",
        "Модерен, бърз сайт, удобен за телефон, който превръща посетителите в обаждания, на същия домейн",
        "Can I send you a free 2-minute video of what's costing you customers on the current site?",
        "Да ви пратя ли безплатно кратко видео какво ви губи клиенти на сегашния сайт?",
    ),
    LeadCategory.NO_BOOKING: CategoryInfo(
        "No online booking", "Без онлайн записване", "Online booking", "Онлайн записване",
        "A working site, but customers of this kind of business book appointments and there is no way to "
        "book online - every booking is a phone call during working hours.",
        "Online booking on your site and Google profile, so customers book 24/7 without calling",
        "Онлайн записване в сайта и в Google профила, за да записват часове 24/7 без обаждане",
        "Can I set up a free demo booking page for you to try?",
        "Да ви направя ли безплатна демо страница за записване, за да я пробвате?",
    ),
    LeadCategory.WEAK_GOOGLE: CategoryInfo(
        "Weak Google profile", "Слаб Google профил", "Google profile boost", "Подобряване на Google профила",
        "The website is fine, but the Google listing is thin: few reviews or photos, missing hours or details. "
        "Cheapest, fastest yes - a small first deal that opens the door for more.",
        "We complete and optimise your Google profile and give you QR review cards to get more 5-star reviews",
        "Попълваме и оптимизираме Google профила ви и ви даваме QR карти за още отзиви с 5 звезди",
        "Can I send you a free check of your Google profile with the 3 quickest wins?",
        "Да ви пратя ли безплатна проверка на Google профила с 3-те най-бързи подобрения?",
    ),
    LeadCategory.UNCHECKED: CategoryInfo(
        "Website not checked yet", "Сайтът не е проверен", "Check the site first", "Първо проверка на сайта",
        "Has an own website that hasn't been audited yet. Run the audit before calling to know what to sell.",
        "", "", "", "",
    ),
    LeadCategory.NOT_A_FIT: CategoryInfo(
        "Not a fit", "Не е подходящ", "Skip", "Пропусни",
        "Good online presence already, a chain branch, closed, or too badly rated to buy. Not worth a call.",
        "", "", "", "",
    ),
}  # fmt: skip

# The order categories are worth pitching in (also the order of the filter list).
CATEGORY_ORDER = list(CATEGORY_INFO)
SELLABLE = frozenset(c for c in CATEGORY_ORDER if c not in (LeadCategory.UNCHECKED, LeadCategory.NOT_A_FIT))


class OfferSettings(BaseModel):
    model_config = ConfigDict(json_schema_serialization_defaults_required=True)

    price: int = Field(ge=0, le=100_000)
    premium_price: int = Field(ge=0, le=100_000)
    odds: int = Field(ge=0, le=100, description="Relative close odds in %, used to rank the calling queue")


DEFAULT_OFFERS: dict[LeadCategory, OfferSettings] = {
    LeadCategory.BROKEN_SITE: OfferSettings(price=290, premium_price=390, odds=30),
    LeadCategory.NO_SITE: OfferSettings(price=290, premium_price=390, odds=22),
    LeadCategory.SOCIAL_ONLY: OfferSettings(price=290, premium_price=390, odds=24),
    LeadCategory.NEW_BUSINESS: OfferSettings(price=390, premium_price=490, odds=22),
    LeadCategory.PLATFORM_ONLY: OfferSettings(price=390, premium_price=490, odds=16),
    LeadCategory.WEAK_SITE: OfferSettings(price=390, premium_price=590, odds=12),
    LeadCategory.NO_BOOKING: OfferSettings(price=190, premium_price=290, odds=14),
    LeadCategory.WEAK_GOOGLE: OfferSettings(price=129, premium_price=149, odds=20),
    LeadCategory.UNCHECKED: OfferSettings(price=0, premium_price=0, odds=5),
    LeadCategory.NOT_A_FIT: OfferSettings(price=0, premium_price=0, odds=0),
}


class OfferConfig(BaseModel):
    """Editable prices/odds per category (Settings → Offers)."""

    model_config = ConfigDict(json_schema_serialization_defaults_required=True)

    offers: dict[LeadCategory, OfferSettings] = Field(
        default_factory=lambda: {k: v.model_copy() for k, v in DEFAULT_OFFERS.items()}
    )
    weekly_goal: int = Field(default=500, ge=0, le=1_000_000, description="Revenue goal per 7 days (EUR)")
    calls_per_day: int = Field(default=150, ge=1, le=2000)

    @field_validator("offers")
    @classmethod
    def _fill_missing(cls, value: dict[LeadCategory, OfferSettings]) -> dict[LeadCategory, OfferSettings]:
        merged = {k: v.model_copy() for k, v in DEFAULT_OFFERS.items()}
        merged.update(value)
        return merged

    def offer(self, category: LeadCategory) -> OfferSettings:
        return self.offers.get(category) or DEFAULT_OFFERS[category]


@dataclass(slots=True)
class CategoryResult:
    category: LeadCategory
    deal_value: int
    close_odds: int
    expected_value: int
    reason: str
    upsells: list[str] = field(default_factory=list)
    fit_notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "category": self.category.value,
            "deal_value": self.deal_value,
            "close_odds": self.close_odds,
            "expected_value": self.expected_value,
            "reason": self.reason,
            "upsells": self.upsells,
            "fit_notes": self.fit_notes,
        }


def _need(inp: ScoringInput, result: ScoreResult) -> tuple[LeadCategory, str]:
    opportunities = set(result.opportunities)
    reviews = inp.review_count or 0
    if OpportunityType.BROKEN_WEBSITE in opportunities:
        return LeadCategory.BROKEN_SITE, next(
            (r.text for r in result.reasons if r.opportunity == OpportunityType.BROKEN_WEBSITE),
            "Website does not work",
        )
    if not inp.website_url:
        if inp.review_count is not None and reviews < NEW_BUSINESS_MAX_REVIEWS:
            return LeadCategory.NEW_BUSINESS, f"No website and only {reviews} Google reviews - new business"
        return LeadCategory.NO_SITE, f"No website, {reviews} Google reviews"
    if inp.website_kind in ("social", "link_hub"):
        return LeadCategory.SOCIAL_ONLY, "Google listing links to a social/link page, not a website"
    if inp.website_kind == "booking_platform":
        return LeadCategory.PLATFORM_ONLY, "Google listing links to a booking-platform profile, not a website"
    if inp.audit is None or inp.website_status == "unaudited":
        return LeadCategory.UNCHECKED, "Own website, not audited yet"
    if inp.audit.status == "skipped":
        return LeadCategory.UNCHECKED, "Own website, audit was skipped"
    problems = [r for r in result.reasons if r.opportunity in WEBSITE_PROBLEMS]
    if problems:
        return LeadCategory.WEAK_SITE, problems[0].text
    if OpportunityType.NO_BOOKING in opportunities:
        return LeadCategory.NO_BOOKING, "No online booking on the website"
    google = [r for r in result.reasons if r.opportunity in GOOGLE_GAPS]
    if google:
        return LeadCategory.WEAK_GOOGLE, google[0].text
    return LeadCategory.NOT_A_FIT, "Website and Google profile look good"


def _not_a_fit(inp: ScoringInput, chain: str | None) -> str | None:
    if inp.business_status and inp.business_status.startswith("CLOSED"):
        return "Listed as closed"
    if chain:
        return f"Branch of a chain ({chain})"
    if inp.rating is not None and (inp.review_count or 0) >= 5 and inp.rating < MIN_GOOD_RATING:
        return f"Rated {inp.rating:.1f}★ - unlikely to invest in marketing"
    return None


def categorize(
    inp: ScoringInput,
    result: ScoreResult,
    config: OfferConfig,
    target: Target | None = None,
    chain: str | None = None,
) -> CategoryResult:
    """Pick the one offer to pitch this lead, its price and close odds."""
    blocker = _not_a_fit(inp, chain)
    if blocker:
        return CategoryResult(LeadCategory.NOT_A_FIT, 0, 0, 0, blocker)
    category, reason = _need(inp, result)
    offer = config.offer(category)
    premium = bool(target and target.value_tier >= 3)
    price = offer.premium_price if premium else offer.price
    odds = offer.odds
    notes: list[str] = []

    if category in SELLABLE:
        reviews = inp.review_count or 0
        if reviews >= 100:
            odds += 6
            notes.append(f"{reviews} reviews - busy, established business")
        elif reviews >= 30:
            odds += 4
            notes.append(f"{reviews} reviews - established business")
        elif reviews < 5 and category != LeadCategory.NEW_BUSINESS:
            odds -= 4
            notes.append("Very few reviews")
        if inp.rating is not None and inp.rating >= 4.5 and reviews >= 10:
            odds += 2
            notes.append(f"{inp.rating:.1f}★ - cares about reputation")
        if inp.phone_type == "mobile":
            odds += 4
            notes.append("Mobile number - the owner usually answers")
        elif inp.phone_type == "fixed_line":
            odds -= 2
            notes.append("Landline - may reach staff, ask for the owner")
        if premium and target:
            notes.append(f"{target.label}: high-value customers, premium price")
        odds = max(3, min(60, odds))
        if not inp.has_phone or inp.phone_invalid:
            odds = 0  # can't be called: nothing to rank it for
            notes.append("No working phone number")

    upsells: list[str] = []
    opportunities = set(result.opportunities)
    if category != LeadCategory.WEAK_GOOGLE and category in SELLABLE and opportunities & GOOGLE_GAPS:
        upsells.append(CATEGORY_INFO[LeadCategory.WEAK_GOOGLE].offer)
    if (
        category in (LeadCategory.NO_SITE, LeadCategory.SOCIAL_ONLY, LeadCategory.BROKEN_SITE,
                     LeadCategory.WEAK_SITE, LeadCategory.NEW_BUSINESS)
        and result.booking_oriented
    ):  # fmt: skip
        upsells.append(CATEGORY_INFO[LeadCategory.NO_BOOKING].offer)
    if category in SELLABLE and category not in (LeadCategory.WEAK_GOOGLE, LeadCategory.NO_BOOKING):
        upsells.append("Care plan €15/month (hosting, updates, small changes)")

    expected = round(price * odds / 100)
    return CategoryResult(category, price, odds, expected, reason, upsells, notes)
