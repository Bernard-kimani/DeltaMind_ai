"""Track 4: Income & Portfolio Overlay Agents — The Wheel.

Sell 14-30 DTE cash-secured puts at ~0.30 delta on liquid, high-IV names.
If assigned, the live-loop monitor (not this proposal step) switches the
position to selling 0.30-delta covered calls until shares are called away.
This module only proposes the opening leg for a fresh cycle; state["track"]
== "track4_income_wheel" combined with an existing equity position (checked
by the live loop) selects the covered-call branch instead.
"""

from app.agents.state import AgentState
from app.strategies._common import closest_by_delta, estimate_notional

CSP_DELTA = 0.30
CC_DELTA = 0.30
STOP_LOSS_PCT = 0.20  # applied to the premium collected, per risk-gate convention


def propose_order(state: AgentState, thesis: str) -> dict | None:
    option_chain = state.get("option_chain", [])
    holds_shares = state.get("portfolio_risk", {}).get("holds_underlying_shares", False)

    if holds_shares:
        leg = closest_by_delta(option_chain, CC_DELTA, is_call=True)
        side_note = "covered_call"
    else:
        leg = closest_by_delta(option_chain, -CSP_DELTA, is_call=False)
        side_note = "cash_secured_put"

    if not leg:
        return None

    legs = [{"side": "sell", "ratio_qty": 1, "option_symbol": leg["symbol"], "estimated_cost": leg["bid"]}]

    return {
        "symbol": state["symbol"],
        "legs": legs,
        "order_type": "limit",
        "time_in_force": "day",
        "estimated_notional": estimate_notional(legs),
        "stop_loss_pct": STOP_LOSS_PCT,
        "wheel_leg": side_note,
        "thesis": thesis,
    }
