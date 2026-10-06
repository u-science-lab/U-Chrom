"""Row-group size of the format 2.1 store: file size, full read, get_cell / get_trace / get_chrom.

The spot-aligned tables of a ``.chromdata.zarr`` 2.1 store are partitioned by
chromosome, and a cell has spots on every chromosome: ``get_cell`` reads one
row group per chromosome (and per table), so its latency grows with the
row-group size, while ``get_chrom`` reads whole partitions and full reads
prefer large groups.  This script measures the trade-off on the same
whole-cell Takei 2025 subset as panels b / c (1e7 spots by default):

* one store per ``--rows`` value (``cd.write(row_group_rows=R)``; write time
  and size per table, measured once);
* ``--repeats`` fresh processes each for the full read (``ChromData.read``:
  time and peak RSS) and for the backed queries (``c_access.py``'s child:
  20 random ids per level, with and without ``columns="coords"``).

    python benchmarks/fig2/rowgroup_sweep.py [--n 1e7] [--rows 8192,16384,32768,65536] [--repeats 3]

Writes ``u-chrom-paper/manuscripts/full/figures/fig2/results/rowgroup_sweep.json``.
"""

from __future__ import annotations

import argparse
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _common as C  # noqa: E402

SCRIPT = Path(__file__).resolve()
ACCESS = SCRIPT.parent / "c_access.py"


def child_write(stage, out, rows):
    cd = C.load_stage(Path(stage))
    t0 = time.perf_counter()
    cd.write(out, row_group_rows=int(rows))
    dt = time.perf_counter() - t0
    out = Path(out)
    tables = {}
    for sub in ("spots", "spot_tracks", "layers"):
        p = out / "tables" / sub
        if p.exists():
            tables[sub] = C.size_bytes(p)
    import zarr
    meta = zarr.open_group(str(out), mode="r").attrs["uchrom"]
    C.emit({"write_s": dt, "bytes": C.size_bytes(out), "table_bytes": tables,
            "n_row_groups": meta["n_row_groups"], "n_partitions": meta.get("n_partitions"),
            "write_peak_rss_mb": C.peak_rss_mb()})


def child_read(path):
    import pyarrow.parquet  # noqa: F401
    import zarr  # noqa: F401
    from uchrom import ChromData
    import uchrom.core.backed  # noqa: F401
    base = C.current_rss_mb()
    t0 = time.perf_counter()
    cd = ChromData.read(path)
    dt = time.perf_counter() - t0
    C.emit({"read_s": dt, "read_peak_rss_mb": C.peak_rss_mb(), "baseline_rss_mb": base,
            "n_spots": int(cd.n_spots)})


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--n", default="1e7")
    ap.add_argument("--rows", default="8192,16384,32768,65536")
    ap.add_argument("--repeats", type=int, default=3)
    ap.add_argument("--queries", type=int, default=20)
    ap.add_argument("--child", nargs="+", help=argparse.SUPPRESS)
    args = ap.parse_args()
    if args.child:
        kind, *rest = args.child
        return {"write": child_write, "read": child_read}[kind](*rest)

    n = int(float(args.n))
    stage = C.stage_subset(n)
    info = C.stage_info(stage)
    work = C.WORK / "rowgroup_sweep"
    work.mkdir(parents=True, exist_ok=True)
    points = []
    for rows in [int(r) for r in args.rows.split(",")]:
        path = work / f"n{n}_rg{rows}.chromdata.zarr"
        C.remove(path)
        w = C.run_child(SCRIPT, ["--child", "write", str(stage), str(path), str(rows)])
        reads = [C.run_child(SCRIPT, ["--child", "read", str(path)]) for _ in range(args.repeats)]
        runs = [C.run_child(ACCESS, ["--child", "zarr-backed", str(path), str(args.queries)])
                for _ in range(args.repeats)]
        levels = {}
        for lv in ("trace", "cell", "chrom", "trace_coords", "cell_coords", "chrom_coords"):
            times = [t for r in runs for t in r[lv]["times_s"]]
            levels[lv] = {"latency_s": C.iqr(times),
                          "per_repeat_median_s": [r[lv]["latency_s"]["median"] for r in runs],
                          "result_spots_median": runs[0][lv]["result_spots_median"]}
        pt = {"row_group_rows": rows, "size_mb": w["bytes"] / 2**20,
              "table_mb": {k: v / 2**20 for k, v in w["table_bytes"].items()},
              "n_row_groups": w["n_row_groups"], "n_partitions": w["n_partitions"],
              "write_s": w["write_s"], "write_peak_rss_mb": w["write_peak_rss_mb"],
              "read_s": C.summarize([r["read_s"] for r in reads]),
              "read_peak_rss_mb": C.summarize([r["read_peak_rss_mb"] for r in reads]),
              "open_s": statistics.median(r["open_s"] for r in runs), **levels}
        points.append(pt)
        print(f"rg {rows:>6}: {pt['size_mb']:8.1f} MB  read {pt['read_s']['median']:.2f} s  "
              + "  ".join(f"{lv} {pt[lv]['latency_s']['median'] * 1e3:7.1f} ms" for lv in levels), flush=True)
        C.remove(path)
    C.write_json("rowgroup_sweep", {
        "what": "format 2.1 row-group size trade-off (Takei 2025 rep 1 whole-cell subset)",
        "machine": C.machine_info(), "n_spots": info["n_spots"], "n_cells": info["n_cells"],
        "repeats": args.repeats, "queries_per_level": args.queries,
        "protocol": "fresh process per trial; warm OS cache; query times pooled over repeats",
        "points": points})
    print(C.RESULTS / "rowgroup_sweep.json")


if __name__ == "__main__":
    main()
