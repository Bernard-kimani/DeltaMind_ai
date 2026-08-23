from typing import Any, Literal, TypedDict


class AgentState(TypedDict, total=False):
    """Shared state threaded through every LangGraph node in one decision cycle.

    Each node reads what it needs and returns a partial dict merged into this
    state — see app/agents/graph.py for the wiring.
    """

    # Set at cycle start
    symbol: str
    track: Literal[
        "track1_alpha_spreads",
        "track2_volatility_events",
        "track3_hedging",
        "track4_income_wheel",
    ]

    # market_ingestion.py
    market_data: list[dict[str, Any]]  # oldest-first bars, see alpaca/rest_client.get_recent_bars
    option_chain: list[dict[str, Any]]

    # quant_engine.py — deterministic, no LLM involved
    greeks: dict[str, float]
    iv_percentile: float
    historical_volatility: float
    portfolio_risk: dict[str, Any]
    technical_signal: dict[str, Any]  # see quant/technical_signals.py — breakout/direction/volume_ratio

    # news_analyst.py — LLM
    sentiment_score: float
    sentiment_rationale: str

    # lead_architect.py — LLM
    thesis: str
    proposed_order: dict[str, Any] | None

    # risk_gate.py — deterministic circuit breaker
    risk_approved: bool
    risk_rejection_reason: str | None

    # execution.py
    execution_result: dict[str, Any] | None
