from fastapi import APIRouter
from pydantic import BaseModel

from app.backtest.runner import run_backtest

router = APIRouter()


class BacktestRequest(BaseModel):
    symbol: str
    track: str  # track1_alpha_spreads | track2_volatility_events | track3_hedging | track4_income_wheel
    start: str  # ISO date
    end: str  # ISO date


@router.post("")
def backtest(req: BacktestRequest):
    """Run a strategy against historical data. Pre-hackathon use only — see PLAN.md."""
    return run_backtest(symbol=req.symbol, track=req.track, start=req.start, end=req.end)
