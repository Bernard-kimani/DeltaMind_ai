"""Client for Alpaca MCP Server v2 (https://github.com/alpacahq/alpaca-mcp-server).

The agent talks to Alpaca through MCP tool calls (get_news, place_option_order,
etc.) rather than raw REST, per the hackathon's technology-implementation
scoring criteria. The server runs as a local subprocess (stdio transport) —
clone it per PLAN.md > Setup, then set ALPACA_MCP_SERVER_PATH in .env.

This module wraps the raw MCP ClientSession with typed helpers so agent nodes
never touch the JSON-RPC plumbing directly.
"""

import asyncio
from contextlib import asynccontextmanager

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from app.config import get_settings

settings = get_settings()


@asynccontextmanager
async def _session():
    params = StdioServerParameters(
        command="uv",
        args=["run", "alpaca-mcp-server"],
        cwd=settings.alpaca_mcp_server_path,
        env={
            "ALPACA_API_KEY": settings.alpaca_api_key,
            "ALPACA_SECRET_KEY": settings.alpaca_secret_key,
            "ALPACA_PAPER": str(settings.alpaca_paper),
        },
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            yield session


async def _call_tool(name: str, arguments: dict) -> dict:
    async with _session() as session:
        result = await session.call_tool(name, arguments)
        return result.content


def _run(coro):
    """Sync bridge — agent nodes are currently sync functions (see agents/*.py)."""
    return asyncio.run(coro)


def get_news(symbol: str) -> list[str]:
    result = _run(_call_tool("get_news", {"symbol": symbol}))
    return result.get("headlines", [])


def place_option_order(order: dict) -> dict:
    """order: {symbol, legs: [{side, ratio_qty, option_symbol}], order_type, time_in_force, ...}
    See Alpaca MCP v2's place_option_order tool schema for the exact shape.
    """
    return _run(_call_tool("place_option_order", order))


def get_account_info() -> dict:
    return _run(_call_tool("get_account_info", {}))


def get_all_positions() -> list[dict]:
    return _run(_call_tool("get_all_positions", {}))


def close_position(symbol: str) -> dict:
    return _run(_call_tool("close_position", {"symbol": symbol}))
