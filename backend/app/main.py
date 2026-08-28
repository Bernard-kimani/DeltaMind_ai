from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import (
    routes_account,
    routes_backtest,
    routes_config,
    routes_engine,
    routes_logs,
    routes_positions,
    routes_trades,
    ws,
)
from app.agent_loop_manager import get_manager
from app.config import get_settings
from app.db import repository as db_repo
from app.db.session import init_db

settings = get_settings()

app = FastAPI(title="DeltaMind AI", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.backend_cors_origins.split(",")],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(routes_account.router, prefix="/api/account", tags=["account"])
app.include_router(routes_positions.router, prefix="/api/positions", tags=["positions"])
app.include_router(routes_trades.router, prefix="/api/trades", tags=["trades"])
app.include_router(routes_backtest.router, prefix="/api/backtest", tags=["backtest"])
app.include_router(routes_config.router, prefix="/api/config", tags=["config"])
app.include_router(routes_engine.router, prefix="/api/engine", tags=["engine"])
app.include_router(routes_logs.router, prefix="/api/logs", tags=["logs"])
app.include_router(ws.router, tags=["ws"])


@app.on_event("startup")
def on_startup() -> None:
    init_db()
    # Track 1 and Track 4 run as independent concurrent engines — resume
    # whichever ones were running before this restart, not just one.
    for track in db_repo.list_tracks_with_run_state():
        get_manager(track).auto_resume_if_needed()


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "env": settings.app_env}
