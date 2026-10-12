"""Example structures of chromosome 2 for Extended Data Fig. 3d: one typical ExN and one typical Oligo cell of the
imaging (Liu 2025 DNA-MERFISH), of the diploid EMber reconstruction of Dip-C (Tan 2021) and of the haploid one of
scHiCAR.  A typical cell is the one whose single-cell score (``transfer.py``: imaging cells by the reconstructions'
consensus signature, reconstructed cells by the imaging signature) is closest to its class median; for imaged cells,
of the 300 closest, the one with the most complete chromosome 2 copy (that copy drawn; detection is about half the
loci per copy), a diploid reconstruction draws copy 0.  Output ``--out``/cross_assay_ed_structures.parquet: source, cls, cell_id, trace_id,
start, end, x, y, z.

    python benchmarks/cross_assay/structures.py --liu STORE --recon-root $SCRATCH/uchrom-nd/runs/xassay \\
        --scores $SCRATCH/uchrom-nd/runs/xassay/transfer --out DIR
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

CHROM = "chr2"
MIN_COVER = 0.8                                        # stop early at a copy this complete
N_CANDIDATES = 300                                     # imaged cells closest to the class median considered
SOURCES = [("imaging", "scores_liu2025.parquet", "all reconstructions (mean)", None),
           ("Dip-C (reconstructed)", "scores_recon_tan_dip.parquet", "imaging", ("recon_tan", "dip")),
           ("scHiCAR (reconstructed)", "scores_recon_schicar_mouse_cortex_hap.parquet", "imaging",
            ("recon_schicar_mouse_cortex", "hap"))]


def chrom_traces(cd, cell: str) -> pd.DataFrame:
    c = cd.get_cell(cell, columns="coords")
    s = c.spots_with_loci()
    t = pd.DataFrame({"trace_id": s["trace_id"].astype(str).to_numpy(), "chrom": s["chrom"].astype(str).to_numpy(),
                      "start": s["start"].to_numpy(), "end": s["end"].to_numpy()})
    t[["x", "y", "z"]] = np.asarray(c.coords, float)
    t = t[(t["chrom"] == CHROM) & np.isfinite(t[["x", "y", "z"]]).all(axis=1)]
    return t.sort_values(["trace_id", "start"])


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--liu", type=Path, required=True)
    ap.add_argument("--recon-root", type=Path, required=True)
    ap.add_argument("--scores", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args()
    from chromdata import ChromData

    rows = []
    for source, score_file, col, recon in SOURCES:
        S = pd.read_parquet(a.scores / score_file)
        if recon is None:
            cd = ChromData.read(str(a.liu), backed=True)
            n_loci = int((cd.bins["chrom"].astype(str) == CHROM).sum())
        else:
            cd = ChromData.read(a.recon_root / recon[0] / f"{recon[1]}.chromdata.zarr", backed=True)
        for cls in ("ExN", "Oligo"):
            s = S.loc[S["cls"] == cls, col].dropna()
            order = (s - s.median()).abs().sort_values().index
            pick = None
            for cell in order[:N_CANDIDATES if recon is None else 1]:
                t = chrom_traces(cd, str(cell))
                if t.empty:
                    continue
                if recon is None:                       # the most complete chromosome 2 copy among the candidates
                    best = t.groupby("trace_id").size().idxmax()
                    t = t[t["trace_id"] == best]
                    if pick is None or len(t) > len(pick[1]):
                        pick = (cell, t)
                    if len(t) >= MIN_COVER * n_loci:
                        break
                else:
                    tr = sorted(t["trace_id"].unique())
                    pick = (cell, t[t["trace_id"] == tr[0]])
            if pick is None:
                continue
            cell, t = pick
            rows.append(t.assign(source=source, cls=cls, cell_id=str(cell), score=float(s[cell]),
                                 score_median=float(s.median())))
            print(f"{source} {cls}: cell {cell}, {len(t)} loci" + (f" of {n_loci}" if recon is None else "")
                  + f", score {s[cell]:.3f} (median {s.median():.3f})", flush=True)
    a.out.mkdir(parents=True, exist_ok=True)
    pd.concat(rows, ignore_index=True).to_parquet(a.out / "cross_assay_ed_structures.parquet")


if __name__ == "__main__":
    main()
