"""Sanity checks for app/strategies/_common.py — pure-function, no Alpaca
call needed. Covers the closest_by_delta bug fix (DTE-blindness, put-delta
sign) and the new net_debit_credit helper, using a hand-built fake chain
shaped like rest_client.get_option_chain()'s real flattened output.
"""

import datetime as dt

from app.strategies._common import closest_by_delta, estimate_notional, net_debit_credit

TODAY = dt.date.today()


def _contract(symbol: str, option_type: str, delta: float, dte: int) -> dict:
    return {
        "symbol": symbol,
        "type": option_type,
        "expiration_date": TODAY + dt.timedelta(days=dte),
        "bid": 1.0,
        "ask": 1.2,
        "greeks": {"delta": delta},
    }


CHAIN = [
    _contract("CALL_70D_14DTE", "call", 0.70, 14),
    _contract("CALL_30D_14DTE", "call", 0.30, 14),
    _contract("CALL_70D_45DTE", "call", 0.70, 45),  # same delta, wrong expiration
    _contract("PUT_70D_14DTE", "put", -0.70, 14),
    _contract("PUT_30D_14DTE", "put", -0.30, 14),
]


def test_closest_by_delta_filters_by_type():
    leg = closest_by_delta(CHAIN, 0.70, is_call=True)
    assert leg["symbol"].startswith("CALL_")


def test_closest_by_delta_never_crosses_type():
    # A put's delta (-0.70) is numerically far from a 0.70 call target, so
    # this wouldn't catch a broken filter by accident — it only passes if
    # the type filter is genuinely still being applied.
    leg = closest_by_delta(CHAIN, 0.70, is_call=True)
    assert leg["type"] == "call"


def test_closest_by_delta_empty_chain_returns_none():
    assert closest_by_delta([], 0.70, is_call=True) is None


def test_closest_by_delta_respects_target_dte():
    # Without target_dte, delta alone could pick either 14 or 45 DTE contract
    # (both are exactly 0.70) — with it, only the 14 DTE one should qualify.
    leg = closest_by_delta(CHAIN, 0.70, is_call=True, target_dte=14)
    assert leg["symbol"] == "CALL_70D_14DTE"

    leg_far = closest_by_delta(CHAIN, 0.70, is_call=True, target_dte=45)
    assert leg_far["symbol"] == "CALL_70D_45DTE"


def test_closest_by_delta_put_requires_signed_target():
    # This is the sign-bug regression test: an unsigned 0.70 target against
    # put deltas in [-1, 0] should NOT select the near-the-money -0.70 put —
    # it should be closer to -0.30 (|-0.30 - 0.70| < |-0.70 - 0.70|).
    wrong_leg = closest_by_delta(CHAIN, 0.70, is_call=False)
    assert wrong_leg["symbol"] == "PUT_30D_14DTE"

    # The correct call: a signed negative target selects the intended
    # near-the-money put.
    right_leg = closest_by_delta(CHAIN, -0.70, is_call=False)
    assert right_leg["symbol"] == "PUT_70D_14DTE"


def test_net_debit_credit_debit_spread():
    # Buy the more expensive leg, sell the cheaper one -> net debit (positive).
    legs = [
        {"side": "buy", "ratio_qty": 1, "estimated_cost": 3.00},
        {"side": "sell", "ratio_qty": 1, "estimated_cost": 1.20},
    ]
    assert net_debit_credit(legs) == (3.00 - 1.20) * 100


def test_net_debit_credit_credit_trade():
    # Selling only (Track 4's CSP/covered call) -> net credit (negative).
    legs = [{"side": "sell", "ratio_qty": 1, "estimated_cost": 1.50}]
    assert net_debit_credit(legs) == -1.50 * 100


def test_estimate_notional_unchanged():
    legs = [
        {"side": "buy", "ratio_qty": 1, "estimated_cost": 3.00},
        {"side": "sell", "ratio_qty": 1, "estimated_cost": 1.20},
    ]
    assert estimate_notional(legs) == (3.00 + 1.20) * 100
