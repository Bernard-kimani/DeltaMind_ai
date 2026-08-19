"""Pulls historical bars + options chains for backtesting via alpaca-py.
This is the pre-hackathon-legal way to validate strategy parameters (per
PLAN.md's rules table) before ever touching a live paper account.
"""

from alpaca.data.historical.option import OptionHistoricalDataClient
from alpaca.data.historical.stock import StockHistoricalDataClient
from alpaca.data.requests import OptionBarsRequest, StockBarsRequest
from alpaca.data.timeframe import TimeFrame

from app.config import get_settings

settings = get_settings()


def load_stock_bars(symbol: str, start: str, end: str):
    client = StockHistoricalDataClient(settings.alpaca_api_key, settings.alpaca_secret_key)
    request = StockBarsRequest(symbol_or_symbols=symbol, timeframe=TimeFrame.Day, start=start, end=end)
    return client.get_stock_bars(request).df


def load_option_bars(option_symbols: list[str], start: str, end: str):
    client = OptionHistoricalDataClient(settings.alpaca_api_key, settings.alpaca_secret_key)
    request = OptionBarsRequest(symbol_or_symbols=option_symbols, timeframe=TimeFrame.Day, start=start, end=end)
    return client.get_option_bars(request).df
