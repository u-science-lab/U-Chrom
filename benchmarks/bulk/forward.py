"""Truth population -> simulated population (bulk) Hi-C.

Subcommands
-----------
``truth``  Imaging truth population (``truths.py``) -> ``Population`` ``.npz``::

               python benchmarks/bulk/forward.py truth --dataset su2020_genome --out SIM/su_genome/truth.npz

``bulk``   Population Hi-C = the **sum over truth cells of per-cell contacts** (the screcon
           forward model applied to every cell)::

               python benchmarks/bulk/forward.py bulk --truth SIM/su_genome/truth.npz --bins centered:3000000 \\
                   --kernel step --rc igm --depth inf --out SIM/su_genome/bulk_step_inf.npz

           * contact propensity at 3-D distance d: ``step`` 1[d < rc] (IGM's own contact
             definition: centre distance <= 2 (r_i + r_j)), ``gauss`` exp(-(d/rc)^2) (a smoother,
             mismatched kernel, as cross-linking), ``sigmoid`` (``benchmarks/screcon/simulate.kernel``);
           * ``rc``: ``--rc-nm X``, ``--rc-rel r`` (r x the truth's median consecutive-locus
             distance), or ``--rc igm`` = 2 (r_i + r_j) with IGM's bead radii
             r_i = (occupancy V_nuc / sum(diploid bin sizes) * size_i / (4 pi / 3))^(1/3)
             (``igm/_preprocess.py``; default occupancy 0.2, V_nuc = sphere of the truth's median
             nuclear radius, estimated per cell as sqrt(5/3) Rg of all its spots);
           * **infinite depth** (``--depth inf``): the exact contact probabilities IGM's input
             means (``pgs_spec.md`` section 4.2): for loci i != j of one chromosome the mean over
             structures and over the *same-copy* combinations (i_a, j_a); for loci of different
             chromosomes the mean over all copy combinations (4 for diploid).  Missing positions
             are left out of the means (``--missing drop``, default) or interpolated along the
             chain (``interp``, screcon convention).  Diagonal = 1; ``--nn-one`` also sets
             consecutive loci to 1 (the IGM preprocessing convention).
           * **finite depth** (``--depth N`` reads): the read propensity of a locus pair is the
             kernel summed over *all* copy combinations (real Hi-C cannot tell homologs apart, so
             homolog-crossing cis pairs count), summed over cells; ``N (1 - eps)`` signal reads
             are drawn multinomially, ``N eps`` noise reads uniformly over pairs, every fine bin
             gets a log-normal visibility bias (``--bias-sd``).  This is exactly the sum of
             per-cell Poisson reads conditioned on the total.  With ``--fine-sub k`` every model
             bin is split into k fine bins and each read end is placed in a uniformly random fine
             bin (a raw fine matrix that exercises ``uchrom.recon.bulk.deconv.preprocess``).
             The raw counts are written next to the output (``*.counts.npz``) and the IGM
             preprocessing is run with the model bins as coarse bins (``--target`` contacts per
             bin; default = the truth's own mean off-diagonal row sum of the infinite-depth matrix,
             i.e. the oracle scale; ``--target 24`` = the paper's value).

Output: the probability-matrix ``.npz`` of ``preprocess.ProbabilityMatrix.save`` (``i, j, p``
upper triangle incl. diagonal, ``bins_*``, ``provenance``) - the same interface as real data.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import scipy.sparse as sp

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import jdump, load_preprocess  # noqa: E402
from population import Population, median_consecutive  # noqa: E402
from simulate import kernel  # noqa: E402  (benchmarks/screcon)


# --------------------------------------------------------------------------- geometry

def nuclear_radius(pop: Population, max_cells: int = 500) -> float:
    """Median over structures of sqrt(5/3) x Rg of all positions (uniform-sphere equivalent)."""
    r = []
    for X in pop.coords[:max_cells]:
        Y = X.reshape(-1, 3)
        Y = Y[np.isfinite(Y).all(1)]
        if len(Y) > 3:
            r.append(np.sqrt(5.0 / 3.0 * ((Y - Y.mean(0)) ** 2).sum(1).mean()))
    return float(np.median(r))


def ploidy_per_chrom(pop: Population) -> dict:
    out = {}
    for c in np.unique(pop.chrom):
        pres = np.isfinite(pop.coords[:, :, pop.chrom == c, 0]).any(axis=(0, 2))
        out[c] = int(pres.sum())
    return out


def igm_radii(bins: pd.DataFrame, ploidy: dict, nucleus_radius: float, occupancy: float = 0.2) -> np.ndarray:
    """IGM bead radii (``igm/_preprocess.py``): rho = occupancy V / sum over the diploid index of
    (end - start), r = (rho size / (4 pi / 3))^(1/3)."""
    size = (bins["end"] - bins["start"]).to_numpy(float)
    total = sum(size[bins["chrom"].to_numpy() == c].sum() * k for c, k in ploidy.items())
    V = 4.0 / 3.0 * np.pi * nucleus_radius ** 3
    rho = occupancy * V / total
    return (rho * size / (4.0 * np.pi / 3.0)) ** (1.0 / 3.0)


def model_bins(pop: Population, spec: str = "loci") -> pd.DataFrame:
    """``loci`` (the imaged loci), or ``centered:W`` (W bp centred on every locus midpoint,
    clipped at 0 and at the midpoint between neighbouring loci)."""
    b = pd.DataFrame({"chrom": pop.chrom, "start": pop.start, "end": pop.end})
    if spec == "loci":
        return b
    if not spec.startswith("centered:"):
        raise ValueError(spec)
    w = int(float(spec.split(":")[1]))
    mid = (pop.start + pop.end) // 2
    s = np.maximum(mid - w // 2, 0)
    e = mid + w // 2
    for c in np.unique(pop.chrom):
        k = np.flatnonzero(pop.chrom == c)
        o = k[np.argsort(mid[k])]
        half = (mid[o][1:] + mid[o][:-1]) // 2
        s[o[1:]] = np.maximum(s[o[1:]], half)
        e[o[:-1]] = np.minimum(e[o[:-1]], half)
    return pd.DataFrame({"chrom": pop.chrom, "start": s, "end": e})


# --------------------------------------------------------------------------- contact sums

def contact_sums(pop: Population, rc, kind: str = "step", missing: str = "drop"):
    """Per haploid pair: IGM-pooled sum / count and the Hi-C propensity (all copy combinations).

    ``rc``: scalar (nm) or (L, L) array.  Returns dict with ``igm_sum``, ``igm_n`` (L, L) and
    ``hic`` (L, L; mean over structures of the kernel summed over all copy combinations).
    """
    from truth import interpolate_missing  # screcon
    S, P, L, _ = pop.coords.shape
    same = pop.chrom[:, None] == pop.chrom[None]
    rc = np.broadcast_to(np.asarray(rc, float), (L, L))
    igm_sum = np.zeros((L, L))
    igm_n = np.zeros((L, L))
    hic = np.zeros((L, L))
    for s in range(S):
        X = pop.coords[s].astype(np.float64)
        if missing == "interp":
            X = np.stack([interpolate_missing(pop.chrom, pop.start, X[c])[0] if np.isfinite(X[c]).any() else X[c]
                          for c in range(P)])
        for a in range(P):
            for b in range(P):
                d = np.linalg.norm(X[a][:, None] - X[b][None], axis=-1)
                ok = np.isfinite(d)
                k = np.where(ok, kernel(np.where(ok, d, 0.0), rc, kind), 0.0)
                hic += k
                use = (~same) | (a == b)
                igm_sum += np.where(use, k, 0.0)
                igm_n += use & ok
    return {"igm_sum": igm_sum, "igm_n": igm_n, "hic": hic / S}


def probability_matrix(sums: dict, bins: pd.DataFrame, nn_one: bool = False):
    with np.errstate(invalid="ignore", divide="ignore"):
        f = np.where(sums["igm_n"] > 0, sums["igm_sum"] / sums["igm_n"], 0.0)
    np.fill_diagonal(f, 1.0)
    if nn_one:
        ch = bins["chrom"].to_numpy()
        for i in range(len(ch) - 1):
            if ch[i] == ch[i + 1]:
                f[i, i + 1] = f[i + 1, i] = 1.0
    return np.clip(f, 0, 1)


def simulate_counts(hic: np.ndarray, bins: pd.DataFrame, reads: int, eps: float = 0.0, bias_sd: float = 0.0,
                    fine_sub: int = 1, seed: int = 0):
    """Multinomial reads over locus pairs (i < j) with propensity ``hic`` x bias, plus uniform
    noise; each read end in a random fine sub-bin.  Returns (upper csr counts, fine bins)."""
    rng = np.random.default_rng(seed)
    L = len(bins)
    nf = L * fine_sub
    iu = np.triu_indices(L, 1)
    lam = hic[iu].astype(float)
    n_noise = int(rng.binomial(reads, eps))
    cnt = rng.multinomial(reads - n_noise, lam / lam.sum()) if lam.sum() > 0 else np.zeros(len(lam), int)
    noise = rng.integers(0, len(lam), n_noise)
    pair = np.concatenate([np.repeat(np.arange(len(lam)), cnt), noise])
    A, B = iu[0][pair], iu[1][pair]
    fa = A * fine_sub + rng.integers(0, fine_sub, len(A))
    fb = B * fine_sub + rng.integers(0, fine_sub, len(B))
    if bias_sd > 0:                     # visibility bias: thin reads by b_i b_j / max
        b = rng.lognormal(0.0, bias_sd, nf)
        keep = rng.random(len(fa)) < (b[fa] * b[fb]) / (b.max() ** 2)
        fa, fb = fa[keep], fb[keep]
    lo, hi = np.minimum(fa, fb), np.maximum(fa, fb)
    m = sp.coo_matrix((np.ones(len(lo)), (lo, hi)), shape=(nf, nf)).tocsr()
    m.sum_duplicates()
    rows = []
    for c, s, e in zip(bins["chrom"], bins["start"], bins["end"]):
        edges = np.linspace(s, e, fine_sub + 1).astype(np.int64)
        rows += [(c, edges[k], edges[k + 1]) for k in range(fine_sub)]
    return m, pd.DataFrame(rows, columns=["chrom", "start", "end"])


# --------------------------------------------------------------------------- commands

def cmd_truth(args) -> None:
    from truths import load_dataset
    kw = {}
    if args.min_detect is not None:
        kw["min_detect"] = args.min_detect
    pop = load_dataset(args.dataset, args.data, **kw)
    pop.meta["median_consecutive_nm"] = median_consecutive(pop)
    pop.meta["nuclear_radius_nm"] = nuclear_radius(pop)
    pop.save(args.out)
    print(jdump({k: v for k, v in pop.meta.items() if k != "cell_ids"}), flush=True)


def resolve_rc(args, pop: Population, bins: pd.DataFrame):
    info = {}
    if args.rc_nm is not None:
        rc = float(args.rc_nm)
    elif args.rc_rel is not None:
        rc = args.rc_rel * median_consecutive(pop)
    else:
        R = args.nucleus_radius or pop.meta.get("nuclear_radius_nm") or nuclear_radius(pop)
        pl = ploidy_per_chrom(pop)
        r = igm_radii(bins, pl, R, args.occupancy)
        rc = 2.0 * (r[:, None] + r[None])
        info = {"nucleus_radius_nm": R, "occupancy": args.occupancy, "ploidy": pl,
                "bead_radius_nm_median": float(np.median(r)), "contact_range": 2.0}
    info["rc_nm_median"] = float(np.median(rc))
    return rc, info


def cmd_bulk(args) -> None:
    pp = load_preprocess()
    pop = Population.load(args.truth)
    bins = model_bins(pop, args.bins)
    rc, rcinfo = resolve_rc(args, pop, bins)
    sums = contact_sums(pop, rc, args.kernel, args.missing)
    f = probability_matrix(sums, bins, args.nn_one)
    prov = {"truth": str(args.truth), "dataset": pop.meta.get("dataset"), "bins": args.bins, "kernel": args.kernel,
            "missing": args.missing, "nn_one": args.nn_one, **rcinfo, "n_structures": pop.n_structures,
            "pooling": "IGM: cis same-copy mean, trans mean over all copy combinations",
            "truth_mean_rowsum": float(np.mean(f.sum(1) - np.diag(f)))}
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    exact = pp.ProbabilityMatrix(pp.symmetrize_upper(sp.triu(sp.csr_matrix(f))),
                                 bins.assign(chrom=bins.chrom.astype(str)), dict(prov, depth="inf"))
    if args.depth == "inf":
        exact.save(out)
        print(jdump(prov), flush=True)
        return
    exact.save(out.with_name(out.stem + ".exact.npz"))
    reads = int(float(args.depth))
    m, fine = simulate_counts(sums["hic"], bins, reads, args.eps, args.bias_sd, args.fine_sub, args.seed)
    c = m.tocoo()
    np.savez_compressed(out.with_name(out.stem + ".counts.npz"), i=c.row, j=c.col, count=c.data,
                        bins_chrom=fine.chrom.astype(str).to_numpy(), bins_start=fine.start.to_numpy(),
                        bins_end=fine.end.to_numpy(), n=len(fine))
    target = args.target if args.target is not None else prov["truth_mean_rowsum"]
    P = pp.IGMPreprocessParams(fine_resolution=int(np.median(fine.end - fine.start)), coarse_resolution=0,
                               target_contacts=float(target))
    res = pp.preprocess_igm(m, fine, params=P, coarse_bins=bins)
    res.provenance.update({"simulation": dict(prov, depth=reads, eps=args.eps, bias_sd=args.bias_sd,
                                              fine_sub=args.fine_sub, seed=args.seed, n_reads_kept=int(m.sum()))})
    res.save(out)
    # agreement of the preprocessed matrix with the exact one (off-diagonal, non-neighbour pairs)
    got = res.probabilities.toarray()
    iu = np.triu_indices(len(bins), 2)
    ok = np.isfinite(got[iu]) & (f[iu] > 0)
    from scipy import stats
    summ = {"reads": reads, "fmax": res.provenance["fmax"], "target": target,
            "pearson_vs_exact": float(np.corrcoef(got[iu][ok], f[iu][ok])[0, 1]),
            "spearman_vs_exact": float(stats.spearmanr(got[iu][ok], f[iu][ok])[0]),
            "median_ratio_vs_exact": float(np.median(got[iu][ok] / f[iu][ok]))}
    Path(str(out) + ".json").write_text(jdump(summ))
    print(jdump(summ), flush=True)


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    t = sub.add_parser("truth")
    t.add_argument("--dataset", required=True, choices=["su2020_genome", "su2020_chr21", "takei2021_1mb"])
    t.add_argument("--data")
    t.add_argument("--min-detect", type=float)
    t.add_argument("--out", required=True)
    t.set_defaults(fn=cmd_truth)
    b = sub.add_parser("bulk")
    b.add_argument("--truth", required=True)
    b.add_argument("--bins", default="loci", help="loci | centered:W")
    b.add_argument("--kernel", default="step", choices=["step", "gauss", "sigmoid"])
    g = b.add_mutually_exclusive_group()
    g.add_argument("--rc-nm", type=float)
    g.add_argument("--rc-rel", type=float)
    b.add_argument("--nucleus-radius", type=float, help="nm (default: from the truth)")
    b.add_argument("--occupancy", type=float, default=0.2)
    b.add_argument("--missing", default="drop", choices=["drop", "interp"])
    b.add_argument("--nn-one", action="store_true")
    b.add_argument("--depth", default="inf", help="'inf' or a number of reads")
    b.add_argument("--eps", type=float, default=0.0)
    b.add_argument("--bias-sd", type=float, default=0.2)
    b.add_argument("--fine-sub", type=int, default=10)
    b.add_argument("--target", type=float, help="contacts per coarse bin for the preprocessing (default: oracle)")
    b.add_argument("--seed", type=int, default=1)
    b.add_argument("--out", required=True)
    b.set_defaults(fn=cmd_bulk)
    args = ap.parse_args(argv)
    args.fn(args)


if __name__ == "__main__":
    main()
