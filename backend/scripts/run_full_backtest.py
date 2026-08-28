"""Run the gate-qualification backtest across the full curated watchlist for
both tracks, saving each symbol's result via the normal run_backtest() path
(which persists to backtest_runs) and printing a combined summary table.

One-off weekend job, not part of the live app -- see PLAN.md's Workstream 3.
"""

import argparse
import datetime as dt
import sys
import time
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.backtest.runner import run_backtest
from app.watchlist import WATCHLIST


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the backtest across the full watchlist for one or both tracks")
    parser.add_argument("--start", default="2026-03-01")
    parser.add_argument("--end", default=(dt.date.today() - dt.timedelta(days=1)).isoformat())
    parser.add_argument("--tracks", nargs="+", default=["track1_alpha_spreads", "track4_income_wheel"])
    parser.add_argument("--symbols", nargs="+", default=WATCHLIST)
    args = parser.parse_args()

    rows = []
    for track in args.tracks:
        for symbol in args.symbols:
            t0 = time.time()
            try:
                result = run_backtest(symbol=symbol, track=track, start=args.start, end=args.end)
                elapsed = time.time() - t0
                rows.append({
                    "track": track,
                    "symbol": symbol,
                    "bars": result["total_bars_evaluated"],
                    "qualified": result["qualified_count"],
                    "rate": result["qualification_rate"],
                    "gaps": len(result["known_gaps"]),
                    "elapsed_s": round(elapsed, 1),
                    "error": None,
                })
                print(f"[{track}] {symbol}: bars={result['total_bars_evaluated']} qualified={result['qualified_count']} "
                      f"rate={result['qualification_rate']:.2%} ({elapsed:.1f}s)")
            except Exception as e:
                elapsed = time.time() - t0
                rows.append({"track": track, "symbol": symbol, "bars": 0, "qualified": 0, "rate": 0.0,
                             "gaps": 0, "elapsed_s": round(elapsed, 1), "error": str(e)})
                print(f"[{track}] {symbol}: ERROR {e}")

    print("\n=== Summary ===")
    for track in args.tracks:
        track_rows = [r for r in rows if r["track"] == track]
        total_bars = sum(r["bars"] for r in track_rows)
        total_qualified = sum(r["qualified"] for r in track_rows)
        errors = [r for r in track_rows if r["error"]]
        overall_rate = (total_qualified / total_bars) if total_bars else 0.0
        print(f"{track}: {total_bars} bars evaluated, {total_qualified} qualified, overall rate {overall_rate:.2%}, "
              f"{len(errors)} symbol(s) errored")
        for r in sorted(track_rows, key=lambda r: -r["rate"]):
            flag = f" ERROR: {r['error']}" if r["error"] else ""
            print(f"  {r['symbol']:6s} bars={r['bars']:6d} qualified={r['qualified']:5d} rate={r['rate']:.2%}{flag}")


if __name__ == "__main__":
    main()
