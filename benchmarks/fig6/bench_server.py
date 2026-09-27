"""Fig 6c — web browser: latency of each interaction, measured against the running server over HTTP.

Each interaction is the request(s) the page sends for it, timed end to end from the client (connection,
server work, transfer).  Requests the page sends in parallel are sent in parallel here too.
Group-based interactions use a fresh random group each repetition, so no server-side cache is hit;
the first call of every interaction (cold) is reported separately.  Drawing time is not included; it is
measured by bench_frontend.py.

    .venv/bin/python benchmarks/fig6/bench_server.py \
        --imaging example-data/takei2025_fov0/takei2025_fov0.chromdata.zarr \
        --scaled benchmarks/fig6/_data/takei2025_fov0_x10.chromdata.zarr benchmarks/fig6/_data/takei2025_fov0_x30.chromdata.zarr \
        --hic example-data/schicar_mop/schicar_mop.chromdata.zarr --out paper/fig6/results/server.json
"""
from __future__ import annotations

import argparse
import os
import json
import platform
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import requests

from bench_frontend import check_quiet, free_port, start_server

RNG = np.random.default_rng(0)


def timed(fn):
    t = time.perf_counter()
    fn()
    return (time.perf_counter() - t) * 1e3


def ok(r):
    r.raise_for_status()
    return r


class Client:
    def __init__(self, base):
        self.base, self.s = base, requests.Session()

    def get(self, path, **params):
        return ok(self.s.get(self.base + path, params=params, timeout=600))

    def post(self, path, body):
        return ok(self.s.post(self.base + path, json=body, timeout=600))

    def group(self, did, cells, name="bench"):
        return self.post(f"/api/datasets/{did}/groups", {"cells": list(cells), "name": name}).json()["id"]

    def parallel(self, *calls):
        with ThreadPoolExecutor(len(calls)) as ex:
            for f in [ex.submit(c) for c in calls]:
                f.result()


def run(name, fn, reps, out):
    cold = fn()
    warm = [fn() for _ in range(reps)]
    out.append({"interaction": name, "cold_ms": cold, "ms": warm,
                "median_ms": float(np.median(warm)), "p95_ms": float(np.percentile(warm, 95))})
    print(f"  {name:38s} cold {cold:7.1f}  median {np.median(warm):7.1f}  p95 {np.percentile(warm, 95):7.1f} ms")


def imaging_interactions(c, did, info, reps, out, chrom="chr15", tracks=True):
    cells = [x["cell_id"] for x in c.get(f"/api/datasets/{did}/cells", limit=100000).json()["cells"]]
    D = f"/api/datasets/{did}"

    def focus():
        cell = str(RNG.choice(cells))
        return timed(lambda: c.parallel(lambda: c.post(D + "/geometry", {"cell_ids": [cell]}),
                                        lambda: c.get(D + "/cell_info", cell_id=cell)))

    def lasso():
        sel = RNG.choice(cells, size=min(8, len(cells)), replace=False)

        def go():
            g = c.group(did, sel)
            calls = [lambda: c.post(D + "/geometry", {"cell_ids": list(map(str, sel))}),
                     lambda: c.get(D + "/distance", chrom=chrom, group=g),
                     lambda: c.get(D + "/stats/rg", group=g)]
            if tracks:
                calls.append(lambda: c.get(D + "/tracks", names="H3K27ac,H3K9me3", chrom=chrom, group=g))
            c.parallel(*calls)
        return timed(go)

    def pan():
        s = int(RNG.integers(3, 80)) * 1_000_000
        return timed(lambda: c.get(D + "/tracks", names="H3K27ac,H3K9me3", chrom=chrom, start=s, end=s + 20_000_000))

    def dist_all():
        return timed(lambda: c.get(D + "/distance", chrom=chrom))

    def dist_group():
        g = c.group(did, RNG.choice(cells, size=min(20, len(cells)), replace=False))
        return timed(lambda: c.get(D + "/distance", chrom=chrom, group=g))

    run("focus a cell", focus, reps, out)
    run("lasso → re-scope views", lasso, reps, out)
    if tracks:
        run("pan locus (2 tracks, 20 Mb)", pan, reps, out)
    run(f"distance map, {chrom}, all cells", dist_all, max(3, reps // 4), out)
    run(f"distance map, {chrom}, 20-cell group", dist_group, reps, out)


def hic_interactions(c, did, info, reps, out, chrom="chr1"):
    D = f"/api/datasets/{did}"
    maps = {m["kind"]: m for m in info.get("contact_maps", [])}
    cells = [x["cell_id"] for x in c.get(D + "/cells", limit=100000).json()["cells"]]
    if "mcool" in maps:
        key = maps["mcool"]["key"]
        run(f"contact map, {chrom} (≤1,000 bins)", lambda: timed(lambda: c.get(f"{D}/contacts/{key}", chrom=chrom)),
            reps, out)
    if "scool" in maps:
        key = maps["scool"]["key"]
        for n in (50, 500):
            def pb(n=n):
                g = c.group(did, RNG.choice(cells, size=n, replace=False))
                return timed(lambda: c.get(f"{D}/contacts/{key}", chrom=chrom, group=g))
            run(f"pseudo-bulk, {n} cells, {chrom}", pb, reps, out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--imaging", type=Path, required=True)
    ap.add_argument("--scaled", type=Path, nargs="*", default=[])
    ap.add_argument("--hic", type=Path)
    ap.add_argument("--reps", type=int, default=20)
    ap.add_argument("--max-load", type=float, default=2.0)
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--wait", type=float, default=1800, help="seconds to wait for a quiet machine")
    ap.add_argument("--out", type=Path, default=Path("paper/fig6/results/server.json"))
    a = ap.parse_args()
    load = check_quiet(a.max_load, a.force, a.wait)
    port = free_port()
    proc = start_server(port)
    c = Client(f"http://127.0.0.1:{port}")
    res = {"machine": {"platform": platform.platform(), "processor": platform.processor(),
                       "python": platform.python_version(), "cpu_count": os.cpu_count()},
           "load_avg_start": load, "reps": a.reps, "datasets": []}
    try:
        jobs = [(a.imaging, "imaging", True)] + [(p, "imaging-replicated", False) for p in a.scaled]
        if a.hic:
            jobs.append((a.hic, "hic", None))
        for path, kind, tracks in jobs:
            info = c.post("/api/datasets", {"path": str(path.resolve())}).json()
            print(f"{path.name}: {info['n_spots']:,} spots, {info['n_cells']:,} cells")
            rows = []
            if kind == "hic":
                hic_interactions(c, info["id"], info, a.reps, rows)
            else:
                imaging_interactions(c, info["id"], info, a.reps, rows, tracks=tracks)
            res["datasets"].append({"file": path.name, "kind": kind, "n_spots": info["n_spots"],
                                    "n_cells": info["n_cells"], "interactions": rows})
            c.s.delete(f"{c.base}/api/datasets/{info['id']}")
    finally:
        proc.terminate()
        proc.wait(10)
    res["load_avg_end"] = list(os.getloadavg())
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(res, indent=1))
    print("->", a.out)


if __name__ == "__main__":
    main()
