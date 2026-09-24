"""Plain-data inputs for the scoring engine (no database access), so every rule
is unit-testable."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class NicheInfo:
    key: str
    label: str
    label_bg: str | None = None
    booking_oriented: bool = False
    discovery_dependent: bool = True
    match_types: list[str] = field(default_factory=list)


@dataclass(slots=True)
class AuditSnapshot:
    status: str  # success | failed | skipped
    error_code: str | None = None
    error_message: str | None = None
    health_score: int | None = None
    outdated_score: int | None = None
    outdated_band: str | None = None
    response_time_ms: int | None = None
    signals: list[dict[str, Any]] = field(default_factory=list)
    facts: dict[str, Any] = field(default_factory=dict)

    @property
    def signal_codes(self) -> set[str]:
        return {str(s.get("code")) for s in self.signals if (s.get("penalty") or 0) > 0}

    def signal(self, code: str) -> dict[str, Any] | None:
        return next((s for s in self.signals if s.get("code") == code), None)


@dataclass(slots=True)
class ScoringInput:
    name: str
    category: str | None = None
    primary_type: str | None = None
    types: list[str] = field(default_factory=list)
    city: str | None = None
    niche: NicheInfo | None = None
    has_phone: bool = False
    phone_invalid: bool = False
    website_url: str | None = None
    website_kind: str | None = None
    website_status: str = "none"
    audit: AuditSnapshot | None = None
    rating: float | None = None
    review_count: int | None = None
    opening_hours: dict[str, Any] | None = None
    address: str | None = None
    business_status: str | None = None
    photo_count: int | None = None
    description: str | None = None
    description_requested: bool = False
    open_in_calling_window: bool | None = None
    provider: str = "google_places"
