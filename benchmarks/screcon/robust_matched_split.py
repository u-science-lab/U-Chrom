"""Development / held-back split of the Nagano 2017 serum cells for the matched-imaging analysis of
``robust`` (PREREG.md §6, entry 2026-10-01): cells sorted by name, permuted with
``numpy.random.default_rng(20261001)``, the first floor(n / 2) are development, the rest held back.
2i cells are not used for tuning at all.

    python benchmarks/screcon/robust_matched_split.py --manifest M/nagano/serum/manifest.tsv --out-dir M/robust_split
writes ``dev_manifest.tsv`` and ``heldback_manifest.tsv`` (same columns as the input).
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

SEED = 20261001


def split(cells) -> tuple[list[str], list[str]]:
    cells = sorted(cells)
    perm = np.random.default_rng(SEED).permutation(len(cells))
    k = len(cells) // 2
    dev = sorted(cells[i] for i in perm[:k])
    rest = sorted(cells[i] for i in perm[k:])
    return dev, rest


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--out-dir", type=Path, required=True)
    args = ap.parse_args(argv)
    m = pd.read_csv(args.manifest, sep="\t")
    dev, rest = split(m["cell"].astype(str))
    args.out_dir.mkdir(parents=True, exist_ok=True)
    m[m["cell"].isin(dev)].to_csv(args.out_dir / "dev_manifest.tsv", sep="\t", index=False)
    m[m["cell"].isin(rest)].to_csv(args.out_dir / "heldback_manifest.tsv", sep="\t", index=False)
    print(f"{len(dev)} development, {len(rest)} held back")


if __name__ == "__main__":
    main()
