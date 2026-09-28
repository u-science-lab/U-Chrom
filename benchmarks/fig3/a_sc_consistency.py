"""Fig. 3a feasibility: single-cell structures from scHi-C (NucDynamics / GEM).

Given several structure models of the same cell (different random seeds)
and the cell's contact pairs, report the quantities Stevens et al. 2017
used to judge structure quality:

* **precision** — RMSD between models after optimal superposition
  (Kabsch, no scaling), whole genome and per chromosome, in model units
  (NucDynamics: 1 unit ~ one particle radius), plus the Pearson r of their
  per-chromosome distance matrices;
* **contact-distance consistency** — 3-D distance of every input contact
  (particles in contact in the data should be ~1 unit apart): median,
  fraction <= 1.2 (the upper restraint bound for one contact) and
  fraction > 5 (the violation threshold), vs the median distance of all
  pairs at the same genomic separation.

Usage::

    python benchmarks/fig3/a_sc_consistency.py PAIRS MODEL1 MODEL2 [MODEL3 ...] [--out x.json]
"""

from __future__ import annotations

import argparse
import itertools
import json
from pathlib import Path

import numpy as np
import pandas as pd

from uchrom import ChromData


def kabsch_rmsd(a: np.ndarray, b: np.ndarray) -> float:
    a = a - a.mean(0)
    b = b - b.mean(0)
    u, s, vt = np.linalg.svd(a.T @ b)
    d = np.sign(np.linalg.det(u @ vt))
    r = u @ np.diag([1, 1, d]) @ vt
    return float(np.sqrt(((a @ r - b) ** 2).sum(1).mean()))


def load(path: str) -> pd.DataFrame:
    cd = ChromData.read(path)
    df = cd.spots_with_loci()[["chrom", "start", "end"]].copy()
    df[["x", "y", "z"]] = cd.coords
    return df.sort_values(["chrom", "start"]).reset_index(drop=True)


def contact_consistency(model: pd.DataFrame, pairs: pd.DataFrame) -> dict:
    size = int(np.median(model["end"] - model["start"]))
    pairs = pairs[pairs["c1"] == pairs["c2"]]
    i = np.full(len(pairs), np.nan)
    j = np.full(len(pairs), np.nan)
    for c, idx in model.groupby(model["chrom"].astype(str)).indices.items():
        st, en = model["start"].to_numpy()[idx], model["end"].to_numpy()[idx]
        sel = (pairs["c1"] == c).to_numpy()
        for p, out in (("p1", i), ("p2", j)):
            x = pairs.loc[sel, p].to_numpy()
            k = np.searchsorted(st, x, side="right") - 1
            good = (k >= 0) & (x < en[np.clip(k, 0, None)])
            out[np.flatnonzero(sel)[good]] = idx[k[good]]
    ok = np.isfinite(i) & np.isfinite(j) & (np.abs(i - j) >= 2)
    i, j = i[ok].astype(int), j[ok].astype(int)
    ij = np.unique(np.c_[np.minimum(i, j), np.maximum(i, j)], axis=0)
    xyz = model[["x", "y", "z"]].to_numpy()
    d = np.linalg.norm(xyz[ij[:, 0]] - xyz[ij[:, 1]], axis=1)
    # background: same genomic separation, random shift within chromosome
    rng = np.random.default_rng(0)
    sep = ij[:, 1] - ij[:, 0]
    chrom = model["chrom"].astype(str).to_numpy()
    starts = rng.integers(0, len(model), len(ij) * 3)
    s3 = np.tile(sep, 3)
    ends = starts + s3
    ok = (ends < len(model))
    ok[ok] &= chrom[starts[ok]] == chrom[ends[ok]]
    dbg = np.linalg.norm(xyz[starts[ok]] - xyz[ends[ok]], axis=1)
    return {"n_contacts": int(len(ij)), "particle_bp": size,
            "median_contact_dist": float(np.median(d)),
            "frac_contact_le_1.2": float((d <= 1.2).mean()),
            "frac_contact_gt_5": float((d > 5).mean()),
            "median_same_sep_background": float(np.median(dbg))}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pairs")
    ap.add_argument("models", nargs="+")
    ap.add_argument("--out", type=Path)
    args = ap.parse_args()
    pairs = pd.read_csv(args.pairs, sep="\t", header=None, comment="#", usecols=[1, 2, 3, 4],
                        names=["c1", "p1", "c2", "p2"])
    models = [load(m) for m in args.models]
    res = {"models": args.models, "consistency": [contact_consistency(m, pairs) for m in models],
           "precision": []}
    for (a, ma), (b, mb) in itertools.combinations(enumerate(models), 2):
        assert (ma[["chrom", "start"]].values == mb[["chrom", "start"]].values).all()
        xa, xb = ma[["x", "y", "z"]].to_numpy(), mb[["x", "y", "z"]].to_numpy()
        per = {}
        for c, idx in ma.groupby("chrom", observed=True).indices.items():
            da = np.linalg.norm(xa[idx, None] - xa[None, idx], axis=-1)
            db = np.linalg.norm(xb[idx, None] - xb[None, idx], axis=-1)
            iu = np.triu_indices(len(idx), 1)
            per[str(c)] = {"rmsd": kabsch_rmsd(xa[idx], xb[idx]),
                           "dist_pearson": float(np.corrcoef(da[iu], db[iu])[0, 1])}
        res["precision"].append({
            "pair": [a, b], "rmsd_genome": kabsch_rmsd(xa, xb),
            "rmsd_chrom_median": float(np.median([v["rmsd"] for v in per.values()])),
            "dist_pearson_chrom_median": float(np.median([v["dist_pearson"] for v in per.values()])),
            "per_chrom": per})
    for c in res["consistency"]:
        print({k: round(v, 3) if isinstance(v, float) else v for k, v in c.items()})
    for p in res["precision"]:
        print(f"models {p['pair']}: RMSD genome {p['rmsd_genome']:.2f}, per-chrom median "
              f"{p['rmsd_chrom_median']:.2f}; distance-matrix r (median chrom) {p['dist_pearson_chrom_median']:.3f}")
    if args.out:
        args.out.write_text(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
