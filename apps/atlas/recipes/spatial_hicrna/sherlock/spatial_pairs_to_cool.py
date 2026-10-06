"""Spatial Hi-C-RNA .pairs → per-spot contact maps (.scool) + pseudo-bulk (.mcool) + per-spot stats.

The spot barcode is the first 16 bases of the read ID (``AGATCGCACTGGCATA:LH00516:…``), the same
barcodes as the tissue_positions_list.csv of the sample.  Only in-tissue spots are kept.  Streams the
file once in chunks; memory grows with the number of distinct (spot, bin1, bin2) pixels.

    pigz -dc sample.nodups.pairs.gz | python spatial_pairs_to_cool.py --positions tissue_positions_list.csv \
        --out out/sample --spot-res 1000000 --bulk-res 25000

Writes ``<out>.spots_1Mb.scool``, ``<out>.bulk.mcool`` (bulk-res … 1 Mb), ``<out>.spot_stats.tsv``
and ``<out>.log.json`` (counts, filters, timings).
"""
from __future__ import annotations

import argparse
import io
import json
import re
import sys
import time

import numpy as np
import pandas as pd

MAIN_CHROM = re.compile(r"^chr([0-9]+|X|Y)$")


def read_header(stream):
    """Consume the '#' header; return (header lines, chromsizes in file order, assembly, first data line)."""
    lines, sizes, asm = [], {}, None
    while True:
        line = stream.readline()
        if not line.startswith("#"):
            return lines, sizes, asm, line
        lines.append(line)
        if line.startswith("#chromsize:"):
            _, c, n = line.split()
            sizes[c] = int(n)
        elif line.startswith("#genome_assembly:"):
            asm = line.split(":", 1)[1].strip()


class Accumulator:
    """Sums counts per int64 key; merges chunk results periodically (sorted unique keys)."""

    def __init__(self, merge_every=16):
        self.keys = np.zeros(0, np.int64)
        self.counts = np.zeros(0, np.int64)
        self.pending: list[tuple[np.ndarray, np.ndarray]] = []
        self.merge_every = merge_every

    def add(self, keys: np.ndarray):
        if len(keys):
            k, c = np.unique(keys, return_counts=True)
            self.pending.append((k, c))
        if len(self.pending) >= self.merge_every:
            self.merge()

    def merge(self):
        if not self.pending:
            return
        k = np.concatenate([self.keys] + [p[0] for p in self.pending])
        c = np.concatenate([self.counts] + [p[1] for p in self.pending])
        order = np.argsort(k, kind="stable")
        k, c = k[order], c[order]
        starts = np.flatnonzero(np.r_[True, k[1:] != k[:-1]])
        self.keys, self.counts = k[starts], np.add.reduceat(c, starts)
        self.pending = []


def bins_table(chroms: list[str], sizes: dict[str, int], res: int):
    rows, offsets, n = [], {}, 0
    for c in chroms:
        nb = -(-sizes[c] // res)
        offsets[c] = n
        starts = np.arange(nb) * res
        rows.append(pd.DataFrame({"chrom": c, "start": starts, "end": np.minimum(starts + res, sizes[c])}))
        n += nb
    return pd.concat(rows, ignore_index=True), offsets, n


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--pairs", default="-", help="uncompressed .pairs (default: stdin)")
    ap.add_argument("--positions", required=True, help="tissue_positions_list.csv of the sample")
    ap.add_argument("--out", required=True, help="output prefix")
    ap.add_argument("--spot-res", type=int, default=1_000_000)
    ap.add_argument("--bulk-res", type=int, default=25_000)
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
    header, sizes, asm, first = read_header(stream)
    chroms = [c for c in sizes if MAIN_CHROM.match(c)]
    sb, soff, snb = bins_table(chroms, sizes, a.spot_res)
    bb, boff, bnb = bins_table(chroms, sizes, a.bulk_res)
    off_s = pd.Series(soff)
    off_b = pd.Series(boff)
    spot_acc, bulk_acc = Accumulator(), Accumulator()
    n_spots = len(spots)
    cis = np.zeros(n_spots, np.int64)
    trans = np.zeros(n_spots, np.int64)
    stats = {"lines": 0, "kept": 0, "low_mapq": 0, "other_chrom": 0, "no_spot": 0}

    reader = pd.read_csv(
        _chain(first, stream), sep="\t", header=None, usecols=[0, 1, 2, 3, 4, 8, 9],
        names=["rid", "c1", "p1", "c2", "p2", "s1", "s2", "t", "m1", "m2"],
        dtype={"rid": str, "c1": str, "p1": np.int64, "c2": str, "p2": np.int64, "m1": np.int16, "m2": np.int16},
        chunksize=a.chunksize, engine="c")
    for chunk in reader:
        n = len(chunk)
        stats["lines"] += n
        q = (chunk["m1"].to_numpy() >= a.min_mapq) & (chunk["m2"].to_numpy() >= a.min_mapq)
        stats["low_mapq"] += int((~q).sum())
        chunk = chunk[q]
        o1s, o2s = chunk["c1"].map(off_s), chunk["c2"].map(off_s)
        ok = o1s.notna().to_numpy() & o2s.notna().to_numpy()
        stats["other_chrom"] += int((~ok).sum())
        chunk, o1s, o2s = chunk[ok], o1s[ok], o2s[ok]
        spot = spot_index.get_indexer(chunk["rid"].str.slice(0, 16))
        has = spot >= 0
        stats["no_spot"] += int((~has).sum())
        p1, p2 = chunk["p1"].to_numpy()[has], chunk["p2"].to_numpy()[has]
        same = (chunk["c1"].to_numpy() == chunk["c2"].to_numpy())[has]
        spot = spot[has]
        s1 = o1s.to_numpy()[has].astype(np.int64) + p1 // a.spot_res
        s2 = o2s.to_numpy()[has].astype(np.int64) + p2 // a.spot_res
        b1 = chunk["c1"].map(off_b).to_numpy()[has].astype(np.int64) + p1 // a.bulk_res
        b2 = chunk["c2"].map(off_b).to_numpy()[has].astype(np.int64) + p2 // a.bulk_res
        lo, hi = np.minimum(s1, s2), np.maximum(s1, s2)
        spot_acc.add(spot.astype(np.int64) * snb * snb + lo * snb + hi)
        lo, hi = np.minimum(b1, b2), np.maximum(b1, b2)
        bulk_acc.add(lo * bnb + hi)
        np.add.at(cis, spot[same], 1)
        np.add.at(trans, spot[~same], 1)
        stats["kept"] += int(has.sum())
        print(f"[{time.time() - t0:7.0f} s] {stats['lines']:,} pairs read, {stats['kept']:,} kept", flush=True)
        if a.max_lines and stats["lines"] >= a.max_lines:
            break
    spot_acc.merge()
    bulk_acc.merge()
    t_read = time.time() - t0

    import cooler
    # per-spot .scool
    key = spot_acc.keys
    sp, rest = np.divmod(key, snb * snb)
    b1, b2 = np.divmod(rest, snb)
    starts = np.flatnonzero(np.r_[True, sp[1:] != sp[:-1]])
    ends = np.r_[starts[1:], len(sp)]
    cells = {}
    for s, e in zip(starts, ends):
        cells[spots["barcode"][sp[s]]] = pd.DataFrame(
            {"bin1_id": b1[s:e], "bin2_id": b2[s:e], "count": spot_acc.counts[s:e].astype(np.int32)})
    res_tag = f"{a.spot_res // 1_000_000}Mb" if a.spot_res % 1_000_000 == 0 else f"{a.spot_res // 1000}kb"
    scool = f"{a.out}.spots_{res_tag}.scool"
    cooler.create_scool(scool, sb, cells, ordered=True, symmetric_upper=True, mode="w")
    # pseudo-bulk .mcool
    bb1, bb2 = np.divmod(bulk_acc.keys, bnb)
    base = f"{a.out}.bulk_{a.bulk_res}.cool"
    cooler.create_cooler(base, bb, pd.DataFrame({"bin1_id": bb1, "bin2_id": bb2, "count": bulk_acc.counts}),
                         ordered=True, symmetric_upper=True, assembly=asm)
    resolutions = [r for r in (25_000, 50_000, 100_000, 250_000, 500_000, 1_000_000) if r >= a.bulk_res]
    cooler.zoomify_cooler(base, f"{a.out}.bulk.mcool", resolutions, chunksize=10_000_000)
    # per-spot stats
    spots.assign(n_contacts=cis + trans, cis=cis, trans=trans,
                 cis_fraction=np.where(cis + trans > 0, cis / np.maximum(cis + trans, 1), np.nan)
                 ).to_csv(f"{a.out}.spot_stats.tsv", sep="\t", index=False)
    stats.update({"assembly": asm, "n_spots_in_tissue": n_spots, "n_spots_with_contacts": len(cells),
                  "spot_res": a.spot_res, "bulk_res": a.bulk_res, "min_mapq": a.min_mapq,
                  "spot_pixels": int(len(spot_acc.keys)), "bulk_pixels": int(len(bulk_acc.keys)),
                  "seconds_read": t_read, "seconds_total": time.time() - t0})
    with open(f"{a.out}.log.json", "w") as f:
        json.dump(stats, f, indent=1)
    print(json.dumps(stats, indent=1))


def _chain(first: str, stream):
    """A file-like object yielding `first` then the rest of `stream` (the header is already consumed)."""
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
