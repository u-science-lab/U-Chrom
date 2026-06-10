import uuid, shutil, tempfile, os, pathlib
from concurrent.futures import ProcessPoolExecutor
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, UploadFile, File
from pydantic import BaseModel
from typing import Any
from .session import Session
from .ws_handler import handle_message
from .data_api import data_router
from .tileset_api import tileset_router
from .track_wig import track_wig_router
from .strc_api import strc_router
from .figure_render import figure_render_router, build_svg, CANVAS_SIZES as _CANVAS_SIZES
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
app.include_router(tileset_router)
app.include_router(track_wig_router)
app.include_router(strc_router)
app.include_router(figure_render_router)

# HiGlass requests /api/v1/tileset_info and /api/v1/tiles — alias our endpoints
from .tileset_api import tileset_info, tiles as tiles_endpoint
app.add_api_route("/api/v1/tileset_info", tileset_info, methods=["GET"])
app.add_api_route("/api/v1/tiles/", tiles_endpoint, methods=["GET"])
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
        # Don't clear current_session on disconnect — REST APIs (tileset, data)
        # need to keep serving the last loaded data after the WS closes.


CANVAS_SIZES = {
    "nature-single": (336, 280),
    "nature-double": (692, 460),
    "science-double": (658, 440),
}


class ExportRequest(BaseModel):
    figure_state: Any
    format: str


@app.post("/api/export")
async def export_figure(req: ExportRequest):
    from fastapi.responses import Response
    state = req.figure_state or {}
    panels = state.get("panels", [])
    style = state.get("style", {})
    svg_content = build_svg(panels, style)
    return Response(
        content=svg_content,
        media_type="image/svg+xml",
        headers={"Content-Disposition": "attachment; filename=figure.svg"},
    )


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

    # Security: only allow downloading from temp directory (path traversal fix)
    from fastapi import HTTPException
    real = pathlib.Path(path).resolve()
    allowed = pathlib.Path(tempfile.gettempdir()).resolve()
    if not str(real).startswith(str(allowed) + os.sep) and str(real) != str(allowed):
        raise HTTPException(status_code=403, detail={"error": "Invalid path"})
    if not real.exists():
        raise HTTPException(status_code=404, detail={"error": "File not found"})

    filename = os.path.basename(path)
    if path.endswith(".pdf"):
        media_type = "application/pdf"
    elif path.endswith(".svg"):
        media_type = "image/svg+xml"
    else:
        media_type = "application/octet-stream"
    return FileResponse(path, media_type=media_type, filename=filename)


# =============================================================================
# Session persistence endpoints - DEPRECATED
# =============================================================================
# These backend session endpoints are unused and superseded by client-side
# implementation in App.tsx (saveSession/loadSession/shareLink functions).
# Client-side approach is simpler, faster, and doesn't require server state.
#
# If future server-side collaboration features (multi-user sessions, cloud sync)
# are needed, these can be re-implemented with proper database backing.
# =============================================================================

# @app.post("/api/session/save")
# async def save_session(session_id: str):
#     """Save current session to .uchromfig file."""
#     session = sessions.get(session_id)
#     if not session:
#         return {"error": "Session not found"}
#
#     # Generate filename
#     import tempfile
#     tmp = tempfile.NamedTemporaryFile(suffix=".uchromfig", delete=False, mode='w')
#     tmp.close()
#
#     # Save session
#     session.save(tmp.name)
#
#     return {
#         "path": tmp.name,
#         "filename": f"session_{session_id[:8]}.uchromfig"
#     }
#
#
# @app.post("/api/session/load")
# async def load_session(file: UploadFile = File(...)):
#     """Load session from .uchromfig file."""
#     import tempfile
#     from .session import Session
#
#     # Save uploaded file
#     tmp = tempfile.NamedTemporaryFile(suffix=".uchromfig", delete=False)
#     shutil.copyfileobj(file.file, tmp)
#     tmp.close()
#
#     # Load session
#     session_id = str(uuid.uuid4())
#     session = Session.load(tmp.name, session_id)
#     sessions[session_id] = session
#
#     # Clean up
#     os.unlink(tmp.name)
#
#     return {
#         "session_id": session_id,
#         "state": session.to_dict()
#     }
#
#
# @app.post("/api/session/export_html")
# async def export_html(session_id: str):
#     """Export session as standalone HTML file."""
#     session = sessions.get(session_id)
#     if not session:
#         return {"error": "Session not found"}
#
#     # Load template
#     template_path = os.path.join(os.path.dirname(__file__), "templates", "standalone.html")
#     with open(template_path, 'r') as f:
#         template = f.read()
#
#     # Prepare data
#     session_dict = session.to_dict()
#     viewport = session_dict.get("viewport", {})
#
#     # Replace placeholders
#     html = template.replace("{{SESSION_ID}}", session_id[:8])
#     html = html.replace("{{TIMESTAMP}}", session_dict.get("timestamp", ""))
#     html = html.replace("{{VIEWPORT_CHROM}}", viewport.get("chrom") or "N/A")
#     html = html.replace("{{VIEWPORT_START}}", str(viewport.get("start") or "N/A"))
#     html = html.replace("{{VIEWPORT_END}}", str(viewport.get("end") or "N/A"))
#     html = html.replace("{{SESSION_DATA}}", json.dumps(session_dict))
#
#     # Save to temp file
#     import tempfile
#     tmp = tempfile.NamedTemporaryFile(suffix=".html", delete=False, mode='w')
#     tmp.write(html)
#     tmp.close()
#
#     return {
#         "path": tmp.name,
#         "filename": f"uchrom_session_{session_id[:8]}.html"
#     }


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
