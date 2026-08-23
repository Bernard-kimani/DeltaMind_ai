"""Shared helpers for strategy modules — mostly contract selection by target
delta (and optionally target DTE), since every track's structure boils down
to "pick a leg near delta X, near expiration Y".
"""

from datetime import date


def closest_by_delta(
    option_chain: list[dict], target_delta: float, is_call: bool, target_dte: int | None = None
) -> dict | None:
    """`target_delta` must be signed to match the contract side: positive
    for calls, negative for puts (Track 2/4 already do this; Track 1's
    bear-put branch must too — an unsigned target ranks against put deltas
    in [-1, 0] backwards, favoring near-zero/deep-OTM contracts instead of
    the intended near-the-money ones).

    `target_dte`, if given, first narrows to the single expiration closest
    to that many days out, then ranks by delta within just that expiration —
    otherwise the nearest-delta contract could come from any expiration in
    the fetched window, DTE-blind.
    """
    # `c.get("greeks", {})` doesn't help when the real value is explicitly
    # `None` (vs. absent) — `.get()`'s default only applies to a missing
    # key. Confirmed live: Alpaca's paper/indicative feed returns `greeks:
    # None` for a real fraction of contracts (0 DTE ones especially), so
    # this must be an explicit None-check, not a chained .get().
    candidates = [
        c
        for c in option_chain
        if c.get("type") == ("call" if is_call else "put")
        and c.get("greeks") is not None
        and c["greeks"].get("delta") is not None
    ]
    if not candidates:
        return None

    if target_dte is not None:
        today = date.today()
        expirations = {c["expiration_date"] for c in candidates}
        nearest_expiration = min(expirations, key=lambda exp: abs((exp - today).days - target_dte))
        candidates = [c for c in candidates if c["expiration_date"] == nearest_expiration]
        if not candidates:
            return None

    return min(candidates, key=lambda c: abs(c["greeks"]["delta"] - target_delta))


def estimate_notional(legs: list[dict]) -> float:
    """Gross value of both legs — overstates a spread's true capital-at-risk
    (the net debit). Kept for callers that want a conservative upper bound;
    risk sizing itself should use `net_debit_credit` instead."""
    return sum(abs(leg.get("estimated_cost", 0)) * leg.get("ratio_qty", 1) * 100 for leg in legs)


def net_debit_credit(legs: list[dict]) -> float:
    """Signed net cost of a multi-leg order, dollar-scaled like
    `estimate_notional` (per-share cost x ratio_qty x 100): positive = net
    debit (you pay, e.g. Track 1's spreads), negative = net credit (you
    collect, e.g. Track 4's short premium). This is the real capital-at-risk
    / max-loss figure for a debit spread, and the real premium collected for
    a credit trade — used as the risk gate's `position_notional` (see
    risk_gate.py). For an order's per-share `limit_price`, divide this by
    100 (Alpaca's mleg limit_price convention matches a single option's
    per-share premium, not the dollar total) — see execution.py."""
    signed = 0.0
    for leg in legs:
        cost = leg.get("estimated_cost", 0) * leg.get("ratio_qty", 1) * 100
        signed += cost if leg.get("side") == "buy" else -cost
    return signed
