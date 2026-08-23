"""Track 1: Options Alpha Agents — directional conviction via vertical debit
spreads. Bull call spread: buy an ITM leg (delta ~0.70), sell an OTM leg
(delta ~0.30), same expiration, same side. Bear put spread mirrors this on
the put side. Bounds max loss to the net debit paid.

Entry condition (enforced by lead_architect's thesis, executed here): a
technical breakout signal coinciding with sentiment_score > 0.75 (bullish) or
< -0.75 (bearish). Exit management (50% profit-take / 20% stop-loss on the
spread's net debit) belongs in the live-loop monitor, not this proposal step.
"""

from app.agents.state import AgentState
from app.strategies._common import closest_by_delta, estimate_notional, net_debit_credit

LONG_LEG_DELTA = 0.70
SHORT_LEG_DELTA = 0.30
DTE_TARGET_DAYS = 14
# Matches risk_gate.py's global ceiling (settings.stop_loss_pct, default 0.20)
# — the hackathon brief's suggested 30% would have every order rejected by
# the risk gate as configured. Tightening the strategy to the platform
# ceiling (rather than raising the ceiling itself) keeps the global guardrail
# meaningful for every track, not loosened for this one.
STOP_LOSS_PCT = 0.20
# Read by position_monitor.py's exit sweep. Simplified from the brief's "50%
# of max potential gain" (which needs the spread's strike width, parsed from
# OCC symbols, for one extra layer of precision) to "50% of net debit paid
# back as unrealized profit" — a common, defensible reading of the same
# target that doesn't require reconstructing the spread's geometry.
PROFIT_TAKE_PCT = 0.50


def propose_order(state: AgentState, thesis: str) -> dict | None:
    option_chain = state.get("option_chain", [])
    signal = state.get("technical_signal", {})
    sentiment = state.get("sentiment_score", 0)

    # Both halves of the documented entry condition, not just sentiment —
    # a good-news score with no confirming price/volume breakout (or vice
    # versa) is exactly the noise this AND-gate exists to filter out.
    bullish = sentiment > 0.75 and signal.get("direction") == "up"
    bearish = sentiment < -0.75 and signal.get("direction") == "down"
    if not (bullish or bearish):
        return None

    is_call = bullish  # bearish -> put spread

    # Put deltas are negative — an unsigned target would rank against
    # [-1, 0] backwards (favoring near-zero/deep-OTM puts). Confirmed live
    # 2026-08-24: also confirmed that WITHOUT target_dte, the two legs can
    # land on completely different expirations (one 0 DTE, one 39 DTE in a
    # real test run) — not a valid vertical spread at all. Both fixes are
    # required together, not just the delta sign.
    long_target = LONG_LEG_DELTA if is_call else -LONG_LEG_DELTA
    short_target = SHORT_LEG_DELTA if is_call else -SHORT_LEG_DELTA

    long_leg = closest_by_delta(option_chain, long_target, is_call, target_dte=DTE_TARGET_DAYS)
    short_leg = closest_by_delta(option_chain, short_target, is_call, target_dte=DTE_TARGET_DAYS)
    if not long_leg or not short_leg or long_leg["expiration_date"] != short_leg["expiration_date"]:
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
        # The real capital-at-risk for risk_gate.py's position-size check —
        # a debit spread's max loss is the net debit paid, full stop.
        "capital_at_risk": net_debit_credit(legs),
        "stop_loss_pct": STOP_LOSS_PCT,
        "thesis": thesis,
    }
