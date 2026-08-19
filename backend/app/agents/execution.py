"""Execution Specialist Node.

Only reached when state["risk_approved"] is True (see graph.py's conditional
edge). Dispatches the validated multi-leg option order via the Alpaca MCP
client and persists the fill/order result for the dashboard's trade log.
"""

from app.agents.state import AgentState
from app.alpaca.mcp_client import place_option_order
from app.db.repository import save_trade


def run(state: AgentState) -> dict:
    order = state["proposed_order"]
    result = place_option_order(order)
    save_trade(symbol=state["symbol"], order=order, result=result, thesis=state.get("thesis", ""))
    return {"execution_result": result}
