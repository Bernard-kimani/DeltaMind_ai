"""Track 5 (Momentum Swing) Validator Node (LLM).

Reached only when quant_engine.py's momentum-swing confluence screener
already qualified this symbol (see graph.py's conditional edge, which skips
this node — and its LLM cost — entirely otherwise). Mirrors
track1_validator.py's merged catalyst-check pattern, but deliberately
looser: Track 1's deterministic gate does most of the filtering (five
factors must all agree), so its LLM call only needs to double-check
against contradicting news. Track 5's deterministic gate is thin on
purpose (two factors — see technical_signals.check_momentum_swing_confluence),
so THIS validator is where the real decision-making weight sits — a lower
confidence bar and a looser sentiment requirement (no contradiction, not
"needs strong confirming sentiment") by design, not an oversight.

The verdict/sentiment/confidence gate below is a hardcoded constant, same
precedent as Track 1's — not a Controls-UI-tunable setting.
"""

from app.agents.state import AgentState
from app.alpaca.mcp_client import get_news
from app.alpaca.rest_client import get_option_chain
from app.llm.client import get_llm_client
from app.quant.news_calendar import todays_calendar_summary
from app.strategies import track5_momentum_swing

# Deliberately lower than Track 1's (0.50 / 70.0) — see module docstring.
# Sentiment only needs to not outright contradict the technical direction,
# not confirm it strongly, since the technical gate here already required a
# real 1h-trend + 5m-crossover agreement.
SENTIMENT_CONTRADICTION_GATE = 0.35
CONFIDENCE_GATE = 55.0

SYSTEM_PROMPT = """You are the Lead Quantitative Strategist for an autonomous swing-trading options agent, trading a slower momentum-continuation setup (hours, not minutes) than a typical intraday scalp.
Your sole role is to validate whether breaking news catalysts align with (or at least don't contradict) a deterministic momentum setup already confirmed by a separate quantitative screener — you are not re-deriving the technical case, only checking whether news supports or clearly contradicts it.

Evaluation Rules:
1. Directional Alignment: Bullish setups need news that is not clearly bearish; bearish setups need news that is not clearly bullish. Neutral or absent news is fine here — this is a real difference from a stricter validator: only REJECT when news clearly contradicts the technical direction, not merely for lacking confirmation.
2. Sentiment Score: Output a float between -1.0 (max bearish) and +1.0 (max bullish). This is a supporting signal, not the primary gate.
3. Confidence: Output a percentage (0 to 100) reflecting how comfortable you are with this trade given the full picture (technical setup + news context + macro calendar).
4. Macro Context: today's scheduled macro releases (if any) are provided separately from this symbol's own headlines — a deterministic gate elsewhere already blocks new entries within 5 minutes of any of them. Use this context to judge whether a recent price move is genuine company-specific momentum or just macro noise, and whether an upcoming release later today is close enough to this trade's expected multi-hour hold time to lower your confidence.
5. Targets: Propose take_profit_pct (e.g. 40.0 to 100.0) and stop_loss_pct (e.g. 10.0 to 20.0) based on setup quality and catalyst horizon, and max_hold_minutes (e.g. 120 to 480, i.e. 2-8 hours) reflecting how long this specific setup seems likely to need — these are guidance the deterministic strategy layer will still clamp to platform risk limits.
6. Strict Compliance: Output MUST be valid JSON matching the schema — no markdown, no prose outside the JSON fields."""


def run(state: AgentState) -> dict:
    symbol = state["symbol"]
    signal = state.get("technical_signal", {})
    headlines = get_news([symbol])

    user = (
        f"Symbol: {symbol}\n"
        f"Trigger Direction: {signal.get('direction')} (5-minute EMA crossover confirmed by 1-hour trend)\n"
        f"Technical Summary:\n"
        f"- 1h Trend: price vs 1h 50-EMA: {signal.get('price_vs_1h_ema_pct', 0):.2%}\n"
        f"- 5m Momentum: price vs 5m 20-EMA: {signal.get('price_vs_5m_ema_pct', 0):.2%}\n"
        f"{todays_calendar_summary()}\n"
        f"Recent News Headlines:\n" + "\n".join(headlines or ["(no recent headlines)"])
    )

    llm = get_llm_client()
    result = llm.structured_generate(
        system=SYSTEM_PROMPT,
        user=user,
        schema={
            "verdict": str,
            "sentiment_score": float,
            "confidence_pct": float,
            "take_profit_pct": float,
            "stop_loss_pct": float,
            "max_hold_minutes": int,
            "thesis": str,
        },
    )

    direction = signal.get("direction")
    sentiment_score = result.get("sentiment_score", 0.0)
    # Contradiction check, not confirmation: a bullish setup is rejected only
    # if sentiment is clearly bearish (below -gate), and vice versa — this
    # is the concrete difference from Track 1's |sentiment| >= gate rule.
    contradicts = (
        (direction == "up" and sentiment_score <= -SENTIMENT_CONTRADICTION_GATE)
        or (direction == "down" and sentiment_score >= SENTIMENT_CONTRADICTION_GATE)
    )
    qualified = (
        result.get("verdict") == "APPROVE"
        and not contradicts
        and result.get("confidence_pct", 0.0) >= CONFIDENCE_GATE
    )

    proposed_order = None
    if qualified:
        # Deferred until here, same reasoning as track1_validator.py: the
        # option chain is the single most expensive fetch in the cycle,
        # only worth paying for on a cycle that's already cleared both the
        # technical gate and this LLM check.
        option_chain = get_option_chain(symbol)
        proposed_order = track5_momentum_swing.propose_order({**state, "option_chain": option_chain}, result)

    return {
        "sentiment_score": result.get("sentiment_score"),
        "thesis": result.get("thesis", ""),
        "proposed_order": proposed_order,
    }
