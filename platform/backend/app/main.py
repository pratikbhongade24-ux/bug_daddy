from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from app.api import agents, dashboard, issues, runs, triggers
from app.core.config import get_settings
from app.db import Base, SessionLocal, engine
from app.services.realtime import realtime_manager
from app.services.seed import seed_platform

settings = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        seed_platform(db)
    yield


app = FastAPI(
    title="Bug Daddy Platform API",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(dashboard.router)
app.include_router(issues.router)
app.include_router(triggers.router)
app.include_router(agents.router)
app.include_router(runs.router)


@app.get("/health")
def healthcheck():
    return {"status": "ok", "env": settings.app_env}


@app.websocket("/ws/dashboard")
async def dashboard_ws(websocket: WebSocket):
    await realtime_manager.connect_dashboard(websocket)
    await websocket.send_json({"kind": "hello", "channel": "dashboard"})
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        realtime_manager.disconnect_dashboard(websocket)


@app.websocket("/ws/runs/{run_id}")
async def run_ws(websocket: WebSocket, run_id: int):
    await realtime_manager.connect_run(run_id, websocket)
    await websocket.send_json({"kind": "hello", "channel": "run", "run_id": run_id})
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        realtime_manager.disconnect_run(run_id, websocket)
