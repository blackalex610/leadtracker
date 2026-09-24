"""Editable configuration for the deterministic opportunity engine."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.enums import OpportunityType


class RuleKey(StrEnum):
    NO_WEBSITE = "no_website"
    WEBSITE_BROKEN = "website_broken"
    LOW_HEALTH = "low_health"
    NO_BOOKING = "no_booking"
    NO_CONTACT_CTA = "no_contact_cta"
    MOBILE_PROBLEM = "mobile_problem"
    WEAK_CONVERSION = "weak_conversion"
    OUTDATED_WEBSITE = "outdated_website"
    SLOW_WEBSITE = "slow_website"
    INCOMPLETE_GOOGLE = "incomplete_google"
    MISSING_BUSINESS_INFO = "missing_business_info"
    LOW_REVIEWS = "low_reviews"
    DISCOVERY_CATEGORY = "discovery_category"
    OPEN_IN_CALLING_WINDOW = "open_in_calling_window"
    PHONE_AVAILABLE = "phone_available"


class RuleMeta(BaseModel):
    model_config = ConfigDict(json_schema_serialization_defaults_required=True)

    label: str
    tier: str
    opportunity: OpportunityType | None
    description: str


RULE_META: dict[RuleKey, RuleMeta] = {
    RuleKey.NO_WEBSITE: RuleMeta(
        label="No website",
        tier="very_strong",
        opportunity=OpportunityType.NO_WEBSITE,
        description="No website listed, or the listing links only to a social/booking-platform page.",
    ),
    RuleKey.WEBSITE_BROKEN: RuleMeta(
        label="Website unreachable / broken",
        tier="very_strong",
        opportunity=OpportunityType.BROKEN_WEBSITE,
        description="DNS/SSL/connection failure, error status, parked domain or 'under construction' page.",
    ),
    RuleKey.LOW_HEALTH: RuleMeta(
        label="Low Website Health",
        tier="strong",
        opportunity=OpportunityType.WEBSITE_REDESIGN,
        description="Website Health score below the configured threshold.",
    ),
    RuleKey.NO_BOOKING: RuleMeta(
        label="No booking (booking-oriented category)",
        tier="very_strong",
        opportunity=OpportunityType.NO_BOOKING,
        description="No online booking mechanism detected for a category where customers typically book.",
    ),
    RuleKey.NO_CONTACT_CTA: RuleMeta(
        label="No clear contact CTA",
        tier="strong",
        opportunity=OpportunityType.NO_CONTACT_CTA,
        description="No call/contact/book call-to-action detected on the audited pages.",
    ),
    RuleKey.MOBILE_PROBLEM: RuleMeta(
        label="Mobile problem",
        tier="strong",
        opportunity=OpportunityType.MOBILE_PROBLEM,
        description="Missing/fixed viewport, Flash, or other major mobile usability signals.",
    ),
    RuleKey.WEAK_CONVERSION: RuleMeta(
        label="Weak conversion path",
        tier="strong",
        opportunity=OpportunityType.WEAK_CONVERSION,
        description="Several conversion elements missing (phone, contact form, services, prices, hours...).",
    ),
    RuleKey.OUTDATED_WEBSITE: RuleMeta(
        label="Outdated website",
        tier="moderate",
        opportunity=OpportunityType.OUTDATED_WEBSITE,
        description="Outdated index at or above the configured threshold.",
    ),
    RuleKey.SLOW_WEBSITE: RuleMeta(
        label="Slow website",
        tier="moderate",
        opportunity=OpportunityType.SLOW_WEBSITE,
        description="Homepage response slower than the 'very slow' threshold.",
    ),
    RuleKey.INCOMPLETE_GOOGLE: RuleMeta(
        label="Google profile gaps",
        tier="moderate",
        opportunity=OpportunityType.GOOGLE_PROFILE,
        description="Few photos, missing description (when requested) or possible category mismatch.",
    ),
    RuleKey.MISSING_BUSINESS_INFO: RuleMeta(
        label="Missing business info",
        tier="moderate",
        opportunity=OpportunityType.MISSING_BUSINESS_INFO,
        description="Opening hours, phone or address missing from the listing.",
    ),
    RuleKey.LOW_REVIEWS: RuleMeta(
        label="Low review volume",
        tier="moderate",
        opportunity=OpportunityType.LOW_REVIEWS,
        description="Fewer reviews than the configured threshold (a visibility opportunity, not a quality verdict).",
    ),
    RuleKey.DISCOVERY_CATEGORY: RuleMeta(
        label="Discovery-dependent category",
        tier="contextual",
        opportunity=None,
        description="Category relies heavily on online discovery.",
    ),
    RuleKey.OPEN_IN_CALLING_WINDOW: RuleMeta(
        label="Open during calling window",
        tier="contextual",
        opportunity=None,
        description="Open during the calling window on most weekdays.",
    ),
    RuleKey.PHONE_AVAILABLE: RuleMeta(
        label="Phone available",
        tier="contextual",
        opportunity=None,
        description="A valid phone number is available.",
    ),
}


class ScoringRule(BaseModel):
    model_config = ConfigDict(json_schema_serialization_defaults_required=True)

    points: int = Field(ge=0, le=100)
    enabled: bool = True


DEFAULT_RULE_POINTS: dict[RuleKey, int] = {
    RuleKey.NO_WEBSITE: 35,
    RuleKey.WEBSITE_BROKEN: 30,
    RuleKey.LOW_HEALTH: 25,
    RuleKey.NO_BOOKING: 15,
    RuleKey.NO_CONTACT_CTA: 10,
    RuleKey.MOBILE_PROBLEM: 10,
    RuleKey.WEAK_CONVERSION: 10,
    RuleKey.OUTDATED_WEBSITE: 10,
    RuleKey.SLOW_WEBSITE: 5,
    RuleKey.INCOMPLETE_GOOGLE: 5,
    RuleKey.MISSING_BUSINESS_INFO: 5,
    RuleKey.LOW_REVIEWS: 5,
    RuleKey.DISCOVERY_CATEGORY: 5,
    RuleKey.OPEN_IN_CALLING_WINDOW: 5,
    RuleKey.PHONE_AVAILABLE: 5,
}

DEFAULT_STRONG_TYPES = [
    "gym", "fitness_center", "yoga_studio", "beauty_salon", "hair_salon", "hair_care", "nail_salon",
    "barber_shop", "spa", "massage", "skin_care_clinic", "beautician", "makeup_artist", "tanning_studio",
    "dentist", "dental_clinic", "physiotherapist", "chiropractor", "doctor", "veterinary_care",
    "restaurant", "cafe", "coffee_shop", "bar", "bakery", "car_wash", "car_repair",
    "real_estate_agency", "florist", "photographer", "wedding_venue", "lodging", "hotel",
]  # fmt: skip

DEFAULT_BOOKING_TYPES = [
    "gym", "fitness_center", "yoga_studio", "beauty_salon", "hair_salon", "hair_care", "nail_salon",
    "barber_shop", "spa", "massage", "skin_care_clinic", "beautician", "tanning_studio", "dentist",
    "dental_clinic", "physiotherapist", "chiropractor", "doctor", "veterinary_care", "restaurant",
    "car_wash",
]  # fmt: skip


class ScoringConfig(BaseModel):
    model_config = ConfigDict(json_schema_serialization_defaults_required=True)

    rules: dict[RuleKey, ScoringRule] = Field(
        default_factory=lambda: {k: ScoringRule(points=v) for k, v in DEFAULT_RULE_POINTS.items()}
    )
    # Priority rules (transparent, see engine.assign_priority)
    hot_min_score: int = Field(default=50, ge=0, le=100)
    warm_min_score: int = Field(default=25, ge=0, le=100)
    hot_requires_phone: bool = True
    hot_requires_strong_category: bool = True
    hot_requires_major_opportunity: bool = True
    warm_requires_phone: bool = True
    major_opportunities: list[OpportunityType] = Field(
        default_factory=lambda: [
            OpportunityType.NO_WEBSITE,
            OpportunityType.BROKEN_WEBSITE,
            OpportunityType.WEBSITE_REDESIGN,
            OpportunityType.NO_BOOKING,
        ]
    )
    # Thresholds
    low_health_threshold: int = Field(default=40, ge=0, le=100)
    outdated_threshold: int = Field(default=50, ge=0, le=100)
    low_review_threshold: int = Field(default=20, ge=0)
    weak_conversion_min_missing: int = Field(default=3, ge=1, le=9)
    few_photos_threshold: int = Field(default=3, ge=0, le=10)
    # Category knowledge (Google place types), used when a business has no niche preset.
    strong_types: list[str] = Field(default_factory=lambda: list(DEFAULT_STRONG_TYPES))
    booking_types: list[str] = Field(default_factory=lambda: list(DEFAULT_BOOKING_TYPES))

    @field_validator("rules")
    @classmethod
    def _fill_missing_rules(cls, value: dict[RuleKey, ScoringRule]) -> dict[RuleKey, ScoringRule]:
        merged = {k: ScoringRule(points=v) for k, v in DEFAULT_RULE_POINTS.items()}
        merged.update(value)
        return merged

    def points(self, key: RuleKey) -> int:
        rule = self.rules.get(key)
        return rule.points if rule and rule.enabled else 0

    def enabled(self, key: RuleKey) -> bool:
        rule = self.rules.get(key)
        return bool(rule and rule.enabled)
