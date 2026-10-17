"""Spatial Hi-C-RNA .pairs → per-spot contacts in the windows of the section's pooled-map structures (boundary
flanks and crossing squares, loop peaks and donuts: uchrom-reproducibility ``benchmarks/spatial_variable/bulk_calls.py``), the inputs of
per-spot insulation and loop strength (``uchrom.io.WindowCounts``).  Same reading and spots as
``spatial_pairs_stats.py``; MAPQ >= 30 on both legs (the filter of the pooled maps the structures were called on).

    pigz -dc sample.nodups.pairs.gz | python spatial_pairs_windows.py --positions tissue_positions_list.csv \
        --windows sample.windows.parquet --resolution 25000 --out out/sample

Writes ``<out>.window_counts.npz`` (``WindowCounts.load``) and ``<out>.window_counts.json``.
"""
from __future__ import annotations

import argparse
import json
import sys
import time

import numpy as np
import pandas as pd

from uchrom.io.pairs_windows import WindowCounts

from spatial_pairs_stats import MAIN_CHROM, _chain, _codes, read_header


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--pairs", default="-")
    ap.add_argument("--positions", required=True)
    ap.add_argument("--windows", required=True, help="parquet: chrom, start1, end1, start2, end2, feature, part, kind")
    ap.add_argument("--resolution", type=int, default=25_000)
    ap.add_argument("--out", required=True)
    ap.add_argument("--min-mapq", type=int, default=30)
    ap.add_argument("--chunksize", type=int, default=5_000_000)
    ap.add_argument("--max-lines", type=int, default=0)
    a = ap.parse_args()
    t0 = time.time()
    pos = pd.read_csv(a.positions, header=None,
                      names=["barcode", "in_tissue", "array_row", "array_col", "pxl_row", "pxl_col"])
    spots = pos[pos["in_tissue"] == 1].reset_index(drop=True)
    spot_index = pd.Index(spots["barcode"].to_numpy())
    stream = sys.stdin if a.pairs == "-" else open(a.pairs)
    sizes, asm, columns, first = read_header(stream)
    chroms = [c for c in sizes if MAIN_CHROM.match(c)]
    code = {c: i for i, c in enumerate(chroms)}
    windows = pd.read_parquet(a.windows)
    wc = WindowCounts(spots["barcode"], windows, a.resolution, chroms)
    log(f"{len(windows):,} windows, {len(wc._keys):,} pixels, {len(spots)} spots", t0)
    want = ["readID", "chrom1", "pos1", "chrom2", "pos2", "mapq1", "mapq2"]
    reader = pd.read_csv(
        _chain(first, stream), sep="\t", header=None, usecols=[columns.index(c) for c in want], names=columns,
        dtype={"readID": str, "chrom1": "category", "pos1": np.int64, "chrom2": "category", "pos2": np.int64,
               "mapq1": np.int16, "mapq2": np.int16}, chunksize=a.chunksize, engine="c")
    n = 0
    for chunk in reader:
        n += len(chunk)
        spot = spot_index.get_indexer(chunk["readID"].str.slice(0, 16))
        q = (chunk["mapq1"].to_numpy() >= a.min_mapq) & (chunk["mapq2"].to_numpy() >= a.min_mapq)
        wc.add(np.where(q, spot, -1), _codes(chunk["chrom1"], code), chunk["pos1"].to_numpy(),
               _codes(chunk["chrom2"], code), chunk["pos2"].to_numpy())
        log(f"{n:,} pairs read", t0)
        if a.max_lines and n >= a.max_lines:
            break
    meta = {"assembly": asm, "min_mapq": a.min_mapq, "resolution": a.resolution, "windows": a.windows,
            "positions": a.positions, "lines": n}
    wc.save(f"{a.out}.window_counts.npz", **meta)
    log_ = {**meta, "n_spots_in_tissue": len(spots), "n_windows": int(len(windows)),
            "counted": int(wc.counts.sum()), "seconds": time.time() - t0}
    with open(f"{a.out}.window_counts.json", "w") as f:
        json.dump(log_, f, indent=1)
    print(json.dumps(log_, indent=1))


def log(msg, t0):
    print(f"[{time.time() - t0:7.0f} s] {msg}", flush=True)


if __name__ == "__main__":
    main()
