from fastapi import APIRouter

from app.agents.pnl_utils import compute_unrealized_pnl
from app.db.repository import get_track_pnl_summary, list_agent_decisions, list_trades

router = APIRouter()


@router.get("")
def trades(limit: int = 100, track: str | None = None):
    """Trade/order history persisted from the execution node, for the dashboard's trade log."""
    return list_trades(limit=limit, track=track)


@router.get("/decisions")
def decisions(limit: int = 100, track: str | None = None):
    """Agent reasoning trail: thesis, signals, and risk-gate verdicts per cycle."""
    return list_agent_decisions(limit=limit, track=track)


@router.get("/pnl-summary")
def pnl_summary():
    """Realized (closed trades) + unrealized (open trades, live-repriced)
    P&L per track — backs the Controls tab's Track P&L card."""
    realized = {row["track"]: row for row in get_track_pnl_summary()}
    tracks = set(realized) | {"track1_alpha_spreads", "track4_income_wheel"}

    summary = []
    for track in tracks:
        row = realized.get(track, {"track": track, "realized_pnl": 0.0, "open_count": 0, "closed_count": 0, "win_count": 0})
        unrealized_pnl, matched_positions = compute_unrealized_pnl(track)
        summary.append({
            **row,
            "unrealized_pnl": unrealized_pnl,
            "matched_open_positions": matched_positions,
        })
    return summary
