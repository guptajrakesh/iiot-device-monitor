import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect

logging.basicConfig(level=logging.INFO)
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from .db import SessionLocal, init_db
from .mqtt_ingest import ingest_loop
from .routers import alerts, gateways, history, instances, templates
from .seed import seed_if_empty
from .ws_manager import WSManager

ws_manager = WSManager()


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    session = SessionLocal()
    try:
        seed_if_empty(session)
    finally:
        session.close()
    task = asyncio.create_task(ingest_loop(ws_manager))
    yield
    task.cancel()


app = FastAPI(title="IIoT Device Monitor", lifespan=lifespan)
app.include_router(templates.router)
app.include_router(instances.router)
app.include_router(gateways.router)
app.include_router(alerts.router)
app.include_router(alerts.events_router)
app.include_router(history.router)


@app.get("/api/readings/latest")
def latest_readings():
    session = SessionLocal()
    try:
        rows = session.execute(
            text(
                "SELECT DISTINCT ON (device_instance_id, tag_key) "
                "device_instance_id, tag_key, value, quality, time "
                "FROM readings ORDER BY device_instance_id, tag_key, time DESC"
            )
        ).fetchall()
        return [dict(r._mapping) for r in rows]
    finally:
        session.close()


@app.websocket("/ws/live")
async def websocket_live(ws: WebSocket):
    await ws_manager.connect(ws)
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        ws_manager.disconnect(ws)


app.mount("/", StaticFiles(directory="app/static", html=True), name="static")
