"""Direct alpaca-py REST/WebSocket client.

Used for high-frequency market data ingestion and historical pulls (backtest
data_loader) where going through the MCP/LLM stack would be pure overhead —
per the CLI vs MCP vs REST tradeoffs in PLAN.md. Trade EXECUTION still goes
through mcp_client.py so every live order carries the MCP-tool-call paper
trail the hackathon rewards.
"""

import functools
import logging
from datetime import date, timedelta
from functools import lru_cache, wraps

import requests
from alpaca.data.historical.option import OptionHistoricalDataClient
from alpaca.data.historical.stock import StockHistoricalDataClient
from alpaca.data.requests import OptionChainRequest, StockBarsRequest
from alpaca.data.timeframe import TimeFrame, TimeFrameUnit
from alpaca.trading.client import TradingClient
from alpaca.trading.enums import AssetStatus
from alpaca.trading.requests import GetOptionContractsRequest

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

# Covers Track 1's 14 DTE and Track 4's 14-30 DTE with margin either side.
CHAIN_DTE_WINDOW_DAYS = 45

# alpaca-py's REST client (alpaca.common.rest.RESTClient._one_request) calls
# self._session.request(...) with no `timeout` anywhere in its own code —
# confirmed by reading that module directly, not assumed. A stalled/dead
# connection (e.g. the same network blip that drops the market-data
# websocket) can therefore hang for as long as the OS takes to notice a dead
# socket — observed live on 2026-08-27: a single quant_engine cycle stalled
# 39s this way, blowing Track 1's 2s candle-to-decision budget by 20x.
# Patched onto each cached client's underlying `requests.Session` below
# rather than forked/subclassed, since alpaca-py exposes no constructor
# param for this at all.
REST_TIMEOUT_SECONDS = 15

# requests.Session()'s default HTTPAdapter caps at 10 pooled connections per
# host (urllib3's pool_maxsize). market_ingestion.py's concurrent per-symbol
# fetches all share these same cached clients (one requests.Session per
# client, process-wide), and Track 1's websocket delivers every watched
# symbol's bar-close within the same second — 15 symbols x up to 2-3
# concurrent REST calls each can mean 30-45 simultaneous requests to
# data.alpaca.markets against a 10-connection pool. Observed live on
# 2026-08-27: "Connection pool is full, discarding connection" warnings on
# nearly every bar close, each discarded connection forcing a fresh TCP+TLS
# handshake on the next call — a single cycle's market_ingestion jumped from
# the ~500-900ms baseline to 4100-4200ms, blowing the 2s latency budget.
# Sized to comfortably cover the full 15-symbol watchlist at max concurrency
# with headroom, not tuned to today's exact watchlist size.
REST_POOL_MAXSIZE = 50


def _with_default_timeout(client):
    """Binds a default `timeout` onto `client._session.request` via
    functools.partial — safe because alpaca-py's own `_one_request` never
    passes `timeout` itself (confirmed by reading rest.py), so there's no
    "got multiple values for keyword argument" collision. This is the only
    way to enforce a timeout here at all: `_session` is a plain
    `requests.Session()` with no per-call timeout hook exposed by the
    client's public API. Also widens the session's connection pool (see
    REST_POOL_MAXSIZE) — same "no constructor param for this" constraint
    applies, so it's mounted directly onto the session's adapters."""
    client._session.request = functools.partial(client._session.request, timeout=REST_TIMEOUT_SECONDS)
    adapter = requests.adapters.HTTPAdapter(pool_maxsize=REST_POOL_MAXSIZE, pool_connections=REST_POOL_MAXSIZE)
    client._session.mount("https://", adapter)
    client._session.mount("http://", adapter)
    return client


@lru_cache
def _trading_client() -> TradingClient:
    return _with_default_timeout(TradingClient(settings.alpaca_api_key, settings.alpaca_secret_key, paper=settings.alpaca_paper))


@lru_cache
def _stock_data_client() -> StockHistoricalDataClient:
    return _with_default_timeout(StockHistoricalDataClient(settings.alpaca_api_key, settings.alpaca_secret_key))


def get_stock_data_client() -> StockHistoricalDataClient:
    """Public accessor for backend/app/backtest/historical_data.py — reuses
    this module's cached, timeout-patched, retry-wrapped singleton instead
    of backtest/data_loader.py's old pattern of building a fresh, uncached
    client per call (no timeout, no retry, exactly the gaps this module's
    live-path clients already closed)."""
    return _stock_data_client()


@lru_cache
def _option_data_client() -> OptionHistoricalDataClient:
    return _with_default_timeout(OptionHistoricalDataClient(settings.alpaca_api_key, settings.alpaca_secret_key))


def _retry_once_on_disconnect(fn):
    """alpaca-py's own retry (see alpaca.common.rest._one_request) only
    covers HTTP-level rate-limit responses — a transport-level drop from a
    stale pooled keep-alive connection (idle socket closed server-side
    between calls, since _trading_client()/_option_data_client() are
    long-lived @lru_cache singletons for the process lifetime) surfaces as
    a raw ConnectionError instead, uncaught by that retry loop. `Timeout`
    (raised by REST_TIMEOUT_SECONDS above, a sibling exception class, not a
    ConnectionError subclass) gets the same one-retry treatment — a fresh
    connection after a bounded wait is much more likely to succeed than
    hanging again. One immediate retry is enough: the dead/slow connection
    gets evicted from the pool on failure, so the retry opens a fresh socket."""
    @wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as exc:
            logger.warning("%s: %s, retrying once", fn.__name__, type(exc).__name__)
            return fn(*args, **kwargs)
    return wrapper


@_retry_once_on_disconnect
def get_account_info() -> dict:
    account = _trading_client().get_account()
    return account.model_dump()


@_retry_once_on_disconnect
def get_all_positions() -> list[dict]:
    positions = _trading_client().get_all_positions()
    return [p.model_dump() for p in positions]


@_retry_once_on_disconnect
def get_recent_bars(symbol: str, limit: int = 100) -> dict:
    request = StockBarsRequest(symbol_or_symbols=symbol, timeframe=TimeFrame.Minute, limit=limit)
    bars = _stock_data_client().get_stock_bars(request)
    return bars.df.reset_index().to_dict(orient="records")


@_retry_once_on_disconnect
def get_15m_bars(symbol: str, limit: int = 60) -> list[dict]:
    """Native 15-minute bars — used by technical_signals.check_track1_confluence's
    50-period EMA trend check. Fetched directly rather than resampled from
    get_recent_bars' 1-minute window: 500 1-minute bars only resample to
    ~33 complete 15-minute candles, not enough to seed a stable 50-period
    EMA; 60 native 15-minute bars covers it cleanly."""
    request = StockBarsRequest(symbol_or_symbols=symbol, timeframe=TimeFrame(15, TimeFrameUnit.Minute), limit=limit)
    bars = _stock_data_client().get_stock_bars(request)
    return bars.df.reset_index().to_dict(orient="records")


@_retry_once_on_disconnect
def get_daily_bars(symbol: str, limit: int = 20) -> list[dict]:
    """Daily (not minute) bars — used by watchlist.py's liquidity pre-filter
    for average daily volume, distinct from get_recent_bars' minute bars
    (used by technical_signals.py's breakout detection)."""
    request = StockBarsRequest(symbol_or_symbols=symbol, timeframe=TimeFrame.Day, limit=limit)
    bars = _stock_data_client().get_stock_bars(request)
    return bars.df.reset_index().to_dict(orient="records")


@_retry_once_on_disconnect
def get_option_chain(symbol: str) -> list[dict]:
    """Flattens two separate Alpaca APIs into one per-contract dict, joined
    on the OCC contract symbol — neither alone has what `closest_by_delta()`
    needs:

    - `TradingClient.get_option_contracts()` (contract metadata): type,
      strike_price, expiration_date, open_interest.
    - `OptionHistoricalDataClient.get_option_chain()` (market-data snapshot):
      bid/ask, greeks, implied volatility.

    Confirmed bug this replaces: the old version returned raw
    `OptionsSnapshot.model_dump()`s, which have no `type`/`strike_price`/
    `expiration_date`/flat `bid`/`ask` fields at all — `closest_by_delta()`'s
    `c.get("type")` filter could never match anything, so it always returned
    `None`, so every strategy silently failed to ever build a real order.
    """
    today = date.today()
    window_end = today + timedelta(days=CHAIN_DTE_WINDOW_DAYS)

    contracts_request = GetOptionContractsRequest(
        underlying_symbols=[symbol],
        status=AssetStatus.ACTIVE,
        expiration_date_gte=today,
        expiration_date_lte=window_end,
        limit=10000,
    )
    contracts_response = _trading_client().get_option_contracts(contracts_request)
    contracts = {c.symbol: c for c in (contracts_response.option_contracts or [])}
    if contracts_response.next_page_token:
        logger.warning("Option contracts for %s truncated at 10000 — more than one page available", symbol)

    snapshot_request = OptionChainRequest(
        underlying_symbol=symbol,
        expiration_date_gte=today,
        expiration_date_lte=window_end,
    )
    snapshots = _option_data_client().get_option_chain(snapshot_request)

    flattened = []
    for occ_symbol, contract in contracts.items():
        snapshot = snapshots.get(occ_symbol)
        if snapshot is None or snapshot.latest_quote is None:
            continue

        bid = snapshot.latest_quote.bid_price
        ask = snapshot.latest_quote.ask_price
        if not bid or not ask:
            # Unquoted contract — not a real candidate. Doubles as a first
            # liquidity screen: illiquid strikes tend to have no live quote.
            continue

        flattened.append({
            "symbol": occ_symbol,
            "type": contract.type.value,
            "strike_price": contract.strike_price,
            "expiration_date": contract.expiration_date,
            "open_interest": int(contract.open_interest) if contract.open_interest else None,
            "bid": bid,
            "ask": ask,
            "mid": (bid + ask) / 2,
            "spread_pct": (ask - bid) / ask,
            "implied_volatility": snapshot.implied_volatility,
            "greeks": snapshot.greeks.model_dump() if snapshot.greeks else None,
        })

    return flattened


def test_connection(api_key: str | None = None, secret_key: str | None = None) -> tuple[bool, str]:
    """Backs the Controls tab's "Test Alpaca Connection" button — confirms
    the given (or default) credentials actually authenticate against
    Alpaca. Explicit api_key/secret_key (see routes_config.py, which
    resolves them per-track via get_alpaca_credentials) build a one-off,
    uncached TradingClient rather than going through _trading_client()'s
    process-wide @lru_cache singleton — that cache is deliberately keyed to
    whichever single account the live trading subprocess itself uses, and
    can't answer "test this OTHER account's key" from the same backend
    process without a separate client instance."""
    key = api_key if api_key is not None else settings.alpaca_api_key
    secret = secret_key if secret_key is not None else settings.alpaca_secret_key
    if not key or not secret:
        return False, "ALPACA_API_KEY / ALPACA_SECRET_KEY not set in .env"
    try:
        client = _trading_client() if api_key is None and secret_key is None else TradingClient(key, secret, paper=settings.alpaca_paper)
        account = client.get_account()
        mode = "paper" if settings.alpaca_paper else "LIVE"
        return True, f"Connected ({mode}) — account {account.account_number}, equity ${account.equity}"
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}"
