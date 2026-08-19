"""Thin wrapper around the Alpaca Trading CLI for low-overhead scheduled tasks
(e.g. a cron health-check or EOD position reconciliation) where spinning up
the MCP stdio server or an LLM call would be pure overhead. Returns parsed
JSON, mirroring the CLI's --json output mode.
"""

import json
import subprocess


def run_cli(*args: str) -> dict:
    result = subprocess.run(
        ["alpaca", *args, "--json"],
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(result.stdout)


def get_account_summary() -> dict:
    return run_cli("account", "show")


def list_positions() -> dict:
    return run_cli("positions", "list")
