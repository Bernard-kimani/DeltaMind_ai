from app.backtest.engine import run as run_engine
from app.db.repository import save_backtest_run


def run_backtest(symbol: str, track: str, start: str, end: str) -> dict:
    result = run_engine(symbol=symbol, track=track, start=start, end=end)
    results_dict = {
        "trades": result.trades,
        "total_pnl": result.total_pnl,
        "win_rate": result.win_rate,
        "max_drawdown_pct": result.max_drawdown_pct,
        # Gate-qualification-frequency fields (see engine.py's module
        # docstring for why this backtest reports these instead of a P&L
        # simulation) — GateQualificationEvent is a dataclass, not directly
        # JSON-serializable, so qualifying_events is flattened to plain dicts.
        "total_bars_evaluated": result.total_bars_evaluated,
        "qualified_count": result.qualified_count,
        "qualification_rate": result.qualification_rate,
        "qualifying_events": [vars(e) for e in result.qualifying_events],
        "qualification_by_month": result.qualification_by_month,
        "known_gaps": result.known_gaps,
        "daily_prices": result.daily_prices,
        "qualifying_dates": result.qualifying_dates,
    }
    save_backtest_run(symbol=symbol, track=track, start_date=start, end_date=end, results=results_dict)
    return results_dict


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Run a strategy backtest from the CLI")
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--track", required=True)
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    args = parser.parse_args()

    print(run_backtest(args.symbol, args.track, args.start, args.end))
