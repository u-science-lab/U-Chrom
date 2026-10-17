"""Loops from single-cell Hi-C maps without pooling them first: SnapHiC (Yu et al. 2021).

Single-cell maps are too sparse for the bulk callers.  SnapHiC imputes every cell, normalises it per genomic
distance and tests each pixel *across cells* against its neighbourhood:

1. **Imputation** (:mod:`uchrom.fea.impute_rwr`): per cell and autosome, the binary contact graph at 10 kb
   (contacts of neighbouring bins left out, neighbouring bins linked) is imputed by a random walk with
   restart (restart probability 0.05) — whole chromosomes (the published SnapHiC, the default) or sliding
   windows (SnapHiC2: Li et al. 2022; ``window="auto"``) — and every diagonal up to ``max_dist + buffer`` is converted to z-scores (the top 1 % left out of the mean
   and standard deviation; ``buffer`` bins at both chromosome ends left out).
2. **Local background**: per cell and pixel, the mean z-score of the square of ``2 outer + 1`` bins around
   the pixel without the inner ``2 inner + 1`` square (11 x 11 minus 5 x 5).
3. **Test**: per pixel, a paired t-test across cells of the z-score against the local background
   (two-sided), Benjamini–Hochberg FDR among the pixels at the same distance; ``outlier_count`` = cells with
   z > 1.96.
4. **Candidates**: separation in ``[min_dist, max_dist]``, mean z > 0, t > 3, FDR < 0.1, more than 10 % of
   the cells outliers, and ``outlier_count`` above 1.33 x its mean over the circle, donut and lower-left
   neighbourhoods and 1.2 x the horizontal and vertical ones (the ring of step 2, split as SnapHiC does);
   candidates on excluded bins (low mappability, blacklist: ``exclude=``) are dropped.
5. **Clusters and summits**: candidates without another one within 2 bins are dropped; the rest are
   clustered by Rodriguez & Laio's density peaks (2014, *Science* 344:1492: density = candidates within
   ``clustering_gap`` diagonal bins, distance to the nearest denser candidate, centres above the elbow of
   density x distance); in each cluster the candidate with the lowest FDR is a summit, and further summits are
   taken after removing the candidates within ``summit_gap`` of each.  Summits of clusters with more than one
   candidate are the loops.

The sums of step 3 are accumulated cell by cell (z, background, their difference and its square, outliers),
so memory is one chromosome's band of sums plus the cells in flight — not cells x pixels.  With
``packages/uchrom-maps`` installed, steps 1-3 run natively (Rust: profile Cholesky + selected inversion per
window, cells and windows in parallel; ``uchrom_maps.snaphic_chrom``); ``BACKEND`` (``"auto"``, ``"native"``,
``"numpy"``) forces either path.  The two agree to rounding (z-scores ~1e-12), and give the same calls.

Deviations from the authors' code (github.com/HuMingLab/SnapHiC v0.2.x, read for the method, not used): the
sliding windows own every pixel (SnapHiC's leave two families of pixels at 0, see
:mod:`uchrom.fea.impute_rwr`; ``SnapHiCParams(sliding_window_holes=True)`` reproduces them, for
comparisons); candidates are ordered by position (start1, start2) where SnapHiC's order follows its file
merges — this only decides ties of equal FDR between neighbouring summits and equidistant denser neighbours
in the clustering; ``window="auto"`` pools the contacts of the cells called on the autosomes.

Validation (uchrom-reproducibility ``benchmarks/toolkit_parity/sc_structures/snaphic_*.py``; Sherlock, AMD EPYC 9754, 32 threads, shared nodes):

* Against the authors' code (SnapHiC v0.2 @782dc2b, its own environment) on the same 100 mES cells and contacts
  (chr17-19, its 10 Mb sliding windows): with ``sliding_window_holes=True`` the z-scores agree to 1.4e-13,
  every outlier count is equal, t to 7e-5 (the precision of its text files) and the 479 loops are identical;
  the default (every pixel imputed) gives 528 loops, 441 identical, 98 % of the authors' within 20 kb.  The
  authors' run took 21 min on 32 processes, this one 5 s.
* Against the paper (Nagano 2017 diploid serum mES cells, the 742 with the most contacts; loops 100 kb - 1 Mb;
  the paper's references: precision against HiCCUPS + MAPS loops, recall of the bulk HiCCUPS loops): whole
  chromosomes 19,324 loops, precision 0.60, recall 0.60, F1 0.60, APA on the bulk map 1.89 (the paper's own
  calls: 15,896, 0.66, 0.60, 0.62, 1.98; 73 % of them within 20 kb of ours); 10 Mb windows: 23,269 loops,
  0.52, 0.59, 0.56, 1.74.  By number of cells (whole chromosomes; the paper's first subset): 50 cells 498 loops
  (516), 100: 2,685 (2,452), 200: 9,178 (6,820).  The windows call 1.5-2x more loops at lower precision, hence
  the default.  HiCCUPS on the pseudo-bulk of the same 742 cells: 396 loops, recall 0.06.
* Run time, 742 cells genome-wide: 98 min whole chromosomes, 4 min windows (6.0 / 3.4 GB peak); the numpy
  path (dense LAPACK per window) is 4-60x slower per cell; whole chromosomes need a dense chromosome x
  chromosome matrix there (~15 GB for chr1 at 10 kb): without the native kernels use ``window="auto"``.

References
----------
Yu, M. et al. (2021) SnapHiC: a computational pipeline to identify chromatin loops from single-cell Hi-C
data. *Nat. Methods* 18:1056-1059.
Li, X. et al. (2022) SnapHiC2: a computationally efficient loop caller for single cell Hi-C data. *Comput.
Struct. Biotechnol. J.* 20:2778-2783.
Rodriguez, A. & Laio, A. (2014) Clustering by fast search and find of density peaks. *Science* 344:1492.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass
from typing import Dict, Optional, Sequence, Tuple, Union

import numpy as np
import pandas as pd

from uchrom.convention import merge_tables, store_and_return

#: steps 1-3: ``"auto"`` (native ``uchrom_maps`` when installed), ``"native"`` or ``"numpy"``
BACKEND = "auto"


@dataclass(frozen=True)
class SnapHiCParams:
    """Knobs of :func:`call_loops_snaphic` (defaults: SnapHiC v0.2's).

    Attributes
    ----------
    rp : float
        Restart probability of the random walk (``--alpha``).
    window, step : int, "auto" or None
        The RWR of whole chromosomes (``None``, the published SnapHiC and the default: its calls match the
        paper's best) or of sliding windows, bp (``"auto"`` = SnapHiC2's 10-100 Mb rule; much faster, more
        loops at lower precision — see the module docstring).
    min_dist, max_dist : int
        Separation of the candidate pixels, bp (``--candidate-lower-distance``, ``--dist``).  The paper
        reports loops in 100 kb - 1 Mb; the software's default upper end is 2 Mb.
    buffer : int
        bp: diagonals imputed beyond ``max_dist`` and bins left out at the chromosome ends (50 kb).
    min_sep : int
        Contacts closer than this many bins are left out before the imputation (2: neighbouring bins).
    trim : float
        Share of each diagonal's largest values left out of its z-score mean / sd.
    outlier : float
        z-score above which a cell counts as an outlier at a pixel (1.96).
    inner, outer : int
        Local background: the ``(2 outer + 1)^2`` square around a pixel minus the ``(2 inner + 1)^2`` one, and
        the ring of the neighbourhood filters (``--local-lower/upper-limit``, ``--postproc-gap-small/large``).
    fdr, tstat, min_outlier_frac : float
        Candidates: FDR (per distance) below ``fdr``, t-statistic above ``tstat``, more than
        ``min_outlier_frac`` of the cells outliers.
    circle, donut, lower_left, horizontal, vertical : float
        ``outlier_count`` must exceed these multiples of its mean over each neighbourhood.
    clustering_gap : int
        Bins: density radius ``sqrt(2) * gap`` of the clustering.
    summit_gap : int
        bp: further summits of a cluster lie farther than this from the previous ones (in either anchor).
    batch : int
        Cells imputed at once by the native path (0: one per thread); memory ~3 bands per cell.
    sliding_window_holes : bool
        Reproduce SnapHiC v0.2's sliding windows exactly, including the pixels they never set (left at 0: sums
        ``i + j = (2k + 1) step`` and ``i + j <= step``).  Only to compare with the authors' code.
    """

    rp: float = 0.05
    window: Union[int, str, None] = None
    step: Optional[int] = None
    min_dist: int = 100_000
    max_dist: int = 2_000_000
    buffer: int = 50_000
    min_sep: int = 2
    trim: float = 0.01
    outlier: float = 1.96
    inner: int = 2
    outer: int = 5
    fdr: float = 0.1
    tstat: float = 3.0
    min_outlier_frac: float = 0.1
    circle: float = 1.33
    donut: float = 1.33
    lower_left: float = 1.33
    horizontal: float = 1.2
    vertical: float = 1.2
    clustering_gap: int = 1
    summit_gap: int = 20_000
    batch: int = 0
    sliding_window_holes: bool = False

    def __post_init__(self):
        if not 0 < self.rp < 1:
            raise ValueError(f"rp={self.rp} must be in (0, 1)")
        if not 0 <= self.min_dist < self.max_dist:
            raise ValueError("need 0 <= min_dist < max_dist")
        if not 0 <= self.inner < self.outer:
            raise ValueError("need 0 <= inner < outer")


# ----------------------------------------------------------------------------------------------------------
# steps 1-3: sums over cells, one chromosome
# ----------------------------------------------------------------------------------------------------------

def _maps_kernels(backend: Optional[str]):
    from uchrom.fea.impute_rwr import _maps_kernels as mk

    return mk(BACKEND if backend is None else backend)


def _local_background_numpy(z: np.ndarray, out_diag: int, inner: int, outer: int) -> np.ndarray:
    """Mean over the defined entries (``0 <= a < b < n``; offsets beyond the band count as 0) of the square of
    half-width ``outer`` minus that of half-width ``inner`` around every pixel ``(i, i + d)``, ``1 <= d <=
    out_diag``."""
    n, W = z.shape
    D = W - 1
    V = np.where(np.isfinite(z), z, 0.0)
    V[:, 0] = 0.0
    P = np.zeros((n, W + 1))
    np.cumsum(V, axis=1, out=P[:, 1:])                   # P[a, t] = sum of V[a, :t]
    i = np.arange(n)[:, None]
    d = np.arange(out_diag + 1)[None, :]

    def box(h):
        s = np.zeros((n, out_diag + 1))
        c = np.zeros((n, out_diag + 1), np.int64)
        for u in range(-h, h + 1):
            a = i + u
            ok_a = (a >= 0) & (a < n)
            ac = np.clip(a, 0, n - 1)
            t0 = np.maximum(d - h - u, 1)
            t1 = np.minimum(d + h - u, n - 1 - a)
            okc = ok_a & (t1 >= t0)
            c += np.where(okc, t1 - t0 + 1, 0)
            hi = np.minimum(t1, D)
            okv = okc & (hi >= t0)
            vals = P[ac, np.clip(hi + 1, 0, D + 1)] - P[ac, np.clip(t0, 0, D + 1)]
            s += np.where(okv, vals, 0.0)
        return s, c

    sb, cb = box(outer)
    ss, cs = box(inner)
    cnt = cb - cs
    with np.errstate(invalid="ignore", divide="ignore"):
        out = np.where(cnt > 0, (sb - ss) / cnt, np.nan)
    out[:, 0] = np.nan
    out[(i + d) >= n] = np.nan
    return out


def _sums_numpy(n: int, cells: Sequence[Tuple[np.ndarray, np.ndarray]], *, rp, window, step, max_diag,
                out_diag, edge, trim, outlier, inner, outer, min_sep, holes=False) -> Dict[str, np.ndarray]:
    from uchrom.fea.impute_rwr import _rwr_band_numpy, _zscore_numpy

    shape = (n, out_diag + 1)
    acc = {k: np.zeros(shape) for k in ("sum_z", "sum_l", "sum_d", "sum_dd")}
    acc["n_out"] = np.zeros(shape, np.int64)
    margin = max(edge, outer)
    i = np.arange(n)[:, None]
    d = np.arange(out_diag + 1)[None, :]
    region = (i >= margin) & (i + d + margin < n) & (d >= 1)
    for ci, cj in cells:
        band = _rwr_band_numpy(n, ci, cj, rp=rp, window=window, step=step, max_diag=max_diag, min_sep=min_sep,
                               chain=True, holes=holes)
        z = _zscore_numpy(band, edge, trim, 1e-6)
        lb = _local_background_numpy(z, out_diag, inner, outer)
        zz = np.where(region, z[:, :out_diag + 1], 0.0)
        ll = np.where(region, lb, 0.0)
        df = zz - ll
        acc["sum_z"] += zz
        acc["sum_l"] += ll
        acc["sum_d"] += df
        acc["sum_dd"] += df * df
        acc["n_out"] += region & (zz > outlier)
    acc["n_cells"] = len(cells)
    return acc


def snaphic_sums(n: int, cells: Sequence[Tuple[np.ndarray, np.ndarray]], *, rp: float = 0.05, window: int = 0,
                 step: int = 0, max_diag: int = 205, out_diag: int = 200, edge: int = 5, trim: float = 0.01,
                 outlier: float = 1.96, inner: int = 2, outer: int = 5, min_sep: int = 2, batch: int = 0,
                 backend: Optional[str] = None, n_threads: int = 0, holes: bool = False) -> Dict[str, np.ndarray]:
    """Steps 1-3 of SnapHiC on one chromosome: the sums over cells that the paired t-test needs.

    ``cells``: per cell ``(i, j)``, its contacts (bins of the chromosome).  Window, step and offsets are in
    bins.  Returns ``(n, out_diag + 1)`` arrays ``sum_z``, ``sum_l`` (local background), ``sum_d`` (z -
    background), ``sum_dd`` (its square), ``n_out`` (cells with z > ``outlier``) — 0 outside the tested
    pixels (``margin <= i``, ``i + d <= n - 1 - margin``, ``margin = max(edge, outer)``) — and ``n_cells``.
    """
    mod = _maps_kernels(backend)
    if mod is None:
        return _sums_numpy(n, cells, rp=rp, window=window, step=step, max_diag=max_diag, out_diag=out_diag,
                           edge=edge, trim=trim, outlier=outlier, inner=inner, outer=outer, min_sep=min_sep,
                           holes=holes)
    lens = np.array([len(c[0]) for c in cells], np.int64)
    ptr = np.r_[0, np.cumsum(lens)].astype(np.int64)
    ci = np.ascontiguousarray(np.concatenate([c[0] for c in cells]) if len(cells) else np.zeros(0), np.int64)
    cj = np.ascontiguousarray(np.concatenate([c[1] for c in cells]) if len(cells) else np.zeros(0), np.int64)
    return dict(mod.snaphic_chrom(int(n), ci, cj, ptr, float(rp), int(window), int(step), int(max_diag),
                                  int(out_diag), int(edge), float(trim), 1e-6, int(inner), int(outer),
                                  float(outlier), int(min_sep), True, int(batch), int(n_threads), bool(holes)))


# ----------------------------------------------------------------------------------------------------------
# statistics, candidates
# ----------------------------------------------------------------------------------------------------------

def _bh(p: np.ndarray) -> np.ndarray:
    """Benjamini–Hochberg adjusted p-values (``statsmodels`` ``fdr_bh``)."""
    m = len(p)
    if not m:
        return p.copy()
    order = np.argsort(p, kind="mergesort")
    q = p[order] * m / np.arange(1, m + 1)
    q = np.minimum.accumulate(q[::-1])[::-1]
    out = np.empty(m)
    out[order] = np.minimum(q, 1.0)
    return out


def _pixel_table(acc: Dict[str, np.ndarray], n: int, edge: int, outer: int) -> pd.DataFrame:
    """Every tested pixel: ``i, j, outlier_count, case_avg, control_avg, tstat, pvalue, fdr_dist``."""
    from scipy.stats import t as tdist

    N = int(acc["n_cells"])
    W = acc["sum_z"].shape[1]
    margin = max(edge, outer)
    ii, dd = np.nonzero(np.ones((n, W), bool))
    keep = (dd >= 1) & (ii >= margin) & (ii + dd + margin < n)
    ii, dd = ii[keep], dd[keep]
    sd_ = acc["sum_d"][ii, dd]
    sdd = acc["sum_dd"][ii, dd]
    with np.errstate(invalid="ignore", divide="ignore"):
        mean = sd_ / N
        var = (sdd - sd_ * sd_ / N) / (N - 1) if N > 1 else np.full(len(sd_), np.nan)
        var = np.where(var < 0, 0.0, var)
        t = mean / np.sqrt(var / N)
    # scipy's ttest_rel: NaN when every difference is equal (SnapHiC: p = 1, t = -1000); +-inf -> p = 0
    p = np.where(np.isnan(t), 1.0, 2 * tdist.sf(np.abs(t), N - 1))
    t = np.where(np.isnan(t), -1000.0, t)
    out = pd.DataFrame({"i": ii, "j": ii + dd, "outlier_count": acc["n_out"][ii, dd].astype(np.int64),
                        "case_avg": acc["sum_z"][ii, dd] / N, "control_avg": acc["sum_l"][ii, dd] / N,
                        "tstat": t, "pvalue": p})
    fdr = np.empty(len(out))
    for d, idx in pd.Series(np.arange(len(out))).groupby(dd).groups.items():
        idx = np.asarray(idx)
        fdr[idx] = _bh(p[idx])
    out["fdr_dist"] = fdr
    return out


_RING = ("circle", "donut", "lower_left", "horizontal", "vertical")


def _neighbourhood_means(px: pd.DataFrame, cand: pd.DataFrame, n: int, gap_small: int, gap_large: int) -> pd.DataFrame:
    """SnapHiC's filters: the mean ``outlier_count`` of the tested pixels in the ring ``gap_small <
    max(|di|, |dj|) <= gap_large`` around each candidate — all of it (circle), the same row (horizontal), the
    same column (vertical), both bins smaller (lower_left), the rest (donut)."""
    W = int(px["j"].sub(px["i"]).max()) + 1 if len(px) else 1
    grid = np.full((n, W), np.nan)
    grid[px["i"].to_numpy(), (px["j"] - px["i"]).to_numpy()] = px["outlier_count"].to_numpy(np.float64)
    ci, cj = cand["i"].to_numpy(), cand["j"].to_numpy()
    sums = {k: np.zeros(len(cand)) for k in _RING}
    cnts = {k: np.zeros(len(cand)) for k in _RING}
    for di in range(-gap_large, gap_large + 1):
        for dj in range(-gap_large, gap_large + 1):
            if abs(di) <= gap_small and abs(dj) <= gap_small:
                continue
            a, b = ci + di, cj + dj
            off = b - a
            ok = (a >= 0) & (a < n) & (off >= 0) & (off < W)
            v = np.full(len(cand), np.nan)
            v[ok] = grid[a[ok], off[ok]]
            have = ~np.isnan(v)
            kind = "lower_left" if (di < 0 and dj < 0) else "vertical" if dj == 0 else "horizontal" if di == 0 \
                else "donut"
            for k in ("circle", kind):
                sums[k][have] += v[have]
                cnts[k][have] += 1
    with np.errstate(invalid="ignore", divide="ignore"):
        return pd.DataFrame({k: sums[k] / cnts[k] for k in _RING}, index=cand.index)


def _candidates(px: pd.DataFrame, n: int, binsize: int, n_cells: int, params: SnapHiCParams,
                exclude: Optional[np.ndarray]) -> pd.DataFrame:
    sep = (px["j"] - px["i"]) * binsize
    cand = px[(sep <= params.max_dist) & (sep >= params.min_dist) & (px["case_avg"] > 0)
              & (px["tstat"] > params.tstat) & (px["fdr_dist"] < params.fdr)
              & (px["outlier_count"] > params.min_outlier_frac * n_cells)]
    if not len(cand):
        return cand.assign(**{k: pd.Series(dtype=float) for k in _RING})
    ring = _neighbourhood_means(px, cand, n, params.inner, params.outer)
    cand = pd.concat([cand, ring], axis=1)
    oc = cand["outlier_count"]
    keep = ((oc > cand["circle"] * params.circle) & (oc > cand["donut"] * params.donut)
            & (oc > cand["lower_left"] * params.lower_left) & (oc > cand["horizontal"] * params.horizontal)
            & (oc > cand["vertical"] * params.vertical))
    cand = cand[keep]
    if exclude is not None and len(cand):
        cand = cand[~exclude[cand["i"].to_numpy()] & ~exclude[cand["j"].to_numpy()]]
    return cand


# ----------------------------------------------------------------------------------------------------------
# clustering (Rodriguez & Laio) and summits
# ----------------------------------------------------------------------------------------------------------

def cluster_candidates(cand: pd.DataFrame, *, clustering_gap: int = 1, summit_gap_bins: int = 2) -> pd.DataFrame:
    """SnapHiC's clustering of the candidate pixels of one chromosome (density peaks; Rodriguez & Laio 2014).

    ``cand``: ``i, j`` (bins) and ``fdr_dist``, in the order ties are broken in.  Returns the clustered
    candidates (singletons — no other candidate within 2 bins — removed) with ``eta_cluster``,
    ``cluster_size``, ``neg_log10_fdr`` (summed over the cluster) and ``summit``.
    """
    from scipy.spatial import cKDTree

    cols = list(cand.columns) + ["eta_cluster", "cluster_size", "neg_log10_fdr", "summit"]
    if len(cand) < 2:
        return pd.DataFrame(columns=cols)
    pts = cand[["i", "j"]].to_numpy(np.int64)
    tree = cKDTree(pts.astype(np.float64))
    dist, _ = tree.query(pts.astype(np.float64), k=2)
    keep = np.rint(dist[:, 1] ** 2) <= 8                             # a neighbour within sqrt(8): 2 bins
    cand = cand[keep].reset_index(drop=True)
    pts = pts[keep]
    k = len(cand)
    if not k:
        return pd.DataFrame(columns=cols)
    P = pts.astype(np.float64)
    tree = cKDTree(P)
    r2 = 2 * clustering_gap ** 2
    rho = np.asarray(tree.query_ball_point(P, math.sqrt(r2) + 1e-9, return_length=True), np.int64)
    delta = np.zeros(k)
    ref = np.arange(k)
    levels = np.unique(rho)
    for lev in levels:
        mine = np.flatnonzero(rho == lev)
        higher = np.flatnonzero(rho > lev)
        if not len(higher):
            # the densest: delta = the largest distance to any candidate
            for x in mine:
                delta[x] = math.sqrt(float(((pts - pts[x]) ** 2).sum(axis=1).max()))
            continue
        ht = cKDTree(P[higher])
        dmin, _ = ht.query(P[mine], k=1)
        for q, x in enumerate(mine):
            # equidistant denser candidates: the first in the table's order
            near = ht.query_ball_point(P[x], dmin[q] + 1e-9)
            d2 = ((pts[higher[near]] - pts[x]) ** 2).sum(axis=1)
            best = np.asarray(near)[d2 == d2.min()]
            ref[x] = int(higher[best].min())
            delta[x] = math.sqrt(float(d2.min()))
    eta = rho * delta
    rank = pd.Series(eta).rank(ascending=False, method="dense").to_numpy()
    teta = (eta / eta.max() + rank / rank.max()) / math.sqrt(2)
    breakpoint = eta[int(np.argmin(teta))]
    clus = np.full(k, -1, np.int64)
    centres = np.flatnonzero(eta > breakpoint)
    clus[centres] = np.arange(1, len(centres) + 1)
    while True:
        new = np.where((clus[ref] != -1) & (eta <= breakpoint), clus[ref], clus)
        if np.array_equal(new, clus):
            break
        clus = new
    cand = cand.assign(eta_cluster=clus)
    nl = -np.log10(cand["fdr_dist"].to_numpy(np.float64))
    grp = cand.groupby("eta_cluster", sort=True)
    cand["cluster_size"] = grp["eta_cluster"].transform("size").to_numpy(np.int64)
    cand["neg_log10_fdr"] = pd.Series(nl).groupby(clus).transform("sum").to_numpy()
    summit = np.zeros(k, np.int64)
    for _, idx in grp.indices.items():
        idx = np.sort(idx)
        alive = np.ones(len(idx), bool)
        fdr = cand["fdr_dist"].to_numpy()[idx]
        ii, jj = pts[idx, 0], pts[idx, 1]
        while alive.any():
            live = np.flatnonzero(alive)
            s = live[int(np.argmin(fdr[live]))]
            summit[idx[s]] = 1
            alive &= (np.abs(ii - ii[s]) > summit_gap_bins) | (np.abs(jj - jj[s]) > summit_gap_bins)
    cand["summit"] = summit
    return cand


# ----------------------------------------------------------------------------------------------------------
# public API
# ----------------------------------------------------------------------------------------------------------

_COLUMNS = ["chrom1", "start1", "end1", "chrom2", "start2", "end2", "score", "outlier_count", "pvalue", "tstat",
            "fdr_dist", "case_avg", "control_avg", "circle", "donut", "horizontal", "vertical", "lower_left",
            "cluster_size", "neg_log10_fdr"]


def _empty_result() -> pd.DataFrame:
    dt = {c: "float64" for c in _COLUMNS}
    dt.update({c: "int64" for c in ("start1", "end1", "start2", "end2", "outlier_count", "cluster_size")})
    dt.update({"chrom1": str, "chrom2": str})
    return pd.DataFrame({c: pd.Series(dtype=dt[c]) for c in _COLUMNS})


def _exclude_mask(exclude, chrom: str, n: int, binsize: int) -> Optional[np.ndarray]:
    """Bins of ``chrom`` to exclude: from a table / BED path with ``chrom, start[, end]`` (every bin a row
    overlaps)."""
    if exclude is None:
        return None
    t = exclude
    if not isinstance(t, pd.DataFrame):
        t = pd.read_csv(t, sep="\t", header=None, comment="#", usecols=[0, 1, 2], names=["chrom", "start", "end"])
    t = t[t["chrom"].astype(str) == chrom]
    m = np.zeros(n, bool)
    if not len(t):
        return m
    s = (t["start"].to_numpy(np.int64) // binsize).clip(0, n - 1)
    e = t["end"].to_numpy(np.int64) if "end" in t.columns else t["start"].to_numpy(np.int64) + binsize
    e = (-(-e // binsize)).clip(1, n)
    for a, b in zip(s, e):
        m[a:max(b, a + 1)] = True
    return m


def call_loops_snaphic(
    cd,
    *,
    contacts: str = "per_cell",
    cells: Optional[Sequence] = None,
    chrom: Union[None, str, Sequence[str]] = None,
    resolution: Optional[int] = None,
    params: Optional[SnapHiCParams] = None,
    exclude=None,
    key_added: Optional[str] = "loops.snaphic",
    copy: bool = False,
    backend: Optional[str] = None,
    n_threads: int = 0,
    timing: Optional[dict] = None,
):
    """Loops from single-cell Hi-C maps, tested across cells: SnapHiC (Yu et al. 2021; SnapHiC2 windows, Li et
    al. 2022).  See the module docstring for the steps and the deviations from the authors' code.

    Parameters
    ----------
    cd : ChromData
        With per-cell maps linked (``cd.link_scool``) or embedded in its atlas store.
    contacts : str
        Key of the per-cell maps (or the path of a ``.scool`` whose cells are named by cell id).
    cells : sequence, optional
        Cells to use (default: every cell of ``cd.cells``).
    chrom : str or sequence, optional
        Chromosomes (default: the autosomes of the maps, as SnapHiC).
    resolution : int, optional
        Bin size the maps must have (SnapHiC: 10 kb); default: the maps' own.
    params : SnapHiCParams, optional
    exclude : DataFrame or path, optional
        Bins excluded from the loop anchors (``chrom, start[, end]``; a BED file): SnapHiC removes 10-kb bins
        of mappability <= 0.8 and the ENCODE blacklist (its ``ext/<genome>_filter_regions.txt``).
    key_added : str or None
        ``cd.results`` / ``cd.intervals`` key (``None``: not stored); the clustered candidates go to
        ``cd.results[key_added + ".candidates"]``.
    copy : bool
        Return a new ``ChromData`` holding the result.
    backend : {"auto", "native", "numpy"}, optional
        Steps 1-3 (default: the module's :data:`BACKEND`).
    n_threads : int
        Threads of the native path (0: all).
    timing : dict, optional
        Filled with seconds per step and the backend.

    Returns
    -------
    DataFrame (``copy=False``) or ChromData (``copy=True``)
        A ``pair`` table, one row per loop summit: ``chrom1, start1, end1, chrom2, start2, end2``, ``score``
        (-log10 ``fdr_dist``), ``outlier_count`` (cells with z > 1.96), ``pvalue``, ``tstat`` (paired t-test
        against the local background), ``fdr_dist`` (BH among the pixels at the same distance),
        ``case_avg`` / ``control_avg`` (mean z-score of the pixel / its background), the neighbourhood means
        ``circle, donut, horizontal, vertical, lower_left`` of ``outlier_count``, ``cluster_size``,
        ``neg_log10_fdr`` (of the cluster).
    """
    from uchrom.fea.impute_rwr import ImputeParams, _autosomes, _cells_and_source, _resolve_window, \
        _ScoolCells, _window_bins, read_cell_pixels

    if copy and key_added is None:
        raise ValueError("call_loops_snaphic(): copy=True needs a key_added")
    params = params or SnapHiCParams()
    timing = {} if timing is None else timing
    t0 = time.perf_counter()
    ids, scool = _cells_and_source(cd, contacts, cells)
    src = _ScoolCells(scool)
    names, binsize, assembly = list(src.chroms), int(src.binsize), src.assembly
    src.close()
    if resolution is not None and int(resolution) != binsize:
        raise ValueError(f"the per-cell maps are at {binsize} bp, not {resolution}: rebin them first")
    chroms = _autosomes(names) if chrom is None else ([chrom] if isinstance(chrom, str) else [str(c) for c in chrom])
    missing = [c for c in chroms if c not in names]
    if missing:
        raise ValueError(f"not in the maps: {missing}")
    ip = ImputeParams(rp=params.rp, window=params.window, step=params.step,
                      max_dist=params.max_dist + params.buffer, min_sep=params.min_sep)
    window_bp = _resolve_window(ip, scool, ids, binsize, _autosomes(names) or chroms)
    w, step = _window_bins(ip, binsize, window_bp)
    out_diag = params.max_dist // binsize
    max_diag = (params.max_dist + params.buffer) // binsize
    edge = params.buffer // binsize
    if out_diag + params.outer > max_diag:
        raise ValueError("buffer must cover the local background: buffer >= outer bins")
    mod = _maps_kernels(backend)
    timing["backend"] = "numpy" if mod is None else "native"
    timing["setup_s"] = time.perf_counter() - t0
    frames, all_cand, info = [], [], {}
    for c in chroms:
        t1 = time.perf_counter()
        n, pix = read_cell_pixels(scool, ids, c)
        t2 = time.perf_counter()
        acc = snaphic_sums(n, pix, rp=params.rp, window=w, step=step, max_diag=max_diag, out_diag=out_diag,
                           edge=edge, trim=params.trim, outlier=params.outlier, inner=params.inner,
                           outer=params.outer, min_sep=params.min_sep, batch=params.batch,
                           backend="numpy" if mod is None else "native", n_threads=n_threads,
                           holes=params.sliding_window_holes)
        t3 = time.perf_counter()
        px = _pixel_table(acc, n, edge, params.outer)
        del acc
        cand = _candidates(px, n, binsize, len(ids), params, _exclude_mask(exclude, c, n, binsize))
        cand = cand.sort_values(["i", "j"], kind="mergesort").reset_index(drop=True)
        cl = cluster_candidates(cand, clustering_gap=params.clustering_gap,
                                summit_gap_bins=params.summit_gap // binsize)
        t4 = time.perf_counter()
        for k, v in (("read_s", t2 - t1), ("impute_test_s", t3 - t2), ("candidates_s", t4 - t3)):
            timing[k] = timing.get(k, 0.0) + v
        info[c] = {"n_bins": int(n), "n_tested": int(len(px)), "n_candidates": int(len(cand)),
                   "n_clustered": int(len(cl))}
        if not len(cl):
            continue
        cl = cl.assign(chrom=c)
        all_cand.append(cl)
        s = cl[(cl["summit"] == 1) & (cl["cluster_size"] > 1)]
        frames.append(_as_pairs(s, c, binsize))
    table = merge_tables(frames, _empty_result())
    table = table.sort_values(["chrom1", "start1", "start2"], kind="mergesort").reset_index(drop=True)[_COLUMNS]
    candidates = (pd.concat(all_cand, ignore_index=True) if all_cand else pd.DataFrame())
    if len(candidates):
        candidates = pd.concat([_as_pairs(candidates, None, binsize),
                                candidates[["eta_cluster", "summit"]].reset_index(drop=True)], axis=1)
    timing["n_cells"] = len(ids)
    inputs = {"contacts": str(contacts), "n_cells": len(ids), "resolution": binsize, "chrom": chroms,
              "window_bp": window_bp, "step_bp": None if window_bp is None else step * binsize,
              "genome_assembly": assembly, "excluded_bins": exclude is not None, "per_chrom": info}
    extra = [] if key_added is None else [(f"{key_added}.candidates", candidates, "table")]
    return store_and_return(cd, table, key_added=key_added, copy=copy, kind="intervals", interval_kind="pair",
                            function="uchrom.strc.loop.call_loops_snaphic", params=params, inputs=inputs,
                            extra=extra)


def _as_pairs(t: pd.DataFrame, chrom: Optional[str], binsize: int) -> pd.DataFrame:
    ch = t["chrom"].astype(str).to_numpy() if chrom is None else chrom
    i = t["i"].to_numpy(np.int64)
    j = t["j"].to_numpy(np.int64)
    out = pd.DataFrame({"chrom1": ch, "start1": i * binsize, "end1": (i + 1) * binsize,
                        "chrom2": ch, "start2": j * binsize, "end2": (j + 1) * binsize})
    fdr = t["fdr_dist"].to_numpy(np.float64)
    out["score"] = -np.log10(np.maximum(fdr, 1e-300))
    for c in ("outlier_count", "pvalue", "tstat", "fdr_dist", "case_avg", "control_avg", *_RING,
              "cluster_size", "neg_log10_fdr"):
        if c in t.columns:
            out[c] = t[c].to_numpy()
    return out


__all__ = ["SnapHiCParams", "call_loops_snaphic", "cluster_candidates", "snaphic_sums", "BACKEND"]
