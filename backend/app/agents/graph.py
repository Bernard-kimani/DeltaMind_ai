"""LangGraph state-graph wiring for one full decision cycle.

    news_blackout_gate --(blocked)--------------------------------------------> END (0 REST/LLM calls)
                       --(clear)--> market_ingestion -> quant_engine --(Track 1, qualified)--> track1_validator --> risk_gate
                                                                     --(Track 4, qualified)--> track4_validator --> risk_gate
                                                                     --(Track 1/4, not qualified)-----------------> END (0 LLM calls)
                                                                     --(Track 2/3)-----------> news_analyst -> lead_architect -> risk_gate
                                                                                                                                     |
                                                                                               risk_approved? --yes--+--> execution -> END
                                                                                                                     +--no---------------> END (logged, no trade)

news_blackout_gate is the entry point, before market_ingestion — a cycle
inside a red-folder release's blackout window (see app/quant/news_calendar.py)
pays for zero REST calls and zero LLM calls, same "gate cheaply before
spending anything" principle as Track 1/4's own screens below it.
risk_gate.py re-checks the same condition as a backstop, in case a slow
cycle drifts across a blackout boundary between this gate and final approval.

Track 1 never reaches news_analyst/lead_architect: its technical confluence
screener (quant_engine.py, gating on state["technical_signal"]["qualified"])
must pass BEFORE any LLM is called, and its LLM validation + thesis are one
merged call (track1_validator.py) instead of two — see docs/tracks/track1_alpha_spreads.md.

Track 4 likewise never reaches news_analyst/lead_architect: IV percentile
(>= track4_income_wheel.IV_PERCENTILE_FLOOR) must qualify first, and — for a
fresh cash-secured put only, not a covered call — the daily-bar 200-EMA/RSI
regime check (quant_engine.py) must also qualify, before its own merged
risk-officer call (track4_validator.py) — see docs/tracks/track4_income_wheel.md.

Run one cycle with `run_cycle(symbol, track)`. `backend/scripts/run_agent_loop.py`
(Track 4) and `backend/scripts/run_agent_stream_track1.py` (Track 1) call this
on their own schedules for the live hackathon-week loop.
"""

import logging
import time
from typing import Callable

from langgraph.graph import END, StateGraph

from app.agents import execution, lead_architect, market_ingestion, news_analyst, news_blackout_gate, quant_engine, risk_gate, track1_validator, track4_validator
from app.agents.state import AgentState
from app.strategies.track4_income_wheel import IV_PERCENTILE_FLOOR as WHEEL_IV_FLOOR

logger = logging.getLogger(__name__)


def _timed(name: str, fn: Callable[[AgentState], dict]) -> Callable[[AgentState], dict]:
    """Wraps a node so every cycle logs where its latency actually went —
    the target is sub-2-second candle-close-to-decision for Track 1, and a
    single opaque "cycle took 1400ms" line can't say whether that was the
    REST data fetch, the LLM call, or placing the order with Alpaca. Logged
    via the standard `logging` module into whichever log file the running
    script already configured (see run_agent_stream_track1.py's/
    run_agent_loop.py's _configure_logging) — same file the WAIT/TRADE line
    already goes to, not a separate one."""
    def wrapper(state: AgentState) -> dict:
        t0 = time.monotonic()
        result = fn(state)
        elapsed_ms = (time.monotonic() - t0) * 1000
        logger.info("[%s] %s: %.0fms", state.get("symbol", "?"), name, elapsed_ms)
        timings = {**state.get("stage_timings_ms", {}), name: elapsed_ms}
        return {**result, "stage_timings_ms": timings}
    return wrapper


def _route_after_blackout(state: AgentState) -> str:
    return END if state.get("news_blackout_reason") else "market_ingestion"


def _route_after_quant(state: AgentState) -> str:
    if state["track"] == "track1_alpha_spreads":
        return "track1_validator" if state.get("technical_signal", {}).get("qualified") else END

    if state["track"] == "track4_income_wheel":
        if state.get("iv_percentile", 0) < WHEEL_IV_FLOOR:
            return END
        holds_shares = state.get("portfolio_risk", {}).get("holds_underlying_shares", False)
        # Covered call: IV percentile alone is the gate (no regime check —
        # see track4_income_wheel.py). Cash-secured put: also needs the
        # daily 200-EMA/RSI regime to have qualified.
        if holds_shares or state.get("technical_signal", {}).get("qualified"):
            return "track4_validator"
        return END

    return "news_analyst"


def _route_after_risk_gate(state: AgentState) -> str:
    return "execution" if state.get("risk_approved") else END


def build_graph():
    graph = StateGraph(AgentState)

    graph.add_node("news_blackout_gate", _timed("news_blackout_gate", news_blackout_gate.run))
    graph.add_node("market_ingestion", _timed("market_ingestion", market_ingestion.run))
    graph.add_node("quant_engine", _timed("quant_engine", quant_engine.run))
    graph.add_node("news_analyst", _timed("news_analyst", news_analyst.run))
    graph.add_node("lead_architect", _timed("lead_architect", lead_architect.run))
    graph.add_node("track1_validator", _timed("track1_validator", track1_validator.run))
    graph.add_node("track4_validator", _timed("track4_validator", track4_validator.run))
    graph.add_node("risk_gate", _timed("risk_gate", risk_gate.run))
    graph.add_node("execution", _timed("execution", execution.run))

    graph.set_entry_point("news_blackout_gate")
    graph.add_conditional_edges(
        "news_blackout_gate", _route_after_blackout, {"market_ingestion": "market_ingestion", END: END}
    )
    graph.add_edge("market_ingestion", "quant_engine")
    graph.add_conditional_edges(
        "quant_engine",
        _route_after_quant,
        {"news_analyst": "news_analyst", "track1_validator": "track1_validator", "track4_validator": "track4_validator", END: END},
    )
    graph.add_edge("news_analyst", "lead_architect")
    graph.add_edge("lead_architect", "risk_gate")
    graph.add_edge("track1_validator", "risk_gate")
    graph.add_edge("track4_validator", "risk_gate")
    graph.add_conditional_edges("risk_gate", _route_after_risk_gate, {"execution": "execution", END: END})
    graph.add_edge("execution", END)

    return graph.compile()


_compiled_graph = None


def run_cycle(symbol: str, track: str, sentiment_threshold: float = 0.5, volume_ratio_min: float = 1.2) -> AgentState:
    global _compiled_graph
    if _compiled_graph is None:
        _compiled_graph = build_graph()

    t0 = time.monotonic()
    result = _compiled_graph.invoke({
        "symbol": symbol,
        "track": track,
        "sentiment_threshold": sentiment_threshold,
        "volume_ratio_min": volume_ratio_min,
    })
    graph_ms = (time.monotonic() - t0) * 1000
    # graph_ms includes LangGraph's own routing/merge overhead between
    # nodes, on top of the per-node stage_timings_ms sum below — both
    # numbers are worth keeping since a gap between them means overhead
    # outside any single node, not just noise.
    stage_total_ms = sum(result.get("stage_timings_ms", {}).values())
    logger.info(
        "[%s] cycle internal total: %.0fms (stages: %.0fms, graph overhead: %.0fms)",
        symbol, graph_ms, stage_total_ms, graph_ms - stage_total_ms,
    )
    return result
