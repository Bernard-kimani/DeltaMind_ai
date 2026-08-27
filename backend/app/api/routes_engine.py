from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.agent_loop_manager import get_manager
from app.db.repository import get_decision_counts
from app.rate_limits import MIN_INTERVAL_SECONDS

router = APIRouter()


class StartRequest(BaseModel):
    track: str
    symbols: str
    interval_seconds: int = Field(default=300, ge=MIN_INTERVAL_SECONDS)
    sentiment_threshold: float = Field(default=0.5, gt=0, le=1)
    # Floored at 1.0 — below that, "volume ratio" would mean below-average
    # volume "confirming" a breakout, which is backwards.
    volume_ratio_min: float = Field(default=1.2, ge=1.0)


class TrackRequest(BaseModel):
    track: str


@router.get("/status")
def status(track: str) -> dict:
    return get_manager(track).status()


@router.get("/stats")
def stats(track: str) -> dict:
    counts = get_decision_counts(track=track)
    return {"uptime": get_manager(track).uptime_label(), **counts}


@router.post("/start")
def start(body: StartRequest) -> dict:
    ok, message = get_manager(body.track).start(
        body.symbols, body.interval_seconds, body.sentiment_threshold, body.volume_ratio_min
    )
    return {"ok": ok, "message": message}


@router.post("/stop")
def stop(body: TrackRequest) -> dict:
    ok, message = get_manager(body.track).stop()
    return {"ok": ok, "message": message}


@router.post("/restart")
def restart(body: StartRequest) -> dict:
    ok, message = get_manager(body.track).restart(
        body.symbols, body.interval_seconds, body.sentiment_threshold, body.volume_ratio_min
    )
    return {"ok": ok, "message": message}
