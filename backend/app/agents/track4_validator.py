"""Track 4 Risk Officer Validator Node (LLM).

Reached only when quant_engine.py's deterministic gate already qualified
this symbol (see graph.py's conditional edge after quant_engine, which
skips this node — and its LLM cost — entirely otherwise): IV percentile
>= 45 for either wheel leg, AND (for a fresh cash-secured put only) the
daily-bar 200-EMA/RSI regime check. Replaces news_analyst.py + lead_architect.py
for Track 4 with a single merged LLM call, mirroring track1_validator.py's
pattern — but the job here is different: not a directional catalyst check,
a solvency/binary-event risk gate (per the user-supplied Wheel Strategy
spec). See docs/tracks/track4_income_wheel.md for the full spec and worked
example.

Caveat, stated plainly rather than oversold: there is no earnings-calendar
data source anywhere in this codebase or Alpaca's MCP tools (checked before
building this) — the "earnings within N days" check is necessarily an LLM
judgment call from news headlines, not a real calendar lookup. Same category
of honest limitation as Track 1's catalyst validation.

The verdict/risk_score/confidence gate below is a hardcoded constant, not a
Controls-UI-tunable setting — same precedent as Track 1's validator.
"""

from app.agents.state import AgentState
from app.alpaca.mcp_client import get_news
from app.llm.client import get_llm_client
from app.quant.news_calendar import todays_calendar_summary
from app.strategies import track4_income_wheel

RISK_SCORE_CEILING = 0.35
CONFIDENCE_GATE = 70.0

SYSTEM_PROMPT = """You are the Lead Risk Officer for a systematic institutional Income Wheel Agent.
Your sole job is to protect capital from catastrophic tail risk, impending binary events, and severe structural degradation.

Evaluation Rules:
1. Binary Event Defense: If earnings or FDA announcements fall within the 21-day holding period, REJECT the trade (avoid IV crush / gap-down assignment).
2. Solvency & Sentiment: Evaluate if recent news indicates fraud, regulatory investigations, or systemic business deterioration.
3. Macro Context: today's scheduled macro releases (if any) are provided separately — this is a small, manually-curated calendar (not exhaustive), for context only, not a substitute for your own earnings-conflict judgment from the headlines below.
4. Output strictly valid JSON matching the requested schema. No prose."""


def run(state: AgentState) -> dict:
    symbol = state["symbol"]
    signal = state.get("technical_signal", {})
    holds_shares = state.get("portfolio_risk", {}).get("holds_underlying_shares", False)
    headlines = get_news([symbol])

    user = (
        f"Symbol: {symbol}\n"
        f"Wheel leg under consideration: {'covered call' if holds_shares else 'cash-secured put'} (~21 DTE)\n"
        f"IV percentile: {state.get('iv_percentile', 0):.1f}\n"
        + (
            f"Daily regime: price vs 200-EMA {signal.get('price_vs_200ema_pct', 0):.2%}, RSI(14) {signal.get('rsi', 0):.1f}\n"
            if not holds_shares else ""
        )
        + f"{todays_calendar_summary()}\n"
        + f"Recent News Headlines:\n" + "\n".join(headlines or ["(no recent headlines)"])
    )

    llm = get_llm_client()
    result = llm.structured_generate(
        system=SYSTEM_PROMPT,
        user=user,
        schema={
            "verdict": str,
            "risk_score": float,
            "earnings_conflict": bool,
            "confidence_pct": float,
            "profit_target_pct": float,
            "thesis": str,
        },
    )

    qualified = (
        result.get("verdict") == "APPROVE"
        and not result.get("earnings_conflict", True)
        and result.get("risk_score", 1.0) <= RISK_SCORE_CEILING
        and result.get("confidence_pct", 0.0) >= CONFIDENCE_GATE
    )
    proposed_order = track4_income_wheel.propose_order(state, result) if qualified else None

    return {
        "thesis": result.get("thesis", ""),
        "proposed_order": proposed_order,
    }
