"""The native kernels of the Hi-C loop callers (``uchrom_maps``, packages/uchrom-maps) against the numpy reference
on real Hi-C: identical results, and the time / memory they save.

Sections (each prints a table; everything goes to ``OUT/native_speed.json``):

``identity``  Rao 2014 IMR90 and GM12878 chr21 at 5 / 10 / 25 kb and IMR90 chr1 at 5 kb, both backends
              (``uchrom.strc.loop.hiccups.BACKEND`` / ``mustache.BACKEND`` = ``"numpy"`` / ``"native"``):
              HiCCUPS — the scoring of the chromosome (candidates, locally adjusted expecteds, λ-chunk
              histograms: bit for bit), the enriched pixels (``hiccups_pixels``) and the calls (defaults,
              loops up to 10 Mb; chr1 also 2 Mb); Mustache — the scan (best responses, layers, per-layer
              statistics: bit for bit) and the calls (defaults).
``speed``     IMR90 chr1 at 5 kb (49,851 bins, 26.5 M pixels): the whole call and the ported function
              (``hiccups._score_chrom``, ``mustache._scan``) for HiCCUPS at max_dist 2 and 10 Mb and Mustache
              with its defaults; numpy, and native with 1, 4 and all threads (``RAYON_NUM_THREADS``); peak
              RSS.  Every run is a fresh process (clean peak memory, rayon's pool size); the best of
              ``--repeats`` runs is reported (other jobs may share the machine).

Run from the repository root (the maps are those of ``hiccups.py``: ICE-balanced by ``uchrom.fea.rebin_map``,
built in ``OUT/hiccups_maps`` or reused from there)::

    .venv/bin/python benchmarks/hic_structures/native_speed.py --out SCRATCH/native [--only identity,speed]

Inputs (``uchrom.datasets``): ``rao2014_imr90_chr21`` (load), ``rao2014_gm12878_chr21``, ``rao2014_imr90_chr1``
(fetch).  Needs ``uchrom_maps`` installed (``pip install ./packages/uchrom-maps``).
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
KERNELS = ("donut", "vertical", "horizontal", "lowleft")


def _maps(out: Path) -> dict:
    sys.path.insert(0, str(HERE))
    from hiccups import prepare                            # the HiCCUPS validation's maps (rebin_map + ICE)

    return prepare(out, chr1=True)


# ------------------------------------------------------------------------------------------------ identity

def _same(a, b) -> bool:
    a, b = np.asarray(a), np.asarray(b)
    return a.shape == b.shape and bool(np.array_equal(a, b))


def _frames_equal(a: pd.DataFrame, b: pd.DataFrame) -> bool:
    try:
        pd.testing.assert_frame_equal(a.reset_index(drop=True), b.reset_index(drop=True), check_exact=True)
    except AssertionError:
        return False
    return True


def hiccups_identity(path: str, max_dist: int) -> dict:
    import cooler

    from uchrom.fea.band import read_band
    from uchrom.strc.loop import hiccups as H

    clr = cooler.Cooler(path)
    chrom = clr.chromnames[0]
    binsize = int(clr.binsize)
    params = H.HiccupsParams(max_dist=max_dist)
    p, w = H.kernel_sizes(binsize, params)
    D = int(params.max_dist / binsize)
    band = read_band(clr, chrom=chrom, max_dist=(D + 2 * w + 1) * binsize, balance=True)
    edges = H._lambda_edges(params.lambda_base)
    cmin = H._min_counts(edges, params.fdr, params.pvalue)
    score, secs = {}, {}
    for b in ("numpy", "native"):
        hist = H._Hist()
        t = time.perf_counter()
        res = H._score_chrom(band, p, w, D, params, hist, edges, cmin, backend=b)
        secs[b] = time.perf_counter() - t
        score[b] = (res, hist)
    (ra, ha), (rb, hb) = score["numpy"], score["native"]
    row = {"n_tested": int(ra["n_tested"]), "n_candidates": int(len(ra["i"])),
           "score_identical": bool(ra["n_tested"] == rb["n_tested"]
                                   and all(_same(np.asarray(ra[k], dtype=np.int64), rb[k]) for k in ("i", "j", "count"))
                                   and all(_same(ra[k], rb[k]) for k in KERNELS)),
           "hist_identical": all(_same(ha.h[k], hb.h[k]) for k in KERNELS),
           "score_numpy_s": round(secs["numpy"], 2), "score_native_s": round(secs["native"], 2)}
    if not row["score_identical"]:
        lam_rel = max(float(np.max(np.abs(ra[k] - rb[k]) / np.abs(ra[k]))) if len(ra[k]) == len(rb[k]) and len(ra[k])
                      else float("nan") for k in KERNELS)
        row["lam_max_rel_diff"] = lam_rel
    del band, score
    px, calls = {}, {}
    old = H.BACKEND
    try:
        for b in ("numpy", "native"):
            H.BACKEND = b
            px[b], info = H.hiccups_pixels(clr, [chrom], params)
            calls[b], _ = H._call_one(clr, [chrom], params)
    finally:
        H.BACKEND = old
    row.update({"n_enriched": int(len(px["numpy"])), "pixels_identical": _frames_equal(px["numpy"], px["native"]),
                "n_calls": int(len(calls["numpy"])), "calls_identical": _frames_equal(calls["numpy"], calls["native"])})
    if not row["pixels_identical"]:
        a = set(zip(px["numpy"]["i"], px["numpy"]["j"]))
        b = set(zip(px["native"]["i"], px["native"]["j"]))
        row["pixels_only_numpy"], row["pixels_only_native"] = len(a - b), len(b - a)
    return row


def mustache_identity(path: str) -> dict:
    import cooler

    from uchrom.fea.band import read_band
    from uchrom.strc.loop import mustache as M

    clr = cooler.Cooler(path)
    chrom = clr.chromnames[0]
    res = int(clr.binsize)
    p = M.MustacheParams()
    D = M.default_max_dist(res) // res
    band = read_band(clr, chrom=chrom, max_dist=D * res)
    v = band.values()
    keep = np.isfinite(v) & (v > 0) & (band.diag <= D)
    x, y, v, n = band.i[keep], band.j[keep], v[keep], band.n
    del band, keep
    z = M._normalize(x, y, v, n, D, res, p)
    el = np.flatnonzero((z != 0) & ((y - x) >= p.min_diag))
    ex, ey = x[el], y[el]
    out, secs = {}, {}
    for b in ("numpy", "native"):
        t = time.perf_counter()
        out[b] = M._scan(x, y, z, ex, ey, n, D, p, 256, backend=b)
        secs[b] = time.perf_counter() - t
    a, b2 = out["numpy"], out["native"]
    row = {"n_eligible": int(len(ex)), "n_extrema": int((a[1] >= 0).sum()),
           "scan_identical": _same(a[0], b2[0]) and _same(a[1], b2[1]) and all(_same(u, w) for u, w in zip(a[2], b2[2])),
           "scan_numpy_s": round(secs["numpy"], 2), "scan_native_s": round(secs["native"], 2)}
    if not row["scan_identical"]:
        row["best_differs"] = int((a[0] != b2[0]).sum())
        row["layer_differs"] = int((a[1] != b2[1]).sum())
    del out, x, y, z, ex, ey
    calls = {}
    old = M.BACKEND
    try:
        for b in ("numpy", "native"):
            M.BACKEND = b
            calls[b] = M.call_loops_mustache(path, chrom=chrom, params=p)
    finally:
        M.BACKEND = old
    row.update({"n_calls": int(len(calls["numpy"])), "calls_identical": _frames_equal(calls["numpy"], calls["native"])})
    if not row["calls_identical"]:
        a = set(zip(calls["numpy"]["summit_i"], calls["numpy"]["summit_j"]))
        b = set(zip(calls["native"]["summit_i"], calls["native"]["summit_j"]))
        row["calls_only_numpy"], row["calls_only_native"] = len(a - b), len(b - a)
    return row


def section_identity(maps: dict, out: Path, args) -> dict:
    rows_h, rows_m = [], []
    order = [(c, r) for c in ("imr90", "gm12878") for r in (5000, 10000, 25000)] + [("imr90_chr1", 5000)]
    for key in order:
        path = maps[key]
        name = f"{key[0]}{'' if 'chr1' in key[0] else '_chr21'} {key[1] // 1000} kb"
        for md in ((2_000_000, 10_000_000) if key[0] == "imr90_chr1" else (10_000_000,)):
            t = time.perf_counter()
            rows_h.append({"map": name, "max_dist_mb": md // 1_000_000, **hiccups_identity(path, md)})
            print(f"  hiccups {name} {md // 1_000_000} Mb: {time.perf_counter() - t:.0f} s", flush=True)
        t = time.perf_counter()
        rows_m.append({"map": name, **mustache_identity(path)})
        print(f"  mustache {name}: {time.perf_counter() - t:.0f} s", flush=True)
    _table(rows_h, "HiCCUPS, native vs numpy (identical = bit for bit / exactly equal tables)")
    _table(rows_m, "Mustache, native vs numpy")
    return {"hiccups": rows_h, "mustache": rows_m}


# ------------------------------------------------------------------------------------------------ speed

_CHILD = r"""
import json, resource, sys, time
import numpy as np, pandas as pd
what, path, backend = sys.argv[1], sys.argv[2], sys.argv[3]
from uchrom.strc.loop import hiccups as H, mustache as M
H.BACKEND = M.BACKEND = backend
tm = {"ported_s": 0.0}
def timed(fn):
    def run(*a, **k):
        t = time.perf_counter()
        try:
            return fn(*a, **k)
        finally:
            tm["ported_s"] += time.perf_counter() - t
    return run
if backend == "native":
    import uchrom_maps
    uchrom_maps.scipy_arithmetic()                       # the once-per-process scipy probe, outside the timing
    tm["threads"] = uchrom_maps.default_threads()
t = time.perf_counter()
if what == "hiccups":
    from chromdata import ChromData
    H._score_chrom = timed(H._score_chrom)
    cd = ChromData(np.zeros((0, 3)), pd.DataFrame({"chrom": pd.Series(dtype=str), "start": pd.Series(dtype=np.int64),
                   "end": pd.Series(dtype=np.int64), "trace_id": pd.Series(dtype=str)}))
    calls = H.call_loops_hiccups(cd, contacts=path, params=H.HiccupsParams(max_dist=int(sys.argv[4])), key_added=None)
else:
    M._scan = timed(M._scan)
    calls = M.call_loops_mustache(path)
tm["total_s"] = time.perf_counter() - t
tm["n_calls"] = int(len(calls))
tm["max_rss_gb"] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / (1e9 if sys.platform == "darwin" else 1e6)
print(json.dumps(tm))
"""


def _child(what: str, path: str, backend: str, threads: int, extra=()) -> dict:
    env = dict(os.environ)
    env.pop("RAYON_NUM_THREADS", None)
    if threads:
        env["RAYON_NUM_THREADS"] = str(threads)
    r = subprocess.run([sys.executable, "-c", _CHILD, what, path, backend, *map(str, extra)], capture_output=True,
                       text=True, env=env)
    if r.returncode:
        raise RuntimeError(r.stderr[-3000:])
    return json.loads(r.stdout.strip().splitlines()[-1])


def section_speed(maps: dict, out: Path, args) -> list:
    path = maps[("imr90_chr1", 5000)]
    threads = [int(t) for t in args.threads.split(",")]
    cases = [("hiccups", "HiCCUPS 2 Mb", (2_000_000,)), ("hiccups", "HiCCUPS 10 Mb", (10_000_000,)),
             ("mustache", "Mustache (defaults)", ())]
    rows = []
    for what, label, extra in cases:
        for backend, th in [("numpy", 0)] + [("native", t) for t in threads]:
            runs = [_child(what, path, backend, th, extra) for _ in range(args.repeats)]
            best = min(runs, key=lambda r: r["total_s"])
            row = {"case": label, "backend": backend,
                   "threads": "-" if backend == "numpy" else best.get("threads", th),
                   "total_s": round(min(r["total_s"] for r in runs), 2),
                   "ported_s": round(min(r["ported_s"] for r in runs), 2),
                   "max_rss_gb": round(min(r["max_rss_gb"] for r in runs), 2),
                   "n_calls": best["n_calls"], "runs_total_s": [round(r["total_s"], 2) for r in runs],
                   "runs_ported_s": [round(r["ported_s"], 2) for r in runs]}
            rows.append(row)
            print(f"  {label} {backend} threads={row['threads']}: total {row['total_s']} s, ported {row['ported_s']} s",
                  flush=True)
    base = {r["case"]: r for r in rows if r["backend"] == "numpy"}
    for r in rows:
        r["speedup_total"] = round(base[r["case"]]["total_s"] / r["total_s"], 1)
        r["speedup_ported"] = round(base[r["case"]]["ported_s"] / max(r["ported_s"], 1e-9), 1)
    _table([{k: v for k, v in r.items() if not k.startswith("runs_")} for r in rows],
           f"IMR90 chr1 at 5 kb: whole call and ported function (s, best of {args.repeats}), peak RSS (GB)")
    return rows


# ------------------------------------------------------------------------------------------------ main

def _table(rows, title):
    print(f"\n{title}")
    with pd.option_context("display.width", 250, "display.max_columns", 50):
        print(pd.DataFrame(rows).to_string(index=False))


def _machine() -> dict:
    import scipy
    import uchrom_maps

    return {"platform": platform.platform(), "machine": platform.machine(), "cpu_count": os.cpu_count(),
            "python": platform.python_version(), "numpy": np.__version__, "scipy": scipy.__version__,
            "uchrom_maps": uchrom_maps.__version__, "rayon_threads": uchrom_maps.default_threads(),
            "scipy_arithmetic": uchrom_maps.scipy_arithmetic()}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", type=Path, default=Path(tempfile.gettempdir()) / "uchrom_native_speed")
    ap.add_argument("--only", default="identity,speed")
    ap.add_argument("--repeats", type=int, default=3)
    ap.add_argument("--threads", default="1,4,0", help="native thread counts (0: all cores)")
    a = ap.parse_args(argv)
    a.out.mkdir(parents=True, exist_ok=True)
    maps = _maps(a.out)
    dst = a.out / "native_speed.json"
    res = json.loads(dst.read_text()) if dst.exists() else {}
    res["machine"] = _machine()
    for name in a.only.split(","):
        t = time.time()
        res[name] = globals()[f"section_{name}"](maps, a.out, a)
        print(f"[{name}: {time.time() - t:.0f} s]", flush=True)
        dst.write_text(json.dumps(res, indent=1))
    print(f"\nwrote {dst}")


if __name__ == "__main__":
    main()
