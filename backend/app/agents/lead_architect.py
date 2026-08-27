"""Lead Architect Node (LLM).

The central decision orchestrator for tracks 2/3. Synthesizes deterministic
quant output (Greeks, IV percentile, technical breakout signal, portfolio
risk) with the news analyst's sentiment score into an explicit, testable
thesis, then dispatches to the strategy module for `state["track"]` to
translate that thesis into a concrete multi-leg option order proposal. This
node NEVER touches the brokerage directly — it only produces a proposal for
the Risk Gate to evaluate.

Neither Track 1 nor Track 4 goes through this node (see graph.py's
conditional edge after quant_engine, and app/agents/track1_validator.py /
track4_validator.py) — both gate their own LLM call behind a deterministic
screener first, and both use one merged validator call instead of this
node's sentiment-then-thesis split. `TRACK_ENTRY_RULES`/`STRATEGY_MODULES`
below intentionally have no Track 1 or Track 4 entry as a result.

The thesis text is carried onto the resulting order/decision record as the
human-readable explanation (shown in the dashboard's decision detail modal
and read by hackathon judges) — it does NOT feed back into propose_order()'s
actual entry logic, which is 100% deterministic per strategy module. That
split is deliberate (see PLAN.md section 3: judges need to verify guardrails
without a prompt-injection/hallucination surface on capital-touching logic).
"""

from app.agents.state import AgentState
from app.llm.client import get_llm_client
from app.strategies import track2_volatility_events, track3_hedging

STRATEGY_MODULES = {
    "track2_volatility_events": track2_volatility_events,
    "track3_hedging": track3_hedging,
}

# Plain-English entry rule per track, injected into the prompt so the LLM's
# thesis stays inside the structure that propose_order() will actually check
# deterministically — the model explains the decision, it doesn't make it.
TRACK_ENTRY_RULES = {
    "track2_volatility_events": (
        "Track 2 — Volatility & Events: trades IV percentile, not direction. "
        "Long strangle when IV percentile < 25 (cheap options ahead of an "
        "expected vol expansion); iron condor when IV percentile > 85 "
        "(expensive options, betting on post-event IV crush). Do not "
        "describe a directional debit spread; that belongs to Track 1."
    ),
    "track3_hedging": (
        "Track 3 — Hedging & Protection: a defensive collar (buy an OTM put, "
        "sell an OTM call to offset premium) triggered only by portfolio "
        "drawdown beyond 3.5%, weighted by each position's beta-adjusted "
        "delta. Do not describe a new speculative position; this track only "
        "protects existing exposure."
    ),
}

SYSTEM_PROMPT_TEMPLATE = """You are the lead trading strategist for an autonomous options agent.
The agent is currently running under exactly ONE strategy — you must reason
only within its rules below, even if the raw numbers might superficially
suggest a different strategy shape.

ACTIVE STRATEGY:
{track_rule}

Given the quantitative signals and sentiment score, produce a one-sentence
trading thesis that is explicit, testable, and consistent with the active
strategy above. If the active strategy's entry condition is not met, say so
plainly (e.g. "No breakout confirmed; sentiment alone is insufficient —
no trade this cycle") rather than inventing a rationale for a different
structure."""


def run(state: AgentState) -> dict:
    llm = get_llm_client()
    track = state["track"]
    rule = TRACK_ENTRY_RULES[track]
    track_rule = rule(state) if callable(rule) else rule
    system_prompt = SYSTEM_PROMPT_TEMPLATE.format(track_rule=track_rule)

    thesis = llm.generate(
        system=system_prompt,
        user=(
            f"Symbol: {state['symbol']}\n"
            f"Greeks: {state.get('greeks')}\n"
            f"IV percentile: {state.get('iv_percentile')}\n"
            f"Technical signal: {state.get('technical_signal')}\n"
            f"Sentiment: {state.get('sentiment_score')} ({state.get('sentiment_rationale')})\n"
            f"Portfolio risk: {state.get('portfolio_risk')}"
        ),
    )

    strategy = STRATEGY_MODULES[track]
    proposed_order = strategy.propose_order(state, thesis)

    return {"thesis": thesis, "proposed_order": proposed_order}
