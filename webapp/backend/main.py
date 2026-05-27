import uuid, shutil, tempfile, os
from concurrent.futures import ProcessPoolExecutor
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, UploadFile, File
from pydantic import BaseModel
from typing import Any
from .session import Session
from .ws_handler import handle_message
from .data_api import data_router
from .tileset_api import tileset_router
import webapp.backend.data_api as _data_api

UPLOAD_DIR = tempfile.mkdtemp(prefix="uchrom_uploads_")


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.executor = ProcessPoolExecutor()
    yield
    app.state.executor.shutdown(wait=False)


app = FastAPI(title="U-Chrom WebApp", lifespan=lifespan)
app.state.executor = ProcessPoolExecutor()  # fallback for TestClient (no lifespan)
app.include_router(data_router)
from .tileset_api import tileset_router
app.include_router(tileset_router)
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


@app.post("/api/upload")
async def upload_file(file: UploadFile = File(...)):
    ext = os.path.splitext(file.filename or "")[1] or ".h5cd"
    dest = os.path.join(UPLOAD_DIR, f"{uuid.uuid4()}{ext}")
    with open(dest, "wb") as f:
        shutil.copyfileobj(file.file, f)
    return {"path": dest}


@app.get("/api/download")
async def download_file(path: str):
    """Download generated figure files."""
    from fastapi.responses import FileResponse

    # Security: only allow downloading from temp directory
    if not path.startswith("/tmp/") and not path.startswith(tempfile.gettempdir()):
        return {"error": "Invalid path"}

    if not os.path.exists(path):
        return {"error": "File not found"}

    filename = os.path.basename(path)
    return FileResponse(
        path,
        media_type="application/pdf" if path.endswith(".pdf") else "application/octet-stream",
        filename=filename
    )


@app.post("/api/session/save")
async def save_session(session_id: str):
    """Save current session to .uchromfig file."""
    session = sessions.get(session_id)
    if not session:
        return {"error": "Session not found"}

    # Generate filename
    import tempfile
    tmp = tempfile.NamedTemporaryFile(suffix=".uchromfig", delete=False, mode='w')
    tmp.close()

    # Save session
    session.save(tmp.name)

    return {
        "path": tmp.name,
        "filename": f"session_{session_id[:8]}.uchromfig"
    }


@app.post("/api/session/load")
async def load_session(file: UploadFile = File(...)):
    """Load session from .uchromfig file."""
    import tempfile
    from .session import Session

    # Save uploaded file
    tmp = tempfile.NamedTemporaryFile(suffix=".uchromfig", delete=False)
    shutil.copyfileobj(file.file, tmp)
    tmp.close()

    # Load session
    session_id = str(uuid.uuid4())
    session = Session.load(tmp.name, session_id)
    sessions[session_id] = session

    # Clean up
    os.unlink(tmp.name)

    return {
        "session_id": session_id,
        "state": session.to_dict()
    }


@app.post("/api/session/export_html")
async def export_html(session_id: str):
    """Export session as standalone HTML file."""
    session = sessions.get(session_id)
    if not session:
        return {"error": "Session not found"}

    # Load template
    template_path = os.path.join(os.path.dirname(__file__), "templates", "standalone.html")
    with open(template_path, 'r') as f:
        template = f.read()

    # Prepare data
    session_dict = session.to_dict()
    viewport = session_dict.get("viewport", {})

    # Replace placeholders
    html = template.replace("{{SESSION_ID}}", session_id[:8])
    html = html.replace("{{TIMESTAMP}}", session_dict.get("timestamp", ""))
    html = html.replace("{{VIEWPORT_CHROM}}", viewport.get("chrom") or "N/A")
    html = html.replace("{{VIEWPORT_START}}", str(viewport.get("start") or "N/A"))
    html = html.replace("{{VIEWPORT_END}}", str(viewport.get("end") or "N/A"))
    html = html.replace("{{SESSION_DATA}}", json.dumps(session_dict))

    # Save to temp file
    import tempfile
    tmp = tempfile.NamedTemporaryFile(suffix=".html", delete=False, mode='w')
    tmp.write(html)
    tmp.close()

    return {
        "path": tmp.name,
        "filename": f"uchrom_session_{session_id[:8]}.html"
    }


@app.get("/api/plugins")
async def list_plugins():
    """List all registered plugins."""
    from uchrom.plugins import list_plugins
    return {"plugins": list_plugins()}


@app.post("/api/plugins/load")
async def load_plugin_file(file: UploadFile = File(...)):
    """Load a plugin from uploaded .py file."""
    from uchrom.plugins import load_plugin
    import tempfile

    # Save uploaded file
    tmp = tempfile.NamedTemporaryFile(suffix=".py", delete=False)
    shutil.copyfileobj(file.file, tmp)
    tmp.close()

    try:
        plugin = load_plugin(tmp.name)
        return {
            "success": True,
            "plugin": {
                "name": plugin.name,
                "version": plugin.version,
                "description": plugin.description
            }
        }
    except Exception as e:
        return {"success": False, "error": str(e)}
    finally:
        os.unlink(tmp.name)


@app.post("/api/plugins/run")
async def run_plugin_analysis(plugin_name: str, session_id: str):
    """Run a plugin's analyze method on current session data."""
    from uchrom.plugins import run_plugin

    session = sessions.get(session_id)
    if not session:
        return {"error": "Session not found"}

    if session.chromdata is None:
        return {"error": "No data loaded"}

    try:
        result = run_plugin(plugin_name, session.chromdata)
        # Store result in session
        session.analysis_results[plugin_name] = result
        return {"success": True, "result": result}
    except Exception as e:
        return {"success": False, "error": str(e)}
