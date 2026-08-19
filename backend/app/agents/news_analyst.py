"""Macro & News Analysis Node (LLM).

Uses the Alpaca MCP `get_news` tool to pull headlines for the symbol, then
asks the configured LLM (see app/llm/client.py) to score sentiment on a
normalized -1..+1 scale with a short rationale. Kept separate from the Lead
Architect so the sentiment signal stays independently inspectable/loggable.
"""

from app.agents.state import AgentState
from app.alpaca.mcp_client import get_news
from app.llm.client import get_llm_client

SYSTEM_PROMPT = """You are a market sentiment analyst. Given recent news headlines for a
symbol, return a JSON object {"score": float in [-1, 1], "rationale": str}.
score > 0.75 means strong bullish conviction, < -0.75 strong bearish conviction."""


def run(state: AgentState) -> dict:
    headlines = get_news(state["symbol"])
    llm = get_llm_client()
    result = llm.structured_generate(
        system=SYSTEM_PROMPT,
        user=f"Headlines for {state['symbol']}:\n" + "\n".join(headlines),
        schema={"score": float, "rationale": str},
    )
    return {
        "sentiment_score": result["score"],
        "sentiment_rationale": result["rationale"],
    }
