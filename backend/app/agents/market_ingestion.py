"""Market Ingestion Node.

Pulls real-time bars, quotes, and the option chain snapshot (with Greeks/IV
where available) for `state["symbol"]` via the Alpaca REST/WebSocket client.
No LLM involved — pure data fetch.
"""

from app.agents.state import AgentState
from app.alpaca.rest_client import get_option_chain, get_recent_bars


def run(state: AgentState) -> dict:
    symbol = state["symbol"]
    market_data = get_recent_bars(symbol)
    option_chain = get_option_chain(symbol)
    return {"market_data": market_data, "option_chain": option_chain}
