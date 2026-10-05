"""Slice Rao et al. 2014 in situ Hi-C (GEO GSE63525) into small coolers.

The GEO ``.hic`` files are 9-51 GB each, far too large to download for a
figure.  ``hicstraw`` reads a ``.hic`` over HTTP range requests, so this
script pulls only the intra-chromosomal blocks it needs (observed, raw
counts; MAPQ > 0 "combined" files, as used by Bintu et al. 2018) and writes
one single-resolution ``.cool`` per (cell line, resolution):

    rao2014_<cell>/<CELL>_<chroms>_<res>_hg19.cool

Coordinates stay in **hg19** (Rao 2014's build); chromosome names get a
``chr`` prefix.  Nothing is normalised here — balance with
``cooler balance`` if a method needs it.

Used by Fig. 3 (``u-chrom-paper/figures/fig3/PLAN.md``): panel b (imaging-derived contacts
vs Hi-C: IMR90 / K562 chr21 for Bintu 2018), panel a / c (GEM-FISH on
IMR90 chr20-22, X; MDS on GM12878).

Usage::

    python example-data/build_rao2014_slices.py                    # IMR90 + K562 chr21, 5 kb
    python example-data/build_rao2014_slices.py --cell IMR90 --chroms 20 21 22 X --res 50000
    python example-data/build_rao2014_slices.py --cell GM12878 --chroms 22 --res 100000

Needs ``hic-straw`` (``pip install hic-straw``) and ``cooler``.
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
GEO = "https://ftp.ncbi.nlm.nih.gov/geo/series/GSE63nnn/GSE63525/suppl"
HIC = {
    # MAPQ > 0 combined maps (GEO sizes: IMR90 13 GB, K562 ~ see catalog, GM12878 51 GB)
    "IMR90": f"{GEO}/GSE63525_IMR90_combined.hic",
    "K562": f"{GEO}/GSE63525_K562_combined.hic",
    "GM12878": f"{GEO}/GSE63525_GM12878_insitu_primary+replicate_combined.hic",
}


def slice_hic(cell: str, chroms: list[str], res: int, out: Path) -> Path:
    import cooler
    import hicstraw

    t0 = time.time()
    hic = hicstraw.HiCFile(HIC[cell])
    assert hic.getGenomeID() == "hg19", hic.getGenomeID()
    if res not in hic.getResolutions():
        raise SystemExit(f"{res} bp not in {hic.getResolutions()}")
    sizes = {c.name: c.length for c in hic.getChromosomes()}
    bins, pixels, offset = [], [], 0
    for c in chroms:
        n = int(np.ceil(sizes[c] / res))
        starts = np.arange(n) * res
        bins.append(pd.DataFrame({"chrom": f"chr{c}", "start": starts,
                                  "end": np.minimum(starts + res, sizes[c])}))
        zd = hic.getMatrixZoomData(c, c, "observed", "NONE", "BP", res)
        # row blocks of 10 Mb (all columns to the right) keep memory small
        step = 10_000_000
        for s in range(0, sizes[c], step):
            recs = zd.getRecords(s, min(s + step, sizes[c]) - 1, s, sizes[c])
            if not recs:
                continue
            b1 = np.fromiter((r.binX for r in recs), np.int64, len(recs)) // res
            b2 = np.fromiter((r.binY for r in recs), np.int64, len(recs)) // res
            v = np.fromiter((r.counts for r in recs), np.float64, len(recs))
            lo, hi = np.minimum(b1, b2), np.maximum(b1, b2)
            keep = (lo * res >= s) & (lo * res < s + step)   # each pixel once
            pixels.append(pd.DataFrame({"bin1_id": lo[keep] + offset,
                                        "bin2_id": hi[keep] + offset,
                                        "count": np.rint(v[keep]).astype(np.int64)}))
        offset += n
        print(f"  {cell} chr{c} @ {res}: {sum(len(p) for p in pixels):,} pixels so far "
              f"({time.time() - t0:.0f} s)")
    px = (pd.concat(pixels).groupby(["bin1_id", "bin2_id"], as_index=False)["count"].sum()
          .sort_values(["bin1_id", "bin2_id"]))
    out.parent.mkdir(parents=True, exist_ok=True)
    cooler.create_cooler(str(out), pd.concat(bins, ignore_index=True), px, ordered=True,
                         assembly="hg19",
                         metadata={"source": HIC[cell], "normalization": "none (observed)",
                                   "citation": "Rao et al. 2014 Cell 159:1665, GEO GSE63525"})
    print(f"wrote {out} ({out.stat().st_size / 1e6:.1f} MB, {px['count'].sum():,} contacts, "
          f"{time.time() - t0:.0f} s)")
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cell", nargs="+", default=["IMR90", "K562"], choices=list(HIC))
    ap.add_argument("--chroms", nargs="+", default=["21"])
    ap.add_argument("--res", type=int, default=5000)
    ap.add_argument("--root", type=Path, default=HERE, help="example-data directory to write into")
    args = ap.parse_args()
    tag = "chr" + "-".join(args.chroms)
    res = f"{args.res // 1000}kb" if args.res < 1_000_000 else f"{args.res // 1_000_000}Mb"
    for cell in args.cell:
        out = args.root / f"rao2014_{cell.lower()}" / f"{cell}_{tag}_{res}_hg19.cool"
        if out.exists():
            print(f"[skip] {out} exists")
            continue
        slice_hic(cell, args.chroms, args.res, out)


if __name__ == "__main__":
    main()
