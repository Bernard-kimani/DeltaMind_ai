"""Unrealized P&L for currently-OPEN trades, by track — used by the
Controls tab's Track P&L summary (api/routes_trades.py's /pnl-summary).

Deliberately a standalone helper, not a refactor of
position_monitor.py's `_sweep_track1_positions()`: that function's matching
logic is live-verified exit-management code (profit-take/stop-loss), and
reusing it here would mean threading a "just report, don't act" mode through
tested trading logic for a read-only dashboard number — not worth the risk
of regressing verified behavior. This module intentionally duplicates the
simple "match trade legs to live positions" half only.
"""

from app.alpaca.rest_client import get_all_positions
from app.db.repository import list_open_trades


def compute_unrealized_pnl(track: str) -> tuple[float, int]:
    """Returns (total unrealized P&L, number of open trades matched to a
    live position). Trades whose option leg is no longer found (e.g. a
    Track 4 CSP that got assigned and became shares) fall back to matching
    the underlying equity position — best-effort, may undercount if a trade
    is mid-transition between the two (see docs/tracks/track4_income_wheel.md).
    """
    open_trades = list_open_trades(track=track)
    if not open_trades:
        return 0.0, 0

    positions_by_symbol = {p["symbol"]: p for p in get_all_positions()}
    total = 0.0
    matched = 0

    for trade in open_trades:
        legs = trade["order"].get("legs", [])
        leg_symbols = [leg["option_symbol"] for leg in legs if "option_symbol" in leg]
        leg_positions = [positions_by_symbol.get(sym) for sym in leg_symbols]

        if leg_symbols and all(p is not None for p in leg_positions):
            total += sum(float(p.get("unrealized_pl") or 0) for p in leg_positions)
            matched += 1
            continue

        equity_position = positions_by_symbol.get(trade["symbol"])
        if equity_position is not None and equity_position.get("asset_class") == "us_equity":
            total += float(equity_position.get("unrealized_pl") or 0)
            matched += 1

    return total, matched
