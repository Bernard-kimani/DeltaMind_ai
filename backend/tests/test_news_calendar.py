"""Sanity checks for app/quant/news_calendar.py's blackout-window math —
pure functions, no Alpaca/LLM call needed. Uses a fake `now` throughout so
these stay correct regardless of which real week RED_FOLDER_CALENDAR
currently holds."""

import datetime as dt

from app.quant.news_calendar import (
    BLACKOUT_MINUTES_AFTER,
    BLACKOUT_MINUTES_BEFORE,
    RedFolderEvent,
    check_news_blackout,
    todays_calendar_summary,
)

_EVENT: RedFolderEvent = {
    "name": "Test High-Impact Release",
    "datetime_utc": dt.datetime(2026, 9, 4, 12, 30, tzinfo=dt.timezone.utc),
    "impact": "high",
    "source": "test fixture",
}


def _patched(monkeypatch, events):
    monkeypatch.setattr("app.quant.news_calendar.RED_FOLDER_CALENDAR", events)


def test_clear_well_before_event(monkeypatch):
    _patched(monkeypatch, [_EVENT])
    now = _EVENT["datetime_utc"] - dt.timedelta(minutes=30)
    blocked, reason = check_news_blackout(now)
    assert blocked is False
    assert reason is None


def test_blocked_exactly_at_before_boundary(monkeypatch):
    _patched(monkeypatch, [_EVENT])
    now = _EVENT["datetime_utc"] - dt.timedelta(minutes=BLACKOUT_MINUTES_BEFORE)
    blocked, reason = check_news_blackout(now)
    assert blocked is True
    assert "Test High-Impact Release" in reason


def test_clear_one_minute_before_boundary(monkeypatch):
    _patched(monkeypatch, [_EVENT])
    now = _EVENT["datetime_utc"] - dt.timedelta(minutes=BLACKOUT_MINUTES_BEFORE + 1)
    blocked, _ = check_news_blackout(now)
    assert blocked is False


def test_blocked_at_the_event_itself(monkeypatch):
    _patched(monkeypatch, [_EVENT])
    blocked, reason = check_news_blackout(_EVENT["datetime_utc"])
    assert blocked is True
    assert "high-impact" in reason


def test_blocked_exactly_at_after_boundary(monkeypatch):
    _patched(monkeypatch, [_EVENT])
    now = _EVENT["datetime_utc"] + dt.timedelta(minutes=BLACKOUT_MINUTES_AFTER)
    blocked, _ = check_news_blackout(now)
    assert blocked is True


def test_clear_one_minute_after_boundary(monkeypatch):
    _patched(monkeypatch, [_EVENT])
    now = _EVENT["datetime_utc"] + dt.timedelta(minutes=BLACKOUT_MINUTES_AFTER + 1)
    blocked, _ = check_news_blackout(now)
    assert blocked is False


def test_no_events_never_blocks(monkeypatch):
    _patched(monkeypatch, [])
    blocked, reason = check_news_blackout(dt.datetime(2026, 9, 4, 12, 30, tzinfo=dt.timezone.utc))
    assert blocked is False
    assert reason is None


def test_todays_calendar_summary_includes_past_and_upcoming(monkeypatch):
    past_event: RedFolderEvent = {
        "name": "Already Released",
        "datetime_utc": dt.datetime(2026, 9, 4, 8, 0, tzinfo=dt.timezone.utc),
        "impact": "medium",
        "source": "test fixture",
    }
    upcoming_event: RedFolderEvent = {
        "name": "Coming Up Later",
        "datetime_utc": dt.datetime(2026, 9, 4, 18, 0, tzinfo=dt.timezone.utc),
        "impact": "high",
        "source": "test fixture",
    }
    _patched(monkeypatch, [past_event, upcoming_event])
    now = dt.datetime(2026, 9, 4, 12, 0, tzinfo=dt.timezone.utc)

    summary = todays_calendar_summary(now)
    assert "Already Released" in summary
    assert "released 240min ago" in summary
    assert "Coming Up Later" in summary
    assert "in 360min" in summary


def test_todays_calendar_summary_excludes_other_days(monkeypatch):
    tomorrow_event: RedFolderEvent = {
        "name": "Tomorrow's Release",
        "datetime_utc": dt.datetime(2026, 9, 5, 12, 30, tzinfo=dt.timezone.utc),
        "impact": "high",
        "source": "test fixture",
    }
    _patched(monkeypatch, [tomorrow_event])
    now = dt.datetime(2026, 9, 4, 12, 0, tzinfo=dt.timezone.utc)

    summary = todays_calendar_summary(now)
    assert "Tomorrow's Release" not in summary
    assert "No scheduled" in summary
