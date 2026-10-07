"""Score NucDynamics ensembles of the 8 Stevens et al. 2017 cells (Fig. 3a).

Reads the model files written by ``a_nucdyn_engine_run.py`` (``cell<n>.npz``:
``chrom``, ``pos`` = particle sequence position in the original's convention,
``coords`` (models, particles, 3) in particle radii) and the paper's
deposited 100 kb models (GEO GSE80280, ``<GSM>_Cell_<n>_genome_structure_model.pdb.gz``,
10 models per cell), and reports per cell:

* **precision** (the paper's metric, Extended Data Table 2): mean pairwise
  all-particle RMSD between the models after optimal superposition, without
  (``rmsd_pair_mean``) and with mirror images allowed
  (``rmsd_pair_mirror_mean``), and the RMSD of the models to the
  superposed ensemble mean;
* **vs published**: particles matched by chromosome and sequence position;
  every model vs every GEO model: RMSD (best of mirror) and the median over
  chromosomes of the Pearson r between distance matrices; the same for GEO
  vs GEO (ceiling);
* **restraint violations**: the cell's GEO contacts binned onto the
  ensemble's particles (a contact end at p goes to the first particle with
  position >= p); pairs of non-adjacent particles with n contacts get
  d_upper = 1.2 n^-0.33; ``pct_viol_gt3`` / ``pct_viol_gt4`` = share of such
  restraints with d > d_upper + 3 / 4 radii, mean over models (ED Table 2's
  %V>3 / %V>4);

next to the paper's ED Table 2 rows (``100kb_unambig``: the 100 kb stage of
the protocol the 2017 code implements; ``100kb_final``: after the paper's
extra round with ambiguous contacts, = the GEO models).  The same metrics are
computed for the GEO models themselves.

Usage::

    python benchmarks/fig3/a_nucdyn_engine_score.py --runs RUN_DIR [RUN_DIR ...] --labels cpu gpu \\
        --cells 1-8 --out u-chrom-paper/manuscripts/full/figures/fig3/results/a_nucdyn_engine_validation.json
"""

from __future__ import annotations

from uchrom.datasets import data_dir
import argparse
import gzip
import itertools
import json
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
GEO_DIR = data_dir() / "stevens2017_mesc"
GSM = {1: "GSM2219497", 2: "GSM2219498", 3: "GSM2219499", 4: "GSM2219500",
       5: "GSM2219501", 6: "GSM2219502", 7: "GSM2219503", 8: "GSM2219504"}
CHAINS = {chr(ord("a") + i): f"chr{i + 1}" for i in range(19)} | {"t": "chrX"}
SIZE = 100_000

# Stevens et al. 2017, Extended Data Table 2 (RMSD radii, N_rest, %V>3, %V>4)
ED_TABLE2 = {
    "100kb_unambig": {1: (0.56, 71729, 2.81, 0.57), 2: (0.88, 47598, 1.04, 0.15), 3: (0.89, 22822, 4.82, 1.36),
                      4: (1.03, 50516, 2.49, 0.94), 5: (1.08, 44298, 2.12, 0.73), 6: (1.09, 44687, 0.99, 0.22),
                      7: (1.91, 33588, 0.11, 0.01), 8: (1.52, 28083, 0.02, 0.02)},
    "100kb_final": {1: (0.41, 74945, 2.29, 0.22), 2: (0.63, 56159, 0.74, 0.13), 3: (0.70, 25952, 2.87, 0.42),
                    4: (0.74, 60420, 1.14, 0.17), 5: (0.86, 51824, 1.24, 0.21), 6: (0.91, 53710, 0.74, 0.17),
                    7: (1.75, 39257, 0.13, 0.02), 8: (1.26, 32482, 0.03, 0.02)},
}


def parse_cells(s: str) -> list[int]:
    out = []
    for part in s.split(","):
        a, _, b = part.partition("-")
        out.extend(range(int(a), int(b or a) + 1))
    return out


def read_pdb(path: Path):
    """GEO extended PDB -> chrom (N), pos (N), coords (M, N, 3)."""
    models, rows, keys = [], [], None
    with gzip.open(path, "rt") as fh:
        for line in fh:
            if line.startswith("MODEL"):
                rows = []
            elif line.startswith("HETATM"):
                rows.append((CHAINS.get(line[21], line[21]), int(line.split()[-1]),
                             float(line[30:38]), float(line[38:46]), float(line[46:54])))
            elif line.startswith("ENDMDL"):
                k = [(r[0], r[1]) for r in rows]
                if keys is None:
                    keys = k
                if k != keys:
                    raise ValueError("published models have different particles")
                models.append(np.array([r[2:] for r in rows]))
    chrom = np.array([k[0] for k in keys])
    pos = np.array([k[1] for k in keys], np.int64)
    return chrom, pos, np.stack(models)


def read_pairs(path: Path):
    ca, pa, cb, pb = [], [], [], []
    with gzip.open(path, "rt") as fh:
        for line in fh:
            if line.startswith("#"):
                continue
            r = line.split()
            ca.append(r[0]); pa.append(int(r[1])); cb.append(r[2]); pb.append(int(r[3]))
    return np.array(ca), np.array(pa, np.int64), np.array(cb), np.array(pb, np.int64)


def kabsch(a: np.ndarray, b: np.ndarray, mirror: bool) -> float:
    """RMSD of b superposed on a (rotation; with mirror: best of b and -b)."""
    a = a - a.mean(0)
    b = b - b.mean(0)
    best = np.inf
    for s in ((1.0, -1.0) if mirror else (1.0,)):
        bb = b * s
        u, _, vt = np.linalg.svd(bb.T @ a)
        d = np.sign(np.linalg.det(u @ vt))
        r = u @ np.diag([1.0, 1.0, d]) @ vt
        best = min(best, float(np.sqrt(((bb @ r - a) ** 2).sum(1).mean())))
    return best


def superpose_mean(X: np.ndarray, n_iter: int = 3, mirror: bool = False):
    """Iteratively superpose models on their mean (rotation only); RMSD to the mean.
    With ``mirror``, each model is first replaced by its mirror image if that fits model 0 better."""
    Y = X - X.mean(1, keepdims=True)
    if mirror:
        for k in range(1, len(Y)):
            if kabsch(Y[0], -Y[k], False) < kabsch(Y[0], Y[k], False):
                Y[k] = -Y[k]
    ref = Y[0]
    for _ in range(n_iter):
        for k in range(len(Y)):
            u, _, vt = np.linalg.svd(Y[k].T @ ref)
            d = np.sign(np.linalg.det(u @ vt))
            Y[k] = Y[k] @ (u @ np.diag([1.0, 1.0, d]) @ vt)
        ref = Y.mean(0)
    return np.sqrt(((Y - ref) ** 2).sum(2).mean(1))


def match(chrom_a, pos_a, chrom_b, pos_b):
    """Indices (ia, ib) of particles present in both sets (same chrom and position)."""
    ka = {(c, p): i for i, (c, p) in enumerate(zip(chrom_a, pos_a))}
    ia, ib = [], []
    for j, (c, p) in enumerate(zip(chrom_b, pos_b)):
        i = ka.get((c, p))
        if i is not None:
            ia.append(i)
            ib.append(j)
    return np.array(ia), np.array(ib)


def dist_r_matrix(sets, chrom):
    """Median over chromosomes of Pearson r between distance matrices, for all pairs of models in `sets`
    (list of (M_k, N, 3) arrays on the same particles)."""
    models = np.concatenate(sets)
    n_models = len(models)
    rs = {pair: [] for pair in itertools.combinations(range(n_models), 2)}
    for c in np.unique(chrom):
        idx = np.flatnonzero(chrom == c)
        if len(idx) < 10:
            continue
        iu = np.triu_indices(len(idx), 1)
        vecs = []
        for m in models:
            x = m[idx]
            d = np.sqrt(((x[:, None] - x[None]) ** 2).sum(-1))[iu].astype(np.float32)
            d = (d - d.mean()) / d.std()
            vecs.append(d)
        V = np.stack(vecs)
        C = (V @ V.T) / V.shape[1]
        for (a, b) in rs:
            rs[(a, b)].append(float(C[a, b]))
    return {pair: float(np.median(v)) for pair, v in rs.items()}


def violations(chrom, pos, X, ca, pa, cb, pb):
    """%V>3, %V>4 (mean over models) and N_rest, ED Table 2 definition."""
    order = {}
    for c in np.unique(chrom):
        idx = np.flatnonzero(chrom == c)
        order[c] = (idx, pos[idx])

    def particle(cs, ps):
        out = np.full(len(ps), -1)
        for c, (idx, pp) in order.items():
            sel = cs == c
            if not sel.any():
                continue
            k = np.searchsorted(pp, ps[sel], side="left")
            ok = k < len(pp)
            tmp = np.full(sel.sum(), -1)
            tmp[ok] = idx[k[ok]]
            out[sel] = tmp
        return out

    i = particle(ca, pa)
    j = particle(cb, pb)
    ok = (i >= 0) & (j >= 0)
    i, j = np.minimum(i[ok], j[ok]), np.maximum(i[ok], j[ok])
    same = chrom[i] == chrom[j]
    keep = ~same | (j - i >= 2)
    pairs, counts = np.unique(np.stack([i[keep], j[keep]], 1), axis=0, return_counts=True)
    dup = 1.2 * counts.astype(float) ** -0.33
    v3, v4 = [], []
    for m in X:
        d = np.linalg.norm(m[pairs[:, 0]] - m[pairs[:, 1]], axis=1)
        v3.append(100.0 * np.mean(d > dup + 3.0))
        v4.append(100.0 * np.mean(d > dup + 4.0))
    return float(np.mean(v3)), float(np.mean(v4)), int(len(pairs))


def precision(X):
    pair = [kabsch(X[a], X[b], False) for a, b in itertools.combinations(range(len(X)), 2)]
    pair_m = [kabsch(X[a], X[b], True) for a, b in itertools.combinations(range(len(X)), 2)]
    to_mean = superpose_mean(X.copy())
    to_mean_m = superpose_mean(X.copy(), mirror=True)
    n_mirrored = sum(kabsch(X[0], -X[k], False) < kabsch(X[0], X[k], False) for k in range(1, len(X)))
    return {
        "rmsd_pair_mean": float(np.mean(pair)),
        "rmsd_pair_sem": float(np.std(pair) / np.sqrt(len(pair))),
        "rmsd_pair_mirror_mean": float(np.mean(pair_m)),
        "rmsd_pair_mirror_sem": float(np.std(pair_m) / np.sqrt(len(pair_m))),
        "rmsd_to_mean_mean": float(np.mean(to_mean)),
        "rmsd_to_mean_mirror_mean": float(np.mean(to_mean_m)),
        "n_models_mirror_of_model0": int(n_mirrored),
    }


def score_cell(cell, runs, labels, geo_dir):
    ch_p, pos_p, Xp = read_pdb(geo_dir / f"{GSM[cell]}_Cell_{cell}_genome_structure_model.pdb.gz")
    ca, pa, cb, pb = read_pairs(geo_dir / f"{GSM[cell]}_Cell_{cell}_contact_pairs.txt.gz")
    out = {"cell": cell, "ed_table2": {k: dict(zip(("rmsd", "n_rest", "pct_v3", "pct_v4"), v[cell]))
                                       for k, v in ED_TABLE2.items()}}
    pub = {"n_models": int(len(Xp)), "n_particles": int(Xp.shape[1])}
    pub.update(precision(Xp))
    v3, v4, nr = violations(ch_p, pos_p, Xp, ca, pa, cb, pb)
    pub.update({"pct_viol_gt3": v3, "pct_viol_gt4": v4, "n_rest": nr})
    out["published"] = pub
    for run, label in zip(runs, labels):
        f = Path(run) / f"cell{cell}.npz"
        if not f.exists():
            continue
        z = np.load(f, allow_pickle=True)
        chrom, pos, X = z["chrom"].astype(str), z["pos"].astype(np.int64), z["coords"].astype(float)
        res = {"n_models": int(len(X)), "n_particles": int(X.shape[1])}
        meta = Path(run) / f"cell{cell}.json"
        if meta.exists():
            m = json.loads(meta.read_text())
            res.update({"device": m.get("device"), "wall_seconds": m.get("wall_seconds"),
                        "peak_rss_mb": m.get("peak_rss_mb")})
        res.update(precision(X))
        v3, v4, nr = violations(chrom, pos, X, ca, pa, cb, pb)
        res.update({"pct_viol_gt3": v3, "pct_viol_gt4": v4, "n_rest": nr})
        ia, ib = match(chrom, pos, ch_p, pos_p)
        res["n_matched_particles"] = int(len(ia))
        Xa, Xb = X[:, ia], Xp[:, ib]
        rm = [kabsch(Xb[b], Xa[a], True) for a in range(len(Xa)) for b in range(len(Xb))]
        res["vs_published_rmsd_mirror_mean"] = float(np.mean(rm))
        res["vs_published_rmsd_mirror_median"] = float(np.median(rm))
        rr = dist_r_matrix([Xa, Xb], ch_p[ib])
        na = len(Xa)
        cross = [v for (a, b), v in rr.items() if a < na <= b]
        own = [v for (a, b), v in rr.items() if a < na and b < na]
        pp = [v for (a, b), v in rr.items() if a >= na]
        res["vs_published_dist_r_median"] = float(np.median(cross))
        res["own_models_dist_r_median"] = float(np.median(own))
        pub.setdefault("pub_vs_pub_dist_r_median", float(np.median(pp)))
        pub.setdefault("pub_vs_pub_rmsd_mirror_mean",
                       float(np.mean([kabsch(Xb[a], Xb[b], True) for a, b in itertools.combinations(range(len(Xb)), 2)])))
        out[label] = res
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--runs", nargs="+", required=True)
    ap.add_argument("--labels", nargs="+")
    ap.add_argument("--cells", default="1-8")
    ap.add_argument("--geo-dir", type=Path, default=GEO_DIR)
    ap.add_argument("--out", type=Path)
    args = ap.parse_args()
    labels = args.labels or [Path(r).name for r in args.runs]
    results = []
    for cell in parse_cells(args.cells):
        r = score_cell(cell, args.runs, labels, args.geo_dir)
        results.append(r)
        brief = {k: {kk: (round(vv, 3) if isinstance(vv, float) else vv) for kk, vv in v.items()}
                 for k, v in r.items() if isinstance(v, dict) and k != "ed_table2"}
        print(json.dumps({"cell": cell, **brief}), flush=True)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps({"cells": results, "labels": labels}, indent=1))


if __name__ == "__main__":
    main()
