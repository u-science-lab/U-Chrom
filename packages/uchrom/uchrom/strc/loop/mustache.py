"""Loops of a Hi-C map by scale-space blob detection (Mustache).

Re-implementation of Mustache (Roayaei Ardakany, Gezer, Lonardi & Ay 2020, *Genome Biology* 21:256,
doi:10.1186/s13059-020-02167-0), following the paper and the reference code (``mustache-hic`` 1.3.3, MIT),
on a banded map so that a 5 kb map of a large chromosome fits in memory.

Algorithm (per chromosome)
--------------------------
1. **Read** the balanced pixels within ``max_dist`` of the diagonal (:func:`uchrom.fea.band.read_band`);
   masked / zero pixels are left out.
2. **Normalise** every diagonal ``d``: a pixel becomes a local z-score, its value minus the mean of the
   present pixels of its diagonal within a sliding window of ``norm_window`` bp, divided by their standard
   deviation (diagonal-wide mean / sd where the window holds fewer than ``min_window_pixels`` pixels),
   scaled by ``1 + log30(1 + mean of the diagonal)``.  A chromosome shorter than ``max_dist + norm_window``
   uses the diagonal-wide z-score.
3. **Image**: the z-scores of the band ``min_diag < j - i <= max_dist``; absent pixels are 0; everything
   else (the diagonal ``j - i <= min_diag``, beyond ``max_dist``, the lower triangle) holds the constant 2.
4. **Scale space**: for every octave ``o = sigma0 * 2**q`` (``q < octaves``) the image is smoothed with
   Gaussians ``sigma_k = o * 2**((k - 1) / scales)``, ``k = 1 .. scales + 2`` (kernels truncated at
   ``ceil(2 sigma)``), and differenced, ``L_k = G_k - G_{k+1}``.
5. **Extrema**: a pixel (non-zero z-score, ``j - i >= min_diag``) is a candidate at ``L_k``
   (``k = 2 .. scales``) when ``L_k`` there is the maximum of its 3 x 3 neighbourhood, larger than the
   whole 3 x 3 neighbourhood of ``L_{k-1}`` and of ``L_{k+1}``, ``L_{k-1}`` or ``L_{k+1}`` is itself a
   3 x 3 maximum there, and ``L_k`` exceeds the pixel's best response so far (over all scales and
   octaves); the last such scale is the pixel's detection scale.
6. **Test**: an exponential distribution is fitted (maximum likelihood: ``loc = min``, ``scale = mean -
   min``) to ``|L_k|`` over all candidate-eligible pixels of the scale; the p-value of a candidate is the
   upper tail at its response; Benjamini-Hochberg over all candidates gives the FDR; ``fdr < params.fdr``
   is kept.
7. **Filters**: the share of eligible pixels in the ``(2s + 1)^2`` window around the candidate must be
   ``>= sparsity`` for ``s = ceil(scale)`` and ``>= sparsity_outer`` for ``2s``; the z-score must exceed
   ``enrichment`` times the mean non-zero z-score of its diagonal.
8. **Clustering**: candidates whose 3 x 3 neighbourhoods touch (Chebyshev distance <= 3) are one loop,
   reported at its lowest-FDR pixel.

Deviations from the reference code (deliberate)
-----------------------------------------------
* The reference cuts a chromosome into blocks of ``max(2 * max_dist, 2000)`` bins overlapping by
  ``max_dist`` and computes the exponential fits, the Benjamini-Hochberg correction, the diagonal means of
  the enrichment filter and the minimum-pixel guard per block.  Here they are computed once per
  chromosome; the image is processed in row tiles with a halo wider than the largest Gaussian, so results
  do not depend on where blocks fall (no reflected / zero-padded block edges, no clusters split at a block
  edge).  On whole chromosomes this moves borderline candidates across the FDR threshold (e.g. reference
  block FDR 0.06-0.10, chromosome-wide 0.10-0.16); the kernels agree exactly when run on the same block.
* p-values are ``exp(-(x - loc) / scale)`` (the survival function) instead of ``1 - cdf``, which rounds to 0
  for strong loops; the FDR order among strong candidates is kept.
* The reported pixel of a cluster is the lowest-FDR *candidate* (the reference takes the minimum over the
  candidates' 3 x 3 neighbourhoods, which can return a pixel that failed the filters); ties go to the
  larger response.
* The reference drops candidates on the first rows of a block (a negative slice start); here windows are
  clipped at the chromosome edges.
* For short chromosomes the reference leaves the last diagonal un-normalised; here every diagonal is.
* ``fdr`` defaults to 0.1, the default documented in the reference README (its command line uses 0.2).
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

import numpy as np
import pandas as pd

from uchrom.convention import merge_tables, resolve_chroms, store_and_return

__all__ = ["MustacheParams", "call_loops_mustache"]

#: image value outside the analysed band (the reference's constant)
_FILL = 2.0
#: pseudocount that marks a present pixel in the reference's sliding-window sums
_EPS = 1e-3
#: candidates within this Chebyshev distance (pixels) are one loop: touching 3 x 3 neighbourhoods
_LINK = 3


@dataclass(frozen=True)
class MustacheParams:
    """Parameters of :func:`call_loops_mustache` (defaults: the reference's, tuned for 5 kb maps).

    Attributes
    ----------
    sigma0 : float
        Smallest Gaussian of the first octave (pixels); 1.6 in the paper.
    octaves : int
        Octaves (each doubles sigma); 2.
    scales : int
        Gaussian levels per octave (DoG layers ``scales + 1``); 10.
    fdr : float
        Benjamini-Hochberg threshold (the reference's ``-pt``).
    sparsity : float
        Least share of observed pixels around a candidate (``-st``); lower it for sparse maps (0.8).
    sparsity_outer : float
        The same in a window twice as wide.
    max_dist : int, optional
        Largest anchor separation (bp).  Default: the reference's rule, 2 Mb clamped to
        ``[200, 2000]`` bins (2 Mb at 5 / 10 kb, 5 Mb at 25 kb).
    min_diag : int
        Diagonals ``j - i <= min_diag`` are not analysed (bins).
    norm_window : int
        Width of the sliding window of the per-diagonal normalisation (bp).
    min_window_pixels : int
        Fewer present pixels in the window: the diagonal-wide mean / sd are used.
    enrichment : float
        A loop's z-score must exceed this multiple of its diagonal's mean non-zero z-score.
    min_pixels : int
        Chromosomes with fewer analysable pixels give no loops (the reference applies 10,000 per block).
    """

    sigma0: float = 1.6
    octaves: int = 2
    scales: int = 10
    fdr: float = 0.1
    sparsity: float = 0.88
    sparsity_outer: float = 0.6
    max_dist: Optional[int] = None
    min_diag: int = 4
    norm_window: int = 2_000_000
    min_window_pixels: int = 30
    enrichment: float = 2.0
    min_pixels: int = 10_000

    def __post_init__(self):
        if self.sigma0 <= 0 or self.octaves < 1 or self.scales < 2:
            raise ValueError("sigma0 > 0, octaves >= 1 and scales >= 2 are required")
        if not 0 < self.fdr <= 1:
            raise ValueError(f"fdr must be in (0, 1], not {self.fdr}")
        if self.max_dist is not None and self.max_dist <= 0:
            raise ValueError(f"max_dist must be positive, not {self.max_dist}")


def default_max_dist(resolution: int) -> int:
    """The reference's distance limit for a map of ``resolution`` bp: 2 Mb, at least 200 and at most 2000
    bins."""
    res = int(resolution)
    if 200 * res >= 2_000_000:
        return 200 * res
    if 2000 * res <= 2_000_000:
        return 2000 * res
    return 2_000_000


# ----------------------------------------------------------------------------------------------------------
# kernel
# ----------------------------------------------------------------------------------------------------------

def _normalize(x, y, v, n: int, D: int, resolution: int, p: MustacheParams) -> np.ndarray:
    """Per-diagonal local z-scores of the pixel values ``v`` (step 2 of the module docstring)."""
    d = y - x
    order = np.argsort(d, kind="stable")
    edges = np.searchsorted(d[order], np.arange(D + 2))
    z = np.zeros(len(v))
    M = int(p.norm_window / resolution)
    local = (n - D) * resolution > p.norm_window and M >= 1
    with np.errstate(all="ignore"):
        for k in range(D + 1):
            idx = order[edges[k]:edges[k + 1]]
            if len(idx) == 0:
                continue
            xd, vd = x[idx], v[idx]
            mean, std = float(vd.mean()), float(vd.std())
            if not math.isfinite(mean):
                mean = 0.0
            if not math.isfinite(std):
                std = 1.0
            if not local:
                zd = (vd - mean) / std
                z[idx] = np.where(np.isfinite(zd), zd, 0.0)
                continue
            N = n - k
            a = np.zeros(N)
            a[xd] = vd + _EPS
            c1 = np.concatenate([[0.0], np.cumsum(a)])
            c2 = np.concatenate([[0.0], np.cumsum(a * a)])
            cn = np.concatenate([[0], np.cumsum(a != 0)])
            lo = np.clip(xd - M // 2, 0, N)
            hi = np.clip(xd - M // 2 + M, 0, N)
            s1, s2, cnt = c1[hi] - c1[lo], c2[hi] - c2[lo], (cn[hi] - cn[lo]).astype(np.float64)
            var = (s2 - s1 * s1 / cnt) / (cnt - 1)
            var[~np.isfinite(var)] = std * std
            mu = s1 / cnt
            few = cnt < p.min_window_pixels
            mu[few] = mean
            var[few] = std * std
            mu[~np.isfinite(mu)] = mean
            zd = (vd + _EPS - mu) / np.sqrt(var)
            zd[~np.isfinite(zd)] = 0.0
            z[idx] = zd * (1.0 + math.log(1.0 + mean, 30))
    return z


def _pyramid(p: MustacheParams):
    """Per octave: the Gaussian sigmas and truncations (kernel radius ``ceil(2 sigma)``) of the reference."""
    out = []
    for q in range(p.octaves):
        o = p.sigma0 * 2 ** q
        sig = [o * 2 ** ((k - 1) / p.scales) for k in range(1, p.scales + 3)]
        trunc = [(math.ceil(2 * s) - 0.5) / s for s in sig]
        out.append((sig, trunc))
    return out


def _max3(a: np.ndarray) -> np.ndarray:
    """3 x 3 maximum with zero padding (= ``scipy.ndimage.maximum_filter(a, 3, mode="constant")``, ~6x
    faster)."""
    p = np.zeros((a.shape[0], a.shape[1] + 2))
    p[:, 1:-1] = a
    h = np.zeros((a.shape[0] + 2, a.shape[1]))
    h[1:-1] = np.maximum(np.maximum(p[:, :-2], p[:, 1:-1]), p[:, 2:])
    return np.maximum(np.maximum(h[:-2], h[1:-1]), h[2:])


def _scan(x, y, z, ex, ey, n: int, D: int, p: MustacheParams, tile: int):
    """Steps 3-5 over row tiles: per eligible pixel (``ex, ey``) its best DoG response and detection layer,
    plus the per-layer ``|L|`` statistics (sum, count, min) for the exponential fits."""
    from scipy.ndimage import gaussian_filter

    pyr = _pyramid(p)
    radius = max(int(t * s + 0.5) for sig, trunc in pyr for s, t in zip(sig, trunc))
    halo = radius + 2                       # Gaussian support + the 3 x 3 maximum
    S = p.scales
    K = p.octaves * (S - 1)
    m = len(ex)
    best = np.zeros(m)
    layer = np.full(m, -1, dtype=np.int16)
    st_sum, st_cnt, st_min = np.zeros(K), np.zeros(K, dtype=np.int64), np.full(K, np.inf)
    row_ptr = np.searchsorted(x, np.arange(n + 1))
    el_ptr = np.searchsorted(ex, np.arange(n + 1))
    for r0 in range(0, n, tile):
        r1 = min(n, r0 + tile)
        e0, e1 = int(el_ptr[r0]), int(el_ptr[r1])
        if e0 == e1:
            continue
        a0, a1 = max(0, r0 - halo), min(n, r1 + halo)
        b0, b1 = a0, min(n, r1 + D + 1 + halo)
        dd = np.arange(b0, b1)[None, :] - np.arange(a0, a1)[:, None]
        img = np.where((dd > p.min_diag) & (dd <= D), 0.0, _FILL)
        s0, s1 = int(row_ptr[a0]), int(row_ptr[a1])
        px, py = x[s0:s1], y[s0:s1]
        inb = (py - px) > p.min_diag
        img[px[inb] - a0, py[inb] - b0] = z[s0:s1][inb]
        P = (ex[e0:e1] - a0, ey[e0:e1] - b0)
        vb, lb = best[e0:e1], layer[e0:e1]             # views
        for q, (sig, trunc) in enumerate(pyr):
            G = [gaussian_filter(img, s, truncate=t, mode="reflect") for s, t in zip(sig, trunc)]
            LP, MP = [], []
            for k in range(S + 1):                     # L[k] = G_{k+1} - G_{k+2} (the reference's L_{k+1})
                L = G[k] - G[k + 1]
                LP.append(L[P])
                MP.append(_max3(L)[P])
            del G
            for k in range(1, S):                      # Lc = L[k]; its scale is sig[k + 1]
                lc = LP[k]
                a = np.abs(lc)
                j = q * (S - 1) + (k - 1)
                st_sum[j] += a.sum()
                st_cnt[j] += len(a)
                st_min[j] = min(st_min[j], a.min())
                upd = ((lc > vb) & (lc == MP[k]) & ((LP[k - 1] == MP[k - 1]) | (LP[k + 1] == MP[k + 1]))
                       & (lc > MP[k - 1]) & (lc > MP[k + 1]))
                vb[upd] = lc[upd]
                lb[upd] = j
    scales = np.array([sig[k + 1] for sig, _ in pyr for k in range(1, S)])
    return best, layer, (st_sum, st_cnt, st_min), scales


def _window_share(key, n: int, xs, ys, s: np.ndarray) -> np.ndarray:
    """Share of eligible pixels (sorted keys ``i * n + j``) in the ``(2s + 1)^2`` windows around
    ``(xs, ys)``; the window is clipped at the chromosome edges, the denominator is not."""
    out = np.zeros(len(xs))
    for w in np.unique(s):
        sel = np.flatnonzero(s == w)
        r = np.arange(-w, w + 1)
        rows = xs[sel, None] + r[None, :]
        lo = np.maximum(ys[sel] - w, 0)[:, None]
        hi = np.minimum(ys[sel] + w, n - 1)[:, None]
        ok = (rows >= 0) & (rows < n)
        cnt = np.searchsorted(key, rows * n + hi, side="right") - np.searchsorted(key, rows * n + lo, side="left")
        out[sel] = np.where(ok, cnt, 0).sum(axis=1) / (2 * w + 1) ** 2
    return out


def _clusters(xs, ys) -> np.ndarray:
    """Single-linkage labels of the points (Chebyshev distance <= ``_LINK``)."""
    from scipy.sparse import coo_matrix
    from scipy.sparse.csgraph import connected_components
    from scipy.spatial import cKDTree

    m = len(xs)
    if m <= 1:
        return np.zeros(m, dtype=np.int64)
    pairs = cKDTree(np.c_[xs, ys]).query_pairs(r=_LINK, p=np.inf, output_type="ndarray")
    g = coo_matrix((np.ones(len(pairs)), (pairs[:, 0], pairs[:, 1])), shape=(m, m))
    return connected_components(g, directed=False)[1]


def _call_pixels(chrom: str, starts: np.ndarray, binsize: int, x, y, v, p: MustacheParams, *,
                 D: int, tile: int = 256, verbose: bool = False) -> pd.DataFrame:
    """Mustache on one chromosome's balanced pixels ``(x, y, v)`` (``x <= y <= x + D``, sorted by
    ``(x, y)``, positive values), ``len(starts)`` bins."""
    t0 = time.perf_counter()
    x = np.asarray(x, dtype=np.int64)
    y = np.asarray(y, dtype=np.int64)
    z = _normalize(x, y, np.asarray(v, dtype=np.float64), len(starts), D, binsize, p)
    if verbose:
        print(f"[mustache/{chrom}] normalised {len(x)} pixels in {time.perf_counter() - t0:.1f} s")
    return _detect(chrom, starts, binsize, x, y, z, p, D=D, tile=tile, verbose=verbose)


def _detect(chrom: str, starts: np.ndarray, binsize: int, x, y, z, p: MustacheParams, *, D: int,
            tile: int = 256, verbose: bool = False) -> pd.DataFrame:
    """Steps 3-8 on normalised pixels ``z`` (sorted by ``(x, y)``)."""
    from scipy.stats import false_discovery_control

    t1 = time.perf_counter()
    n = len(starts)
    diag = y - x
    eligible = np.flatnonzero((z != 0) & (diag >= p.min_diag))
    if len(eligible) < max(p.min_pixels, 1):
        if verbose:
            print(f"[mustache/{chrom}] {len(eligible)} analysable pixels < min_pixels; skipped")
        return _empty()
    ex, ey, ez, ed = x[eligible], y[eligible], z[eligible], diag[eligible]
    best, layer, (ssum, scnt, smin), scales = _scan(x, y, z, ex, ey, n, D, p, tile)
    t2 = time.perf_counter()

    found = np.flatnonzero(layer >= 0)
    lay = layer[found].astype(np.int64)
    loc = smin[lay]
    scl = ssum[lay] / np.maximum(scnt[lay], 1) - loc
    with np.errstate(over="ignore", invalid="ignore", divide="ignore"):
        pval = np.where(scl > 0, np.exp(-(best[found] - loc) / scl), 1.0)
    pval = np.clip(pval, 0.0, 1.0)
    fdr = false_discovery_control(pval, method="bh") if len(found) else np.zeros(0)
    sig = fdr < p.fdr
    cand, pval, fdr, lay = found[sig], pval[sig], fdr[sig], lay[sig]
    cx, cy, cz = ex[cand], ey[cand], ez[cand]
    scale = scales[lay]

    # sparsity: share of eligible pixels around the candidate at ceil(scale) and twice that
    key = ex * n + ey
    w = np.ceil(scale).astype(np.int64)
    keep = (_window_share(key, n, cx, cy, w) >= p.sparsity) & (_window_share(key, n, cx, cy, 2 * w)
                                                              >= p.sparsity_outer)
    # enrichment: the image value against the mean non-zero image value of its diagonal (eligible = non-zero)
    dmean = np.bincount(ed, weights=ez, minlength=D + 1) / np.maximum(np.bincount(ed, minlength=D + 1), 1)
    cd_ = cy - cx
    img_val = np.where(cd_ <= p.min_diag, _FILL, cz)
    img_mean = np.where(cd_ <= p.min_diag, _FILL, dmean[np.minimum(cd_, D)])
    keep &= img_val > p.enrichment * img_mean
    sel = np.flatnonzero(keep)
    t3 = time.perf_counter()
    if verbose:
        print(f"[mustache/{chrom}] {n} bins, {len(x)} pixels, {len(eligible)} analysable; {len(found)} "
              f"extrema, {len(cand)} at FDR < {p.fdr}, {len(sel)} after the filters; "
              f"scale space {t2 - t1:.1f} s, test + filters {t3 - t2:.1f} s")
    if len(sel) == 0:
        return _empty()

    lab = _clusters(cx[sel], cy[sel])
    resp = best[cand][sel]
    order = np.lexsort((-resp, fdr[sel], lab))           # per cluster: lowest FDR, then largest response
    lab_o = lab[order]
    first = np.r_[True, lab_o[1:] != lab_o[:-1]]
    head = sel[order[first]]
    size = np.bincount(lab)[lab_o[first]]
    i_, j_ = cx[head], cy[head]
    out = pd.DataFrame({
        "chrom1": chrom, "start1": starts[i_].astype(np.int64), "end1": (starts[i_] + binsize).astype(np.int64),
        "chrom2": chrom, "start2": starts[j_].astype(np.int64), "end2": (starts[j_] + binsize).astype(np.int64),
        "score": -np.log10(np.maximum(pval[head], 1e-300)),
        "pval": pval[head], "fdr": fdr[head], "scale": scale[head], "response": best[cand][head],
        "cluster_size": size.astype(np.int64), "summit_i": i_.astype(np.int64), "summit_j": j_.astype(np.int64),
    })
    return out.sort_values(["start1", "start2"], ignore_index=True)


def _empty() -> pd.DataFrame:
    cols = {"chrom1": str, "start1": "int64", "end1": "int64", "chrom2": str, "start2": "int64", "end2": "int64",
            "score": "float64", "pval": "float64", "fdr": "float64", "scale": "float64", "response": "float64",
            "cluster_size": "int64", "summit_i": "int64", "summit_j": "int64"}
    return pd.DataFrame({c: pd.Series(dtype=t) for c, t in cols.items()})


# ----------------------------------------------------------------------------------------------------------
# public API
# ----------------------------------------------------------------------------------------------------------

def call_loops_mustache(
    cd,
    *,
    contacts: Optional[str] = None,
    chrom=None,
    resolution: Optional[int] = None,
    balance: bool = True,
    params: Optional[MustacheParams] = None,
    key_added: Optional[str] = "loops.mustache",
    copy: bool = False,
    tile: int = 256,
    verbose: bool = False,
):
    """Loops of a Hi-C map by multi-scale blob detection (Mustache).

    Each diagonal of the balanced map is turned into local z-scores; the band near the diagonal is
    smoothed with Gaussians of growing width, and loops are the pixels where the difference of
    Gaussians is a maximum in space and across scales, significant against an exponential fit of the
    responses (Benjamini-Hochberg), in a densely observed neighbourhood and enriched over their diagonal
    (Roayaei Ardakany et al. 2020; steps and deviations from the reference code in the module docstring).
    The map is read and processed as a band (memory linear in the chromosome length).

    Parameters
    ----------
    cd : ChromData, str or cooler.Cooler
        A ``ChromData`` with the map linked (``cd.link_cool``), or the path of a ``.cool`` / ``.mcool`` /
        a ``cooler.Cooler`` (then nothing is stored: ``key_added`` is ignored).
    contacts : str, optional
        Key of the linked map (``None``: the only one) or the path of a map.
    chrom : str, sequence of str, or None
        Chromosome(s), as named in the map.  ``None``: the chromosomes of ``cd.spots`` the map has, or
        every chromosome of the map (Hi-C-only data); chromosomes with too few pixels give no loops.
    resolution : int, optional
        The level of an ``.mcool``; checked against a ``.cool``.
    balance : bool
        Use the balancing weights (``weight`` column; raw counts with a warning when there are none).
    params : MustacheParams, optional
    key_added : str or None
        ``cd.results`` / ``cd.intervals`` key (default ``"loops.mustache"``); ``None`` does not store.
    copy : bool
        ``True``: return a new ChromData holding the result.
    tile : int
        Rows of the map processed at once (memory / speed only; results do not depend on it).
    verbose : bool
        Print counts and timings per chromosome.

    Returns
    -------
    DataFrame (``copy=False``) or ChromData (``copy=True``)
        A ``pair`` interval table, one row per loop: ``chrom1, start1, end1, chrom2, start2, end2`` (the
        two anchor bins), ``score`` (``-log10 pval``), ``pval``, ``fdr`` (Benjamini-Hochberg), ``scale``
        (detection sigma, pixels), ``response`` (difference of Gaussians), ``cluster_size`` (candidate
        pixels merged) and ``summit_i`` / ``summit_j`` (bin indices within the chromosome).

    References
    ----------
    Roayaei Ardakany A, Gezer HT, Lonardi S, Ay F (2020).  Mustache: multi-scale detection of chromatin
    loops from Hi-C and Micro-C maps using scale-space representation.  *Genome Biology* 21:256.

    Examples
    --------
    >>> hic = ds.load("rao2014_imr90_chr21")                         # doctest: +SKIP
    >>> rebin_map(hic, "bulk", resolution=10_000)                    # doctest: +SKIP
    >>> loops = call_loops_mustache(hic, contacts="bulk_10kb")       # doctest: +SKIP
    """
    from uchrom.fea.band import read_band
    from uchrom.fea.maps import _is_chromdata, _is_cooler, map_path, open_map

    params = params or MustacheParams()
    is_cd = _is_chromdata(cd)
    if copy and (key_added is None or not is_cd):
        raise ValueError("call_loops_mustache(copy=True) needs a ChromData and a key_added")
    if _is_cooler(cd):
        clr, path = cd, str(cd.uri)
    else:
        path = map_path(cd, contacts)
        clr = open_map(path, resolution=resolution)
    binsize = int(clr.binsize)
    max_dist = params.max_dist if params.max_dist is not None else default_max_dist(binsize)
    D = int(max_dist // binsize)

    if chrom is None:
        wanted = resolve_chroms(cd, None) if is_cd and len(cd.spots) else []
        chroms = [c for c in wanted if c in clr.chromnames] or list(clr.chromnames)
    else:
        chroms = [str(chrom)] if isinstance(chrom, str) else [str(c) for c in chrom]
        missing = [c for c in chroms if c not in clr.chromnames]
        if missing:
            raise ValueError(f"not in the map: {missing} ({list(clr.chromnames)[:10]})")

    frames: List[pd.DataFrame] = []
    for c in chroms:
        band = read_band(clr, chrom=c, max_dist=D * binsize, balance=balance)
        v = band.values(balance)
        keep = np.isfinite(v) & (v > 0) & (band.diag <= D)
        x, y, v = band.i[keep], band.j[keep], v[keep]
        starts = band.starts
        del band, keep
        frames.append(_call_pixels(c, starts, binsize, x, y, v, params, D=D, tile=int(tile), verbose=verbose))
    table = merge_tables(frames, _empty())
    if not is_cd:
        return table
    if contacts is not None and path == str(Path(str(contacts)).expanduser()):
        label = path                                            # a map given by its path
    else:
        from uchrom.fea.maps import _map_key

        label = _map_key(cd, contacts)
    inputs = {"contacts": label, "contacts_path": str(path), "resolution": binsize, "balance": bool(balance),
              "chrom": list(chroms), "max_dist": int(D * binsize)}
    return store_and_return(
        cd, table, key_added=key_added, copy=copy, kind="intervals", interval_kind="pair",
        function="uchrom.strc.loop.call_loops_mustache", params=params, inputs=inputs,
    )
