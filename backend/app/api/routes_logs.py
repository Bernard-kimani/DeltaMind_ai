"""Byte-offset log tailing, mirrored from the Logs tab's polling contract:
the client sends back the offset it was given, the server returns only the
lines written since then plus the new offset. Reading straight from the
agent loop's log file (rather than an in-memory buffer) means this survives
a backend restart and needs no coordination with agent_loop_manager.py.
"""

from fastapi import APIRouter

from app.agent_loop_manager import LOG_FILE

router = APIRouter()


@router.get("/tail")
def tail(offset: int = 0) -> dict:
    if not LOG_FILE.exists():
        return {"lines": [], "new_offset": 0}

    with open(LOG_FILE, encoding="utf-8", errors="replace") as f:
        f.seek(offset)
        content = f.read()
        new_offset = f.tell()

    lines = content.splitlines() if content else []
    return {"lines": lines, "new_offset": new_offset}


@router.get("/stats")
def stats() -> dict:
    if not LOG_FILE.exists():
        return {"total_entries": 0, "file_size_bytes": 0}

    size = LOG_FILE.stat().st_size
    with open(LOG_FILE, encoding="utf-8", errors="replace") as f:
        total = sum(1 for _ in f)
    return {"total_entries": total, "file_size_bytes": size}


@router.post("/clear")
def clear() -> dict:
    if LOG_FILE.exists():
        LOG_FILE.write_text("", encoding="utf-8")
    return {"new_offset": 0}
