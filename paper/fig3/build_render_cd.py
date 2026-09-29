"""ChromData of Stevens et al. 2017 Cell 1 for the 3-D renders in Fig. 3.

Three "cells", each one model of the same genome structure at 100 kb, one trace per
chromosome: ``published`` (GEO model 1), ``original`` (tjs23/nuc_dynamics, our run,
model 1) and ``U-Chrom`` (native engine, GPU, model 1).  Particles are matched by
chromosome and position; each model is superposed on the published one (Kabsch,
mirror allowed -- contacts do not fix the handedness).  Coordinates in particle radii.

    python paper/fig3/build_render_cd.py --data example-data --runs <dir with orig_master_full/, native_gpu_full/>
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from prepare_fig3 import read_pdb

HERE = Path(__file__).resolve().parent


def kabsch_fit(X: np.ndarray, Y: np.ndarray) -> np.ndarray:
    """X superposed on Y (both N x 3), mirror image allowed; returns the moved X."""
    best = None
    for s in (1.0, -1.0):
        A = X * np.array([s, 1.0, 1.0])
        a, b = A - A.mean(0), Y - Y.mean(0)
        U, _, Vt = np.linalg.svd(a.T @ b)
        d = np.sign(np.linalg.det(U @ Vt))
        R = U @ np.diag([1, 1, d]) @ Vt
        Z = a @ R + Y.mean(0)
        rmsd = np.sqrt(((Z - Y) ** 2).sum(1).mean())
        if best is None or rmsd < best[0]:
            best = (rmsd, Z)
    return best[1]


def main() -> None:
    from uchrom import ChromData

    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", type=Path, required=True)
    ap.add_argument("--runs", type=Path, required=True)
    ap.add_argument("--out", type=Path, default=HERE / "renders" / "stevens_cell1.chromdata.zarr")
    args = ap.parse_args()
    ch, pos, Xp = read_pdb(args.data / "stevens2017_mesc" / "GSM2219497_Cell_1_genome_structure_model.pdb.gz")
    models = {"published": (ch, pos, Xp)}
    for name, run in (("original", "orig_master_full"), ("U-Chrom", "native_gpu_full")):
        z = np.load(args.runs / run / "cell1.npz")
        models[name] = (z["chrom"].astype(str), z["pos"], z["coords"][0])
    # particles present in all three
    keys = set(zip(ch, pos))
    for c, p, _ in models.values():
        keys &= set(zip(c, p))
    order = sorted(keys, key=lambda k: (int(k[0][3:]) if k[0][3:].isdigit() else 99, k[1]))
    rows, xyz = [], []
    for name, (c, p, X) in models.items():
        idx = {k: i for i, k in enumerate(zip(c, p))}
        sel = np.array([idx[k] for k in order])
        models[name] = X[sel]
    ref = models["published"]
    for name in models:
        X = ref if name == "published" else kabsch_fit(models[name], ref)
        xyz.append(X)
        rows.append(pd.DataFrame({"chrom": [k[0] for k in order], "start": [k[1] - 100_000 for k in order],
                                  "end": [k[1] for k in order], "cell_id": name,
                                  "trace_id": [f"{name}:{k[0]}" for k in order]}))
    spots = pd.concat(rows, ignore_index=True)
    cd = ChromData(np.vstack(xyz), spots, uns={"genome_assembly": "mm10", "xyz_unit": "particle radius",
                                               "description": "Stevens 2017 Cell 1: published vs original vs U-Chrom"})
    args.out.parent.mkdir(parents=True, exist_ok=True)
    cd.write(args.out)
    print(args.out, cd)


if __name__ == "__main__":
    main()
