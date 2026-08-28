"""Execution Specialist Node.

Only reached when state["risk_approved"] is True (see graph.py's conditional
edge). Dispatches the validated multi-leg option order via the Alpaca MCP
client and persists the fill/order result for the dashboard's trade log.

Confirmed bug fixed here: this used to call `place_option_order(order)` with
a single dict, but the real function takes separate symbol/legs/... keyword
arguments with `legs` required — unreachable until the option-chain data
layer fix (rest_client.py) made it possible for a real order to ever exist
in the first place. Also translates each leg's `option_symbol` (the
strategy modules' internal key) to the `symbol` key `mcp_client.OptionLeg`
actually expects, and derives the order's per-share `limit_price` from
`net_debit_credit` rather than requiring each strategy module to compute it.
"""

from app.agents.state import AgentState
from app.alpaca.mcp_client import OptionLeg, place_option_order
from app.db.repository import save_trade
from app.strategies._common import net_debit_credit


def run(state: AgentState) -> dict:
    order = state["proposed_order"]

    order_type = order.get("order_type", "market")
    limit_price = None
    if order_type == "limit":
        # net_debit_credit is dollar-scaled (x100, matching estimate_notional's
        # convention) — Alpaca's mleg limit_price is per-share, like a single
        # option's premium, so convert back down.
        limit_price = round(net_debit_credit(order["legs"]) / 100, 2)

    common_kwargs = dict(
        order_type=order_type,
        time_in_force=order.get("time_in_force", "day"),
        qty=order.get("qty", 1),
        limit_price=limit_price,
    )

    if len(order["legs"]) == 1:
        # True single-leg order (every live track today) -- top-level
        # symbol/side, no `legs` array. See mcp_client.place_option_order's
        # docstring for why: a non-None `legs` list (even one element) makes
        # the MCP server treat this as multi-leg regardless of order_class,
        # and Alpaca's real API then rejects it for lacking a top-level side.
        leg = order["legs"][0]
        result = place_option_order(symbol=leg["option_symbol"], side=leg["side"], **common_kwargs)
    else:
        legs: list[OptionLeg] = [
            {"symbol": leg["option_symbol"], "ratio_qty": leg["ratio_qty"], "side": leg["side"]}
            for leg in order["legs"]
        ]
        result = place_option_order(legs=legs, order_class="mleg", **common_kwargs)

    save_trade(symbol=state["symbol"], order=order, result=result, thesis=state.get("thesis", ""), track=state["track"])
    return {"execution_result": result}
