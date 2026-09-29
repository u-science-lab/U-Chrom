"""Deduplicated spatial Hi-C .pairs (readID = "<bcB>_<bcA>") -> per-barcode-pair maps (.scool) + bulk (.mcool).

Barcodes are corrected to the whitelist with at most one mismatch (the lists are >= 4 apart); pairs whose
barcodes do not correct are dropped.  Cells of the .scool are named "<bcB>_<bcA>" (whitelist sequences);
which spot of which section a pair is, is decided when the maps are linked to a store.  Only pairs with
both ends on chr1-19 / chrX and mapq >= --min-mapq count.  Streams the file in chunks; memory grows with
the number of distinct (barcode pair, bin1, bin2) pixels.

    pigz -dc run.dedup.pairs.gz | python pairs_to_cool.py --grid 50|96 --barcodes DIR --out out/run

Writes <out>.pixels_1Mb.scool, <out>.bulk.mcool (25 kb .. 1 Mb), <out>.barcode_stats.tsv (pairs, cis,
trans, cis > 10 kb per barcode pair) and <out>.log.json.
"""
from __future__ import annotations

import argparse
import itertools
import json
import sys
import time

import numpy as np
import pandas as pd

CHROMS = [f"chr{i}" for i in range(1, 20)] + ["chrX"]


def corrector(barcodes: list[str]) -> dict[str, int]:
    """Barcode (or any one-mismatch variant, N included) -> index; ambiguous variants dropped."""
    out, seen = {b: i for i, b in enumerate(barcodes)}, {}
    for i, b in enumerate(barcodes):
        for k, base in itertools.product(range(len(b)), "ACGTN"):
            v = b[:k] + base + b[k + 1:]
            if v != b:
                seen.setdefault(v, set()).add(i)
    for v, s in seen.items():
        if v not in out and len(s) == 1:
            out[v] = next(iter(s))
    return out


def bins_table(sizes: dict[str, int], res: int) -> pd.DataFrame:
    parts = []
    for c in CHROMS:
        n = -(-sizes[c] // res)
        s = np.arange(n, dtype=np.int64) * res
        parts.append(pd.DataFrame({"chrom": c, "start": s, "end": np.minimum(s + res, sizes[c])}))
    return pd.concat(parts, ignore_index=True)


class Acc:
    """Sum of counts per int64 key, merged every few chunks to bound memory."""

    def __init__(self):
        self.parts = []

    def add(self, keys: np.ndarray):
        k, c = np.unique(keys, return_counts=True)
        self.parts.append(pd.Series(c, index=k))
        if len(self.parts) >= 8:
            self.parts = [pd.concat(self.parts).groupby(level=0).sum()]

    def total(self) -> pd.Series:
        return pd.concat(self.parts).groupby(level=0).sum() if self.parts else pd.Series(dtype=np.int64)


def main() -> None:
    import cooler

    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--pairs", default="-")
    ap.add_argument("--grid", type=int, choices=(50, 96), required=True)
    ap.add_argument("--barcodes", required=True, help="folder with barcodes_50_A/B.tsv and barcodes_96.tsv")
    ap.add_argument("--out", required=True)
    ap.add_argument("--spot-res", type=int, default=1_000_000)
    ap.add_argument("--bulk-res", type=int, default=25_000)
    ap.add_argument("--min-mapq", type=int, default=30)
    ap.add_argument("--min-pairs", type=int, default=100, help="barcode pairs with fewer cis pairs get no map")
    ap.add_argument("--chunksize", type=int, default=5_000_000)
    a = ap.parse_args()
    t0 = time.time()
    if a.grid == 50:
        A = pd.read_csv(f"{a.barcodes}/barcodes_50_A.tsv", sep="\t")["barcode"].tolist()
        B = pd.read_csv(f"{a.barcodes}/barcodes_50_B.tsv", sep="\t")["barcode"].tolist()
    else:
        A = B = pd.read_csv(f"{a.barcodes}/barcodes_96.tsv", sep="\t")["barcode"].tolist()
    ca, cb = corrector(A), corrector(B)
    nA = len(A)
    stream = sys.stdin if a.pairs == "-" else open(a.pairs)
    header, sizes = [], {}
    line = stream.readline()
    while line.startswith("#"):
        header.append(line)
        if line.startswith("#chromsize:"):
            _, c, n = line.split()
            sizes[c] = int(n)
        if line.startswith("#columns:"):
            cols = line.split()[1:]
        line = stream.readline()
    first = line
    offs = {}
    for res in (a.spot_res, a.bulk_res):
        n = np.array([-(-sizes[c] // res) for c in CHROMS], dtype=np.int64)
        offs[res] = (dict(zip(CHROMS, np.r_[0, np.cumsum(n)[:-1]])), int(n.sum()))
    spot, bulk = Acc(), Acc()
    per_bc = np.zeros((4, len(B) * nA), dtype=np.int64)          # pairs, cis, trans, cis > 10 kb
    st = dict(lines=0, kept=0, bad_barcode=0, low_mapq=0, other_chrom=0)
    use = ["readID", "chrom1", "pos1", "chrom2", "pos2"] + (["mapq1", "mapq2"] if "mapq1" in cols else [])
    import io

    src = io.StringIO(first) if first else io.StringIO("")
    reader = pd.read_csv(itertools_chain(src, stream), sep="\t", header=None, names=cols, usecols=use,
                         chunksize=a.chunksize, dtype={"readID": str, "chrom1": str, "chrom2": str})
    for df in reader:
        st["lines"] += len(df)
        rid = df["readID"].str[-17:]
        ib = rid.str[:8].map(cb)
        ia = rid.str[9:].map(ca)
        ok = ib.notna() & ia.notna()
        st["bad_barcode"] += int((~ok).sum())
        df, bc = df[ok], (ib[ok].astype(np.int64) * nA + ia[ok].astype(np.int64)).to_numpy()
        if "mapq1" in df:
            q = (df["mapq1"] >= a.min_mapq) & (df["mapq2"] >= a.min_mapq)
            st["low_mapq"] += int((~q).sum())
            df, bc = df[q], bc[q.to_numpy()]
        main = df["chrom1"].isin(CHROMS) & df["chrom2"].isin(CHROMS)
        st["other_chrom"] += int((~main).sum())
        df, bc = df[main], bc[main.to_numpy()]
        cis = (df["chrom1"] == df["chrom2"]).to_numpy()
        p1, p2 = df["pos1"].to_numpy(np.int64), df["pos2"].to_numpy(np.int64)
        np.add.at(per_bc[0], bc, 1)
        np.add.at(per_bc[1], bc[cis], 1)
        np.add.at(per_bc[2], bc[~cis], 1)
        np.add.at(per_bc[3], bc[cis & (np.abs(p2 - p1) > 10_000)], 1)
        st["kept"] += len(df)
        for res, acc, with_bc in ((a.spot_res, spot, True), (a.bulk_res, bulk, False)):
            off, n = offs[res]
            b1 = df["chrom1"].map(off).to_numpy(np.int64) + p1 // res
            b2 = df["chrom2"].map(off).to_numpy(np.int64) + p2 // res
            lo, hi = np.minimum(b1, b2), np.maximum(b1, b2)
            key = lo * n + hi
            if with_bc:
                key = key[cis]                                  # per-spot maps: cis only (as the authors')
                key = bc[cis] * (n * n) + key
            acc.add(key)
        print(f"[{time.time() - t0:.0f}s] {st['lines']:,} pairs read, {st['kept']:,} kept", flush=True)
    # per barcode pair: one cis map when it has enough pairs
    names = [f"{B[i // nA]}_{A[i % nA]}" for i in range(len(B) * nA)]
    keep = per_bc[1] >= a.min_pairs
    s = spot.total()
    _, n = offs[a.spot_res]
    keys, vals = s.index.to_numpy(np.int64), s.to_numpy(np.int64)
    bcs, pix = keys // (n * n), keys % (n * n)
    bounds = np.searchsorted(bcs, np.arange(len(names) + 1))
    cells = {names[i]: pd.DataFrame({"bin1_id": pix[bounds[i]:bounds[i + 1]] // n, "bin2_id": pix[bounds[i]:bounds[i + 1]] % n,
                                     "count": vals[bounds[i]:bounds[i + 1]]})
             for i in np.flatnonzero(keep) if bounds[i + 1] > bounds[i]}
    tag = f"{a.spot_res // 1_000_000}Mb" if a.spot_res % 1_000_000 == 0 else f"{a.spot_res // 1000}kb"
    cooler.create_scool(f"{a.out}.pixels_{tag}.scool", bins_table(sizes, a.spot_res), cells, ordered=True)
    b = bulk.total()
    _, n = offs[a.bulk_res]
    k = b.index.to_numpy(np.int64)
    tmp = f"{a.out}.bulk_base.cool"
    cooler.create_cooler(tmp, bins_table(sizes, a.bulk_res),
                         pd.DataFrame({"bin1_id": k // n, "bin2_id": k % n, "count": b.to_numpy(np.int64)}), ordered=True)
    cooler.zoomify_cooler(tmp, f"{a.out}.bulk.mcool", [a.bulk_res * f for f in (1, 2, 4, 10, 20, 40)], chunksize=10_000_000)
    import os

    os.remove(tmp)
    pd.DataFrame({"barcode_pair": names, "pairs": per_bc[0], "cis": per_bc[1], "trans": per_bc[2],
                  "cis_more_10kb": per_bc[3], "has_map": keep}).to_csv(f"{a.out}.barcode_stats.tsv", sep="\t", index=False)
    st.update(maps=len(cells), seconds=round(time.time() - t0), spot_res=a.spot_res, bulk_res=a.bulk_res,
              min_mapq=a.min_mapq, min_pairs=a.min_pairs)
    json.dump(st, open(f"{a.out}.log.json", "w"), indent=1)
    print(json.dumps(st), flush=True)


def itertools_chain(first, rest):
    """A file-like object reading `first` (the first data line) and then `rest`."""
    class _Chain:
        def __init__(self):
            self.parts = [first, rest]

        def read(self, n=-1):
            out = ""
            while self.parts and (n < 0 or len(out) < n):
                chunk = self.parts[0].read(-1 if n < 0 else n - len(out))
                if not chunk:
                    self.parts.pop(0)
                    continue
                out += chunk
            return out

        def readline(self, *args):
            while self.parts:
                line = self.parts[0].readline()
                if line:
                    return line
                self.parts.pop(0)
            return ""

        def __iter__(self):
            while True:
                line = self.readline()
                if not line:
                    return
                yield line

    return _Chain()


if __name__ == "__main__":
    main()
