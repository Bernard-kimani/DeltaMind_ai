"""Implied Volatility Percentile — IV_current relative to its 52-week range.

    IV_P = (IV_current - IV_min_52wk) / (IV_max_52wk - IV_min_52wk) * 100

Drives Track 2 (Volatility & Event) entries: IV_P < 25 pre-earnings favors
long strangles/straddles (buying cheap vol); IV_P > 85 favors iron condors
(selling rich vol, capturing post-event IV crush).
"""

from app.db.repository import get_iv_52wk_range


def compute_iv_percentile(symbol: str, option_chain: list[dict]) -> float:
    current_iv = _atm_iv(option_chain)
    if current_iv is None:
        return 0.0

    iv_min, iv_max = get_iv_52wk_range(symbol)
    if iv_max <= iv_min:
        return 0.0

    percentile = (current_iv - iv_min) / (iv_max - iv_min) * 100
    return max(0.0, min(100.0, percentile))


def _atm_iv(option_chain: list[dict]) -> float | None:
    """Implied volatility of the near-the-money contract, used as the
    representative IV for the underlying at this snapshot.
    """
    ivs = [c["implied_volatility"] for c in option_chain if c.get("implied_volatility")]
    if not ivs:
        return None
    return sum(ivs) / len(ivs)
