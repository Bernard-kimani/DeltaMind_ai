"""SQLAlchemy models — provider-agnostic by design. Runs on SQLite for the
hackathon (DATABASE_URL=sqlite:///./deltamind.db); pointing DATABASE_URL at
Supabase's Postgres connection string later requires zero changes here.
"""

import datetime as dt

from sqlalchemy import JSON, DateTime, Float, Integer, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Trade(Base):
    __tablename__ = "trades"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow)
    symbol: Mapped[str] = mapped_column(String)
    track: Mapped[str] = mapped_column(String, nullable=True)
    order: Mapped[dict] = mapped_column(JSON)
    result: Mapped[dict] = mapped_column(JSON)
    thesis: Mapped[str] = mapped_column(String, nullable=True)
    # "open"/"closed" — lets position_monitor.py know which DB row a given
    # live Alpaca position corresponds to, and recover the net debit paid
    # (Track 1) or premium collected (Track 4) for P&L math without
    # re-deriving it from the order JSON every sweep.
    status: Mapped[str] = mapped_column(String, default="open")
    closed_at: Mapped[dt.datetime] = mapped_column(DateTime, nullable=True)
    realized_pnl: Mapped[float] = mapped_column(Float, nullable=True)


class AgentDecision(Base):
    """Every cycle's outcome, including rejected proposals — the full
    reasoning trail judges can audit for Technology Implementation scoring.
    """

    __tablename__ = "agent_decisions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow)
    symbol: Mapped[str] = mapped_column(String)
    track: Mapped[str] = mapped_column(String)
    sentiment_score: Mapped[float] = mapped_column(Float, nullable=True)
    thesis: Mapped[str] = mapped_column(String, nullable=True)
    proposed_order: Mapped[dict] = mapped_column(JSON, nullable=True)
    risk_approved: Mapped[bool] = mapped_column(nullable=True)
    risk_rejection_reason: Mapped[str] = mapped_column(String, nullable=True)


class WheelState(Base):
    """One row per symbol: whether Track 4's wheel currently holds assigned
    shares (sell covered calls) or not (sell cash-secured puts). Written by
    position_monitor.py's sweep, read by quant_engine.py's
    portfolio_risk_snapshot() — see track4_income_wheel.py's
    `holds_underlying_shares` gap.
    """

    __tablename__ = "wheel_state"

    symbol: Mapped[str] = mapped_column(String, primary_key=True)
    holds_shares: Mapped[bool] = mapped_column(default=False)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow, onupdate=dt.datetime.utcnow)


class BacktestRun(Base):
    __tablename__ = "backtest_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow)
    symbol: Mapped[str] = mapped_column(String)
    track: Mapped[str] = mapped_column(String)
    start_date: Mapped[str] = mapped_column(String)
    end_date: Mapped[str] = mapped_column(String)
    results: Mapped[dict] = mapped_column(JSON)
