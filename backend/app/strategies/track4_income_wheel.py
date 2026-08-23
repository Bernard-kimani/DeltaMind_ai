"""Track 4: Income & Portfolio Overlay Agents — The Wheel.

Sell ~21 DTE cash-secured puts at ~0.30 delta on liquid, high-IV names.
If assigned, position_monitor.py's sweep detects the resulting equity
position and flips wheel_state so the next cycle sells 0.30-delta covered
calls instead, until shares are called away. This module only proposes the
opening leg for a fresh cycle.
"""

from app.agents.state import AgentState
from app.strategies._common import closest_by_delta, estimate_notional

CSP_DELTA = 0.30
CC_DELTA = 0.30
# Single point estimate for the brief's 14-30 DTE range — closest_by_delta
# picks the nearest single expiration to one target, not a range; a true
# range filter would need a different (small) change to that helper if this
# ever needs to be a real band instead of a point.
DTE_TARGET_DAYS = 21
# "Elevated IV" per the hackathon brief, made concrete: only sell premium
# when IV percentile is at/above the median. Selling options on a low-IV
# name collects a thin premium for the same assignment risk.
IV_PERCENTILE_FLOOR = 50
STOP_LOSS_PCT = 0.20  # applied to the premium collected, per risk-gate convention


def propose_order(state: AgentState, thesis: str) -> dict | None:
    if state.get("iv_percentile", 0) < IV_PERCENTILE_FLOOR:
        return None

    option_chain = state.get("option_chain", [])
    holds_shares = state.get("portfolio_risk", {}).get("holds_underlying_shares", False)

    if holds_shares:
        leg = closest_by_delta(option_chain, CC_DELTA, is_call=True, target_dte=DTE_TARGET_DAYS)
        side_note = "covered_call"
        # Shares are already owned (already counted in existing position
        # sizing elsewhere) — selling a call against them commits no new
        # capital, unlike a cash-secured put.
        capital_at_risk = 0.0
    else:
        leg = closest_by_delta(option_chain, -CSP_DELTA, is_call=False, target_dte=DTE_TARGET_DAYS)
        side_note = "cash_secured_put"
        # The real capital commitment is the cash secured against
        # assignment (strike x 100), NOT the small premium collected —
        # using premium alone would let risk_gate.py's position-size check
        # pass almost any CSP regardless of strike price.
        capital_at_risk = leg["strike_price"] * 100 if leg else 0.0

    if not leg:
        return None

    legs = [{"side": "sell", "ratio_qty": 1, "option_symbol": leg["symbol"], "estimated_cost": leg["bid"]}]

    return {
        "symbol": state["symbol"],
        "legs": legs,
        "order_type": "limit",
        "time_in_force": "day",
        "estimated_notional": estimate_notional(legs),
        "capital_at_risk": capital_at_risk,
        "stop_loss_pct": STOP_LOSS_PCT,
        "wheel_leg": side_note,
        "thesis": thesis,
    }
