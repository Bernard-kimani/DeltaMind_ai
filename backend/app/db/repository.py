"""Data-access layer — every DB read/write in the app goes through here, so
the storage backend (SQLite now, Supabase Postgres later) stays swappable
behind a stable function-based interface instead of scattered ORM calls.
"""

import datetime as dt

from sqlalchemy import func, select

from app.db.models import AgentDecision, BacktestRun, Trade, WheelState
from app.db.session import get_session


def save_trade(symbol: str, order: dict, result: dict, thesis: str = "", track: str | None = None) -> None:
    with get_session() as session:
        session.add(Trade(symbol=symbol, track=track, order=order, result=result, thesis=thesis, status="open"))
        session.commit()


def list_open_trades(track: str | None = None) -> list[dict]:
    """Backs position_monitor.py's sweep — the DB-side half of "what did we
    open, and what did we pay/collect for it" needed to compute unrealized
    P&L against a freshly re-priced chain."""
    with get_session() as session:
        query = select(Trade).where(Trade.status == "open")
        if track is not None:
            query = query.where(Trade.track == track)
        rows = session.scalars(query.order_by(Trade.created_at.desc())).all()
        return [
            {
                "id": r.id,
                "created_at": r.created_at.isoformat(),
                "symbol": r.symbol,
                "track": r.track,
                "order": r.order,
                "result": r.result,
                "thesis": r.thesis,
            }
            for r in rows
        ]


def close_trade(trade_id: int, realized_pnl: float) -> None:
    with get_session() as session:
        trade = session.get(Trade, trade_id)
        if trade is None:
            return
        trade.status = "closed"
        trade.closed_at = dt.datetime.utcnow()
        trade.realized_pnl = realized_pnl
        session.commit()


def get_wheel_state(symbol: str) -> bool:
    with get_session() as session:
        row = session.get(WheelState, symbol)
        return row.holds_shares if row else False


def set_wheel_state(symbol: str, holds_shares: bool) -> None:
    with get_session() as session:
        row = session.get(WheelState, symbol)
        if row is None:
            session.add(WheelState(symbol=symbol, holds_shares=holds_shares))
        else:
            row.holds_shares = holds_shares
        session.commit()


def list_trades(limit: int = 100) -> list[dict]:
    with get_session() as session:
        rows = session.scalars(select(Trade).order_by(Trade.created_at.desc()).limit(limit)).all()
        return [
            {
                "id": r.id,
                "created_at": r.created_at.isoformat(),
                "symbol": r.symbol,
                "track": r.track,
                "order": r.order,
                "result": r.result,
                "thesis": r.thesis,
            }
            for r in rows
        ]


def save_agent_decision(**kwargs) -> None:
    with get_session() as session:
        session.add(AgentDecision(**kwargs))
        session.commit()


def list_agent_decisions(limit: int = 100) -> list[dict]:
    with get_session() as session:
        rows = session.scalars(
            select(AgentDecision).order_by(AgentDecision.created_at.desc()).limit(limit)
        ).all()
        return [
            {
                "id": r.id,
                "created_at": r.created_at.isoformat(),
                "symbol": r.symbol,
                "track": r.track,
                "sentiment_score": r.sentiment_score,
                "thesis": r.thesis,
                "proposed_order": r.proposed_order,
                "risk_approved": r.risk_approved,
                "risk_rejection_reason": r.risk_rejection_reason,
            }
            for r in rows
        ]


def get_decision_counts() -> dict:
    """Telemetry numbers for the Controls tab — total cycles run, trades
    the risk gate approved, cycles it rejected/vetoed, and the most recent
    decision's timestamp."""
    with get_session() as session:
        total = session.scalar(select(func.count()).select_from(AgentDecision)) or 0
        approved = session.scalar(select(func.count()).where(AgentDecision.risk_approved.is_(True))) or 0
        rejected = session.scalar(select(func.count()).where(AgentDecision.risk_approved.is_(False))) or 0
        last_created = session.scalar(select(func.max(AgentDecision.created_at)))
        return {
            "total_cycles": total,
            "approved_trades": approved,
            "rejected_cycles": rejected,
            "last_decision_time": last_created.isoformat() if last_created else None,
        }


def save_backtest_run(symbol: str, track: str, start_date: str, end_date: str, results: dict) -> None:
    with get_session() as session:
        session.add(
            BacktestRun(symbol=symbol, track=track, start_date=start_date, end_date=end_date, results=results)
        )
        session.commit()


def get_iv_52wk_range(symbol: str) -> tuple[float, float]:
    """52-week IV min/max for iv_percentile.py. TODO: back this with a real
    historical-IV table populated by backtest/data_loader.py; returns a
    placeholder wide range until that's wired up so quant_engine.py doesn't
    crash on a fresh DB.
    """
    return 0.10, 0.90
