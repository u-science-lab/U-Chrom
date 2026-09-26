"""Figure 2b — storage: file size, write time, full read time and peak RSS vs n_spots.

Formats (``_common.FORMATS``):

* **FOF-CT / CSV** — the official ``uchrom.io.write_fofct`` (``cd.to_fofct``)
  and ``ChromData.from_fofct`` (the first series used the minimal
  ``_common.write_fofct``; the JSON records the writer);
* **Parquet** — the flat spot table (spots + x/y/z + tracks), pyarrow, default
  snappy compression; read back with ``pd.read_parquet``;
* **AnnData (spots as obs)** — spot columns + tracks in ``obs``, coords in
  ``obsm['spatial']``; ``write_h5ad`` / ``read_h5ad`` defaults;
* **h5cd N.x** — ``cd.write`` / ``ChromData.read`` of this checkout (1.x on
  main; run the same script on a 2.x checkout to add the 2.x series).

Data: whole-cell subsets of the real Takei 2025 cerebellum rep-1 data (all
FOVs, 62 spot tracks — ``_common.stage_subset``).  Sizes above the real size
replicate real cells under new ids and are flagged ``replicated``.

Protocol: for every (size, format, repeat) a fresh interpreter loads the staged
subset (untimed) and writes the file (timed); a second fresh interpreter reads
it back in full (timed; peak RSS from ``getrusage``, plus the RSS after imports
as a baseline).  Files are deleted after each repeat.  The OS page cache is not
flushed (no root), so reads are warm-cache reads of a just-written file.

    python benchmarks/fig2/b_storage.py [--sizes 1e4,1e5,1e6,1e7,1e8] [--repeats 3] [--formats fofct,parquet,anndata,h5cd]

Writes ``paper/fig2/results/b_storage.json`` (series merged by format label).
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _common as C  # noqa: E402

SCRIPT = Path(__file__).resolve()


def child_stage(sizes, schema):
    out = {}
    for n in sizes:
        p = C.stage_subset(int(n), schema=schema)
        out[str(int(n))] = {"path": str(p), **C.stage_info(p)}
    C.emit(out)


def child_write(fmt_key, stage, out):
    cd = C.load_stage(Path(stage))
    fmt = C.FORMATS[fmt_key]
    t0 = time.perf_counter()
    fmt.write(cd, Path(out))
    dt = time.perf_counter() - t0
    C.emit({"write_s": dt, "bytes": C.size_bytes(Path(out)), "write_peak_rss_mb": C.peak_rss_mb(),
            "label": fmt.label})


def child_read(fmt_key, path):
    fmt = C.FORMATS[fmt_key]
    import anndata, h5py, pyarrow, pyarrow.parquet  # noqa: F401  (import cost out of the timing)
    from uchrom import ChromData  # noqa: F401
    try:
        import zarr  # noqa: F401
        import uchrom.core.backed  # noqa: F401
    except ImportError:  # 1.x checkout
        pass
    base = C.current_rss_mb()
    t0 = time.perf_counter()
    obj = fmt.read(Path(path))
    dt = time.perf_counter() - t0
    n = obj.n_spots if hasattr(obj, "n_spots") else (obj.n_obs if hasattr(obj, "n_obs") else len(obj))
    C.emit({"read_s": dt, "read_peak_rss_mb": C.peak_rss_mb(), "baseline_rss_mb": base, "n_rows": int(n)})


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=__import__("argparse").RawDescriptionHelpFormatter)
    ap.add_argument("--sizes", default="1e4,1e5,1e6,1e7,1e8")
    ap.add_argument("--repeats", type=int, default=3)
    ap.add_argument("--formats", default="fofct,parquet,anndata,h5cd")
    ap.add_argument("--schema", default="full", choices=["full", "core"])
    ap.add_argument("--mem-fraction", type=float, default=0.6,
                    help="skip sizes whose estimated in-memory footprint exceeds this fraction of RAM")
    ap.add_argument("--child", nargs="+", help=argparse.SUPPRESS)
    args = ap.parse_args()
    if args.child:
        kind, *rest = args.child
        if kind == "stage":
            return child_stage([float(x) for x in rest[1:]], rest[0])
        return {"write": child_write, "read": child_read}[kind](*rest)

    sizes = [int(float(s)) for s in args.sizes.split(",")]
    machine = C.machine_info()
    ram_mb = machine.get("ram_gb", 64) * 1024

    # per-spot in-memory footprint, from the largest staged size that fits
    feasible, infeasible = [], []
    probe = C.run_child(SCRIPT, ["--child", "stage", args.schema, "1e5"])
    bytes_per_spot = None
    import pickle
    p = Path(probe[str(int(1e5))]["path"])
    bytes_per_spot = p.stat().st_size / probe[str(int(1e5))]["n_spots"]
    for n in sizes:
        est_mb = n * bytes_per_spot / 2**20
        # the widest reader (FOF-CT via from_fofct) holds ~4-5x the table in memory
        if est_mb * 4 > args.mem_fraction * ram_mb:
            infeasible.append({"n_target": n, "est_in_memory_mb": round(est_mb),
                               "reason": f"~{est_mb / 1024:.0f} GB in memory for the table alone "
                                         f"(x4 for the CSV reader) exceeds {args.mem_fraction:.0%} of "
                                         f"{machine.get('ram_gb')} GB RAM"})
        else:
            feasible.append(n)
    print(f"bytes/spot in memory ≈ {bytes_per_spot:.0f}; feasible sizes {feasible}; infeasible {[d['n_target'] for d in infeasible]}")

    staged = C.run_child(SCRIPT, ["--child", "stage", args.schema, *[str(n) for n in feasible]])
    work = C.WORK / "b_storage"
    work.mkdir(parents=True, exist_ok=True)
    series = {}
    for key in args.formats.split(","):
        fmt = C.FORMATS[key]
        points = []
        for n in feasible:
            st = staged[str(n)]
            trials = []
            for r in range(args.repeats):
                out = work / f"n{n}_{key}_{r}{fmt.ext}"
                w = C.run_child(SCRIPT, ["--child", "write", key, st["path"], str(out)])
                rd = C.run_child(SCRIPT, ["--child", "read", key, str(out)])
                C.remove(out)
                trials.append({**w, **rd})
                print(f"{fmt.label:24s} n={st['n_spots']:>11,} rep{r}: {w['bytes'] / 2**20:9.1f} MB  "
                      f"write {w['write_s']:8.2f} s  read {rd['read_s']:8.2f} s  peak {rd['read_peak_rss_mb']:9.0f} MB",
                      flush=True)
            points.append({
                "n_target": n, "n_spots": st["n_spots"], "n_cells": st["n_cells"],
                "replicated": st["replicated"], "n_copies": st["n_copies"],
                "size_mb": C.summarize([t["bytes"] / 2**20 for t in trials]),
                "write_s": C.summarize([t["write_s"] for t in trials]),
                "read_s": C.summarize([t["read_s"] for t in trials]),
                "read_peak_rss_mb": C.summarize([t["read_peak_rss_mb"] for t in trials]),
                "read_baseline_rss_mb": C.summarize([t["baseline_rss_mb"] for t in trials]),
                "write_peak_rss_mb": C.summarize([t["write_peak_rss_mb"] for t in trials]),
                "trials": trials,
            })
        series[fmt.label] = {"points": points, "infeasible": infeasible, "repeats": args.repeats,
                             **({"writer": fmt.writer} if getattr(fmt, "writer", None) else {}),
                             **({"container_version": C._zarr_version()} if key.startswith("zarr") else {})}
        C.write_json("b_storage", {"panel": "b", "machine": machine, "schema": args.schema,
                                   "dataset": _dataset_note(), "protocol": _protocol(args),
                                   "series": series}, merge_key="series")
    print(C.RESULTS / "b_storage.json")


def _dataset_note():
    import json
    s = C.TAKEI_DIR / "build_summary.json"
    comb = json.loads(s.read_text()).get("combined", {}) if s.exists() else {}
    return {"name": "Takei 2025 cerebellum rep 1, all FOVs (Zenodo 7693825)",
            "n_spots": comb.get("n_spots"), "n_cells": comb.get("n_cells"), "n_traces": comb.get("n_traces"),
            "n_tracks": comb.get("n_tracks"),
            "subsetting": "whole cells in a fixed random order (seed 0); above the real size, "
                          "real cells copied under new cell/trace ids (flag 'replicated')"}


def _protocol(args):
    return {"repeats": args.repeats, "stat": "median with min/max over repeats",
            "fresh_process_per_trial": True, "page_cache": "warm (not flushed; read follows write)",
            "peak_rss": "getrusage ru_maxrss of the read process (absolute; baseline = RSS after imports)",
            "read_target": {"FOF-CT / CSV": "ChromData (ChromData.from_fofct)", "Parquet": "pandas DataFrame",
                            "AnnData (spots as obs)": "AnnData (read_h5ad, in memory)",
                            "h5cd": "ChromData (ChromData.read)",
                            "chromdata.zarr 2.0": "ChromData (ChromData.read, in memory)",
                            "chromdata.zarr 2.1": "ChromData (ChromData.read, in memory)"},
            "compression": {"FOF-CT / CSV": "none", "Parquet": "snappy (pyarrow default)",
                            "AnnData (spots as obs)": "none (write_h5ad default)",
                            "h5cd 1.x": "none (cd.write)",
                            "h5cd 2.0": "gzip-4 on integer / string data, floats uncompressed (cd.write default)",
                            "chromdata.zarr 2.0": "Parquet zstd-3 + Zarr zstd-3; spots sorted by (cell, trace, "
                                                  "bin), 65,536-row row groups on cell boundaries "
                                                  "(cd.write default)",
                            "chromdata.zarr 2.1": "Parquet zstd-3 + Zarr zstd-3; spot tables partitioned by "
                                                  "chromosome (tables/spots/chrom=<name>/), sorted by (cell, "
                                                  "trace, bin) within a partition, 16,384-row row groups on "
                                                  "cell boundaries (cd.write default)"},
            "fofct_writer": "uchrom.io.write_fofct (official writer, PR #67)"}


if __name__ == "__main__":
    main()
