"""Direct alpaca-py REST/WebSocket client.

Used for high-frequency market data ingestion and historical pulls (backtest
data_loader) where going through the MCP/LLM stack would be pure overhead —
per the CLI vs MCP vs REST tradeoffs in PLAN.md. Trade EXECUTION still goes
through mcp_client.py so every live order carries the MCP-tool-call paper
trail the hackathon rewards.
"""

from functools import lru_cache

from alpaca.data.historical.option import OptionHistoricalDataClient
from alpaca.data.historical.stock import StockHistoricalDataClient
from alpaca.data.requests import OptionChainRequest, StockBarsRequest
from alpaca.data.timeframe import TimeFrame
from alpaca.trading.client import TradingClient

from app.config import get_settings

settings = get_settings()


@lru_cache
def _trading_client() -> TradingClient:
    return TradingClient(settings.alpaca_api_key, settings.alpaca_secret_key, paper=settings.alpaca_paper)


@lru_cache
def _stock_data_client() -> StockHistoricalDataClient:
    return StockHistoricalDataClient(settings.alpaca_api_key, settings.alpaca_secret_key)


@lru_cache
def _option_data_client() -> OptionHistoricalDataClient:
    return OptionHistoricalDataClient(settings.alpaca_api_key, settings.alpaca_secret_key)


def get_account_info() -> dict:
    account = _trading_client().get_account()
    return account.model_dump()


def get_all_positions() -> list[dict]:
    positions = _trading_client().get_all_positions()
    return [p.model_dump() for p in positions]


def get_recent_bars(symbol: str, limit: int = 100) -> dict:
    request = StockBarsRequest(symbol_or_symbols=symbol, timeframe=TimeFrame.Minute, limit=limit)
    bars = _stock_data_client().get_stock_bars(request)
    return bars.df.reset_index().to_dict(orient="records")


def get_option_chain(symbol: str) -> list[dict]:
    request = OptionChainRequest(underlying_symbol=symbol)
    chain = _option_data_client().get_option_chain(request)
    return [snapshot.model_dump() for snapshot in chain.values()]


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
