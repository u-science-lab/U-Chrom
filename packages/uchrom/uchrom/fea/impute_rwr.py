"""Imputation of single-cell contact maps: convolution and random walk with restart (RWR).

A single cell's contact map is too sparse to be read pixel by pixel.  scHiCluster (Zhou et al. 2019, *PNAS*
116:14011) and SnapHiC (Yu et al. 2021, *Nat Methods* 18:1056) impute it by a random walk with restart on
the cell's chromosome graph — a node per bin, an edge between neighbouring bins and between the two bins of
every contact — whose stationary distribution spreads each contact to the bins around it::

    Q = rp (I - (1 - rp) P)^-1,    P = D^-1 A    (A adjacency, D degrees; rp: restart probability)

SnapHiC symmetrises ``R = Q + Q^T`` and normalises every diagonal (genomic distance) to z-scores.  With
``M = D - (1 - rp) A`` (symmetric positive definite) ``R_ij = rp (M^-1)_ij (d_i + d_j)``, which is how both
implementations here compute it:

* **numpy** (the reference): per window a dense ``M`` and its inverse (``scipy.linalg.cho_solve``, LAPACK);
* **native** (``uchrom_maps.rwr_band``, Rust, when ``packages/uchrom-maps`` is installed): a Cholesky
  factorisation of ``M`` in profile storage and the selected inversion of Takahashi et al. (1973) — only the
  entries of ``M^-1`` inside the profile, which holds the band — windows in parallel.  Equal to the
  reference up to rounding: on real cells (Nagano 2017 mES, chr1 / chr19, 10 kb) the bands differ by at most
  9e-15 relatively and the z-scores by 9e-14 (uchrom-reproducibility ``benchmarks/toolkit_parity/sc_structures/impute_speed.py``); 7x faster on one
  thread, ~60x on 16 (chr1; AMD EPYC 9754).

``BACKEND`` (``"auto"``, ``"native"``, ``"numpy"``) forces either path.

**Sliding windows** (SnapHiC2: Li et al. 2022, *Comput Struct Biotechnol J* 20:2778): the RWR of a whole
chromosome needs its dense inverse (``n^3``; 20,000 bins at 10 kb); instead each window of ``window`` bins
(the chain and the contacts with both ends in it) is solved alone, windows start every ``step`` bins
(``window / 2``), and a pixel takes the value of the window whose centre is nearest to its midpoint.  SnapHiC2
chooses the window as the smallest of 10, 20, ..., 100 Mb holding more than 80 % of the cells' contacts
(:func:`auto_window`).  ``window=None`` solves each chromosome whole (SnapHiC's original method).

Functions
---------
:func:`rwr_band` — one cell, one chromosome: the band ``R(i, i + d)``, ``0 <= d <= max_diag``.
:func:`zscore_band` — SnapHiC's per-diagonal z-scores of a band.
:func:`impute_maps` — every cell of a ``ChromData`` (maps linked as ``.scool`` or embedded): yields
``(cell, chrom, band)``.
:func:`convolve_maps`, :func:`rwr_dense` — a dense batch imputation in scHiCluster's style (row-normalised,
with self-loops, symmetrised); ``uchrom.emb.hic`` follows the authors' code instead.

Deliberate deviations from SnapHiC's code (``github.com/HuMingLab/SnapHiC`` v0.2.x, read for the method):
the windows here own every pixel — SnapHiC's sliding windows leave the anti-diagonals ``i + j = (2k + 1) *
step`` and the corner ``i + j <= step`` at 0; the linear systems are solved by a symmetric factorisation
(SnapHiC: ``scipy.linalg.solve`` of ``I - (1 - rp) P^T``, the same matrix up to a diagonal scaling).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterator, List, Optional, Sequence, Tuple, Union

import numpy as np

__all__ = ["ImputeParams", "rwr_band", "zscore_band", "auto_window", "impute_maps", "plan_windows",
           "convolve_maps", "rwr_dense", "read_cell_pixels", "BACKEND"]

#: ``"auto"`` (the native ``uchrom_maps`` when installed, else numpy), ``"native"`` or ``"numpy"``
BACKEND = "auto"

#: window sizes tried by :func:`auto_window` (bp): SnapHiC2's 10, 20, ..., 100 Mb
AUTO_WINDOWS = tuple(int(k * 10_000_000) for k in range(1, 11))
#: share of the contacts a window must hold (SnapHiC2)
AUTO_SHARE = 0.8


def _maps_kernels(backend: Optional[str]):
    """``uchrom_maps`` for ``backend`` (``None``: :data:`BACKEND`), or ``None`` for numpy."""
    backend = BACKEND if backend is None else backend
    if backend == "numpy":
        return None
    if backend not in ("auto", "native"):
        raise ValueError(f"backend must be 'auto', 'native' or 'numpy', got {backend!r}")
    try:
        import uchrom_maps
    except ImportError:
        if backend == "native":
            raise ImportError("the native kernels are not installed: pip install ./packages/uchrom-maps "
                              "(u-chrom[maps])") from None
        return None
    if not hasattr(uchrom_maps, "rwr_band"):                       # an older build without the RWR kernels
        if backend == "native":
            raise ImportError("uchrom_maps has no rwr_band: reinstall packages/uchrom-maps")
        return None
    return uchrom_maps


@dataclass(frozen=True)
class ImputeParams:
    """Knobs of the RWR imputation (defaults: SnapHiC at 10 kb).

    Attributes
    ----------
    rp : float
        Restart probability (SnapHiC 0.05; scHiCluster 0.5).
    window : int, "auto" or None
        ``None`` (default): each chromosome solved whole, as the published SnapHiC (in the numpy path memory and
        time grow as ``n^2`` / ``n^3``: a dense chromosome matrix); or a sliding-window size, bp (a multiple of
        the bin size), ``"auto"``: SnapHiC2's rule (:func:`auto_window`).
    step : int, optional
        Window step, bp; default half the window.
    max_dist : int
        Band of the output, bp: pixels up to this separation (SnapHiC: the loop range plus a 50 kb buffer).
    min_sep : int
        Contacts closer than this many bins are left out (SnapHiC removes neighbouring bins: 2).
    chain : bool
        Link neighbouring bins (SnapHiC).
    normalize : bool
        SnapHiC's z-scores per diagonal (:func:`zscore_band`) instead of the raw RWR values.
    edge : int
        Bins at each chromosome end left out of the z-scores (SnapHiC: the 50 kb buffer, 5 bins at 10 kb).
    trim : float
        Share of each diagonal's largest values left out of its mean / standard deviation (1 %).
    min_sd : float
        Diagonals with a smaller standard deviation are set to 0.
    """

    rp: float = 0.05
    window: Union[int, str, None] = None
    step: Optional[int] = None
    max_dist: int = 2_050_000
    min_sep: int = 2
    chain: bool = True
    normalize: bool = True
    edge: int = 5
    trim: float = 0.01
    min_sd: float = 1e-6

    def __post_init__(self):
        if not 0 < self.rp < 1:
            raise ValueError(f"rp={self.rp} must be in (0, 1)")
        if isinstance(self.window, str) and self.window != "auto":
            raise ValueError(f"window={self.window!r}: bp, 'auto' or None")


# ----------------------------------------------------------------------------------------------------------
# windows
# ----------------------------------------------------------------------------------------------------------

def plan_windows(n: int, window: int, step: int, max_diag: int) -> Tuple[np.ndarray, np.ndarray, np.ndarray,
                                                                           np.ndarray]:
    """The windows of a chromosome of ``n`` bins (all in bins): ``(starts, ends, c_lo, c_hi)`` — window ``k``
    spans ``starts[k] .. ends[k] - 1`` and owns the pixels with ``c_lo[k] <= i + j < c_hi[k]`` (the pixel's
    midpoint nearest to the window's centre).  ``window == 0`` or ``>= n``: one window, the chromosome."""
    big = np.iinfo(np.int64)
    if n <= 0:
        z = np.zeros(0, np.int64)
        return z, z, z, z
    if window == 0 or window >= n:
        return (np.array([0]), np.array([n]), np.array([big.min]), np.array([big.max]))
    if not 0 < step <= window:
        raise ValueError(f"step {step} must be in 1..window ({window})")
    if max_diag + step > window:
        raise ValueError(f"window {window} bins too small for the band: needs window - step >= {max_diag}")
    top = 2 * n - 2 - window + step
    k_max = top // (2 * step) if top >= 0 else 0
    k = np.arange(k_max + 1, dtype=np.int64)
    starts = k * step
    ends = np.minimum(starts + window, n)
    c_lo = np.where(k == 0, big.min, 2 * starts + window - step)
    c_hi = np.where(k == k_max, big.max, 2 * (starts + step) + window - step)
    return starts, ends, c_lo, c_hi


def _window_bins(params: ImputeParams, binsize: int, window_bp: Optional[int]) -> Tuple[int, int]:
    """(window, step) in bins for the given window (bp; None: whole chromosome)."""
    if window_bp is None:
        return 0, 0
    if window_bp % binsize:
        raise ValueError(f"window {window_bp} bp is not a multiple of the {binsize} bp bins")
    w = window_bp // binsize
    step = params.step if params.step is not None else window_bp // 2
    if step % binsize:
        raise ValueError(f"step {step} bp is not a multiple of the {binsize} bp bins")
    return int(w), int(step // binsize)


def auto_window(distances, *, binsize: int, windows: Sequence[int] = AUTO_WINDOWS,
                share: float = AUTO_SHARE) -> int:
    """SnapHiC2's window size: the smallest of ``windows`` (bp) such that more than ``share`` of the contacts
    are closer than it.

    Parameters
    ----------
    distances : array or sequence of arrays
        Separations of the contacts in bins (``j - i``), pooled over cells and chromosomes.
    binsize : int
        Bin size, bp.
    """
    if isinstance(distances, (list, tuple)):
        distances = np.concatenate([np.asarray(d) for d in distances]) if len(distances) else np.zeros(0)
    d = np.asarray(distances, dtype=np.int64) * int(binsize)
    if not len(d):
        raise ValueError("no contacts to choose the window size from")
    for w in windows:
        if (d < w).mean() > share:
            return int(w)
    raise ValueError(f"no window up to {max(windows)} bp holds {share:.0%} of the contacts; pass window=")


# ----------------------------------------------------------------------------------------------------------
# one cell: RWR band (numpy reference + native) and z-scores
# ----------------------------------------------------------------------------------------------------------

def _edges(n: int, i, j, min_sep: int, chain: bool) -> Tuple[np.ndarray, np.ndarray]:
    """Unique undirected edges ``(a < b)``: contacts at least ``min_sep`` bins apart (+ the chain)."""
    i = np.asarray(i, np.int64)
    j = np.asarray(j, np.int64)
    if len(i) and (i.min() < 0 or j.min() < 0 or i.max() >= n or j.max() >= n):
        raise ValueError(f"contacts outside the chromosome's {n} bins")
    a, b = np.minimum(i, j), np.maximum(i, j)
    keep = (b - a) >= max(1, int(min_sep))
    a, b = a[keep], b[keep]
    if chain and n > 1:
        a = np.r_[a, np.arange(n - 1)]
        b = np.r_[b, np.arange(1, n)]
    key = np.unique(a * n + b)
    return key // n, key % n


def _snaphic_holes(n: int, W: int, step: int) -> np.ndarray:
    """The pixels SnapHiC v0.2's sliding windows never set (left at 0): sums ``i + j = (2k + 1) step`` and
    ``i + j <= step``."""
    c = 2 * np.arange(n)[:, None] + np.arange(W)[None, :]
    return (c <= step) | ((c - step) % (2 * step) == 0)


def _rwr_band_numpy(n: int, i, j, *, rp: float, window: int, step: int, max_diag: int, min_sep: int,
                    chain: bool, holes: bool = False) -> np.ndarray:
    from scipy.linalg import cho_factor, cho_solve

    ea, eb = _edges(n, i, j, min_sep, chain)
    starts, ends, c_lo, c_hi = plan_windows(n, window, step, max_diag)
    W = max_diag + 1
    band = np.full((n, W), np.nan)
    rows = np.arange(n)
    for s, e, lo, hi in zip(starts, ends, c_lo, c_hi):
        s, e = int(s), int(e)
        m = e - s
        sel = (ea >= s) & (eb < e)
        a, b = ea[sel] - s, eb[sel] - s
        A = np.zeros((m, m))
        A[a, b] = 1.0
        A[b, a] = 1.0
        deg = A.sum(axis=1)
        if (deg == 0).any():
            raise ValueError("a bin without neighbours in its window (chain=False and no contact): the walk is "
                             "undefined")
        M = np.diag(deg) - (1.0 - rp) * A
        G = cho_solve(cho_factor(M, lower=True), np.eye(m))
        R = rp * G * (deg[:, None] + deg[None, :])
        # owned pixels: rows s..e-1, offsets d with c = 2i + d in [lo, hi), i + d < e
        r = rows[s:e]
        d = np.arange(W)
        c = 2 * r[:, None] + d[None, :]
        own = (c >= lo) & (c < hi) & ((r[:, None] + d[None, :]) < e)
        ii, dd = np.nonzero(own)
        band[s + ii, dd] = R[ii, ii + dd]
    if holes and 0 < window < n:
        band[_snaphic_holes(n, W, step) & np.isfinite(band)] = 0.0
    return band


def rwr_band(i, j, n: int, *, rp: float = 0.05, window: int = 0, step: int = 0, max_diag: int = 205,
             min_sep: int = 2, chain: bool = True, backend: Optional[str] = None,
             n_threads: int = 0, holes: bool = False) -> np.ndarray:
    """The RWR-imputed map of one cell's chromosome, as a band (SnapHiC; Yu et al. 2021).

    Parameters
    ----------
    i, j : array of int
        The cell's contacts (bins of the chromosome; duplicates and order do not matter: the graph is binary).
    n : int
        Bins of the chromosome.
    rp : float
        Restart probability.
    window, step : int
        Sliding windows, in bins (``window=0``: the whole chromosome, one graph).
    max_diag : int
        Offsets ``0 ..= max_diag`` are returned (``window - step >= max_diag`` is required).
    min_sep, chain
        Contacts closer than ``min_sep`` bins are left out; ``chain`` links neighbouring bins.
    backend : {"auto", "native", "numpy"}, optional
        Default: the module's :data:`BACKEND`.
    n_threads : int
        Threads of the native path (0: all).
    holes : bool
        Leave at 0 the pixels SnapHiC v0.2's sliding windows never set (sums ``i + j = (2k + 1) step`` and
        ``i + j <= step``): only to compare with the authors' code.

    Returns
    -------
    ndarray (n, max_diag + 1)
        ``out[i, d] = R(i, i + d)``, ``R = Q + Q^T``; NaN beyond the chromosome.
    """
    mod = _maps_kernels(backend)
    i = np.ascontiguousarray(i, dtype=np.int64)
    j = np.ascontiguousarray(j, dtype=np.int64)
    if mod is not None:
        return mod.rwr_band(int(n), i, j, float(rp), int(window), int(step), int(max_diag), int(min_sep),
                            bool(chain), int(n_threads), bool(holes))
    return _rwr_band_numpy(int(n), i, j, rp=float(rp), window=int(window), step=int(step),
                           max_diag=int(max_diag), min_sep=int(min_sep), chain=bool(chain), holes=bool(holes))


def _zscore_numpy(band: np.ndarray, edge: int, trim: float, min_sd: float) -> np.ndarray:
    n, W = band.shape
    out = np.zeros_like(band)
    out[:, 0] = np.nan
    rows = np.arange(n)[:, None]
    out[(rows + np.arange(W)[None, :]) >= n] = np.nan
    for d in range(1, W):
        i0, i1 = edge, n - 1 - edge - d
        if i1 < i0:
            continue
        v = band[i0:i1 + 1, d]
        t = round(trim * len(v)) - 1                       # SnapHiC: Python's round (half to even)
        srt = np.sort(v)[::-1]
        rest = srt[t:] if t >= 0 else srt[-1:]
        mu, sd = np.mean(rest), np.std(rest)
        out[i0:i1 + 1, d] = 0.0 if sd < min_sd else (v - mu) / sd
    return out


def zscore_band(band: np.ndarray, *, edge: int = 5, trim: float = 0.01, min_sd: float = 1e-6,
                backend: Optional[str] = None, n_threads: int = 0) -> np.ndarray:
    """SnapHiC's normalisation of an RWR band: z-scores per diagonal (Yu et al. 2021).

    On every diagonal ``d >= 1`` the pixels of the rows ``edge <= i``, ``i + d <= n - 1 - edge`` are converted
    to ``(x - mean) / sd``, the mean and the (population) standard deviation taken without the largest
    ``round(trim * len) - 1`` values; a diagonal with ``sd < min_sd`` is 0.  Pixels of those diagonals
    outside the trimmed rows are 0 (SnapHiC drops them: zeros in its matrices); the main diagonal and
    pixels beyond the chromosome are NaN.

    Returns a new array of the band's shape.
    """
    band = np.ascontiguousarray(band, dtype=np.float64)
    mod = _maps_kernels(backend)
    if mod is not None:
        return mod.zscore_band(band, int(edge), float(trim), float(min_sd), int(n_threads))
    return _zscore_numpy(band, int(edge), float(trim), float(min_sd))


# ----------------------------------------------------------------------------------------------------------
# dense batch imputation in scHiCluster's style (uchrom.emb.hic follows the authors' code exactly)
# ----------------------------------------------------------------------------------------------------------

def convolve_maps(mats: np.ndarray, pad: int = 1) -> np.ndarray:
    """The ``(2 pad + 1)^2`` mean filter of scHiCluster (zeros outside the map) over a batch ``(k, n, n)``."""
    a = np.asarray(mats, dtype=np.float64)
    if pad <= 0:
        return a
    n = a.shape[-1]
    p = np.pad(a, ((0, 0), (pad, pad), (pad, pad)))
    c = np.zeros_like(a)
    for di in range(2 * pad + 1):
        for dj in range(2 * pad + 1):
            c += p[:, di:di + n, dj:dj + n]
    return c / (2 * pad + 1) ** 2


def rwr_dense(mats: np.ndarray, *, rp: float = 0.5, tol: float = 1e-6, max_iter: int = 100,
              self_loops: bool = True, method: str = "iterative") -> np.ndarray:
    """Random walk with restart on a batch of dense symmetric maps ``(k, n, n)`` (in scHiCluster's style; the
    authors' exact ``random_walk_cpu`` is ``uchrom.emb.hic.schicluster_impute``).

    ``P`` is the row-normalised map (with ``self_loops``: plus the identity, which keeps the rows of empty
    bins stochastic).  ``method="iterative"``: ``Q <- (1 - rp) Q P + rp I`` from ``Q = I`` until the largest
    change is below ``tol`` (at most ``max_iter`` steps); ``"exact"``: ``Q = rp (I - (1 - rp) P)^-1``.
    Returns ``(Q + Q^T) / 2``.
    """
    a = np.asarray(mats, dtype=np.float64)
    n = a.shape[-1]
    if self_loops:
        a = a + np.eye(n)[None]
    P = a / a.sum(axis=2, keepdims=True)
    eye = np.broadcast_to(np.eye(n), a.shape)
    if method == "exact":
        Q = rp * np.linalg.solve(np.eye(n)[None] - (1 - rp) * P, eye)
    elif method == "iterative":
        Q = eye.copy()
        for _ in range(max_iter):
            Q_new = (1 - rp) * (Q @ P) + rp * eye
            delta = np.abs(Q_new - Q).max()
            Q = Q_new
            if delta < tol:
                break
    else:
        raise ValueError(f"method={method!r}: 'iterative' or 'exact'")
    return (Q + np.swapaxes(Q, 1, 2)) / 2


# ----------------------------------------------------------------------------------------------------------
# per-cell maps of a ChromData
# ----------------------------------------------------------------------------------------------------------

class _ScoolCells:
    """Per-cell maps of a ``.scool``: cis pixels of one chromosome per cell, read through the indexes."""

    def __init__(self, path: str):
        import h5py

        self.path = str(path)
        self.f = h5py.File(self.path, "r")
        self.names = [str(c) for c in self.f["cells"]]
        self.chroms = [c.decode() if isinstance(c, bytes) else str(c) for c in self.f["chroms/name"][:]]
        self.lengths = np.asarray(self.f["chroms/length"][:], np.int64)
        start = self.f["bins/start"]
        end = self.f["bins/end"]
        self.binsize = int(self.f.attrs.get("bin-size") or (int(end[0]) - int(start[0])))
        chrom = np.asarray(self.f["bins/chrom"][:], np.int64)
        self.first = np.searchsorted(chrom, np.arange(len(self.chroms)), side="left")
        self.n_bins = np.diff(np.r_[self.first, len(chrom)])
        self.assembly = self.f.attrs.get("genome-assembly")

    def close(self):
        self.f.close()

    def n(self, chrom: str) -> int:
        return int(self.n_bins[self.chroms.index(chrom)])

    def cis(self, cell: str, chrom: str) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """``(i, j, count)``: the cell's pixels of ``chrom`` (bins of the chromosome, ``i <= j``)."""
        g = self.f["cells"][cell]
        k = self.chroms.index(chrom)
        lo, hi = int(self.first[k]), int(self.first[k] + self.n_bins[k])
        off = g["indexes/bin1_offset"]
        a, b = int(off[lo]), int(off[hi])
        if b <= a:
            z = np.zeros(0, np.int64)
            return z, z, z
        px = g["pixels"]
        b1 = np.asarray(px["bin1_id"][a:b], np.int64)
        b2 = np.asarray(px["bin2_id"][a:b], np.int64)
        c = np.asarray(px["count"][a:b], np.int64)
        sel = b2 < hi
        return b1[sel] - lo, b2[sel] - lo, c[sel]


def _cells_and_source(cd, contacts: str, cells) -> Tuple[List[str], str]:
    """(cell ids, path of a ``.scool`` holding them: the linked file, or the cells exported from the
    store's embedded copy, cis only)."""
    all_ids = [str(c) for c in cd.cells.index] if len(getattr(cd, "cells", ())) else None
    ids = [str(c) for c in cells] if cells is not None else all_ids
    if hasattr(cd, "linked_scool_path"):
        record = (cd.uns.get("linked_scool") or {}).get(contacts) or {}
        if record or contacts in (cd.embedded_links().get("contacts", {}) if hasattr(cd, "embedded_links") else {}):
            path = cd.linked_scool_path(contacts, cells=ids, trans=False)
            if ids is None:
                ids = list(_ScoolCells(path).names)
            return ids, path
    from pathlib import Path

    p = Path(str(contacts)).expanduser()
    if p.exists():
        src = _ScoolCells(str(p))
        names = list(src.names)
        src.close()
        return (ids if ids is not None else names), str(p)
    raise KeyError(f"contacts={contacts!r}: neither per-cell maps linked to cd (cd.link_scool) nor a .scool")


def read_cell_pixels(scool: str, cells: Sequence[str], chrom: str) -> Tuple[int, List[Tuple[np.ndarray, np.ndarray]]]:
    """``(n_bins, [(i, j), ...])``: every cell's cis contacts of ``chrom`` in a ``.scool`` (cells missing from
    the file: no contacts)."""
    src = _ScoolCells(scool)
    try:
        n = src.n(chrom)
        have = set(src.names)
        out = []
        for c in cells:
            if c in have:
                i, j, _ = src.cis(c, chrom)
            else:
                i = j = np.zeros(0, np.int64)
            out.append((i, j))
        return n, out
    finally:
        src.close()


def _autosomes(names: Sequence[str]) -> List[str]:
    import re

    return [c for c in names if re.fullmatch(r"(chr)?\d+", str(c))]


def _resolve_window(params: ImputeParams, scool: str, cells: Sequence[str], binsize: int,
                    chroms: Sequence[str]) -> Optional[int]:
    """The window in bp (None: whole chromosomes); ``"auto"`` pools the cells' contacts on ``chroms``."""
    if params.window is None:
        return None
    if params.window != "auto":
        return int(params.window)
    dists = []
    src = _ScoolCells(scool)
    try:
        have = set(src.names)
        for chrom in chroms:
            for c in cells:
                if c not in have:
                    continue
                i, j, _ = src.cis(c, chrom)
                n = src.n(chrom)
                key = np.unique((i * n + j)[(j - i) >= params.min_sep])      # binary, as SnapHiC bins them
                dists.append(key % n - key // n)
    finally:
        src.close()
    return auto_window(dists, binsize=binsize)


def impute_maps(cd, *, contacts: str = "per_cell", cells: Optional[Sequence] = None,
                chrom: Union[None, str, Sequence[str]] = None, params: Optional[ImputeParams] = None,
                backend: Optional[str] = None, n_threads: int = 0) -> Iterator[Tuple[str, str, np.ndarray]]:
    """Impute the per-cell contact maps of ``cd`` by random walk with restart (SnapHiC; Yu et al. 2021 — or
    scHiCluster's RWR with ``rp=0.5``, Zhou et al. 2019): yields ``(cell, chrom, band)`` per cell and
    chromosome, chromosome by chromosome.

    Parameters
    ----------
    cd : ChromData
        With per-cell maps linked (``cd.link_scool``; or embedded in its atlas store: the cells are exported
        once, cis only).
    contacts : str
        Key of the linked per-cell maps, or the path of a ``.scool`` named by cell id.
    cells : sequence, optional
        Cell ids (default: every cell of ``cd.cells``).
    chrom : str or sequence, optional
        Chromosomes (default: the autosomes of the maps).
    params : ImputeParams, optional
        RWR and normalisation settings (default: SnapHiC's, whole chromosomes).  ``window="auto"`` is chosen
        from the contacts of ``cells`` on the autosomes of the maps.
    backend, n_threads
        See :func:`rwr_band`.

    Yields
    ------
    (cell, chrom, band)
        ``band``: ``(n_bins, max_diag + 1)`` float64, ``band[i, d]`` = imputed contact of bins ``i`` and
        ``i + d`` (z-scores with ``params.normalize``; NaN beyond the chromosome, on the diagonal when
        normalised).
    """
    params = params or ImputeParams()
    ids, scool = _cells_and_source(cd, contacts, cells)
    src = _ScoolCells(scool)
    names, binsize = list(src.chroms), src.binsize
    src.close()
    chroms = _autosomes(names) if chrom is None else ([chrom] if isinstance(chrom, str) else [str(c) for c in chrom])
    missing = [c for c in chroms if c not in names]
    if missing:
        raise ValueError(f"not in the maps: {missing}")
    window_bp = _resolve_window(params, scool, ids, binsize, _autosomes(names) or chroms)
    w, step = _window_bins(params, binsize, window_bp)
    max_diag = int(np.ceil(params.max_dist / binsize))
    for c in chroms:
        n, pix = read_cell_pixels(scool, ids, c)
        for cell, (i, j) in zip(ids, pix):
            band = rwr_band(i, j, n, rp=params.rp, window=w, step=step, max_diag=max_diag,
                            min_sep=params.min_sep, chain=params.chain, backend=backend, n_threads=n_threads)
            if params.normalize:
                band = zscore_band(band, edge=params.edge, trim=params.trim, min_sd=params.min_sd,
                                   backend=backend, n_threads=n_threads)
            yield cell, c, band
