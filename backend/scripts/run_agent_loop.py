"""Main entrypoint for the live hackathon-week agent loop (Aug 28 - Sep 4).

Runs one LangGraph decision cycle per watched symbol every INTERVAL_SECONDS,
persists the full decision trail (including rejections) via
app.db.repository, and logs every cycle to logs/agent_loop.log in the format
the dashboard's Logs tab parses (see app/api/routes_logs.py).

Usage:
    uv run python scripts/run_agent_loop.py --symbols SPY,QQQ --track track1_alpha_spreads --interval 300

Normally launched as a subprocess by app/agent_loop_manager.py (the
Controls tab's Start/Stop/Restart buttons); can also be run standalone for
the Day 1 hackathon deploy — see PLAN.md > Setup > Day 1 checklist.
"""

import argparse
import logging
import sys
import time
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

LOG_FILE = BACKEND_DIR / "logs" / "agent_loop.log"
logger = logging.getLogger("agent_loop")


def _configure_logging() -> None:
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[logging.FileHandler(LOG_FILE, encoding="utf-8"), logging.StreamHandler(sys.stdout)],
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
    args = parser.parse_args()

    # Logging is configured — and writes its first line — before the heavy
    # imports below (LangGraph, alpaca-py, openai/anthropic SDKs take ~10s
    # cold). Without this ordering, the Logs tab looks dead for that whole
    # window instead of showing the process is alive and importing.
    _configure_logging()
    symbols = [s.strip() for s in args.symbols.split(",")]
    logger.info("Agent loop process starting — symbols=%s track=%s interval=%ss", symbols, args.track, args.interval)
    logger.info("Importing agent graph and dependencies (LangGraph, Alpaca SDK, LLM clients)...")

    from app.agents.graph import run_cycle
    from app.agents.position_monitor import sweep_positions
    from app.db.repository import save_agent_decision

    logger.info("Imports complete — entering live decision loop")

    while True:
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
                result = run_cycle(symbol=symbol, track=args.track)
                save_agent_decision(
                    symbol=symbol,
                    track=args.track,
                    sentiment_score=result.get("sentiment_score"),
                    thesis=result.get("thesis"),
                    proposed_order=result.get("proposed_order"),
                    risk_approved=result.get("risk_approved"),
                    risk_rejection_reason=result.get("risk_rejection_reason"),
                )
                if result.get("risk_approved"):
                    logger.info("[%s] TRADE — %s", symbol, result.get("thesis"))
                elif result.get("risk_rejection_reason"):
                    logger.warning("[%s] REJECTED — %s", symbol, result.get("risk_rejection_reason"))
                else:
                    logger.info("[%s] WAIT — no qualifying setup this cycle", symbol)
            except Exception:
                logger.exception("[%s] cycle error", symbol)

        time.sleep(args.interval)


if __name__ == "__main__":
    main()
