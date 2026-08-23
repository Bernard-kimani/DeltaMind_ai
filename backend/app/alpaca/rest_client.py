"""Direct alpaca-py REST/WebSocket client.

Used for high-frequency market data ingestion and historical pulls (backtest
data_loader) where going through the MCP/LLM stack would be pure overhead —
per the CLI vs MCP vs REST tradeoffs in PLAN.md. Trade EXECUTION still goes
through mcp_client.py so every live order carries the MCP-tool-call paper
trail the hackathon rewards.
"""

import logging
from datetime import date, timedelta
from functools import lru_cache, wraps

import requests
from alpaca.data.historical.option import OptionHistoricalDataClient
from alpaca.data.historical.stock import StockHistoricalDataClient
from alpaca.data.requests import OptionChainRequest, StockBarsRequest
from alpaca.data.timeframe import TimeFrame
from alpaca.trading.client import TradingClient
from alpaca.trading.enums import AssetStatus
from alpaca.trading.requests import GetOptionContractsRequest

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

# Covers Track 1's 14 DTE and Track 4's 14-30 DTE with margin either side.
CHAIN_DTE_WINDOW_DAYS = 45


@lru_cache
def _trading_client() -> TradingClient:
    return TradingClient(settings.alpaca_api_key, settings.alpaca_secret_key, paper=settings.alpaca_paper)


@lru_cache
def _stock_data_client() -> StockHistoricalDataClient:
    return StockHistoricalDataClient(settings.alpaca_api_key, settings.alpaca_secret_key)


@lru_cache
def _option_data_client() -> OptionHistoricalDataClient:
    return OptionHistoricalDataClient(settings.alpaca_api_key, settings.alpaca_secret_key)


def _retry_once_on_disconnect(fn):
    """alpaca-py's own retry (see alpaca.common.rest._one_request) only
    covers HTTP-level rate-limit responses — a transport-level drop from a
    stale pooled keep-alive connection (idle socket closed server-side
    between calls, since _trading_client()/_option_data_client() are
    long-lived @lru_cache singletons for the process lifetime) surfaces as
    a raw ConnectionError instead, uncaught by that retry loop. One
    immediate retry is enough: the dead connection gets evicted from the
    pool on failure, so the retry opens a fresh socket."""
    @wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except requests.exceptions.ConnectionError:
            logger.warning("%s: connection dropped, retrying once", fn.__name__)
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


def test_connection() -> tuple[bool, str]:
    """Backs the Controls tab's "Test Alpaca Connection" button — confirms
    the credentials in `.env` actually authenticate against Alpaca."""
    if not settings.alpaca_api_key or not settings.alpaca_secret_key:
        return False, "ALPACA_API_KEY / ALPACA_SECRET_KEY not set in .env"
    try:
        account = _trading_client().get_account()
        mode = "paper" if settings.alpaca_paper else "LIVE"
        return True, f"Connected ({mode}) — account {account.account_number}, equity ${account.equity}"
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}"
