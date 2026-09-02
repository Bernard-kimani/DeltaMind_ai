"""Track 5: Momentum Swing — a deliberately looser sibling of Track 1, not a
hackathon-labeled strategy. Same single-leg long call/put structure and max
loss bounded to premium paid, but on a slower timeframe (5-minute entry,
1-hour trend, vs. Track 1's 1m/15m) with a much thinner deterministic gate
and a genuinely decisive LLM validator, instead of a five-factor stack that
rarely lets anything through. Built 2026-09-01 after Track 1/Track 4 both
produced zero trades on the first live trading day — see
technical_signals.check_momentum_swing_confluence and track5_validator.py
for the two halves of "loosen the gate, let the LLM actually decide."

Entry condition (enforced upstream, BEFORE this function is ever called —
see graph.py's conditional edge after quant_engine and
app/agents/track5_validator.py): quant_engine.py's momentum-swing confluence
screener (1h 50-EMA trend + a genuine 5m EMA(20) crossover event, agreeing
on direction) AND the LLM validator's verdict == APPROVE with a
deliberately lower confidence bar than Track 1's. This function only builds
the order from an already-qualified signal.

Exit management lives in position_monitor.py's existing Track-1-style
tiered sweep (TP1/TP2/stop-loss/time-stop/EOD) — fully reused unchanged,
since every threshold it checks (tp1_pct, tp2_pct, stop_loss_pct,
max_hold_minutes) is read from each trade's own stored order, not
hardcoded per track. Only the values below differ from Track 1's.

DTE is widened (3-7 days vs. Track 1's 1-3) and the time-stop is hours, not
90 minutes — this trade is meant to develop over a slower timeframe than
Track 1's intraday scalp, so it needs more room before either resolves.
"""

from datetime import date

from app.agents.state import AgentState
from app.config import get_settings
from app.strategies._common import closest_by_delta

TARGET_DELTA = 0.50
# Widened from (0.45, 0.55) 2026-09-02: verified live that NVDA/TSLA-type
# names sit on a $2.50 strike grid, so the nearest-to-target strike often
# lands just outside a +/-0.05 band by pure bad luck of where price sits
# between strikes (confirmed -- the same NVDA setup passed minutes later
# once price drifted). Still near-the-money, just less brittle against
# discrete strike spacing.
DELTA_BAND = (0.40, 0.60)
DTE_TARGET_DAYS = 5
ACCEPTABLE_DTE = (3, 7)
# Lowered from 500 2026-09-02: verified live on IWM that its actual ATM
# strikes (delta 0.45-0.53, exactly on target) carry open interest of only
# 45-287, while the only strikes clearing 500 OI were far-OTM (delta
# 0.08-0.30, outside even the widened band) -- for a $1-strike ETF, OI
# piles up on cheap far-OTM contracts (retail lottery-ticket activity)
# rather than the true ATM ones, which trade actively without
# accumulating static open interest. Spread_pct is the more direct
# fill-quality signal and stays untouched; those same ATM strikes had
# tight 2-4% spreads, well under the 15% ceiling below.
MIN_OPEN_INTEREST = 200
# Same corrected floor as Track 1/Track 4 (see their identical constants'
# comments) — a cheap contract's percentage spread runs wide even with a
# perfectly normal absolute spread; 15% screens genuinely thin contracts
# without rejecting real, liquid ones.
MAX_SPREAD_PCT = 0.15

# Same profit-target percentages as Track 1 (position_monitor.py's sweep
# reads these from the order, so reusing the same tier structure is free) —
# only the TIME given to reach them differs.
TP1_PCT = 0.50
TP2_PCT = 1.00
MAX_HOLD_MINUTES_DEFAULT = 240  # 4 hours, vs. Track 1's 90 minutes
MAX_HOLD_MINUTES_CEILING = 480  # 8 hours — most of a trading day


def propose_order(state: AgentState, llm_result: dict) -> dict | None:
    settings = get_settings()
    option_chain = state.get("option_chain", [])
    signal = state.get("technical_signal", {})
    direction = signal.get("direction")
    if direction not in ("up", "down"):
        return None
    is_call = direction == "up"

    liquid_chain = [
        c for c in option_chain
        if c.get("open_interest") and c["open_interest"] >= MIN_OPEN_INTEREST
        and c.get("spread_pct") is not None and c["spread_pct"] <= MAX_SPREAD_PCT
    ]
    target_delta = TARGET_DELTA if is_call else -TARGET_DELTA
    contract = closest_by_delta(liquid_chain, target_delta, is_call, target_dte=DTE_TARGET_DAYS)
    if not contract:
        return None

    dte = (contract["expiration_date"] - date.today()).days
    if not (ACCEPTABLE_DTE[0] <= dte <= ACCEPTABLE_DTE[1]):
        return None
    actual_delta = abs(contract["greeks"]["delta"])
    if not (DELTA_BAND[0] <= actual_delta <= DELTA_BAND[1]):
        return None

    equity = state.get("portfolio_risk", {}).get("equity", 0)
    contract_cost = contract["ask"] * 100
    if contract_cost <= 0 or equity <= 0:
        return None
    qty = max(1, int((equity * settings.max_position_pct) // contract_cost))

    llm_sl_frac = float(llm_result.get("stop_loss_pct", settings.stop_loss_pct * 100)) / 100
    stop_loss_pct = min(llm_sl_frac, settings.stop_loss_pct)
    max_hold_minutes = min(int(llm_result.get("max_hold_minutes", MAX_HOLD_MINUTES_DEFAULT)), MAX_HOLD_MINUTES_CEILING)

    legs = [{"side": "buy", "ratio_qty": 1, "option_symbol": contract["symbol"], "estimated_cost": contract["ask"]}]

    return {
        "symbol": state["symbol"],
        "legs": legs,
        "order_type": "market",
        "time_in_force": "day",
        "qty": qty,
        "direction": direction,
        "capital_at_risk": contract["ask"] * 100 * qty,
        "stop_loss_pct": stop_loss_pct,
        "tp1_pct": TP1_PCT,
        "tp2_pct": TP2_PCT,
        "max_hold_minutes": max_hold_minutes,
        "thesis": llm_result.get("thesis", ""),
    }
