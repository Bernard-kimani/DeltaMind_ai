"""Red-folder macro news calendar — a deterministic, code-enforced no-trade
window around high-impact scheduled economic releases (FOMC, NFP/Employment
Situation, CPI, ISM PMI, JOLTS, ADP, etc.), separate from news_analyst.py/
track1_validator.py/track4_validator.py's per-symbol headline sentiment.

Why this exists as its own deterministic gate, not an LLM judgment call: the
whole point is that price action in the minutes around a red-folder release
is often violent, mechanical, and unrelated to any real edge this agent has
— the LLM can't be trusted to "decide" not to trade through it any more than
risk_gate.py trusts the LLM to size a position. This is enforced the same
way EOD liquidation is: a hard, auditable time check with zero LLM
involvement (see graph.py's news_blackout_gate node, the first node in the
graph, and risk_gate.py's backstop check for a cycle that started before a
blackout window and finished inside one).

**This calendar is a manually curated, week-specific list, not a live feed.**
No free/already-integrated real-time economic calendar exists in this
project's dependencies (same category of gap documented for Track 4's
earnings-conflict check in docs/tracks/track4_income_wheel.md) — building a
live one (e.g. FRED's release-dates API) is a real, separate integration
task. The entries below were verified via web search against federalreserve.gov,
bls.gov-adjacent sources, and ismworld.org on 2026-08-27 for the Aug 28 -
Sep 4, 2026 hackathon week specifically (sources noted per entry) — this is
a good-faith seed, NOT guaranteed exhaustive (lower-tier releases like
Case-Shiller, Chicago PMI, or Dallas Fed surveys weren't individually
checked). Re-verify against a live economic calendar (e.g. ForexFactory,
Investing.com, TradingEconomics) before trusting this for real capital, and
update RED_FOLDER_CALENDAR for any week beyond the one seeded here.

All comparison happens in UTC (explicit tz-aware datetimes throughout, never
the host machine's local clock) so the blackout check is correct regardless
of what timezone the process happens to run in. Display/logging uses
Africa/Nairobi (EAT, UTC+3 year-round — no DST to worry about, unlike
America/New_York) alongside UTC, so log lines read directly in the user's
own timezone without manual conversion.
"""

import datetime as dt
from typing import Literal, TypedDict
from zoneinfo import ZoneInfo

NAIROBI = ZoneInfo("Africa/Nairobi")

BLACKOUT_MINUTES_BEFORE = 5
BLACKOUT_MINUTES_AFTER = 5


class RedFolderEvent(TypedDict):
    name: str
    datetime_utc: dt.datetime
    impact: Literal["high", "medium"]
    source: str  # where this specific date/time was verified, for future re-checking


def _utc(year: int, month: int, day: int, hour: int, minute: int = 0) -> dt.datetime:
    return dt.datetime(year, month, day, hour, minute, tzinfo=dt.timezone.utc)


# Aug 28 - Sep 4, 2026 (the hackathon week). US is on EDT (UTC-4) throughout
# this window, so e.g. 8:30am ET -> 12:30 UTC.
RED_FOLDER_CALENDAR: list[RedFolderEvent] = [
    {
        "name": "ISM Manufacturing PMI (Aug data)",
        "datetime_utc": _utc(2026, 9, 1, 14, 0),
        "impact": "high",
        "source": "ismworld.org release calendar, verified 2026-08-27",
    },
    {
        "name": "JOLTS Job Openings (Jul data)",
        "datetime_utc": _utc(2026, 9, 1, 14, 0),
        "impact": "medium",
        "source": "bls.gov/jlt, verified 2026-08-27",
    },
    {
        "name": "ADP National Employment Report (Aug data)",
        "datetime_utc": _utc(2026, 9, 2, 12, 15),
        "impact": "medium",
        "source": "adp.com press release calendar, verified 2026-08-27",
    },
    {
        "name": "Initial Jobless Claims (weekly)",
        "datetime_utc": _utc(2026, 9, 3, 12, 30),
        "impact": "medium",
        "source": "recurring weekly BLS/DOL release, every Thursday 8:30am ET",
    },
    {
        "name": "Employment Situation / Non-Farm Payrolls (Aug data)",
        "datetime_utc": _utc(2026, 9, 4, 12, 30),
        "impact": "high",
        "source": "bls.gov Employment Situation schedule + financecalendar.com, verified 2026-08-27",
    },
]
# Confirmed via federalreserve.gov/monetarypolicy/fomccalendars.htm (2026-08-27):
# no FOMC meeting falls in this window — the nearest is September 15-16, 2026.


def _format_utc_and_nairobi(moment: dt.datetime) -> str:
    nairobi_time = moment.astimezone(NAIROBI)
    return f"{moment.strftime('%H:%M')} UTC / {nairobi_time.strftime('%H:%M')} EAT"


def check_news_blackout(now: dt.datetime | None = None) -> tuple[bool, str | None]:
    """True + a human-readable reason if `now` (defaults to the real current
    UTC time) falls within BLACKOUT_MINUTES_BEFORE/AFTER of any calendar
    entry. Boundaries are inclusive on both sides (exactly 5:00 before/after
    counts as blocked, not a one-tick-early escape)."""
    moment = now if now is not None else dt.datetime.now(dt.timezone.utc)
    before = dt.timedelta(minutes=BLACKOUT_MINUTES_BEFORE)
    after = dt.timedelta(minutes=BLACKOUT_MINUTES_AFTER)

    for event in RED_FOLDER_CALENDAR:
        window_start = event["datetime_utc"] - before
        window_end = event["datetime_utc"] + after
        if window_start <= moment <= window_end:
            reason = (
                f"within {BLACKOUT_MINUTES_BEFORE}min of {event['impact']}-impact release "
                f"'{event['name']}' at {_format_utc_and_nairobi(event['datetime_utc'])}"
            )
            return True, reason
    return False, None


def todays_calendar_summary(now: dt.datetime | None = None) -> str:
    """Full-day (not just the blackout window) context for the LLM catalyst
    validators (track1_validator.py/track4_validator.py) — the user's own
    goal: a symbol's price move at, say, 10:35am should be explainable by
    the LLM as "macro noise from the 10:05am release" or "heads-up, FOMC-
    adjacent event in 10 minutes" rather than the LLM only ever seeing
    company-specific headlines with no macro-calendar context at all."""
    moment = now if now is not None else dt.datetime.now(dt.timezone.utc)
    day_start = moment.replace(hour=0, minute=0, second=0, microsecond=0)
    day_end = day_start + dt.timedelta(days=1)
    todays_events = [e for e in RED_FOLDER_CALENDAR if day_start <= e["datetime_utc"] < day_end]
    if not todays_events:
        return "No scheduled high/medium-impact macro releases today."

    lines = []
    for event in sorted(todays_events, key=lambda e: e["datetime_utc"]):
        delta_min = (event["datetime_utc"] - moment).total_seconds() / 60
        when = f"released {abs(delta_min):.0f}min ago" if delta_min < 0 else f"in {delta_min:.0f}min"
        lines.append(f"- {event['name']} ({event['impact']} impact) — {_format_utc_and_nairobi(event['datetime_utc'])}, {when}")
    return "Today's scheduled macro releases:\n" + "\n".join(lines)
