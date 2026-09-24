"""WebsiteScoreCalculator: turns signals into a transparent Website Health score.

Health (0–100, higher = healthier) = sum over five categories of
``category_max - sum(penalties in category)``, floored at 0 per category.
A page that is effectively not a website (parked, default server page,
'under construction') is capped at 10.

The outdated index (0–100, higher = more outdated) is the capped sum of the
outdated-signal points.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.audit.signals import (
    CATEGORY_LABELS,
    CATEGORY_MAX,
    EFFECTIVELY_NO_SITE,
    OutdatedSignal,
    Signal,
    outdated_band,
)

EFFECTIVELY_NO_SITE_CAP = 10


@dataclass(slots=True)
class WebsiteScores:
    health: int
    categories: dict[str, dict[str, Any]]
    outdated: int
    outdated_band: str
    effectively_no_site: bool


def calculate_scores(signals: list[Signal], outdated_signals: list[OutdatedSignal]) -> WebsiteScores:
    categories: dict[str, dict[str, Any]] = {}
    for category, maximum in CATEGORY_MAX.items():
        penalty = sum(s.penalty for s in signals if s.category == category)
        score = max(0, maximum - penalty)
        categories[category] = {
            "label": CATEGORY_LABELS[category],
            "score": score,
            "max": maximum,
            "penalty": penalty,
            "signals": [s.code for s in signals if s.category == category and s.penalty > 0],
        }
    health = sum(c["score"] for c in categories.values())
    effectively_no_site = any(s.code in EFFECTIVELY_NO_SITE for s in signals)
    if effectively_no_site:
        health = min(health, EFFECTIVELY_NO_SITE_CAP)
    outdated = min(100, sum(o.points for o in outdated_signals))
    return WebsiteScores(
        health=health,
        categories=categories,
        outdated=outdated,
        outdated_band=outdated_band(outdated),
        effectively_no_site=effectively_no_site,
    )
