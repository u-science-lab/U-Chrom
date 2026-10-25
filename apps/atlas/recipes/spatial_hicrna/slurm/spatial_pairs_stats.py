"""Spatial Hi-C-RNA .pairs → per-spot contact statistics: cis contact-distance histograms (per chromosome, per
read orientation) and trans contacts per chromosome (``uchrom.io.ContactStats``), the inputs of the short /
long-range ratio, the contact-decay slope and the cis fraction of every spot (``uchrom.fea.contact_features``).

Same reading as ``spatial_pairs_to_cool.py`` (spot barcode = first 16 bases of the read ID, in-tissue spots of
the sample's tissue_positions_list.csv, main chromosomes), one pass, two filters side by side:

* ``q30`` — both legs MAPQ >= 30 (the filter of the per-spot maps in the atlas stores);
* ``all`` — every pair of the .nodups.pairs (the contacts Guo et al. 2026 split per spot for their short /
  long ratio: columns 2-5 of the file, no MAPQ filter; their extra blacklist filter is not applied here).

    pigz -dc sample.nodups.pairs.gz | python spatial_pairs_stats.py --positions tissue_positions_list.csv \
        --out out/sample

Writes ``<out>.contact_stats_q30.npz``, ``<out>.contact_stats_all.npz`` (``ContactStats.load``) and
``<out>.contact_stats.json`` (counts, pair types, filters, timings).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time

import numpy as np
import pandas as pd

from uchrom.io.pairs_stats import ContactStats, distance_edges

MAIN_CHROM = re.compile(r"^chr([0-9]+|X|Y)$")


def read_header(stream):
    """Consume the '#' header; return (chromsizes in file order, assembly, column names, first data line)."""
    sizes, asm, columns = {}, None, None
    while True:
        line = stream.readline()
        if not line.startswith("#"):
            return sizes, asm, columns, line
        if line.startswith("#chromsize:"):
            _, c, n = line.split()
            sizes[c] = int(n)
        elif line.startswith("#genome_assembly:"):
            asm = line.split(":", 1)[1].strip()
        elif line.startswith("#columns:"):
            columns = line.split(":", 1)[1].split()


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--pairs", default="-", help="uncompressed .pairs (default: stdin)")
    ap.add_argument("--positions", required=True, help="tissue_positions_list.csv of the sample")
    ap.add_argument("--out", required=True, help="output prefix")
    ap.add_argument("--min-mapq", type=int, default=30)
    ap.add_argument("--chunksize", type=int, default=5_000_000)
    ap.add_argument("--max-lines", type=int, default=0, help="stop after this many pairs (tests)")
    a = ap.parse_args()
    t0 = time.time()

    pos = pd.read_csv(a.positions, header=None,
                      names=["barcode", "in_tissue", "array_row", "array_col", "pxl_row", "pxl_col"])
    spots = pos[pos["in_tissue"] == 1].reset_index(drop=True)
    spot_index = pd.Index(spots["barcode"].to_numpy())

    stream = sys.stdin if a.pairs == "-" else open(a.pairs)
    sizes, asm, columns, first = read_header(stream)
    want = ["readID", "chrom1", "pos1", "chrom2", "pos2", "strand1", "strand2", "pair_type", "mapq1", "mapq2"]
    if columns is None or [c for c in want if c not in columns]:
        raise SystemExit(f"pairs columns {columns} lack some of {want}")
    chroms = [c for c in sizes if MAIN_CHROM.match(c)]
    edges = distance_edges({c: sizes[c] for c in chroms})
    code = {c: i for i, c in enumerate(chroms)}
    stats = {"q30": ContactStats(spots["barcode"], chroms, edges), "all": ContactStats(spots["barcode"], chroms, edges)}
    counts = {"lines": 0, "no_spot": 0, "low_mapq": 0}
    pair_types: dict = {}

    reader = pd.read_csv(
        _chain(first, stream), sep="\t", header=None,
        usecols=[columns.index(c) for c in want], names=columns,
        dtype={"readID": str, "chrom1": "category", "pos1": np.int64, "chrom2": "category", "pos2": np.int64,
               "strand1": "category", "strand2": "category", "pair_type": "category",
               "mapq1": np.int16, "mapq2": np.int16},
        chunksize=a.chunksize, engine="c")
    for chunk in reader:
        n = len(chunk)
        counts["lines"] += n
        spot = spot_index.get_indexer(chunk["readID"].str.slice(0, 16))
        counts["no_spot"] += int((spot < 0).sum())
        c1 = _codes(chunk["chrom1"], code)
        c2 = _codes(chunk["chrom2"], code)
        p1, p2 = chunk["pos1"].to_numpy(), chunk["pos2"].to_numpy()
        s1, s2 = chunk["strand1"].to_numpy() == "-", chunk["strand2"].to_numpy() == "-"
        q = (chunk["mapq1"].to_numpy() >= a.min_mapq) & (chunk["mapq2"].to_numpy() >= a.min_mapq)
        counts["low_mapq"] += int((~q & (spot >= 0)).sum())
        stats["all"].add(spot, c1, p1, c2, p2, s1, s2)
        stats["q30"].add(np.where(q, spot, -1), c1, p1, c2, p2, s1, s2)
        for t, k in chunk["pair_type"][spot >= 0].value_counts().items():
            pair_types[str(t)] = pair_types.get(str(t), 0) + int(k)
        print(f"[{time.time() - t0:7.0f} s] {counts['lines']:,} pairs read", flush=True)
        if a.max_lines and counts["lines"] >= a.max_lines:
            break

    meta = {"assembly": asm, "min_mapq": a.min_mapq, "spot_barcode": "readID[:16]", "chroms": chroms,
            "positions": a.positions}
    for name, st in stats.items():
        st.save(f"{a.out}.contact_stats_{name}.npz", filter=name, **meta)
    log = {**counts, **meta, "pair_types": pair_types, "n_spots_in_tissue": len(spots),
           "n_edges": int(len(edges)), "edges_first_last": [float(edges[0]), float(edges[-1])],
           "n_cis": {k: int(s.n_cis.sum()) for k, s in stats.items()},
           "n_trans": {k: int(s.n_trans.sum()) for k, s in stats.items()},
           "n_other_chrom": {k: int(s.n_other) for k, s in stats.items()},
           "seconds": time.time() - t0}
    with open(f"{a.out}.contact_stats.json", "w") as f:
        json.dump(log, f, indent=1)
    print(json.dumps(log, indent=1))


def _codes(cat: pd.Series, code: dict) -> np.ndarray:
    table = np.array([code.get(str(c), -1) for c in cat.cat.categories] + [-1], np.int64)
    return table[cat.cat.codes.to_numpy().astype(np.int64)]


def _chain(first: str, stream):
    """A file-like object yielding `first` then the rest of `stream` (the header is already consumed)."""
    import io

    class _C(io.TextIOBase):
        def __init__(self):
            self._first = first

        def readable(self):
            return True

        def read(self, n=-1):
            if self._first:
                s, self._first = self._first, ""
                return s + (stream.read(max(n - len(s), 0)) if n and n > 0 else stream.read())
            return stream.read(n)

        def readline(self, *args):
            if self._first:
                s, self._first = self._first, ""
                return s
            return stream.readline(*args)
    return _C()


if __name__ == "__main__":
    main()
