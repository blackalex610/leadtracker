"""Future AI layer (not used in V1).

V1 is fully deterministic. An LLM-backed implementation of
:class:`LeadInsightProvider` can later summarize opportunities, write
personalized openers, classify businesses or analyze screenshots. It must only
receive observed data (``BusinessAnalysisInput``) and its output should be
shown alongside — never instead of — the deterministic reasons.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(slots=True)
class BusinessAnalysisInput:
    name: str
    category: str | None
    city: str | None
    opportunities: list[str]
    reasons: list[str]
    website_signals: list[dict[str, Any]] = field(default_factory=list)
    google_signals: list[dict[str, Any]] = field(default_factory=list)
    screenshot_url: str | None = None


@dataclass(slots=True)
class LeadInsight:
    summary: str
    opening_line: str | None = None
    redesign_angle: str | None = None
    provider: str = "none"
    confidence: float | None = None


class LeadInsightProvider(Protocol):
    name: str

    async def analyze_business(self, data: BusinessAnalysisInput) -> LeadInsight: ...


class NullInsightProvider:
    """Default: no AI. Returns the deterministic reasons as the summary."""

    name = "none"

    async def analyze_business(self, data: BusinessAnalysisInput) -> LeadInsight:
        return LeadInsight(summary="; ".join(data.reasons[:3]) or "No opportunity signals recorded.")
