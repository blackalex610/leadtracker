"""Google Business Profile completeness analysis, based only on the fields the
provider returned. A low review count is treated as a visibility/social-proof
opportunity, never as a verdict on the business."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.core.enums import Severity
from app.scoring.config import ScoringConfig
from app.scoring.inputs import ScoringInput


@dataclass(slots=True)
class GoogleProfileAnalysis:
    score: int | None
    signals: list[dict[str, Any]] = field(default_factory=list)

    @property
    def codes(self) -> set[str]:
        return {s["code"] for s in self.signals}


def _sig(code: str, label: str, severity: Severity) -> dict[str, Any]:
    return {"code": code, "label": label, "severity": severity.value}


def analyze_google_profile(inp: ScoringInput, cfg: ScoringConfig) -> GoogleProfileAnalysis:
    signals: list[dict[str, Any]] = []
    from_google = inp.provider in ("google_places", "demo")

    if not inp.has_phone:
        signals.append(_sig("missing_phone", "No phone number on the listing", Severity.MAJOR))
    if not inp.website_url:
        signals.append(_sig("missing_website", "No website on the listing", Severity.MAJOR))
    periods = (inp.opening_hours or {}).get("periods") if inp.opening_hours else None
    if not periods:
        signals.append(_sig("missing_hours", "No opening hours on the listing", Severity.MINOR))
    if not inp.address:
        signals.append(_sig("missing_address", "No address on the listing", Severity.MINOR))

    if inp.review_count is not None:
        if inp.review_count == 0:
            signals.append(_sig("no_reviews", "No Google reviews yet", Severity.MINOR))
        elif inp.review_count < cfg.low_review_threshold:
            signals.append(
                _sig(
                    "low_review_volume",
                    f"Only {inp.review_count} Google reviews (visibility opportunity)",
                    Severity.MINOR,
                )
            )
    if inp.rating is not None and inp.review_count and inp.review_count >= 5 and inp.rating < 4.0:
        signals.append(_sig("low_rating", f"Rating {inp.rating:.1f} — reputation opportunity", Severity.INFO))
    if from_google and inp.photo_count is not None and inp.photo_count < cfg.few_photos_threshold:
        signals.append(_sig("few_photos", f"Only {inp.photo_count} photo(s) on the listing", Severity.MINOR))
    if inp.description_requested and not inp.description:
        signals.append(_sig("missing_description", "No business description", Severity.MINOR))
    niche = inp.niche
    if (
        niche
        and niche.match_types
        and inp.primary_type
        and inp.primary_type not in niche.match_types
        and not set(inp.types) & set(niche.match_types)
    ):
        signals.append(
            _sig(
                "category_mismatch",
                f"Primary Google category '{inp.category or inp.primary_type}' may not match '{niche.label}'",
                Severity.MINOR,
            )
        )
    if inp.business_status and inp.business_status != "OPERATIONAL":
        signals.append(
            _sig(
                "not_operational",
                f"Listed as {inp.business_status.replace('_', ' ').lower()}",
                Severity.MAJOR,
            )
        )

    if not from_google:
        return GoogleProfileAnalysis(score=None, signals=signals)

    # Completeness score over the checks we can evaluate.
    earned = 0.0
    possible = 0.0
    checks: list[tuple[float, float]] = [
        (20, 20 if inp.has_phone else 0),
        (20, 20 if inp.website_url and inp.website_kind == "own" else (8 if inp.website_url else 0)),
        (15, 15 if periods else 0),
        (10, 10 if inp.address else 0),
    ]
    if inp.review_count is not None:
        checks.append(
            (15, 15 if inp.review_count >= cfg.low_review_threshold else (7 if inp.review_count > 0 else 0))
        )
    if inp.photo_count is not None:
        checks.append(
            (10, 10 if inp.photo_count >= cfg.few_photos_threshold else (5 if inp.photo_count > 0 else 0))
        )
    if inp.description_requested:
        checks.append((10, 10 if inp.description else 0))
    for weight, got in checks:
        possible += weight
        earned += got
    return GoogleProfileAnalysis(score=round(earned / possible * 100) if possible else None, signals=signals)
