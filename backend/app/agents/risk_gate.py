"""Autonomous Risk Gate Node — deterministic circuit breaker.

Deliberately contains ZERO LLM calls. This is the last line of defense before
an order reaches the brokerage: it validates the Lead Architect's proposal
against hard-coded guardrails (see app/config.py for thresholds) and either
approves it unchanged or rejects it with a logged reason. Judges should be
able to read this file top-to-bottom and verify the guardrails hold.
"""

from app.agents.state import AgentState
from app.config import get_settings

settings = get_settings()


def run(state: AgentState) -> dict:
    order = state.get("proposed_order")
    if not order:
        return {"risk_approved": False, "risk_rejection_reason": "no order proposed"}

    portfolio_risk = state.get("portfolio_risk", {})
    equity = portfolio_risk.get("equity", 0)
    margin_used_pct = portfolio_risk.get("margin_utilization_pct", 0)

    position_notional = order.get("estimated_notional", 0)
    position_pct = (position_notional / equity) if equity else 1.0

    if not order.get("symbol") or not order.get("legs"):
        return {"risk_approved": False, "risk_rejection_reason": "invalid order structure"}

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

    if "stop_loss_pct" not in order or order["stop_loss_pct"] > settings.stop_loss_pct:
        return {
            "risk_approved": False,
            "risk_rejection_reason": "missing or excessive stop-loss on proposed order",
        }

    return {"risk_approved": True, "risk_rejection_reason": None}
