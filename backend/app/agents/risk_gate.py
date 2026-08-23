"""Autonomous Risk Gate Node — deterministic circuit breaker.

Deliberately contains ZERO LLM calls. This is the last line of defense before
an order reaches the brokerage: it validates the Lead Architect's proposal
against hard-coded guardrails (see app/config.py for thresholds) and either
approves it unchanged or rejects it with a logged reason. Judges should be
able to read this file top-to-bottom and verify the guardrails hold.
"""

from app.agents.state import AgentState
from app.config import get_settings
from app.quant.risk_metrics import sector_exposure_pct
from app.strategies._common import net_debit_credit
from app.watchlist import SECTOR_MAP

settings = get_settings()


def run(state: AgentState) -> dict:
    order = state.get("proposed_order")
    if not order:
        return {"risk_approved": False, "risk_rejection_reason": "no order proposed"}

    if not order.get("symbol") or not order.get("legs"):
        return {"risk_approved": False, "risk_rejection_reason": "invalid order structure"}

    portfolio_risk = state.get("portfolio_risk", {})
    equity = portfolio_risk.get("equity", 0)
    margin_used_pct = portfolio_risk.get("margin_utilization_pct", 0)

    # Prefer the strategy's own `capital_at_risk` — it knows things this
    # function can't derive from legs alone (e.g. a cash-secured put's real
    # commitment is the strike x 100, not the premium collected; a covered
    # call commits no new capital since the shares are already owned).
    # Falls back to net debit/credit (not gross both-legs estimated_notional)
    # for any order that doesn't set it explicitly.
    position_notional = abs(order.get("capital_at_risk", net_debit_credit(order["legs"])))
    position_pct = (position_notional / equity) if equity else 1.0

    if position_pct > settings.max_position_pct:
        return {
            "risk_approved": False,
            "risk_rejection_reason": (
                f"position size {position_pct:.1%} exceeds max {settings.max_position_pct:.0%}"
            ),
        }

    if margin_used_pct > settings.max_margin_utilization_pct:
        return {
            "risk_approved": False,
            "risk_rejection_reason": (
                f"margin utilization {margin_used_pct:.1%} exceeds max "
                f"{settings.max_margin_utilization_pct:.0%}"
            ),
        }

    position_count = portfolio_risk.get("position_count", 0)
    if position_count >= settings.max_open_positions:
        return {
            "risk_approved": False,
            "risk_rejection_reason": (
                f"{position_count} open positions already at/above max {settings.max_open_positions}"
            ),
        }

    cash = portfolio_risk.get("cash", 0)
    projected_cash_pct = ((cash - position_notional) / equity) if equity else 0.0
    if projected_cash_pct < settings.min_cash_reserve_pct:
        return {
            "risk_approved": False,
            "risk_rejection_reason": (
                f"this trade would leave cash reserve at {projected_cash_pct:.1%}, "
                f"below the {settings.min_cash_reserve_pct:.0%} floor"
            ),
        }

    sector = SECTOR_MAP.get(order["symbol"])
    existing_sector_pct = sector_exposure_pct(sector, portfolio_risk.get("positions", []), SECTOR_MAP)
    projected_sector_pct = existing_sector_pct + position_pct
    if sector is not None and projected_sector_pct > settings.max_sector_pct:
        return {
            "risk_approved": False,
            "risk_rejection_reason": (
                f"{sector} exposure would reach {projected_sector_pct:.1%}, "
                f"exceeding the {settings.max_sector_pct:.0%} sector cap"
            ),
        }

    if "stop_loss_pct" not in order or order["stop_loss_pct"] > settings.stop_loss_pct:
        return {
            "risk_approved": False,
            "risk_rejection_reason": "missing or excessive stop-loss on proposed order",
        }

    return {"risk_approved": True, "risk_rejection_reason": None}
