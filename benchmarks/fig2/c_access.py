"""Figure 2c — access by level: ``get_trace`` / ``get_cell`` / ``get_chrom`` latency vs n_spots.

Data: the same whole-cell Takei 2025 subsets as panel b (``_common.stage_subset``),
written once to ``.h5cd`` by this checkout.  For each size a fresh interpreter
opens the file through a *backend* (``BACKENDS``), records the open/read time
and RSS, then times ``n_queries`` random ids per level (fixed seed; chromosome
names are drawn with replacement since there are only ~20).  Reported: median
and IQR per level, plus the read time separately.

Backends:

* ``h5cd-1x-memory`` — ``ChromData.read`` then in-memory ``cd.get_*`` (a
  boolean-mask scan over all spots).
* 2.x hook: add a class with the same three methods — e.g. an indexed
  in-memory variant (offsets from ``index/``) and a backed variant that
  reads one slice from disk — and register it in ``BACKENDS``.  Its series is
  merged into the JSON next to the 1.x one.

    python benchmarks/fig2/c_access.py [--sizes 1e4,1e5,1e6,1e7] [--queries 20] [--backends h5cd-1x-memory]

Writes ``paper/fig2/results/c_access.json``.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _common as C  # noqa: E402

SCRIPT = Path(__file__).resolve()


class H5cd1xMemory:
    """Load the whole file (format 1.x), query in memory by mask scan."""

    label = "h5cd 1.x (in memory, scan)"

    def open(self, path):
        from uchrom import ChromData
        self.cd = ChromData.read(path)

    def ids(self):
        s = self.cd.spots
        return {"trace": list(s["trace_id"].cat.categories), "cell": list(s["cell_id"].cat.categories),
                "chrom": list(s["chrom"].cat.categories)}

    def get(self, level, key):
        return {"trace": self.cd.get_trace, "cell": self.cd.get_cell, "chrom": self.cd.get_chrom}[level](key)


BACKENDS = {"h5cd-1x-memory": H5cd1xMemory}


def child(backend_key, path, n_queries):
    be = BACKENDS[backend_key]()
    base = C.current_rss_mb()
    t0 = time.perf_counter()
    be.open(Path(path))
    open_s = time.perf_counter() - t0
    rss_open = C.current_rss_mb()
    ids = be.ids()
    rng = np.random.default_rng(0)
    out = {"open_s": open_s, "rss_after_open_mb": rss_open, "baseline_rss_mb": base}
    for level in ("trace", "cell", "chrom"):
        pool = ids[level]
        picks = rng.choice(len(pool), int(n_queries), replace=len(pool) < int(n_queries) or level == "chrom")
        be.get(level, pool[picks[0]])  # warm-up (first-call imports / caches), not timed
        times, sizes = [], []
        for i in picks:
            t0 = time.perf_counter()
            sub = be.get(level, pool[i])
            times.append(time.perf_counter() - t0)
            sizes.append(int(sub.n_spots))
        out[level] = {"latency_s": C.iqr(times), "times_s": times, "result_spots_median": float(np.median(sizes)),
                      "n_ids": len(pool)}
    out["peak_rss_mb"] = C.peak_rss_mb()
    C.emit(out)


def child_write(stage, out):
    cd = C.load_stage(Path(stage))
    cd.write(out)
    C.emit({"bytes": Path(out).stat().st_size})


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sizes", default="1e4,1e5,1e6,1e7")
    ap.add_argument("--queries", type=int, default=20)
    ap.add_argument("--backends", default="h5cd-1x-memory")
    ap.add_argument("--child", nargs="+", help=argparse.SUPPRESS)
    args = ap.parse_args()
    if args.child:
        if args.child[0] == "write":
            return child_write(*args.child[1:])
        return child(*args.child)

    from uchrom.core.cdata import FORMAT_VERSION

    sizes = [int(float(s)) for s in args.sizes.split(",")]
    work = C.WORK / "c_access"
    work.mkdir(parents=True, exist_ok=True)
    series = {}
    for key in args.backends.split(","):
        be = BACKENDS[key]
        points = []
        for n in sizes:
            stage = C.stage_subset(n)
            info = C.stage_info(stage)
            h5 = work / f"n{n}_v{FORMAT_VERSION}.h5cd"
            if not h5.exists():
                C.run_child(SCRIPT, ["--child", "write", str(stage), str(h5)])
            r = C.run_child(SCRIPT, ["--child", key, str(h5), str(args.queries)])
            points.append({"n_target": n, "n_spots": info["n_spots"], "n_cells": info["n_cells"],
                           "replicated": info["replicated"], "file_mb": h5.stat().st_size / 2**20, **r})
            print(f"{be.label:28s} n={info['n_spots']:>11,}  open {r['open_s']:7.2f} s  "
                  + "  ".join(f"{lv} {r[lv]['latency_s']['median'] * 1e3:8.2f} ms" for lv in ("trace", "cell", "chrom")),
                  flush=True)
        series[be.label] = {"backend": key, "format_version": FORMAT_VERSION, "points": points}
        C.write_json("c_access", {"panel": "c", "machine": C.machine_info(), "queries_per_level": args.queries,
                                  "dataset": "Takei 2025 cerebellum rep 1 whole-cell subsets (see b_storage.json)",
                                  "series": series}, merge_key="series")
    print(C.RESULTS / "c_access.json")


if __name__ == "__main__":
    main()
