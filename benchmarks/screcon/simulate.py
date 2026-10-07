"""Imaging-truth simulation benchmark: truth structure -> simulated single-cell Hi-C -> score.

Subcommands
-----------
``truth``   Extract truth cells from chromatin tracing data (see ``truth.py``) and a
            population summary of the *other* cells (for the structure-free baselines)::

                python benchmarks/screcon/simulate.py truth --dataset su2020_chr21 --n 5 --out SIM/su21

``reads``   Forward model, truth -> reads in the Stevens GEO format (``chr_A pos_A chr_B pos_B``)::

                python benchmarks/screcon/simulate.py reads --truth SIM/su21/truth_1.npz \\
                    --reads-per-mb 40 --rc-rel 1.0 --eps 0.05 --seed 1 --out SIM/su21/reads/...txt.gz

            * contact propensity of loci i != j at 3-D distance d: ``kernel``
              ``gauss``: f(d) = exp(-(d / rc)^2) (default); ``step``: 1[d < rc];
              ``sigmoid``: 1 / (1 + exp((d - rc) / (0.1 rc))).  The contact probability is
              p(d) = q f(d), q = capture efficiency.
            * depth: ``--reads N`` or ``--reads-per-mb x`` (N = x times the total span of the
              truth loci in Mb) fixes the total; the signal reads (1 - eps) N are then drawn
              multinomially over locus pairs with probabilities proportional to p(d) (q cancels).
              Without a depth, every pair gets Poisson(q f(d)) reads (q = expected reads of a
              pair at d = 0) and eps / (1 - eps) times as many noise reads are added.
            * noise: a fraction ``eps`` of the reads is placed uniformly at random over all
              locus pairs (cis and trans), modelling random ligation / mapping artefacts.
            * rc: ``--rc`` in nm, or ``--rc-rel r`` = r x the truth's median distance between
              consecutive loci (dataset-agnostic: 1.0 = "within one bead spacing").
            * each read's genomic positions are uniform integers in [start + 1, end - 1] of
              its loci (inside the locus under both the (pos - size, pos] and the
              [start, end) particle conventions).
            * missing loci: interpolated along the chain (``--missing interp``, default) or
              given no reads (``drop``); see ``truth.py``.
            A JSON sidecar records every parameter and the realised read counts.

``grid``    Writes the reads for a whole (depth x rc x eps x seed) grid.

``score``   Scores models (``.npz``) against the truth on the measured loci, plus the
            structure-free baselines, per model and for the ensemble:
            * loci -> particles by genomic midpoint (particle covers (pos - size, pos]);
              loci whose particle is missing or already taken by another locus are dropped
              (``n_loci_scored`` / ``coverage``);
            * ``rmsd_nm``: RMSD after the optimal similarity superposition (rotation,
              translation, least-squares scale, mirror allowed) of the model onto the truth,
              i.e. the model in truth units; ``rmsd_rel`` = rmsd_nm / Rg(truth) (scale-free);
              ``rmsd_rel_chrom_median``: the same per chromosome (median);
            * ``dist_r``: Pearson and Spearman r between model and truth distance matrices
              over all loci pairs (``whole``) and same-chromosome pairs (``cis``);
            * ensemble: the same for the ensemble-mean distance matrix, and the RMSD of the
              superposed ensemble mean structure;
            * baselines: ``pop_mean`` (mean distance of every loci pair over the other
              imaged cells), ``pop_ps`` (population mean distance as a function of genomic
              separation only; trans pairs get the mean trans distance), both as distance
              matrices, with a 3-D structure by classical MDS for the RMSD; and
              ``random_polymer`` (random walks, 10 models).  They give the floor
              (``random_polymer``) and a strong population prior (``pop_mean``).
"""

from __future__ import annotations

from uchrom.datasets import data_dir
import argparse
import itertools
import json
import sys
from pathlib import Path

import numpy as np
from scipy.spatial.distance import pdist, squareform

sys.path.insert(0, str(Path(__file__).resolve().parent))
from contacts import ParticleIndex, load_models, write_geo  # noqa: E402
from metrics import dist_matrix_r, superpose, superpose_ensemble  # noqa: E402
from truth import (interpolate_missing, load_truth, save_truth, su2020_truths,  # noqa: E402
                   takei1mb_truths, takei25kb_truths)

DATASETS = {
    "su2020_chr21": ("su2020_imr90/chromosome21.tsv", su2020_truths),
    "takei2021_25kb": ("4DNFIHF3JCBY.csv", takei25kb_truths),
    "takei2021_1mb": ("4DNFIFLJGGNR.csv", takei1mb_truths),
}


def example_data() -> Path:
    return data_dir()                       # $UCHROM_DATA, else ~/.cache/uchrom


# --------------------------------------------------------------------------- population summary

def population_summary(pop: np.ndarray, chrom, start, max_cells: int = 2000, seed: int = 0) -> dict:
    """Mean distance per loci pair over cells (NaN-aware) and a P(s)-style mean distance
    curve over log-spaced genomic separation bins (cis) plus the mean trans distance."""
    rng = np.random.default_rng(seed)
    if len(pop) > max_cells:
        pop = pop[np.sort(rng.choice(len(pop), max_cells, replace=False))]
    L = pop.shape[1]
    npair = L * (L - 1) // 2
    s = np.zeros(npair); n = np.zeros(npair)
    for X in pop:
        d = pdist(X)
        ok = np.isfinite(d)
        s[ok] += d[ok]; n[ok] += 1
    mean = np.where(n > 0, s / np.maximum(n, 1), np.nan)
    iu = np.triu_indices(L, 1)
    cis = chrom[iu[0]] == chrom[iu[1]]
    sep = np.abs(start[iu[1]] - start[iu[0]]).astype(float)
    edges = np.unique(np.concatenate([[0], np.logspace(3, 9, 61)]))
    b = np.digitize(sep, edges)
    curve = np.full(len(edges) + 1, np.nan)
    for k in np.unique(b[cis]):
        sel = cis & (b == k) & np.isfinite(mean)
        if sel.any():
            curve[k] = np.average(mean[sel], weights=n[sel])
    trans = (~cis) & np.isfinite(mean)
    trans_mean = float(np.average(mean[trans], weights=n[trans])) if trans.any() else np.nan
    ps = np.where(cis, curve[b], trans_mean)
    return {"pop_mean": mean, "pop_n": n, "pop_ps": ps, "ps_edges": edges, "ps_curve": curve,
            "trans_mean": trans_mean, "n_cells": int(len(pop))}


def cmd_truth(args) -> None:
    rel, fn = DATASETS[args.dataset]
    path = Path(args.data) if args.data else example_data() / rel
    kw = {"n": args.n, "seed": args.seed}
    if args.min_detect is not None:
        kw["min_detect"] = args.min_detect
    if args.dataset == "takei2021_1mb" and args.min_sep is not None:
        kw["min_sep"] = args.min_sep
    truths, pop = fn(path, **kw)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    for k, t in enumerate(truths, 1):
        filled, measured = interpolate_missing(t["chrom"], t["start"], t["coords"])
        t["meta"]["n_loci"] = int(len(t["chrom"]))
        t["meta"]["n_measured"] = int(measured.sum())
        t["meta"]["source"] = str(path)
        save_truth(out / f"truth_{k}.npz", t["chrom"], t["start"], t["end"], t["coords"], measured, t["meta"])
        print(json.dumps({k2: v for k2, v in t["meta"].items() if k2 not in ("chroms", "traces")}), flush=True)
    ps = population_summary(pop["population"], pop["chrom"], pop["start"], seed=args.seed)
    np.savez_compressed(out / "population.npz", chrom=pop["chrom"], start=pop["start"], end=pop["end"],
                        **{k: v for k, v in ps.items() if isinstance(v, np.ndarray)},
                        meta=json.dumps({"n_cells": ps["n_cells"], "trans_mean": ps["trans_mean"],
                                         "dataset": args.dataset, **pop.get("stats", {})}))
    print(f"population summary of {ps['n_cells']} other cells -> {out / 'population.npz'}")


# --------------------------------------------------------------------------- forward model

def kernel(d: np.ndarray, rc: float, kind: str = "gauss") -> np.ndarray:
    if kind == "gauss":
        return np.exp(-(d / rc) ** 2)
    if kind == "step":
        return (d < rc).astype(float)
    if kind == "sigmoid":
        return 1.0 / (1.0 + np.exp(np.clip((d - rc) / (0.1 * rc), -50, 50)))
    raise ValueError(kind)


def median_consecutive(chrom, coords) -> float:
    same = chrom[1:] == chrom[:-1]
    d = np.linalg.norm(np.diff(coords, axis=0), axis=1)[same]
    return float(np.nanmedian(d))


def genome_span_mb(chrom, start, end) -> float:
    return float(sum((end[chrom == c].max() - start[chrom == c].min()) for c in np.unique(chrom)) / 1e6)


def simulate_reads(t: dict, *, reads: int | None = None, reads_per_mb: float | None = None, q: float = 1.0,
                   rc: float | None = None, rc_rel: float | None = None, kind: str = "gauss", eps: float = 0.0,
                   seed: int = 0, missing: str = "interp"):
    """-> (chrom_a, pos_a, chrom_b, pos_b, info).  See module docstring."""
    rng = np.random.default_rng(seed)
    chrom, start, end = t["chrom"], t["start"], t["end"]
    X = np.asarray(t["coords"], float)
    filled, measured = interpolate_missing(chrom, start, X)
    usable = np.ones(len(chrom), bool) if missing == "interp" else measured
    unit = median_consecutive(chrom, np.where(measured[:, None], X, np.nan))
    if rc is None:
        rc = (rc_rel if rc_rel is not None else 1.0) * unit
    L = len(chrom)
    iu = np.triu_indices(L, 1)
    ok = usable[iu[0]] & usable[iu[1]]
    ia, ib = iu[0][ok], iu[1][ok]
    d = np.linalg.norm(filled[ia] - filled[ib], axis=1)
    p = q * kernel(d, rc, kind)
    if reads is None and reads_per_mb is not None:
        reads = int(round(reads_per_mb * genome_span_mb(chrom, start, end)))
    if reads is not None:
        n_noise = int(rng.binomial(reads, eps))
        n_sig = reads - n_noise
        cnt = rng.multinomial(n_sig, p / p.sum())
    else:
        cnt = rng.poisson(p)
        n_sig = int(cnt.sum())
        n_noise = int(rng.poisson(n_sig * eps / (1 - eps))) if eps < 1 else 0
    noise = rng.integers(0, len(ia), n_noise)
    pair = np.concatenate([np.repeat(np.arange(len(ia)), cnt), noise])
    is_noise = np.concatenate([np.zeros(int(cnt.sum()), bool), np.ones(n_noise, bool)])
    order = rng.permutation(len(pair))
    pair, is_noise = pair[order], is_noise[order]
    A, B = ia[pair], ib[pair]

    def draw(k):
        lo, hi = start[k] + 1, end[k] - 1
        return lo + (rng.random(len(k)) * (hi - lo + 1)).astype(np.int64)

    pa, pb = draw(A), draw(B)
    info = {"n_reads": int(len(pair)), "n_signal": int(cnt.sum()), "n_noise": int(n_noise), "eps": eps,
            "kernel": kind, "rc_nm": float(rc), "rc_rel": None if rc_rel is None else float(rc_rel),
            "median_consecutive_nm": unit, "q": q, "reads_requested": reads, "reads_per_mb": reads_per_mb,
            "genome_span_mb": genome_span_mb(chrom, start, end), "seed": seed, "missing": missing,
            "n_loci": int(L), "n_loci_usable": int(usable.sum()),
            "frac_cis": float(np.mean(chrom[A] == chrom[B])) if len(A) else None,
            "n_distinct_pairs": int(len(np.unique(pair)))}
    return chrom[A], pa, chrom[B], pb, info


def cmd_reads(args) -> None:
    t = load_truth(args.truth)
    ca, pa, cb, pb, info = simulate_reads(t, reads=args.reads, reads_per_mb=args.reads_per_mb, q=args.q,
                                          rc=args.rc, rc_rel=args.rc_rel, kind=args.kernel, eps=args.eps,
                                          seed=args.seed, missing=args.missing)
    write_geo(args.out, ca, pa, cb, pb)
    info["truth"] = str(args.truth)
    Path(str(args.out) + ".json").write_text(json.dumps(info, indent=1))
    print(json.dumps(info), flush=True)


def grid_name(depth, rc_rel, eps, seed) -> str:
    return f"d{depth:g}_rc{rc_rel:g}_e{eps:g}_s{seed}"


def cmd_grid(args) -> None:
    truths = sorted(Path(args.truth_dir).glob("truth_*.npz"))
    out = Path(args.out)
    for tp in truths:
        t = load_truth(tp)
        for depth, rcr, eps, seed in itertools.product(args.depths, args.rc_rels, args.eps, args.seeds):
            name = f"{tp.stem}_{grid_name(depth, rcr, eps, seed)}"
            f = out / f"{name}.txt.gz"
            if f.exists() and not args.overwrite:
                continue
            ca, pa, cb, pb, info = simulate_reads(t, reads_per_mb=depth, rc_rel=rcr, kind=args.kernel, eps=eps,
                                                  seed=seed, missing=args.missing)
            write_geo(f, ca, pa, cb, pb)
            info.update({"truth": str(tp), "name": name})
            Path(str(f) + ".json").write_text(json.dumps(info, indent=1))
            print(name, info["n_reads"], flush=True)


# --------------------------------------------------------------------------- scoring vs truth

def map_loci(t: dict, chrom, pos, measured_only: bool = True):
    """Truth locus -> particle (midpoint rule); -1 where missing / duplicate / unmeasured."""
    mid = (t["start"] + t["end"]) // 2
    p = ParticleIndex(chrom, pos)(t["chrom"], mid)
    if measured_only:
        p[~t["measured"]] = -1
    seen = set()
    for k in range(len(p)):
        if p[k] >= 0:
            if p[k] in seen:
                p[k] = -1
            else:
                seen.add(int(p[k]))
    return p


def classical_mds(D: np.ndarray) -> np.ndarray:
    """3-D embedding of a (square, NaN-free) distance matrix."""
    n = len(D)
    J = np.eye(n) - 1.0 / n
    with np.errstate(all="ignore"):      # spurious matmul warnings of macOS Accelerate
        B = -0.5 * J @ (D ** 2) @ J
    w, v = np.linalg.eigh(B)
    idx = np.argsort(w)[::-1][:3]
    return v[:, idx] * np.sqrt(np.maximum(w[idx], 0))


def rg(X) -> float:
    return float(np.sqrt(((X - X.mean(0)) ** 2).sum(1).mean()))


def structure_metrics(T: np.ndarray, Y: np.ndarray, chrom: np.ndarray) -> dict:
    """T truth (n, 3) nm, Y model (n, 3) on the same loci."""
    fit, r_abs, scale, mirrored = superpose(T, Y, scale=True, mirror=True)
    out = {"rmsd_nm": r_abs, "rmsd_rel": r_abs / rg(T), "scale_to_nm": scale, "mirrored": bool(mirrored)}
    per = []
    for c in np.unique(chrom):
        sel = chrom == c
        if sel.sum() >= 5:
            per.append(superpose(T[sel], Y[sel], scale=True, mirror=True)[1] / rg(T[sel]))
    out["rmsd_rel_chrom_median"] = float(np.median(per)) if per else None
    return out


def distance_metrics(Dt: np.ndarray, Dm: np.ndarray, cis: np.ndarray) -> dict:
    w = dist_matrix_r(Dt, Dm)
    out = {"dist_pearson_whole": w["pearson"], "dist_spearman_whole": w["spearman"], "n_pairs": w["n_pairs"]}
    if cis.any() and not cis.all():
        c = dist_matrix_r(Dt[cis], Dm[cis])
        out.update({"dist_pearson_cis": c["pearson"], "dist_spearman_cis": c["spearman"]})
    else:
        out.update({"dist_pearson_cis": w["pearson"], "dist_spearman_cis": w["spearman"]})
    return out


def score_ensemble(t: dict, chrom, pos, X) -> dict:
    p = map_loci(t, chrom, pos)
    use = np.flatnonzero(p >= 0)
    T = t["coords"][use]
    lc = t["chrom"][use]
    Dt = pdist(T)
    iu = np.triu_indices(len(use), 1)
    cis = lc[iu[0]] == lc[iu[1]]
    per = []
    Dsum = np.zeros_like(Dt)
    for m in range(len(X)):
        Y = X[m, p[use]]
        Dm = pdist(Y)
        Dsum += Dm
        per.append({**structure_metrics(T, Y, lc), **distance_metrics(Dt, Dm, cis)})
    res = {"n_models": int(len(X)), "n_loci_scored": int(len(use)),
           "coverage": float(len(use) / max(t["measured"].sum(), 1)), "per_model": per}
    keys = [k for k in per[0] if isinstance(per[0][k], (int, float)) and not isinstance(per[0][k], bool)]
    res["median_over_models"] = {k: float(np.median([r[k] for r in per if r[k] is not None])) for k in keys
                                 if any(r[k] is not None for r in per)}
    res["best_model"] = {k: float(max(r[k] for r in per if r[k] is not None)) if "dist" in k
                         else float(min(r[k] for r in per if r[k] is not None))
                         for k in keys if k.startswith(("rmsd", "dist")) and any(r[k] is not None for r in per)}
    ens = distance_metrics(Dt, Dsum / len(X), cis)
    if len(X) > 1:
        Ym = superpose_ensemble(X[:, p[use]]).mean(0)
        ens.update(structure_metrics(T, Ym, lc))
    res["ensemble_mean"] = ens
    return res


def baseline_models(t: dict, pop_path, n_models: int = 10, seed: int = 0) -> dict:
    """Structure-free baselines as (chrom, pos, X) on the truth loci (pos = locus end)."""
    chrom, pos = t["chrom"], t["end"]
    out = {}
    rng = np.random.default_rng(seed)
    L = len(chrom)
    Xr = np.zeros((n_models, L, 3))
    for m in range(n_models):
        for c in np.unique(chrom):
            sel = np.flatnonzero(chrom == c)
            steps = rng.normal(size=(len(sel), 3))
            steps[0] = 0
            Xr[m, sel] = np.cumsum(steps, 0) + rng.normal(size=3) * len(sel) ** 0.5
    out["random_polymer"] = (chrom, pos, Xr)
    if pop_path and Path(pop_path).exists():
        z = np.load(pop_path, allow_pickle=False)
        key = {(c, s): i for i, (c, s) in enumerate(zip(z["chrom"].astype(str), z["start"]))}
        idx = np.array([key[(c, s)] for c, s in zip(chrom, t["start"])])
        Lp = len(z["chrom"])
        for name in ("pop_mean", "pop_ps"):
            D = squareform(np.nan_to_num(z[name], nan=np.nanmean(z[name])))[np.ix_(idx, idx)] if len(z[name]) == Lp * (Lp - 1) // 2 else None
            if D is None:
                continue
            out[name] = (chrom, pos, classical_mds(D)[None], D)
    return out


def cmd_score(args) -> None:
    t = load_truth(args.truth)
    out = {"truth": str(args.truth), "truth_meta": {k: v for k, v in t["meta"].items() if k != "chroms"},
           "methods": {}, "baselines": {}}
    labels = args.labels or [Path(m).stem for m in (args.models or [])]
    for path, lab in zip(args.models or [], labels):
        if not Path(path).exists():
            print(f"missing {path}")
            continue
        chrom, pos, X = load_models(path)
        r = score_ensemble(t, chrom, pos, X)
        r["models"] = str(path)
        out["methods"][lab] = r
        print(json.dumps({"method": lab, **{k: round(v, 3) for k, v in r["median_over_models"].items()}}), flush=True)
    if not args.no_baselines:
        for name, bl in baseline_models(t, args.population, seed=args.seed).items():
            r = score_ensemble(t, *bl[:3])
            if len(bl) == 4:                       # distance-matrix baselines: score the matrix itself
                p = map_loci(t, bl[0], bl[1])
                use = np.flatnonzero(p >= 0)
                iu = np.triu_indices(len(use), 1)
                lc = t["chrom"][use]
                Dt = pdist(t["coords"][use])
                r["distance_matrix"] = distance_metrics(Dt, bl[3][np.ix_(p[use], p[use])][iu], lc[iu[0]] == lc[iu[1]])
            out["baselines"][name] = r
            print(json.dumps({"baseline": name, **{k: round(v, 3) for k, v in r["median_over_models"].items()}}),
                  flush=True)
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(json.dumps(out, indent=1))


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("truth")
    s.add_argument("--dataset", required=True, choices=sorted(DATASETS))
    s.add_argument("--data", help="input file (default: from the data directory, uchrom.datasets)")
    s.add_argument("--n", type=int, default=5)
    s.add_argument("--seed", type=int, default=1)
    s.add_argument("--min-detect", type=float)
    s.add_argument("--min-sep", type=float, help="takei2021_1mb homolog separation threshold")
    s.add_argument("--out", required=True)
    s.set_defaults(fn=cmd_truth)

    r = sub.add_parser("reads")
    r.add_argument("--truth", required=True)
    g = r.add_mutually_exclusive_group()
    g.add_argument("--reads", type=int)
    g.add_argument("--reads-per-mb", type=float)
    r.add_argument("--q", type=float, default=1.0)
    g2 = r.add_mutually_exclusive_group()
    g2.add_argument("--rc", type=float, help="contact radius, nm")
    g2.add_argument("--rc-rel", type=float, help="contact radius / median consecutive-locus distance")
    r.add_argument("--kernel", default="gauss", choices=["gauss", "step", "sigmoid"])
    r.add_argument("--eps", type=float, default=0.0)
    r.add_argument("--missing", default="interp", choices=["interp", "drop"])
    r.add_argument("--seed", type=int, default=1)
    r.add_argument("--out", required=True)
    r.set_defaults(fn=cmd_reads)

    gr = sub.add_parser("grid")
    gr.add_argument("--truth-dir", required=True)
    gr.add_argument("--depths", type=float, nargs="+", default=[10, 40, 160], help="reads per Mb")
    gr.add_argument("--rc-rels", type=float, nargs="+", default=[0.5, 1.0])
    gr.add_argument("--eps", type=float, nargs="+", default=[0.0, 0.05, 0.2])
    gr.add_argument("--seeds", type=int, nargs="+", default=[1])
    gr.add_argument("--kernel", default="gauss", choices=["gauss", "step", "sigmoid"])
    gr.add_argument("--missing", default="interp", choices=["interp", "drop"])
    gr.add_argument("--overwrite", action="store_true")
    gr.add_argument("--out", required=True)
    gr.set_defaults(fn=cmd_grid)

    c = sub.add_parser("score")
    c.add_argument("--truth", required=True)
    c.add_argument("--population", help="population.npz of the truth directory (baselines)")
    c.add_argument("--models", nargs="*")
    c.add_argument("--labels", nargs="*")
    c.add_argument("--no-baselines", action="store_true")
    c.add_argument("--seed", type=int, default=0)
    c.add_argument("--out")
    c.set_defaults(fn=cmd_score)
    args = ap.parse_args(argv)
    args.fn(args)


if __name__ == "__main__":
    main()
