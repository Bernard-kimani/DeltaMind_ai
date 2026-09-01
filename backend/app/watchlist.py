"""Curated watchlist for multi-symbol scanning — 15 liquid, options-active
symbols across four categories (the user's own researched universe, not a
full-market scan — see PLAN.md's watchlist-scope decision: expanding from
2 to ~15 symbols proves diversification without silently stretching
run_agent_loop.py's per-symbol interval, which sleeps once per FULL PASS
over all watched symbols, not per symbol).

Categories double as the sector map for risk_gate.py's concentration cap —
tagging a symbol here is what makes it eligible for that check at all;
untagged symbols are invisible to the sector cap (see risk_metrics.py's
`sector_exposure_pct`).
"""

from app.alpaca.rest_client import get_daily_bars, get_option_chain

WATCHLIST_CATEGORIES: dict[str, list[str]] = {
    "index_etf": ["SPY", "QQQ", "IWM"],
    "mega_cap_tech": ["NVDA", "AAPL", "MSFT", "AMZN", "GOOGL", "META", "INTC"],
    "high_beta_momentum": ["TSLA", "AMD", "COIN"],
    "sector_etf": ["XLF", "XLE", "SMH"],
    # Added 2026-09-01 specifically for Track 4: every technically-qualifying
    # contract on the watchlist above blew the 15%/25% sizing caps in dry-run
    # testing (a single CSP's collateral = strike x 100, and these names are
    # all $150-500+/share) -- confirmed a sizing problem, not a signal or DTE
    # problem, so Track 4's actual DTE/exit logic stays untouched. These are
    # deliberately lower-priced ($28-107/share) but still liquid names
    # (11M-40M avg daily volume, ~21-DTE ATM spread under the 15% floor)
    # so a CSP can actually clear risk_gate without loosening any risk cap.
    "financials": ["BAC"],
    "healthcare": ["PFE"],
    "media_entertainment": ["DIS"],
}

WATCHLIST: list[str] = [symbol for symbols in WATCHLIST_CATEGORIES.values() for symbol in symbols]

SECTOR_MAP: dict[str, str] = {
    symbol: category for category, symbols in WATCHLIST_CATEGORIES.items() for symbol in symbols
}

MIN_AVG_DAILY_VOLUME = 1_000_000
MAX_ATM_SPREAD_PCT = 0.05


def as_csv() -> str:
    """Matches the Controls tab's comma-separated Symbols field format —
    backs the "Load curated watchlist" button."""
    return ",".join(WATCHLIST)


def passes_liquidity_filter(symbol: str) -> tuple[bool, str]:
    """Run once when building/refreshing a watchlist, not every cycle — one
    bars call + one chain call per candidate symbol. Open interest is
    checked opportunistically elsewhere (in the flattened chain itself) but
    not gated on here: Alpaca's paper/indicative feed doesn't reliably
    populate it, so average daily volume and the at-the-money spread are the
    two load-bearing liquidity signals.
    """
    daily_bars = get_daily_bars(symbol, limit=20)
    if len(daily_bars) < 20:
        return False, "insufficient daily bar history"

    avg_volume = sum(b["volume"] for b in daily_bars) / len(daily_bars)
    if avg_volume < MIN_AVG_DAILY_VOLUME:
        return False, f"avg daily volume {avg_volume:,.0f} below {MIN_AVG_DAILY_VOLUME:,.0f} floor"

    spot = daily_bars[-1]["close"]
    chain = get_option_chain(symbol)
    calls = [c for c in chain if c["type"] == "call"]
    if not calls:
        return False, "no call contracts available"

    nearest_expiration = min(c["expiration_date"] for c in calls)
    same_expiration = [c for c in calls if c["expiration_date"] == nearest_expiration]
    atm = min(same_expiration, key=lambda c: abs(c["strike_price"] - spot))

    if atm["spread_pct"] > MAX_ATM_SPREAD_PCT:
        return False, f"ATM spread {atm['spread_pct']:.1%} exceeds {MAX_ATM_SPREAD_PCT:.0%} floor"

    return True, f"OK (avg daily volume {avg_volume:,.0f}, ATM spread {atm['spread_pct']:.1%})"
