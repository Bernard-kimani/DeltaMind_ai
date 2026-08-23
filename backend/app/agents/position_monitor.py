"""Deterministic position-monitor sweep — checks currently OPEN trades (per
the DB's `Trade.status`) against live Alpaca positions once per full pass,
before any new entries get proposed. No LLM involved: exit/rollover
decisions are rule-based, same category as risk_gate.py.

A plain function, not a LangGraph node — deliberate choice (see PLAN.md):
this is an account-wide sweep across every open position, not a per-symbol
decision, so it doesn't fit the graph's one-symbol-per-cycle AgentState
shape, and needs no LLM reasoning to begin with.

Handles the two committed tracks:
- Track 1 (debit spreads): profit-take / stop-loss against the net debit
  paid at entry (see track1_alpha_spreads.PROFIT_TAKE_PCT / STOP_LOSS_PCT).
- Track 4 (the Wheel): syncs `holds_underlying_shares` from Alpaca's own
  position list — the real fix for the gap where that field was hardcoded
  unreachable-False (see docs/tracks/track4_income_wheel.md §5).

Track 2/3 aren't wired in here — out of scope per the current sequencing.
"""

import logging

from app.alpaca.mcp_client import place_option_order
from app.alpaca.rest_client import get_all_positions
from app.db.repository import close_trade, list_open_trades, set_wheel_state
from app.strategies._common import net_debit_credit
from app.strategies.track1_alpha_spreads import PROFIT_TAKE_PCT
from app.strategies.track1_alpha_spreads import STOP_LOSS_PCT as TRACK1_STOP_LOSS_PCT

logger = logging.getLogger(__name__)


def sweep_positions(track: str) -> list[dict]:
    """Returns a log of actions taken this sweep — callers (run_agent_loop.py)
    log/persist as appropriate. Safe to call every pass even when nothing's
    open (returns an empty list)."""
    if track == "track1_alpha_spreads":
        return _sweep_track1_positions()
    if track == "track4_income_wheel":
        _sync_wheel_state()
        return []
    return []


def _sweep_track1_positions() -> list[dict]:
    open_trades = list_open_trades(track="track1_alpha_spreads")
    if not open_trades:
        return []

    positions_by_symbol = {p["symbol"]: p for p in get_all_positions()}
    actions = []

    for trade in open_trades:
        legs = trade["order"].get("legs", [])
        leg_symbols = [leg["option_symbol"] for leg in legs]
        leg_positions = [positions_by_symbol.get(sym) for sym in leg_symbols]

        if any(p is None for p in leg_positions):
            # A leg vanished from the account outside our own close flow —
            # expired, exercised, or manually closed. Reconcile the DB
            # rather than let it sit "open" forever with no way to recover.
            close_trade(trade["id"], realized_pnl=None)
            actions.append({"trade_id": trade["id"], "symbol": trade["symbol"], "action": "reconciled_closed_externally"})
            logger.warning("[%s] trade %s: leg(s) missing from account, marking closed (no P&L recovered)", trade["symbol"], trade["id"])
            continue

        unrealized_pl = sum(float(p.get("unrealized_pl") or 0) for p in leg_positions)
        net_debit = net_debit_credit(legs)
        if net_debit <= 0:
            continue  # not a real debit spread (shouldn't happen for this track) — skip rather than divide by zero/negative

        pl_pct = unrealized_pl / net_debit

        if pl_pct >= PROFIT_TAKE_PCT:
            reason = f"profit target reached ({pl_pct:.0%} of net debit)"
        elif pl_pct <= -TRACK1_STOP_LOSS_PCT:
            reason = f"stop-loss triggered ({pl_pct:.0%} of net debit)"
        else:
            continue

        _close_spread(trade["symbol"], legs, reason)
        close_trade(trade["id"], realized_pnl=unrealized_pl)
        actions.append({"trade_id": trade["id"], "symbol": trade["symbol"], "action": "closed", "reason": reason, "realized_pnl": unrealized_pl})
        logger.info("[%s] closed trade %s — %s (realized P&L $%.2f)", trade["symbol"], trade["id"], reason, unrealized_pl)

    return actions


def _close_spread(symbol: str, legs: list[dict], reason: str) -> None:
    closing_legs = [
        {
            "symbol": leg["option_symbol"],
            "ratio_qty": leg["ratio_qty"],
            "position_intent": "sell_to_close" if leg["side"] == "buy" else "buy_to_close",
        }
        for leg in legs
    ]
    place_option_order(
        symbol=symbol,
        legs=closing_legs,
        order_class="mleg" if len(closing_legs) > 1 else "simple",
        order_type="market",
        time_in_force="day",
    )


def _sync_wheel_state() -> None:
    """Reads Alpaca's own position list fresh each sweep rather than trying
    to detect an assignment transition — simpler, and self-correcting if a
    manual trade or an out-of-band close changes the picture."""
    positions = get_all_positions()
    equity_symbols = {
        p["symbol"] for p in positions if p.get("asset_class") == "us_equity" and float(p.get("qty") or 0) > 0
    }
    open_wheel_trades = list_open_trades(track="track4_income_wheel")
    watched_symbols = {t["symbol"] for t in open_wheel_trades} | equity_symbols

    for symbol in watched_symbols:
        set_wheel_state(symbol, symbol in equity_symbols)
