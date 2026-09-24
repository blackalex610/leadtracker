from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

from app.audit.html import ParsedPage


@dataclass(slots=True)
class AuditThresholds:
    slow_ms: int = 2500
    very_slow_ms: int = 5000


@dataclass(slots=True)
class AuditContext:
    """Everything the analyzers may look at. Analyzers are pure functions of this."""

    listed_url: str
    home: ParsedPage
    pages: list[ParsedPage]  # home first, then extra pages
    response_time_ms: int
    redirect_count: int
    final_https: bool
    https_available: bool | None = None  # when final URL is http: does https work?
    ssl_error: bool = False
    image_checks: dict[str, int | None] = field(default_factory=dict)
    link_checks: dict[str, int | None] = field(default_factory=dict)
    booking_expected: bool = False
    country_code: str = "BG"
    today: date = field(default_factory=date.today)
    thresholds: AuditThresholds = field(default_factory=AuditThresholds)
    facts: dict[str, Any] = field(default_factory=dict)

    @property
    def combined_text(self) -> str:
        return " \n ".join(p.lowered_text for p in self.pages)

    @property
    def combined_headings(self) -> str:
        return " | ".join(h.lower() for p in self.pages for h in p.headings)

    @property
    def combined_link_text(self) -> str:
        return " | ".join(p.all_link_text() for p in self.pages)

    @property
    def combined_buttons(self) -> str:
        return " | ".join(b.lower() for p in self.pages for b in p.button_texts)
