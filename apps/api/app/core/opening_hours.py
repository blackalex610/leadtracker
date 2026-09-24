"""Opening-hours evaluation for Places-style ``periods``.

A period looks like ``{"open": {"day": 1, "hour": 9, "minute": 0},
"close": {"day": 1, "hour": 21, "minute": 0}}`` with day 0 = Sunday, in the
business's local time. A single period with no ``close`` means open 24/7.
"""

from __future__ import annotations

import re
from typing import Any

WEEK = 7 * 24 * 60
DAY = 24 * 60
WEEKDAYS_MON_FRI = (1, 2, 3, 4, 5)
_HHMM = re.compile(r"^([01]?\d|2[0-3]):([0-5]\d)$")


def parse_hhmm(value: str) -> int:
    match = _HHMM.match(value.strip())
    if not match:
        raise ValueError(f"Invalid time '{value}', expected HH:MM")
    return int(match.group(1)) * 60 + int(match.group(2))


def _point(p: dict[str, Any]) -> int:
    return int(p.get("day", 0)) * DAY + int(p.get("hour", 0)) * 60 + int(p.get("minute", 0))


def weekly_intervals(periods: list[dict[str, Any]] | None) -> list[tuple[int, int]]:
    """Convert periods into [start, end) minute intervals within a week (end may exceed WEEK)."""
    if not periods:
        return []
    intervals: list[tuple[int, int]] = []
    for period in periods:
        open_ = period.get("open")
        if not open_:
            continue
        close = period.get("close")
        if close is None:
            return [(0, WEEK)]  # always open
        start, end = _point(open_), _point(close)
        if end <= start:
            end += WEEK
        intervals.append((start, end))
    return intervals


def _overlap(a: tuple[int, int], b: tuple[int, int]) -> int:
    return max(0, min(a[1], b[1]) - max(a[0], b[0]))


def overlap_minutes(periods: list[dict[str, Any]] | None, day: int, start: int, end: int) -> int:
    """Minutes the business is open inside the window on ``day`` (0 = Sunday)."""
    window_start = day * DAY + start
    window_end = day * DAY + (end if end > start else end + DAY)
    total = 0
    for interval in weekly_intervals(periods):
        for shift in (-WEEK, 0, WEEK):
            total += _overlap((interval[0] + shift, interval[1] + shift), (window_start, window_end))
    return min(total, window_end - window_start)


def is_open_during(
    periods: list[dict[str, Any]] | None, day: int, window_start: str, window_end: str, min_overlap: int = 30
) -> bool:
    start, end = parse_hhmm(window_start), parse_hhmm(window_end)
    length = (end - start) if end > start else (end + DAY - start)
    return overlap_minutes(periods, day, start, end) >= min(min_overlap, length)


def open_days_bitmask(periods: list[dict[str, Any]] | None, window_start: str, window_end: str) -> int:
    mask = 0
    for day in range(7):
        if is_open_during(periods, day, window_start, window_end):
            mask |= 1 << day
    return mask


def open_in_window_on_weekdays(
    periods: list[dict[str, Any]] | None, window_start: str, window_end: str, min_days: int = 3
) -> bool | None:
    """True when open during the calling window on at least ``min_days`` of Mon–Fri.
    ``None`` when hours are unknown."""
    if not periods:
        return None
    days = sum(1 for d in WEEKDAYS_MON_FRI if is_open_during(periods, d, window_start, window_end))
    return days >= min_days


def python_weekday_to_places(weekday: int) -> int:
    """datetime.weekday() (Mon=0) -> Places day (Sun=0)."""
    return (weekday + 1) % 7
