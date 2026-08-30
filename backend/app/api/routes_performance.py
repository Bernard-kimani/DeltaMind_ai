from fastapi import APIRouter

from app.db.repository import get_performance_metrics

router = APIRouter()


@router.get("")
def performance(track: str):
    """Cumulative realized-P&L series + trade-level Sharpe/profit-factor/
    recovery-factor for the Performance page — see get_performance_metrics's
    docstring for what these ratios do and don't mean without a daily
    equity-curve snapshot."""
    return get_performance_metrics(track)
