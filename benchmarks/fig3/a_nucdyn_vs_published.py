"""Fig. 3a feasibility: U-Chrom NucDynamics vs the published Stevens 2017 models.

Stevens et al. 2017 deposited 10 final 100 kb models per cell on GEO
(GSE80280, ``<GSM>_Cell_<n>_genome_structure_model.pdb.gz``; extended PDB,
chain letter a..t = chr1..chr19, chrX, particle start in the last column,
coordinates in particle radii).  This script reports:

* **published precision** — RMSD between the published models after
  optimal superposition (Kabsch, no scaling), the paper's own metric
  (Extended Data Table 2: Cell 1 = 0.41 radii at 100 kb);
* **U-Chrom vs published** — every U-Chrom particle is matched to the
  published particle of the same chromosome with the nearest start; then
  genome-wide RMSD after superposition (reflection allowed, since a model
  and its mirror image fit the contacts equally) and the median over
  chromosomes of the Pearson r of the distance matrices, with the same
  numbers for published-vs-published as the ceiling.

Usage::

    python benchmarks/fig3/a_nucdyn_vs_published.py PDB_GZ MODEL [MODEL ...] [--out x.json]
"""

from __future__ import annotations

import argparse
import gzip
import itertools
import json
from pathlib import Path

import numpy as np
import pandas as pd

from uchrom import ChromData

CHAINS = {chr(ord("a") + i): f"chr{i + 1}" for i in range(19)} | {"t": "chrX"}


def read_pdb(path: str) -> list[pd.DataFrame]:
    models, rows = [], []
    with gzip.open(path, "rt") as fh:
        for line in fh:
            if line.startswith("MODEL"):
                rows = []
            elif line.startswith("HETATM"):
                rows.append((CHAINS.get(line[21], line[21]), int(line.split()[-1]),
                             float(line[30:38]), float(line[38:46]), float(line[46:54])))
            elif line.startswith("ENDMDL"):
                df = pd.DataFrame(rows, columns=["chrom", "start", "x", "y", "z"])
                models.append(df.drop_duplicates(["chrom", "start"]).reset_index(drop=True))
    return models


def kabsch_rmsd(a: np.ndarray, b: np.ndarray, reflect: bool = False) -> float:
    a, b = a - a.mean(0), b - b.mean(0)
    u, _, vt = np.linalg.svd(a.T @ b)
    d = 1.0 if reflect else np.sign(np.linalg.det(u @ vt))
    r = u @ np.diag([1, 1, d]) @ vt
    return float(np.sqrt(((a @ r - b) ** 2).sum(1).mean()))


def dist_r(a: pd.DataFrame, b: np.ndarray) -> float:
    rs = []
    xa = a[["x", "y", "z"]].to_numpy()
    for _, idx in a.groupby("chrom").indices.items():
        if len(idx) < 10:
            continue
        da = np.linalg.norm(xa[idx, None] - xa[None, idx], axis=-1)
        db = np.linalg.norm(b[idx, None] - b[None, idx], axis=-1)
        iu = np.triu_indices(len(idx), 1)
        rs.append(np.corrcoef(da[iu], db[iu])[0, 1])
    return float(np.median(rs))


def match(ours: pd.DataFrame, ref: pd.DataFrame) -> np.ndarray:
    """Index into ``ref`` of the nearest-start particle on the same chromosome."""
    out = np.full(len(ours), -1)
    for c, idx in ours.groupby("chrom").indices.items():
        r = ref.index[ref["chrom"] == c]
        if len(r) == 0:
            continue
        rs = ref.loc[r, "start"].to_numpy()
        k = np.clip(np.searchsorted(rs, ours["start"].to_numpy()[idx]), 1, len(rs) - 1)
        left = np.abs(rs[k - 1] - ours["start"].to_numpy()[idx]) <= np.abs(rs[k] - ours["start"].to_numpy()[idx])
        out[idx] = r[np.where(left, k - 1, k)]
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pdb")
    ap.add_argument("models", nargs="+")
    ap.add_argument("--out", type=Path)
    args = ap.parse_args()
    pub = read_pdb(args.pdb)
    res = {"pdb": args.pdb, "n_published_models": len(pub), "n_particles_published": len(pub[0])}
    pp = [kabsch_rmsd(*(m[["x", "y", "z"]].to_numpy() for m in (a, b)))
          for a, b in itertools.combinations(pub, 2)]
    pr = [dist_r(a, b[["x", "y", "z"]].to_numpy()) for a, b in itertools.combinations(pub, 2)]
    res["published_vs_published"] = {"rmsd_mean": float(np.mean(pp)), "rmsd_min": float(np.min(pp)),
                                      "rmsd_max": float(np.max(pp)), "dist_r_median": float(np.median(pr))}
    res["uchrom_vs_published"] = []
    for path in args.models:
        cd = ChromData.read(path)
        ours = cd.spots_with_loci()[["chrom", "start"]].astype({"chrom": str}).reset_index(drop=True)
        ours[["x", "y", "z"]] = cd.coords
        rmsd, rr = [], []
        for ref in pub:
            j = match(ours, ref)
            ok = j >= 0
            xr = ref[["x", "y", "z"]].to_numpy()[j[ok]]
            xo = ours.loc[ok, ["x", "y", "z"]].to_numpy()
            rmsd.append(kabsch_rmsd(xo, xr, reflect=False))
            rmsd.append(kabsch_rmsd(xo, xr, reflect=True))
            rr.append(dist_r(ours.loc[ok].reset_index(drop=True), xr))
        res["uchrom_vs_published"].append({
            "model": path, "n_particles": len(ours), "rmsd_best_of_mirror_mean": float(np.mean(np.minimum(rmsd[::2], rmsd[1::2]))),
            "dist_r_median": float(np.median(rr))})
    print(json.dumps(res, indent=1))
    if args.out:
        args.out.write_text(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
