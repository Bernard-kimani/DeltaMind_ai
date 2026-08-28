"""Track 4: Income & Portfolio Overlay Agents — The Wheel.

Sell ~21 DTE cash-secured puts at ~0.30 delta on liquid, high-IV names,
gated by a daily-bar technical regime check (avoid selling puts into a
structural downtrend). If assigned, position_monitor.py's sweep detects the
resulting equity position, records cost_basis, and flips wheel_state so the
next cycle sells covered calls (floored at that cost basis) instead, until
shares are called away. This module only proposes the opening leg for a
fresh cycle — exit management (profit-target buy-to-close, stop-loss
defense, assignment/called-away detection) lives in position_monitor.py.

Entry condition (enforced upstream, BEFORE this function is ever called —
see graph.py's conditional edge after quant_engine and
app/agents/track4_validator.py): quant_engine.py's IV percentile computation
AND (for a fresh cash-secured put only) technical_signals.check_wheel_put_regime
(price > 200-day EMA, RSI(14) in [35, 55]) AND the LLM risk-officer
validator's verdict == APPROVE with no earnings conflict and low risk_score.
This function only builds the order from an already-qualified signal.
"""

from datetime import date

from app.agents.state import AgentState
from app.strategies._common import closest_by_delta, estimate_notional

CSP_DELTA = 0.30
CC_DELTA = 0.30
DELTA_BAND = (0.25, 0.30)
# Single-point anchor for closest_by_delta's nearest-expiration narrowing;
# ACCEPTABLE_DTE below is the real accept/reject band (the brief's 14-30 DTE
# sweet spot) — same "point estimate to rank, band to accept" split as
# track1_alpha_spreads.py's DTE handling.
DTE_TARGET_DAYS = 21
ACCEPTABLE_DTE = (14, 30)
MIN_OPEN_INTEREST = 500
# Was 0.05 (5%) -- see track1_alpha_spreads.py's identical change for the
# live finding: a genuinely liquid XLF put (247 OI, right at target delta)
# had a perfectly normal $0.06 absolute bid/ask spread that still read as
# 11.5% spread_pct simply because the contract itself is cheap. 5% silently
# rejected nearly every real candidate checked. 0.15 lets those through.
MAX_SPREAD_PCT = 0.15
# "Elevated IV" per the spec, made concrete. Tightened from the original
# scaffold's 50 to the spec's own 45.
IV_PERCENTILE_FLOOR = 45
STOP_LOSS_PCT = 0.20  # order-level declared ceiling, checked by risk_gate.py at entry — distinct from position_monitor.py's dynamic 3x-premium defense trigger


def propose_order(state: AgentState, llm_result: dict) -> dict | None:
    if state.get("iv_percentile", 0) < IV_PERCENTILE_FLOOR:
        return None

    option_chain = state.get("option_chain", [])
    portfolio_risk = state.get("portfolio_risk", {})
    holds_shares = portfolio_risk.get("holds_underlying_shares", False)

    # Same liquidity pre-filter Track 1 applies at contract-selection time —
    # Track 4 previously had none here (only a one-time check when a symbol
    # is added to the watchlist), which could let a stale/illiquid quote
    # through on a live cycle.
    liquid_chain = [
        c for c in option_chain
        if c.get("open_interest") and c["open_interest"] >= MIN_OPEN_INTEREST
        and c.get("spread_pct") is not None and c["spread_pct"] <= MAX_SPREAD_PCT
    ]

    if holds_shares:
        # Covered call (State 1): no technical regime gate per the spec —
        # only floor the strike at or above cost basis so assignment can
        # never turn into a guaranteed loss. If cost_basis isn't recorded
        # (e.g. a manually-created position outside this agent's own CSP
        # flow), degrade gracefully rather than block trading entirely.
        cost_basis = portfolio_risk.get("cost_basis")
        candidates = liquid_chain
        if cost_basis is not None:
            candidates = [
                c for c in candidates
                if c.get("type") != "call" or (c.get("strike_price") is not None and c["strike_price"] >= cost_basis)
            ]
        leg = closest_by_delta(candidates, CC_DELTA, is_call=True, target_dte=DTE_TARGET_DAYS)
        side_note = "covered_call"
        # Shares are already owned — selling a call against them commits no
        # new capital, unlike a cash-secured put.
        capital_at_risk = 0.0
    else:
        # Cash-secured put (State 0): also requires the daily-bar regime
        # check to have already qualified (see quant_engine.py / graph.py's
        # conditional edge) — avoid selling puts into a structural downtrend.
        if not state.get("technical_signal", {}).get("qualified"):
            return None
        leg = closest_by_delta(liquid_chain, -CSP_DELTA, is_call=False, target_dte=DTE_TARGET_DAYS)
        side_note = "cash_secured_put"
        # The real capital commitment is the cash secured against
        # assignment (strike x 100), NOT the small premium collected —
        # using premium alone would let risk_gate.py's position-size check
        # pass almost any CSP regardless of strike price.
        capital_at_risk = leg["strike_price"] * 100 if leg else 0.0

    if not leg:
        return None

    # closest_by_delta narrows to a single nearest expiration/delta, which
    # can't itself express an accept band — guard explicitly rather than
    # trade whatever it lands on.
    dte = (leg["expiration_date"] - date.today()).days
    if not (ACCEPTABLE_DTE[0] <= dte <= ACCEPTABLE_DTE[1]):
        return None
    actual_delta = abs(leg["greeks"]["delta"])
    if not (DELTA_BAND[0] <= actual_delta <= DELTA_BAND[1]):
        return None

    legs = [{
        "side": "sell", "ratio_qty": 1, "option_symbol": leg["symbol"], "estimated_cost": leg["bid"],
        # Read by position_monitor.py's assignment-detection path to compute
        # cost_basis (strike - premium) without parsing the OCC symbol.
        "strike_price": leg["strike_price"],
    }]

    return {
        "symbol": state["symbol"],
        "legs": legs,
        # Was "limit" (priced at the fetched bid) -- same reasoning as
        # track1_alpha_spreads.py's identical change: a passive limit risks
        # never filling if the quote moves away before it's matched. Market
        # orders trade price control away for actually getting filled, until
        # backtest data suggests a specific limit-pricing approach.
        "order_type": "market",
        "time_in_force": "day",
        "estimated_notional": estimate_notional(legs),
        "capital_at_risk": capital_at_risk,
        "stop_loss_pct": STOP_LOSS_PCT,
        "wheel_leg": side_note,
        "thesis": llm_result.get("thesis", ""),
    }
