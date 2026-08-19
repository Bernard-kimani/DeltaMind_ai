from fastapi import APIRouter

from app.db.repository import list_agent_decisions, list_trades

router = APIRouter()


@router.get("")
def trades(limit: int = 100):
    """Trade/order history persisted from the execution node, for the dashboard's trade log."""
    return list_trades(limit=limit)


@router.get("/decisions")
def decisions(limit: int = 100):
    """Agent reasoning trail: thesis, signals, and risk-gate verdicts per cycle."""
    return list_agent_decisions(limit=limit)
