"""Track 2: Volatility & Event Trading Agents — trade IV shifts around
scheduled events, not price direction.

  IV_percentile < 25  (pre-earnings)  -> long strangle (buy cheap vol, OTM
                                          call + OTM put)
  IV_percentile > 85  (pre-earnings)  -> iron condor (sell rich vol, capture
                                          post-event IV crush)
"""

from app.agents.state import AgentState
from app.strategies._common import closest_by_delta, estimate_notional

STRANGLE_DELTA = 0.25
CONDOR_SHORT_DELTA = 0.20
CONDOR_LONG_DELTA = 0.10
IV_LOW_THRESHOLD = 25
IV_HIGH_THRESHOLD = 85
STOP_LOSS_PCT = 0.30


def propose_order(state: AgentState, thesis: str) -> dict | None:
    option_chain = state.get("option_chain", [])
    iv_p = state.get("iv_percentile", 50)

    if iv_p < IV_LOW_THRESHOLD:
        legs = _long_strangle_legs(option_chain)
    elif iv_p > IV_HIGH_THRESHOLD:
        legs = _iron_condor_legs(option_chain)
    else:
        return None

    if not legs:
        return None

    return {
        "symbol": state["symbol"],
        "legs": legs,
        "order_type": "limit",
        "time_in_force": "day",
        "estimated_notional": estimate_notional(legs),
        "stop_loss_pct": STOP_LOSS_PCT,
        "thesis": thesis,
    }


def _long_strangle_legs(option_chain: list[dict]) -> list[dict] | None:
    call = closest_by_delta(option_chain, STRANGLE_DELTA, is_call=True)
    put = closest_by_delta(option_chain, -STRANGLE_DELTA, is_call=False)
    if not call or not put:
        return None
    return [
        {"side": "buy", "ratio_qty": 1, "option_symbol": call["symbol"], "estimated_cost": call["ask"]},
        {"side": "buy", "ratio_qty": 1, "option_symbol": put["symbol"], "estimated_cost": put["ask"]},
    ]


def _iron_condor_legs(option_chain: list[dict]) -> list[dict] | None:
    short_call = closest_by_delta(option_chain, CONDOR_SHORT_DELTA, is_call=True)
    long_call = closest_by_delta(option_chain, CONDOR_LONG_DELTA, is_call=True)
    short_put = closest_by_delta(option_chain, -CONDOR_SHORT_DELTA, is_call=False)
    long_put = closest_by_delta(option_chain, -CONDOR_LONG_DELTA, is_call=False)
    if not all([short_call, long_call, short_put, long_put]):
        return None
    return [
        {"side": "sell", "ratio_qty": 1, "option_symbol": short_call["symbol"], "estimated_cost": short_call["bid"]},
        {"side": "buy", "ratio_qty": 1, "option_symbol": long_call["symbol"], "estimated_cost": long_call["ask"]},
        {"side": "sell", "ratio_qty": 1, "option_symbol": short_put["symbol"], "estimated_cost": short_put["bid"]},
        {"side": "buy", "ratio_qty": 1, "option_symbol": long_put["symbol"], "estimated_cost": long_put["ask"]},
    ]
