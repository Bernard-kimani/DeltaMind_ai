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


def detect_breakout(bars: list[dict[str, Any]], sma_window: int = 20, volume_lookback: int = 20) -> BreakoutSignal:
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
    volume_confirmed = volume_ratio >= 1.5

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
