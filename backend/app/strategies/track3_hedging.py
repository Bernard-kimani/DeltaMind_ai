"""Track 3: Hedging & Risk Protection Agents — defensive overlay triggered by
portfolio drawdown, not a standalone directional bet.

If portfolio drawdown > 3.5%: buy a 5% OTM put, sell a 3% OTM call
(costless/near-costless collar) on existing equity holdings. Unwind
(propose_unwind) when volatility normalizes and momentum turns positive.
"""

from app.agents.state import AgentState
from app.strategies._common import estimate_notional

DRAWDOWN_TRIGGER_PCT = 0.035
PUT_OTM_PCT = 0.05
CALL_OTM_PCT = 0.03
STOP_LOSS_PCT = 0.20


def propose_order(state: AgentState, thesis: str) -> dict | None:
    drawdown = state.get("portfolio_risk", {}).get("drawdown_pct", 0)
    if drawdown < DRAWDOWN_TRIGGER_PCT:
        return None

    option_chain = state.get("option_chain", [])
    spot = state.get("market_data", {}).get("close")
    if not spot or not option_chain:
        return None

    put_strike_target = spot * (1 - PUT_OTM_PCT)
    call_strike_target = spot * (1 + CALL_OTM_PCT)
    put_leg = _closest_by_strike(option_chain, put_strike_target, is_call=False)
    call_leg = _closest_by_strike(option_chain, call_strike_target, is_call=True)
    if not put_leg or not call_leg:
        return None

    legs = [
        {"side": "buy", "ratio_qty": 1, "option_symbol": put_leg["symbol"], "estimated_cost": put_leg["ask"]},
        {"side": "sell", "ratio_qty": 1, "option_symbol": call_leg["symbol"], "estimated_cost": call_leg["bid"]},
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


def _closest_by_strike(option_chain: list[dict], target_strike: float, is_call: bool) -> dict | None:
    candidates = [c for c in option_chain if c.get("type") == ("call" if is_call else "put")]
    if not candidates:
        return None
    return min(candidates, key=lambda c: abs(c["strike_price"] - target_strike))
