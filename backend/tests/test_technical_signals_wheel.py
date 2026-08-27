"""Sanity checks for Track 4's daily-bar regime gate
(app/quant/technical_signals.check_wheel_put_regime) — pure function, no
Alpaca call needed."""

from app.quant.technical_signals import WHEEL_EMA_PERIOD, check_wheel_put_regime


def _bar(close: float) -> dict:
    return {"close": close, "volume": 1000, "high": close, "low": close}


def test_insufficient_bars_not_qualified():
    result = check_wheel_put_regime([_bar(100.0)] * 5)
    assert result["qualified"] is False


def test_uptrend_with_midband_rsi_qualifies():
    # A slow uptrend (keeps price above its own lagging 200-EMA) with a much
    # larger alternating wobble on top (keeps the gain/loss ratio close to
    # 1, so RSI lands mid-band instead of pegging toward 100 the way a pure
    # monotonic increase would — confirmed by running the actual function
    # against this data, not hand-derived).
    closes = [90.0 + i * 0.05 + (0.5 if i % 2 == 0 else -0.5) for i in range(WHEEL_EMA_PERIOD + 20)]
    result = check_wheel_put_regime([_bar(c) for c in closes])
    assert result["qualified"] is True
    assert result["price_vs_200ema_pct"] > 0
    assert 35.0 <= result["rsi"] <= 55.0


def test_downtrend_below_200ema_rejected():
    closes = [150.0 - i * 0.3 for i in range(WHEEL_EMA_PERIOD + 20)]
    result = check_wheel_put_regime([_bar(c) for c in closes])
    assert result["price_vs_200ema_pct"] < 0
    assert result["qualified"] is False


def test_rsi_outside_band_rejected():
    # Strong, near-monotonic uptrend: price stays comfortably above its
    # 200-EMA, but RSI pegs near 100 — outside the [35, 55] band.
    closes = [90.0 + i * 1.0 for i in range(WHEEL_EMA_PERIOD + 20)]
    result = check_wheel_put_regime([_bar(c) for c in closes])
    assert result["price_vs_200ema_pct"] > 0
    assert result["rsi"] > 55.0
    assert result["qualified"] is False
