"""Lead Architect Node (LLM).

The central decision orchestrator. Synthesizes deterministic quant output
(Greeks, IV percentile, portfolio risk) with the news analyst's sentiment
score into an explicit, testable thesis, then dispatches to the strategy
module for `state["track"]` to translate that thesis into a concrete
multi-leg option order proposal. This node NEVER touches the brokerage
directly — it only produces a proposal for the Risk Gate to evaluate.
"""

from app.agents.state import AgentState
from app.llm.client import get_llm_client
from app.strategies import track1_alpha_spreads, track2_volatility_events, track3_hedging, track4_income_wheel

STRATEGY_MODULES = {
    "track1_alpha_spreads": track1_alpha_spreads,
    "track2_volatility_events": track2_volatility_events,
    "track3_hedging": track3_hedging,
    "track4_income_wheel": track4_income_wheel,
}

SYSTEM_PROMPT = """You are the lead trading strategist for an autonomous options agent.
Given quantitative signals and a sentiment score, produce a one-sentence trading
thesis. Be explicit and testable, e.g. "Bullish momentum detected; IV percentile
is low; enter a 14-day call debit spread."""


def run(state: AgentState) -> dict:
    llm = get_llm_client()
    thesis = llm.generate(
        system=SYSTEM_PROMPT,
        user=(
            f"Symbol: {state['symbol']}\n"
            f"Greeks: {state.get('greeks')}\n"
            f"IV percentile: {state.get('iv_percentile')}\n"
            f"Sentiment: {state.get('sentiment_score')} ({state.get('sentiment_rationale')})\n"
            f"Portfolio risk: {state.get('portfolio_risk')}"
        ),
    )

    strategy = STRATEGY_MODULES[state["track"]]
    proposed_order = strategy.propose_order(state, thesis)

    return {"thesis": thesis, "proposed_order": proposed_order}
