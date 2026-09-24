from __future__ import annotations

from typing import Any

from app.core.enums import DataQuality


def data_quality(
    *,
    has_phone: bool,
    website_url: str | None,
    address: str | None,
    rating: float | None,
    opening_hours: dict[str, Any] | None,
) -> tuple[DataQuality, dict[str, bool]]:
    checklist = {
        "phone": has_phone,
        "website": bool(website_url),
        "address": bool(address),
        "rating": rating is not None,
        "hours": bool(opening_hours and opening_hours.get("periods")),
    }
    present = sum(checklist.values())
    if present == 5:
        grade = DataQuality.EXCELLENT
    elif present == 4:
        grade = DataQuality.GOOD
    elif present >= 2:
        grade = DataQuality.PARTIAL
    else:
        grade = DataQuality.POOR
    return grade, checklist
