import uuid
from concurrent.futures import ProcessPoolExecutor
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from .session import Session
from .ws_handler import handle_message


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.executor = ProcessPoolExecutor()
    yield
    app.state.executor.shutdown(wait=False)


app = FastAPI(title="U-Chrom WebApp", lifespan=lifespan)
app.state.executor = ProcessPoolExecutor()  # fallback for TestClient (no lifespan)
sessions: dict[str, Session] = {}


@app.websocket("/ws/main")
async def ws_main(ws: WebSocket):
    await ws.accept()
    session_id = str(uuid.uuid4())
    session = Session(session_id=session_id)
    sessions[session_id] = session
    try:
        while True:
            msg = await ws.receive_json()
            await handle_message(ws, session, msg, app.state.executor)
    except WebSocketDisconnect:
        sessions.pop(session_id, None)
