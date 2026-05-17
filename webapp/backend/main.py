import uuid
from concurrent.futures import ProcessPoolExecutor
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
from typing import Any
from .session import Session
from .ws_handler import handle_message
from .data_api import data_router
import webapp.backend.data_api as _data_api


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.executor = ProcessPoolExecutor()
    yield
    app.state.executor.shutdown(wait=False)


app = FastAPI(title="U-Chrom WebApp", lifespan=lifespan)
app.state.executor = ProcessPoolExecutor()  # fallback for TestClient (no lifespan)
app.include_router(data_router)
sessions: dict[str, Session] = {}


@app.websocket("/ws/main")
async def ws_main(ws: WebSocket):
    await ws.accept()
    session_id = str(uuid.uuid4())
    session = Session(session_id=session_id)
    sessions[session_id] = session
    _data_api.current_session = session
    try:
        while True:
            msg = await ws.receive_json()
            await handle_message(ws, session, msg, app.state.executor)
    except WebSocketDisconnect:
        sessions.pop(session_id, None)
        if _data_api.current_session is session:
            _data_api.current_session = None


class ExportRequest(BaseModel):
    figure_state: Any
    format: str


@app.post("/api/export")
async def export_figure(req: ExportRequest):
    return {"url": "/exports/figure.svg"}
