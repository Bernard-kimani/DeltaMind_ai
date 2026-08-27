"""Sanity checks for the rewritten app/strategies/track4_income_wheel.py —
IV percentile gate, the new daily-regime gate (CSP only), liquidity/delta/DTE
band filtering, and cost-basis-floored covered call selection. Pure-function,
no Alpaca/DB call needed (propose_order reads everything from the state dict
passed in)."""

import datetime as dt

from app.strategies.track4_income_wheel import IV_PERCENTILE_FLOOR, propose_order

TODAY = dt.date.today()


def _contract(symbol: str, option_type: str, delta: float, dte: int, strike: float,
              bid: float = 1.5, ask: float = 1.6, open_interest: int = 1000, spread_pct: float = 0.02) -> dict:
    return {
        "symbol": symbol,
        "type": option_type,
        "strike_price": strike,
        "expiration_date": TODAY + dt.timedelta(days=dte),
        "bid": bid,
        "ask": ask,
        "open_interest": open_interest,
        "spread_pct": spread_pct,
        "greeks": {"delta": delta},
    }


def _state(chain: list[dict], holds_shares: bool, iv_percentile: float = 60.0,
           regime_qualified: bool = True, cost_basis: float | None = None) -> dict:
    portfolio_risk: dict = {"holds_underlying_shares": holds_shares}
    if cost_basis is not None:
        portfolio_risk["cost_basis"] = cost_basis
    return {
        "symbol": "XYZ",
        "option_chain": chain,
        "iv_percentile": iv_percentile,
        "technical_signal": {"qualified": regime_qualified},
        "portfolio_risk": portfolio_risk,
    }


PUT_CHAIN = [
    _contract("PUT_030D_21DTE", "put", -0.30, 21, strike=95.0),
    _contract("PUT_050D_21DTE", "put", -0.50, 21, strike=90.0),  # wrong delta, same DTE
    _contract("PUT_030D_60DTE", "put", -0.30, 60, strike=95.0),  # right delta, wrong DTE
]

CALL_CHAIN = [
    _contract("CALL_030D_21DTE_STRIKE96", "call", 0.30, 21, strike=96.0),
    _contract("CALL_030D_21DTE_STRIKE90", "call", 0.30, 21, strike=90.0),  # below a cost basis of 93
]


def test_low_iv_percentile_returns_none():
    assert propose_order(_state(PUT_CHAIN, holds_shares=False, iv_percentile=IV_PERCENTILE_FLOOR - 1), {"thesis": "x"}) is None


def test_csp_requires_regime_qualified():
    order = propose_order(_state(PUT_CHAIN, holds_shares=False, regime_qualified=False), {"thesis": "x"})
    assert order is None


def test_csp_selects_030_delta_put_in_dte_window():
    order = propose_order(_state(PUT_CHAIN, holds_shares=False), {"thesis": "elevated IV, healthy pullback"})
    assert order is not None
    assert order["legs"][0]["option_symbol"] == "PUT_030D_21DTE"
    assert order["wheel_leg"] == "cash_secured_put"


def test_csp_dte_outside_14_to_30_window_rejected():
    chain = [_contract("PUT_030D_60DTE_ONLY", "put", -0.30, 60, strike=95.0)]
    assert propose_order(_state(chain, holds_shares=False), {"thesis": "x"}) is None


def test_csp_delta_outside_band_rejected():
    # Nearest available delta (0.50) is outside the accepted [0.25, 0.30] band.
    chain = [_contract("PUT_050D_21DTE_ONLY", "put", -0.50, 21, strike=90.0)]
    assert propose_order(_state(chain, holds_shares=False), {"thesis": "x"}) is None


def test_csp_low_open_interest_filtered_out():
    chain = [_contract("PUT_030D_21DTE_THIN", "put", -0.30, 21, strike=95.0, open_interest=10)]
    assert propose_order(_state(chain, holds_shares=False), {"thesis": "x"}) is None


def test_csp_wide_spread_filtered_out():
    chain = [_contract("PUT_030D_21DTE_WIDE", "put", -0.30, 21, strike=95.0, spread_pct=0.25)]
    assert propose_order(_state(chain, holds_shares=False), {"thesis": "x"}) is None


def test_csp_capital_at_risk_is_strike_times_100():
    order = propose_order(_state(PUT_CHAIN, holds_shares=False), {"thesis": "x"})
    assert order["capital_at_risk"] == 95.0 * 100
    assert order["legs"][0]["strike_price"] == 95.0


def test_covered_call_ignores_regime_gate():
    # regime_qualified=False would block a CSP, but covered calls don't
    # check the regime signal at all per the spec.
    order = propose_order(_state(CALL_CHAIN, holds_shares=True, regime_qualified=False, cost_basis=93.0), {"thesis": "x"})
    assert order is not None
    assert order["wheel_leg"] == "covered_call"


def test_covered_call_floors_strike_at_cost_basis():
    order = propose_order(_state(CALL_CHAIN, holds_shares=True, cost_basis=93.0), {"thesis": "x"})
    assert order is not None
    # The $90 strike is below the $93 cost basis and must be excluded, even
    # though its delta (0.30) is otherwise just as valid as the $96 strike's.
    assert order["legs"][0]["option_symbol"] == "CALL_030D_21DTE_STRIKE96"


def test_covered_call_capital_at_risk_is_zero():
    order = propose_order(_state(CALL_CHAIN, holds_shares=True, cost_basis=93.0), {"thesis": "x"})
    assert order["capital_at_risk"] == 0.0


def test_covered_call_without_recorded_cost_basis_degrades_gracefully():
    # No cost_basis known (e.g. a manually-created position) — don't block
    # trading entirely, just skip the floor filter.
    order = propose_order(_state(CALL_CHAIN, holds_shares=True, cost_basis=None), {"thesis": "x"})
    assert order is not None
