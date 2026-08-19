"""Minimal event-loop backtester: walks historical daily bars, calls the same
strategy propose_order() functions used live (see app/strategies/), and
simulates fills against historical option bars to produce win rate,
avg P&L, and max drawdown. Deliberately reuses the live strategy code so
backtest results are representative of what the live agent will actually do.
"""

from dataclasses import dataclass, field


@dataclass
class BacktestResult:
    symbol: str
    track: str
    trades: list[dict] = field(default_factory=list)
    total_pnl: float = 0.0
    win_rate: float = 0.0
    max_drawdown_pct: float = 0.0


def run(symbol: str, track: str, start: str, end: str) -> BacktestResult:
    """TODO: wire up to data_loader.py + app/strategies/<track>.propose_order().

    Left as a stub — implement once real historical option-chain-with-Greeks
    data access is confirmed against your Alpaca data plan/entitlements.
    """
    return BacktestResult(symbol=symbol, track=track)
