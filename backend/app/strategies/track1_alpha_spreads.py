"""Track 1: Options Alpha Agents — single-leg directional conviction via a
long call or put, near-the-money, 1-2 DTE. Max loss is bounded to the
premium paid (scaled by quantity) — the same defined-risk category as the
vertical debit spread this replaces, just structurally simpler: one leg
instead of two, so there's no "legs land on different expirations" failure
mode and no combined two-leg liquidity requirement.

Entry condition (enforced upstream, BEFORE this function is ever called —
see graph.py's conditional edge after quant_engine and
app/agents/track1_validator.py): quant_engine.py's technical confluence
screener (15m EMA(50) trend + 1m VWAP + RSI(14) band + 20-bar breakout +
RVOL >= 1.5, all agreeing on direction) AND the LLM catalyst validator's
verdict == APPROVE with |sentiment| >= 0.50 and confidence >= 70%. This
function only builds the order from an already-qualified signal — it does
not re-check any of that.

Exit management (partial take-profit, full exit, stop-loss, time-stop, EOD
liquidation) lives in position_monitor.py, not here — same split as before.

DTE/exit numbers below are calibrated for a 1-2 DTE hold, not 0-DTE: price
moves are smoother over a day or two than intraday-only, so the stop is
tighter (structural failure, not noise) and the time-stop is longer
(lets the 15m trend actually play out).
"""

from datetime import date

from app.agents.state import AgentState
from app.config import get_settings
from app.strategies._common import closest_by_delta

TARGET_DELTA = 0.50
DELTA_BAND = (0.45, 0.55)
DTE_TARGET_DAYS = 2
ACCEPTABLE_DTE = (1, 2)
MIN_OPEN_INTEREST = 500
# Was 0.05 (5%) -- found live on 2026-08-28 to silently reject nearly every
# real, liquid contract: e.g. a genuinely tradeable near-the-money contract
# (247+ open interest) with a normal $0.06 absolute bid/ask spread still
# reads as an 11-12% spread_pct simply because the option itself is cheap.
# Percentage-of-premium spread naturally runs wide on lower-dollar contracts
# even when the absolute spread is perfectly normal -- 5% was calibrated
# without checking against real quotes. 0.15 lets genuinely liquid
# contracts like that through while still screening out truly wide/thin ones.
MAX_SPREAD_PCT = 0.15

# Fixed exit targets, read by position_monitor.py's sweep — not derived from
# the LLM's take_profit_pct suggestion (kept in the LLM's schema for thesis
# coherence, but the actual exit levels are deterministic constants).
TP1_PCT = 0.50  # partial (half) scale-out trigger
TP2_PCT = 1.00  # full/runner exit trigger
MAX_HOLD_MINUTES_DEFAULT = 90
MAX_HOLD_MINUTES_CEILING = 120


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

    # closest_by_delta narrows to a single nearest expiration, which can't
    # itself express "1 or 2 DTE" as an acceptance window — guard explicitly
    # rather than trade whatever it lands on (e.g. a single-stock name with
    # no near-dated expiration at all).
    dte = (contract["expiration_date"] - date.today()).days
    if dte not in ACCEPTABLE_DTE:
        return None
    actual_delta = abs(contract["greeks"]["delta"])
    if not (DELTA_BAND[0] <= actual_delta <= DELTA_BAND[1]):
        return None

    equity = state.get("portfolio_risk", {}).get("equity", 0)
    contract_cost = contract["ask"] * 100
    if contract_cost <= 0 or equity <= 0:
        return None
    qty = max(1, int((equity * settings.max_position_pct) // contract_cost))

    # LLM's stop_loss_pct is on a 0-100 percentage scale (see
    # track1_validator.py's schema); clamped to the existing platform-wide
    # ceiling (settings.stop_loss_pct, fractional) rather than the original
    # spec's own number — every order must still clear risk_gate.py's
    # existing check unchanged.
    llm_sl_frac = float(llm_result.get("stop_loss_pct", settings.stop_loss_pct * 100)) / 100
    stop_loss_pct = min(llm_sl_frac, settings.stop_loss_pct)
    max_hold_minutes = min(int(llm_result.get("max_hold_minutes", MAX_HOLD_MINUTES_DEFAULT)), MAX_HOLD_MINUTES_CEILING)

    # ratio_qty is always 1 for a single-leg "simple" order — the real
    # contract count travels via the order-level `qty` field (see
    # execution.py), not the leg's ratio_qty, so it isn't double-applied.
    legs = [{"side": "buy", "ratio_qty": 1, "option_symbol": contract["symbol"], "estimated_cost": contract["ask"]}]

    return {
        "symbol": state["symbol"],
        "legs": legs,
        "order_type": "limit",
        "time_in_force": "day",
        "qty": qty,
        # Read by position_monitor.py's TP2/runner exit check (a 15m EMA
        # cross against this direction is the other trigger, alongside
        # tp2_pct itself).
        "direction": direction,
        # The real capital-at-risk for risk_gate.py's position-size check —
        # total premium paid across all `qty` contracts, not per-contract
        # (net_debit_credit's ratio_qty-based math assumes qty==1, which no
        # longer holds now that Track 1 sizes >1 contract per trade).
        "capital_at_risk": contract["ask"] * 100 * qty,
        "stop_loss_pct": stop_loss_pct,
        "tp1_pct": TP1_PCT,
        "tp2_pct": TP2_PCT,
        "max_hold_minutes": max_hold_minutes,
        "thesis": llm_result.get("thesis", ""),
    }
