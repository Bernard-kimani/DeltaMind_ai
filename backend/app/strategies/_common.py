"""Shared helpers for strategy modules — mostly contract selection by target
delta, since every track's structure boils down to "pick a leg near delta X".
"""


def closest_by_delta(option_chain: list[dict], target_delta: float, is_call: bool) -> dict | None:
    candidates = [
        c
        for c in option_chain
        if c.get("type") == ("call" if is_call else "put") and c.get("greeks", {}).get("delta") is not None
    ]
    if not candidates:
        return None
    return min(candidates, key=lambda c: abs(c["greeks"]["delta"] - target_delta))


def estimate_notional(legs: list[dict]) -> float:
    return sum(abs(leg.get("estimated_cost", 0)) * leg.get("ratio_qty", 1) * 100 for leg in legs)
