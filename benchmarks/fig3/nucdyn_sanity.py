"""Physical sanity checks of NucDynamics ensembles at any resolution (no reference structure needed).

For each model of ``<run>/cell<n>.npz`` (``chrom``, ``pos``, ``coords`` in particle radii):

Coordinates are in the engine's length unit, in which consecutive particles sit ~1 apart (the
backbone restraint of NucDynamics: 0.1-1.1 x the sequence spacing), so the statistics are
comparable across resolutions and with the published GEO models (``--geo-pdb``, the baseline).

* **bonds**: distance between consecutive particles of a chromosome: median, 99th percentile,
  max, share > 3 units;
* **packing**: nearest non-bonded neighbour (|i - j| >= 2 on the chain or another chromosome) per
  particle (KD-tree): 1st percentile and median;
* **contact restraints**: the cell's GEO contacts mapped to particles (a contact end at p goes to
  the particle covering p); share of non-adjacent contact pairs farther apart than 2 units
  (= 2 bead spacings, the violation threshold of Meng et al. 2021, Si-C), 4 and 6 units;
* **cross-resolution consistency** (``--coarse RUN``): particles averaged into the blocks of a
  coarser run's particles, then the median over chromosomes of the Pearson r between the
  distance matrices of fine-averaged and coarse models (best model pair), and between the coarse
  run's own models (ceiling).

    python benchmarks/fig3/nucdyn_sanity.py RUN_DIR --cell 1 [--coarse COARSE_RUN_DIR] --out x.json
"""

from __future__ import annotations

import argparse
import gzip
import json
import sys
from pathlib import Path

import numpy as np
from scipy.spatial import cKDTree

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _nucdyn_env import geo_pairs, print_environment  # noqa: E402


def load(run: Path, cell: int):
    if run.suffix == ".gz":                                   # GEO extended PDB (published models)
        from a_nucdyn_engine_score import read_pdb
        return read_pdb(run)
    z = np.load(run / f"cell{cell}.npz")
    chrom = z["chrom"].astype(str)
    pos = z["pos"].astype(np.int64)
    return chrom, pos, z["coords"]


def particle_index(chrom, pos, size):
    """(chrom, genomic position) -> particle index; particle k covers (pos_k - size, pos_k]."""
    idx = {}
    for c in np.unique(chrom):
        sel = np.where(chrom == c)[0]
        order = sel[np.argsort(pos[sel])]
        idx[c] = (pos[order], order)
    def lookup(c, p):
        if c not in idx:
            return -1
        ps, order = idx[c]
        k = np.searchsorted(ps, p, side="left")
        return int(order[k]) if k < len(ps) and ps[k] - size < p <= ps[k] else -1
    return lookup


def contacts(cell: int):
    out = []
    with gzip.open(geo_pairs(cell), "rt") as fh:
        for line in fh:
            f = line.split()
            if len(f) < 4 or not f[1].lstrip("-").isdigit():
                continue
            a, b = f[0], f[2]
            a = a if a.startswith("chr") else "chr" + a
            b = b if b.startswith("chr") else "chr" + b
            out.append((a, int(f[1]), b, int(f[3])))
    return out


def model_checks(chrom, pos, X, pairs):
    same = chrom[1:] == chrom[:-1]
    bonds = np.linalg.norm(X[1:] - X[:-1], axis=1)[same]
    tree = cKDTree(X)
    d, j = tree.query(X, k=4)
    idx = np.arange(len(X))[:, None]
    nonbonded = ~((np.abs(j - idx) < 2) & (chrom[j] == chrom[:, None]))
    nonbonded[:, 0] = False                                    # self
    nn = np.where(nonbonded, d, np.inf).min(axis=1)
    nn = nn[np.isfinite(nn)]
    pd = np.linalg.norm(X[pairs[:, 0]] - X[pairs[:, 1]], axis=1)
    return {
        "bond_median": float(np.median(bonds)), "bond_p99": float(np.percentile(bonds, 99)),
        "bond_max": float(bonds.max()), "bond_gt3_pct": float(100 * (bonds > 3).mean()),
        "nn_nonbonded_p1": float(np.percentile(nn, 1)), "nn_nonbonded_median": float(np.median(nn)),
        "contact_gt2_pct": float(100 * (pd > 2).mean()), "contact_gt4_pct": float(100 * (pd > 4).mean()),
        "contact_gt6_pct": float(100 * (pd > 6).mean()), "contact_median": float(np.median(pd)),
    }


def block_mean(chrom, pos, X, cchrom, cpos, csize):
    look = particle_index(cchrom, cpos, csize)
    tgt = np.array([look(c, p) for c, p in zip(chrom, pos)])
    ok = tgt >= 0
    n = len(cchrom)
    out = np.zeros((X.shape[0], n, 3))
    cnt = np.bincount(tgt[ok], minlength=n).astype(float)
    for m in range(X.shape[0]):
        for k in range(3):
            out[m, :, k] = np.bincount(tgt[ok], weights=X[m, ok, k], minlength=n)
    with np.errstate(invalid="ignore"):
        out /= cnt[None, :, None]
    return out, cnt > 0


def dist_r(A, B, chrom, rng, n=20000):
    rs = []
    for c in np.unique(chrom):
        sel = np.where(chrom == c)[0]
        if len(sel) < 10:
            continue
        i = rng.choice(sel, n); j = rng.choice(sel, n)
        m = i != j
        rs.append(np.corrcoef(np.linalg.norm(A[i[m]] - A[j[m]], axis=1),
                              np.linalg.norm(B[i[m]] - B[j[m]], axis=1))[0, 1])
    return float(np.median(rs))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("run", type=Path, help="run directory with cell<n>.npz, or a GEO *.pdb.gz")
    ap.add_argument("--cell", type=int, default=1)
    ap.add_argument("--coarse", type=Path)
    ap.add_argument("--out", type=Path)
    args = ap.parse_args()
    env = print_environment("sanity")
    chrom, pos, X = load(args.run, args.cell)
    size = int(np.median(np.diff(np.sort(pos[chrom == chrom[0]]))))
    look = particle_index(chrom, pos, size)
    pr = np.array([(look(a, p), look(b, q)) for a, p, b, q in contacts(args.cell)])
    pr = pr[(pr >= 0).all(1)]
    pr = pr[(chrom[pr[:, 0]] != chrom[pr[:, 1]]) | (np.abs(pr[:, 0] - pr[:, 1]) >= 2)]
    pr = np.unique(np.sort(pr, axis=1), axis=0)
    res = {"run": str(args.run), "cell": args.cell, "particle_size": size, "n_particles": int(len(chrom)),
           "n_models": int(X.shape[0]), "n_contact_pairs": int(len(pr)), "env": env,
           "models": [model_checks(chrom, pos, X[m], pr) for m in range(X.shape[0])]}
    res["summary"] = {k: float(np.mean([m[k] for m in res["models"]])) for k in res["models"][0]}
    if args.coarse:
        cc, cp, CX = load(args.coarse, args.cell)
        csize = int(np.median(np.diff(np.sort(cp[cc == cc[0]]))))
        F, ok = block_mean(chrom, pos, X, cc, cp, csize)
        rng = np.random.default_rng(0)
        cross = [dist_r(F[a][ok], CX[b][ok], cc[ok], rng) for a in range(min(3, len(F))) for b in range(min(3, len(CX)))]
        within = [dist_r(CX[a][ok], CX[b][ok], cc[ok], rng) for a in range(3) for b in range(a + 1, 3)]
        res["cross_resolution"] = {"coarse_run": str(args.coarse), "coarse_size": csize,
                                   "fine_vs_coarse_dist_r_best": float(max(cross)),
                                   "fine_vs_coarse_dist_r_mean": float(np.mean(cross)),
                                   "coarse_vs_coarse_dist_r_mean": float(np.mean(within))}
    print(json.dumps({k: v for k, v in res.items() if k not in ("models", "env")}, indent=1))
    if args.out:
        args.out.write_text(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
