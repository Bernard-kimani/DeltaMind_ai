"""Client for Alpaca's Trading MCP Server v2 (PyPI package `alpaca-mcp-server`,
source: https://github.com/alpacahq/alpaca-mcp-server).

The agent talks to Alpaca through MCP tool calls (get_news, place_option_order,
etc.) rather than raw REST, per the hackathon's technology-implementation
scoring criteria. Launched via `uvx alpaca-mcp-server` — the officially
documented setup — which fetches the published package on first run; no local
git clone or path configuration needed (a clone still lives at
../alpaca-mcp-server, kept around for reading the real tool-registration
source rather than for running it).

This module wraps the raw MCP ClientSession with typed helpers so agent nodes
never touch the JSON-RPC plumbing directly.

place_option_order's shape is confirmed against alpaca-py's own
OptionLegRequest/OrderRequest models (the MCP server is generated from these
via FastMCP+OpenAPI, per Alpaca's docs) — see backend/.venv/.../alpaca/trading/requests.py.
get_news's exact return shape has NOT been independently verified against a
live call yet (see PLAN.md TODOs) — the parsing below is a best-effort first
cut, adjust once tested against a real response.
"""

import asyncio
import json
from contextlib import asynccontextmanager
from typing import Literal, TypedDict

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from app.config import get_settings

settings = get_settings()


class OptionLeg(TypedDict, total=False):
    symbol: str  # OCC option symbol, e.g. "AAPL250117C00150000"
    ratio_qty: float
    side: Literal["buy", "sell"]  # mutually exclusive with position_intent
    position_intent: Literal["buy_to_open", "buy_to_close", "sell_to_open", "sell_to_close"]


@asynccontextmanager
async def _session():
    params = StdioServerParameters(
        command="uvx",
        args=["alpaca-mcp-server"],
        env={
            "ALPACA_API_KEY": settings.alpaca_api_key,
            "ALPACA_SECRET_KEY": settings.alpaca_secret_key,
            "ALPACA_PAPER_TRADE": str(settings.alpaca_paper).lower(),
        },
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            yield session


async def _call_tool(name: str, arguments: dict) -> dict:
    """Normalizes a raw `CallToolResult` into a plain dict.

    Confirmed against the installed `mcp` SDK's actual attribute names
    (`is_error`, `structured_content` — both snake_case; verified via a real
    failing call during live testing, not assumed from docs): prefer
    structured_content when the tool declares an output schema (FastMCP
    auto-generates this from Pydantic return types), otherwise fall back to
    parsing the first text content block as JSON.
    """
    async with _session() as session:
        result = await session.call_tool(name, arguments)

        if result.is_error:
            text = "; ".join(getattr(block, "text", str(block)) for block in result.content)
            raise RuntimeError(f"MCP tool {name!r} returned an error: {text}")

        if result.structured_content is not None:
            return result.structured_content

        for block in result.content:
            text = getattr(block, "text", None)
            if text is not None:
                try:
                    return json.loads(text)
                except json.JSONDecodeError:
                    return {"text": text}
        return {}


def _run(coro):
    """Sync bridge — agent nodes are currently sync functions (see agents/*.py)."""
    return asyncio.run(coro)


def get_news(symbols: list[str], limit: int = 10) -> list[dict]:
    result = _run(_call_tool("get_news", {"symbols": symbols, "limit": limit}))
    return result.get("news", result.get("articles", []))


def place_option_order(
    symbol: str | None = None,
    side: Literal["buy", "sell"] | None = None,
    legs: list[OptionLeg] | None = None,
    order_class: Literal["mleg", "simple"] | None = None,
    order_type: Literal["market", "limit"] = "market",
    time_in_force: Literal["day", "gtc"] = "day",
    qty: float = 1,
    limit_price: float | None = None,
) -> dict:
    """Single- or multi-leg options order.

    True single-leg (Track 1): pass `symbol`/`side` at the top level, leave
    `legs`/`order_class` as None -- confirmed live on 2026-08-28 against the
    real alpaca-mcp-server source (overrides.py's place_option_order): a
    `legs` array (even a 1-element one) makes the server's own
    `is_multi_leg` check true regardless of what `order_class` string is
    passed, and Alpaca's real API then rejects it ("either side or
    position_intent must be set") since a `legs`-shaped body has no
    top-level `side` for it to read. This was silently broken all week --
    never exercised until a real order actually reached execution here.

    Multi-leg (Track 2/3's spreads, if used): pass `legs` (each needs
    `symbol`/`ratio_qty`/`side`) and `order_class="mleg"`; `symbol`/`side`
    at the top level aren't needed for this case per the server's own docstring.

    The MCP server's tool schema also requires qty/limit_price as strings,
    not native int/float -- confirmed via a separate real pydantic
    validation error while fixing this.
    """
    payload = {
        "type": order_type,
        "time_in_force": time_in_force,
        "qty": str(qty),
    }
    if symbol is not None:
        payload["symbol"] = symbol
    if side is not None:
        payload["side"] = side
    if legs is not None:
        payload["legs"] = legs
    if order_class is not None:
        payload["order_class"] = order_class
    if limit_price is not None:
        payload["limit_price"] = str(limit_price)
    return _run(_call_tool("place_option_order", payload))


def get_account_info() -> dict:
    return _run(_call_tool("get_account_info", {}))


def get_all_positions() -> list[dict]:
    return _run(_call_tool("get_all_positions", {}))


def close_position(symbol: str) -> dict:
    return _run(_call_tool("close_position", {"symbol": symbol}))
