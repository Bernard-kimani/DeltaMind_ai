"""Market Ingestion Node.

The ONLY node that does network I/O for market/options data — quant_engine.py
is pure computation over whatever this node fetched (moved here specifically
so independent REST calls can run concurrently instead of one after another;
see below). No LLM involved.
"""

import concurrent.futures

from app.agents.state import AgentState
from app.alpaca.rest_client import get_15m_bars, get_daily_bars, get_option_chain, get_recent_bars

# Enough daily history to seed a 200-period EMA (plus RSI(14) warmup) — see
# technical_signals.check_wheel_put_regime. Duplicated (not imported) in
# position_monitor.py for the same reason noted there: keeps that sweep
# decoupled from this node's own fetch list.
WHEEL_DAILY_BARS_LIMIT = 220


def run(state: AgentState) -> dict:
    symbol = state["symbol"]
    track = state["track"]

    # Every track needs its own combination of REST fetches, and none of
    # them read each other's results — confirmed via graph.py's per-node
    # timing that running these one after another (as separate sequential
    # calls, some of them previously in quant_engine.py) was a meaningful
    # chunk of a cycle's latency against the <2s candle-to-decision target.
    # Fetching each track's combination concurrently overlaps their REST
    # round trips instead of paying for each one back-to-back.
    #
    # Track 1's option chain is the one deliberate exception, not fetched
    # here at all: it's the single most expensive call in the whole cycle
    # (thousands of contracts for a liquid underlying, ~12s on its own) and
    # Track 1's gate (technical_signal.qualified) never reads it — deferred
    # to track1_validator.py, which only fetches it on a cycle that's
    # already cleared both the technical gate and the LLM catalyst check,
    # i.e. the rare cycle actually about to place an order. Track 4's gate
    # needs iv_percentile (sourced from this same chain) before it can even
    # route past quant_engine, so it keeps fetching eagerly here.
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        market_data_future = pool.submit(get_recent_bars, symbol)
        bars_15m_future = pool.submit(get_15m_bars, symbol) if track == "track1_alpha_spreads" else None
        option_chain_future = pool.submit(get_option_chain, symbol) if track != "track1_alpha_spreads" else None
        daily_bars_future = pool.submit(get_daily_bars, symbol, WHEEL_DAILY_BARS_LIMIT) if track == "track4_income_wheel" else None

        market_data = market_data_future.result()
        bars_15m = bars_15m_future.result() if bars_15m_future else []
        option_chain = option_chain_future.result() if option_chain_future else []
        daily_bars = daily_bars_future.result() if daily_bars_future else []

    return {"market_data": market_data, "option_chain": option_chain, "bars_15m": bars_15m, "daily_bars": daily_bars}
