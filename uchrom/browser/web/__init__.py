"""Web version of the U-Chrom structure browser.

A local FastAPI server exposes loaded ``ChromData`` over a small HTTP API
(``API.md``); a React + Three.js single-page app (``frontend/``, built into
``static/``) renders it in the browser.

    python -m uchrom.browser --web data.h5cd

Requires the ``web`` extra: ``pip install "u-chrom[web]"``.
"""

from __future__ import annotations

import socket
import threading
import webbrowser
from typing import Iterable, Optional

from .data import DatasetStore, decode_geometry, encode_geometry

__all__ = ["DatasetStore", "create_app", "decode_geometry", "encode_geometry", "serve"]


def create_app(store: Optional[DatasetStore] = None):
    """Build the FastAPI app (imported lazily so ``data`` works without FastAPI)."""
    from .server import create_app as _create_app

    return _create_app(store)


def _free_port(host: str, port: int, tries: int = 20) -> int:
    for candidate in range(port, port + tries):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind((host, candidate))
            except OSError:
                continue
            return candidate
    raise OSError(f"no free port in {port}-{port + tries - 1}")


def serve(paths: Iterable[str] = (), *, host: str = "127.0.0.1", port: int = 8765,
          open_browser: bool = True) -> None:
    """Load ``paths`` and serve the browser until interrupted."""
    try:
        import uvicorn
    except ImportError as exc:  # pragma: no cover - depends on environment
        raise ImportError(
            "The web browser needs the 'web' extra: pip install \"u-chrom[web]\""
        ) from exc

    store = DatasetStore()
    for path in paths:
        ds = store.load(path)
        print(f"[uchrom] loaded {ds.name}: {ds.cd.n_spots} spots, "
              f"{ds.cd.n_traces} traces")
    port = _free_port(host, port)
    url = f"http://{host}:{port}/"
    print(f"[uchrom] browser at {url}  (Ctrl+C to stop)")
    if open_browser:
        threading.Timer(1.0, webbrowser.open, args=(url,)).start()
    from ..client import clear_state, write_state
    write_state(url)  # lets uchrom.browser.connect() find this server
    try:
        uvicorn.run(create_app(store), host=host, port=port, log_level="warning")
    finally:
        clear_state(url)
