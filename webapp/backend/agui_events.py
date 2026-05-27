"""AG-UI event type constants and WebSocket send helper."""
from __future__ import annotations
from fastapi import WebSocket


class AGUI:
    RUN_STARTED = "RUN_STARTED"
    TEXT_MESSAGE_START = "TEXT_MESSAGE_START"
    TEXT_MESSAGE_CONTENT = "TEXT_MESSAGE_CONTENT"
    TEXT_MESSAGE_END = "TEXT_MESSAGE_END"
    TOOL_CALL_START = "TOOL_CALL_START"
    TOOL_CALL_ARGS = "TOOL_CALL_ARGS"
    TOOL_CALL_END = "TOOL_CALL_END"
    RUN_FINISHED = "RUN_FINISHED"
    RUN_ERROR = "RUN_ERROR"


async def send_agui(ws: WebSocket, event_type: str, payload: dict) -> None:
    await ws.send_json({"type": event_type, "payload": payload})


TOOLS = [
    {
        "name": "set_viewport",
        "description": "Navigate the genomic viewer to a specific chromosomal region.",
        "input_schema": {
            "type": "object",
            "properties": {
                "chrom": {"type": "string"},
                "start": {"type": "integer"},
                "end": {"type": "integer"},
            },
            "required": ["chrom", "start", "end"],
        },
    },
    {
        "name": "select_cells",
        "description": "Select a subset of cells in the UMAP/3D view.",
        "input_schema": {
            "type": "object",
            "properties": {
                "mode": {"type": "string", "enum": ["cell_type", "manual", "all"]},
                "ids": {"type": "array", "items": {"type": "string"}},
                "label": {"type": "string"},
            },
            "required": ["mode", "ids", "label"],
        },
    },
    {
        "name": "highlight_region",
        "description": "Highlight genomic regions in the 3D structure view.",
        "input_schema": {
            "type": "object",
            "properties": {
                "regions": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "chrom": {"type": "string"},
                            "start": {"type": "integer"},
                            "end": {"type": "integer"},
                            "color": {"type": "string"},
                            "label": {"type": "string"},
                        },
                        "required": ["chrom", "start", "end"],
                    },
                }
            },
            "required": ["regions"],
        },
    },
    {
        "name": "set_colormap",
        "description": "Change the colormap used to render the 3D chromatin structure.",
        "input_schema": {
            "type": "object",
            "properties": {
                "scheme": {"type": "string"},
                "property": {"type": "string"},
                "range": {"type": "array", "items": {"type": "number"}, "minItems": 2, "maxItems": 2},
            },
            "required": ["scheme"],
        },
    },
    {
        "name": "run_python",
        "description": (
            "Execute Python analysis code in the backend sandbox. "
            "Available: cd (ChromData), uchrom, np, pd, emit_artifact(type, payload)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "code": {"type": "string"},
            },
            "required": ["code"],
        },
    },
]
