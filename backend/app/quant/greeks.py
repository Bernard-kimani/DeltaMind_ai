"""Option Greeks (Delta, Gamma, Vega, Theta, Rho) derived analytically from
Black-Scholes. Used by quant_engine.py to annotate the option chain before
the Lead Architect reasons about it, and by risk_metrics.py for portfolio
beta-weighted delta.
"""

import math

from app.quant.black_scholes import BSInputs, _d1_d2, _norm_cdf, _norm_pdf


def delta(inputs: BSInputs, is_call: bool) -> float:
    d1, _ = _d1_d2(inputs)
    return _norm_cdf(d1) if is_call else _norm_cdf(d1) - 1


def gamma(inputs: BSInputs) -> float:
    d1, _ = _d1_d2(inputs)
    return _norm_pdf(d1) / (inputs.spot * inputs.volatility * math.sqrt(inputs.time_to_expiry))


def vega(inputs: BSInputs) -> float:
    """Per 1.00 (100%) change in IV. Divide by 100 for the conventional 'per 1 vol point' quote."""
    d1, _ = _d1_d2(inputs)
    return inputs.spot * _norm_pdf(d1) * math.sqrt(inputs.time_to_expiry)


def theta(inputs: BSInputs, is_call: bool) -> float:
    """Per year. Divide by 365 for daily theta decay."""
    d1, d2 = _d1_d2(inputs)
    s, k, t, r, sigma = (
        inputs.spot,
        inputs.strike,
        inputs.time_to_expiry,
        inputs.risk_free_rate,
        inputs.volatility,
    )
    term1 = -(s * _norm_pdf(d1) * sigma) / (2 * math.sqrt(t))
    if is_call:
        term2 = -r * k * math.exp(-r * t) * _norm_cdf(d2)
    else:
        term2 = r * k * math.exp(-r * t) * _norm_cdf(-d2)
    return term1 + term2


def rho(inputs: BSInputs, is_call: bool) -> float:
    """Per 1.00 (100%) change in rates."""
    _, d2 = _d1_d2(inputs)
    k, t, r = inputs.strike, inputs.time_to_expiry, inputs.risk_free_rate
    sign = 1 if is_call else -1
    cdf_arg = d2 if is_call else -d2
    return sign * k * t * math.exp(-r * t) * _norm_cdf(cdf_arg)


def compute_greeks(option_chain: list[dict]) -> dict[str, float]:
    """Aggregate/portfolio-level Greeks from a list of option snapshots.

    Each item in `option_chain` is expected to already carry the fields
    produced by app.alpaca.rest_client.get_option_chain(); this function is
    intentionally forgiving (skips malformed entries) since it runs inside
    the live agent loop where a single bad snapshot shouldn't halt the cycle.
    """
    totals = {"delta": 0.0, "gamma": 0.0, "vega": 0.0, "theta": 0.0, "rho": 0.0}
    for snapshot in option_chain:
        greeks = snapshot.get("greeks")
        if not greeks:
            continue
        for key in totals:
            totals[key] += greeks.get(key, 0.0)
    return totals
