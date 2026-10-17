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

Used by Fig. 3 (`an unpublished design note`): panel b (imaging-derived contacts
vs Hi-C: IMR90 / K562 chr21 for Bintu 2018), panel a / c (GEM-FISH on
IMR90 chr20-22, X; MDS on GM12878).

Usage::

    python apps/atlas/recipes/build_rao2014_slices.py                    # IMR90 + K562 chr21, 5 kb
    python apps/atlas/recipes/build_rao2014_slices.py --cell IMR90 --chroms 20 21 22 X --res 50000
    python apps/atlas/recipes/build_rao2014_slices.py --cell GM12878 --chroms 22 --res 100000

The slicing is ``uchrom.datasets._builders.slice_hic`` (the registered slices, e.g. ``python -m
uchrom.datasets fetch rao2014_imr90_chr21``, are built by it); this script makes other chromosome /
resolution combinations.  Needs ``hic-straw`` (``pip install hic-straw``) and ``cooler``.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from uchrom.datasets import data_dir
from uchrom.datasets._builders import HIC, slice_hic

DATA = data_dir()                       # $UCHROM_DATA, else ~/.cache/uchrom


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cell", nargs="+", default=["IMR90", "K562"], choices=list(HIC))
    ap.add_argument("--chroms", nargs="+", default=["21"])
    ap.add_argument("--res", type=int, default=5000)
    ap.add_argument("--root", type=Path, default=DATA, help="data directory to write into (default $UCHROM_DATA, else ~/.cache/uchrom)")
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
