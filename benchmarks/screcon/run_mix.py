"""Methods of the few-cell deconvolution benchmark (PREREG §12) on a pooled contact table.

    python benchmarks/screcon/run_mix.py --method mix --contacts POOL.txt.gz --k 3 --res 1000000 \\
        --device gpu --n-models 2 --seed 1 [--params '{...}'] --out RUN/mix.npz

* ``mix``    EMber-mix: native engine, protocol ``robust`` with ``mix_cells = k`` (``MIX_DEFAULTS``
             below, overridden by ``$MIX_PARAMS`` then ``--params``), ``n_models`` per cell.
* ``naive``  frozen EMber (``run_robust.ROBUST_DEFAULTS``) on the pooled table as if one cell.
* ``igm``    IGM with S = k structures (native protocol ``igm``, its defaults: sphere, occupancy,
             demo annealing; ``ploidy = "haploid"``), input p_ij = min(1, n_ij / k) on the 2017
             particle grid of the resolution (bins (pos - res, pos]; neighbours 1).
* ``oracle`` frozen EMber on every cell's own table (``--cell-tables``; real pools: the cells'
             references), one cell per table.

Output ``.npz``: ``chrom``, ``pos`` (2017 convention: particle covers (pos - size, pos]), ``coords``
(M, N, 3), ``model_cell`` (M,) and, when the method assigns contacts, ``cell_probs`` (n_rows, k) for the
rows of ``--contacts``; ``<out>.json`` holds timings and parameters.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from contacts import ParticleIndex, read_contacts  # noqa: E402
from run_nucdyn import peak_rss_mb, schedule  # noqa: E402
from run_robust import ROBUST_DEFAULTS  # noqa: E402

#: EMber-mix parameters (engine defaults otherwise); changed only by development experiments
#: (mix_devlog.md).
MIX_DEFAULTS: dict = {**ROBUST_DEFAULTS}


def _pos_end(res) -> np.ndarray:
    pos = np.asarray(res["position"], np.int64)
    if res["position_convention"] == "start":
        pos = pos + int(res["particle_size"])
    return pos


def run_ember(c, sizes, n_models, seed, device, params, n_threads=0, mix_prior=None):
    """EMber / EMber-mix on contacts ``c``; phased contacts (``diploid.Phased``) run diploid (every
    chromosome two copies)."""
    import uchrom_nucdyn as un
    kw = {} if mix_prior is None else {"mix_prior": mix_prior}
    if hasattr(c, "hap_a"):
        kw.update(hap_a=c.hap_a, hap_b=c.hap_b, ploidy="diploid")
    return un.calc_genome_structure(c.chrom_a.astype(str), c.pos_a, c.chrom_b.astype(str), c.pos_b, protocol="robust",
                                    particle_sizes=sizes, n_models=n_models, seed=seed, device=device,
                                    n_threads=n_threads, verbose=True, **kw, **params)


def chain_names(res) -> np.ndarray:
    """Particle chain names: chromosomes, or copy chains ``chr1(0)`` / ``chr1(1)`` for diploid runs."""
    if res.get("diploid"):
        from diploid import copy_name
        k = res["ploidy"]
        return np.array([copy_name(ch, h, k[ch]) for ch, h in zip(res["chrom"].astype(str), res["copy"])])
    return res["chrom"].astype(str)


def load_table(path, diploid: bool):
    if diploid:
        from diploid import read_phased
        return read_phased(path)
    return read_contacts(path)


def run_igm(c, k: int, res_bp: int, seed: int, device: str, params: dict, ploidy: str = "haploid"):
    """IGM (S = k; haploid, or diploid with every chromosome two copies) on the pooled contacts binned at
    ``res_bp`` (phases not used: IGM's probabilities are haploid)."""
    import uchrom_nucdyn as un
    from contacts import sort_chroms
    chroms = sort_chroms(np.concatenate([c.chrom_a, c.chrom_b]))
    rows = []
    for ch in chroms:
        mx = max(c.pos_a[c.chrom_a == ch].max(initial=0), c.pos_b[c.chrom_b == ch].max(initial=0))
        mn = min(c.pos_a[c.chrom_a == ch].min(initial=mx), c.pos_b[c.chrom_b == ch].min(initial=mx))
        # 2017 grid: particle k covers (pos - res, pos], pos multiple of res
        first = (mn + res_bp - 1) // res_bp * res_bp
        last = (mx + res_bp - 1) // res_bp * res_bp
        for p in range(max(first, res_bp), last + 1, res_bp):
            rows.append((ch, p - res_bp, p))
    chrom = np.array([r[0] for r in rows]); start = np.array([r[1] for r in rows]); end = np.array([r[2] for r in rows])
    pidx = ParticleIndex(chrom, end, res_bp)
    ia, ib = pidx(c.chrom_a, c.pos_a), pidx(c.chrom_b, c.pos_b)
    ok = (ia >= 0) & (ib >= 0) & (ia != ib)
    a, b = np.minimum(ia[ok], ib[ok]), np.maximum(ia[ok], ib[ok])
    pairs, cnt = np.unique(np.stack([a, b], 1), axis=0, return_counts=True)
    prob = np.minimum(1.0, cnt / k)
    # chain neighbours: probability 1
    same = chrom[1:] == chrom[:-1]
    nb = np.flatnonzero(same)
    pi = np.concatenate([pairs[:, 0], nb]); pj = np.concatenate([pairs[:, 1], nb + 1])
    pv = np.concatenate([prob, np.ones(len(nb))])
    key = pi.astype(np.int64) * len(chrom) + pj
    _, first_idx = np.unique(key, return_index=True)
    pi, pj, pv = pi[first_idx], pj[first_idx], pv[first_idx]
    out = un.calc_population(chrom, start, end, pi, pj, pv, ploidy=ploidy, n_structures=k, seed=seed,
                             device=device, **params)
    X = np.asarray(out["coords"], float)                      # (S, N_beads, 3) nm
    bead_bin = np.asarray(out["bead_bin"], np.int64)
    names = chrom[bead_bin]
    if ploidy != "haploid":
        from diploid import copy_name
        names = np.array([copy_name(ch, h) for ch, h in zip(names, np.asarray(out["bead_copy"]))])
    return names, end[bead_bin], X, out


def closest_cell_probs(c, chrom, pos, X, model_cell, k):
    """One-hot cell of every row: the cell whose (replicate-mean) structure places its ends closest."""
    from mix_score import closest_assign
    pred = closest_assign(c, chrom, pos, X, model_cell)
    P = np.full((len(pred), k), np.nan)
    ok = pred >= 0
    P[ok] = 0.0
    P[np.flatnonzero(ok), pred[ok]] = 1.0
    return P


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--method", required=True, choices=["mix", "naive", "igm", "oracle", "split"])
    ap.add_argument("--contacts", required=True, help="pooled table (oracle: used for the row assignment only)")
    ap.add_argument("--k", type=int, required=True)
    ap.add_argument("--cell-tables", nargs="*", help="oracle: the cells' own tables, in pool order")
    ap.add_argument("--res", type=float, default=1e6)
    ap.add_argument("--device", default="gpu", choices=["cpu", "gpu"])
    ap.add_argument("--n-models", type=int, default=2, help="models per cell")
    ap.add_argument("--n-threads", type=int, default=0)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--params", default="{}")
    ap.add_argument("--oracle-prior", type=float, default=None,
                    help="DIAGNOSTIC ONLY: seed with the true cell of every row (the pool's .origin.npz); the\n"
                         "value is the fraction of rows whose seed is replaced by a random cell")
    ap.add_argument("--diploid", action="store_true", help="phased contact tables (hickit pairs): diploid runs")
    ap.add_argument("--prior", help=".npy (n_rows, k): per-row prior over the cells (the first-stage seed)")
    ap.add_argument("--oracle-subset", default="all", choices=["all", "trans"],
                    help="DIAGNOSTIC ONLY: rows that get the oracle seed (trans: cis rows uniform)")
    ap.add_argument("--label")
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args(argv)
    import uchrom_nucdyn as un
    sizes = schedule(args.res)
    c = load_table(args.contacts, args.diploid)
    t0 = time.time()
    meta = {"method": args.method, "label": args.label or args.method, "contacts": args.contacts, "k": args.k,
            "particle_sizes": sizes, "n_models": args.n_models, "seed": args.seed, "device": args.device,
            "engine_version": un.__version__, "slurm_job_id": os.environ.get("SLURM_JOB_ID")}
    extra = {}
    if args.method == "mix":
        params = {**MIX_DEFAULTS, **json.loads(os.environ.get("MIX_PARAMS", "{}")), **json.loads(args.params),
                  "mix_cells": args.k}
        prior = None
        if args.oracle_prior is not None:
            base = args.contacts[:-7] if args.contacts.endswith(".txt.gz") else args.contacts
            cell = np.load(base + ".origin.npz")["cell"].astype(np.int64)
            rng = np.random.default_rng(args.seed)
            flip = rng.random(len(cell)) < args.oracle_prior
            cell = np.where(flip, rng.integers(0, args.k, len(cell)), cell)
            prior = np.zeros((len(cell), args.k))
            prior[np.arange(len(cell)), cell] = 1.0
            if args.oracle_subset == "trans":
                prior[c.chrom_a == c.chrom_b] = 1.0 / args.k
            meta["oracle_prior"] = args.oracle_prior
        if args.prior:
            prior = np.load(args.prior)
            meta["prior_file"] = args.prior
        passes = int(params.pop("passes", 0))
        if passes < 0:                       # -j: k + j passes (one more cell is seeded per pass)
            passes = args.k - passes
        popt = {key[5:]: params.pop(key) for key in list(params) if key.startswith("pass_")}
        if passes > 0:
            res = un.deconvolve_passes(c.chrom_a.astype(str), c.pos_a, c.chrom_b.astype(str), c.pos_b, passes=passes,
                                       mix_prior=prior, particle_sizes=sizes, n_models=args.n_models, seed=args.seed,
                                       device=args.device, n_threads=args.n_threads, protocol="robust", verbose=True,
                                       log=lambda d: print(json.dumps(d), file=sys.stderr, flush=True), **popt, **params)
            meta["passes_log"] = res["passes_log"]
        else:
            res = run_ember(c, sizes, args.n_models, args.seed, args.device, params, args.n_threads, prior)
        chrom, pos, X = chain_names(res), _pos_end(res), res["coords"]
        model_cell = np.asarray(res["model_cell"])
        extra = {"cell_probs": res["cell_probs"], "contact_weights": res["contact_weights"]}
        meta.update(params=res["params"], stages=res["stages"])
    elif args.method == "naive":
        params = {**ROBUST_DEFAULTS, **json.loads(args.params)}
        res = run_ember(c, sizes, args.n_models, args.seed, args.device, params, args.n_threads)
        chrom, pos, X = chain_names(res), _pos_end(res), res["coords"]
        model_cell = np.zeros(len(X), np.int64)
        meta.update(params=res["params"], stages=res["stages"])
    elif args.method == "igm":
        params = json.loads(args.params)
        chrom, pos, X, out = run_igm(c, args.k, int(args.res), args.seed, args.device, params,
                                     "diploid" if args.diploid else "haploid")
        model_cell = np.arange(len(X))
        extra = {"cell_probs": closest_cell_probs(c, chrom, pos, X, model_cell, args.k)}
        meta.update(params=out["params"], rounds=out["rounds"])
    else:
        params = {**ROBUST_DEFAULTS, **json.loads(args.params)}
        Xs, model_cell = [], []
        chrom = pos = None
        grids = []
        if args.method == "split":
            # prior-split: every row to the cell of its largest prior (ties at random), frozen EMber per cell
            P = np.load(args.prior)
            rng = np.random.default_rng(args.seed)
            best = np.argmax(P + 1e-9 * rng.random(P.shape), 1)
            tables = [c.subset(best == j) for j in range(args.k)]
            extra = {"cell_probs": np.eye(args.k)[best]}
            meta["prior_file"] = args.prior
        else:
            tables = [load_table(f, args.diploid) for f in args.cell_tables]
        for j, cc in enumerate(tables):
            res = run_ember(cc, sizes, args.n_models, args.seed, args.device, params, args.n_threads)
            grids.append((chain_names(res), _pos_end(res), res["coords"]))
            model_cell += [j] * len(res["coords"])
        # common particle set: union of the cells' grids; a cell's coordinates at particles it lacks
        # are taken from the nearest particle of its own grid on the same chromosome
        from contacts import sort_chroms, chrom_key
        keys = sorted({(ch, p) for g in grids for ch, p in zip(g[0], g[1])}, key=lambda x: (chrom_key(x[0]), x[1]))
        chrom = np.array([x[0] for x in keys]); pos = np.array([x[1] for x in keys], np.int64)
        for gc, gp, gX in grids:
            idx = np.zeros(len(keys), np.int64)
            for ch in np.unique(chrom):
                sel = np.flatnonzero(chrom == ch)
                own = np.flatnonzero(gc == ch)
                if not len(own):
                    idx[sel] = 0
                    continue
                k = np.searchsorted(gp[own], pos[sel]).clip(0, len(own) - 1)
                km = (k - 1).clip(0)
                pick = np.where(np.abs(gp[own][km] - pos[sel]) < np.abs(gp[own][k] - pos[sel]), km, k)
                idx[sel] = own[pick]
            Xs.append(gX[:, idx])
        X = np.concatenate(Xs, 0)
        model_cell = np.asarray(model_cell)
        meta.update(params=params, cell_tables=args.cell_tables)
    wall = time.time() - t0
    args.out.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(args.out, chrom=chrom, pos=pos, coords=X, model_cell=model_cell, **extra)
    meta.update(wall_seconds=wall, peak_rss_mb=peak_rss_mb(), n_rows=len(c))
    Path(str(args.out) + ".json").write_text(json.dumps(meta, indent=1, default=str))
    print(f"{args.method} {args.contacts}: {X.shape} in {wall:.1f} s", flush=True)


if __name__ == "__main__":
    main()
