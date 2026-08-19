from fastapi import APIRouter
from pydantic import BaseModel

from app.agent_loop_manager import get_manager
from app.db.repository import get_decision_counts

router = APIRouter()


class StartRequest(BaseModel):
    symbols: str
    track: str
    interval_seconds: int = 300


@router.get("/status")
def status() -> dict:
    return get_manager().status()


@router.get("/stats")
def stats() -> dict:
    counts = get_decision_counts()
    return {"uptime": get_manager().uptime_label(), **counts}


@router.post("/start")
def start(body: StartRequest) -> dict:
    ok, message = get_manager().start(body.symbols, body.track, body.interval_seconds)
    return {"ok": ok, "message": message}


@router.post("/stop")
def stop() -> dict:
    ok, message = get_manager().stop()
    return {"ok": ok, "message": message}


@router.post("/restart")
def restart(body: StartRequest) -> dict:
    ok, message = get_manager().restart(body.symbols, body.track, body.interval_seconds)
    return {"ok": ok, "message": message}
