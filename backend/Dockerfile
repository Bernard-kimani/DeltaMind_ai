# DeltaMind AI backend — container image for Render deployment.
#
# Prep-only: this image has not been deploy-tested against Render itself.
# See docs/deployment.md for the cutover checklist before going live.

FROM python:3.11-slim

# uv gives us both `uv` (fast installs) and `uvx` on PATH. `uvx` is required
# at runtime: app/alpaca/mcp_client.py launches the Alpaca MCP server via
# `StdioServerParameters(command="uvx", args=["alpaca-mcp-server"], ...)`.
RUN pip install --no-cache-dir uv

WORKDIR /app

# No uv.lock / requirements.txt in this repo — install straight from
# pyproject.toml. The `postgres` extra pulls in psycopg2-binary so
# DATABASE_URL can point at Render's managed Postgres with zero code changes
# (see app/config.py: DATABASE_URL is read straight from env via
# pydantic-settings, SQLite is only the local default).
COPY pyproject.toml ./
COPY app ./app
COPY scripts ./scripts

RUN uv pip install --system --no-cache ".[postgres]"

# Render injects $PORT at runtime and routes traffic to it — do not hardcode
# 8000. Using the shell form so $PORT is expanded by the container's shell.
CMD uvicorn app.main:app --host 0.0.0.0 --port $PORT
