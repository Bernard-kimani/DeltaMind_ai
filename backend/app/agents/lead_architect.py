"""Lead Architect Node (LLM).

The central decision orchestrator. Synthesizes deterministic quant output
(Greeks, IV percentile, technical breakout signal, portfolio risk) with the
news analyst's sentiment score into an explicit, testable thesis, then
dispatches to the strategy module for `state["track"]` to translate that
thesis into a concrete multi-leg option order proposal. This node NEVER
touches the brokerage directly — it only produces a proposal for the Risk
Gate to evaluate.

The thesis text is carried onto the resulting order/decision record as the
human-readable explanation (shown in the dashboard's decision detail modal
and read by hackathon judges) — it does NOT feed back into propose_order()'s
actual entry logic, which is 100% deterministic per strategy module. That
split is deliberate (see PLAN.md section 3: judges need to verify guardrails
without a prompt-injection/hallucination surface on capital-touching logic),
but it means an ungrounded thesis is a real bug even though it can't cause a
bad trade: a Track 1 thesis reasoning about a different track's structure
(e.g. IV-percentile-driven straddles, which is Track 2's playbook) reads as
incoherent to exactly the audience — judges reading the reasoning trail —
this thesis exists for. Confirmed live 2026-08-23: running Track 1, the LLM
produced a Track-2-shaped thesis given the same raw Greeks/IV/sentiment
numbers with no track framing at all. Fixed by naming the active track and
its actual entry rule explicitly in the prompt below, rather than handing
the model undifferentiated signals and letting it pick whichever structure
the numbers most resemble.
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

# Plain-English entry rule per track, injected into the prompt so the LLM's
# thesis stays inside the structure that propose_order() will actually check
# deterministically — the model explains the decision, it doesn't make it.
TRACK_ENTRY_RULES = {
    "track1_alpha_spreads": (
        "Track 1 — Options Alpha: a vertical debit spread (buy ~0.70-delta, "
        "sell ~0.30-delta, ~14 DTE), entered ONLY when a technical breakout "
        "(price outside its recent range, confirmed by volume) AND sentiment "
        "beyond +/-0.75 agree on the same direction. If they don't agree, or "
        "either signal is absent, the correct thesis is that no trade "
        "qualifies this cycle — do not describe a straddle, condor, collar, "
        "or wheel; those belong to other tracks."
    ),
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
    "track4_income_wheel": (
        "Track 4 — Income & Overlay (the Wheel): sell ~0.30-delta "
        "cash-secured puts for premium; if assigned, switch to selling "
        "~0.30-delta covered calls on the resulting shares until called "
        "away. This is a yield/theta-decay play, not a directional bet — "
        "do not describe buying options outright."
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
    system_prompt = SYSTEM_PROMPT_TEMPLATE.format(track_rule=TRACK_ENTRY_RULES[track])

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
