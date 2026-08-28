"""Engineered end-to-end dry run — proves real order placement and the
risk_gate/execution mechanics actually work on the paper account, without
waiting for a real qualifying market signal.

Forces the technical/IV gates open (skips waiting for a real signal) but
otherwise uses REAL data throughout: a real live option chain
(rest_client.get_option_chain), a real portfolio snapshot
(risk_metrics.portfolio_risk_snapshot), and the REAL strategy propose_order()
functions (not a hand-typed order dict) — so a bug in the actual
order-construction logic would surface here too, not just in a synthetic
signal path. risk_gate.run() and execution.run() are also the real,
unmodified live-path functions.

Defaults to preview-only (builds the order, runs it through risk_gate, stops
there) — pass --confirm to actually call execution.run() and place a real
order on the currently-configured Alpaca account. Safe to run on the current
shared/dev account (not yet the dedicated per-track submission account) —
see PLAN.md's account-separation notes.

Usage:
    python scripts/dry_run_trade_test.py --track track1_alpha_spreads --symbol SPY --direction up
    python scripts/dry_run_trade_test.py --track track1_alpha_spreads --symbol SPY --direction up --confirm
    python scripts/dry_run_trade_test.py --track track4_income_wheel --symbol XLF
    python scripts/dry_run_trade_test.py --track track4_income_wheel --symbol XLF --confirm
"""

import argparse
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.agents import execution, risk_gate  # noqa: E402
from app.alpaca.rest_client import get_option_chain  # noqa: E402
from app.quant.risk_metrics import portfolio_risk_snapshot  # noqa: E402
from app.strategies import track1_alpha_spreads, track4_income_wheel  # noqa: E402

DRY_RUN_THESIS = "ENGINEERED DRY RUN -- not a real signal, testing order-placement/exit-management mechanics ahead of Monday."


def build_track1_state(symbol: str, direction: str) -> dict:
    return {
        "symbol": symbol,
        "track": "track1_alpha_spreads",
        "option_chain": get_option_chain(symbol),
        "portfolio_risk": portfolio_risk_snapshot(symbol),
        # Force-qualified -- the real technical gate is skipped on purpose,
        # everything downstream of it (contract selection, sizing, risk_gate,
        # execution) is real.
        "technical_signal": {"qualified": True, "direction": direction},
    }


def build_track4_state(symbol: str) -> dict:
    return {
        "symbol": symbol,
        "track": "track4_income_wheel",
        "option_chain": get_option_chain(symbol),
        "portfolio_risk": portfolio_risk_snapshot(symbol),
        "iv_percentile": 50.0,  # force above IV_PERCENTILE_FLOOR (45)
        "technical_signal": {"qualified": True},  # force the CSP regime gate open
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--track", required=True, choices=["track1_alpha_spreads", "track4_income_wheel"])
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--direction", choices=["up", "down"], default="up", help="Track 1 only -- ignored for Track 4")
    parser.add_argument("--confirm", action="store_true", help="actually place the order via execution.run() -- omit to preview only")
    args = parser.parse_args()

    llm_result = {"thesis": DRY_RUN_THESIS, "stop_loss_pct": 15, "max_hold_minutes": 90}

    if args.track == "track1_alpha_spreads":
        state = build_track1_state(args.symbol, args.direction)
        order = track1_alpha_spreads.propose_order(state, llm_result)
    else:
        state = build_track4_state(args.symbol)
        order = track4_income_wheel.propose_order(state, llm_result)

    if not order:
        print(f"propose_order() returned None for {args.symbol}/{args.track} -- no contract cleared the delta/DTE/liquidity band right now.")
        print("Try a different symbol (or --direction for Track 1).")
        return

    print("=== Proposed order ===")
    print(order)

    state["proposed_order"] = order
    gate_result = risk_gate.run(state)
    print("\n=== risk_gate result ===")
    print(gate_result)

    if not gate_result["risk_approved"]:
        print("\nRejected by risk_gate -- stopping here. This is itself useful signal (a realistically-sized order would be blocked live too).")
        return

    if not args.confirm:
        print("\n=== PREVIEW ONLY -- no order placed ===")
        print("Rerun with --confirm to actually place this order on the paper account.")
        return

    state["risk_approved"] = True
    state["thesis"] = llm_result["thesis"]
    print("\n=== Placing real (paper) order via execution.run() ===")
    exec_result = execution.run(state)
    print(exec_result)


if __name__ == "__main__":
    main()
