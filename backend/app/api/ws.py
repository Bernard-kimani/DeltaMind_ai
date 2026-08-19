import asyncio
import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

router = APIRouter()


class ConnectionManager:
    """Broadcasts agent-loop events (ticks, decisions, fills) to connected dashboards."""

    def __init__(self) -> None:
        self.active: list[WebSocket] = []

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self.active.append(ws)

    def disconnect(self, ws: WebSocket) -> None:
        if ws in self.active:
            self.active.remove(ws)

    async def broadcast(self, event: dict) -> None:
        dead = []
        for ws in self.active:
            try:
                await ws.send_text(json.dumps(event))
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)


manager = ConnectionManager()


@router.websocket("/ws/live")
async def live_feed(websocket: WebSocket) -> None:
    await manager.connect(websocket)
    try:
        while True:
            # Client doesn't need to send anything; keep the connection alive.
            await asyncio.sleep(30)
            await websocket.send_text(json.dumps({"type": "ping"}))
    except WebSocketDisconnect:
        manager.disconnect(websocket)
