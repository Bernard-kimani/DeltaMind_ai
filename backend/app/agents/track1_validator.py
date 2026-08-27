"""Track 1 Catalyst Validator Node (LLM).

Reached only when quant_engine.py's technical confluence screener already
qualified this symbol (see graph.py's conditional edge after quant_engine,
which skips this node — and this node's LLM cost — entirely when it hasn't).
Replaces news_analyst.py + lead_architect.py for Track 1 with a single
merged LLM call: validates the technical setup against real news catalysts
and returns a verdict plus TP/SL/hold-time sizing hints in one schema,
instead of a separate sentiment call followed by a separate thesis call.
See docs/tracks/track1_alpha_spreads.md for the full spec and worked example.

The verdict/sentiment/confidence gate below is a hardcoded constant, not a
Controls-UI-tunable setting (unlike the old sentiment_threshold/volume_ratio_min)
— confirmed with the user when this replaced the old strategy.
"""

from app.agents.state import AgentState
from app.alpaca.mcp_client import get_news
from app.alpaca.rest_client import get_option_chain
from app.llm.client import get_llm_client
from app.quant.news_calendar import todays_calendar_summary
from app.strategies import track1_alpha_spreads

SENTIMENT_GATE = 0.50
CONFIDENCE_GATE = 70.0

SYSTEM_PROMPT = """You are the Lead Quantitative Strategist for an autonomous intraday options alpha agent.
Your sole role is to validate whether breaking news catalysts align with a deterministic technical breakout that has already been confirmed by a separate quantitative screener — you are not re-deriving the technical case, only checking whether news supports or contradicts it.

Evaluation Rules:
1. Directional Alignment: Bullish breakouts require positive catalysts; Bearish breakdowns require negative catalysts. If news is absent, neutral, or contradicts the technical direction, verdict must be "REJECT".
2. Sentiment Score: Output a float between -1.0 (max bearish) and +1.0 (max bullish). Neutral/conflicted news must fall between -0.49 and +0.49.
3. Confidence: Output a percentage (0 to 100) reflecting how strongly the news supports this specific trade.
4. Macro Context: today's scheduled macro releases (if any) are provided separately from this symbol's own headlines — a deterministic gate elsewhere already blocks new entries within 5 minutes of any of them, so you will never be asked to validate a trade happening AT a release. Use this context only to judge whether a recent price move is genuine company-specific news or just macro noise from an already-released print, and whether an upcoming release later today is close enough to the position's expected hold time to raise confidence bar.
5. Targets: Propose take_profit_pct (e.g. 40.0 to 100.0) and stop_loss_pct (e.g. 10.0 to 20.0) based on news intensity and catalyst horizon — these are guidance the deterministic strategy layer will still clamp to platform risk limits.
6. Strict Compliance: Output MUST be valid JSON matching the schema — no markdown, no prose outside the JSON fields."""


def run(state: AgentState) -> dict:
    symbol = state["symbol"]
    signal = state.get("technical_signal", {})
    headlines = get_news([symbol])

    user = (
        f"Symbol: {symbol}\n"
        f"Trigger Direction: {signal.get('direction')} (1-minute confluence confirmed by 15-minute trend)\n"
        f"Technical Summary:\n"
        f"- 15m Trend: {signal.get('trend_regime')} (price vs 15m 50-EMA: {signal.get('price_vs_15m_ema_pct', 0):.2%})\n"
        f"- 1m Trend: price vs 1m 20-EMA: {signal.get('price_vs_1m_ema_pct', 0):.2%}\n"
        f"- 1m VWAP offset: {signal.get('price_vs_vwap_pct', 0):.2%}\n"
        f"- 1m Relative Volume (RVOL): {signal.get('rvol', 0):.2f}x\n"
        f"- 1m RSI(14): {signal.get('rsi', 0):.1f}\n"
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

    qualified = (
        result.get("verdict") == "APPROVE"
        and abs(result.get("sentiment_score", 0.0)) >= SENTIMENT_GATE
        and result.get("confidence_pct", 0.0) >= CONFIDENCE_GATE
    )

    proposed_order = None
    if qualified:
        # Deferred from market_ingestion.py: the option chain (the single
        # most expensive fetch in the cycle, ~12s for a liquid underlying)
        # is only fetched here — a cycle that has ALREADY cleared both the
        # technical confluence gate and this LLM catalyst check, i.e. the
        # rare case actually about to place an order, not every cycle.
        option_chain = get_option_chain(symbol)
        proposed_order = track1_alpha_spreads.propose_order({**state, "option_chain": option_chain}, result)

    return {
        "sentiment_score": result.get("sentiment_score"),
        "thesis": result.get("thesis", ""),
        "proposed_order": proposed_order,
    }
