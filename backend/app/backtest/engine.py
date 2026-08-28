"""Real backtest engine: replays historical bars through each track's
DETERMINISTIC (non-LLM) entry gate — check_track1_confluence /
check_wheel_put_regime — to measure how often a symbol would actually have
qualified for LLM validation over a real historical window. This is
deliberately a gate-qualification-frequency report, not a P&L simulator:
no historical option-chain/Greeks/IV data source exists anywhere in this
codebase or the Alpaca API surface available to it, so trade simulation
and Track 4's IV-percentile leg are both out of scope — reported as
explicit known_gaps rather than faked with a synthetic IV proxy.

Confirmed via a real API call while building this: Alpaca's free-tier
data plan restricts only *recent* (same-day/in-progress) SIP data, not
genuinely historical data — a request for an already-closed historical
date range gets full consolidated (SIP) bars, not the sparse IEX-only feed
the live streaming path is limited to. `run()` clamps `end` to at least
one full day in the past to avoid ever requesting an in-progress day.
"""

import datetime as dt
from dataclasses import dataclass, field

from app.backtest import historical_data
from app.quant.technical_signals import EMA_TREND_PERIOD, WHEEL_EMA_PERIOD, check_track1_confluence, check_wheel_put_regime

# Match live's own fixed trailing-window sizes exactly (rest_client.py's
# get_recent_bars/get_15m_bars limits, market_ingestion.py's
# WHEEL_DAILY_BARS_LIMIT) rather than feeding the gate functions
# ever-growing history — compute_ema/compute_rsi always re-seed from the
# first bar of whatever window they're given, so a faithful replay means
# reproducing live's exact fixed-window shape at each evaluation point,
# not a continuously-carried full-history EMA live never actually computes.
TRACK1_1M_WINDOW = 100
TRACK1_15M_WINDOW = 60
TRACK4_DAILY_WINDOW = 220

MAX_QUALIFYING_EVENTS = 500

KNOWN_GAP_IV = (
    "Track 4's IV-percentile floor (>=45) is NOT evaluated here — no historical "
    "option-chain/implied-volatility data source exists in this codebase. This "
    "qualification_rate reflects the 200-day EMA/RSI regime gate only, one of two "
    "conditions a fresh cash-secured-put entry requires live (see "
    "track4_income_wheel.py) — real live qualification will be lower than this number."
)
KNOWN_GAP_NO_PNL = (
    "This is a gate-qualification-frequency report, not a trade P&L simulation — "
    "no historical option pricing or fills are modeled."
)


@dataclass
class GateQualificationEvent:
    timestamp: str
    symbol: str
    direction: str | None
    detail: dict


@dataclass
class BacktestResult:
    symbol: str
    track: str
    trades: list[dict] = field(default_factory=list)
    total_pnl: float = 0.0
    win_rate: float = 0.0
    max_drawdown_pct: float = 0.0
    total_bars_evaluated: int = 0
    qualified_count: int = 0
    qualification_rate: float = 0.0
    qualifying_events: list[GateQualificationEvent] = field(default_factory=list)
    qualification_by_month: dict[str, dict] = field(default_factory=dict)
    known_gaps: list[str] = field(default_factory=list)


def _record(result: BacktestResult, ts_iso: str, symbol: str, qualified: bool, direction: str | None, detail: dict) -> None:
    result.total_bars_evaluated += 1
    month_key = ts_iso[:7]
    bucket = result.qualification_by_month.setdefault(month_key, {"evaluated": 0, "qualified": 0})
    bucket["evaluated"] += 1
    if not qualified:
        return
    result.qualified_count += 1
    bucket["qualified"] += 1
    if len(result.qualifying_events) < MAX_QUALIFYING_EVENTS:
        result.qualifying_events.append(GateQualificationEvent(ts_iso, symbol, direction, detail))
    else:
        note = f"qualifying_events truncated at {MAX_QUALIFYING_EVENTS} entries"
        if note not in result.known_gaps:
            result.known_gaps.append(note)


def _ts_iso(value) -> str:
    return value.isoformat() if hasattr(value, "isoformat") else str(value)


def _run_track1(symbol: str, start: dt.datetime, end: dt.datetime, result: BacktestResult) -> None:
    result.known_gaps.append(KNOWN_GAP_NO_PNL)

    buffer_start = start - dt.timedelta(days=10)  # runway so the 15m EMA(50) is seeded before the reporting window starts
    bars_1m = historical_data.load_1m_bars(symbol, start, end)
    bars_15m = historical_data.load_15m_bars(symbol, buffer_start, end)
    historical_data.sleep_between_symbols()

    needed_1m = 21  # matches check_track1_confluence's own max(BREAKOUT_LOOKBACK, RSI_PERIOD, EMA_1M_PERIOD) + 1
    if len(bars_1m) < needed_1m or len(bars_15m) < EMA_TREND_PERIOD:
        result.known_gaps.append(f"insufficient historical bars for {symbol}: {len(bars_1m)} 1m / {len(bars_15m)} 15m bars")
        return

    fifteen_ts = [b["timestamp"] for b in bars_15m]
    j = 0
    for i in range(needed_1m - 1, len(bars_1m)):
        current_ts = bars_1m[i]["timestamp"]
        while j < len(fifteen_ts) and fifteen_ts[j] <= current_ts:
            j += 1
        window_15m = bars_15m[max(0, j - TRACK1_15M_WINDOW):j]
        if len(window_15m) < EMA_TREND_PERIOD:
            continue  # not enough 15m history yet at this point in the replay
        window_1m = bars_1m[max(0, i - TRACK1_1M_WINDOW + 1):i + 1]
        signal = check_track1_confluence(window_1m, window_15m)
        _record(result, _ts_iso(current_ts), symbol, signal["qualified"], signal.get("direction"), dict(signal))


def _run_track4(symbol: str, start: dt.datetime, end: dt.datetime, result: BacktestResult) -> None:
    result.known_gaps.append(KNOWN_GAP_IV)
    result.known_gaps.append(KNOWN_GAP_NO_PNL)

    buffer_start = start - dt.timedelta(days=300)  # runway so the 200-day EMA is seeded before the reporting window starts
    daily_bars = historical_data.load_daily_bars(symbol, buffer_start, end)
    historical_data.sleep_between_symbols()

    if len(daily_bars) < WHEEL_EMA_PERIOD:
        result.known_gaps.append(f"insufficient historical daily bars for {symbol}: {len(daily_bars)}")
        return

    daily_ts = [b["timestamp"] for b in daily_bars]
    start_idx = next((i for i, ts in enumerate(daily_ts) if ts >= start), len(daily_ts))

    for i in range(max(start_idx, WHEEL_EMA_PERIOD - 1), len(daily_bars)):
        window = daily_bars[max(0, i - TRACK4_DAILY_WINDOW + 1):i + 1]
        signal = check_wheel_put_regime(window)
        _record(result, _ts_iso(daily_ts[i]), symbol, signal["qualified"], None, dict(signal))


def run(symbol: str, track: str, start: str, end: str) -> BacktestResult:
    """Replays historical bars through the deterministic entry gate for
    `track` between `start`/`end` (ISO date strings) — see module docstring
    for scope. `trades`/`total_pnl`/`win_rate`/`max_drawdown_pct` stay at
    their zero/empty defaults (no trade simulation); the qualification_*
    fields carry the actual result.
    """
    result = BacktestResult(symbol=symbol, track=track)
    # Bare date strings (e.g. "2026-06-01") parse to naive datetimes, but
    # alpaca-py's bar timestamps are UTC-aware — comparing the two directly
    # raises TypeError, so pin both ends to UTC explicitly.
    start_dt = dt.datetime.fromisoformat(start).replace(tzinfo=dt.timezone.utc)
    end_dt = dt.datetime.fromisoformat(end).replace(tzinfo=dt.timezone.utc)

    # Alpaca's free-tier data plan restricts querying the in-progress
    # (not-yet-closed) trading day as "recent" data — confirmed via a real
    # 403 while building this. Any real backtest window ends well in the
    # past anyway; this just guards the edge case of an end date of "today".
    one_day_ago = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=1)
    if end_dt > one_day_ago:
        result.known_gaps.append(f"end date clamped from {end} to {one_day_ago.date()} — today's still-forming session can't be queried as historical data")
        end_dt = one_day_ago

    if track == "track1_alpha_spreads":
        _run_track1(symbol, start_dt, end_dt, result)
    elif track == "track4_income_wheel":
        _run_track4(symbol, start_dt, end_dt, result)
    else:
        result.known_gaps.append(f"track {track!r} has no deterministic pre-LLM gate wired into this backtest yet")
        return result

    result.qualification_rate = (result.qualified_count / result.total_bars_evaluated) if result.total_bars_evaluated else 0.0
    return result
