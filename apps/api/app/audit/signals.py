"""Website signal catalog: every observable problem, its category, severity,
label and Website Health penalty — in one place so the score is transparent.

Labels are phrased as observations ("No booking mechanism detected"), never as
claims about the business.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from app.core.enums import Severity

CATEGORY_MAX: dict[str, int] = {"technical": 25, "mobile": 20, "conversion": 25, "content": 15, "trust": 15}
CATEGORY_LABELS: dict[str, str] = {
    "technical": "Technical quality",
    "mobile": "Mobile quality",
    "conversion": "Conversion quality",
    "content": "Content quality",
    "trust": "Trust signals",
}


@dataclass(frozen=True, slots=True)
class SignalSpec:
    category: str
    severity: Severity
    label: str
    penalty: int


C, M, m, i = Severity.CRITICAL, Severity.MAJOR, Severity.MINOR, Severity.INFO

SIGNAL_CATALOG: dict[str, SignalSpec] = {
    # technical
    "not_https": SignalSpec("technical", M, "Site is not served over HTTPS", 10),
    "no_https_redirect": SignalSpec(
        "technical", m, "HTTPS works but the listed http:// address does not redirect to it", 3
    ),
    "ssl_error": SignalSpec("technical", M, "HTTPS certificate/connection error", 10),
    "very_slow": SignalSpec("technical", M, "Very slow homepage response", 8),
    "slow": SignalSpec("technical", m, "Slow homepage response", 4),
    "missing_title": SignalSpec("technical", m, "Missing page title", 4),
    "missing_meta_description": SignalSpec("technical", m, "Missing meta description", 2),
    "missing_h1": SignalSpec("technical", m, "Missing main heading (H1)", 2),
    "broken_images": SignalSpec("technical", m, "Broken images", 4),
    "broken_links": SignalSpec("technical", m, "Broken internal links", 4),
    "mixed_content": SignalSpec("technical", m, "Insecure (http) resources on an HTTPS page", 3),
    "excessive_redirects": SignalSpec("technical", m, "Long redirect chain", 2),
    # mobile
    "no_viewport": SignalSpec("mobile", C, "No mobile viewport configured (likely not mobile-friendly)", 14),
    "viewport_not_responsive": SignalSpec("mobile", M, "Viewport uses a fixed width (not responsive)", 10),
    "uses_flash": SignalSpec("mobile", M, "Uses Flash content (does not work on phones)", 10),
    "table_layout": SignalSpec("mobile", M, "Fixed-width table layout", 6),
    "fixed_width_css": SignalSpec("mobile", m, "Fixed-width page container in CSS", 4),
    "zoom_disabled": SignalSpec("mobile", m, "Pinch-zoom disabled", 2),
    # conversion
    "no_phone": SignalSpec("conversion", M, "No phone number found on the website", 7),
    "no_click_to_call": SignalSpec("conversion", m, "Phone shown but not tappable (no tel: link)", 2),
    "no_contact_cta": SignalSpec("conversion", M, "No clear contact call-to-action detected", 6),
    "no_booking": SignalSpec("conversion", M, "No online booking mechanism detected", 6),
    "no_contact_form": SignalSpec("conversion", m, "No contact/inquiry form detected", 3),
    "no_clear_service_description": SignalSpec("conversion", M, "No clear services section detected", 4),
    "no_price_information": SignalSpec("conversion", m, "No price information detected", 2),
    "no_location_information": SignalSpec("conversion", m, "No address/location information detected", 3),
    "no_hours": SignalSpec("conversion", m, "No opening hours detected", 2),
    "no_social_links": SignalSpec("conversion", i, "No social media links detected", 1),
    # content
    "very_little_text": SignalSpec("content", M, "Very little text content", 5),
    "outdated_copyright": SignalSpec("content", M, "Outdated copyright year", 6),
    "stale_copyright": SignalSpec("content", m, "Copyright year not updated recently", 3),
    "placeholder_text": SignalSpec("content", M, "Placeholder/template text found", 8),
    "under_construction": SignalSpec(
        "content", C, "Site shows an 'under construction' / 'coming soon' page", 15
    ),
    "parked_domain": SignalSpec("content", C, "Domain appears to be parked / for sale", 15),
    "default_server_page": SignalSpec("content", C, "Server default page instead of a website", 15),
    "generic_template_language": SignalSpec("content", m, "Generic template wording", 3),
    "unfinished_content": SignalSpec("content", m, "Many links point nowhere (#) — unfinished sections", 4),
    "prices_only_in_bgn": SignalSpec("content", M, "Prices appear only in leva (BGN)", 5),
    # trust
    "no_business_identity": SignalSpec("trust", M, "Neither phone nor address shown on the website", 8),
    "no_privacy_policy": SignalSpec("trust", m, "No privacy/cookie policy link detected", 4),
    "no_testimonials": SignalSpec("trust", m, "No testimonials or reviews section detected", 3),
    "no_about": SignalSpec("trust", m, "No 'About us' section detected", 3),
}

EFFECTIVELY_NO_SITE = frozenset({"under_construction", "parked_domain", "default_server_page"})
MOBILE_MAJOR = frozenset({"no_viewport", "viewport_not_responsive", "uses_flash"})
CONVERSION_ELEMENTS = frozenset(
    {
        "no_phone",
        "no_contact_cta",
        "no_booking",
        "no_contact_form",
        "no_clear_service_description",
        "no_price_information",
        "no_location_information",
        "no_hours",
    }
)


@dataclass(slots=True)
class Signal:
    code: str
    category: str
    severity: str
    label: str
    detail: str | None = None
    penalty: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def make_signal(
    code: str, detail: str | None = None, *, penalty: int | None = None, severity: Severity | None = None
) -> Signal:
    spec = SIGNAL_CATALOG[code]
    return Signal(
        code=code,
        category=spec.category,
        severity=(severity or spec.severity).value,
        label=spec.label,
        detail=detail,
        penalty=spec.penalty if penalty is None else penalty,
    )


@dataclass(slots=True)
class OutdatedSignal:
    code: str
    label: str
    points: int
    detail: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


OUTDATED_BANDS: list[tuple[int, str]] = [
    (80, "Severe problems"),
    (60, "Clearly outdated"),
    (40, "Needs improvement"),
    (20, "Some issues"),
    (0, "Modern / healthy"),
]


def outdated_band(score: int) -> str:
    for threshold, label in OUTDATED_BANDS:
        if score >= threshold:
            return label
    return OUTDATED_BANDS[-1][1]
