"""Deterministic position-monitor sweep — checks currently OPEN trades (per
the DB's `Trade.status`) against live Alpaca positions once per full pass,
before any new entries get proposed. No LLM involved: exit/rollover
decisions are rule-based, same category as risk_gate.py.

A plain function, not a LangGraph node — deliberate choice (see PLAN.md):
this is an account-wide sweep across every open position, not a per-symbol
decision, so it doesn't fit the graph's one-symbol-per-cycle AgentState
shape, and needs no LLM reasoning to begin with.

Handles the two committed tracks:
- Track 1 (single-leg 1-2 DTE long options): a tiered exit — partial
  profit-take at +50% (closes half, moves the stop to breakeven for the
  remainder), full exit at +100% or a 15m EMA(50) trend reversal, a hard
  stop-loss, a time-stop for a stalled position, and an unconditional
  end-of-day liquidation before market close (see
  app/strategies/track1_alpha_spreads.py for where these numbers come from).
- Track 4 (the Wheel): a real exit sweep — profit-target buy-to-close at
  +50% (the option has decayed to a third of its collected premium),
  stop-loss defense (buy-to-close if the cost to close has risen to 3x the
  original premium AND the daily 200-EMA regime has broken), and detects
  the three ways a position stops existing between sweeps: assignment
  (records cost_basis), called-away (records the realized capital gain),
  and plain expiration worthless (keeps 100% of the premium). Previously
  this only ever synced a holds_shares boolean and never closed anything.

Track 2/3 aren't wired in here — out of scope per the current sequencing.
"""

import logging
from datetime import datetime, time
from zoneinfo import ZoneInfo

from app.alpaca.mcp_client import place_option_order
from app.alpaca.rest_client import get_15m_bars, get_all_positions, get_daily_bars
from app.db.repository import (
    close_trade,
    get_wheel_cost_basis,
    list_open_trades,
    mark_tp1_triggered,
    set_wheel_cost_basis,
    set_wheel_state,
)
from app.quant.technical_signals import EMA_TREND_PERIOD as TRACK1_EMA_PERIOD
from app.quant.technical_signals import check_wheel_put_regime, compute_ema
from app.strategies.track1_alpha_spreads import TP1_PCT as TRACK1_TP1_DEFAULT
from app.strategies.track1_alpha_spreads import TP2_PCT as TRACK1_TP2_DEFAULT

logger = logging.getLogger(__name__)

EASTERN = ZoneInfo("America/New_York")
EOD_LIQUIDATION_TIME = time(15, 45)
TIME_STOP_FLAT_BAND_PCT = 0.10

# Track 4 exit constants (see docs/tracks/track4_income_wheel.md §7).
WHEEL_PROFIT_TARGET_PCT = 0.50  # option has decayed to 50% of collected premium — buy to close, deterministic, not LLM-tunable
WHEEL_STOP_LOSS_PLPC = -2.0  # cost to close has risen to 3x original premium (short-position plpc convention: -2.0 == 3x)
# Enough daily history to seed check_wheel_put_regime's 200-EMA — matches
# quant_engine.py's WHEEL_DAILY_BARS_LIMIT (duplicated, not imported, same
# decoupling convention as this file's other cross-module constants).
WHEEL_DAILY_BARS_LIMIT = 220


def sweep_positions(track: str) -> list[dict]:
    """Returns a log of actions taken this sweep — callers (run_agent_loop.py,
    run_agent_stream_track1.py) log/persist as appropriate. Safe to call
    every pass even when nothing's open (returns an empty list)."""
    if track == "track1_alpha_spreads":
        return _sweep_track1_positions()
    if track == "track4_income_wheel":
        return _sweep_track4_positions()
    return []


def _sweep_track1_positions() -> list[dict]:
    open_trades = list_open_trades(track="track1_alpha_spreads")
    if not open_trades:
        return []

    positions_by_symbol = {p["symbol"]: p for p in get_all_positions()}
    actions: list[dict] = []
    is_eod = datetime.now(EASTERN).time() >= EOD_LIQUIDATION_TIME

    for trade in open_trades:
        legs = trade["order"].get("legs", [])
        if len(legs) != 1:
            continue  # not a Track 1 single-leg order — shouldn't happen, skip defensively
        option_symbol = legs[0]["option_symbol"]
        position = positions_by_symbol.get(option_symbol)

        if position is None:
            # The position vanished from the account outside our own close
            # flow — expired, exercised, or manually closed. Reconcile the
            # DB rather than let it sit "open" forever with no way to recover.
            close_trade(trade["id"], realized_pnl=None)
            actions.append({"trade_id": trade["id"], "symbol": trade["symbol"], "action": "reconciled_closed_externally"})
            logger.warning("[%s] trade %s: option position missing from account, marking closed (no P&L recovered)", trade["symbol"], trade["id"])
            continue

        order = trade["order"]
        pl_pct = float(position.get("unrealized_plpc") or 0)
        unrealized_pl = float(position.get("unrealized_pl") or 0)
        current_qty = abs(float(position.get("qty") or 0))
        if current_qty <= 0:
            continue

        tp1_pct = order.get("tp1_pct", TRACK1_TP1_DEFAULT)
        tp2_pct = order.get("tp2_pct", TRACK1_TP2_DEFAULT)
        sl_pct = order.get("stop_loss_pct", 0.20)
        max_hold_minutes = order.get("max_hold_minutes", 90)
        tp1_triggered = trade.get("tp1_triggered", False)

        if is_eod:
            _close_full(trade, option_symbol, current_qty, unrealized_pl, "end-of-day liquidation", actions)
            continue

        # Once tier-1 has already taken half off, the remainder's stop
        # moves to breakeven (0%) instead of the original stop-loss.
        effective_sl = 0.0 if tp1_triggered else -sl_pct
        if pl_pct <= effective_sl:
            reason = "stop moved to breakeven, triggered" if tp1_triggered else f"stop-loss triggered ({pl_pct:.0%})"
            _close_full(trade, option_symbol, current_qty, unrealized_pl, reason, actions)
            continue

        trend_reversed = bool(order.get("direction")) and _trend_reversed(trade["symbol"], order["direction"])
        if pl_pct >= tp2_pct or (tp1_triggered and trend_reversed):
            reason = f"runner target reached ({pl_pct:.0%})" if pl_pct >= tp2_pct else "15m trend reversed against the trade"
            _close_full(trade, option_symbol, current_qty, unrealized_pl, reason, actions)
            continue

        if not tp1_triggered and pl_pct >= tp1_pct:
            half_qty = max(1, int(current_qty // 2))
            _close_option(trade["symbol"], option_symbol, half_qty, "sell_to_close")
            mark_tp1_triggered(trade["id"])
            actions.append({
                "trade_id": trade["id"], "symbol": trade["symbol"], "action": "partial_close",
                "reason": f"tier-1 profit target reached ({pl_pct:.0%}), stop moved to breakeven", "qty_closed": half_qty,
            })
            logger.info("[%s] trade %s: partial close (%d contracts) — tier-1 profit target reached (%.0f%%)", trade["symbol"], trade["id"], half_qty, pl_pct * 100)
            continue

        age_minutes = (datetime.utcnow() - datetime.fromisoformat(trade["created_at"])).total_seconds() / 60
        if age_minutes >= max_hold_minutes and -TIME_STOP_FLAT_BAND_PCT <= pl_pct <= TIME_STOP_FLAT_BAND_PCT:
            _close_full(trade, option_symbol, current_qty, unrealized_pl, f"time-stop ({age_minutes:.0f}min, flat)", actions)
            continue

    return actions


def _close_full(trade: dict, option_symbol: str, qty: float, unrealized_pl: float, reason: str, actions: list[dict]) -> None:
    _close_option(trade["symbol"], option_symbol, qty, "sell_to_close")
    close_trade(trade["id"], realized_pnl=unrealized_pl)
    actions.append({"trade_id": trade["id"], "symbol": trade["symbol"], "action": "closed", "reason": reason, "realized_pnl": unrealized_pl})
    logger.info("[%s] closed trade %s — %s (realized P&L $%.2f)", trade["symbol"], trade["id"], reason, unrealized_pl)


def _close_option(symbol: str, option_symbol: str, qty: float, position_intent: str) -> None:
    place_option_order(
        symbol=symbol,
        legs=[{"symbol": option_symbol, "ratio_qty": 1, "position_intent": position_intent}],
        order_class="simple",
        order_type="market",
        time_in_force="day",
        qty=qty,
    )


def _trend_reversed(symbol: str, direction: str) -> bool:
    """True if the fresh 15m EMA(50) trend now disagrees with the trade's
    original direction — one of the two TP2/runner exit triggers, alongside
    the tp2_pct profit target itself."""
    bars_15m = get_15m_bars(symbol)
    closes = [b["close"] for b in bars_15m]
    ema = compute_ema(closes, TRACK1_EMA_PERIOD)
    if ema is None or not closes:
        return False
    latest_close = closes[-1]
    return latest_close < ema if direction == "up" else latest_close > ema


def _sweep_track4_positions() -> list[dict]:
    open_trades = list_open_trades(track="track4_income_wheel")
    positions = get_all_positions()
    option_positions_by_symbol = {p["symbol"]: p for p in positions if p.get("asset_class") == "us_option"}
    equity_symbols = {
        p["symbol"] for p in positions if p.get("asset_class") == "us_equity" and float(p.get("qty") or 0) > 0
    }

    actions: list[dict] = []

    for trade in open_trades:
        legs = trade["order"].get("legs", [])
        if len(legs) != 1:
            continue  # not a Track 4 single-leg order — shouldn't happen, skip defensively
        leg = legs[0]
        option_symbol = leg["option_symbol"]
        underlying = trade["symbol"]
        wheel_leg = trade["order"].get("wheel_leg")
        strike = leg.get("strike_price")
        premium_collected = leg.get("estimated_cost", 0) * 100  # dollar-scaled, matches estimate_notional's convention

        option_position = option_positions_by_symbol.get(option_symbol)

        if option_position is None:
            # The option position is gone — three ways that happens: expired
            # worthless (full premium kept), assigned (CSP -> equity now
            # held), or called away (covered call -> equity no longer held).
            if wheel_leg == "cash_secured_put" and underlying in equity_symbols:
                cost_basis = (strike - leg.get("estimated_cost", 0)) if strike is not None else None
                close_trade(trade["id"], realized_pnl=premium_collected)
                set_wheel_cost_basis(underlying, cost_basis)
                set_wheel_state(underlying, True)
                reason = f"assigned at ${strike:.2f}, cost basis ${cost_basis:.2f}" if cost_basis is not None else "assigned"
                actions.append({"trade_id": trade["id"], "symbol": underlying, "action": "assigned", "reason": reason, "realized_pnl": premium_collected})
                logger.info("[%s] trade %s: %s (premium kept $%.2f)", underlying, trade["id"], reason, premium_collected)
            elif wheel_leg == "covered_call" and underlying not in equity_symbols:
                prior_cost_basis = get_wheel_cost_basis(underlying)
                capital_gain = (strike - prior_cost_basis) * 100 if strike is not None and prior_cost_basis is not None else 0.0
                realized = premium_collected + capital_gain
                close_trade(trade["id"], realized_pnl=realized)
                set_wheel_cost_basis(underlying, None)
                set_wheel_state(underlying, False)
                reason = f"shares called away at ${strike:.2f}" if strike is not None else "shares called away"
                actions.append({"trade_id": trade["id"], "symbol": underlying, "action": "called_away", "reason": reason, "realized_pnl": realized})
                logger.info("[%s] trade %s: %s (realized P&L $%.2f)", underlying, trade["id"], reason, realized)
            elif wheel_leg in ("cash_secured_put", "covered_call"):
                # Expired worthless — full premium kept, State unchanged
                # (still no shares for a CSP, still holding shares for a CC).
                close_trade(trade["id"], realized_pnl=premium_collected)
                actions.append({"trade_id": trade["id"], "symbol": underlying, "action": "closed", "reason": f"{wheel_leg} expired worthless, premium kept", "realized_pnl": premium_collected})
                logger.info("[%s] trade %s: %s expired worthless (premium kept $%.2f)", underlying, trade["id"], wheel_leg, premium_collected)
            else:
                # No wheel_leg tag, or an otherwise-unexplained disappearance
                # (manual close outside our own flow) — reconcile rather than
                # let it sit "open" forever with no way to recover.
                close_trade(trade["id"], realized_pnl=None)
                actions.append({"trade_id": trade["id"], "symbol": underlying, "action": "reconciled_closed_externally"})
                logger.warning("[%s] trade %s: option position missing from account, marking closed (no P&L recovered)", underlying, trade["id"])
            continue

        pl_pct = float(option_position.get("unrealized_plpc") or 0)
        unrealized_pl = float(option_position.get("unrealized_pl") or 0)
        qty = abs(float(option_position.get("qty") or 0))
        if qty <= 0:
            continue

        if pl_pct >= WHEEL_PROFIT_TARGET_PCT:
            _close_option(underlying, option_symbol, qty, "buy_to_close")
            close_trade(trade["id"], realized_pnl=unrealized_pl)
            actions.append({"trade_id": trade["id"], "symbol": underlying, "action": "closed", "reason": f"profit target reached ({pl_pct:.0%})", "realized_pnl": unrealized_pl})
            logger.info("[%s] closed trade %s — profit target reached (%.0f%%, realized P&L $%.2f)", underlying, trade["id"], pl_pct * 100, unrealized_pl)
            continue

        if pl_pct <= WHEEL_STOP_LOSS_PLPC:
            daily_bars = get_daily_bars(underlying, limit=WHEEL_DAILY_BARS_LIMIT)
            regime = check_wheel_put_regime(daily_bars)
            structure_broken = regime["qualified"] is False and regime["price_vs_200ema_pct"] < 0
            if structure_broken:
                _close_option(underlying, option_symbol, qty, "buy_to_close")
                close_trade(trade["id"], realized_pnl=unrealized_pl)
                actions.append({"trade_id": trade["id"], "symbol": underlying, "action": "closed", "reason": f"stop-loss defense (cost to close at {abs(pl_pct):.0%} of premium, 200-EMA support broken)", "realized_pnl": unrealized_pl})
                logger.info("[%s] closed trade %s — stop-loss defense triggered (realized P&L $%.2f)", underlying, trade["id"], unrealized_pl)
                continue

    # Fallback boolean consistency pass — self-correcting for anything not
    # covered above (e.g. a position opened outside this agent's own flow).
    watched_symbols = {t["symbol"] for t in list_open_trades(track="track4_income_wheel")} | equity_symbols
    for symbol in watched_symbols:
        set_wheel_state(symbol, symbol in equity_symbols)

    return actions
