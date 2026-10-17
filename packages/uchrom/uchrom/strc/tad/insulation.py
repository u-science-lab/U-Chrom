"""TAD boundaries and domains of a Hi-C map by the diamond insulation score.

The insulation score of a bin (Crane et al. 2015, *Nature* 523:240) is the contact frequency in a ``w x w``
square that slides along the diagonal of the map with its corner on the bin — the contacts between the ``w``
bins up to the bin and the ``w`` bins from it on.  Domain boundaries insulate the two sides from each other,
so they are local minima of the score.  The definitions here are those of the cooltools ``insulation``
(Open2C et al. 2024, *PLoS Comput Biol* 20:e1012067):

* **score** — the mean balanced contact of the ``w x w`` diamond over its *valid* pixels (both bins unmasked,
  separation ``>= ignore_diags``; ``n_valid_pixels``), divided by the median of the chromosome and taken as
  log2 (0 -> NaN);
* **boundary strength** — every local minimum of the log2 score (over the bins whose diamond has at least
  ``min_frac_valid_pixels`` of its pixels valid) with its topographic prominence along the chromosome;
* **boundaries** — the minima whose strength passes a threshold set by Li's minimum cross-entropy method
  (Li & Lee 1993, *Pattern Recognit.* 26:617; Li & Tam 1998, *Pattern Recognit. Lett.* 18:771), cooltools'
  default; Otsu's method (1979) or a fixed strength can be chosen;
* **domains** (this module) — the stretches between consecutive boundaries, plus the stretch from the first
  scored bin to the first boundary and from the last boundary to the last scored bin of each chromosome; a
  domain never spans ``window`` or more consecutive bins without a score (a masked region).

The map is read as a band of pixels near the diagonal (:func:`uchrom.fea.band.read_band`), never as a dense
matrix: the diamond sums are a difference array over the pixels (``O(pixels)``), the valid-pixel counts
cumulative sums over the bins.  Own implementation, no cooltools dependency; validated against cooltools
0.7.1 in uchrom-reproducibility ``supp_table3/hic_structures/insulation.py`` (scores within 1e-13, identical boundaries).

Deliberate differences from cooltools: ``min_frac_valid_pixels`` is a fraction of a *full* diamond (cooltools:
of the largest count in its table — the same whenever a chromosome has ``w`` valid bins in a row);
``min_dist_bad_bin`` counts masked bins only (cooltools also the chromosome ends); Otsu's threshold is taken
over the finite strengths (cooltools 0.7.1 fails on their NaNs); a default window (cooltools has none).
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass, replace
from typing import Dict, List, Optional, Sequence, Tuple, Union

import numpy as np
import pandas as pd

from uchrom.convention import merge_tables, resolve_chroms, store_and_return

#: pixels per chunk of the diamond sums and of the pixel-table read (bounds the temporaries: ~100 MB peak
#: on chr1 at 5 kb, as fast as larger chunks)
CHUNK = 2_000_000
#: ``ignore_diags`` when the map's balancing weights do not record one (``cooler balance`` default)
DEFAULT_IGNORE_DIAGS = 2
#: default diamond side (bp; rounded to whole bins, at least ``MIN_WINDOW_BINS``): the scale at which the
#: boundaries agree best with the Rao 2014 Arrowhead domain edges at 5, 10 and 25 kb
#: (uchrom-reproducibility ``supp_table3/hic_structures/insulation.py``)
DEFAULT_WINDOW_BP = 100_000
MIN_WINDOW_BINS = 3


@dataclass(frozen=True)
class InsulationParams:
    """Knobs of :func:`insulation_score` and :func:`call_tads_insulation` (defaults: cooltools ``insulation``).

    Attributes
    ----------
    window_bp : int, optional
        Side of the diamond, bp (a multiple of the bin size).  ``None``: 100 kb in whole bins, at least 3
        (20 bins at 5 kb, 10 at 10 kb, 4 at 25 kb, 3 at 50 kb) — the scale whose boundaries match the Rao 2014
        Arrowhead domain edges best.  On a map of variable-size bins the window is
        ``round(window_bp / median bin size)`` bins.
    ignore_diags : int, optional
        Pixels closer to the diagonal than this (in bins) are left out.  ``None``: the ``ignore_diags`` the map
        was balanced with (``bins/weight`` attributes), else 2.
    statistic : {"mean", "sum"}
        ``"mean"``: sum over the valid pixels / ``n_valid_pixels`` (cooltools, Crane et al. 2015); ``"sum"``:
        the sum alone (masked pixels then lower the score).
    min_frac_valid_pixels : float
        Bins whose diamond has fewer valid pixels than this fraction of a full diamond get no boundary
        strength (cooltools: 0.66).
    min_dist_bad_bin : int
        Bins closer than this (in bins) to a masked bin get no score (0: keep all).
    threshold : "li", "otsu" or float
        Rule for the boundary-strength cut, applied to all chromosomes of a call together: Li's minimum
        cross-entropy threshold (default; as cooltools), Otsu's threshold, or a fixed strength.  The strengths
        are a long right tail of strong boundaries over many shallow noise minima, not two balanced classes:
        Otsu cuts high, Li lower — on Rao 2014 IMR90 / GM12878 (5-25 kb, 100 kb window) Li recovers 0.11-0.20
        more of the Arrowhead domain edges at 0.01-0.12 less precision (higher F1 in every case).
    balance : bool
        Use the balanced map (the cooler ``weight`` column); ``False`` / an unbalanced map: raw counts.
    """

    window_bp: Optional[int] = None
    ignore_diags: Optional[int] = None
    statistic: str = "mean"
    min_frac_valid_pixels: float = 0.66
    min_dist_bad_bin: int = 0
    threshold: Union[str, float] = "li"
    balance: bool = True


# ----------------------------------------------------------------------------------------------------------
# kernels (one chromosome, bins 0..n-1)
# ----------------------------------------------------------------------------------------------------------

def n_valid_pixels(valid: np.ndarray, window: int, ignore_diags: int = 0) -> np.ndarray:
    """The number of valid pixels in the ``window x window`` diamond of every bin.

    The diamond of bin ``k`` holds the pixels ``(k - a, k + b)``, ``0 <= a, b < window``, inside the
    chromosome and with ``a + b >= ignore_diags``; a pixel is valid when both its bins are.  Counted as
    ``(valid bins in [k - w + 1, k]) * (valid bins in [k, k + w - 1])`` minus the pairs closer than
    ``ignore_diags``, so ``O(n * ignore_diags**2)``.
    """
    v = np.asarray(valid, dtype=bool).astype(np.int64)
    n, w = len(v), int(window)
    c = np.r_[0, np.cumsum(v)]
    k = np.arange(n)
    left = c[k + 1] - c[np.maximum(k - w + 1, 0)]
    right = c[np.minimum(k + w, n)] - c[k]
    out = left * right
    for a in range(min(ignore_diags, w)):
        for b in range(min(ignore_diags - a, w)):
            ok = (k - a >= 0) & (k + b < n)
            out[ok] -= v[k[ok] - a] * v[k[ok] + b]
    return out


def full_diamond(window: int, ignore_diags: int = 0) -> int:
    """Pixels of a diamond with every bin valid (``window**2`` minus the pairs closer than ``ignore_diags``)."""
    w = int(window)
    return w * w - sum(min(ignore_diags - a, w) for a in range(min(ignore_diags, w)))


def diamond_sums(i: np.ndarray, j: np.ndarray, values: np.ndarray, n: int, window: int,
                 ignore_diags: int = 0, chunk: int = CHUNK) -> Tuple[np.ndarray, np.ndarray]:
    """Sum of ``values`` over the diamond of every bin, and the number of finite pixels in it.

    Pixel ``(i, j)`` (``i <= j``) lies in the diamond of bins ``max(i, j - w + 1) .. min(j, i + w - 1)`` (a
    run when ``j - i <= 2 (w - 1)``), so each pixel adds its value at the first bin of its run and removes
    it after the last one; a cumulative sum gives the diamond sums.  Pixels with a non-finite value or
    separation ``< ignore_diags`` are left out.

    Returns
    -------
    sums : ndarray (n,) float64
        0 exactly where no pixel contributes.
    nnz : ndarray (n,) int64
        The pixels that contribute (stored, finite) per diamond.
    """
    w = int(window)
    acc = np.zeros(n + 1)
    cnt = np.zeros(n + 1, dtype=np.int64)
    for s in range(0, len(i), chunk):
        ii, jj, vv = i[s:s + chunk], j[s:s + chunk], values[s:s + chunk]
        d = jj - ii
        sel = (d >= ignore_diags) & (d <= 2 * (w - 1)) & np.isfinite(vv)
        ii, jj, vv = ii[sel], jj[sel], vv[sel]
        lo = np.maximum(ii, jj - w + 1)
        hi = np.minimum(jj, ii + w - 1) + 1
        acc += np.bincount(lo, vv, minlength=n + 1) - np.bincount(hi, vv, minlength=n + 1)
        cnt += np.bincount(lo, minlength=n + 1) - np.bincount(hi, minlength=n + 1)
    nnz = np.cumsum(cnt)[:n]
    sums = np.cumsum(acc)[:n]
    sums[nnz == 0] = 0.0                       # no rounding residue where nothing contributes
    return sums, nnz


def boundary_strength(track: np.ndarray) -> np.ndarray:
    """Prominence of every local minimum of ``track`` (NaN elsewhere), as cooltools ``find_boundaries``.

    NaN bins are skipped (a minimum is lower than its nearest finite neighbours).  The prominence of a
    minimum is its depth below the higher of the two highest points between it and the nearest lower point
    on each side; a side with no lower point does not count; the deepest minimum is measured against the
    highest local maximum.  (Topographic prominence of ``-track``; the sides via
    :func:`scipy.signal.peak_prominences`.)
    """
    from scipy.signal import peak_prominences

    track = np.asarray(track, dtype=np.float64)
    out = np.full(len(track), np.nan)
    pos = np.flatnonzero(np.isfinite(track))
    x = -track[pos]
    if len(x) < 3:
        return out
    peaks = np.flatnonzero((x[1:-1] > x[:-2]) & (x[1:-1] > x[2:])) + 1
    if not len(peaks):
        return out
    _, lb, rb = peak_prominences(x, peaks)
    h = x[peaks]
    has_left = np.maximum.accumulate(x)[peaks - 1] > h
    has_right = np.maximum.accumulate(x[::-1])[::-1][peaks + 1] > h
    lmin, rmin = x[lb], x[rb]
    with np.errstate(invalid="ignore"):
        prom = np.where(has_left & has_right, h - np.maximum(lmin, rmin),
                        np.where(has_left, h - lmin, np.where(has_right, h - rmin, np.nan)))
    top = np.flatnonzero(~has_left & ~has_right)
    if len(top):                                # the global maximum: against the lowest local minimum
        mins = np.flatnonzero((x[1:-1] < x[:-2]) & (x[1:-1] < x[2:])) + 1
        prom[top[0]] = h[top[0]] - (x[mins].min() if len(mins) else x.min())
    out[pos[peaks]] = prom
    return out


def threshold_li(values: np.ndarray) -> float:
    """Li's iterative minimum cross-entropy threshold (Li & Tam 1998) of the finite ``values``.

    The threshold ``t`` is iterated as ``(m_b - m_f) / (ln m_b - ln m_f)`` from the mean, where ``m_b`` /
    ``m_f`` are the means below / above ``t`` (values shifted to start at 0), until it moves by less than half
    the smallest gap between distinct values — the float branch of ``skimage.filters.threshold_li``.
    """
    x = np.asarray(values, dtype=np.float64)
    x = x[np.isfinite(x)]
    if x.size == 0:
        return float("nan")
    if np.all(x == x[0]):
        return float(x[0])
    x0 = x.min()
    x = x - x0
    tol = np.min(np.diff(np.unique(x))) / 2
    t_next, t_curr = x.mean(), -2 * tol
    while abs(t_next - t_curr) > tol:
        t_curr = t_next
        fg = x > t_curr
        m_f, m_b = x[fg].mean(), x[~fg].mean()
        if m_b == 0:
            break
        t_next = (m_b - m_f) / (np.log(m_b) - np.log(m_f))
    return float(t_next + x0)


def threshold_otsu(values: np.ndarray, nbins: int = 256) -> float:
    """Otsu's threshold (1979, *IEEE Trans. Syst. Man Cybern.* 9:62) of the finite ``values``: the centre of
    the histogram bin (``nbins`` over the range) that maximises the between-class variance."""
    x = np.asarray(values, dtype=np.float64)
    x = x[np.isfinite(x)]
    if x.size == 0:
        return float("nan")
    if np.all(x == x[0]):
        return float(x[0])
    counts, edges = np.histogram(x, bins=nbins, range=(x.min(), x.max()))
    centres = (edges[:-1] + edges[1:]) / 2
    w1 = np.cumsum(counts)
    w2 = np.cumsum(counts[::-1])[::-1]
    with np.errstate(invalid="ignore", divide="ignore"):
        m1 = np.cumsum(counts * centres) / w1
        m2 = (np.cumsum((counts * centres)[::-1]) / w2[::-1])[::-1]
    var12 = w1[:-1] * w2[1:] * (m1[:-1] - m2[1:]) ** 2
    return float(centres[np.nanargmax(var12)])


def _threshold(strengths: np.ndarray, rule: Union[str, float]) -> float:
    if isinstance(rule, str):
        name = rule.lower()
        if name == "li":
            return threshold_li(strengths)
        if name == "otsu":
            return threshold_otsu(strengths)
        raise ValueError(f"threshold={rule!r}: 'li', 'otsu' or a number")
    return float(rule)


def _dist_to_bad(bad: np.ndarray) -> np.ndarray:
    """Distance (bins) of every bin to the nearest masked bin (inf when there is none)."""
    idx = np.flatnonzero(bad)
    n = len(bad)
    if not len(idx):
        return np.full(n, np.inf)
    k = np.arange(n)
    r = np.searchsorted(idx, k)
    right = np.where(r < len(idx), idx[np.minimum(r, len(idx) - 1)] - k, np.inf)
    left = np.where(r > 0, k - idx[np.maximum(r - 1, 0)], np.inf)
    return np.minimum(left, right)


def _log2_score(sums: np.ndarray, nnz: np.ndarray, n_valid: np.ndarray, statistic: str) -> np.ndarray:
    with np.errstate(invalid="ignore", divide="ignore"):
        if statistic == "mean":
            score = np.where(n_valid > 0, sums / np.maximum(n_valid, 1), np.nan)
        elif statistic == "sum":
            score = np.where(n_valid > 0, sums, np.nan)
        else:
            raise ValueError(f"statistic={statistic!r}: 'mean' or 'sum'")
        finite = np.isfinite(score)
        if finite.any():
            score = score / np.median(score[finite])
        score[score == 0] = np.nan
        out = np.log2(score)
    out[~np.isfinite(out)] = np.nan
    return out


# ----------------------------------------------------------------------------------------------------------
# reading a map
# ----------------------------------------------------------------------------------------------------------

def _ignore_diags(clr, params: InsulationParams) -> int:
    if params.ignore_diags is not None:
        return int(params.ignore_diags)
    if params.balance:
        try:
            with clr.open("r") as grp:
                if "weight" in grp["bins"]:
                    value = grp["bins"]["weight"].attrs.get("ignore_diags")
                    if value is not None:
                        return int(value)
        except (KeyError, OSError):
            pass
    return DEFAULT_IGNORE_DIAGS


def _band(clr, chrom: str, max_diag: int, balance: bool):
    """The pixels of ``chrom`` within ``max_diag`` bins of the diagonal: :func:`read_band`, or (a map of
    variable-size bins, which is small) its pixel table."""
    from uchrom.fea.band import Band, read_band

    if clr.binsize:
        return read_band(clr, chrom=chrom, max_dist=max_diag * int(clr.binsize), balance=balance, chunk=CHUNK)
    lo, hi = clr.extent(chrom)
    bins = clr.bins()[lo:hi]
    weight = None
    if balance:
        if "weight" in bins.columns:
            weight = bins["weight"].to_numpy(dtype=np.float64)
        else:
            warnings.warn(f"{clr.uri}: not balanced (no 'weight' column); using raw counts", stacklevel=3)
    px = clr.matrix(balance=False, as_pixels=True).fetch(chrom)
    i = px["bin1_id"].to_numpy(np.int64) - lo
    j = px["bin2_id"].to_numpy(np.int64) - lo
    keep = (j >= i) & (j - i <= max_diag)
    return Band(chrom=str(chrom), binsize=0, starts=bins["start"].to_numpy(np.int64), i=i[keep], j=j[keep],
                count=px["count"].to_numpy(np.float64)[keep], weight=weight, max_diag=int(max_diag))


def _window_bins(clr, chroms: Sequence[str], window_bp: Optional[int]) -> Tuple[int, int]:
    """``(window_bp, window_bins)``: a multiple of a fixed bin size, or ``window_bp / median bin size``;
    ``window_bp=None``: 100 kb in whole bins, at least 3."""
    if clr.binsize:
        size = float(clr.binsize)
    else:
        bins = pd.concat([clr.bins().fetch(c) for c in chroms])
        size = float(np.median((bins["end"] - bins["start"]).to_numpy()))
    if window_bp is None:
        w = max(MIN_WINDOW_BINS, int(round(DEFAULT_WINDOW_BP / size)))
        return int(round(w * size)), w
    if clr.binsize:
        if int(window_bp) % int(size):
            raise ValueError(f"window {window_bp} bp is not a multiple of the bin size ({int(size)} bp)")
        return int(window_bp), int(window_bp) // int(size)
    return int(window_bp), max(1, int(round(int(window_bp) / size)))


def _chroms(cd, clr, chrom) -> List[str]:
    """``chrom=None``: the chromosomes of ``cd``'s spots that the map has, else all of the map's."""
    if chrom is None:
        has_spots = hasattr(cd, "spots") and len(cd.spots) > 0
        wanted = resolve_chroms(cd, None) if has_spots else []
        return [c for c in wanted if c in clr.chromnames] or list(clr.chromnames)
    out = [str(chrom)] if isinstance(chrom, str) else [str(c) for c in chrom]
    missing = [c for c in out if c not in clr.chromnames]
    if missing:
        raise ValueError(f"not in the map: {missing} ({list(clr.chromnames)[:10]})")
    return out


def _resolve(cd, contacts, resolution):
    """``(cooler, path, provenance label)`` of the map: a ChromData + key / path, a path, or a cooler."""
    from uchrom.fea.maps import _is_cooler, _map_record, map_path, open_map

    if _is_cooler(cd):
        return cd, str(cd.uri), str(cd.uri)
    path = map_path(cd, contacts, resolution=resolution)
    clr = open_map(path, resolution=resolution)
    label = _map_record(cd, contacts).get("key") or path if hasattr(cd, "uns") else path
    return clr, path, str(label)


# ----------------------------------------------------------------------------------------------------------
# per-chromosome insulation + boundaries
# ----------------------------------------------------------------------------------------------------------

def _chrom_tracks(clr, chrom: str, windows: Sequence[Tuple[int, int]], ignore_diags: int,
                  params: InsulationParams) -> pd.DataFrame:
    """The insulation columns of one chromosome for every ``(window_bp, window_bins)``, before thresholding."""
    lo, hi = clr.extent(chrom)
    bins = clr.bins()[lo:hi]
    n = hi - lo
    out = pd.DataFrame({"chrom": str(chrom), "start": bins["start"].to_numpy(np.int64),
                        "end": bins["end"].to_numpy(np.int64), "bin_index": np.arange(n, dtype=np.int64)})
    wmax = max(w for _, w in windows)
    band = _band(clr, chrom, 2 * (wmax - 1), params.balance)
    valid = band.valid
    out["is_bad_bin"] = ~valid
    values = band.values(params.balance)
    near_bad = (_dist_to_bad(~valid) < params.min_dist_bad_bin) if params.min_dist_bad_bin else None
    for wbp, w in windows:
        nv = n_valid_pixels(valid, w, ignore_diags)
        sums, nnz = diamond_sums(band.i, band.j, values, n, w, ignore_diags)
        log2 = _log2_score(sums, nnz, nv, params.statistic)
        if near_bad is not None:
            log2[near_bad] = np.nan
        usable = nv >= params.min_frac_valid_pixels * full_diamond(w, ignore_diags)
        if near_bad is not None:
            usable &= ~near_bad
        strength = np.full(n, np.nan)
        strength[usable] = boundary_strength(log2[usable])
        out[f"log2_insulation_score_{wbp}"] = log2
        out[f"n_valid_pixels_{wbp}"] = nv
        out[f"boundary_strength_{wbp}"] = strength
    return out


def _insulation_table(clr, chroms: Sequence[str], windows: Sequence[Tuple[int, int]], ignore_diags: int,
                      params: InsulationParams) -> Tuple[pd.DataFrame, Dict[int, float]]:
    parts = [_chrom_tracks(clr, c, windows, ignore_diags, params) for c in chroms]
    table = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()
    thresholds = {}
    for wbp, _ in windows:
        col = f"boundary_strength_{wbp}"
        s = table[col].to_numpy() if len(table) else np.zeros(0)
        thr = _threshold(s, params.threshold)
        thresholds[wbp] = thr
        with np.errstate(invalid="ignore"):
            table[f"is_boundary_{wbp}"] = s >= thr
    return table, thresholds


def _jsonable(x: float) -> Optional[float]:
    return float(x) if np.isfinite(x) else None


def _windows(clr, chroms, windows, params) -> List[Tuple[int, int]]:
    ws = [params.window_bp] if windows is None else (
        [windows] if np.isscalar(windows) else list(windows))
    out = [_window_bins(clr, chroms, None if w is None else int(w)) for w in ws]
    if not out:
        raise ValueError("windows: give at least one window")
    if any(w < 1 for _, w in out):
        raise ValueError(f"windows {ws}: at least one bin")
    seen, unique = set(), []
    for wbp, w in out:
        if wbp not in seen:
            seen.add(wbp)
            unique.append((wbp, w))
    return unique


def _loci_track(cd, table: pd.DataFrame, column: str) -> Optional[np.ndarray]:
    """``table[column]`` on the loci of ``cd``: the map bin that holds each locus' midpoint (NaN outside)."""
    bins = getattr(cd, "bins", None)
    if bins is None or not len(bins):
        return None
    values = np.full(len(bins), np.nan)
    lchrom = bins["chrom"].astype(str).to_numpy()
    mid = (bins["start"].to_numpy(np.int64) + bins["end"].to_numpy(np.int64)) // 2
    tchrom = table["chrom"].astype(str).to_numpy()
    hit = False
    for c in np.unique(tchrom):
        rows = np.flatnonzero(tchrom == c)
        want = np.flatnonzero(lchrom == c)
        if not len(want):
            continue
        starts = table["start"].to_numpy(np.int64)[rows]
        ends = table["end"].to_numpy(np.int64)[rows]
        k = np.searchsorted(starts, mid[want], side="right") - 1
        ok = (k >= 0) & (mid[want] < ends[np.clip(k, 0, None)])
        values[want[ok]] = table[column].to_numpy(dtype=float)[rows[k[ok]]]
        hit = hit or bool(ok.any())
    return values if hit else None


# ----------------------------------------------------------------------------------------------------------
# public API
# ----------------------------------------------------------------------------------------------------------

def insulation_score(
    cd,
    *,
    contacts=None,
    chrom=None,
    resolution: Optional[int] = None,
    windows=None,
    params: Optional[InsulationParams] = None,
    key_added: Optional[str] = "insulation",
    copy: bool = False,
):
    """Diamond insulation score of a Hi-C map, with the boundary strength of its minima.

    The insulation of Crane et al. (2015) as computed by cooltools ``insulation`` (Open2C et al. 2024): the
    mean balanced contact in the ``w x w`` diamond on the diagonal at each bin, over the diamond's valid
    pixels (``n_valid_pixels``: both bins unmasked, separation ``>= ignore_diags``), normalised by the
    chromosome median, log2.  Every local minimum gets a boundary strength (its prominence; bins whose
    diamond is less than ``min_frac_valid_pixels`` valid are left out) and ``is_boundary`` marks the minima
    above the threshold (Li by default), computed over all chromosomes of the call.

    Parameters
    ----------
    cd : ChromData, path or cooler.Cooler
        Holds the map (``cd.link_cool(path, key=...)``) and receives the result; or the path of a ``.cool`` /
        ``.mcool``, or an open ``cooler.Cooler`` (nothing is stored then).
    contacts : str, optional
        Key of the linked map (``None``: the only one) or the path of a map.
    chrom : str, sequence of str, or None
        ``None``: the chromosomes of ``cd``'s spots that the map has, else every chromosome of the map.
    resolution : int, optional
        The level of an ``.mcool``.
    windows : int or sequence of int, optional
        Diamond sides in bp (multiples of the bin size); default ``(params.window_bp,)`` (100 kb in whole
        bins, at least 3).
    params : InsulationParams, optional
    key_added : str or None
        ``cd.results`` key (default ``"insulation"``; ``None``: not stored).  When stored, the log2 score of
        each window is also written on the loci of ``cd`` (the map bin holding each locus' midpoint) as
        ``cd.bin_tracks[f"{key_added}.log2_{window}"]``, if ``cd`` has loci on these chromosomes.
    copy : bool
        ``True``: return a copy of ``cd`` holding the result.

    Returns
    -------
    DataFrame (``copy=False``) or ChromData (``copy=True``)
        One row per bin of the map: ``chrom, start, end, bin_index`` (within the chromosome),
        ``is_bad_bin`` (masked by balancing) and per window ``W`` (bp) ``log2_insulation_score_W``,
        ``n_valid_pixels_W``, ``boundary_strength_W`` (NaN off the minima) and ``is_boundary_W`` — the
        columns of cooltools ``insulation``.
    """
    params = params or InsulationParams()
    if copy and key_added is None:
        raise ValueError("insulation_score(): copy=True needs a key_added")
    clr, path, label = _resolve(cd, contacts, resolution)
    chroms = _chroms(cd, clr, chrom)
    wins = _windows(clr, chroms, windows, params)
    ig = _ignore_diags(clr, params)
    table, thresholds = _insulation_table(clr, chroms, wins, ig, params)
    if not hasattr(cd, "results"):
        return table
    inputs = {"contacts": label, "contacts_path": str(path),
              "resolution": int(clr.binsize) if clr.binsize else None, "chrom": list(chroms),
              "windows_bp": [w for w, _ in wins], "windows_bins": [b for _, b in wins], "ignore_diags": ig,
              "thresholds": {str(w): _jsonable(t) for w, t in thresholds.items()}}
    out = store_and_return(cd, table, key_added=key_added, copy=copy, kind="table",
                           function="uchrom.strc.tad.insulation_score", params=params, inputs=inputs)
    if key_added is not None:
        target = out if copy else cd
        for wbp, _ in wins:
            values = _loci_track(target, table, f"log2_insulation_score_{wbp}")
            if values is not None:
                bt = target.bin_tracks.copy()
                bt[f"{key_added}.log2_{wbp}"] = values
                target.bin_tracks = bt
    return out


_DOMAIN_COLUMNS = {"chrom": str, "start": "int64", "end": "int64", "start_bin": "int64", "end_bin": "int64"}
_BOUNDARY_COLUMNS = {"chrom": str, "start": "int64", "end": "int64", "bin_index": "int64",
                     "log2_insulation_score": float, "boundary_strength": float}


def _empty(columns) -> pd.DataFrame:
    return pd.DataFrame({c: pd.Series(dtype=t) for c, t in columns.items()})


def _chrom_domains(track: pd.DataFrame, wbp: int, window_bins: int) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Boundaries and domains of one chromosome from its insulation track."""
    is_b = track[f"is_boundary_{wbp}"].to_numpy(bool)
    scored = np.isfinite(track[f"log2_insulation_score_{wbp}"].to_numpy())
    starts = track["start"].to_numpy(np.int64)
    ends = track["end"].to_numpy(np.int64)
    chrom = str(track["chrom"].iat[0])
    b = np.flatnonzero(is_b)
    bounds = pd.DataFrame({"chrom": chrom, "start": starts[b], "end": ends[b], "bin_index": b.astype(np.int64),
                           "log2_insulation_score": track[f"log2_insulation_score_{wbp}"].to_numpy()[b],
                           "boundary_strength": track[f"boundary_strength_{wbp}"].to_numpy()[b]})
    if not len(b):
        return bounds, _empty(_DOMAIN_COLUMNS)
    # segments of scored bins: a run of >= window unscored bins separates two segments
    sc = np.flatnonzero(scored)
    gap = np.diff(sc) - 1 >= window_bins
    seg_of_scored = np.r_[0, np.cumsum(gap)]
    seg_first = sc[np.r_[True, gap]]
    seg_last = sc[np.r_[gap, True]]
    seg = seg_of_scored[np.searchsorted(sc, b)]          # boundaries are scored bins
    edges = [(int(b[k]), int(b[k + 1])) for k in range(len(b) - 1) if seg[k] == seg[k + 1]]
    if seg_first[seg[0]] < b[0]:
        edges.insert(0, (int(seg_first[seg[0]]), int(b[0])))
    if seg_last[seg[-1]] + 1 > b[-1] + 1:
        edges.append((int(b[-1]), int(seg_last[seg[-1]]) + 1))
    s = np.array([e[0] for e in edges], dtype=np.int64)
    e = np.array([e[1] for e in edges], dtype=np.int64)
    domains = pd.DataFrame({"chrom": chrom, "start": starts[s],
                            "end": np.where(e < len(starts), starts[np.minimum(e, len(starts) - 1)], ends[e - 1]),
                            "start_bin": s, "end_bin": e})
    return bounds, domains


def call_tads_insulation(
    cd,
    *,
    contacts=None,
    chrom=None,
    resolution: Optional[int] = None,
    params: Optional[InsulationParams] = None,
    key_added: Optional[str] = "tads.insulation",
    copy: bool = False,
):
    """TAD boundaries and domains of a Hi-C map by the diamond insulation score.

    Boundaries are the minima of the insulation score (Crane et al. 2015) whose boundary strength (the
    prominence of the minimum) passes Li's minimum cross-entropy threshold, as cooltools ``insulation``
    (Open2C et al. 2024) calls them; see :func:`insulation_score`.  Domains are the stretches between
    consecutive boundaries (and from the first / to the last scored bin of a chromosome); a domain never
    spans ``window`` or more consecutive bins without a score (masked regions such as centromeres), so the
    boundaries of the domain table (:func:`uchrom.strc.tad.tad_boundaries`) are exactly the called ones.

    Parameters
    ----------
    cd : ChromData, path or cooler.Cooler
        Holds the map (``cd.link_cool``) and receives the result (a path / cooler: the domains are returned).
    contacts : str, optional
        Key of the linked map (``None``: the only one) or the path of a map.
    chrom : str, sequence of str, or None
        ``None``: the chromosomes of ``cd``'s spots that the map has, else every chromosome of the map.
    resolution : int, optional
        The level of an ``.mcool``.
    params : InsulationParams, optional
        ``window_bp`` (default 100 kb in whole bins, at least 3), ``threshold`` (default ``"li"``), …
    key_added : str or None
        ``cd.results`` / ``cd.intervals`` key of the domains (default ``"tads.insulation"``; ``None``: not
        stored).  Also stored: ``f"{key_added}.boundaries"`` (results + a ``peak`` interval table) and the
        per-bin track ``f"{key_added}.score"`` (:func:`insulation_score` columns of the window).
    copy : bool
        ``True``: return a copy of ``cd`` holding the result.

    Returns
    -------
    DataFrame (``copy=False``) or ChromData (``copy=True``)
        The domains: ``chrom, start, end, start_bin, end_bin`` (map bins within the chromosome, ``end_bin``
        exclusive; ``start`` is the start of the boundary bin, ``end`` the start of the next boundary bin) —
        the columns of :func:`call_tads_di`.  The boundaries table has ``chrom, start, end`` (the boundary
        bin), ``bin_index``, ``log2_insulation_score`` and ``boundary_strength``.
    """
    params = params or InsulationParams()
    if copy and key_added is None:
        raise ValueError("call_tads_insulation(): copy=True needs a key_added")
    clr, path, label = _resolve(cd, contacts, resolution)
    chroms = _chroms(cd, clr, chrom)
    (wbp, wbins), = _windows(clr, chroms, None, params)
    ig = _ignore_diags(clr, params)
    table, thresholds = _insulation_table(clr, chroms, [(wbp, wbins)], ig, params)
    b_parts, d_parts = [], []
    for _, track in table.groupby("chrom", sort=False):
        bounds, domains = _chrom_domains(track.reset_index(drop=True), wbp, wbins)
        b_parts.append(bounds)
        d_parts.append(domains)
    domains = merge_tables(d_parts, _empty(_DOMAIN_COLUMNS)).reset_index(drop=True)
    bounds = merge_tables(b_parts, _empty(_BOUNDARY_COLUMNS)).reset_index(drop=True)
    if not hasattr(cd, "results"):
        return domains
    inputs = {"contacts": label, "contacts_path": str(path),
              "resolution": int(clr.binsize) if clr.binsize else None, "chrom": list(chroms),
              "window_bp": wbp, "window_bins": wbins, "ignore_diags": ig, "threshold": _jsonable(thresholds[wbp]),
              "n_boundaries": int(len(bounds))}
    params_used = replace(params, window_bp=wbp)
    extra, intervals = [], []
    if key_added is not None:
        extra = [(f"{key_added}.boundaries", bounds, "intervals"), (f"{key_added}.score", table, "table")]
        intervals = [(f"{key_added}.boundaries", bounds, "peak")]
    return store_and_return(cd, domains, key_added=key_added, copy=copy, kind="intervals",
                            interval_kind="domain", function="uchrom.strc.tad.call_tads_insulation",
                            params=params_used, inputs=inputs, extra=extra, intervals=intervals)


__all__ = [
    "InsulationParams",
    "boundary_strength",
    "call_tads_insulation",
    "diamond_sums",
    "full_diamond",
    "insulation_score",
    "n_valid_pixels",
    "threshold_li",
    "threshold_otsu",
]
