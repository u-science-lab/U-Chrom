"""Render a Jupyter notebook to standalone HTML via nbconvert.

Never raises: returns True on success, False on any failure (caller logs
a warning and continues — a failed notebook must not abort ingest).
"""
from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def render_notebook(nb_path: str, out_html: str) -> bool:
    src = Path(nb_path)
    if not src.exists():
        logger.warning("notebook not found: %s", src)
        return False
    try:
        import nbformat
        from nbconvert import HTMLExporter

        nb = nbformat.read(str(src), as_version=4)
        exporter = HTMLExporter()
        exporter.exclude_input_prompt = True
        body, _ = exporter.from_notebook_node(nb)
        out = Path(out_html)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(body, encoding="utf-8")
        return True
    except Exception as exc:  # noqa: BLE001 — degrade gracefully
        logger.warning("nbconvert failed for %s: %s", src, exc)
        return False
