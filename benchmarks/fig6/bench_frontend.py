"""Fig 6c — web browser: time to first frame and frame rate, measured in a real browser.

For each dataset: start the browser server with no data, open the dataset through the API (timed:
server-side read + index), then load the page in Chromium (new headless mode, Metal GPU) and read the
frontend's performance marks (`uchrom:geometry-request / -loaded / -drawn`, see frontend/src/perf.ts) and
the resource timing of the geometry request.  Frame rate is the requestAnimationFrame rate over a few
seconds with the overview drawn (the render loop redraws every frame).

    .venv/bin/python benchmarks/fig6/bench_frontend.py benchmarks/fig6/_data/takei2025_fov0_x*.chromdata.zarr \
        --out paper/fig6/results/frontend.json
"""
from __future__ import annotations

import argparse
import os
import json
import platform
import socket
import subprocess
import sys
import time
from pathlib import Path


def store_mb(path: Path) -> float:
    """Size on disk of a file or a directory store (.chromdata.zarr), in MB."""
    path = Path(path)
    if path.is_dir():
        return sum(f.stat().st_size for f in path.rglob("*") if f.is_file()) / 1e6
    return path.stat().st_size / 1e6

import requests
from playwright.sync_api import sync_playwright

LAUNCH = dict(headless=True, channel="chromium", args=["--enable-gpu", "--use-angle=metal", "--ignore-gpu-blocklist"])
VIEWPORT = dict(width=1600, height=1000)

GPU_JS = """() => { const gl = document.createElement('canvas').getContext('webgl2');
  const e = gl && gl.getExtension('WEBGL_debug_renderer_info');
  return gl ? (e ? gl.getParameter(e.UNMASKED_RENDERER_WEBGL) : gl.getParameter(gl.RENDERER)) : null }"""

MARKS_JS = """() => {
  const m = {}; for (const e of performance.getEntriesByType('mark'))
    if (e.name.startsWith('uchrom:')) (m[e.name.slice(7)] ||= []).push({t: e.startTime, detail: e.detail});
  const geo = performance.getEntriesByType('resource').filter(r => r.name.includes('/geometry'))
    .map(r => ({start: r.startTime, responseStart: r.responseStart, end: r.responseEnd,
                bytes: r.encodedBodySize || r.transferSize}));
  return {marks: m, geometry: geo} }"""

FPS_JS = """(ms) => new Promise(res => { const ts = []; const t0 = performance.now();
  function f(t) { ts.push(t); if (t - t0 < ms) requestAnimationFrame(f); else {
    const d = ts.slice(1).map((x, i) => x - ts[i]).sort((a, b) => a - b);
    res({frames: ts.length, fps: 1000 * (ts.length - 1) / (ts[ts.length - 1] - ts[0]),
         p50_ms: d[Math.floor(d.length / 2)], p95_ms: d[Math.floor(d.length * 0.95)]}) } }
  requestAnimationFrame(f) })"""


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def start_server(port: int) -> subprocess.Popen:
    proc = subprocess.Popen([sys.executable, "-m", "uchrom.browser", "--web", "--port", str(port),
                             "--noopen_browser"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(200):
        try:
            if requests.get(f"http://127.0.0.1:{port}/api/health", timeout=0.5).ok:
                return proc
        except requests.ConnectionError:
            pass
        time.sleep(0.1)
    proc.kill()
    raise RuntimeError("server did not start")


def bench_one(path: Path, reps: int, fps_ms: int, browser) -> dict:
    port = free_port()
    proc = start_server(port)
    base = f"http://127.0.0.1:{port}"
    try:
        t = time.perf_counter()
        r = requests.post(f"{base}/api/datasets", json={"path": str(path.resolve())}, timeout=600)
        r.raise_for_status()
        open_s = time.perf_counter() - t
        info = r.json()
        loads = []
        for i in range(reps):
            ctx = browser.new_context(viewport=VIEWPORT, device_scale_factor=2)
            page = ctx.new_page()
            page.goto(base + "/")
            page.wait_for_function("performance.getEntriesByName('uchrom:geometry-drawn').length > 0",
                                   timeout=600_000, polling=50)
            res = page.evaluate(MARKS_JS)
            mk = res["marks"]
            g = res["geometry"][0] if res["geometry"] else {}
            rec = {"rep": i,
                   "first_frame_ms": mk["geometry-drawn"][0]["t"],
                   "request_ms": mk["geometry-request"][0]["t"],
                   "loaded_ms": mk["geometry-loaded"][0]["t"],
                   "points": mk["geometry-loaded"][0]["detail"]["points"],
                   "response_start_ms": g.get("responseStart"), "response_end_ms": g.get("end"),
                   "bytes": g.get("bytes")}
            if i == 0:
                page.wait_for_timeout(500)
                rec["fps"] = page.evaluate(FPS_JS, fps_ms)
            loads.append(rec)
            ctx.close()
            print(f"  rep {i}: first frame {rec['first_frame_ms']:.0f} ms, points {rec['points']:,}, "
                  f"{(rec['bytes'] or 0) / 1e6:.1f} MB" + (f", {rec['fps']['fps']:.0f} fps" if 'fps' in rec else ""))
        return {"file": path.name, "file_mb": store_mb(path), "n_spots": info["n_spots"],
                "n_cells": info["n_cells"], "n_traces": info["n_traces"], "open_s": open_s, "loads": loads}
    finally:
        proc.terminate()
        proc.wait(10)


def check_quiet(max_load: float, force: bool, wait_s: float = 0) -> list:
    """Benchmarks need an idle machine: wait up to ``wait_s`` for the 1-min load average to drop below
    ``max_load``, then refuse (unless ``force``)."""
    t0 = time.time()
    while not force and os.getloadavg()[0] > max_load and time.time() - t0 < wait_s:
        time.sleep(15)
    load = list(os.getloadavg())
    if load[0] > max_load and not force:
        raise SystemExit(f"load average {load[0]:.1f} > {max_load}: close other work (or pass --force)")
    return load


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-load", type=float, default=2.0)
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--wait", type=float, default=1800, help="seconds to wait for a quiet machine")
    ap.add_argument("files", nargs="+", type=Path)
    ap.add_argument("--reps", type=int, default=5)
    ap.add_argument("--fps-ms", type=int, default=3000)
    ap.add_argument("--out", type=Path, default=Path("paper/fig6/results/frontend.json"))
    a = ap.parse_args()
    load = check_quiet(a.max_load, a.force, a.wait)
    out = {"machine": {"platform": platform.platform(), "processor": platform.processor(),
                       "python": platform.python_version(), "cpu_count": os.cpu_count()},
           "load_avg_start": load,
           "viewport": {**VIEWPORT, "device_scale_factor": 2}, "datasets": []}
    with sync_playwright() as p:
        browser = p.chromium.launch(**LAUNCH)
        pg = browser.new_page()
        out["machine"]["gpu"] = pg.evaluate(GPU_JS)
        out["machine"]["browser"] = f"chromium {browser.version}"
        pg.close()
        for f in a.files:
            print(f.name)
            out["datasets"].append(bench_one(f, a.reps, a.fps_ms, browser))
        browser.close()
    out["load_avg_end"] = list(os.getloadavg())
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(out, indent=1))
    print("->", a.out)


if __name__ == "__main__":
    main()
