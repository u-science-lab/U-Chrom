"""Figure rendering: embed panel screenshots into SVG layout.

Endpoint: POST /api/figure_render
Body: {
  "panels": [{"id": "...", "label": "...", "x": 0, "y": 0, "w": 300, "h": 200, "image": "data:image/png;base64,..."}],
  "style": {"sizePreset": "nature-double", "fontSize": 7},
}
Returns: SVG file (image/svg+xml)
"""
from typing import Any, List, Optional

from fastapi import APIRouter
from fastapi.responses import Response
from pydantic import BaseModel

figure_render_router = APIRouter()

CANVAS_SIZES = {
    "nature-single": (336, 280),
    "nature-double": (692, 460),
    "science-double": (658, 440),
}


class PanelCapture(BaseModel):
    id: str
    label: str
    x: float
    y: float
    w: float
    h: float
    image: Optional[str] = None  # data:image/png;base64,...


class FigureRenderRequest(BaseModel):
    panels: List[PanelCapture]
    style: Any = None


def build_svg(panels, style) -> str:
    """Build SVG content from panels and style. Shared by figure_render and export endpoints."""
    if not isinstance(style, dict):
        style = {}
    preset = style.get("sizePreset", "nature-double")
    font_size = style.get("fontSize", 7)
    w, h = CANVAS_SIZES.get(preset, (692, 460))

    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink"'
        f' width="{w}" height="{h}" viewBox="0 0 {w} {h}">',
        f'  <rect width="{w}" height="{h}" fill="white"/>',
    ]

    for p in panels:
        # Support both dict (from export) and object (from figure_render)
        if isinstance(p, dict):
            px, py, pw, ph = p.get("x", 0), p.get("y", 0), p.get("w", 100), p.get("h", 80)
            label = str(p.get("label", ""))
            image = p.get("image")
        else:
            px, py, pw, ph = p.x, p.y, p.w, p.h
            label = p.label
            image = p.image

        label = label.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

        # Embed screenshot if provided
        if image and image.startswith("data:image/"):
            lines.append(
                f'  <image x="{px}" y="{py}" width="{pw}" height="{ph}"'
                f' xlink:href="{image}" preserveAspectRatio="xMidYMid meet"/>'
            )

        # Border
        lines.append(
            f'  <rect x="{px}" y="{py}" width="{pw}" height="{ph}"'
            f' fill="none" stroke="#333" stroke-width="0.5"/>'
        )
        # Label
        lines.append(
            f'  <text x="{px + 2}" y="{py + font_size + 1}"'
            f' font-family="Arial,sans-serif" font-size="{font_size}" fill="#333">{label}</text>'
        )

    lines.append("</svg>")
    return "\n".join(lines)


@figure_render_router.post("/api/figure_render")
async def render_figure(req: FigureRenderRequest):
    style = req.style or {}
    svg_content = build_svg(req.panels, style)
    return Response(
        content=svg_content,
        media_type="image/svg+xml",
        headers={"Content-Disposition": "attachment; filename=figure.svg"},
    )
