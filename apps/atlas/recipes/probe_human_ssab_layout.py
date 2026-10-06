"""What the 5,359 columns of the human melanoma single-spot A/B (``obsm['X_abcompartment']``) are.

The authors give no bin table.  This probe shows what the data say (it does not link anything):

1. A rule from the UCSC hg38 annotation (``apps/atlas/recipes/ref_hg38``): 500-kb bins from the start of chr1..chr22,
   dropping every bin that overlaps the centromere models or a ``heterochromatin`` / ``short_arm`` gap, gives
   5,378 columns (5,359 observed).
2. Where each chromosome starts in the 5,359 columns, found by correlating the mean ssAB of the first 40 retained
   bins with the bulk compartment eigenvector E1 (500 kb, our bulk map of human_melanoma_r1) of that chromosome.
3. The same for the whole chromosome: sliding windows along chr1 give the offset (bin - column) = 0 over
   columns 0-~215, then a jump of 43 bins (the centromere models 122.0-124.9 Mb + the 18-Mb heterochromatin gap
   125.2-143.2 Mb), then 43 again to the end of the chromosome.

    python apps/atlas/recipes/probe_human_ssab_layout.py

Result: the layout is 500-kb bins from bin 0, chr1..chr22, centromere / heterochromatin removed, but the exact bins
dropped near the centromeres differ from the annotation rule by a few per chromosome (-5..+2, 19 in all), so the
columns cannot be placed bin by bin without the authors' table; human ssAB stays unlinked.
"""

from __future__ import annotations

import gzip
import io
import sys
import warnings
from pathlib import Path
from uchrom.datasets import data_dir

import h5py
import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
HERE = Path(__file__).resolve().parent
DATA = data_dir()                       # $UCHROM_DATA, else ~/.cache/uchrom
sys.path.insert(0, str(HERE))
import build_spatial_hicrna as b  # noqa: E402
from link_spatial_hicrna_contacts import CONTACTS, bulk_e1  # noqa: E402

H, RES = b.HG38, 500_000
CHS = [f"chr{i}" for i in range(1, 23)]
gap = pd.read_csv(HERE / "ref_hg38/hg38.gap.txt.gz", sep="\t", header=None, usecols=[1, 2, 3, 7], names=["chrom", "start", "end", "type"])
cen = pd.read_csv(HERE / "ref_hg38/hg38.centromeres.txt.gz", sep="\t", header=None, usecols=[1, 2, 3], names=["chrom", "start", "end"])


def rule_bins(c: str) -> np.ndarray:
    nb = H[c] // RES
    bad = np.zeros(nb, bool)
    g = gap[(gap.chrom == c) & gap.type.isin(["heterochromatin", "short_arm"])]
    for s, e in list(zip(g.start, g.end)) + list(zip(cen[cen.chrom == c].start, cen[cen.chrom == c].end)):
        bad[s // RES: min(nb, (e - 1) // RES + 1)] = True
    return np.flatnonzero(~bad)


def main() -> None:
    raw = DATA / "spatial_hicrna/raw/GSE311199/GSM9320922_Human_melanoma_HIC_RNA.h5ad.gz"
    with gzip.open(raw, "rb") as fh, h5py.File(io.BytesIO(fh.read()), "r") as f:
        X = f["obsm/X_abcompartment"][:]
    mean = X.mean(0)
    B = [rule_bins(c) for c in CHS]
    E = [bulk_e1(CONTACTS / "human_melanoma_r1.bulk.mcool", c) for c in CHS]
    cum = np.cumsum([0] + [len(x) for x in B])
    print(f"[1] annotation rule: {cum[-1]:,} columns for chr1-22 (observed {X.shape[1]:,}; difference {cum[-1] - X.shape[1]})")
    starts = [0]
    for ci in range(1, 22):
        v = E[ci][B[ci][:40]]
        g = np.isfinite(v)
        res = sorted(((abs(np.corrcoef(v[g], mean[S:S + 40][g])[0, 1]), S) for S in range(int(cum[ci]) - 60, int(cum[ci]) + 25)
                      if len(mean[S:S + 40]) == 40), reverse=True)
        starts.append(res[0][1])
        print(f"[2] {CHS[ci]} starts at column {res[0][1]} (|r| {res[0][0]:.2f}, next {res[1][0]:.2f}); rule would put it at {cum[ci]}")
    starts.append(X.shape[1])
    cols = np.diff(starts)
    print("[2] columns per chromosome (observed - rule):",
          {c: int(n - len(B[i])) for i, (c, n) in enumerate(zip(CHS, cols)) if i < 21})
    e = bulk_e1(CONTACTS / "human_melanoma_r1.bulk.mcool", "chr1")
    print("[3] chr1: window (40 columns) best offset bin - column")
    for j in range(0, 400, 40):
        best = []
        for d in range(-5, 60):
            v = e[j + d: j + d + 40] if j + d >= 0 else np.array([])
            if len(v) == 40 and np.isfinite(v).sum() > 25:
                ok = np.isfinite(v)
                best.append((abs(np.corrcoef(v[ok], mean[j: j + 40][ok])[0, 1]), d))
        r, d = max(best)
        print(f"    columns {j}-{j + 39}: offset {d}  |r| {r:.2f}")


if __name__ == "__main__":
    main()
