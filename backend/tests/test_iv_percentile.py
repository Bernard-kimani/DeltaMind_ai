"""Sanity checks for the real, self-bootstrapping IV percentile history
(app/db/repository.record_iv_observation / get_iv_52wk_range, consumed by
app/quant/iv_percentile.compute_iv_percentile) — replaces what used to be a
permanent hardcoded (0.10, 0.90) placeholder.

Writes to the real configured DB (this project has no test-DB fixture —
same as the rest of the suite) using a fresh, randomly-suffixed symbol per
test so runs never collide with each other or with real trading data.
"""

import uuid

from app.db.repository import _IV_MIN_SAMPLES, _IV_PLACEHOLDER_RANGE, get_iv_52wk_range, record_iv_observation
from app.quant.iv_percentile import compute_iv_percentile


def _fresh_symbol() -> str:
    return f"ZZTEST_{uuid.uuid4().hex[:10].upper()}"


def test_insufficient_samples_falls_back_to_placeholder():
    symbol = _fresh_symbol()
    record_iv_observation(symbol, 0.55)  # only 1 sample, well under _IV_MIN_SAMPLES
    assert get_iv_52wk_range(symbol) == _IV_PLACEHOLDER_RANGE


def test_enough_samples_computes_a_real_range():
    symbol = _fresh_symbol()
    ivs = [0.20 + 0.01 * i for i in range(_IV_MIN_SAMPLES)]  # 0.20 .. 0.20+0.01*(N-1)
    for iv in ivs:
        record_iv_observation(symbol, iv)
    iv_min, iv_max = get_iv_52wk_range(symbol)
    assert iv_min == min(ivs)
    assert iv_max == max(ivs)
    assert (iv_min, iv_max) != _IV_PLACEHOLDER_RANGE


def test_compute_iv_percentile_records_an_observation_and_uses_the_range():
    symbol = _fresh_symbol()
    ivs = [0.20, 0.30, 0.40, 0.50, 0.60, 0.70, 0.80, 0.90, 1.00, 0.25,
           0.35, 0.45, 0.55, 0.65, 0.75, 0.85, 0.95, 0.28, 0.38, 0.48]
    assert len(ivs) == _IV_MIN_SAMPLES
    for iv in ivs:
        compute_iv_percentile(symbol, [{"implied_volatility": iv}])

    # One more observation at the current max — percentile should read 100.
    percentile = compute_iv_percentile(symbol, [{"implied_volatility": 1.00}])
    assert percentile == 100.0


def test_compute_iv_percentile_no_iv_data_returns_zero_without_recording():
    symbol = _fresh_symbol()
    assert compute_iv_percentile(symbol, [{"implied_volatility": None}]) == 0.0
    # No observation should have been recorded — still insufficient samples.
    assert get_iv_52wk_range(symbol) == _IV_PLACEHOLDER_RANGE
