"""Sanity checks for the pure-math pricing/Greeks module — the one piece of
the stack that's fully buildable and testable pre-hackathon (no brokerage or
LLM dependency).
"""

from app.quant.black_scholes import BSInputs, call_price, put_price
from app.quant.greeks import delta

ATM = BSInputs(spot=100, strike=100, time_to_expiry=30 / 365, risk_free_rate=0.05, volatility=0.25)


def test_call_price_positive():
    assert call_price(ATM) > 0


def test_put_call_parity():
    # C - P = S - K*e^(-rT)
    import math

    c = call_price(ATM)
    p = put_price(ATM)
    expected = ATM.spot - ATM.strike * math.exp(-ATM.risk_free_rate * ATM.time_to_expiry)
    assert abs((c - p) - expected) < 1e-6


def test_atm_call_delta_near_half():
    d = delta(ATM, is_call=True)
    assert 0.4 < d < 0.7  # ATM call delta skews slightly above 0.5 with positive drift
