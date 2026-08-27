"""Track 1's live entrypoint — bar-close-triggered via a real Alpaca
websocket stream, not interval polling (see scripts/run_agent_loop.py, which
Track 4 still uses unchanged). Every time a symbol's 1-minute bar closes,
one LangGraph decision cycle runs for it immediately — no `--interval` flag,
no fixed sleep between passes. Position exits (partial take-profit, full
exit, stop-loss, time-stop, EOD liquidation) run on their own fixed ~15s
cadence in parallel, since exits aren't bar-triggered (see
app/agents/position_monitor.py).

Usage:
    uv run python scripts/run_agent_stream_track1.py --symbols SPY,QQQ,NVDA

Normally launched as a subprocess by app/agent_loop_manager.py (the Controls
tab's Start/Stop/Restart buttons, when track=track1_alpha_spreads).

Architecture note: `StockDataStream.run()` blocks and manages its own
asyncio event loop internally, so it's run in a background daemon thread;
its async bar-close handler dispatches the (synchronous) per-symbol
LangGraph pipeline via `asyncio.to_thread(...)` — required, not just
convenient: `mcp_client.py`'s `_run()` calls `asyncio.run(...)` for every
Alpaca trading/news call, which raises if called from the stream's own
already-running event loop; a worker thread has no running loop of its own,
so the nested `asyncio.run()` works there. The main thread stays a plain
synchronous loop doing the position-exit sweep — no need for the two
concerns to share one event loop.
"""

import argparse
import asyncio
import ctypes
import logging
import sys
import threading
import time
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.rate_limits import CIRCUIT_BREAKER_EXIT_CODE, CONSECUTIVE_FAILED_PASSES_THRESHOLD  # noqa: E402

logger = logging.getLogger("agent_stream_track1")

TRACK = "track1_alpha_spreads"
SWEEP_INTERVAL_SECONDS = 15
# Target: candle-close to cycle-complete (WAIT/TRADE/REJECTED, including a
# real Alpaca order placement on a qualifying+approved cycle) should stay
# under this. graph.py's per-node timings (logged separately, same file)
# say WHERE the time went when this budget is blown.
LATENCY_BUDGET_MS = 2000


def _log_file_for_track(track: str) -> Path:
    """Must match the formula scripts/run_agent_loop.py and
    agent_loop_manager.py each use independently (deliberately duplicated,
    not imported — see run_agent_loop.py's identical comment)."""
    return BACKEND_DIR / "logs" / f"agent_loop_{track}.log"


ES_CONTINUOUS = 0x80000000
ES_SYSTEM_REQUIRED = 0x00000001


def _prevent_sleep() -> None:
    """Blocks Windows inactivity sleep for as long as this process is
    alive. No-op (and safe to call) on non-Windows. Duplicated from
    run_agent_loop.py — see that file's identical function."""
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


# Shared between the stream's background thread (writes, on a bar-close
# failure) and the main thread (reads, once per sweep tick) — a
# threading.Event and a lock-guarded int are enough here; no asyncio
# primitives, since the two sides are genuinely different OS threads, not
# two coroutines on one loop.
_circuit_breaker_tripped = threading.Event()
_failure_lock = threading.Lock()
_consecutive_failures = 0


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbols", required=True, help="comma-separated, e.g. SPY,QQQ")
    args = parser.parse_args()

    log_file = _log_file_for_track(TRACK)
    _configure_logging(log_file)
    symbols = [s.strip() for s in args.symbols.split(",")]
    logger.info("Track 1 streaming agent starting — symbols=%s (bar-close-triggered, no fixed interval)", symbols)
    logger.info("Importing agent graph and dependencies (LangGraph, Alpaca SDK, LLM clients)...")

    from alpaca.data.live import StockDataStream

    from app.agents.graph import run_cycle
    from app.agents.position_monitor import sweep_positions
    from app.config import get_settings
    from app.db.repository import save_agent_decision
    from app.llm.rate_limiter import LLMBudgetExceededError

    logger.info("Imports complete — connecting to Alpaca stream")

    settings = get_settings()
    stream = StockDataStream(settings.alpaca_api_key, settings.alpaca_secret_key)

    def _run_and_persist(symbol: str) -> dict:
        result = run_cycle(symbol=symbol, track=TRACK)
        save_agent_decision(
            symbol=symbol,
            track=TRACK,
            sentiment_score=result.get("sentiment_score"),
            thesis=result.get("thesis"),
            proposed_order=result.get("proposed_order"),
            risk_approved=result.get("risk_approved"),
            risk_rejection_reason=result.get("risk_rejection_reason"),
        )
        return result

    def _process_symbol(symbol: str, label: str = "bar close", candle_close_at: float | None = None) -> None:
        """Runs one cycle for `symbol` and updates the shared failure
        counter / circuit breaker. Called both by the immediate warmup pass
        below (synchronously, once per symbol right after connecting) and
        by every subsequent bar-close event (via asyncio.to_thread, from
        _handle_bar_close) — same logic either way, since both are just
        "a fresh REST-fetched window is ready to be screened right now."

        `candle_close_at` (a time.monotonic() reading taken the instant the
        websocket delivered the bar, in `_on_bar` — before any dispatch
        overhead) is only set for real bar-close events, not the warmup
        pass (which has no external "candle updated" moment to time from).
        This is the number the sub-2-second goal is actually about — it
        includes asyncio.to_thread's own dispatch latency, unlike graph.py's
        internal per-node timings."""
        global _consecutive_failures
        try:
            result = _run_and_persist(symbol)
            with _failure_lock:
                _consecutive_failures = 0
            if result.get("news_blackout_reason"):
                logger.info("[%s] BLOCKED — %s", symbol, result.get("news_blackout_reason"))
            elif result.get("risk_approved"):
                logger.info("[%s] TRADE — %s", symbol, result.get("thesis"))
            elif result.get("risk_rejection_reason"):
                logger.warning("[%s] REJECTED — %s", symbol, result.get("risk_rejection_reason"))
            else:
                logger.info("[%s] WAIT — no qualifying setup this %s", symbol, label)
            if candle_close_at is not None:
                total_ms = (time.monotonic() - candle_close_at) * 1000
                over_budget = total_ms > LATENCY_BUDGET_MS
                (logger.warning if over_budget else logger.info)(
                    "[%s] candle-close-to-decision latency: %.0fms%s",
                    symbol, total_ms, f" — EXCEEDS {LATENCY_BUDGET_MS:.0f}ms budget" if over_budget else "",
                )
        except LLMBudgetExceededError as exc:
            logger.warning("[%s] LLM budget exceeded, skipping this %s — %s", symbol, label, exc)
        except Exception:
            logger.exception("[%s] %s cycle error", symbol, label)
            with _failure_lock:
                _consecutive_failures += 1
                failures = _consecutive_failures
            logger.warning("consecutive failures: %d/%d", failures, CONSECUTIVE_FAILED_PASSES_THRESHOLD)
            if failures >= CONSECUTIVE_FAILED_PASSES_THRESHOLD:
                logger.critical(
                    "%d consecutive failures — stopping (likely a dead credential or persistent outage, not a transient blip)",
                    failures,
                )
                _circuit_breaker_tripped.set()

    async def _handle_bar_close(symbol: str, candle_close_at: float) -> None:
        if _circuit_breaker_tripped.is_set():
            return
        await asyncio.to_thread(_process_symbol, symbol, "bar close", candle_close_at)

    async def _on_bar(bar) -> None:
        # Captured here, not inside _handle_bar_close/_process_symbol — this
        # is the earliest point the websocket has actually delivered the
        # closed candle, so it's the real zero point for the sub-2-second
        # candle-to-decision latency goal (includes asyncio.create_task's
        # own scheduling delay and to_thread's dispatch overhead, both of
        # which are real latency, not measurement noise to exclude).
        candle_close_at = time.monotonic()
        # Every invocation IS a new, already-closed bar — Alpaca's `bars`
        # websocket channel only fires once a minute has fully elapsed
        # (unlike `quotes`/`trades`, there's no "still forming, will update"
        # message for the in-progress candle on this channel), and every
        # cycle re-fetches its own window fresh via REST (see
        # market_ingestion.py/quant_engine.py) rather than appending to a
        # buffer of our own — so there's no risk of screening against a
        # partial candle, and no separate "is this an update or a new bar"
        # branch needed: each fetch is simply authoritative as of right now.
        asyncio.create_task(_handle_bar_close(bar.symbol, candle_close_at))

    stream.subscribe_bars(_on_bar, *symbols)

    stream_thread = threading.Thread(target=stream.run, daemon=True, name="alpaca-stream")
    stream_thread.start()
    logger.info("Stream connection thread started")

    # Don't wait for the first natural bar-close event (up to ~60s of dead
    # time otherwise) — the full historical window is already available via
    # REST the instant we connect, so screen every symbol once immediately.
    # From here on, each bar-close event naturally slides that same window
    # forward one bar at a time.
    logger.info("Running immediate warmup pass for all %d symbols (full historical window via REST, not waiting for the first bar close)", len(symbols))
    for symbol in symbols:
        if _circuit_breaker_tripped.is_set():
            break
        _process_symbol(symbol, "warmup pass")
    logger.info("Warmup pass complete — now waiting for live bar-close events")

    while True:
        _prevent_sleep()

        if _circuit_breaker_tripped.is_set():
            logger.critical("circuit breaker tripped — stopping stream and exiting")
            stream.stop()
            sys.exit(CIRCUIT_BREAKER_EXIT_CODE)

        try:
            for action in sweep_positions(TRACK):
                logger.info("[%s] monitor: %s", action["symbol"], action["action"])
        except Exception:
            logger.exception("position monitor sweep failed")

        time.sleep(SWEEP_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
