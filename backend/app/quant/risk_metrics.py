"""Portfolio-level risk metrics feeding the Risk Gate and Track 3 (Hedging)
drawdown trigger.
"""

from app.alpaca.rest_client import get_account_info, get_all_positions


def beta_weighted_delta(positions: list[dict], betas: dict[str, float]) -> float:
    """Delta_portfolio = sum(weight_i * beta_i * delta_i) across positions."""
    total_notional = sum(abs(p.get("market_value", 0)) for p in positions) or 1.0
    weighted = 0.0
    for p in positions:
        symbol = p["symbol"]
        weight = abs(p.get("market_value", 0)) / total_notional
        beta = betas.get(symbol, 1.0)
        delta = p.get("delta", 0.0)
        weighted += weight * beta * delta
    return weighted


def portfolio_drawdown_pct(equity_curve: list[float]) -> float:
    if not equity_curve:
        return 0.0
    peak = equity_curve[0]
    max_dd = 0.0
    for value in equity_curve:
        peak = max(peak, value)
        max_dd = max(max_dd, (peak - value) / peak if peak else 0.0)
    return max_dd


def portfolio_risk_snapshot() -> dict:
    """Live equity/margin snapshot consumed by quant_engine.py -> risk_gate.py."""
    account = get_account_info()
    positions = get_all_positions()
    equity = float(account.get("equity", 0))
    maintenance_margin = float(account.get("maintenance_margin", 0))
    return {
        "equity": equity,
        "margin_utilization_pct": (maintenance_margin / equity) if equity else 0.0,
        "position_count": len(positions),
    }
