from typing import Any, Literal, TypedDict


class AgentState(TypedDict, total=False):
    """Shared state threaded through every LangGraph node in one decision cycle.

    Each node reads what it needs and returns a partial dict merged into this
    state — see app/agents/graph.py for the wiring.
    """

    # news_blackout_gate.py — the very first node (see graph.py). None when
    # clear; a human-readable reason string when a red-folder macro release
    # is within its blackout window right now (see app/quant/news_calendar.py).
    news_blackout_reason: str | None

    # Set at cycle start
    symbol: str
    track: Literal[
        "track1_alpha_spreads",
        "track2_volatility_events",
        "track3_hedging",
        "track4_income_wheel",
    ]
    # Track 1's runtime-configurable entry thresholds (Controls UI), read by
    # quant_engine.py (volume_ratio_min) and track1_alpha_spreads.py
    # (sentiment_threshold). Other tracks ignore these.
    sentiment_threshold: float
    volume_ratio_min: float

    # market_ingestion.py — the only node that does network I/O; fetches
    # everything a given track's later steps need, concurrently where
    # fetches are independent of each other (see that file for which track
    # gets which combination).
    market_data: list[dict[str, Any]]  # oldest-first 1-minute bars, see alpaca/rest_client.get_recent_bars
    option_chain: list[dict[str, Any]]  # empty for Track 1 (deferred to track1_validator.py — see its docstring)
    bars_15m: list[dict[str, Any]]  # Track 1 only — native 15-minute bars, see rest_client.get_15m_bars
    daily_bars: list[dict[str, Any]]  # Track 4 only — see rest_client.get_daily_bars / technical_signals.check_wheel_put_regime

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

    # Populated by graph.py's per-node timing wrapper, not by any node
    # itself — {"market_ingestion": 42.1, "quant_engine": 3.4, ...} in
    # milliseconds. Lets run_agent_stream_track1.py/run_agent_loop.py log
    # exactly where a cycle's latency went (data fetch vs. LLM vs. Alpaca
    # order placement) instead of only a single opaque total.
    stage_timings_ms: dict[str, float]
