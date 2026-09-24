from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.core.enums import CallOutcome, LeadStatus
from app.core.opening_hours import (
    is_open_during,
    open_days_bitmask,
    open_in_window_on_weekdays,
    overlap_minutes,
    parse_hhmm,
    python_weekday_to_places,
)
from app.services.calls import default_callback_time, status_after_call
from app.services.settings import RuntimeSettings

WEEKDAYS_9_TO_21 = [
    {"open": {"day": d, "hour": 9, "minute": 0}, "close": {"day": d, "hour": 21, "minute": 0}}
    for d in range(1, 6)
]


def test_parse_hhmm() -> None:
    assert parse_hhmm("19:00") == 1140
    assert parse_hhmm("7:05") == 425
    with pytest.raises(ValueError):
        parse_hhmm("25:00")


def test_open_during_evening_window() -> None:
    assert is_open_during(WEEKDAYS_9_TO_21, 1, "19:00", "21:00")
    assert not is_open_during(WEEKDAYS_9_TO_21, 0, "19:00", "21:00")  # Sunday closed
    closes_at_19 = [
        {"open": {"day": 1, "hour": 9, "minute": 0}, "close": {"day": 1, "hour": 19, "minute": 15}}
    ]
    assert not is_open_during(closes_at_19, 1, "19:00", "21:00")  # only 15 minutes of overlap


def test_periods_crossing_midnight_and_week_boundary() -> None:
    late = [{"open": {"day": 6, "hour": 20, "minute": 0}, "close": {"day": 0, "hour": 2, "minute": 0}}]
    assert is_open_during(late, 6, "23:00", "01:00")
    assert overlap_minutes(late, 6, parse_hhmm("19:00"), parse_hhmm("21:00")) == 60


def test_always_open() -> None:
    always = [{"open": {"day": 0, "hour": 0, "minute": 0}}]
    assert open_days_bitmask(always, "19:00", "21:00") == 0b1111111


def test_open_on_most_weekdays() -> None:
    assert open_in_window_on_weekdays(WEEKDAYS_9_TO_21, "19:00", "21:00") is True
    assert open_in_window_on_weekdays(WEEKDAYS_9_TO_21, "22:00", "23:00") is False
    assert open_in_window_on_weekdays(None, "19:00", "21:00") is None


def test_weekday_conversion() -> None:
    assert python_weekday_to_places(0) == 1  # Monday
    assert python_weekday_to_places(6) == 0  # Sunday


@pytest.mark.parametrize(
    ("current", "outcome", "expected"),
    [
        (LeadStatus.NEW, CallOutcome.NO_ANSWER, LeadStatus.NO_ANSWER),
        (LeadStatus.NEW, CallOutcome.INTERESTED, LeadStatus.INTERESTED),
        (LeadStatus.NEW, CallOutcome.CALLBACK, LeadStatus.CALLBACK),
        (LeadStatus.NEW, CallOutcome.NOT_INTERESTED, LeadStatus.LOST),
        (LeadStatus.NEW, CallOutcome.ALREADY_HAS_PROVIDER, LeadStatus.LOST),
        (LeadStatus.NEW, CallOutcome.WRONG_NUMBER, LeadStatus.CALLED),
        (LeadStatus.NEW, CallOutcome.DO_NOT_CONTACT, LeadStatus.DO_NOT_CONTACT),
        # Never downgrade a progressed lead
        (LeadStatus.PROPOSAL, CallOutcome.NO_ANSWER, LeadStatus.PROPOSAL),
        (LeadStatus.QUALIFIED, CallOutcome.CALLBACK, LeadStatus.QUALIFIED),
        (LeadStatus.WON, CallOutcome.NOT_INTERESTED, LeadStatus.WON),
        (LeadStatus.PROPOSAL, CallOutcome.NOT_INTERESTED, LeadStatus.LOST),
        (LeadStatus.LOST, CallOutcome.INTERESTED, LeadStatus.INTERESTED),
        (LeadStatus.DO_NOT_CONTACT, CallOutcome.INTERESTED, LeadStatus.DO_NOT_CONTACT),
        (LeadStatus.WON, CallOutcome.DO_NOT_CONTACT, LeadStatus.DO_NOT_CONTACT),
    ],
)
def test_status_after_call(current: LeadStatus, outcome: CallOutcome, expected: LeadStatus) -> None:
    assert status_after_call(current, outcome) == expected


def test_default_callback_is_next_day_at_window_start() -> None:
    runtime = RuntimeSettings()
    now = datetime(2026, 9, 24, 20, 30, tzinfo=UTC)  # 23:30 in Sofia
    callback = default_callback_time(runtime, now)
    assert callback == datetime(2026, 9, 25, 16, 0, tzinfo=UTC)  # 19:00 EEST
