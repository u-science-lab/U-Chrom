"""HTML visualization entrypoint for U-Chrom idea graphs."""

from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any

from .graph import IdeaGraph, load_idea_graph


_UI_DIST = Path(__file__).with_name("ui") / "dist"
_UI_JS = _UI_DIST / "idea-graph.iife.js"
_UI_CSS = _UI_DIST / "style.css"


def write_idea_graph_html(
    graph: IdeaGraph | str | Path,
    output_path: str | Path,
    *,
    title: str = "U-Chrom Idea Graph",
    notebook_base_url: str | None = None,
) -> Path:
    """Write a self-contained Vue-powered interactive idea-graph viewer."""
    if not isinstance(graph, IdeaGraph):
        graph = load_idea_graph(graph)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = graph.to_dict()
    if notebook_base_url:
        payload["notebook_base_url"] = notebook_base_url.rstrip("/")
    output_path.write_text(_html_template(title, payload), encoding="utf-8")
    return output_path


def _html_template(title: str, payload: dict[str, Any]) -> str:
    css, js = _load_ui_bundle()
    data = json.dumps(payload, default=str).replace("</", "<\\/")
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(title)}</title>
  <style>{css}</style>
</head>
<body>
  <div id="uchrom-idea-graph-app"></div>
  <script id="uchrom-idea-graph-data" type="application/json">{data}</script>
  <script>{js}</script>
</body>
</html>
"""


def _load_ui_bundle() -> tuple[str, str]:
    """Load the checked-in Vite bundle used by static graph exports."""
    if not _UI_JS.exists() or not _UI_CSS.exists():
        raise FileNotFoundError(
            "The auto-discovery graph UI bundle is missing. "
            "Run `npm install && npm run build` in uchrom/auto_discovery/ui."
        )
    return _UI_CSS.read_text(encoding="utf-8"), _UI_JS.read_text(encoding="utf-8")
