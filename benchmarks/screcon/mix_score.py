"""Scoring of the few-cell deconvolution benchmark (PREREG §12).

    python benchmarks/screcon/mix_score.py --pool POOL.txt.gz --models RUN/mix.npz RUN/igm.npz RUN/naive.npz \\
        --labels mix igm naive [--refs RUN/oracle.npz] --out SCORE.json

The pool's ``.origin.npz`` (cell of origin per row, noise flag for simulations) and ``.json`` (truth
files of a simulated pool) sit next to the table.  References: simulated pools -> the imaging truths
(measured loci); real pools -> ``--refs`` (the per-cell EMber runs, ``run_mix.py --method oracle``;
``model_cell`` = cell index in pool order) on a 1 Mb grid of bin midpoints.

* Evaluation pairs: up to ``--n-pairs`` (200,000) locus pairs drawn once per pool (seed 0) among the
  evaluation loci (sims: the truth loci; real: the 1 Mb grid bins covered by every reference cell);
  a recovered cell's distance = mean over its replicate models; Spearman r per (recovered, true) cell
  over the pairs finite in both.
* Matching: Hungarian on that r (one to one); ``oracle`` runs keep their own cell order.
* **M2** = mean over true cells of the matched r (``whole``; also ``cis``); a method with one structure
  (naive) scores every true cell against it.
* **M1** = fraction of all pooled rows whose most probable cell (``cell_probs``; rows a method cannot
  place count as wrong) is matched to the row's true cell; also by separation (cis < 2 Mb, 2-20 Mb,
  > 20 Mb, trans), signal rows only (sims), and with the ``closest`` rule (the cell whose structure
  places the row's ends closest) for every method with more than one structure.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
from scipy import stats
from scipy.optimize import linear_sum_assignment

sys.path.insert(0, str(Path(__file__).resolve().parent))
from contacts import ParticleIndex, read_contacts  # noqa: E402
from truth import load_truth  # noqa: E402

SEP_BANDS = [("cis_lt2mb", 0, 2_000_000), ("cis_2_20mb", 2_000_000, 20_000_000), ("cis_gt20mb", 20_000_000, None)]


def pool_files(pool: str):
    base = pool[:-7] if pool.endswith(".txt.gz") else pool.rsplit(".", 1)[0]
    origin = np.load(base + ".origin.npz", allow_pickle=True)
    meta = json.loads(Path(base + ".json").read_text())
    return origin, meta


def eval_loci_sim(meta):
    truths = [load_truth(Path(meta["truth_dir"]) / f) for f in meta["truths"]]
    t0 = truths[0]
    chrom, start, end = t0["chrom"], t0["start"], t0["end"]
    mid = (start + end) // 2
    T = [np.where(t["measured"][:, None], t["coords"], np.nan) for t in truths]
    return chrom, mid, T


def eval_loci_real(ref_path, res=1_000_000):
    """1 Mb grid bins (midpoints) covered by the reference particles; per true cell its models on them."""
    z = np.load(ref_path, allow_pickle=True)
    chrom, pos, X, mc = z["chrom"].astype(str), z["pos"].astype(np.int64), np.asarray(z["coords"], float), z["model_cell"]
    k = int(mc.max()) + 1
    pidx = ParticleIndex(chrom, pos)
    gc, gm = [], []
    for ch in np.unique(chrom):
        p = pos[chrom == ch]
        for b in range(int(p.min() // res), int(p.max() // res) + 1):
            gc.append(ch); gm.append(b * res + res // 2)
    gc, gm = np.array(gc), np.array(gm, np.int64)
    ii = pidx(gc, gm)
    keep = ii >= 0
    gc, gm, ii = gc[keep], gm[keep], ii[keep]
    return gc, gm, [X[mc == s][:, ii] for s in range(k)]


def pair_sample(n_loci, n_pairs, seed=0):
    rng = np.random.default_rng(seed)
    tot = n_loci * (n_loci - 1) // 2
    if tot <= n_pairs:
        iu = np.triu_indices(n_loci, 1)
        return iu[0], iu[1]
    a = rng.integers(0, n_loci, 2 * n_pairs)
    b = rng.integers(0, n_loci, 2 * n_pairs)
    ok = a != b
    a, b = np.minimum(a[ok], b[ok]), np.maximum(a[ok], b[ok])
    key = np.unique(a.astype(np.int64) * n_loci + b)[:n_pairs]
    rng.shuffle(key)
    return key // n_loci, key % n_loci


def cell_dists(X_models: np.ndarray, li: np.ndarray, a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Mean over models of the distance of loci pairs (a, b); li = particle per locus (-1 = none)."""
    ok = (li[a] >= 0) & (li[b] >= 0)
    d = np.full(len(a), np.nan)
    if ok.any():
        d[ok] = np.linalg.norm(X_models[:, li[a[ok]]] - X_models[:, li[b[ok]]], axis=2).mean(0)
    return d


def spearman(x, y) -> float:
    ok = np.isfinite(x) & np.isfinite(y)
    if ok.sum() < 10:
        return np.nan
    return float(stats.spearmanr(x[ok], y[ok]).statistic)


def row_sep(c) -> np.ndarray:
    cis = c.chrom_a == c.chrom_b
    return np.where(cis, np.abs(c.pos_a - c.pos_b), -1)


def end_candidates(chrom, pos, cchrom, cpos) -> list:
    """Particle index arrays of contact ends (``cchrom``, ``cpos``) on the model's chains: one array for
    haploid models; for copy chains (``chr1(0)`` / ``chr1(1)``) one per copy (-1 = none)."""
    chrom = np.asarray(chrom).astype(str)
    pidx = ParticleIndex(chrom, pos)
    cchrom = np.asarray(cchrom).astype(str)
    if not any("(" in x for x in np.unique(chrom)):
        return [pidx(cchrom, cpos)]
    out = []
    for h in (0, 1):
        names = np.char.add(np.char.add(cchrom, f"({h})"), "")
        idx = pidx(names, cpos)
        plain = pidx(cchrom, cpos)                 # single-copy chromosomes keep the plain name
        out.append(np.where(idx >= 0, idx, plain))
    return out


def closest_assign(c, chrom, pos, X, model_cell):
    """Cell whose (replicate-mean) structure places the row's ends closest (copy chains: the closest
    copy pair)."""
    ca = end_candidates(chrom, pos, c.chrom_a, c.pos_a)
    cb = end_candidates(chrom, pos, c.chrom_b, c.pos_b)
    cells = np.unique(model_cell)
    D = np.full((len(c.pos_a), len(cells)), np.inf)
    for q, s in enumerate(cells):
        Xs = X[model_cell == s]
        for ia in ca:
            for ib in cb:
                ok = (ia >= 0) & (ib >= 0)
                d = np.full(len(ia), np.inf)
                d[ok] = np.linalg.norm(Xs[:, ia[ok]] - Xs[:, ib[ok]], axis=2).mean(0)
                D[:, q] = np.minimum(D[:, q], d)
    pred = cells[np.argmin(D, 1)]
    pred[~np.isfinite(D).any(1)] = -1
    return pred


def accuracy_table(pred_true, origin, sep, noise=None) -> dict:
    """pred_true: predicted true cell per row (-1 = none)."""
    ok = pred_true == origin
    out = {"all": float(ok.mean()), "assigned": float((pred_true >= 0).mean())}
    for name, lo, hi in SEP_BANDS:
        sel = (sep >= lo) & ((sep < hi) if hi else True)
        out[name] = float(ok[sel].mean()) if sel.any() else None
    sel = sep < 0
    out["trans"] = float(ok[sel].mean()) if sel.any() else None
    if noise is not None:
        out["signal"] = float(ok[~noise].mean()) if (~noise).any() else None
    return out


def score(pool, models, labels, refs=None, n_pairs=200_000, real_res=1_000_000) -> dict:
    origin, meta = pool_files(pool)
    cell = np.asarray(origin["cell"], np.int64)
    noise = np.asarray(origin["noise"], bool) if "noise" in origin.files else None
    k = len(origin["cells"])
    c = read_contacts(pool)
    sep = row_sep(c)
    if refs:
        chrom, mid, T = eval_loci_real(refs, real_res)        # T[t]: (models, loci, 3)
        kind = "real"
    else:
        chrom, mid, T = eval_loci_sim(meta)                   # T[t]: (loci, 3), NaN = not measured
        T = [t[None] for t in T]
        kind = "sim"
    a, b = pair_sample(len(chrom), n_pairs)
    cis = chrom[a] == chrom[b]
    Dt = [np.linalg.norm(t[:, a] - t[:, b], axis=2).mean(0) for t in T]
    out = {"pool": pool, "kind": kind, "k": k, "n_rows": int(len(c)), "n_eval_loci": int(len(chrom)),
           "n_pairs": int(len(a)), "meta": {x: meta.get(x) for x in ("name", "k", "pool", "depth", "eps", "set", "dataset")},
           "methods": {}}
    for path, lab in zip(models, labels):
        if not Path(path).exists():
            out["methods"][lab] = {"missing": str(path)}
            continue
        z = np.load(path, allow_pickle=True)
        X = np.asarray(z["coords"], float)
        mchrom, mpos = z["chrom"].astype(str), z["pos"].astype(np.int64)
        mc = np.asarray(z["model_cell"], np.int64) if "model_cell" in z.files else np.zeros(len(X), np.int64)
        li = ParticleIndex(mchrom, mpos)(chrom, mid)
        cells = np.unique(mc)
        Dm = [cell_dists(X[mc == s], li, a, b) for s in cells]
        R = np.array([[spearman(d, t) for t in Dt] for d in Dm])
        Rc = np.array([[spearman(d[cis], t[cis]) for t in Dt] for d in Dm])
        res = {"n_cells_recovered": int(len(cells)), "coverage": float((li >= 0).mean()), "r_matrix": np.round(R, 4).tolist()}
        if len(cells) == 1:
            match = np.zeros(k, np.int64)                         # every true cell vs the one structure
            res["M2"] = float(np.nanmean(R[0]))
            res["M2_cis"] = float(np.nanmean(Rc[0]))
            res["per_cell_r"] = R[0].tolist()
        else:
            if lab.startswith("oracle") or "oracle" in Path(path).stem:
                rows = cols = np.arange(min(len(cells), k))
            else:
                rows, cols = linear_sum_assignment(np.nan_to_num(R, nan=-1.0), maximize=True)
            match = np.full(len(cells), -1, np.int64)
            match[rows] = cols
            per = np.full(k, np.nan)
            per_c = np.full(k, np.nan)
            per[cols] = R[rows, cols]
            per_c[cols] = Rc[rows, cols]
            res["M2"] = float(np.nanmean(per))
            res["M2_cis"] = float(np.nanmean(per_c))
            res["per_cell_r"] = per.tolist()
            res["matching"] = match.tolist()
            # assignment: own posteriors, and the closest-structure rule
            if "cell_probs" in z.files:
                P = np.asarray(z["cell_probs"], float)
                okp = np.isfinite(P).all(1)
                best = np.where(okp, np.argmax(np.nan_to_num(P, nan=-1.0), 1), -1)
                pred = np.where(best >= 0, match[np.clip(best, 0, None)], -1)
                res["M1"] = accuracy_table(pred, cell, sep, noise)
                res["M1_confident_frac"] = float((np.nan_to_num(P).max(1) >= 0.9).mean())
            pc = closest_assign(c, mchrom, mpos, X, mc)
            idx = np.searchsorted(cells, pc.clip(0))
            pred_c = np.where(pc >= 0, match[idx.clip(0, len(cells) - 1)], -1)
            res["M1_closest"] = accuracy_table(pred_c, cell, sep, noise)
            if "M1" not in res:
                res["M1"] = res["M1_closest"]
        jp = Path(str(path) + ".json")
        if jp.exists():
            mj = json.loads(jp.read_text())
            res["wall_seconds"] = mj.get("wall_seconds")
        out["methods"][lab] = res
    return out


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pool", required=True)
    ap.add_argument("--models", nargs="+", required=True)
    ap.add_argument("--labels", nargs="+")
    ap.add_argument("--refs", help="real pools: per-cell reference runs (.npz, model_cell = pool order)")
    ap.add_argument("--n-pairs", type=int, default=200_000)
    ap.add_argument("--out")
    args = ap.parse_args(argv)
    labels = args.labels or [Path(m).stem for m in args.models]
    res = score(args.pool, args.models, labels, args.refs, args.n_pairs)
    brief = {lab: {"M2": round(r.get("M2", np.nan), 4), "M1": round(r.get("M1", {}).get("all", np.nan), 4)
                   if isinstance(r.get("M1"), dict) else None} for lab, r in res["methods"].items() if "missing" not in r}
    print(json.dumps({"pool": Path(args.pool).name, **brief}))
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
