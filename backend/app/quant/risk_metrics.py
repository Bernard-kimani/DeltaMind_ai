"""Portfolio-level risk metrics feeding the Risk Gate and Track 3 (Hedging)
drawdown trigger.
"""

from app.alpaca.rest_client import get_account_info, get_all_positions
from app.db.repository import get_wheel_state


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


def sector_exposure_pct(sector: str | None, positions: list[dict], sector_map: dict[str, str]) -> float:
    """Fraction of equity currently held in the given sector — used by
    risk_gate.py's sector concentration cap (see app/watchlist.py for the
    sector tags). Positions for symbols outside the sector map are ignored
    (untagged, so they can't be checked against a cap that doesn't know
    about them)."""
    if sector is None:
        return 0.0
    total_equity = sum(abs(float(p.get("market_value") or 0)) for p in positions) or 1.0
    sector_value = sum(
        abs(float(p.get("market_value") or 0)) for p in positions if sector_map.get(p.get("symbol")) == sector
    )
    return sector_value / total_equity


def portfolio_risk_snapshot(symbol: str | None = None) -> dict:
    """Live equity/margin/cash snapshot consumed by quant_engine.py ->
    risk_gate.py. `holds_underlying_shares` reflects `symbol`'s real wheel
    state (see position_monitor.py's `_sync_wheel_state` — the fix for the
    gap where this was previously hardcoded unreachable-False)."""
    account = get_account_info()
    positions = get_all_positions()
    equity = float(account.get("equity", 0))
    maintenance_margin = float(account.get("maintenance_margin", 0))
    return {
        "equity": equity,
        "cash": float(account.get("cash", 0)),
        "margin_utilization_pct": (maintenance_margin / equity) if equity else 0.0,
        "position_count": len(positions),
        "holds_underlying_shares": get_wheel_state(symbol) if symbol else False,
        # Threaded through for risk_gate.py's sector-concentration check
        # (sector_exposure_pct) — avoids a second get_all_positions() call
        # in the same cycle.
        "positions": positions,
    }
