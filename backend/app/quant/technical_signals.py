"""Deterministic technical-breakout detection — pure math, no LLM.

Track 1's documented entry condition is "technical breakout coinciding with
strong sentiment" (see strategies/track1_alpha_spreads.py and the hackathon
brief), but until this module existed, only the sentiment half was actually
implemented — propose_order() had nothing to check for the technical half.
This closes that gap with one deliberately simple, explainable signal (a
single-timeframe SMA breakout + volume confirmation) computed from the same
bars market_ingestion.py already pulls — not the multi-timeframe scanner the
brief describes, which would be harder to justify start-to-finish to a judge
for the marginal benefit in a 7-day window.
"""

from typing import Any, Literal, TypedDict


class BreakoutSignal(TypedDict):
    breakout: bool
    direction: Literal["up", "down"] | None
    price_vs_sma_pct: float
    volume_ratio: float


def detect_breakout(
    bars: list[dict[str, Any]], sma_window: int = 20, volume_lookback: int = 20, volume_ratio_min: float = 1.2
) -> BreakoutSignal:
    """`bars` is oldest-first (as returned by alpaca-py's bars DataFrame),
    each a dict with at least `close` and `volume`."""
    needed = max(sma_window, volume_lookback) + 1
    if len(bars) < needed:
        return {"breakout": False, "direction": None, "price_vs_sma_pct": 0.0, "volume_ratio": 0.0}

    closes = [b["close"] for b in bars]
    volumes = [b["volume"] for b in bars]

    sma = sum(closes[-sma_window:]) / sma_window
    latest_close = closes[-1]
    price_vs_sma_pct = (latest_close - sma) / sma if sma else 0.0

    avg_volume = sum(volumes[-volume_lookback:-1]) / (volume_lookback - 1)
    volume_ratio = volumes[-1] / avg_volume if avg_volume else 0.0
    volume_confirmed = volume_ratio >= volume_ratio_min

    # A close outside the prior range (excluding today) confirms the SMA
    # tilt isn't just drift around a flat line — an actual breakout, not noise.
    prior_high = max(closes[-sma_window:-1])
    prior_low = min(closes[-sma_window:-1])

    direction: Literal["up", "down"] | None = None
    if latest_close > prior_high and price_vs_sma_pct > 0 and volume_confirmed:
        direction = "up"
    elif latest_close < prior_low and price_vs_sma_pct < 0 and volume_confirmed:
        direction = "down"

    return {
        "breakout": direction is not None,
        "direction": direction,
        "price_vs_sma_pct": price_vs_sma_pct,
        "volume_ratio": volume_ratio,
    }


class Track1Confluence(TypedDict):
    qualified: bool
    direction: Literal["up", "down"] | None
    trend_regime: str
    price_vs_15m_ema_pct: float
    price_vs_1m_ema_pct: float
    vwap: float
    price_vs_vwap_pct: float
    rvol: float
    rsi: float


# Track 1's real multi-timeframe entry gate — see docs/tracks/track1_alpha_spreads.md.
# Runs BEFORE any LLM call (see graph.py's conditional edge after quant_engine);
# unlike detect_breakout() above, this is the only signal Track 1 uses.
EMA_TREND_PERIOD = 50  # 15-minute timeframe trend EMA
EMA_1M_PERIOD = 20     # 1-minute timeframe trend EMA — matches the existing 20-bar breakout/RVOL lookback
RSI_PERIOD = 14
BREAKOUT_LOOKBACK = 20
RVOL_LOOKBACK = 20
RVOL_MIN = 1.5
RSI_BULL_BAND = (45.0, 65.0)
RSI_BEAR_BAND = (35.0, 55.0)


def compute_ema(closes: list[float], period: int) -> float | None:
    """Seeded with a plain SMA of the first `period` closes, then rolled
    forward — the standard EMA construction (an unseeded EMA over the whole
    series would be biased by whatever happens to be first)."""
    if len(closes) < period:
        return None
    multiplier = 2 / (period + 1)
    ema = sum(closes[:period]) / period
    for close in closes[period:]:
        ema = (close - ema) * multiplier + ema
    return ema


def compute_rsi(closes: list[float], period: int = RSI_PERIOD) -> float | None:
    """Wilder's smoothing (the standard RSI construction), not a plain
    rolling average of gains/losses."""
    if len(closes) < period + 1:
        return None
    deltas = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
    gains = [d if d > 0 else 0.0 for d in deltas]
    losses = [-d if d < 0 else 0.0 for d in deltas]

    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    for gain, loss in zip(gains[period:], losses[period:]):
        avg_gain = (avg_gain * (period - 1) + gain) / period
        avg_loss = (avg_loss * (period - 1) + loss) / period

    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def compute_vwap(bars: list[dict[str, Any]]) -> float | None:
    """Volume-weighted average price over whatever window of bars is passed
    in (a rolling-window VWAP, not a true session-open-anchored VWAP — this
    module only ever sees the last N bars, not a guaranteed session-start
    alignment; documented as an approximation in docs/tracks/track1_alpha_spreads.md)."""
    if not bars:
        return None
    cum_pv = 0.0
    cum_vol = 0.0
    for b in bars:
        typical = (b["high"] + b["low"] + b["close"]) / 3
        cum_pv += typical * b["volume"]
        cum_vol += b["volume"]
    return cum_pv / cum_vol if cum_vol else None


def compute_rvol(volumes: list[float], lookback: int = RVOL_LOOKBACK) -> float | None:
    """Latest bar's volume vs. the average of the prior `lookback` bars
    (excluding the latest) — same "average excludes current bar" convention
    as detect_breakout()'s volume_ratio, for consistency."""
    if len(volumes) < lookback + 1:
        return None
    avg = sum(volumes[-(lookback + 1):-1]) / lookback
    return volumes[-1] / avg if avg else None


class WheelRegime(TypedDict):
    qualified: bool
    price_vs_200ema_pct: float
    rsi: float


# Track 4's regime gate for new cash-secured-put entries only (covered
# calls don't need a technical filter, just a cost-basis floor — see
# strategies/track4_income_wheel.py). Daily bars, not Track 1's 1m/15m —
# the Wheel operates on a multi-week holding horizon, not intraday.
WHEEL_EMA_PERIOD = 200
WHEEL_RSI_BAND = (35.0, 55.0)


def check_wheel_put_regime(daily_bars: list[dict[str, Any]]) -> WheelRegime:
    """Price > 200-day EMA (avoid selling puts into a structural downtrend
    — a "falling knife") AND RSI(14) in [35, 55] (an oversold pullback
    within an uptrend, not a freefall) — see docs/tracks/track4_income_wheel.md."""
    empty: WheelRegime = {"qualified": False, "price_vs_200ema_pct": 0.0, "rsi": 0.0}
    if len(daily_bars) < WHEEL_EMA_PERIOD:
        return empty

    closes = [b["close"] for b in daily_bars]
    ema_200 = compute_ema(closes, WHEEL_EMA_PERIOD)
    rsi = compute_rsi(closes, RSI_PERIOD)
    if ema_200 is None or rsi is None:
        return empty

    latest_close = closes[-1]
    price_vs_200ema_pct = (latest_close - ema_200) / ema_200 if ema_200 else 0.0
    qualified = latest_close > ema_200 and WHEEL_RSI_BAND[0] <= rsi <= WHEEL_RSI_BAND[1]

    return {"qualified": qualified, "price_vs_200ema_pct": price_vs_200ema_pct, "rsi": rsi}


def check_track1_confluence(bars_1m: list[dict[str, Any]], bars_15m: list[dict[str, Any]]) -> Track1Confluence:
    """Track 1's full entry gate: 15m EMA(50) trend AND 1m EMA(20) trend
    (both timeframes' EMAs must agree with price direction — not just the
    higher one) + 1m VWAP position + 1m RSI(14) in-band + 1m 20-bar
    breakout + RVOL >= 1.5, all agreeing on the same direction. `bars_15m`
    must be native 15-minute bars (see alpaca/rest_client.get_15m_bars) —
    resampling from only ~500 1-minute bars can't seed a stable 50-period
    EMA (yields ~33 complete 15m candles, well short of 50)."""
    empty: Track1Confluence = {
        "qualified": False, "direction": None, "trend_regime": "unknown",
        "price_vs_15m_ema_pct": 0.0, "price_vs_1m_ema_pct": 0.0,
        "vwap": 0.0, "price_vs_vwap_pct": 0.0, "rvol": 0.0, "rsi": 0.0,
    }
    needed_1m = max(BREAKOUT_LOOKBACK, RSI_PERIOD, EMA_1M_PERIOD) + 1
    if len(bars_1m) < needed_1m or len(bars_15m) < EMA_TREND_PERIOD:
        return empty

    closes_1m = [b["close"] for b in bars_1m]
    latest_close = closes_1m[-1]

    ema_15m = compute_ema([b["close"] for b in bars_15m], EMA_TREND_PERIOD)
    ema_1m = compute_ema(closes_1m, EMA_1M_PERIOD)
    if ema_15m is None or ema_1m is None:
        return empty
    price_vs_15m_ema_pct = (latest_close - ema_15m) / ema_15m if ema_15m else 0.0
    price_vs_1m_ema_pct = (latest_close - ema_1m) / ema_1m if ema_1m else 0.0
    trend_regime = "bullish" if latest_close > ema_15m else "bearish"

    vwap = compute_vwap(bars_1m)
    price_vs_vwap_pct = (latest_close - vwap) / vwap if vwap else 0.0

    rsi = compute_rsi(closes_1m) or 50.0
    rvol = compute_rvol([b["volume"] for b in bars_1m]) or 0.0

    prior_window = closes_1m[-(BREAKOUT_LOOKBACK + 1):-1]
    prior_high, prior_low = max(prior_window), min(prior_window)

    bullish = (
        latest_close > ema_15m and latest_close > ema_1m
        and vwap is not None and latest_close > vwap
        and RSI_BULL_BAND[0] <= rsi <= RSI_BULL_BAND[1]
        and latest_close > prior_high and rvol >= RVOL_MIN
    )
    bearish = (
        latest_close < ema_15m and latest_close < ema_1m
        and vwap is not None and latest_close < vwap
        and RSI_BEAR_BAND[0] <= rsi <= RSI_BEAR_BAND[1]
        and latest_close < prior_low and rvol >= RVOL_MIN
    )
    direction: Literal["up", "down"] | None = "up" if bullish else "down" if bearish else None

    return {
        "qualified": direction is not None,
        "direction": direction,
        "trend_regime": trend_regime,
        "price_vs_15m_ema_pct": price_vs_15m_ema_pct,
        "price_vs_1m_ema_pct": price_vs_1m_ema_pct,
        "vwap": vwap or 0.0,
        "price_vs_vwap_pct": price_vs_vwap_pct,
        "rvol": rvol,
        "rsi": rsi,
    }


class MomentumSwingConfluence(TypedDict):
    qualified: bool
    direction: Literal["up", "down"] | None
    price_vs_1h_ema_pct: float
    price_vs_5m_ema_pct: float


# Track 5 ("momentum swing"): a deliberately thin gate compared to Track 1's
# five-factor stack above (no VWAP, no RSI band, no RVOL, no breakout
# lookback) -- two conditions only: (1) the 1-hour 50-EMA sets trend
# direction, (2) a genuine 5-minute EMA(20) crossover EVENT (not just
# "currently above/below", an actual crossing between the previous and
# latest bar) in that same direction is the entry trigger. Deliberately
# loose on purpose (see strategies/track5_momentum_swing.py's module
# docstring) -- the goal is to push more candidates to the LLM validator for
# a real decision, not filter almost everything out deterministically the
# way Track 1's gate does.
EMA_1H_TREND_PERIOD = 50
EMA_5M_PERIOD = 20


def check_momentum_swing_confluence(bars_5m: list[dict[str, Any]], bars_1h: list[dict[str, Any]]) -> MomentumSwingConfluence:
    """`bars_1h` must be native 1-hour bars (see alpaca/rest_client.get_1h_bars)
    — same "native, not resampled" precedent as check_track1_confluence's
    15m leg. `bars_5m` needs one extra bar beyond EMA_5M_PERIOD's own warmup
    so the crossover check has both the previous and latest bar's EMA to
    compare (computed by re-running compute_ema over two slices, not a full
    rolling series — compute_ema only ever returns the final value of
    whatever closes list it's given, so calling it twice over
    closes_5m[:-1] and closes_5m is the direct way to get "yesterday's" and
    "today's" EMA)."""
    empty: MomentumSwingConfluence = {
        "qualified": False, "direction": None, "price_vs_1h_ema_pct": 0.0, "price_vs_5m_ema_pct": 0.0,
    }
    if len(bars_5m) < EMA_5M_PERIOD + 2 or len(bars_1h) < EMA_1H_TREND_PERIOD:
        return empty

    closes_5m = [b["close"] for b in bars_5m]
    closes_1h = [b["close"] for b in bars_1h]
    latest_close = closes_5m[-1]
    prev_close = closes_5m[-2]

    ema_1h = compute_ema(closes_1h, EMA_1H_TREND_PERIOD)
    ema_5m_latest = compute_ema(closes_5m, EMA_5M_PERIOD)
    ema_5m_prev = compute_ema(closes_5m[:-1], EMA_5M_PERIOD)
    if ema_1h is None or ema_5m_latest is None or ema_5m_prev is None:
        return empty

    price_vs_1h_ema_pct = (latest_close - ema_1h) / ema_1h if ema_1h else 0.0
    price_vs_5m_ema_pct = (latest_close - ema_5m_latest) / ema_5m_latest if ema_5m_latest else 0.0

    trend_up = latest_close > ema_1h
    trend_down = latest_close < ema_1h
    crossed_up = prev_close <= ema_5m_prev and latest_close > ema_5m_latest
    crossed_down = prev_close >= ema_5m_prev and latest_close < ema_5m_latest

    direction: Literal["up", "down"] | None = (
        "up" if (trend_up and crossed_up) else "down" if (trend_down and crossed_down) else None
    )

    return {
        "qualified": direction is not None,
        "direction": direction,
        "price_vs_1h_ema_pct": price_vs_1h_ema_pct,
        "price_vs_5m_ema_pct": price_vs_5m_ema_pct,
    }
