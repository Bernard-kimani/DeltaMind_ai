"""Keeps each track's log file capped at roughly MAX_LOG_LINES by trimming
from the top — an unattended multi-hour/multi-day run otherwise grows the
file unboundedly (every /api/logs/tail poll re-reading more of it, and
Render's disk isn't infinite either).

Called periodically from each engine script's own already-existing main
loop (see run_agent_stream_track1.py/run_agent_loop.py) rather than hooked
into the logging Handler itself — reopening a FileHandler's stream mid-flight
to survive an external rewrite is more fragile than just doing the trim
between cycles, and "roughly the latest N lines" doesn't need to be exact.

routes_logs.py's /tail endpoint self-heals against the byte-offset shift a
trim causes: if a client's stored offset ends up past the (now-smaller)
file size, it resets to 0 rather than getting stuck.
"""

from pathlib import Path

MAX_LOG_LINES = 2000


def trim_log_file(log_file: Path, max_lines: int = MAX_LOG_LINES) -> None:
    if not log_file.exists():
        return
    with open(log_file, encoding="utf-8", errors="replace") as f:
        lines = f.readlines()
    if len(lines) <= max_lines:
        return
    with open(log_file, "w", encoding="utf-8") as f:
        f.writelines(lines[-max_lines:])
