"""Lifecycle manager for the live agent loop (scripts/run_agent_loop.py),
launched as a real OS subprocess — not an in-process thread — so it survives
independently of the FastAPI request/response cycle and terminates cleanly
via SIGTERM/kill rather than needing cooperative shutdown logic.

The subprocess configures its own file logging (see run_agent_loop.py), so
this manager only owns process lifecycle (start/stop/restart/status); log
content is read separately by app/api/routes_logs.py via byte-offset tailing
of the same file, which keeps "is it running" and "what did it log" as two
independently-recoverable concerns.
"""

import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
LOG_FILE = BACKEND_DIR / "logs" / "agent_loop.log"


class AgentLoopManager:
    def __init__(self) -> None:
        self.process: subprocess.Popen | None = None
        self.started_at: datetime | None = None

    def is_running(self) -> bool:
        return self.process is not None and self.process.poll() is None

    def start(self, symbols: str, track: str, interval_seconds: int) -> tuple[bool, str]:
        if self.is_running():
            return False, "Agent engine is already running"

        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        cmd = [
            sys.executable,
            str(BACKEND_DIR / "scripts" / "run_agent_loop.py"),
            "--symbols", symbols,
            "--track", track,
            "--interval", str(interval_seconds),
        ]
        try:
            self.process = subprocess.Popen(cmd, cwd=str(BACKEND_DIR))
        except Exception as exc:
            return False, f"Failed to start agent engine: {exc}"

        time.sleep(0.5)
        if self.process.poll() is not None:
            code = self.process.returncode
            self.process = None
            return False, f"Agent process exited immediately (code {code}) — check the Logs tab"

        self.started_at = datetime.now(timezone.utc)
        return True, f"Agent engine started (pid {self.process.pid})"

    def stop(self) -> tuple[bool, str]:
        if not self.is_running():
            self.process = None
            return True, "Agent engine is not running"

        assert self.process is not None
        self.process.terminate()
        try:
            self.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait()

        self.process = None
        self.started_at = None
        return True, "Agent engine stopped"

    def restart(self, symbols: str, track: str, interval_seconds: int) -> tuple[bool, str]:
        self.stop()
        return self.start(symbols, track, interval_seconds)

    def status(self) -> dict:
        return {
            "is_running": self.is_running(),
            "pid": self.process.pid if self.is_running() else None,
            "started_at": self.started_at.isoformat() if self.started_at else None,
        }

    def uptime_label(self) -> str:
        if not self.is_running() or not self.started_at:
            return "Not running"
        delta = datetime.now(timezone.utc) - self.started_at
        hours, remainder = divmod(int(delta.total_seconds()), 3600)
        minutes, seconds = divmod(remainder, 60)
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


_manager = AgentLoopManager()


def get_manager() -> AgentLoopManager:
    return _manager
