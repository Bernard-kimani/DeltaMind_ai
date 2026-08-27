"""Sanity checks for risk_gate.py's per-track position-size cap: Track 4's
cash-secured-put collateral uses max_wheel_collateral_pct (25%), every other
track uses max_position_pct (3%) — see config.py / risk_gate.py. Pure
function, no Alpaca/DB call needed."""

from app.agents.risk_gate import run
from app.config import get_settings

settings = get_settings()
EQUITY = 100_000.0


def _state(track: str, capital_at_risk: float) -> dict:
    return {
        "track": track,
        "proposed_order": {
            "symbol": "ZZFAKE",  # not in watchlist.SECTOR_MAP — sector check is skipped entirely
            "legs": [{"side": "sell", "ratio_qty": 1, "option_symbol": "ZZFAKE1", "estimated_cost": 1.0}],
            "capital_at_risk": capital_at_risk,
            "stop_loss_pct": settings.stop_loss_pct,
        },
        "portfolio_risk": {
            "equity": EQUITY,
            "cash": EQUITY,
            "margin_utilization_pct": 0.0,
            "position_count": 0,
        },
    }


def test_wheel_position_within_25pct_cap_approved_for_track4():
    state = _state("track4_income_wheel", capital_at_risk=EQUITY * 0.20)
    result = run(state)
    assert result["risk_approved"] is True


def test_same_20pct_position_rejected_for_track1():
    # 20% would clear Track 4's 25% wheel cap but must fail Track 1's 3% cap.
    state = _state("track1_alpha_spreads", capital_at_risk=EQUITY * 0.20)
    result = run(state)
    assert result["risk_approved"] is False
    assert "3%" in result["risk_rejection_reason"]


def test_wheel_position_above_25pct_cap_rejected():
    state = _state("track4_income_wheel", capital_at_risk=EQUITY * 0.30)
    result = run(state)
    assert result["risk_approved"] is False
    assert "25%" in result["risk_rejection_reason"]
