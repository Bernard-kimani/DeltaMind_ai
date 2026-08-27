"""Sanity checks for the rewritten app/strategies/track1_alpha_spreads.py —
single-leg 1-2 DTE contract selection, dynamic sizing, and the SL clamp
against risk_gate.py's global ceiling. Pure-function, no Alpaca call needed
(fake chain shaped like rest_client.get_option_chain()'s real flattened
output, including the open_interest/spread_pct fields the liquidity filter
reads)."""

import datetime as dt

from app.config import get_settings
from app.strategies.track1_alpha_spreads import propose_order

TODAY = dt.date.today()
SETTINGS = get_settings()


def _contract(
    symbol: str, option_type: str, delta: float, dte: int,
    bid: float = 1.0, ask: float = 1.2, open_interest: int = 1000, spread_pct: float = 0.02,
) -> dict:
    return {
        "symbol": symbol,
        "type": option_type,
        "expiration_date": TODAY + dt.timedelta(days=dte),
        "bid": bid,
        "ask": ask,
        "open_interest": open_interest,
        "spread_pct": spread_pct,
        "greeks": {"delta": delta},
    }


def _state(chain: list[dict], direction: str | None, equity: float = 100_000.0) -> dict:
    return {
        "symbol": "SPY",
        "option_chain": chain,
        "technical_signal": {"direction": direction},
        "portfolio_risk": {"equity": equity},
    }


BULLISH_CHAIN = [
    _contract("CALL_50D_2DTE", "call", 0.50, 2, ask=1.2),
    _contract("CALL_30D_2DTE", "call", 0.30, 2, ask=0.6),  # wrong delta, same DTE
    _contract("CALL_50D_30DTE", "call", 0.50, 30, ask=3.0),  # right delta, wrong DTE
    _contract("PUT_50D_2DTE", "put", -0.50, 2, ask=1.1),
]


def test_no_direction_returns_none():
    assert propose_order(_state(BULLISH_CHAIN, None), {"thesis": "x"}) is None


def test_bullish_selects_the_2dte_050_delta_call():
    order = propose_order(_state(BULLISH_CHAIN, "up"), {"thesis": "breakout confirmed"})
    assert order is not None
    assert order["legs"][0]["option_symbol"] == "CALL_50D_2DTE"
    assert order["legs"][0]["ratio_qty"] == 1  # always 1 — qty travels via the order-level field
    assert order["direction"] == "up"


def test_bearish_selects_the_put_side():
    order = propose_order(_state(BULLISH_CHAIN, "down"), {"thesis": "breakdown confirmed"})
    assert order is not None
    assert order["legs"][0]["option_symbol"] == "PUT_50D_2DTE"


def test_dte_outside_1_to_2_window_rejected():
    chain = [_contract("CALL_50D_5DTE", "call", 0.50, 5)]  # only a 5 DTE contract exists
    assert propose_order(_state(chain, "up"), {"thesis": "x"}) is None


def test_delta_outside_band_rejected():
    # Nearest available delta (0.30) is outside the accepted [0.45, 0.55] band.
    chain = [_contract("CALL_30D_2DTE", "call", 0.30, 2)]
    assert propose_order(_state(chain, "up"), {"thesis": "x"}) is None


def test_low_open_interest_contract_filtered_out():
    chain = [_contract("CALL_50D_2DTE_THIN", "call", 0.50, 2, open_interest=10)]
    assert propose_order(_state(chain, "up"), {"thesis": "x"}) is None


def test_wide_spread_contract_filtered_out():
    chain = [_contract("CALL_50D_2DTE_WIDE", "call", 0.50, 2, spread_pct=0.25)]
    assert propose_order(_state(chain, "up"), {"thesis": "x"}) is None


def test_qty_sized_to_max_position_pct_of_equity():
    # equity=100,000 * max_position_pct(0.03) = $3,000 budget; ask=1.2 ->
    # $120/contract -> qty = 3000 // 120 = 25.
    order = propose_order(_state(BULLISH_CHAIN, "up", equity=100_000.0), {"thesis": "x"})
    assert order["qty"] == int((100_000.0 * SETTINGS.max_position_pct) // (1.2 * 100))
    assert order["capital_at_risk"] == 1.2 * 100 * order["qty"]


def test_stop_loss_clamped_to_platform_ceiling():
    # LLM proposes a 30% stop (percentage scale) — must clamp down to
    # risk_gate.py's existing global ceiling (settings.stop_loss_pct, 0.20),
    # not the LLM's own suggestion, so the order can never fail that check.
    order = propose_order(_state(BULLISH_CHAIN, "up"), {"thesis": "x", "stop_loss_pct": 30.0})
    assert order["stop_loss_pct"] == SETTINGS.stop_loss_pct


def test_stop_loss_uses_llm_value_when_tighter_than_ceiling():
    order = propose_order(_state(BULLISH_CHAIN, "up"), {"thesis": "x", "stop_loss_pct": 12.0})
    assert order["stop_loss_pct"] == 0.12


def test_fixed_take_profit_tiers_are_not_derived_from_llm():
    order = propose_order(_state(BULLISH_CHAIN, "up"), {"thesis": "x", "take_profit_pct": 999.0})
    assert order["tp1_pct"] == 0.50
    assert order["tp2_pct"] == 1.00


def test_max_hold_minutes_clamped_to_ceiling():
    order = propose_order(_state(BULLISH_CHAIN, "up"), {"thesis": "x", "max_hold_minutes": 500})
    assert order["max_hold_minutes"] == 120


def test_max_hold_minutes_defaults_to_90_when_absent():
    order = propose_order(_state(BULLISH_CHAIN, "up"), {"thesis": "x"})
    assert order["max_hold_minutes"] == 90
