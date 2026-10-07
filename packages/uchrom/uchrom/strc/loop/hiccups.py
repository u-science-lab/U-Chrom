"""Loops of a Hi-C map by local enrichment: HiCCUPS (Rao et al. 2014), in the formulation of cooltools ``dots``.

A loop is a pixel with more contacts than its neighbourhood predicts.  For every pixel ``(i, j)`` of the
band ``0 < j - i < max_dist`` HiCCUPS computes four *locally adjusted expected* counts

    λ_k(i, j) = E_raw(i, j) · Σ_{K_k}(O_bal) / Σ_{K_k}(E_bal),     k ∈ {donut, vertical, horizontal, lowleft}

where ``E_bal`` is the expected balanced contact at the pixel's separation (the mean per diagonal,
:func:`uchrom.fea.band.expected_cis`), ``E_raw = E_bal / (w_i w_j)`` the same in raw counts, and the sums run
over the footprint ``K_k`` of a kernel around the pixel (half-widths ``w`` outside, ``p`` inside the peak):

- *donut*: the ``(2w+1)²`` square without the ``(2p+1)²`` peak square and without the pixel's row and column;
- *vertical* / *horizontal*: 3-pixel-wide strips through the pixel, without the peak square;
- *lowleft*: the quadrant towards the diagonal (rows below, columns left), without the peak square.

The observed raw count is tested against Poisson(λ) for each kernel.  As in HiCCUPS, the pixels are grouped
by λ into log-spaced *λ-chunks* (edges ``2^(k/3)``), every pixel of a chunk is tested with the chunk's upper
edge as λ, and the Benjamini–Hochberg FDR is controlled within each chunk (from a histogram of the counts in
the chunk: one pass over the map).  A pixel is *enriched* when it passes for all four kernels.  Enriched
pixels within ``cluster_radius`` are grouped greedily from the brightest down (HiCCUPS' clustering: a pixel
joins while it lies within the radius + the cluster's current extent of the running centroid); the
brightest pixel of a cluster is the loop, reported with the centroid, radius and size of its cluster.
The Rao 2014 filter then keeps loops at least 1.5× / 1.75× / 2× above the expecteds and, for singletons, a
summed q-value ≤ 0.02.  Calls at several resolutions can be merged as Rao 2014 merged their 5 / 10 / 25 kb
lists (:func:`merge_resolutions`).

Implementation (numpy / scipy only).  The band of one chromosome is read once (:func:`uchrom.fea.band.read_band`)
and scored in dense row tiles; the kernel sums are rectangle sums on summed-area tables (each kernel is a
union of 2-6 rectangles), so a pixel costs O(1) instead of O(w²).  A pixel is only scored when no bin of its
kernels' footprint is masked, on an ignored diagonal, below the diagonal or beyond the chromosome (cooltools'
``max_nans_tolerated=1``) — pixels closer to the diagonal than ``2w + 2`` bins are not tested.  The
histograms of all chromosomes of a call are pooled (genome-wide FDR, as HiCCUPS and cooltools do), so the
result for one chromosome depends on which chromosomes are called together.

Deviations from cooltools ``dots`` (deliberate): the default p-value is HiCCUPS' ``P(X ≥ obs)``
(cooltools: ``P(X > obs)``, one count more lenient; ``params.pvalue="cooltools"`` reproduces it); the
clustering is HiCCUPS' greedy one (cooltools uses sklearn's Birch); λ-chunks are added as needed instead of
failing when the largest λ exceeds ``2^13``.

References
----------
Rao, S. S. P. et al. (2014) A 3D map of the human genome at kilobase resolution reveals principles of
chromatin looping. *Cell* 159:1665-1680 (HiCCUPS, Extended Experimental Procedures).
Open2C et al. (2024) Cooltools: enabling high-resolution Hi-C analysis in Python. *PLoS Comput. Biol.*
20:e1012067 (``cooltools.dots``).
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple, Union

import numpy as np
import pandas as pd

from uchrom.convention import merge_tables, resolve_chroms, store_and_return

KERNELS = ("donut", "vertical", "horizontal", "lowleft")

#: cells (rows x columns) of one dense tile; sets the working memory (~13 arrays of this size)
TILE_CELLS = 2_000_000


@dataclass(frozen=True)
class HiccupsParams:
    """Knobs of :func:`call_loops_hiccups` (defaults: Rao et al. 2014 / cooltools ``dots``).

    Attributes
    ----------
    p, w : int or None
        Half-widths (bins) of the peak and of the window of the kernels.  ``None``: Rao 2014's choice for
        the resolution — ``p=4, w=7`` at 4-8 kb, ``p=2, w=5`` at 8-18 kb, ``p=1, w=3`` at 18-28 kb.
    max_dist : int
        Largest separation of a tested pixel, bp (pixels with ``j - i < max_dist / binsize``; cooltools'
        ``max_loci_separation``).
    fdr : float
        Benjamini–Hochberg FDR within each λ-chunk.
    ignore_diags : int
        Diagonals whose expected is undefined (cooltools ``expected_cis(ignore_diags=2)``); kernels may not
        touch them.
    lambda_base : float
        Ratio of successive λ-chunk edges (``2^(1/3)``).
    pvalue : {"hiccups", "cooltools"}
        ``"hiccups"``: ``P(X ≥ obs)`` (Juicer HiCCUPS); ``"cooltools"``: ``P(X > obs)`` (cooltools ``dots``).
    cluster_radius : int or None
        Radius of the greedy clustering, bp; ``None``: 20 kb below 18 kb resolution, 50 kb above (Juicer).
    filter : bool
        Apply the Rao 2014 enrichment / singleton filter to the cluster summits.
    enrichment_vh, enrichment_d_and_ll, enrichment_d_or_ll : float
        Summit counts must exceed ``enrichment_vh`` × the vertical and horizontal expecteds,
        ``enrichment_d_and_ll`` × the donut and lower-left ones, and ``enrichment_d_or_ll`` × one of them.
    fdr_orphan : float
        A single-pixel cluster needs the sum of its four q-values ≤ this.
    """

    p: Optional[int] = None
    w: Optional[int] = None
    max_dist: int = 10_000_000
    fdr: float = 0.1
    ignore_diags: int = 2
    lambda_base: float = 2 ** (1 / 3)
    pvalue: str = "hiccups"
    cluster_radius: Optional[int] = None
    filter: bool = True
    enrichment_vh: float = 1.5
    enrichment_d_and_ll: float = 1.75
    enrichment_d_or_ll: float = 2.0
    fdr_orphan: float = 0.02

    def __post_init__(self):
        if self.pvalue not in ("hiccups", "cooltools"):
            raise ValueError(f"pvalue={self.pvalue!r}: 'hiccups' or 'cooltools'")
        if (self.p is None) != (self.w is None):
            raise ValueError("give both p and w, or neither")
        if self.p is not None and not (1 <= self.p < self.w):
            raise ValueError(f"need 1 <= p < w, got p={self.p}, w={self.w}")
        if not 0 < self.fdr < 1:
            raise ValueError(f"fdr={self.fdr} must be in (0, 1)")


def kernel_sizes(binsize: int, params: Optional[HiccupsParams] = None) -> Tuple[int, int]:
    """``(p, w)`` of the kernels at ``binsize`` bp (``params.p / w`` if set, else Rao 2014's choice)."""
    params = params or HiccupsParams()
    if params.p is not None:
        return int(params.p), int(params.w)
    if 18_000 <= binsize <= 28_000:
        return 1, 3
    if 8_000 <= binsize < 18_000:
        return 2, 5
    if 4_000 <= binsize < 8_000:
        return 4, 7
    raise ValueError(f"no HiCCUPS kernel sizes for {binsize} bp bins (Rao 2014: 5-25 kb); pass "
                     f"HiccupsParams(p=..., w=...)")


def kernel_rects(p: int, w: int) -> Dict[str, List[Tuple[int, int, int, int, int]]]:
    """The footprint of every kernel as signed rectangles ``(dy0, dy1, dx0, dx1, sign)`` of neighbour
    offsets (inclusive; the neighbour of pixel ``(i, j)`` is ``(i + dy, j + dx)``, ``dy > 0`` = towards the
    diagonal for a pixel above it)."""
    return {
        "donut": [(-w, w, -w, w, 1), (-p, p, -p, p, -1),
                  (-w, -p - 1, 0, 0, -1), (p + 1, w, 0, 0, -1), (0, 0, -w, -p - 1, -1), (0, 0, p + 1, w, -1)],
        "vertical": [(-w, -p - 1, -1, 1, 1), (p + 1, w, -1, 1, 1)],
        "horizontal": [(-1, 1, -w, -p - 1, 1), (-1, 1, p + 1, w, 1)],
        "lowleft": [(1, w, -w, -1, 1), (1, p, -p, -1, -1)],
    }


def kernel_masks(p: int, w: int) -> Dict[str, np.ndarray]:
    """The kernels as 0/1 ``(2w+1, 2w+1)`` arrays (row = ``dy + w``, column = ``dx + w``)."""
    out = {}
    for name, rects in kernel_rects(p, w).items():
        m = np.zeros((2 * w + 1, 2 * w + 1), np.int64)
        for dy0, dy1, dx0, dx1, s in rects:
            m[dy0 + w: dy1 + w + 1, dx0 + w: dx1 + w + 1] += s
        out[name] = m
    return out


# ----------------------------------------------------------------------------------------------------------
# scoring: one chromosome, tile by tile
# ----------------------------------------------------------------------------------------------------------

def _lambda_edges(base: float, n: int = 160) -> np.ndarray:
    """Upper edges of the λ-chunks: chunk ``k`` holds ``base^(k-1) < λ ≤ base^k`` (chunk 0: ``λ ≤ 1``)."""
    return np.power(base, np.arange(n, dtype=np.float64))


def _pvals(counts, lam, tail: str) -> np.ndarray:
    """Poisson upper-tail p-value of ``counts`` at ``lam`` (arrays broadcast): ``P(X ≥ c)`` or ``P(X > c)``."""
    from scipy.stats import poisson

    c = np.asarray(counts, dtype=np.float64)
    return poisson.sf(c - 1, lam) if tail == "hiccups" else poisson.sf(c, lam)


def _min_counts(edges: np.ndarray, fdr: float, tail: str) -> np.ndarray:
    """For every λ-chunk the smallest count with p ≤ fdr at the chunk's upper edge: no pixel below it can
    pass a BH threshold (``N p ≤ fdr R ≤ fdr N``), so only pixels above it are kept while scoring."""
    from scipy.stats import poisson

    # P(X >= c) <= fdr  <=>  cdf(c - 1) >= 1 - fdr  <=>  c - 1 >= ppf(1 - fdr)   (P(X > c): c >= ppf(1 - fdr));
    # one count lower, to stay a safe lower bound under rounding
    q = poisson.ppf(1.0 - fdr, edges)
    c = q + (1 if tail == "hiccups" else 0) - 1
    return np.maximum(np.nan_to_num(c, nan=0.0, posinf=1e18), 0).astype(np.int64)


class _Hist:
    """Per-kernel 2-D histograms (λ-chunk x observed count) that grow as needed."""

    def __init__(self):
        self.h = {k: np.zeros((1, 1), np.int64) for k in KERNELS}

    def add(self, k: str, lbin: np.ndarray, count: np.ndarray):
        if not len(lbin):
            return
        L, C = int(lbin.max()) + 1, int(count.max()) + 1
        h = self.h[k]
        if L > h.shape[0] or C > h.shape[1]:
            g = np.zeros((max(L, h.shape[0]), max(C, h.shape[1])), np.int64)
            g[: h.shape[0], : h.shape[1]] = h
            self.h[k] = h = g
        flat = np.bincount(lbin * C + count, minlength=L * C).reshape(L, C)
        h[:L, :C] += flat


def _rectsum(S: np.ndarray, rect, y0: int, y1: int, x0: int, x1: int) -> np.ndarray:
    """Sum of the rectangle ``rect`` of offsets around every pixel ``(y, x)``, ``y0 <= y < y1``,
    ``x0 <= x < x1``, from the summed-area table ``S`` (``S[y, x]`` = sum of ``X[:y, :x]``)."""
    dy0, dy1, dx0, dx1 = rect[:4]
    a, b = y0 + dy0, y1 + dy0
    c, d = y0 + dy1 + 1, y1 + dy1 + 1
    e, f = x0 + dx0, x1 + dx0
    g, h = x0 + dx1 + 1, x1 + dx1 + 1
    return S[c:d, g:h] - S[a:b, g:h] - S[c:d, e:f] + S[a:b, e:f]


def _kernel_sum_at(S: np.ndarray, rects, base: np.ndarray) -> np.ndarray:
    """Kernel sums at selected pixels: ``base`` = flat index of ``S[y, x]`` for each pixel ``(y, x)``."""
    flat, sw = S.ravel(), S.shape[1]
    out = np.zeros(len(base))
    for dy0, dy1, dx0, dx1, sign in rects:
        top, bot = dy0 * sw, (dy1 + 1) * sw
        part = flat[base + (bot + dx1 + 1)] - flat[base + (top + dx1 + 1)]
        part -= flat[base + (bot + dx0)]
        part += flat[base + (top + dx0)]
        if sign > 0:
            out += part
        else:
            out -= part
    return out


def _sat(X: np.ndarray, dtype=np.float64) -> np.ndarray:
    S = np.zeros((X.shape[0] + 1, X.shape[1] + 1), dtype)
    np.cumsum(X, axis=0, dtype=dtype, out=S[1:, 1:])
    np.cumsum(S[1:, 1:], axis=1, out=S[1:, 1:])
    return S


def _expected_vector(band, ignore_diags: int, n_diag: int) -> np.ndarray:
    from uchrom.fea.band import _expected_one

    exp = _expected_one(band, True)["balanced_avg"].to_numpy(dtype=np.float64)
    e = np.full(n_diag + 1, np.nan)
    m = min(len(exp), n_diag + 1)
    e[:m] = exp[:m]
    e[: max(0, ignore_diags)] = np.nan
    return e


def _score_chrom(band, p: int, w: int, D: int, params: HiccupsParams, hist: _Hist, edges: np.ndarray,
                 cmin: np.ndarray, timing: Optional[dict] = None) -> dict:
    """Score every testable pixel of one chromosome: add them to ``hist``, return the candidates."""
    steps = {"tile_dense_s": 0.0, "sat_s": 0.0, "mask_s": 0.0, "kernel_sums_s": 0.0, "histogram_s": 0.0}
    clock = [time.perf_counter()]

    def lap(name):
        now = time.perf_counter()
        steps[name] += now - clock[0]
        clock[0] = now

    n = band.n
    wt = band.weight.astype(np.float64)
    rects = kernel_rects(p, w)
    union = [(-w, w, -w, w, 1), (-p, p, -p, p, -1)]               # the union of the four footprints
    e = _expected_vector(band, params.ignore_diags, D + 2 * w + 2)
    bi, bj, bc = band.i, band.j, band.count
    if len(bi) > 1 and not (np.diff(bi) >= 0).all():                 # cooler pixels come sorted by row
        order = np.argsort(bi, kind="stable")
        bi, bj, bc = bi[order], bj[order], bc[order]
    T = max(32, int((-(D + 4 * w) + math.sqrt((D + 4 * w) ** 2 + 4 * TILE_CELLS)) / 2))
    keep = {"i": [], "j": [], "count": [], **{k: [] for k in KERNELS}}
    n_tested = 0
    for r0 in range(0, n, T):
        clock[0] = time.perf_counter()
        r1 = min(n, r0 + T)
        a0, a1 = r0 - w, r1 + w                                    # dense rows / columns (global bins)
        c0, c1 = r0 - w, min(r1 + D + w, n + w)
        H, W = a1 - a0, c1 - c0
        rows, cols = np.arange(a0, a1), np.arange(c0, c1)
        wr = np.where((rows >= 0) & (rows < n), wt[np.clip(rows, 0, n - 1)], np.nan)
        wc = np.where((cols >= 0) & (cols < n), wt[np.clip(cols, 0, n - 1)], np.nan)
        # expected: Toeplitz over the separations of the tile (NaN below the diagonal, on ignored diagonals
        # and beyond the band); E[y, x] = ext[(x - y) - dmin]
        dmin, dmax = c0 - (a1 - 1), (c1 - 1) - a0
        ext = np.full(dmax - dmin + 1, np.nan)
        lo, hi = max(dmin, 0), min(dmax, len(e) - 1)
        if hi >= lo:
            ext[lo - dmin: hi - dmin + 1] = e[lo: hi + 1]
        win = np.lib.stride_tricks.sliding_window_view(ext, W)       # win[k] = ext[k : k + W]
        E = win[(c0 - a0 - dmin) - np.arange(H)]
        N = np.isnan(E) | np.isnan(wr)[:, None] | np.isnan(wc)[None, :]
        # observed: raw counts and balanced values of the band pixels in the tile
        s, t = np.searchsorted(bi, max(a0, 0)), np.searchsorted(bi, min(a1, n))
        ii, jj, cc = bi[s:t], bj[s:t], bc[s:t]
        sel = jj < c1
        ii, jj, cc = ii[sel] - a0, jj[sel] - c0, cc[sel]
        raw = np.zeros((H, W))
        raw[ii, jj] = cc
        O = raw * wr[:, None]
        O *= wc[None, :]
        O[N] = 0.0
        E0 = np.where(N, 0.0, E)
        lap("tile_dense_s")
        SO, SE, SN = _sat(O), _sat(E0), _sat(N, np.int32)
        del O, E0
        lap("sat_s")
        # tested pixels: rows r0..r1-1 (y = w..), columns c0+w.. (x = w..); in the band, no NaN in the
        # union of the kernels' footprints (the window minus the peak square)
        y0, y1, x0, x1 = w, w + (r1 - r0), w, W - w
        gi = (r0 + np.arange(y1 - y0))[:, None]
        gj = (c0 + w + np.arange(x1 - x0))[None, :]
        sep = gj - gi
        ok = (sep > 0) & (sep < D) & (gj < n)
        ok &= (_rectsum(SN, union[0], y0, y1, x0, x1) - _rectsum(SN, union[1], y0, y1, x0, x1)) == 0
        yy, xx = np.nonzero(ok)
        del ok, sep, SN
        lap("mask_s")
        Y, X = yy + y0, xx + x0
        base = Y * (W + 1) + X
        KE = {k: _kernel_sum_at(SE, rects[k], base) for k in KERNELS}
        good = np.logical_and.reduce([KE[k] > 0 for k in KERNELS]) if len(base) else np.zeros(0, bool)
        yy, xx, Y, X, base = yy[good], xx[good], Y[good], X[good], base[good]
        KE = {k: v[good] for k, v in KE.items()}
        KO = {k: _kernel_sum_at(SO, rects[k], base) for k in KERNELS}
        e_raw = E[Y, X] / (wr[Y] * wc[X])
        count = np.rint(raw[Y, X]).astype(np.int64)
        lap("kernel_sums_s")
        n_tested += len(yy)
        cand = np.ones(len(yy), bool)
        lam = {}
        for k in KERNELS:
            lam[k] = e_raw * KO[k] / KE[k]
            lb = np.searchsorted(edges, lam[k], side="left")
            if len(lb) and lb.max() >= len(edges) - 1:
                raise ValueError(f"a locally adjusted expected of {lam[k].max():.3g} is beyond the λ-chunks")
            hist.add(k, lb, count)
            cand &= count >= cmin[lb]
        keep["i"].append(r0 + yy[cand])
        keep["j"].append(c0 + w + xx[cand])
        keep["count"].append(count[cand])
        for k in KERNELS:
            keep[k].append(lam[k][cand])
        lap("histogram_s")
    if timing is not None:
        for name, v in steps.items():
            timing[name] = timing.get(name, 0.0) + v
        timing["tile_rows"] = T
        timing["n_tested"] = timing.get("n_tested", 0) + n_tested
        timing["n_candidates"] = timing.get("n_candidates", 0) + int(sum(len(v) for v in keep["i"]))
    out = {c: (np.concatenate(v) if v else np.zeros(0)) for c, v in keep.items()}
    out["n_tested"] = n_tested
    return out


def _thresholds(h: np.ndarray, edges: np.ndarray, fdr: float, tail: str) -> Tuple[np.ndarray, np.ndarray]:
    """BH per λ-chunk: the smallest passing count of every chunk (``C`` = none) and the q-value of every
    (chunk, count) — ``q(c) = min_{c' <= c} N p(c') / R(c')``, ``R(c)`` the pixels of the chunk with count ≥ c."""
    L, C = h.shape
    thr = np.full(L, C, np.int64)
    q = np.ones((L, C))
    counts = np.arange(C)
    for b in range(L):
        N = int(h[b].sum())
        if N == 0:
            continue
        R = h[b][::-1].cumsum()[::-1].astype(np.float64)
        pv = _pvals(counts, edges[b], tail)
        good = N * pv <= fdr * R
        if good.any():
            thr[b] = int(np.argmax(good))
        with np.errstate(divide="ignore", invalid="ignore"):
            ratio = np.where(R > 0, N * pv / np.where(R > 0, R, 1.0), np.inf)
        q[b] = np.minimum(np.minimum.accumulate(ratio), 1.0)
    return thr, q


# ----------------------------------------------------------------------------------------------------------
# clustering, filtering, merging
# ----------------------------------------------------------------------------------------------------------

def cluster_pixels(start1, start2, count, *, radius: float, resolution: int) -> pd.DataFrame:
    """HiCCUPS' greedy clustering of enriched pixels (Rao 2014; Juicer ``coalescePixelsToCentroid``).

    The pixels are taken brightest first (ties: larger ``start1``, then ``start2``).  Each remaining pixel,
    in that order, joins the current cluster when it lies within ``radius + r`` of the cluster's centroid
    (``r``: the largest distance of a member to the centroid, recomputed after each join; distances between
    pixel starts, bp).  The brightest pixel represents the cluster.

    Returns
    -------
    DataFrame, one row per cluster: ``summit`` (row of the input), ``centroid1``, ``centroid2`` (bp, bin
    centres), ``radius`` (bp), ``cluster_size``, and ``label`` per input row is in ``.attrs['labels']``.
    """
    from scipy.spatial import cKDTree

    s1 = np.asarray(start1, dtype=np.int64)
    s2 = np.asarray(start2, dtype=np.int64)
    cnt = np.asarray(count, dtype=np.float64)
    n = len(s1)
    labels = np.full(n, -1, np.int64)
    if n == 0:
        out = pd.DataFrame({"summit": pd.Series(dtype="int64"), "centroid1": pd.Series(dtype="int64"),
                            "centroid2": pd.Series(dtype="int64"), "radius": pd.Series(dtype="int64"),
                            "cluster_size": pd.Series(dtype="int64")})
        out.attrs["labels"] = labels
        return out
    order = np.lexsort((-s2, -s1, -cnt))
    rank = np.empty(n, np.int64)
    rank[order] = np.arange(n)
    tree = cKDTree(np.c_[s1, s2].astype(np.float64))
    alive = np.ones(n, bool)
    rows = []
    for seed in order:
        if not alive[seed]:
            continue
        reach_q = 4.0 * radius + 1.0
        while True:
            cand = np.asarray(tree.query_ball_point([s1[seed], s2[seed]], reach_q), dtype=np.int64)
            cand = cand[alive[cand] & (cand != seed)]
            cand = cand[np.argsort(rank[cand])]
            members = [seed]
            sx, sy = float(s1[seed]), float(s2[seed])
            cx, cy = int(s1[seed]), int(s2[seed])
            r, rad, reach = 0, float(radius), float(radius)
            for c in cand:
                if math.hypot(cx - s1[c], cy - s2[c]) <= rad:
                    members.append(c)
                    sx += s1[c]
                    sy += s2[c]
                    cx, cy = int(sx / len(members)), int(sy / len(members))
                    m = np.asarray(members)
                    r = int(math.floor(np.hypot(cx - s1[m], cy - s2[m]).max() + 0.5))
                    rad = radius + r
                    reach = max(reach, math.hypot(cx - s1[seed], cy - s2[seed]) + rad)
            if reach <= reach_q:
                break
            reach_q = 2.0 * reach
        m = np.asarray(members)
        alive[m] = False
        labels[m] = len(rows)
        rows.append((int(seed), cx + resolution // 2, cy + resolution // 2, int(r), len(m)))
    out = pd.DataFrame(rows, columns=["summit", "centroid1", "centroid2", "radius", "cluster_size"])
    out.attrs["labels"] = labels
    return out


def _filter_mask(t: pd.DataFrame, params: HiccupsParams) -> np.ndarray:
    o = t["count"].to_numpy(dtype=np.float64)
    ll, d = t["exp_lowleft"].to_numpy(), t["exp_donut"].to_numpy()
    v, h = t["exp_vertical"].to_numpy(), t["exp_horizontal"].to_numpy()
    qsum = sum(t[f"fdr_{k}"].to_numpy() for k in KERNELS)
    return ((o > params.enrichment_d_and_ll * ll) & (o > params.enrichment_d_and_ll * d)
            & (o > params.enrichment_vh * v) & (o > params.enrichment_vh * h)
            & ((o > params.enrichment_d_or_ll * ll) | (o > params.enrichment_d_or_ll * d))
            & ((t["cluster_size"].to_numpy() > 1) | (qsum <= params.fdr_orphan)))


def _near(a: pd.DataFrame, b: pd.DataFrame, radius: float) -> np.ndarray:
    """For every row of ``a``: is a row of ``b`` on the same chromosome with anchor starts within ``radius``
    (Euclidean, bp)?"""
    out = np.zeros(len(a), bool)
    if not len(a) or not len(b):
        return out
    from scipy.spatial import cKDTree

    ac, bc = a["chrom1"].astype(str).to_numpy(), b["chrom1"].astype(str).to_numpy()
    for c in np.unique(ac):
        ia, ib = np.flatnonzero(ac == c), np.flatnonzero(bc == c)
        if not len(ib):
            continue
        tree = cKDTree(np.c_[b["start1"].to_numpy()[ib], b["start2"].to_numpy()[ib]].astype(np.float64))
        d, _ = tree.query(np.c_[a["start1"].to_numpy()[ia], a["start2"].to_numpy()[ia]].astype(np.float64))
        out[ia] = d <= radius
    return out


def merge_resolutions(calls: Dict[int, pd.DataFrame]) -> pd.DataFrame:
    """Merge loop calls made at several resolutions as Rao et al. 2014 (Juicer ``mergeAllResolutions``).

    5 kb + 10 kb: the 5-kb loops with a 10-kb loop within 20 kb, the 10-kb loops without a 5-kb loop within
    20 kb, and the 5-kb loops closer than 110 kb to the diagonal or with more than 100 contacts.  25 kb: added
    when no loop of the merged list lies within 50 kb.  Other resolutions (not 5 / 10 / 25 kb), from the finest
    up: a coarser loop is added when no merged loop lies within twice its bin size.  Distances are Euclidean
    between anchor starts.

    Parameters
    ----------
    calls : dict
        Resolution (bp) → loop table (``chrom1, start1, start2, count``, ...).

    Returns
    -------
    DataFrame with the rows kept (their ``resolution`` column says where each was called).
    """
    calls = {int(r): t.reset_index(drop=True) for r, t in calls.items() if t is not None}
    if not calls:
        raise ValueError("no loop tables to merge")
    parts: List[pd.DataFrame] = []
    five, ten = calls.get(5000), calls.get(10000)
    if five is not None and ten is not None:
        sep5 = (five["start2"] - five["start1"]).to_numpy()
        keep5 = _near(five, ten, 20_000) | (sep5 < 110_000) | (five["count"].to_numpy() > 100)
        parts = [five[keep5], ten[~_near(ten, five, 20_000)]]
    elif five is not None:
        parts = [five]
    elif ten is not None:
        parts = [ten]
    merged = pd.concat(parts, ignore_index=True) if parts else None
    rest = sorted(r for r in calls if r not in (5000, 10000))
    for r in rest:
        t = calls[r]
        if merged is None:
            merged = t
            continue
        radius = 50_000 if r == 25_000 else 2 * r
        merged = pd.concat([merged, t[~_near(t, merged, radius)]], ignore_index=True)
    return merged.drop_duplicates(subset=["chrom1", "start1", "start2", "resolution"]).reset_index(drop=True)


# ----------------------------------------------------------------------------------------------------------
# public API
# ----------------------------------------------------------------------------------------------------------

_COLUMNS = ["chrom1", "start1", "end1", "chrom2", "start2", "end2", "score", "pval", "fdr", "count",
            *[f"exp_{k}" for k in KERNELS], *[f"fdr_{k}" for k in KERNELS], "enrichment",
            "cluster_size", "centroid1", "centroid2", "radius", "resolution", "summit_i", "summit_j"]


def _empty_result() -> pd.DataFrame:
    dt = {c: "float64" for c in _COLUMNS}
    dt.update({c: "int64" for c in ("start1", "end1", "start2", "end2", "count", "cluster_size", "centroid1",
                                    "centroid2", "radius", "resolution", "summit_i", "summit_j")})
    dt.update({"chrom1": str, "chrom2": str})
    return pd.DataFrame({c: pd.Series(dtype=dt[c]) for c in _COLUMNS})


def hiccups_pixels(clr, chroms: Sequence[str], params: Optional[HiccupsParams] = None, *,
                   timing: Optional[dict] = None) -> Tuple[pd.DataFrame, dict]:
    """The enriched pixels of a balanced map (steps 1-2 of :func:`call_loops_hiccups`: before clustering).

    Parameters
    ----------
    clr : cooler.Cooler
        A balanced map (``weight`` column).
    chroms : sequence of str
        Chromosomes scored together (one genome-wide FDR over all of them).
    params : HiccupsParams, optional
    timing : dict, optional
        Filled with seconds per step (``read_s``, ``kernel_sums_s``, ``histogram_s``, ``thresholds_s``).

    Returns
    -------
    pixels : DataFrame
        ``chrom, i, j`` (bins of the chromosome), ``start1, start2``, ``count``, ``exp_<kernel>`` (λ, raw
        counts), ``pval_<kernel>`` and ``fdr_<kernel>`` (q-value) for the four kernels.
    info : dict
        ``p, w, max_diag, n_tested`` (pixels scored), ``thresholds`` (per kernel: the smallest passing count
        of each λ-chunk).
    """
    from uchrom.fea.band import read_band

    params = params or HiccupsParams()
    binsize = int(clr.binsize)
    p, w = kernel_sizes(binsize, params)
    D = int(params.max_dist / binsize)
    edges = _lambda_edges(params.lambda_base)
    cmin = _min_counts(edges, params.fdr, params.pvalue)
    hist = _Hist()
    timing = {} if timing is None else timing
    found = {}
    n_tested = 0
    for c in chroms:
        t0 = time.perf_counter()
        band = read_band(clr, chrom=c, max_dist=(D + 2 * w + 1) * binsize, balance=True)
        timing["read_s"] = timing.get("read_s", 0.0) + time.perf_counter() - t0
        if band.weight is None:
            raise ValueError("HiCCUPS needs a balanced map (a 'weight' column): uchrom.fea.rebin_map(...) or "
                             "cooler balance")
        res = _score_chrom(band, p, w, D, params, hist, edges, cmin, timing)
        n_tested += res.pop("n_tested")
        res["starts"] = band.starts
        found[c] = res
    t0 = time.perf_counter()
    thr, qtab = {}, {}
    for k in KERNELS:
        thr[k], qtab[k] = _thresholds(hist.h[k], edges, params.fdr, params.pvalue)
    frames = []
    for c, res in found.items():
        if not len(res["i"]):
            continue
        count = res["count"].astype(np.int64)
        passed = np.ones(len(count), bool)
        lb = {}
        for k in KERNELS:
            lb[k] = np.searchsorted(edges, res[k], side="left")
            passed &= count >= thr[k][lb[k]]
        if not passed.any():
            continue
        i, j = res["i"][passed].astype(np.int64), res["j"][passed].astype(np.int64)
        df = pd.DataFrame({"chrom": c, "i": i, "j": j, "start1": res["starts"][i], "start2": res["starts"][j],
                           "count": count[passed]})
        for k in KERNELS:
            b = lb[k][passed]
            df[f"exp_{k}"] = res[k][passed]
            df[f"pval_{k}"] = _pvals(df["count"].to_numpy(), edges[b], params.pvalue)
            df[f"fdr_{k}"] = qtab[k][b, np.minimum(df["count"].to_numpy(), qtab[k].shape[1] - 1)]
        frames.append(df)
    timing["thresholds_s"] = time.perf_counter() - t0
    cols = ["chrom", "i", "j", "start1", "start2", "count", *[f"{a}_{k}" for k in KERNELS
                                                                for a in ("exp", "pval", "fdr")]]
    pixels = (pd.concat(frames, ignore_index=True) if frames else
              pd.DataFrame({c: pd.Series(dtype=str if c == "chrom" else "float64") for c in cols}))
    info = {"p": p, "w": w, "max_diag": D, "binsize": binsize, "n_tested": int(n_tested),
            "thresholds": {k: thr[k].tolist() for k in KERNELS}}
    return pixels, info


def _call_one(clr, chroms, params: HiccupsParams, timing: Optional[dict] = None) -> Tuple[pd.DataFrame, dict]:
    pixels, info = hiccups_pixels(clr, chroms, params, timing=timing)
    binsize = info["binsize"]
    radius = params.cluster_radius if params.cluster_radius is not None else (50_000 if binsize >= 18_000
                                                                            else 20_000)
    t0 = time.perf_counter()
    frames = []
    for c, px in pixels.groupby("chrom", sort=False):
        px = px.reset_index(drop=True)
        cl = cluster_pixels(px["start1"], px["start2"], px["count"], radius=radius, resolution=binsize)
        s = px.iloc[cl["summit"].to_numpy()].reset_index(drop=True)
        qmax = np.max([s[f"fdr_{k}"].to_numpy() for k in KERNELS], axis=0)
        pmax = np.max([s[f"pval_{k}"].to_numpy() for k in KERNELS], axis=0)
        t = pd.DataFrame({
            "chrom1": str(c), "start1": s["start1"].astype(np.int64), "end1": s["start1"].astype(np.int64) + binsize,
            "chrom2": str(c), "start2": s["start2"].astype(np.int64), "end2": s["start2"].astype(np.int64) + binsize,
            "score": -np.log10(np.maximum(pmax, 1e-300)), "pval": pmax, "fdr": qmax,
            "count": s["count"].astype(np.int64),
            **{f"exp_{k}": s[f"exp_{k}"] for k in KERNELS},
            **{f"fdr_{k}": s[f"fdr_{k}"] for k in KERNELS},
            "enrichment": s["count"] / s["exp_donut"],
            "cluster_size": cl["cluster_size"].to_numpy(np.int64),
            "centroid1": cl["centroid1"].to_numpy(np.int64), "centroid2": cl["centroid2"].to_numpy(np.int64),
            "radius": cl["radius"].to_numpy(np.int64), "resolution": np.int64(binsize),
            "summit_i": s["i"].astype(np.int64), "summit_j": s["j"].astype(np.int64)})
        frames.append(t)
    table = merge_tables(frames, _empty_result())
    info["n_enriched"] = int(len(pixels))
    info["n_clusters"] = int(len(table))
    if params.filter and len(table):
        table = table[_filter_mask(table, params)].reset_index(drop=True)
    info["n_loops"] = int(len(table))
    if timing is not None:
        timing["cluster_filter_s"] = time.perf_counter() - t0
    table = table.sort_values(["chrom1", "start1", "start2"], kind="mergesort").reset_index(drop=True)
    return table[_COLUMNS], info


def _maps(cd, contacts, resolution) -> List[Tuple[object, str]]:
    """``[(cooler, label), ...]``: one map per resolution."""
    from uchrom.fea.maps import _is_cooler, map_path, open_map

    many_c = isinstance(contacts, (list, tuple))
    many_r = isinstance(resolution, (list, tuple))
    if many_c and many_r and len(contacts) != len(resolution):
        raise ValueError("contacts= and resolution= lists must have the same length")
    pairs = (list(zip(contacts, resolution)) if many_c and many_r else
             [(c, resolution) for c in contacts] if many_c else
             [(contacts, r) for r in resolution] if many_r else [(contacts, resolution)])
    out = []
    for c, r in pairs:
        if _is_cooler(c):
            out.append((c, str(c.uri)))
            continue
        path = map_path(cd, c)
        out.append((open_map(path, resolution=r), str(c) if c is not None else path))
    return out


def call_loops_hiccups(
    cd,
    *,
    contacts=None,
    chrom=None,
    resolution: Union[None, int, Sequence[int]] = None,
    params: Optional[HiccupsParams] = None,
    key_added: Optional[str] = "loops.hiccups",
    copy: bool = False,
    timing: Optional[dict] = None,
):
    """Loops of a Hi-C map by local enrichment: HiCCUPS (Rao et al. 2014; cooltools ``dots``, Open2C 2024).

    Every pixel of the band ``0 < j - i < max_dist`` is tested (Poisson) against four locally adjusted
    expected counts — from the donut, vertical, horizontal and lower-left neighbourhoods — with a
    Benjamini–Hochberg FDR per λ-chunk; pixels enriched for all four are clustered greedily, the brightest
    pixel of each cluster is the loop, and the Rao 2014 enrichment filter is applied.  See the module
    docstring for the details and the deviations from cooltools.

    Parameters
    ----------
    cd : ChromData
        Holds the link (``cd.link_cool(path, key=...)``) and receives the result.
    contacts : str, cooler.Cooler, or a list of them
        Key of a linked map (``None``: the only one), the path of a ``.cool`` / ``.mcool``, or an open cooler.
        The map must be balanced (``weight``; :func:`uchrom.fea.rebin_map` balances).  A list = one map per
        resolution (e.g. ``["bulk", "bulk_10kb", "bulk_25kb"]``): called at each, merged
        (:func:`merge_resolutions`).
    chrom : str, sequence of str, or None
        ``None``: the chromosomes of ``cd`` that the map has (every map chromosome when ``cd`` has no spots).
        The FDR is computed over all of them together.
    resolution : int or sequence of int, optional
        The level(s) of an ``.mcool``; several → called at each and merged.
    params : HiccupsParams, optional
    key_added : str or None
        ``cd.results`` / ``cd.intervals`` key (default ``"loops.hiccups"``); ``None`` does not store.
    copy : bool
        ``True`` → return a new ChromData holding the result.
    timing : dict, optional
        Filled with the seconds of each step (profiling).

    Returns
    -------
    DataFrame (``copy=False``) or ChromData (``copy=True``)
        A ``pair`` table, one row per loop (the summit pixel): ``chrom1, start1, end1, chrom2, start2,
        end2``, ``score`` (-log10 ``pval``), ``pval`` (largest Poisson p-value of the four kernels, at the
        λ-chunk's upper edge), ``fdr`` (largest q-value), ``count`` (raw), ``exp_<kernel>`` (locally adjusted
        expected, raw counts), ``fdr_<kernel>``, ``enrichment`` (count / donut expected), ``cluster_size``,
        ``centroid1/2`` and ``radius`` of the cluster (bp), ``resolution``, ``summit_i/j`` (bins of the
        chromosome).

    Examples
    --------
    >>> hic = ds.load("rao2014_imr90_chr21")                                   # doctest: +SKIP
    >>> rebin_map(hic, "bulk", resolution=10_000)                             # doctest: +SKIP
    >>> loops = call_loops_hiccups(hic, contacts="bulk_10kb")                  # doctest: +SKIP
    """
    if copy and key_added is None:
        raise ValueError("call_loops_hiccups(): copy=True needs a key_added")
    params = params or HiccupsParams()
    maps = _maps(cd, contacts, resolution)
    has_spots = hasattr(cd, "spots") and len(cd.spots) > 0
    tables, infos = {}, {}
    for clr, label in maps:
        if chrom is None:
            wanted = resolve_chroms(cd, None) if has_spots else []
            chroms = [c for c in wanted if c in clr.chromnames] or list(clr.chromnames)
        else:
            chroms = [str(c) for c in ([chrom] if isinstance(chrom, str) else chrom)]
            missing = [c for c in chroms if c not in clr.chromnames]
            if missing:
                raise ValueError(f"not in the map {label}: {missing}")
        t, info = _call_one(clr, chroms, params, timing=timing)
        res = int(clr.binsize)
        if res in tables:
            raise ValueError(f"two maps at {res} bp")
        tables[res] = t
        infos[res] = {**info, "contacts": label, "chrom": list(chroms)}
    table = merge_resolutions(tables)[_COLUMNS] if len(tables) > 1 else next(iter(tables.values()))
    table = table.sort_values(["chrom1", "start1", "start2", "resolution"], kind="mergesort").reset_index(drop=True)
    inputs = {"contacts": [infos[r]["contacts"] for r in infos], "resolution": sorted(infos),
              "chrom": sorted({c for i in infos.values() for c in i["chrom"]}),
              **{f"n_{s}_{r}": infos[r][f"n_{s}"] for r in infos for s in ("tested", "enriched", "clusters", "loops")}}
    return store_and_return(cd, table, key_added=key_added, copy=copy, kind="intervals", interval_kind="pair",
                            function="uchrom.strc.loop.call_loops_hiccups", params=params, inputs=inputs)


__all__ = ["HiccupsParams", "call_loops_hiccups", "cluster_pixels", "hiccups_pixels", "kernel_masks",
           "kernel_rects", "kernel_sizes", "merge_resolutions"]
