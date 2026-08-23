"""Deterministic Quantitative Engine.

Pure Python — computes Greeks, IV percentile, technical breakout signal, and
portfolio risk metrics from `state["market_data"]` / `state["option_chain"]`.
Deliberately has no LLM dependency: this node's output must be reproducible
and auditable by judges.
"""

from app.agents.state import AgentState
from app.quant.greeks import compute_greeks
from app.quant.iv_percentile import compute_iv_percentile
from app.quant.risk_metrics import portfolio_risk_snapshot
from app.quant.technical_signals import detect_breakout


def run(state: AgentState) -> dict:
    option_chain = state.get("option_chain", [])
    market_data = state.get("market_data", [])
    greeks = compute_greeks(option_chain)
    iv_percentile = compute_iv_percentile(state["symbol"], option_chain)
    portfolio_risk = portfolio_risk_snapshot(state["symbol"])
    technical_signal = detect_breakout(market_data)

    return {
        "greeks": greeks,
        "iv_percentile": iv_percentile,
        "portfolio_risk": portfolio_risk,
        "technical_signal": technical_signal,
    }
