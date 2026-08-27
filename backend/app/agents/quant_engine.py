"""Deterministic Quantitative Engine.

Pure Python — computes Greeks, IV percentile, and technical signals from data
market_ingestion.py already fetched (no REST calls of its own; moved there so
independent fetches across a cycle can run concurrently — see that file),
plus portfolio risk metrics via its own live account snapshot. Deliberately
has no LLM dependency: this node's output must be reproducible and auditable
by judges.
"""

from app.agents.state import AgentState
from app.quant.greeks import compute_greeks
from app.quant.iv_percentile import compute_iv_percentile
from app.quant.risk_metrics import portfolio_risk_snapshot
from app.quant.technical_signals import check_track1_confluence, check_wheel_put_regime, detect_breakout


def run(state: AgentState) -> dict:
    option_chain = state.get("option_chain", [])
    market_data = state.get("market_data", [])
    greeks = compute_greeks(option_chain)
    iv_percentile = compute_iv_percentile(state["symbol"], option_chain)
    portfolio_risk = portfolio_risk_snapshot(state["symbol"])

    # Track 1 gets the real multi-timeframe confluence screener (gates the
    # LLM call — see graph.py's conditional edge). Track 4 gets a daily-bar
    # 200-EMA/RSI regime check (gates new cash-secured-put entries only —
    # see track4_income_wheel.py). Tracks 2/3 keep today's single-timeframe
    # SMA breakout, unchanged.
    if state["track"] == "track1_alpha_spreads":
        technical_signal = check_track1_confluence(market_data, state.get("bars_15m", []))
    elif state["track"] == "track4_income_wheel":
        technical_signal = check_wheel_put_regime(state.get("daily_bars", []))
    else:
        technical_signal = detect_breakout(market_data, volume_ratio_min=state.get("volume_ratio_min", 1.2))

    return {
        "greeks": greeks,
        "iv_percentile": iv_percentile,
        "portfolio_risk": portfolio_risk,
        "technical_signal": technical_signal,
    }
