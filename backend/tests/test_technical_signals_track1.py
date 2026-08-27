"""Sanity checks for the Track 1 confluence screener additions to
app/quant/technical_signals.py — pure functions, no Alpaca call needed.
Expected numeric values below were confirmed by running the actual
functions against this data, not hand-derived, since RSI/VWAP interact in
ways that aren't obvious to eyeball.
"""

from app.quant.technical_signals import check_track1_confluence, compute_ema, compute_rsi, compute_rvol, compute_vwap


def _bar(close: float, volume: float = 1000) -> dict:
    return {"close": close, "volume": volume, "high": close, "low": close}


def test_compute_ema_flat_series_equals_the_flat_value():
    assert compute_ema([100.0] * 60, 50) == 100.0


def test_compute_ema_insufficient_data_returns_none():
    assert compute_ema([100.0] * 10, 50) is None


def test_compute_rsi_all_gains_is_100():
    closes = [100.0 + i for i in range(20)]  # strictly increasing
    assert compute_rsi(closes, 14) == 100.0


def test_compute_rsi_all_losses_is_0():
    closes = [100.0 - i for i in range(20)]  # strictly decreasing
    assert compute_rsi(closes, 14) == 0.0


def test_compute_rsi_insufficient_data_returns_none():
    assert compute_rsi([100.0] * 5, 14) is None


def test_compute_vwap_flat_bars_equals_the_flat_price():
    assert compute_vwap([_bar(100.0, volume=500) for _ in range(10)]) == 100.0


def test_compute_vwap_empty_returns_none():
    assert compute_vwap([]) is None


def test_compute_rvol_latest_spike_above_average():
    volumes = [1000] * 20 + [3000]
    assert compute_rvol(volumes, lookback=20) == 3.0


def test_compute_rvol_insufficient_data_returns_none():
    assert compute_rvol([1000] * 5, lookback=20) is None


def test_check_track1_confluence_insufficient_bars_not_qualified():
    result = check_track1_confluence(bars_1m=[_bar(100.0)] * 5, bars_15m=[_bar(100.0)] * 5)
    assert result["qualified"] is False
    assert result["direction"] is None


def _bullish_bars() -> tuple[list[dict], list[dict]]:
    # Alternating 100/99 closes keep RSI mid-band (~57) instead of pegging
    # at 100/0 the way an all-one-direction series would; the final bar
    # breaks above the prior 20-bar high (100) with a 5x volume spike. The
    # alternating pattern also keeps the 1m EMA(20) below the breakout
    # price, so both timeframes' EMAs agree bullish, not just the 15m one.
    closes_1m = [100.0 if i % 2 == 0 else 99.0 for i in range(24)] + [102.0]
    bars_1m = [_bar(c, volume=1000) for c in closes_1m[:-1]] + [_bar(102.0, volume=5000)]
    # 15m bars trending up so the 50-EMA (~93.4) sits well below the 1m
    # breakout price (102), confirming the bullish trend regime.
    bars_15m = [_bar(90.0 + i * 0.1, volume=1000) for i in range(60)]
    return bars_1m, bars_15m


def test_check_track1_confluence_bullish_setup_qualifies():
    bars_1m, bars_15m = _bullish_bars()
    result = check_track1_confluence(bars_1m, bars_15m)
    assert result["qualified"] is True
    assert result["direction"] == "up"
    assert result["trend_regime"] == "bullish"
    assert 45.0 <= result["rsi"] <= 65.0
    assert result["rvol"] >= 1.5
    assert result["price_vs_15m_ema_pct"] > 0
    assert result["price_vs_1m_ema_pct"] > 0


def test_check_track1_confluence_15m_ema_disagreement_does_not_qualify():
    # Same qualifying 1m data as _bullish_bars() (RSI in band, breakout,
    # RVOL spike, 1m EMA agrees) — but bars_15m now trends DOWN instead of
    # up, so the 15m EMA sits above price and disagrees. Confirms both
    # timeframes' EMAs are independently required, not just whichever one
    # happens to be checked first.
    #
    # (A same-shaped test flipping only the 1m EMA in isolation isn't
    # practical to hand-construct: RSI/VWAP/breakout/RVOL are all derived
    # from the same closes_1m series as the 1m EMA, so nudging one lagging
    # indicator against the setup tends to drag the others with it. The 1m
    # side is covered instead by the qualifying test above — it asserts
    # price_vs_1m_ema_pct > 0 — plus direct inspection of the `and
    # latest_close > ema_1m` term in check_track1_confluence's source.)
    bars_1m, _ = _bullish_bars()
    bars_15m_declining = [_bar(150.0 - i * 0.5, volume=1000) for i in range(60)]

    result = check_track1_confluence(bars_1m, bars_15m_declining)
    assert result["price_vs_15m_ema_pct"] < 0  # 15m EMA now disagrees
    assert result["price_vs_1m_ema_pct"] > 0   # 1m side still agrees bullish
    assert result["qualified"] is False


def test_check_track1_confluence_no_volume_spike_does_not_qualify():
    # Same breakout, but no RVOL confirmation (all bars equal volume) — the
    # RVOL gate alone should be enough to withhold qualification.
    closes_1m = [100.0 if i % 2 == 0 else 99.0 for i in range(24)] + [102.0]
    bars_1m = [_bar(c, volume=1000) for c in closes_1m]
    bars_15m = [_bar(90.0 + i * 0.1, volume=1000) for i in range(60)]

    result = check_track1_confluence(bars_1m, bars_15m)
    assert result["qualified"] is False
    assert result["direction"] is None
    assert result["rvol"] < 1.5
