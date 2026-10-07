"""Metrics of the EMber-pop benchmark (``PREREG_POP.md`` sections 5-6), on top of ``bulk_metrics``.

Per-locus and per-pair arrays are kept (not only summaries) so that the endpoints can be averaged
over seeds and units and bootstrapped by chromosome blocks (``block_bootstrap_*``).

* ``ellip_radius``: per structure, centroid and gyration tensor of all its non-missing loci;
  rho = |V^T (x - c) / sqrt(5 lambda)| (1 = surface of the uniform ellipsoid with that tensor);
* ``locus_w1``: per-locus 1-Wasserstein distance between two (S, P, L) samples (copies pooled);
* ``pair_w1``: per-pair W1 of distance samples (``bulk_metrics.pair_samples`` pooling), in units;
* ``fit_to_input``: |cf - f| on the input pairs (computed from the engine output at the model's
  own contact distance, ``_igm_bench.contact_probability``);
* ``territory_neighbourhood``: per chromosome pair, the fraction of (structure, copy combination)
  whose two chromosome copies have any locus pair within r;
* ``shape_stats``: gyration ratios sqrt(l2/l1), sqrt(l3/l1) and Rg per structure;
* ``pair_cv``: per-pair coefficient of variation of the distance samples.
"""

from __future__ import annotations

import numpy as np

from bulk_metrics import _chunks, _per_locus_w1, _spearman, pair_samples
from population import Population


# --------------------------------------------------------------------------- radial / shape

def _gyration(X: np.ndarray):
    Y = X.reshape(-1, 3).astype(np.float64)
    Y = Y[np.isfinite(Y).all(1)]
    c = Y.mean(0)
    G = (Y - c).T @ (Y - c) / len(Y)
    lam, V = np.linalg.eigh(G)
    return c, lam[::-1], V[:, ::-1]


def ellip_radius(pop: Population) -> np.ndarray:
    """(S, P, L) elliptical radial position (scale- and shape-free, see module doc)."""
    S = pop.n_structures
    out = np.full(pop.coords.shape[:3], np.nan)
    for s in range(S):
        X = pop.coords[s].astype(np.float64)
        if np.isfinite(X).all(-1).sum() < 4:
            continue
        c, lam, V = _gyration(X)
        u = (X - c) @ V / np.sqrt(5.0 * np.maximum(lam, 1e-12))
        out[s] = np.linalg.norm(u, axis=-1)
    return out


def locus_w1(a: np.ndarray, b: np.ndarray, n_quantiles: int = 50) -> np.ndarray:
    return _per_locus_w1(a, b, n_quantiles)


def shape_stats(pop: Population) -> dict:
    """Per structure: Rg, sqrt(l2/l1), sqrt(l3/l1) (all non-missing loci, both copies)."""
    rg, r21, r31 = [], [], []
    for X in pop.coords:
        if np.isfinite(X).all(-1).sum() < 4:
            continue
        _, lam, _ = _gyration(X)
        rg.append(np.sqrt(lam.sum()))
        r21.append(np.sqrt(lam[1] / lam[0]))
        r31.append(np.sqrt(lam[2] / lam[0]))
    return {"rg": np.array(rg), "r21": np.array(r21), "r31": np.array(r31)}


def w1_1d(a: np.ndarray, b: np.ndarray, n_quantiles: int = 100) -> float:
    q = (np.arange(n_quantiles) + 0.5) / n_quantiles
    a, b = a[np.isfinite(a)], b[np.isfinite(b)]
    return float(np.mean(np.abs(np.quantile(a, q) - np.quantile(b, q))))


# --------------------------------------------------------------------------- pairs

def pair_w1(R: Population, T: Population, i, j, unit: float, n_quantiles: int = 100, chunk: int = 2000):
    """Per-pair W1 (in ``unit``) and per-pair medians of R and T."""
    q = (np.arange(n_quantiles) + 0.5) / n_quantiles
    w1 = np.empty(len(i))
    mr = np.empty(len(i))
    mt = np.empty(len(i))
    cvr = np.empty(len(i))
    cvt = np.empty(len(i))
    for sl in _chunks(len(i), chunk):
        dr, dt = pair_samples(R, i[sl], j[sl]), pair_samples(T, i[sl], j[sl])
        qr, qt = np.nanquantile(dr, q, axis=0), np.nanquantile(dt, q, axis=0)
        w1[sl] = np.mean(np.abs(qr - qt), axis=0) / unit
        mr[sl], mt[sl] = qr[n_quantiles // 2], qt[n_quantiles // 2]
        cvr[sl] = np.nanstd(dr, axis=0) / np.nanmean(dr, axis=0)
        cvt[sl] = np.nanstd(dt, axis=0) / np.nanmean(dt, axis=0)
    return {"w1": w1, "med_R": mr, "med_T": mt, "cv_R": cvr, "cv_T": cvt}


def contact_freq_pairs(pop: Population, i, j, r, chunk: int = 2000) -> np.ndarray:
    out = np.empty(len(i))
    r = np.broadcast_to(np.asarray(r, float), (len(i),))
    for sl in _chunks(len(i), chunk):
        d = pair_samples(pop, i[sl], j[sl])
        ok = np.isfinite(d)
        out[sl] = (ok & (d < r[sl])).sum(0) / np.maximum(ok.sum(0), 1)
    return out


# --------------------------------------------------------------------------- territories

def territory_neighbourhood(pop: Population, r: float, max_structures: int | None = None) -> tuple[np.ndarray, list]:
    """(C, C) fraction of (structure, copy combination) with min inter-territory distance < r
    (C = chromosomes in genome order; diagonal = the two homologs of one chromosome)."""
    chroms = list(dict.fromkeys(pop.chrom.tolist()))
    idx = [np.flatnonzero(pop.chrom == c) for c in chroms]
    C = len(chroms)
    hit = np.zeros((C, C))
    tot = np.zeros((C, C))
    X = pop.coords if max_structures is None else pop.coords[:max_structures]
    P = X.shape[1]
    r2 = r * r
    for s in range(X.shape[0]):
        Y = X[s].astype(np.float64)                      # (P, L, 3)
        flat = Y.reshape(-1, 3)
        ok = np.isfinite(flat).all(1)
        sq = (flat ** 2).sum(1)
        D2 = sq[:, None] + sq[None] - 2.0 * flat @ flat.T
        D2[~ok] = np.inf
        D2[:, ~ok] = np.inf
        D2 = D2.reshape(P, pop.n_loci, P, pop.n_loci)
        for a in range(C):
            for b in range(a, C):
                for pa in range(P):
                    for pb in range(P):
                        if a == b and pa >= pb:
                            continue
                        blk = D2[pa][idx[a]][:, pb][:, idx[b]]
                        if not np.isfinite(blk).any():
                            continue
                        tot[a, b] += 1
                        hit[a, b] += float(blk.min() < r2)
    with np.errstate(invalid="ignore"):
        F = hit / tot
    F = np.where(np.isfinite(F), F, np.nan)
    iu = np.triu_indices(C, 1)
    F[iu[1], iu[0]] = F[iu]
    return F, chroms


# --------------------------------------------------------------------------- bootstrap

def chrom_codes(chrom: np.ndarray) -> tuple[np.ndarray, list]:
    names = list(dict.fromkeys(np.asarray(chrom).astype(str).tolist()))
    code = {c: k for k, c in enumerate(names)}
    return np.array([code[c] for c in np.asarray(chrom).astype(str)]), names


def block_sums_locus(values: np.ndarray, ccode: np.ndarray, C: int):
    ok = np.isfinite(values)
    s = np.bincount(ccode[ok], values[ok], minlength=C)
    n = np.bincount(ccode[ok], minlength=C).astype(float)
    return s, n


def block_sums_pair(values: np.ndarray, ci: np.ndarray, cj: np.ndarray, C: int):
    ok = np.isfinite(values)
    k = ci[ok] * C + cj[ok]
    s = np.bincount(k, values[ok], minlength=C * C).reshape(C, C)
    n = np.bincount(k, minlength=C * C).astype(float).reshape(C, C)
    return s + s.T - np.diag(np.diag(s)), n + n.T - np.diag(np.diag(n))


def bootstrap_mean(blocks: list, kind: list, C: int, n_boot: int = 2000, seed: int = 0) -> dict:
    """Mean over units of the block-weighted means; percentile CI resampling chromosomes jointly.

    ``blocks[u]`` = (sums, counts) of unit u (locus: (C,), pair: (C, C)); ``kind[u]`` in
    {"locus", "pair"}."""
    def stat(m):
        vals = []
        for (s, n), k in zip(blocks, kind):
            if k == "locus":
                vals.append((m * s).sum() / (m * n).sum())
            else:
                w = np.outer(m, m)
                vals.append((w * s).sum() / (w * n).sum())
        return float(np.mean(vals))

    est = stat(np.ones(C))
    rng = np.random.default_rng(seed)
    reps = np.array([stat(np.bincount(rng.integers(0, C, C), minlength=C).astype(float)) for _ in range(n_boot)])
    lo, hi = np.nanpercentile(reps, [2.5, 97.5])
    return {"estimate": est, "ci": [float(lo), float(hi)], "n_boot": n_boot}


# --------------------------------------------------------------------------- one population

def score_arrays(R: Population, T: Population, *, i, j, rc: float, scale: float | None = None,
                 territory_structures: int | None = 300) -> tuple[dict, dict]:
    """Arrays (per locus / per pair) and summaries of R vs T for the EMber-pop endpoints."""
    from bulk_metrics import global_scale
    from population import median_consecutive
    unit = median_consecutive(T)
    if scale is None:
        si, sj = i[: min(len(i), 50000)], j[: min(len(j), 50000)]
        scale = global_scale(R, T, si, sj)
    Rs = R.scaled(scale)
    arr, summ = {}, {"scale": scale, "unit_nm": unit, "n_R": R.n_structures, "n_T": T.n_structures}
    # P1: elliptical radius
    rho_R, rho_T = ellip_radius(Rs), ellip_radius(T)
    arr["rho_w1"] = locus_w1(rho_R, rho_T)
    arr["rho_mean_R"] = np.nanmean(rho_R.reshape(-1, R.n_loci), 0)
    arr["rho_mean_T"] = np.nanmean(rho_T.reshape(-1, T.n_loci), 0)
    summ["P1_rho_w1_mean"] = float(np.nanmean(arr["rho_w1"]))
    summ["rho_mean_spearman"] = _spearman(arr["rho_mean_R"], arr["rho_mean_T"])
    # P2: pair W1
    pw = pair_w1(Rs, T, i, j, unit)
    arr.update({f"pair_{k}": v for k, v in pw.items()})
    summ["P2_pair_w1_mean"] = float(np.nanmean(pw["w1"]))
    cis = T.chrom[i] == T.chrom[j]
    summ["P2_cis"] = float(np.nanmean(pw["w1"][cis]))
    summ["P2_trans"] = float(np.nanmean(pw["w1"][~cis])) if (~cis).any() else None
    summ["median_spearman"] = _spearman(pw["med_R"], pw["med_T"])
    summ["cv_spearman"] = _spearman(pw["cv_R"], pw["cv_T"])
    summ["cv_ratio_median"] = float(np.nanmedian(pw["cv_R"]) / np.nanmedian(pw["cv_T"]))
    # contact frequencies vs truth
    for rr in (0.5, 1.0, 2.0):
        cr, ct = contact_freq_pairs(Rs, i, j, rr * rc), contact_freq_pairs(T, i, j, rr * rc)
        arr[f"cf{rr:g}_R"], arr[f"cf{rr:g}_T"] = cr, ct
        summ[f"cf{rr:g}rc_mae"] = float(np.mean(np.abs(cr - ct)))
    # shape
    sr, st = shape_stats(Rs), shape_stats(T)
    for k in ("rg", "r21", "r31"):
        summ[f"shape_{k}_median_R"] = float(np.median(sr[k]))
        summ[f"shape_{k}_median_T"] = float(np.median(st[k]))
        summ[f"shape_{k}_w1"] = w1_1d(sr[k], st[k]) / (unit if k == "rg" else 1.0)
    # lamina (truth only has it)
    if T.lamina is not None:
        lam = np.nanmean(T.lamina.reshape(-1, T.n_loci), 0)
        summ["lamina_vs_depth_spearman_R"] = _spearman(1.0 - arr["rho_mean_R"], lam)
        summ["lamina_vs_depth_spearman_T"] = _spearman(1.0 - arr["rho_mean_T"], lam)
    # territories
    if territory_structures:
        FR, chroms = territory_neighbourhood(Rs, rc, territory_structures)
        FT, _ = territory_neighbourhood(T, rc, territory_structures)
        arr["terr_R"], arr["terr_T"] = FR, FT
        iu = np.triu_indices(len(chroms), 1)
        ok = np.isfinite(FR[iu]) & np.isfinite(FT[iu])
        summ["territory_mae"] = float(np.mean(np.abs(FR[iu][ok] - FT[iu][ok])))
        summ["territory_spearman"] = _spearman(FR[iu], FT[iu])
        summ["territory_mean_R"] = float(np.nanmean(FR[iu]))
        summ["territory_mean_T"] = float(np.nanmean(FT[iu]))
    return arr, summ
