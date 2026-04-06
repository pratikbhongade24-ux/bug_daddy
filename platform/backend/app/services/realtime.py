from __future__ import annotations

from collections import defaultdict
from typing import Any

from fastapi import WebSocket


class RealtimeManager:
    def __init__(self) -> None:
        self.dashboard_connections: set[WebSocket] = set()
        self.run_connections: dict[int, set[WebSocket]] = defaultdict(set)

    async def connect_dashboard(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self.dashboard_connections.add(websocket)

    async def connect_run(self, run_id: int, websocket: WebSocket) -> None:
        await websocket.accept()
        self.run_connections[run_id].add(websocket)

    def disconnect_dashboard(self, websocket: WebSocket) -> None:
        self.dashboard_connections.discard(websocket)

    def disconnect_run(self, run_id: int, websocket: WebSocket) -> None:
        connections = self.run_connections.get(run_id)
        if not connections:
            return
        connections.discard(websocket)
        if not connections:
            self.run_connections.pop(run_id, None)

    async def broadcast_dashboard(self, payload: dict[str, Any]) -> None:
        dead: list[WebSocket] = []
        for websocket in self.dashboard_connections:
            try:
                await websocket.send_json(payload)
            except Exception:  # noqa: BLE001
                dead.append(websocket)
        for websocket in dead:
            self.disconnect_dashboard(websocket)

    async def broadcast_run(self, run_id: int, payload: dict[str, Any]) -> None:
        dead: list[WebSocket] = []
        for websocket in self.run_connections.get(run_id, set()):
            try:
                await websocket.send_json(payload)
            except Exception:  # noqa: BLE001
                dead.append(websocket)
        for websocket in dead:
            self.disconnect_run(run_id, websocket)


realtime_manager = RealtimeManager()
