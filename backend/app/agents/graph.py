"""LangGraph state-graph wiring for one full decision cycle.

    market_ingestion -> quant_engine -> news_analyst -> lead_architect -> risk_gate
                                                                              |
                                                        risk_approved? --yes--+--> execution -> END
                                                                              +--no---------------> END (logged, no trade)

Run one cycle with `run_cycle(symbol, track)`. `backend/scripts/run_agent_loop.py`
calls this on a schedule for the live hackathon-week loop.
"""

from langgraph.graph import END, StateGraph

from app.agents import execution, lead_architect, market_ingestion, news_analyst, quant_engine, risk_gate
from app.agents.state import AgentState


def _route_after_risk_gate(state: AgentState) -> str:
    return "execution" if state.get("risk_approved") else END


def build_graph():
    graph = StateGraph(AgentState)

    graph.add_node("market_ingestion", market_ingestion.run)
    graph.add_node("quant_engine", quant_engine.run)
    graph.add_node("news_analyst", news_analyst.run)
    graph.add_node("lead_architect", lead_architect.run)
    graph.add_node("risk_gate", risk_gate.run)
    graph.add_node("execution", execution.run)

    graph.set_entry_point("market_ingestion")
    graph.add_edge("market_ingestion", "quant_engine")
    graph.add_edge("quant_engine", "news_analyst")
    graph.add_edge("news_analyst", "lead_architect")
    graph.add_edge("lead_architect", "risk_gate")
    graph.add_conditional_edges("risk_gate", _route_after_risk_gate, {"execution": "execution", END: END})
    graph.add_edge("execution", END)

    return graph.compile()


_compiled_graph = None


def run_cycle(symbol: str, track: str) -> AgentState:
    global _compiled_graph
    if _compiled_graph is None:
        _compiled_graph = build_graph()
    return _compiled_graph.invoke({"symbol": symbol, "track": track})
