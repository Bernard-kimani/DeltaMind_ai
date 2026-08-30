"""Data-access layer — every DB read/write in the app goes through here, so
the storage backend (SQLite now, Supabase Postgres later) stays swappable
behind a stable function-based interface instead of scattered ORM calls.
"""

import datetime as dt

from sqlalchemy import func, select

from app.db.models import AgentDecision, BacktestRun, EngineRunState, IVObservation, Trade, WheelState
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
                "tp1_triggered": bool(r.tp1_triggered),
            }
            for r in rows
        ]


def mark_tp1_triggered(trade_id: int) -> None:
    """Track 1 only: records that position_monitor.py's sweep already took
    the tier-1 partial profit for this trade, so the next sweep treats the
    remainder's stop as breakeven instead of the original stop-loss."""
    with get_session() as session:
        trade = session.get(Trade, trade_id)
        if trade is None:
            return
        trade.tp1_triggered = True
        session.commit()


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
    """Only touches holds_shares — cost_basis is managed separately (see
    set_wheel_cost_basis) so this function's per-sweep boolean-sync fallback
    (position_monitor.py's _sweep_track4_positions) never clobbers a
    cost_basis set by the assignment-detection path in the same sweep."""
    with get_session() as session:
        row = session.get(WheelState, symbol)
        if row is None:
            session.add(WheelState(symbol=symbol, holds_shares=holds_shares))
        else:
            row.holds_shares = holds_shares
        session.commit()


def get_wheel_cost_basis(symbol: str) -> float | None:
    with get_session() as session:
        row = session.get(WheelState, symbol)
        return row.cost_basis if row else None


def set_wheel_cost_basis(symbol: str, cost_basis: float | None) -> None:
    """Set at assignment (strike - premium collected); cleared (None) once
    shares are called away — see position_monitor.py's
    _sweep_track4_positions."""
    with get_session() as session:
        row = session.get(WheelState, symbol)
        if row is None:
            session.add(WheelState(symbol=symbol, holds_shares=cost_basis is not None, cost_basis=cost_basis))
        else:
            row.cost_basis = cost_basis
        session.commit()


def list_trades(limit: int = 100, track: str | None = None) -> list[dict]:
    with get_session() as session:
        query = select(Trade)
        if track is not None:
            query = query.where(Trade.track == track)
        rows = session.scalars(query.order_by(Trade.created_at.desc()).limit(limit)).all()
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


def get_track_pnl_summary() -> list[dict]:
    """Realized P&L, win rate, and open/closed counts per track — backs the
    Controls tab's Track P&L card. Aggregated in Python rather than SQL
    (small row count for a week-long hackathon test, and avoids a
    dialect-specific conditional-sum for the win-rate count)."""
    with get_session() as session:
        rows = session.scalars(select(Trade)).all()

    by_track: dict[str, dict] = {}
    for r in rows:
        if r.track is None:
            continue
        bucket = by_track.setdefault(r.track, {"track": r.track, "realized_pnl": 0.0, "open_count": 0, "closed_count": 0, "win_count": 0})
        if r.status == "open":
            bucket["open_count"] += 1
        elif r.status == "closed":
            bucket["closed_count"] += 1
            # realized_pnl can be None: position_monitor.py records a
            # "reconciled externally" close (leg vanished outside our own
            # close flow) with no recoverable P&L — exclude, don't zero-fill.
            if r.realized_pnl is not None:
                bucket["realized_pnl"] += r.realized_pnl
                if r.realized_pnl > 0:
                    bucket["win_count"] += 1

    return list(by_track.values())


def get_performance_metrics(track: str) -> dict:
    """Cumulative realized-P&L series + trade-level risk/return ratios for
    the Performance page. Deliberately per-CLOSED-TRADE, not per-day: there's
    no regular daily portfolio-value snapshot anywhere in this app to
    compute a standard daily-returns Sharpe ratio against (same class of gap
    as the backtest engine's own known_gaps) — these are the one-level-down
    approximations a trade-log-only system can actually support, labeled as
    such in `known_gaps` rather than presented as the textbook versions.

    `profit_factor`/`recovery_factor` return None (not float('inf')) when
    the denominator is zero — Python's json module happily emits a literal
    `Infinity` token, which is not valid JSON and breaks `JSON.parse` in the
    browser.
    """
    with get_session() as session:
        rows = session.scalars(
            select(Trade).where(Trade.track == track).order_by(Trade.created_at.asc())
        ).all()

    closed = [r for r in rows if r.status == "closed" and r.realized_pnl is not None]
    open_count = sum(1 for r in rows if r.status == "open")

    cumulative_series = []
    running = 0.0
    for r in closed:
        running += r.realized_pnl
        cumulative_series.append({
            "date": (r.closed_at or r.created_at).isoformat(),
            "cumulative_pnl": running,
            "trade_pnl": r.realized_pnl,
            "symbol": r.symbol,
        })

    pnls = [r.realized_pnl for r in closed]
    gross_profit = sum(p for p in pnls if p > 0)
    gross_loss = abs(sum(p for p in pnls if p < 0))
    profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else None

    sharpe_ratio = None
    if len(pnls) >= 2:
        mean = sum(pnls) / len(pnls)
        variance = sum((p - mean) ** 2 for p in pnls) / (len(pnls) - 1)
        std = variance ** 0.5
        if std > 0:
            sharpe_ratio = (mean / std) * (len(pnls) ** 0.5)

    peak = 0.0
    max_drawdown = 0.0
    for point in cumulative_series:
        peak = max(peak, point["cumulative_pnl"])
        max_drawdown = max(max_drawdown, peak - point["cumulative_pnl"])

    net_realized_pnl = cumulative_series[-1]["cumulative_pnl"] if cumulative_series else 0.0
    recovery_factor = (net_realized_pnl / max_drawdown) if max_drawdown > 0 else None

    known_gaps = (
        ["Sharpe ratio, profit factor, and recovery factor are computed per CLOSED TRADE, not from a daily equity curve — "
         "there's no regular daily portfolio-value snapshot to compute a standard daily-returns Sharpe against."]
        if closed else
        ["No closed trades yet for this track — these ratios need at least a couple of closed trades before they mean anything."]
    )

    return {
        "cumulative_pnl_series": cumulative_series,
        "sharpe_ratio": sharpe_ratio,
        "profit_factor": profit_factor,
        "recovery_factor": recovery_factor,
        "max_drawdown": max_drawdown,
        "net_realized_pnl": net_realized_pnl,
        "closed_count": len(closed),
        "open_count": open_count,
        "recent_completed_trades": [
            {"id": r.id, "symbol": r.symbol, "closed_at": (r.closed_at or r.created_at).isoformat(), "realized_pnl": r.realized_pnl, "thesis": r.thesis}
            for r in reversed(closed[-10:])
        ],
        "known_gaps": known_gaps,
    }


def save_agent_decision(**kwargs) -> None:
    with get_session() as session:
        session.add(AgentDecision(**kwargs))
        session.commit()


def list_agent_decisions(limit: int = 100, track: str | None = None, llm_only: bool = False) -> list[dict]:
    """`llm_only` excludes cycles that never reached the LLM validator at all
    (quant_engine.py's technical/IV gate said no qualifying setup — see
    graph.py's conditional edge). Filtered on `thesis IS NOT NULL`, not
    sentiment_score: track1_validator.py always sets both, but
    track4_validator.py's schema has no sentiment_score field at all (it
    returns risk_score instead) — sentiment_score would be None for every
    real Track 4 LLM decision too, silently hiding all of them. `thesis`
    defaults to `""` (not None) in BOTH validators' return dicts whenever
    they actually run, so its presence is the one track-agnostic signal.
    Without this filter, routine per-minute WAITs (no signal to reason
    about yet) can outnumber genuine LLM verdicts 50-to-1 in the history."""
    with get_session() as session:
        query = select(AgentDecision)
        if track is not None:
            query = query.where(AgentDecision.track == track)
        if llm_only:
            query = query.where(AgentDecision.thesis.is_not(None))
        rows = session.scalars(query.order_by(AgentDecision.created_at.desc()).limit(limit)).all()
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


def get_decision_counts(track: str | None = None) -> dict:
    """Telemetry numbers for the Controls tab — total cycles run, trades
    the risk gate approved, cycles it rejected/vetoed, and the most recent
    decision's timestamp. Track 1 and Track 4 run as independent concurrent
    engines with independent telemetry, so `track` scopes to just one."""
    with get_session() as session:
        filters = (AgentDecision.track == track,) if track is not None else ()
        total = session.scalar(select(func.count()).select_from(AgentDecision).where(*filters)) or 0
        approved = session.scalar(select(func.count()).select_from(AgentDecision).where(AgentDecision.risk_approved.is_(True), *filters)) or 0
        rejected = session.scalar(select(func.count()).select_from(AgentDecision).where(AgentDecision.risk_approved.is_(False), *filters)) or 0
        last_created = session.scalar(select(func.max(AgentDecision.created_at)).where(*filters))
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


def save_engine_run_state(track: str, symbols: str, interval_seconds: int, sentiment_threshold: float, volume_ratio_min: float) -> None:
    """DB-backed replacement for config_store.py's local-JSON run-state —
    see EngineRunState's docstring for why (Render free-tier container
    restarts wipe local disk, but not the provisioned Postgres DB)."""
    with get_session() as session:
        row = session.get(EngineRunState, track)
        if row is None:
            session.add(EngineRunState(
                track=track, symbols=symbols, interval_seconds=interval_seconds,
                sentiment_threshold=sentiment_threshold, volume_ratio_min=volume_ratio_min,
            ))
        else:
            row.symbols = symbols
            row.interval_seconds = interval_seconds
            row.sentiment_threshold = sentiment_threshold
            row.volume_ratio_min = volume_ratio_min
        session.commit()


def load_engine_run_state(track: str) -> dict | None:
    with get_session() as session:
        row = session.get(EngineRunState, track)
        if row is None:
            return None
        return {
            "symbols": row.symbols,
            "interval_seconds": row.interval_seconds,
            "sentiment_threshold": row.sentiment_threshold,
            "volume_ratio_min": row.volume_ratio_min,
        }


def clear_engine_run_state(track: str) -> None:
    with get_session() as session:
        row = session.get(EngineRunState, track)
        if row is not None:
            session.delete(row)
            session.commit()


def list_tracks_with_run_state() -> list[str]:
    """Used by main.py's startup hook to know which tracks to auto-resume."""
    with get_session() as session:
        return list(session.scalars(select(EngineRunState.track)).all())


_IV_PLACEHOLDER_RANGE = (0.10, 0.90)
_IV_MIN_SAMPLES = 20
_IV_LOOKBACK_DAYS = 365


def record_iv_observation(symbol: str, iv: float) -> None:
    """One row per cycle — see IVObservation's docstring. Called
    unconditionally from iv_percentile.py's compute_iv_percentile (every
    track, every cycle), so this table self-populates during normal use
    rather than needing a separate backfill job."""
    with get_session() as session:
        session.add(IVObservation(symbol=symbol, iv=iv))
        session.commit()


def get_iv_52wk_range(symbol: str) -> tuple[float, float]:
    """Real 52-week (well, however much history exists so far, up to 365
    days) IV min/max computed from observed cycles — see record_iv_observation.
    Falls back to a documented placeholder range until at least
    _IV_MIN_SAMPLES observations exist for this symbol, rather than
    computing a percentile against a handful of noisy early samples."""
    cutoff = dt.datetime.utcnow() - dt.timedelta(days=_IV_LOOKBACK_DAYS)
    with get_session() as session:
        ivs = session.scalars(
            select(IVObservation.iv).where(IVObservation.symbol == symbol, IVObservation.observed_at >= cutoff)
        ).all()

    if len(ivs) < _IV_MIN_SAMPLES:
        return _IV_PLACEHOLDER_RANGE
    return min(ivs), max(ivs)
