"""Deterministic opportunity engine.

``calculate_opportunity_score`` applies the configured rules to observed facts
and returns a score, a priority, opportunity tags and human-readable reasons.
No LLM is involved. Reasons describe observations ("No booking mechanism
detected"), never assumptions ("Customers cannot book online").
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.audit.signals import CONVERSION_ELEMENTS, MOBILE_MAJOR, SIGNAL_CATALOG
from app.core.enums import OpportunityType, Priority
from app.core.text import domain_of
from app.scoring.config import RULE_META, RuleKey, ScoringConfig
from app.scoring.google_profile import GoogleProfileAnalysis, analyze_google_profile
from app.scoring.inputs import ScoringInput

BROKEN_EXPLANATIONS = {
    "parked_domain": "Website address shows a parked-domain / for-sale page",
    "default_server_page": "Website address shows a server default page instead of a website",
    "under_construction": "Website shows an 'under construction' / 'coming soon' page",
}

MISSING_ELEMENT_LABELS = {
    "no_phone": "phone number",
    "no_contact_cta": "contact call-to-action",
    "no_booking": "online booking",
    "no_contact_form": "contact form",
    "no_clear_service_description": "services section",
    "no_price_information": "prices",
    "no_location_information": "address/location",
    "no_hours": "opening hours",
}


@dataclass(slots=True)
class Reason:
    rule: str
    points: int
    text: str
    opportunity: OpportunityType | None
    tier: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "rule": self.rule,
            "points": self.points,
            "text": self.text,
            "opportunity": self.opportunity.value if self.opportunity else None,
            "tier": self.tier,
        }


@dataclass(slots=True)
class ScoreResult:
    score: int
    priority: Priority
    priority_reason: str
    opportunities: list[OpportunityType]
    reasons: list[Reason]
    notes: list[str]
    strong_category: bool
    booking_oriented: bool
    google: GoogleProfileAnalysis
    missing_conversion: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "score": self.score,
            "priority": self.priority.value,
            "priority_reason": self.priority_reason,
            "opportunities": [o.value for o in self.opportunities],
            "reasons": [r.to_dict() for r in self.reasons],
            "notes": self.notes,
        }


def is_strong_category(inp: ScoringInput, cfg: ScoringConfig) -> bool:
    if inp.niche is not None:
        return inp.niche.discovery_dependent
    types = {inp.primary_type, *inp.types} - {None}
    return bool(types & set(cfg.strong_types))


def is_booking_oriented(inp: ScoringInput, cfg: ScoringConfig) -> bool:
    if inp.niche is not None:
        return inp.niche.booking_oriented
    if inp.primary_type:
        return inp.primary_type in cfg.booking_types
    return bool(set(inp.types) & set(cfg.booking_types))


def _platform_name(url: str | None) -> str:
    domain = domain_of(url) or "booking platform"
    return domain.split(".")[0].capitalize()


def calculate_opportunity_score(inp: ScoringInput, cfg: ScoringConfig) -> ScoreResult:
    reasons: list[Reason] = []
    notes: list[str] = []
    strong = is_strong_category(inp, cfg)
    booking = is_booking_oriented(inp, cfg)
    audit = inp.audit

    def fire(key: RuleKey, text: str) -> None:
        if not cfg.enabled(key):
            return
        meta = RULE_META[key]
        reasons.append(Reason(key.value, cfg.points(key), text, meta.opportunity, meta.tier))

    # --- website ---------------------------------------------------------------------
    booking_detected = inp.website_kind == "booking_platform" or bool(
        audit and audit.facts.get("booking_detected")
    )
    missing_conversion: list[str] = []

    if not inp.website_url:
        fire(RuleKey.NO_WEBSITE, "No website listed")
    elif inp.website_kind == "social":
        fire(
            RuleKey.NO_WEBSITE,
            f"Listing links to a social media page ({domain_of(inp.website_url)}), not a website",
        )
    elif inp.website_kind == "link_hub":
        fire(
            RuleKey.NO_WEBSITE, f"Listing links to a link page ({domain_of(inp.website_url)}), not a website"
        )
    elif inp.website_kind == "booking_platform":
        fire(
            RuleKey.NO_WEBSITE,
            f"Listing links to a {_platform_name(inp.website_url)} profile, not an own website",
        )
    elif audit is None or inp.website_status == "unaudited":
        notes.append("Website not audited yet")
    elif audit.status == "failed":
        message = audit.error_message or audit.error_code or "unknown error"
        fire(RuleKey.WEBSITE_BROKEN, f"Website could not be loaded: {message}")
    elif audit.status == "skipped":
        notes.append(f"Website audit skipped: {audit.error_message or audit.error_code}")
    else:
        codes = audit.signal_codes
        broken = next((c for c in BROKEN_EXPLANATIONS if c in codes), None)
        if broken:
            fire(RuleKey.WEBSITE_BROKEN, BROKEN_EXPLANATIONS[broken])
        else:
            if audit.health_score is not None and audit.health_score < cfg.low_health_threshold:
                fire(
                    RuleKey.LOW_HEALTH,
                    f"Website Health {audit.health_score}/100 (below {cfg.low_health_threshold})",
                )
            if "no_contact_cta" in codes:
                fire(RuleKey.NO_CONTACT_CTA, "No clear contact call-to-action detected on the website")
            mobile = sorted(codes & MOBILE_MAJOR)
            if mobile:
                fire(RuleKey.MOBILE_PROBLEM, f"Mobile issue: {SIGNAL_CATALOG[mobile[0]].label}")
            missing_conversion = [
                MISSING_ELEMENT_LABELS[c]
                for c in sorted(CONVERSION_ELEMENTS)
                if c in codes and (c != "no_booking" or booking)
            ]
            if len(missing_conversion) >= cfg.weak_conversion_min_missing:
                fire(
                    RuleKey.WEAK_CONVERSION,
                    f"{len(missing_conversion)} conversion elements not found: {', '.join(missing_conversion)}",
                )
            if audit.outdated_score is not None and audit.outdated_score >= cfg.outdated_threshold:
                band = f" ({audit.outdated_band.lower()})" if audit.outdated_band else ""
                fire(RuleKey.OUTDATED_WEBSITE, f"Outdated index {audit.outdated_score}/100{band}")
            if "very_slow" in codes:
                seconds = (audit.response_time_ms or 0) / 1000
                fire(RuleKey.SLOW_WEBSITE, f"Homepage took {seconds:.1f}s to load")

    if booking and not booking_detected:
        if not inp.website_url or inp.website_kind in ("social", "link_hub"):
            fire(
                RuleKey.NO_BOOKING,
                "No online booking channel found (no website) in a booking-oriented category",
            )
        elif inp.website_kind == "own" and audit is not None and inp.website_status != "unaudited":
            if audit.status == "failed" or any(r.rule == RuleKey.WEBSITE_BROKEN.value for r in reasons):
                fire(RuleKey.NO_BOOKING, "No working online booking channel (website not working)")
            elif audit.status == "success":
                fire(
                    RuleKey.NO_BOOKING, "No online booking mechanism detected in a booking-oriented category"
                )

    # --- Google profile ---------------------------------------------------------------
    google = analyze_google_profile(inp, cfg)
    gcodes = google.codes
    profile_gaps = [
        s["label"]
        for s in google.signals
        if s["code"] in ("few_photos", "missing_description", "category_mismatch")
    ]
    if profile_gaps:
        fire(RuleKey.INCOMPLETE_GOOGLE, "Google profile: " + "; ".join(profile_gaps))
    missing_info = [
        s["label"]
        for s in google.signals
        if s["code"] in ("missing_hours", "missing_phone", "missing_address")
    ]
    if missing_info:
        fire(RuleKey.MISSING_BUSINESS_INFO, "; ".join(missing_info))
    if "no_reviews" in gcodes or "low_review_volume" in gcodes:
        fire(
            RuleKey.LOW_REVIEWS,
            f"{inp.review_count} Google reviews (below {cfg.low_review_threshold}) — social proof opportunity",
        )

    # --- contextual -------------------------------------------------------------------
    phone_ok = inp.has_phone and not inp.phone_invalid
    if strong:
        label = inp.niche.label if inp.niche else (inp.category or inp.primary_type or "category")
        fire(RuleKey.DISCOVERY_CATEGORY, f"{label}: category relies on online discovery")
    if inp.open_in_calling_window:
        fire(RuleKey.OPEN_IN_CALLING_WINDOW, "Open during the calling window on most weekdays")
    if phone_ok:
        fire(RuleKey.PHONE_AVAILABLE, "Phone number available")
    elif inp.phone_invalid:
        notes.append("Phone number marked as wrong")
    else:
        notes.append("No phone number found")

    reasons = [r for r in reasons if r.points > 0 or r.opportunity is not None]
    score = min(100, sum(r.points for r in reasons))
    opportunities: list[OpportunityType] = []
    for reason in reasons:
        if reason.opportunity and reason.opportunity not in opportunities:
            opportunities.append(reason.opportunity)

    priority, priority_reason = assign_priority(inp, cfg, score, opportunities, strong, phone_ok)
    return ScoreResult(
        score=score,
        priority=priority,
        priority_reason=priority_reason,
        opportunities=opportunities,
        reasons=sorted(reasons, key=lambda r: -r.points),
        notes=notes,
        strong_category=strong,
        booking_oriented=booking,
        google=google,
        missing_conversion=missing_conversion,
    )


def assign_priority(
    inp: ScoringInput,
    cfg: ScoringConfig,
    score: int,
    opportunities: list[OpportunityType],
    strong: bool,
    phone_ok: bool,
) -> tuple[Priority, str]:
    if inp.business_status == "CLOSED_PERMANENTLY":
        return Priority.COLD, "COLD: listed as permanently closed"
    if inp.business_status == "CLOSED_TEMPORARILY":
        return Priority.COLD, "COLD: listed as temporarily closed"

    major = [o for o in opportunities if o in cfg.major_opportunities]
    checks = [
        (cfg.hot_requires_phone, phone_ok, "phone available", "no phone"),
        (cfg.hot_requires_strong_category, strong, "strong category", "category not discovery-dependent"),
        (
            cfg.hot_requires_major_opportunity,
            bool(major),
            f"major issue: {major[0].value}" if major else "major issue",
            "no major digital issue",
        ),
        (
            True,
            score >= cfg.hot_min_score,
            f"score {score} ≥ {cfg.hot_min_score}",
            f"score {score} < {cfg.hot_min_score}",
        ),
    ]
    required = [c for c in checks if c[0]]
    if all(ok for _, ok, _, _ in required):
        return Priority.HOT, "HOT: " + " · ".join(yes for _, _, yes, _ in required)

    blockers = [no for _, ok, _, no in required if not ok]
    warm_phone_ok = phone_ok or not cfg.warm_requires_phone
    if warm_phone_ok and score >= cfg.warm_min_score:
        parts = (["phone available"] if phone_ok else []) + [f"score {score} ≥ {cfg.warm_min_score}"]
        return Priority.WARM, "WARM: " + " · ".join(parts) + f" (not HOT: {', '.join(blockers)})"
    if not warm_phone_ok:
        return Priority.COLD, "COLD: no phone number"
    return Priority.COLD, f"COLD: score {score} < {cfg.warm_min_score}"
