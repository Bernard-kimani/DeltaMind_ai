"""Historical bar loaders for the backtest engine — 1-minute and 15-minute
(Track 1's confluence gate) and daily (Track 4's regime gate), as far back
as ~5 months.

Deliberately reuses app/alpaca/rest_client.py's cached, timeout-patched,
one-retry-on-disconnect StockHistoricalDataClient singleton (via the public
get_stock_data_client() wrapper) instead of data_loader.py's older pattern
of a fresh, uncached client per call.

No manual date-range chunking/pagination here: alpaca-py's own
get_stock_bars() already loops through next_page_token pages internally
(RESTClient._get_marketdata, page_size=10_000) for a single request
spanning any date range — confirmed by reading alpaca-py's own source
rather than assumed, since a 5-month 1-minute pull is ~30-35k bars, well
past one page. A single get_stock_bars() call per symbol per timeframe is
therefore already correct; chunking would just be unneeded complexity.
"""

import logging
import time

from alpaca.data.enums import DataFeed
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame, TimeFrameUnit

from app.alpaca.rest_client import get_stock_data_client

logger = logging.getLogger(__name__)

# Confirmed live on 2026-09-01: neither this module nor rest_client.py's live
# path ever set `feed` explicitly, so each silently got whatever Alpaca
# defaults to for that KIND of request -- full consolidated SIP for an
# already-closed historical range (what this module was requesting), but the
# sparser IEX-only feed for live's same-day "recent" queries (free-tier data
# plan restriction, not a bug -- see engine.py's module docstring). That
# mismatch meant the backtest's qualification-rate numbers were measured
# against a materially richer tape than live ever actually sees. Explicitly
# requesting IEX here for Track 1's intraday bars (1m/15m) makes this an
# apples-to-apples number instead -- Track 4's daily regime gate isn't part
# of this fix since it reads already-closed prior days even live, not
# today's in-progress session.
LIVE_MATCHED_FEED = DataFeed.IEX

# Politeness delay between symbols, not a pagination mechanism — Alpaca's
# free-tier data API has a per-minute request cap; the SDK's own internal
# paging already spaces requests out somewhat via network round-trip time,
# this is just an extra courtesy margin for a run-once backtest job where
# wall-clock time doesn't matter the way it does for the live 2s budget.
INTER_SYMBOL_SLEEP_SECONDS = 0.5


def _bars_to_dicts(df) -> list[dict]:
    """Matches the plain-dict shape technical_signals.py's gate functions
    expect (close/volume/high/low/timestamp), same conversion rest_client.py
    already uses for the live path (bars.df.reset_index().to_dict(orient="records"))."""
    if df is None or df.empty:
        return []
    return df.reset_index().to_dict(orient="records")


def load_1m_bars(symbol: str, start, end) -> list[dict]:
    """Track 1's confluence gate — oldest-first 1-minute bars. No explicit
    regular-trading-hours filter: the live streaming script
    (run_agent_stream_track1.py) doesn't filter hours either, it just reacts
    to whatever bars the IEX feed delivers — replaying every bar Alpaca
    actually returns (including sparse pre/after-market ones) is the
    faithful match to live behavior, not an approximation of it."""
    request = StockBarsRequest(symbol_or_symbols=symbol, timeframe=TimeFrame.Minute, start=start, end=end, feed=LIVE_MATCHED_FEED)
    bars = get_stock_data_client().get_stock_bars(request)
    return _bars_to_dicts(bars.df)


def load_15m_bars(symbol: str, start, end) -> list[dict]:
    """Track 1's 15-minute EMA(50) trend leg — same native-15-minute-bar
    approach as rest_client.get_15m_bars' live counterpart, not resampled
    from 1-minute bars."""
    request = StockBarsRequest(symbol_or_symbols=symbol, timeframe=TimeFrame(15, TimeFrameUnit.Minute), start=start, end=end, feed=LIVE_MATCHED_FEED)
    bars = get_stock_data_client().get_stock_bars(request)
    return _bars_to_dicts(bars.df)


def load_daily_bars(symbol: str, start, end) -> list[dict]:
    """Track 4's 200-day EMA / RSI regime gate. Callers must pass a `start`
    at least ~300 calendar days before the reporting window's own start, so
    >=200 trading days of history precede the first evaluated day (the
    regime gate's own warmup requirement) instead of the window itself
    being truncated by the gate's minimum-length check."""
    request = StockBarsRequest(symbol_or_symbols=symbol, timeframe=TimeFrame.Day, start=start, end=end)
    bars = get_stock_data_client().get_stock_bars(request)
    return _bars_to_dicts(bars.df)


def sleep_between_symbols() -> None:
    time.sleep(INTER_SYMBOL_SLEEP_SECONDS)
