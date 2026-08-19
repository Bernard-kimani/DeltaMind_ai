"""Track 1: Options Alpha Agents — directional conviction via vertical debit
spreads. Buy an ITM leg (delta ~0.70), sell an OTM leg (delta ~0.30) on the
same side, bounding max loss to the net debit paid.

Entry condition (enforced by lead_architect's thesis, executed here): a
technical breakout signal coinciding with sentiment_score > 0.75 (bullish) or
< -0.75 (bearish). Exit management (50% profit-take / 30% stop-loss on the
spread's net debit) belongs in the live-loop monitor, not this proposal step.
"""

from app.agents.state import AgentState
from app.strategies._common import closest_by_delta, estimate_notional

LONG_LEG_DELTA = 0.70
SHORT_LEG_DELTA = 0.30
DTE_TARGET_DAYS = 14
STOP_LOSS_PCT = 0.30


def propose_order(state: AgentState, thesis: str) -> dict | None:
    option_chain = state.get("option_chain", [])
    bullish = state.get("sentiment_score", 0) > 0.75
    bearish = state.get("sentiment_score", 0) < -0.75
    if not (bullish or bearish):
        return None

    is_call = bullish
    long_leg = closest_by_delta(option_chain, LONG_LEG_DELTA, is_call)
    short_leg = closest_by_delta(option_chain, SHORT_LEG_DELTA, is_call)
    if not long_leg or not short_leg:
        return None

    legs = [
        {"side": "buy", "ratio_qty": 1, "option_symbol": long_leg["symbol"], "estimated_cost": long_leg["ask"]},
        {"side": "sell", "ratio_qty": 1, "option_symbol": short_leg["symbol"], "estimated_cost": short_leg["bid"]},
    ]

    return {
        "symbol": state["symbol"],
        "legs": legs,
        "order_type": "limit",
        "time_in_force": "day",
        "estimated_notional": estimate_notional(legs),
        "stop_loss_pct": STOP_LOSS_PCT,
        "thesis": thesis,
    }
