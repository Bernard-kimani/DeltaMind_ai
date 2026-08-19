"""Black-Scholes option pricing. Pure stdlib (math.erf for the normal CDF) —
no scipy dependency, deterministic, unit-testable in isolation from any
brokerage or LLM call, per the hackathon's "buildable pre-hackathon" guidance.
"""

import math
from dataclasses import dataclass


def _norm_cdf(x: float) -> float:
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def _norm_pdf(x: float) -> float:
    return math.exp(-0.5 * x * x) / math.sqrt(2 * math.pi)


@dataclass(frozen=True)
class BSInputs:
    spot: float  # S_t
    strike: float  # K
    time_to_expiry: float  # T - t, in years
    risk_free_rate: float  # r
    volatility: float  # sigma (implied or historical)


def _d1_d2(inputs: BSInputs) -> tuple[float, float]:
    s, k, t, r, sigma = (
        inputs.spot,
        inputs.strike,
        inputs.time_to_expiry,
        inputs.risk_free_rate,
        inputs.volatility,
    )
    if t <= 0 or sigma <= 0:
        raise ValueError("time_to_expiry and volatility must be positive")
    d1 = (math.log(s / k) + (r + sigma**2 / 2) * t) / (sigma * math.sqrt(t))
    d2 = d1 - sigma * math.sqrt(t)
    return d1, d2


def call_price(inputs: BSInputs) -> float:
    d1, d2 = _d1_d2(inputs)
    return inputs.spot * _norm_cdf(d1) - inputs.strike * math.exp(
        -inputs.risk_free_rate * inputs.time_to_expiry
    ) * _norm_cdf(d2)


def put_price(inputs: BSInputs) -> float:
    d1, d2 = _d1_d2(inputs)
    return inputs.strike * math.exp(-inputs.risk_free_rate * inputs.time_to_expiry) * _norm_cdf(
        -d2
    ) - inputs.spot * _norm_cdf(-d1)
