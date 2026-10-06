"""Population-vs-population metrics of the bulk deconvolution benchmark (design.md section 7(b)).

A reconstructed population R is compared with a truth population T on the same loci
(``population.Population``; R mapped onto T's loci beforehand).  All metrics are invariant to
relabelling the copies of a chromosome within a structure:

* **distance samples of a locus pair**: cis (same chromosome) = one distance per structure and
  copy (same-copy combinations only); trans = one per structure and copy combination
  (4 for diploid) - the pooling IGM's input uses (``pgs_spec.md`` 4.2);
* **scale**: model units are arbitrary, so R is multiplied by **one global factor**
  ``s = sum(m_R m_T) / sum(m_R^2)`` over the per-pair median distances (least squares), reported
  as ``scale``; lengths are then expressed in the truth's **unit** = its median consecutive-locus
  distance.

Metrics (``score_population``):

1. ``pair``: per locus pair, the 1-Wasserstein distance between the R and T distance samples
   (``w1``, from 100 quantiles, in units) on all (or ``max_pairs``) pairs, and the two-sample KS
   statistic (``ks``, exact) on a stratified subsample (``ks_pairs``); summarised as median / IQR,
   by cis genomic-separation band and trans.  Also the Spearman r of per-pair median distances.
2. ``contact``: contact frequency P(d < r) at held-out radii r = ``radii_rel`` x rc (default 0.5, 2;
   the fit uses r = rc): mean absolute error, Pearson r of log10(P + 1e-3), cis / trans.
3. ``triplet``: intra-chromosomal triplets (i < j < k) stratified by span; per (structure, copy)
   all three pairs within rc; ``p3`` = P(all three), ``coop`` = P(ik | ij, jk) - P(ik) (the
   contact of the outer pair given both inner ones, minus its marginal).  R vs T: MAE and
   Spearman over triplets.  Optionally restricted to triplets whose three input probabilities
   are all >= ``sigma`` (``restrained`` set).
4. ``radial``: per locus the distance to the structure centroid, divided by the structure's RMS
   radius (scale- and nucleus-shape-free); W1 per locus (median over loci) and Spearman r of the
   per-locus means.  ``lamina`` (when T has lamina distances and R an envelope in its meta):
   Spearman r of per-locus mean lamina distance and W1 of lamina distances divided by their mean.
5. ``cluster``: structure features = log distances of fixed pairs (cis: mean over copies;
   trans: minimum over copy combinations), imputed / standardised / PCA-reduced on T; k-means
   on T with k chosen by silhouette (k = 2..8) before looking at R; R assigned to the nearest T
   centroid; total-variation distance of the cluster proportions.  ``c2st``: classifier
   two-sample test (histogram gradient boosting when scikit-learn is available, else logistic
   regression in numpy), 5-fold cross-validated ROC-AUC on balanced samples (0.5 =
   indistinguishable).
6. ``nearest``: for every R structure the RMSD to its nearest T cell after similarity
   superposition (mirror allowed) with diploid copy matching per chromosome (alternating: fit
   the superposition, then choose per chromosome the copy permutation; two starts), divided by
   Rg of that T cell; candidates = the ``k_candidates`` nearest T cells in feature space.  And
   the reverse (``coverage``: every T cell to its nearest R structure).

``gain_over_pairwise`` (``aggregate.py``): for a loss metric M,
``(M_pw - M_R) / (M_pw - M_ceiling)`` with M_pw the best pairwise-only baseline and M_ceiling
the held-out truth half: 1 = R reaches the ceiling, 0 = no better than pairwise-only.
"""

from __future__ import annotations

import itertools
import warnings

import numpy as np
from scipy import stats

from population import Population, median_consecutive

warnings.filterwarnings("ignore", message=r".*encountered in matmul")
warnings.filterwarnings("ignore", message="All-NaN slice encountered")
warnings.filterwarnings("ignore", message="Mean of empty slice")

SEP_BANDS_MB = [0, 1, 2, 5, 10, 20, 50, np.inf]


# --------------------------------------------------------------------------- pairs and samples

def all_pairs(pop: Population, max_pairs: int | None = None, seed: int = 0):
    L = pop.n_loci
    i, j = np.triu_indices(L, 1)
    if max_pairs is not None and len(i) > max_pairs:
        k = np.sort(np.random.default_rng(seed).choice(len(i), max_pairs, replace=False))
        i, j = i[k], j[k]
    return i, j


def stratified_pairs(pop: Population, n: int, seed: int = 0):
    """``n`` pairs: half cis stratified over separation bands, half trans (when present)."""
    rng = np.random.default_rng(seed)
    i, j = np.triu_indices(pop.n_loci, 1)
    cis = pop.chrom[i] == pop.chrom[j]
    band = separation_band(pop, i, j)
    groups = [np.flatnonzero(cis & (band == b)) for b in range(len(SEP_BANDS_MB) - 1)]
    groups = [g for g in groups if len(g)]
    trans = np.flatnonzero(~cis)
    n_cis = n if not len(trans) else n // 2
    pick = []
    for g in groups:
        pick.append(rng.choice(g, min(len(g), max(1, n_cis // len(groups))), replace=False))
    if len(trans):
        pick.append(rng.choice(trans, min(len(trans), n - n_cis), replace=False))
    k = np.sort(np.concatenate(pick))
    return i[k], j[k]


def separation_band(pop: Population, i, j) -> np.ndarray:
    mid = (pop.start + pop.end) / 2e6
    sep = np.abs(mid[j] - mid[i])
    b = np.digitize(sep, SEP_BANDS_MB[1:-1])
    return np.where(pop.chrom[i] == pop.chrom[j], b, -1)


def band_label(b: int) -> str:
    if b < 0:
        return "trans"
    lo, hi = SEP_BANDS_MB[b], SEP_BANDS_MB[b + 1]
    return f"cis_{lo:g}-{hi:g}Mb" if np.isfinite(hi) else f"cis_>{lo:g}Mb"


def pair_samples(pop: Population, i, j, cis_only: bool | None = None) -> np.ndarray:
    """Distance samples of pairs (i, j): (n_samples, n_pairs) with NaN.  Rows: cis pairs use
    S x P same-copy rows (the remaining rows NaN), trans pairs S x P x P combinations."""
    X = pop.coords
    S, P = X.shape[:2]
    i, j = np.asarray(i), np.asarray(j)
    cis = pop.chrom[i] == pop.chrom[j]
    out = np.full((S * P * P, len(i)), np.nan, np.float32)
    if cis.any():
        d = np.linalg.norm(X[:, :, i[cis]] - X[:, :, j[cis]], axis=-1)       # (S, P, n)
        out[: S * P, cis] = d.reshape(S * P, -1)
    if (~cis).any():
        d = np.linalg.norm(X[:, :, None, i[~cis]] - X[:, None, :, j[~cis]], axis=-1)   # (S, P, P, n)
        out[:, ~cis] = d.reshape(S * P * P, -1)
    return out


def _chunks(n, size):
    for a in range(0, n, size):
        yield slice(a, min(n, a + size))


# --------------------------------------------------------------------------- scale

def pair_medians(pop: Population, i, j, chunk: int = 2000) -> np.ndarray:
    out = np.empty(len(i))
    for sl in _chunks(len(i), chunk):
        out[sl] = np.nanmedian(pair_samples(pop, i[sl], j[sl]), axis=0)
    return out


def global_scale(R: Population, T: Population, i, j) -> float:
    mr, mt = pair_medians(R, i, j), pair_medians(T, i, j)
    ok = np.isfinite(mr) & np.isfinite(mt)
    return float((mr[ok] * mt[ok]).sum() / (mr[ok] ** 2).sum())


# --------------------------------------------------------------------------- 1. per-pair distributions

def ks_exact(a: np.ndarray, b: np.ndarray) -> float:
    a = np.sort(a[np.isfinite(a)])
    b = np.sort(b[np.isfinite(b)])
    if not len(a) or not len(b):
        return np.nan
    x = np.concatenate([a, b])
    fa = np.searchsorted(a, x, side="right") / len(a)
    fb = np.searchsorted(b, x, side="right") / len(b)
    return float(np.max(np.abs(fa - fb)))


def pair_distribution_metrics(R: Population, T: Population, i, j, unit: float, ks_pairs: int = 20000,
                              n_quantiles: int = 100, chunk: int = 2000, seed: int = 0) -> dict:
    q = (np.arange(n_quantiles) + 0.5) / n_quantiles
    w1 = np.empty(len(i))
    med_r = np.empty(len(i))
    med_t = np.empty(len(i))
    for sl in _chunks(len(i), chunk):
        dr, dt = pair_samples(R, i[sl], j[sl]), pair_samples(T, i[sl], j[sl])
        qr, qt = np.nanquantile(dr, q, axis=0), np.nanquantile(dt, q, axis=0)
        w1[sl] = np.mean(np.abs(qr - qt), axis=0) / unit
        med_r[sl], med_t[sl] = qr[n_quantiles // 2], qt[n_quantiles // 2]
    rng = np.random.default_rng(seed)
    ks_idx = np.sort(rng.choice(len(i), min(ks_pairs, len(i)), replace=False))
    ks = np.full(len(i), np.nan)
    for sl in _chunks(len(ks_idx), chunk):
        k = ks_idx[sl]
        dr, dt = pair_samples(R, i[k], j[k]), pair_samples(T, i[k], j[k])
        for c in range(len(k)):
            ks[k[c]] = ks_exact(dr[:, c], dt[:, c])
    band = separation_band(T, i, j)
    out = {"w1_median": float(np.nanmedian(w1)), "w1_iqr": _iqr(w1), "ks_median": float(np.nanmedian(ks)),
           "ks_iqr": _iqr(ks), "n_pairs": int(len(i)), "n_pairs_ks": int(len(ks_idx)),
           "median_distance_spearman": _spearman(med_r, med_t), "by_band": {}}
    for b in np.unique(band):
        s = band == b
        out["by_band"][band_label(int(b))] = {"n": int(s.sum()), "w1_median": float(np.nanmedian(w1[s])),
                                              "ks_median": float(np.nanmedian(ks[s])) if np.isfinite(ks[s]).any() else None,
                                              "median_distance_spearman": _spearman(med_r[s], med_t[s])}
    cis = band >= 0
    for name, s in (("cis", cis), ("trans", ~cis)):
        if s.any():
            out[f"w1_median_{name}"] = float(np.nanmedian(w1[s]))
            out[f"ks_median_{name}"] = float(np.nanmedian(ks[s])) if np.isfinite(ks[s]).any() else None
    return out


def _iqr(x) -> list:
    x = x[np.isfinite(x)]
    return [float(np.quantile(x, 0.25)), float(np.quantile(x, 0.75))] if len(x) else [None, None]


def _spearman(a, b) -> float | None:
    ok = np.isfinite(a) & np.isfinite(b)
    if ok.sum() < 3:
        return None
    return float(stats.spearmanr(a[ok], b[ok])[0])


def _pearson(a, b) -> float | None:
    ok = np.isfinite(a) & np.isfinite(b)
    if ok.sum() < 3 or np.std(a[ok]) == 0 or np.std(b[ok]) == 0:
        return None
    return float(np.corrcoef(a[ok], b[ok])[0, 1])


# --------------------------------------------------------------------------- 2. contact frequencies

def contact_frequency(pop: Population, i, j, r, chunk: int = 2000) -> np.ndarray:
    out = np.empty(len(i))
    r = np.broadcast_to(np.asarray(r, float), (len(i),))
    for sl in _chunks(len(i), chunk):
        d = pair_samples(pop, i[sl], j[sl])
        ok = np.isfinite(d)
        out[sl] = (ok & (d < r[sl])).sum(0) / np.maximum(ok.sum(0), 1)
    return out


def contact_metrics(R: Population, T: Population, i, j, rc, radii_rel=(0.5, 2.0)) -> dict:
    cis = T.chrom[i] == T.chrom[j]
    out = {}
    for rr in radii_rel:
        r = np.asarray(rc, float) * rr
        cr, ct = contact_frequency(R, i, j, r), contact_frequency(T, i, j, r)
        res = {"mae": float(np.mean(np.abs(cr - ct))), "pearson_log": _pearson(np.log10(cr + 1e-3), np.log10(ct + 1e-3)),
               "spearman": _spearman(cr, ct), "mean_R": float(cr.mean()), "mean_T": float(ct.mean())}
        for name, s in (("cis", cis), ("trans", ~cis)):
            if s.any():
                res[f"mae_{name}"] = float(np.mean(np.abs(cr[s] - ct[s])))
                res[f"pearson_log_{name}"] = _pearson(np.log10(cr[s] + 1e-3), np.log10(ct[s] + 1e-3))
        out[f"r{rr:g}"] = res
    return out


# --------------------------------------------------------------------------- 3. three-body

def sample_triplets(pop: Population, n: int = 20000, seed: int = 0, prob=None, sigma: float | None = None,
                    max_span_mb: float = np.inf):
    """Intra-chromosomal triplets i < j < k, stratified by the span (k - i) over SEP_BANDS_MB;
    with ``prob`` (L x L input probabilities) and ``sigma``: only triplets whose three pairwise
    probabilities are >= sigma."""
    rng = np.random.default_rng(seed)
    mid = (pop.start + pop.end) / 2e6
    out = []
    per_band = max(1, n // (len(SEP_BANDS_MB) - 1))
    chroms = np.unique(pop.chrom)
    for b in range(len(SEP_BANDS_MB) - 1):
        lo, hi = SEP_BANDS_MB[b], min(SEP_BANDS_MB[b + 1], max_span_mb)
        got = []
        for _ in range(per_band * 20):
            if len(got) >= per_band:
                break
            c = chroms[rng.integers(len(chroms))]
            loc = np.flatnonzero(pop.chrom == c)
            if len(loc) < 3:
                continue
            a, cc = np.sort(rng.choice(loc, 2, replace=False))
            span = mid[cc] - mid[a]
            if not (lo <= span < hi) or cc - a < 2:
                continue
            m = rng.integers(a + 1, cc)
            if prob is not None and sigma is not None and min(prob[a, m], prob[m, cc], prob[a, cc]) < sigma:
                continue
            got.append((a, m, cc))
        out += got
    if prob is not None and sigma is not None:   # exhaustive fallback for the restrained set
        if len(out) < n // 4:
            L = pop.n_loci
            same = pop.chrom[:, None] == pop.chrom[None]
            A = (np.asarray(prob) >= sigma) & same
            np.fill_diagonal(A, False)
            cand = []
            for a in range(L):
                nb = np.flatnonzero(A[a, a + 1:]) + a + 1
                for m_, cc_ in itertools.combinations(nb, 2):
                    if A[m_, cc_]:
                        cand.append((a, m_, cc_))
            if cand:
                cand = np.array(cand)
                out = [tuple(x) for x in cand[rng.choice(len(cand), min(n, len(cand)), replace=False)]]
    t = np.array(sorted(set(out)), dtype=np.int64).reshape(-1, 3)
    return t


def triplet_frequencies(pop: Population, trip: np.ndarray, r, chunk: int = 5000) -> dict:
    """Per triplet: p_ij, p_jk, p_ik, p3 (all three) over (structure, copy) samples with all
    three loci present."""
    X = pop.coords
    r = np.asarray(r, float)
    res = {k: np.empty(len(trip)) for k in ("pij", "pjk", "pik", "p3", "n")}
    inner = np.empty(len(trip))
    for sl in _chunks(len(trip), chunk):
        a, b, c = trip[sl, 0], trip[sl, 1], trip[sl, 2]
        rr = r if r.ndim == 0 else None
        dab = np.linalg.norm(X[:, :, a] - X[:, :, b], axis=-1)
        dbc = np.linalg.norm(X[:, :, b] - X[:, :, c], axis=-1)
        dac = np.linalg.norm(X[:, :, a] - X[:, :, c], axis=-1)
        ok = np.isfinite(dab) & np.isfinite(dbc) & np.isfinite(dac)
        if rr is None:
            rab, rbc, rac = r[a, b], r[b, c], r[a, c]
        else:
            rab = rbc = rac = rr
        cab, cbc, cac = (dab < rab) & ok, (dbc < rbc) & ok, (dac < rac) & ok
        n = ok.sum((0, 1))
        nn = np.maximum(n, 1)
        res["pij"][sl] = cab.sum((0, 1)) / nn
        res["pjk"][sl] = cbc.sum((0, 1)) / nn
        res["pik"][sl] = cac.sum((0, 1)) / nn
        res["p3"][sl] = (cab & cbc & cac).sum((0, 1)) / nn
        res["n"][sl] = n
        inner[sl] = (cab & cbc).sum((0, 1)) / nn
    # cooperativity: P(ik | ij and jk) - P(ik)
    with np.errstate(invalid="ignore", divide="ignore"):
        res["coop"] = np.where(inner > 0, res["p3"] / inner - res["pik"], np.nan)
    return res


def triplet_metrics(R: Population, T: Population, trip: np.ndarray, rc, min_samples: int = 20) -> dict:
    fr, ft = triplet_frequencies(R, trip, rc), triplet_frequencies(T, trip, rc)
    ok = (fr["n"] >= min_samples) & (ft["n"] >= min_samples)
    out = {"n_triplets": int(ok.sum())}
    if not ok.any():
        return out
    out.update({"p3_mae": float(np.mean(np.abs(fr["p3"][ok] - ft["p3"][ok]))),
                "p3_spearman": _spearman(fr["p3"][ok], ft["p3"][ok]),
                "p3_mean_R": float(fr["p3"][ok].mean()), "p3_mean_T": float(ft["p3"][ok].mean())})
    c = ok & np.isfinite(fr["coop"]) & np.isfinite(ft["coop"])
    if c.sum() >= 3:
        out.update({"coop_mae": float(np.mean(np.abs(fr["coop"][c] - ft["coop"][c]))),
                    "coop_spearman": _spearman(fr["coop"][c], ft["coop"][c]), "n_coop": int(c.sum()),
                    "coop_mean_R": float(np.mean(fr["coop"][c])), "coop_mean_T": float(np.mean(ft["coop"][c]))})
    return out


# --------------------------------------------------------------------------- 4. radial

def radial_positions(pop: Population) -> np.ndarray:
    """(S, P, L) distance to the structure centroid / RMS radius of the structure."""
    X = pop.coords.astype(np.float64)
    S = X.shape[0]
    flat = X.reshape(S, -1, 3)
    cen = np.nanmean(flat, axis=1)
    d = np.linalg.norm(X - cen[:, None, None], axis=-1)
    rms = np.sqrt(np.nanmean(d.reshape(S, -1) ** 2, axis=1))
    return d / rms[:, None, None]


def envelope_distance(pop: Population) -> np.ndarray | None:
    """Distance to the model envelope from ``meta['nucleus']``: {"shape": "sphere", "radius": R}
    or {"shape": "ellipsoid", "semiaxes": [a, b, c]} (centre at the origin; ellipsoid distance
    approximated radially: (1 - |x / abc|) * |x| / |x / abc|)."""
    nuc = pop.meta.get("nucleus")
    if not nuc:
        return None
    X = pop.coords.astype(np.float64)
    if nuc.get("shape") == "sphere":
        return nuc["radius"] - np.linalg.norm(X, axis=-1)
    ax = np.asarray(nuc["semiaxes"], float)
    rel = np.linalg.norm(X / ax, axis=-1)
    return (1.0 - rel) * np.linalg.norm(X, axis=-1) / np.maximum(rel, 1e-12)


def _per_locus_w1(a: np.ndarray, b: np.ndarray, n_quantiles: int = 50) -> np.ndarray:
    q = (np.arange(n_quantiles) + 0.5) / n_quantiles
    A = a.reshape(-1, a.shape[-1])
    B = b.reshape(-1, b.shape[-1])
    return np.mean(np.abs(np.nanquantile(A, q, axis=0) - np.nanquantile(B, q, axis=0)), axis=0)


def radial_metrics(R: Population, T: Population) -> dict:
    rr, rt = radial_positions(R), radial_positions(T)
    w1 = _per_locus_w1(rr, rt)
    out = {"w1_median": float(np.nanmedian(w1)),
           "mean_spearman": _spearman(np.nanmean(rr.reshape(-1, rr.shape[-1]), 0), np.nanmean(rt.reshape(-1, rt.shape[-1]), 0))}
    er = envelope_distance(R)
    if er is not None and T.lamina is not None:
        lt = T.lamina.astype(np.float64)
        mr = np.nanmean(er.reshape(-1, er.shape[-1]), 0)
        mt = np.nanmean(lt.reshape(-1, lt.shape[-1]), 0)
        out["lamina_mean_spearman"] = _spearman(mr, mt)
        out["lamina_w1_rel_median"] = float(np.nanmedian(_per_locus_w1(er / np.nanmean(er), lt / np.nanmean(lt))))
    return out


# --------------------------------------------------------------------------- 5. subpopulations

def structure_features(pop: Population, i, j) -> np.ndarray:
    """(S, n_pairs) log distances; cis: mean over copies, trans: min over copy combinations."""
    X = pop.coords
    cis = pop.chrom[i] == pop.chrom[j]
    F = np.full((X.shape[0], len(i)), np.nan)
    if cis.any():
        d = np.linalg.norm(X[:, :, i[cis]] - X[:, :, j[cis]], axis=-1)
        F[:, cis] = np.nanmean(np.log(np.maximum(d, 1e-6)), axis=1)
    if (~cis).any():
        d = np.linalg.norm(X[:, :, None, i[~cis]] - X[:, None, :, j[~cis]], axis=-1)
        F[:, ~cis] = np.nanmin(np.log(np.maximum(d, 1e-6)).reshape(X.shape[0], -1, int((~cis).sum())), axis=1)
    return F


class FeatureSpace:
    """Imputation, standardisation and PCA fitted on the truth features."""

    def __init__(self, F_T: np.ndarray, n_components: int = 20):
        self.mu = np.nanmean(F_T, 0)
        self.mu = np.where(np.isfinite(self.mu), self.mu, 0.0)
        Z = np.where(np.isfinite(F_T), F_T, self.mu)
        self.sd = Z.std(0)
        self.sd[self.sd == 0] = 1.0
        Z = (Z - self.mu) / self.sd
        u, s, vt = np.linalg.svd(Z, full_matrices=False)
        self.V = vt[: min(n_components, len(s))].T

    def standardise(self, F):
        Z = np.where(np.isfinite(F), F, self.mu)
        return (Z - self.mu) / self.sd

    def __call__(self, F):
        return self.standardise(F) @ self.V


def kmeans(Z: np.ndarray, k: int, seed: int = 0, n_init: int = 5, n_iter: int = 100):
    rng = np.random.default_rng(seed)
    best = None
    for _ in range(n_init):
        cen = [Z[rng.integers(len(Z))]]
        for _k in range(1, k):                        # k-means++
            d2 = np.min(((Z[:, None] - np.array(cen)[None]) ** 2).sum(-1), 1)
            cen.append(Z[rng.choice(len(Z), p=d2 / d2.sum())])
        cen = np.array(cen)
        for _i in range(n_iter):
            lab = np.argmin(((Z[:, None] - cen[None]) ** 2).sum(-1), 1)
            new = np.array([Z[lab == c].mean(0) if (lab == c).any() else cen[c] for c in range(k)])
            if np.allclose(new, cen):
                break
            cen = new
        inertia = float(((Z - cen[lab]) ** 2).sum())
        if best is None or inertia < best[2]:
            best = (lab, cen, inertia)
    return best[0], best[1]


def silhouette(Z: np.ndarray, lab: np.ndarray, max_n: int = 2000, seed: int = 0) -> float:
    rng = np.random.default_rng(seed)
    idx = rng.choice(len(Z), min(max_n, len(Z)), replace=False)
    Z, lab = Z[idx], lab[idx]
    D = np.sqrt(((Z[:, None] - Z[None]) ** 2).sum(-1))
    s = []
    for a in range(len(Z)):
        same = lab == lab[a]
        if same.sum() <= 1:
            s.append(0.0)
            continue
        ai = D[a, same].sum() / (same.sum() - 1)
        bi = min(D[a, lab == c].mean() for c in np.unique(lab) if c != lab[a])
        s.append((bi - ai) / max(ai, bi))
    return float(np.mean(s))


def cluster_metrics(ZR: np.ndarray, ZT: np.ndarray, ks=range(2, 9), seed: int = 0) -> dict:
    best = None
    sil = {}
    for k in ks:
        if k >= len(ZT):
            break
        lab, cen = kmeans(ZT, k, seed)
        sil[k] = silhouette(ZT, lab, seed=seed)
        if best is None or sil[k] > sil[best[0]]:
            best = (k, lab, cen)
    k, lab, cen = best
    labR = np.argmin(((ZR[:, None] - cen[None]) ** 2).sum(-1), 1)
    pt = np.bincount(lab, minlength=k) / len(lab)
    pr = np.bincount(labR, minlength=k) / len(labR)
    return {"k": int(k), "silhouette": sil, "prop_T": pt.tolist(), "prop_R": pr.tolist(),
            "tv": float(0.5 * np.abs(pt - pr).sum())}


def _auc(y, s) -> float:
    r = stats.rankdata(s)
    n1 = (y == 1).sum()
    n0 = len(y) - n1
    return float((r[y == 1].sum() - n1 * (n1 + 1) / 2) / (n1 * n0))


def _logreg(Xtr, ytr, Xte, l2: float = 1.0, n_iter: int = 200):
    w = np.zeros(Xtr.shape[1] + 1)
    A = np.hstack([Xtr, np.ones((len(Xtr), 1))])
    for _ in range(n_iter):                         # Newton / IRLS
        p = 1 / (1 + np.exp(-A @ w))
        g = A.T @ (p - ytr) + l2 * np.r_[w[:-1], 0]
        H = (A * (p * (1 - p))[:, None]).T @ A + l2 * np.eye(len(w))
        step = np.linalg.solve(H, g)
        w -= step
        if np.abs(step).max() < 1e-6:
            break
    return np.hstack([Xte, np.ones((len(Xte), 1))]) @ w


def c2st(ZR: np.ndarray, ZT: np.ndarray, max_n: int = 2000, folds: int = 5, seed: int = 0) -> dict:
    rng = np.random.default_rng(seed)
    n = min(len(ZR), len(ZT), max_n)
    X = np.vstack([ZR[rng.choice(len(ZR), n, replace=False)], ZT[rng.choice(len(ZT), n, replace=False)]])
    y = np.r_[np.ones(n), np.zeros(n)]
    fold = np.r_[rng.permutation(n) % folds, rng.permutation(n) % folds]
    try:
        from sklearn.ensemble import HistGradientBoostingClassifier
        clf_name = "HistGradientBoostingClassifier"

        def fit_predict(a, b, c):
            m = HistGradientBoostingClassifier(max_iter=200, random_state=seed).fit(a, b)
            return m.predict_proba(c)[:, 1]
    except ImportError:
        clf_name = "logistic regression (numpy)"

        def fit_predict(a, b, c):
            return _logreg(a, b, c)
    score = np.empty(len(y))
    for f in range(folds):
        te = fold == f
        score[te] = fit_predict(X[~te], y[~te], X[te])
    return {"auc": _auc(y, score), "n_per_class": int(n), "classifier": clf_name, "folds": folds}


# --------------------------------------------------------------------------- 6. nearest true cell

def _superpose(A, B, mirror=True):
    """Similarity superposition of B onto A (rows present in both); returns (rmsd, fitted B)."""
    ok = np.isfinite(A).all(1) & np.isfinite(B).all(1)
    a, b = A[ok], B[ok]
    ca, cb = a.mean(0), b.mean(0)
    a0, b0 = a - ca, b - cb
    best = None
    for sm in ((1.0, -1.0) if mirror else (1.0,)):
        bb = b0 * sm
        u, sv, vt = np.linalg.svd(bb.T @ a0)
        d = np.sign(np.linalg.det(u @ vt)) or 1.0
        D = np.diag([1.0, 1.0, d])
        Rm = u @ D @ vt
        s = float((sv * np.diag(D)).sum() / max((bb ** 2).sum(), 1e-300))
        r = float(np.sqrt(((s * bb @ Rm - a0) ** 2).sum(1).mean()))
        if best is None or r < best[0]:
            best = (r, lambda Y, sm=sm, s=s, Rm=Rm: s * ((Y - cb) * sm) @ Rm + ca)
    return best


def _shape_swap(T, Y, masks) -> np.ndarray:
    """Rotation-free start: per chromosome, pair the copies whose internal distance matrices
    correlate best."""
    out = np.zeros(len(masks), bool)
    for c, m in enumerate(masks):
        def dm(X):
            d = np.linalg.norm(X[:, None] - X[None], axis=-1)
            return d[np.triu_indices(len(X), 1)]
        dT = [dm(T[p][m]) for p in (0, 1)]
        dY = [dm(Y[p][m]) for p in (0, 1)]

        def cor(a, b):
            ok = np.isfinite(a) & np.isfinite(b)
            return np.corrcoef(a[ok], b[ok])[0, 1] if ok.sum() > 2 and a[ok].std() > 0 and b[ok].std() > 0 else 0.0
        keep = cor(dT[0], dY[0]) + cor(dT[1], dY[1])
        swap = cor(dT[0], dY[1]) + cor(dT[1], dY[0])
        out[c] = swap > keep
    return out


def diploid_rmsd(T: np.ndarray, Y: np.ndarray, chrom: np.ndarray, n_iter: int = 10) -> float:
    """RMSD of Y (P, L, 3) onto T (P, L, 3) with per-chromosome copy matching (P = 2) or no
    matching (P = 1); similarity superposition with mirror; alternating fit / copy assignment
    from three starts (identity, all swapped, internal-shape matching); best result."""
    P = T.shape[0]
    if P == 1:
        return _superpose(T[0], Y[0])[0]
    chroms = np.unique(chrom)
    masks = [chrom == c for c in chroms]
    best = np.inf
    starts = [np.zeros(len(chroms), bool), np.ones(len(chroms), bool), _shape_swap(T, Y, masks)]
    for start in starts:
        swap = start.copy()
        for _ in range(n_iter):
            Ym = Y.copy()
            for c, m in enumerate(masks):
                if swap[c]:
                    Ym[:, m] = Y[::-1][:, m]
            r, fit = _superpose(T.reshape(-1, 3), Ym.reshape(-1, 3))
            Yf = fit(Y.reshape(-1, 3)).reshape(Y.shape)
            new = swap.copy()
            for c, m in enumerate(masks):
                e0 = np.nansum((Yf[:, m] - T[:, m]) ** 2)
                e1 = np.nansum((Yf[::-1][:, m] - T[:, m]) ** 2)
                new[c] = e1 < e0
            if (new == swap).all():
                break
            swap = new
        best = min(best, r)
    return float(best)


def _rg(X) -> float:
    Y = X.reshape(-1, 3)
    Y = Y[np.isfinite(Y).all(1)]
    return float(np.sqrt(((Y - Y.mean(0)) ** 2).sum(1).mean()))


def nearest_metrics(R: Population, T: Population, ZR, ZT, k_candidates: int = 20, max_query: int = 500,
                    seed: int = 0) -> dict:
    rng = np.random.default_rng(seed)
    out = {}
    for name, Q, ZQ, Ref, ZRef in (("nearest", R, ZR, T, ZT), ("coverage", T, ZT, R, ZR)):
        qi = rng.choice(Q.n_structures, min(max_query, Q.n_structures), replace=False)
        vals = []
        for q in qi:
            d = ((ZRef - ZQ[q]) ** 2).sum(1)
            cand = np.argsort(d)[:k_candidates]
            best = np.inf
            for c in cand:
                t_, y_ = (Ref.coords[c], Q.coords[q]) if name == "nearest" else (Q.coords[q], Ref.coords[c])
                r = diploid_rmsd(t_.astype(np.float64), y_.astype(np.float64), T.chrom)
                best = min(best, r / _rg(t_))
            vals.append(best)
        vals = np.array(vals)
        out[f"{name}_rmsd_rel_median"] = float(np.median(vals))
        out[f"{name}_rmsd_rel_iqr"] = _iqr(vals)
        out[f"{name}_n"] = int(len(vals))
    out["k_candidates"] = k_candidates
    return out


# --------------------------------------------------------------------------- all metrics

def score_population(R: Population, T: Population, *, rc, prob=None, sigma: float = 0.01, max_pairs=None,
                     ks_pairs: int = 20000, n_triplets: int = 20000, n_feature_pairs: int = 2000,
                     max_query: int = 500, k_candidates: int = 20, seed: int = 0, skip=()) -> dict:
    """All metrics of R vs T (same loci).  ``rc``: contact distance of the fit in T's units
    (scalar or (L, L)); ``prob``: the input probability matrix (L, L) for the restrained
    triplet set."""
    assert R.n_loci == T.n_loci and (R.chrom == T.chrom).all(), "R must be on T's loci"
    unit = median_consecutive(T)
    i, j = all_pairs(T, max_pairs, seed)
    si, sj = all_pairs(T, 50000, seed)
    s = global_scale(R, T, si, sj)
    Rs = R.scaled(s)
    rc_arr = np.asarray(rc, float)
    rc_pairs = rc_arr if rc_arr.ndim == 0 else rc_arr[i, j]
    out = {"scale": s, "unit_nm": unit, "n_R": R.n_structures, "n_T": T.n_structures, "rc_median": float(np.median(rc_arr))}
    if "pair" not in skip:
        out["pair"] = pair_distribution_metrics(Rs, T, i, j, unit, ks_pairs=ks_pairs, seed=seed)
    if "contact" not in skip:
        out["contact"] = contact_metrics(Rs, T, i, j, rc_pairs)
    if "triplet" not in skip:
        trip = sample_triplets(T, n_triplets, seed)
        out["triplet"] = triplet_metrics(Rs, T, trip, rc_arr)
        if prob is not None:
            tr2 = sample_triplets(T, n_triplets, seed, prob=np.asarray(prob), sigma=sigma)
            out["triplet_restrained"] = dict(triplet_metrics(Rs, T, tr2, rc_arr), sigma=sigma) if len(tr2) else {"n_triplets": 0}
    if "radial" not in skip:
        out["radial"] = radial_metrics(Rs, T)
    if not {"cluster", "c2st", "nearest"} <= set(skip):
        fi, fj = stratified_pairs(T, n_feature_pairs, seed)
        FT, FR = structure_features(T, fi, fj), structure_features(Rs, fi, fj)
        fs = FeatureSpace(FT)
        ZT, ZR = fs(FT), fs(FR)
        if "cluster" not in skip:
            out["cluster"] = cluster_metrics(ZR, ZT, seed=seed)
        if "c2st" not in skip:
            out["c2st"] = c2st(fs.standardise(FR), fs.standardise(FT), seed=seed)
        if "nearest" not in skip:
            out["nearest"] = nearest_metrics(Rs, T, ZR, ZT, k_candidates, max_query, seed)
    return out


HEADLINE = {  # metric path -> (short name, direction: "loss" lower better | "gain" higher better | "auc")
    "pair.w1_median": ("w1", "loss"),
    "pair.ks_median": ("ks", "loss"),
    "pair.w1_median_trans": ("w1_trans", "loss"),
    "contact.r0.5.mae": ("cf_0.5rc_mae", "loss"),
    "contact.r2.mae": ("cf_2rc_mae", "loss"),
    "triplet.p3_mae": ("p3_mae", "loss"),
    "triplet.coop_mae": ("coop_mae", "loss"),
    "triplet_restrained.p3_mae": ("p3_restr_mae", "loss"),
    "radial.w1_median": ("radial_w1", "loss"),
    "cluster.tv": ("cluster_tv", "loss"),
    "c2st.auc": ("c2st_auc", "auc"),
    "nearest.nearest_rmsd_rel_median": ("nn_rmsd", "loss"),
    "nearest.coverage_rmsd_rel_median": ("cov_rmsd", "loss"),
}


def get_path(d: dict, path: str):
    cur = d
    for p in path.split("."):
        if not isinstance(cur, dict):
            return None
        if p not in cur:
            # keys like "r0.5" contain dots: try joining
            return _get_dotted(d, path)
        cur = cur[p]
    return cur


def _get_dotted(d, path):
    parts = path.split(".")
    for k in range(len(parts), 0, -1):
        key = ".".join(parts[:k])
        if isinstance(d, dict) and key in d:
            rest = ".".join(parts[k:])
            return d[key] if not rest else _get_dotted(d[key], rest)
    return None
