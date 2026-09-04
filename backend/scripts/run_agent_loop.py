"""Main entrypoint for the live hackathon-week agent loop (Aug 28 - Sep 4).

Runs one LangGraph decision cycle per watched symbol every INTERVAL_SECONDS,
persists the full decision trail (including rejections) via
app.db.repository, and logs every cycle to logs/agent_loop_{track}.log (one
file per track — Track 1 and Track 4 run as independent concurrent
subprocesses) in the format the dashboard's Logs tab parses (see
app/api/routes_logs.py).

Usage:
    uv run python scripts/run_agent_loop.py --symbols SPY,QQQ --track track1_alpha_spreads --interval 300

Normally launched as a subprocess by app/agent_loop_manager.py (the
Controls tab's Start/Stop/Restart buttons); can also be run standalone for
the Day 1 hackathon deploy — see PLAN.md > Setup > Day 1 checklist.
"""

import argparse
import ctypes
import logging
import sys
import time
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.log_rotation import trim_log_file  # noqa: E402
from app.rate_limits import CIRCUIT_BREAKER_EXIT_CODE, CONSECUTIVE_FAILED_PASSES_THRESHOLD, MIN_INTERVAL_SECONDS  # noqa: E402

logger = logging.getLogger("agent_loop")


def _log_file_for_track(track: str) -> Path:
    """Track 1 and Track 4 run as independent concurrent subprocesses, each
    with its own log file — must match agent_loop_manager.log_file_for_track
    (deliberately duplicated, not imported, to keep this script decoupled
    from the manager module that spawns it)."""
    return BACKEND_DIR / "logs" / f"agent_loop_{track}.log"

ES_CONTINUOUS = 0x80000000
ES_SYSTEM_REQUIRED = 0x00000001


def _prevent_sleep() -> None:
    """Blocks Windows inactivity sleep (not a manually closed lid) for as
    long as this process is alive. Re-asserted once per pass per MSDN
    guidance for long-running operations — cheap at a multi-minute cadence.
    No-op (and safe to call) on non-Windows."""
    if sys.platform != "win32":
        return
    try:
        ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS | ES_SYSTEM_REQUIRED)
    except Exception:
        logger.exception("failed to set thread execution state (sleep prevention)")


def _configure_logging(log_file: Path) -> None:
    log_file.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[logging.FileHandler(log_file, encoding="utf-8"), logging.StreamHandler(sys.stdout)],
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbols", required=True, help="comma-separated, e.g. SPY,QQQ")
    parser.add_argument(
        "--track",
        required=True,
        choices=["track1_alpha_spreads", "track2_volatility_events", "track3_hedging", "track4_income_wheel"],
    )
    parser.add_argument("--interval", type=int, default=300, help="seconds between cycles")
    parser.add_argument("--sentiment-threshold", type=float, default=0.5, help="Track 1: |sentiment| must exceed this")
    parser.add_argument("--volume-ratio-min", type=float, default=1.2, help="Track 1: breakout volume vs. its own average")
    args = parser.parse_args()

    if args.interval < MIN_INTERVAL_SECONDS:
        parser.error(f"--interval must be >= {MIN_INTERVAL_SECONDS} seconds")

    log_file = _log_file_for_track(args.track)

    # Logging is configured — and writes its first line — before the heavy
    # imports below (LangGraph, alpaca-py, openai/anthropic SDKs take ~10s
    # cold). Without this ordering, the Logs tab looks dead for that whole
    # window instead of showing the process is alive and importing.
    _configure_logging(log_file)
    symbols = [s.strip() for s in args.symbols.split(",")]
    logger.info("Agent loop process starting — symbols=%s track=%s interval=%ss", symbols, args.track, args.interval)
    logger.info("Importing agent graph and dependencies (LangGraph, Alpaca SDK, LLM clients)...")

    from app.agents.graph import run_cycle
    from app.agents.position_monitor import sweep_positions
    from app.db.repository import save_agent_decision
    from app.llm.rate_limiter import LLMBudgetExceededError

    logger.info("Imports complete — entering live decision loop")
    # WARNING, not INFO — survives the Logs tab's default WARNING-level
    # filter, so this is the first line actually visible after Start,
    # instead of an unrelated config_store warning (see
    # run_agent_stream_track1.py's identical fix).
    logger.warning("%s engine started — Alpaca connection active (entering live decision loop, symbols=%s)", args.track, symbols)

    consecutive_failed_passes = 0

    while True:
        _prevent_sleep()
        pass_had_success = False

        try:
            # Runs once per full pass, before fresh entries are proposed —
            # a stop-loss/profit-take/assignment should be acted on before
            # this cycle's new proposals get evaluated against portfolio
            # numbers that sweep would otherwise leave stale.
            for action in sweep_positions(args.track):
                logger.info("[%s] monitor: %s", action["symbol"], action["action"])
        except Exception:
            logger.exception("position monitor sweep failed")

        for symbol in symbols:
            try:
                result = run_cycle(
                    symbol=symbol,
                    track=args.track,
                    sentiment_threshold=args.sentiment_threshold,
                    volume_ratio_min=args.volume_ratio_min,
                )
                save_agent_decision(
                    symbol=symbol,
                    track=args.track,
                    sentiment_score=result.get("sentiment_score"),
                    thesis=result.get("thesis"),
                    proposed_order=result.get("proposed_order"),
                    risk_approved=result.get("risk_approved"),
                    risk_rejection_reason=result.get("risk_rejection_reason"),
                )
                pass_had_success = True

                # One consolidated line per symbol per cycle (2026-08-27
                # log-volume reduction — see graph.py's _timed docstring).
                # TRADE at WARNING so it survives the Logs tab's default
                # WARNING-level filter; WAIT/BLOCKED stay INFO, hidden by
                # that default, visible if the level filter is widened.
                if result.get("news_blackout_reason"):
                    outcome, detail, level = "BLOCKED", result.get("news_blackout_reason"), logging.INFO
                elif result.get("risk_approved"):
                    outcome, detail, level = "TRADE", result.get("thesis"), logging.WARNING
                elif result.get("risk_rejection_reason"):
                    outcome, detail, level = "REJECTED", result.get("risk_rejection_reason"), logging.WARNING
                else:
                    outcome, detail, level = "WAIT", "no qualifying setup this cycle", logging.INFO
                stages = " ".join(f"{name}={ms:.0f}ms" for name, ms in result.get("stage_timings_ms", {}).items())
                logger.log(level, "[%s] %s — %s (%s, total=%.0fms)", symbol, outcome, detail, stages, result.get("cycle_total_ms", 0.0))
            except LLMBudgetExceededError as exc:
                logger.warning("[%s] LLM budget exceeded, skipping this cycle — %s", symbol, exc)
            except Exception:
                logger.exception("[%s] cycle error", symbol)

        if pass_had_success:
            consecutive_failed_passes = 0
        else:
            consecutive_failed_passes += 1
            logger.warning("full pass failed (every symbol errored) — %d/%d consecutive", consecutive_failed_passes, CONSECUTIVE_FAILED_PASSES_THRESHOLD)
            if consecutive_failed_passes >= CONSECUTIVE_FAILED_PASSES_THRESHOLD:
                logger.critical(
                    "%d consecutive full-pass failures — stopping (likely a dead credential or persistent outage, not a transient blip)",
                    consecutive_failed_passes,
                )
                sys.exit(CIRCUIT_BREAKER_EXIT_CODE)

        trim_log_file(log_file)
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
