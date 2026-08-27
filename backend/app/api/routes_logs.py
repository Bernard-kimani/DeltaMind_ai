"""Byte-offset log tailing, mirrored from the Logs tab's polling contract:
the client sends back the offset it was given, the server returns only the
lines written since then plus the new offset. Reading straight from the
agent loop's log file (rather than an in-memory buffer) means this survives
a backend restart and needs no coordination with agent_loop_manager.py.

Track 1 and Track 4 run as independent concurrent subprocesses with their
own log files (see agent_loop_manager.log_file_for_track) — every endpoint
here takes a `track` param to pick which one.
"""

from fastapi import APIRouter

from app.agent_loop_manager import log_file_for_track

router = APIRouter()


@router.get("/tail")
def tail(track: str, offset: int = 0) -> dict:
    log_file = log_file_for_track(track)
    if not log_file.exists():
        return {"lines": [], "new_offset": 0}

    with open(log_file, encoding="utf-8", errors="replace") as f:
        f.seek(offset)
        content = f.read()
        new_offset = f.tell()

    lines = content.splitlines() if content else []
    return {"lines": lines, "new_offset": new_offset}


@router.get("/stats")
def stats(track: str) -> dict:
    log_file = log_file_for_track(track)
    if not log_file.exists():
        return {"total_entries": 0, "file_size_bytes": 0}

    size = log_file.stat().st_size
    with open(log_file, encoding="utf-8", errors="replace") as f:
        total = sum(1 for _ in f)
    return {"total_entries": total, "file_size_bytes": size}


@router.post("/clear")
def clear(track: str) -> dict:
    log_file = log_file_for_track(track)
    if log_file.exists():
        log_file.write_text("", encoding="utf-8")
    return {"new_offset": 0}
