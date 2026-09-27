"""Figure 2d — population analysis beyond RAM: load everything vs stream the traces.

Analysis: the exact per-chromosome **median 3-D distance map** of one
chromosome (``--chrom``, default chr11) — ``uchrom.fea.distance_map`` —
on the Takei 2025 whole-cell subsets of panels b / c (1e4–1e7 spots) and
the 1e8 replicated store (``replicate_store.py``).

* **load all** — ``ChromData.read(store)`` (everything in memory, the usual
  approach), then ``distance_map(cd, chrom, streaming=False)``: every pair
  observation of the chromosome at once, one grouped median.
* **streaming** — ``ChromData.read(store, backed=True)``, then
  ``distance_map(cd, chrom, memory_budget=BUDGET)``: the traces are read in
  batches (``iter_traces(chrom=..., columns="coords")``) and the exact median
  is taken one row band at a time (bands sized from the budget).

Each (mode, size) runs ``--repeats`` times in a fresh interpreter: wall time
and peak RSS (``ru_maxrss``; the RSS after imports is recorded as the
baseline).  The medians of the two modes are compared bitwise (a result
identity scatter is kept for the figure); at 1e8, where loading everything
does not fit, the in-memory reference is computed from the chromosome alone
(``get_chrom(chrom, columns="coords")``).

    python benchmarks/fig2/d_streaming.py [--sizes 1e4,1e5,1e6,1e7] [--prebuilt 1e8=PATH] \\
        [--chrom chr11] [--budget 2GB] [--repeats 3]

Writes ``paper/fig2/results/d_streaming.json``.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _common as C  # noqa: E402

SCRIPT = Path(__file__).resolve()
ACCESS = SCRIPT.parent / "c_access.py"


def child(mode, path, chrom, budget, out_npy):
    import pyarrow.parquet  # noqa: F401  (import cost out of the timing)
    import zarr  # noqa: F401

    from uchrom import ChromData
    from uchrom.fea import distance_map
    import uchrom.core.backed  # noqa: F401

    base = C.current_rss_mb()
    t0 = time.perf_counter()
    if mode == "load_all":
        cd = ChromData.read(path)
        t_load = time.perf_counter() - t0
        res = distance_map(cd, chrom, "median", streaming=False)
    elif mode == "chrom_memory":
        bk = ChromData.read(path, backed=True)
        cd = bk.get_chrom(chrom, columns="coords")
        t_load = time.perf_counter() - t0
        res = distance_map(cd, chrom, "median", streaming=False)
    else:
        cd = ChromData.read(path, backed=True)
        t_load = time.perf_counter() - t0
        res = distance_map(cd, chrom, "median", memory_budget=budget)
    dt = time.perf_counter() - t0
    if out_npy != "-":
        np.save(out_npy, res.matrix)
    iu = np.triu_indices(res.matrix.shape[0], 1)
    C.emit({"mode": mode, "seconds": dt, "load_s": t_load, "peak_rss_mb": C.peak_rss_mb(),
            "baseline_rss_mb": base, "n_traces_chrom": int(res.n_traces), "n_bins": int(res.matrix.shape[0]),
            "n_obs": int(res.count[iu].sum()), "n_bands": int(res.n_bands), "n_passes": int(res.n_passes),
            "n_spots": int(cd.n_spots)})


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sizes", default="1e4,1e5,1e6,1e7")
    ap.add_argument("--prebuilt", action="append", default=[], metavar="N=PATH")
    ap.add_argument("--chrom", default="chr11")
    ap.add_argument("--budget", default="2GB")
    ap.add_argument("--repeats", type=int, default=3)
    ap.add_argument("--load-all-max", type=float, default=1e7,
                    help="largest size run with 'load all' (larger: infeasible in RAM)")
    ap.add_argument("--child", nargs="+", help=argparse.SUPPRESS)
    args = ap.parse_args()
    if args.child:
        return child(*args.child)

    from uchrom.settings import parse_bytes

    sizes = [int(float(s)) for s in args.sizes.split(",")]
    prebuilt = {int(float(k)): Path(v) for k, v in (p.split("=", 1) for p in args.prebuilt)}
    work = C.WORK / "d_streaming"
    work.mkdir(parents=True, exist_ok=True)
    points = []
    scatter = None
    for n in sorted(set(sizes) | set(prebuilt)):
        if n in prebuilt:
            path = prebuilt[n]
            meta = json.loads((path / "zarr.json").read_text())["attributes"]["uchrom"]
            info = {"n_spots": meta["n_spots"], "n_cells": meta["n_cells"], "n_traces": meta["n_traces"],
                    "replicated": True, "prebuilt": str(path)}
        else:
            stage = C.stage_subset(n)
            info = dict(C.stage_info(stage))
            path = C.WORK / "c_access" / f"n{n}_zarr{C._zarr_version().replace('.', '')}.chromdata.zarr"
            if not path.exists():
                C.run_child(ACCESS, ["--child", "write", "zarr-backed", str(stage), str(path)])
            meta = json.loads((path / "zarr.json").read_text())["attributes"]["uchrom"]
            info["n_traces"] = meta["n_traces"]
        rec = {"n_target": n, **info}
        modes = ["streaming"] + (["load_all"] if n <= args.load_all_max else ["chrom_memory"])
        for mode in modes:
            trials = []
            for r in range(args.repeats):
                npy = work / f"n{n}_{mode}.npy" if r == 0 else "-"
                trials.append(C.run_child(SCRIPT, ["--child", mode, str(path), args.chrom, args.budget, str(npy)]))
            rec[mode] = {"seconds": C.summarize([t["seconds"] for t in trials]),
                         "load_s": C.summarize([t["load_s"] for t in trials]),
                         "peak_rss_mb": C.summarize([t["peak_rss_mb"] for t in trials]),
                         "baseline_rss_mb": C.summarize([t["baseline_rss_mb"] for t in trials]),
                         **{k: trials[0][k] for k in ("n_traces_chrom", "n_bins", "n_obs", "n_bands", "n_passes")},
                         "trials": trials}
            print(f"n={info['n_spots']:>11,} {mode:12s} {rec[mode]['seconds']['median']:8.1f} s  "
                  f"peak {rec[mode]['peak_rss_mb']['median'] / 1024:6.2f} GB  bands {trials[0]['n_bands']}",
                  flush=True)
        ref_mode = modes[1]
        a = np.load(work / f"n{n}_streaming.npy")
        b = np.load(work / f"n{n}_{ref_mode}.npy")
        rec["identical"] = bool(np.array_equal(a, b, equal_nan=True))
        rec["identity_reference"] = ref_mode
        d = np.abs(a - b)
        rec["max_abs_diff"] = float(np.nanmax(d)) if np.isfinite(d).any() else 0.0
        rec["n_pairs_compared"] = int(np.isfinite(a[np.triu_indices(len(a), 1)]).sum())
        if n == max(s for s in sizes if s <= args.load_all_max):
            iu = np.triu_indices(len(a), 1)
            ok = np.flatnonzero(np.isfinite(a[iu]) & np.isfinite(b[iu]))
            pick = np.random.default_rng(0).choice(ok, min(4000, len(ok)), replace=False)
            scatter = {"n_spots": info["n_spots"], "load_all": b[iu][pick].round(6).tolist(),
                       "streaming": a[iu][pick].round(6).tolist(), "n_pairs_total": int(len(ok))}
        points.append(rec)
        C.write_json("d_streaming", _payload(args, points, scatter, parse_bytes(args.budget)))
    print(C.RESULTS / "d_streaming.json")


def _payload(args, points, scatter, budget_bytes):
    return {
        "panel": "d", "machine": C.machine_info(),
        "dataset": "Takei 2025 cerebellum rep 1 whole-cell subsets (b_storage.json); 1e8 = rep 1 replicated "
                   "(replicate_store.py, flag 'replicated')",
        "analysis": f"exact median 3-D distance map of {args.chrom} (uchrom.fea.distance_map, stat='median')",
        "chrom": args.chrom, "budget": args.budget, "budget_mb": budget_bytes / 2**20,
        "repeats": args.repeats,
        "modes": {"load_all": "ChromData.read(store) then distance_map(cd, chrom, streaming=False)",
                  "streaming": "ChromData.read(store, backed=True) then distance_map(cd, chrom, "
                               "memory_budget=budget): iter_traces(chrom, columns='coords') batches, exact "
                               "median per row band",
                  "chrom_memory": "identity reference where load-all does not fit: get_chrom(chrom, "
                                  "columns='coords') in memory, then distance_map(streaming=False)"},
        "load_all_infeasible": {"n_target": 1e8, "reason": "the whole 1e8-spot store in memory needs about 10x "
                                "the peak of the 1e7 full read (b_storage.json), more than the 64 GB of RAM"},
        "points": points, "scatter": scatter,
    }


if __name__ == "__main__":
    main()
