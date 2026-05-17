from fastapi import WebSocket
from .session import Session, Viewport


async def handle_message(ws: WebSocket, session: Session, msg: dict, executor) -> None:
    t = msg.get("type")
    p = msg.get("payload", {})

    if t == "load_data":
        # TODO: load uchrom data via ProcessPoolExecutor
        await ws.send_json({"type": "data_loaded", "payload": {}})

    elif t == "update_viewport":
        session.viewport = Viewport(**{k: p[k] for k in ("chrom", "start", "end") if k in p})

    elif t == "select_cells":
        session.cell_selection = p.get("ids", [])

    elif t == "run_analysis":
        # TODO: dispatch to ProcessPoolExecutor
        await ws.send_json({"type": "analysis_progress", "payload": {"job_id": None, "progress": 0, "status": "queued"}})

    elif t == "agent_message":
        await ws.send_json({"type": "not_implemented"})

    elif t == "artifact_action":
        await ws.send_json({"type": "not_implemented"})

    elif t == "export_figure":
        # TODO: render and serve
        await ws.send_json({"type": "export_ready", "payload": {"url": None, "format": p.get("format")}})

    else:
        await ws.send_json({"type": "error", "payload": {"message": f"unknown type: {t}"}})
