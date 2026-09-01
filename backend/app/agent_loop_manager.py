"""Lifecycle manager for the live agent loop (scripts/run_agent_loop.py),
launched as a real OS subprocess — not an in-process thread — so it survives
independently of the FastAPI request/response cycle and terminates cleanly
via SIGTERM/kill rather than needing cooperative shutdown logic.

One `AgentLoopManager` per track, not a global singleton: Track 1 and
Track 4 need to run concurrently (separate subprocesses, separate log
files, separate status) so their performance can be compared over the same
market week rather than sequentially. `get_manager(track)` lazily creates
and caches one instance per track string — any track name works, but only
track1_alpha_spreads/track4_income_wheel are exercised by the Controls UI
today.

The subprocess configures its own file logging (see run_agent_loop.py), so
this manager only owns process lifecycle (start/stop/restart/status); log
content is read separately by app/api/routes_logs.py via byte-offset tailing
of the same file, which keeps "is it running" and "what did it log" as two
independently-recoverable concerns.

A daemon watchdog thread polls the subprocess and auto-restarts it on an
unexpected death (crash, not an explicit Stop click) with backoff — nothing
did this before, so a transient crash would silently end trading until a
human noticed. It does NOT auto-restart past the rate-limiting circuit
breaker's distinct exit code (see app/rate_limits.py) — that exit means a
persistent failure (dead credential, sustained outage), and restarting into
the same failure defeats the point of the breaker.
"""

import logging
import os
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from app.config import get_alpaca_credentials
from app.db import repository as db_repo
from app.rate_limits import CIRCUIT_BREAKER_EXIT_CODE

BACKEND_DIR = Path(__file__).resolve().parent.parent

WATCHDOG_POLL_SECONDS = 15
MAX_AUTO_RESTARTS = 20
AUTO_RESTART_BACKOFF_SECONDS = [5, 15, 30, 60, 120]  # last value repeats past this index

logger = logging.getLogger(__name__)


def log_file_for_track(track: str) -> Path:
    """Must match the formula scripts/run_agent_loop.py uses independently
    (deliberately not imported from there — that script is meant to run as
    a standalone subprocess with no coupling back to this module)."""
    return BACKEND_DIR / "logs" / f"agent_loop_{track}.log"


class AgentLoopManager:
    def __init__(self, track: str) -> None:
        self.track = track
        self.log_file = log_file_for_track(track)
        self.process: subprocess.Popen | None = None
        self.started_at: datetime | None = None
        self._last_start_args: dict | None = None
        self._user_stopped = True
        self._auto_restart_count = 0
        self._circuit_breaker_tripped = False
        self._last_crash_reason: str | None = None
        self._watchdog_thread = threading.Thread(target=self._watchdog_loop, daemon=True)
        self._watchdog_thread.start()

    def is_running(self) -> bool:
        return self.process is not None and self.process.poll() is None

    def _spawn(self, symbols: str, interval_seconds: int, sentiment_threshold: float, volume_ratio_min: float) -> tuple[bool, str]:
        self.log_file.parent.mkdir(parents=True, exist_ok=True)
        if self.track in ("track1_alpha_spreads", "track5_momentum_swing"):
            # Track 1 (and Track 5, its looser sibling — see
            # run_agent_stream_track1.py's own --track argument) run a real
            # Alpaca websocket stream (bar-close triggered, no fixed
            # interval) instead of the interval-polling script every other
            # track uses. interval_seconds/sentiment_threshold/volume_ratio_min
            # don't apply to either of them, so they're silently ignored
            # here rather than forwarded.
            cmd = [
                sys.executable,
                str(BACKEND_DIR / "scripts" / "run_agent_stream_track1.py"),
                "--symbols", symbols,
                "--track", self.track,
            ]
        else:
            cmd = [
                sys.executable,
                str(BACKEND_DIR / "scripts" / "run_agent_loop.py"),
                "--symbols", symbols,
                "--track", self.track,
                "--interval", str(interval_seconds),
                "--sentiment-threshold", str(sentiment_threshold),
                "--volume-ratio-min", str(volume_ratio_min),
            ]
        # Each track is already a separate OS subprocess — giving it its own
        # ALPACA_API_KEY/SECRET_KEY here (rather than inheriting whatever the
        # backend process's own .env has) is what actually separates the two
        # accounts: app.config.Settings reads real process env over .env, and
        # rest_client.py's cached clients / mcp_client.py's MCP subprocess env
        # both read from *this* process's settings — see get_alpaca_credentials.
        api_key, secret_key = get_alpaca_credentials(self.track)
        env = os.environ.copy()
        env["ALPACA_API_KEY"] = api_key
        env["ALPACA_SECRET_KEY"] = secret_key
        try:
            self.process = subprocess.Popen(cmd, cwd=str(BACKEND_DIR), env=env)
        except Exception as exc:
            return False, f"Failed to start agent engine: {exc}"

        time.sleep(0.5)
        if self.process.poll() is not None:
            code = self.process.returncode
            self.process = None
            return False, f"Agent process exited immediately (code {code}) — check the Logs tab"

        self.started_at = datetime.now(timezone.utc)
        return True, f"Agent engine started (pid {self.process.pid})"

    def start(self, symbols: str, interval_seconds: int, sentiment_threshold: float = 0.5, volume_ratio_min: float = 1.2) -> tuple[bool, str]:
        if self.is_running():
            return False, f"{self.track} engine is already running"

        self._last_start_args = {
            "symbols": symbols,
            "interval_seconds": interval_seconds,
            "sentiment_threshold": sentiment_threshold,
            "volume_ratio_min": volume_ratio_min,
        }
        self._user_stopped = False
        self._auto_restart_count = 0
        self._circuit_breaker_tripped = False
        self._last_crash_reason = None

        ok, message = self._spawn(symbols, interval_seconds, sentiment_threshold, volume_ratio_min)
        if ok:
            db_repo.save_engine_run_state(self.track, symbols, interval_seconds, sentiment_threshold, volume_ratio_min)
        else:
            self._user_stopped = True
        return ok, message

    def stop(self) -> tuple[bool, str]:
        self._user_stopped = True
        db_repo.clear_engine_run_state(self.track)

        if not self.is_running():
            self.process = None
            return True, f"{self.track} engine is not running"

        assert self.process is not None
        self.process.terminate()
        try:
            self.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait()

        self.process = None
        self.started_at = None
        return True, f"{self.track} engine stopped"

    def restart(self, symbols: str, interval_seconds: int, sentiment_threshold: float = 0.5, volume_ratio_min: float = 1.2) -> tuple[bool, str]:
        self.stop()
        return self.start(symbols, interval_seconds, sentiment_threshold, volume_ratio_min)

    def auto_resume_if_needed(self) -> None:
        """Called once per known-run-state track from main.py's startup
        hook. If the backend process itself was restarted (crash, reboot,
        manual restart) while this track's engine was running, resumes
        trading with the same args instead of requiring the user to notice
        and click Start again."""
        state = db_repo.load_engine_run_state(self.track)
        if state is None:
            return
        logger.info("[%s] auto-resuming agent engine after backend restart — %s", self.track, state)
        ok, message = self.start(
            state["symbols"], state["interval_seconds"],
            state.get("sentiment_threshold", 0.5), state.get("volume_ratio_min", 1.2),
        )
        if not ok:
            logger.error("[%s] auto-resume failed: %s", self.track, message)

    def _watchdog_loop(self) -> None:
        while True:
            time.sleep(WATCHDOG_POLL_SECONDS)
            self._check_and_restart()

    def _check_and_restart(self) -> None:
        if self._user_stopped or self.process is None:
            return
        returncode = self.process.poll()
        if returncode is None:
            return  # still alive

        self.process = None
        self.started_at = None

        if returncode == CIRCUIT_BREAKER_EXIT_CODE:
            self._circuit_breaker_tripped = True
            self._last_crash_reason = "Circuit breaker tripped (repeated consecutive failures) — see Logs tab, needs manual intervention"
            logger.critical("[%s] agent loop hit its circuit breaker — not auto-restarting, needs a human", self.track)
            return

        self._last_crash_reason = f"Process exited unexpectedly (code {returncode})"
        if self._auto_restart_count >= MAX_AUTO_RESTARTS:
            logger.error("[%s] agent loop crashed %d times — giving up on auto-restart", self.track, self._auto_restart_count)
            return

        backoff_index = min(self._auto_restart_count, len(AUTO_RESTART_BACKOFF_SECONDS) - 1)
        delay = AUTO_RESTART_BACKOFF_SECONDS[backoff_index]
        logger.warning("[%s] agent loop crashed (code %s) — auto-restarting in %ss (attempt %d/%d)", self.track, returncode, delay, self._auto_restart_count + 1, MAX_AUTO_RESTARTS)
        time.sleep(delay)

        assert self._last_start_args is not None
        self._auto_restart_count += 1
        ok, message = self._spawn(**self._last_start_args)
        if not ok:
            logger.error("[%s] auto-restart failed: %s", self.track, message)

    def status(self) -> dict:
        return {
            "track": self.track,
            "is_running": self.is_running(),
            "pid": self.process.pid if self.is_running() else None,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "auto_restart_count": self._auto_restart_count,
            "circuit_breaker_tripped": self._circuit_breaker_tripped,
            "last_crash_reason": self._last_crash_reason,
        }

    def uptime_label(self) -> str:
        if not self.is_running() or not self.started_at:
            return "Not running"
        delta = datetime.now(timezone.utc) - self.started_at
        hours, remainder = divmod(int(delta.total_seconds()), 3600)
        minutes, seconds = divmod(remainder, 60)
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


_managers: dict[str, AgentLoopManager] = {}


def get_manager(track: str) -> AgentLoopManager:
    if track not in _managers:
        _managers[track] = AgentLoopManager(track)
    return _managers[track]
