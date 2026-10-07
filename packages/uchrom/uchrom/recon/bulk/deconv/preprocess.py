"""Bulk Hi-C -> haploid contact-probability matrix (IGM protocol, method-independent).

Implements the preprocessing of Boninsegna et al. 2022 (Nat Methods 19:938; Supplementary
Information section 6, "HFFc6 experimental data pre-processing"), as specified in
``benchmarks/bulk/pgs_spec.md`` section 1.2.  The same input serves every population
deconvolution method (``uchrom.recon.bulk.deconv.deconvolve(method="igm")``).

Protocol (defaults = the paper's values; resolutions are parameters):

1. **Coverage filter** at the fine resolution (20 kb): bins with coverage < 3 % are discarded
   (see :func:`coverage_mask` for what "coverage" means here - the SI wording "sequence
   coverage" is ambiguous; a per-bin sequence-coverage array can be given instead).
2. **Knight-Ruiz balancing** at the fine resolution -> frequency matrix ``G``
   (:func:`kr_balance`, a re-implementation of Knight & Ruiz 2013's ``bnewt`` on the
   symmetric sparse matrix, diagonal included, masked bins removed; ``balance="ice"`` /
   ``"weights"`` / ``"none"`` are alternatives, ``"weights"`` e.g. for Juicer KR vectors).
3. ``p_ij = min(g_ij / f_max, 1)``.
4. **Coarse matrix** (200 kb): ``a_IJ`` = mean of the top 10 % of the fine probabilities of
   the block ``b(I) x b(J)`` after excluding outliers above the box-plot fence
   ``Q3 + 1.5 IQR`` (:func:`topmean_summary`; the block statistics follow alabtools
   ``cmtools.cpp:TopmeanSummaryMatrix``: zeros count, the fine diagonal counts as zero,
   ``top = n // 10`` values not above the fence divided by ``n // 10``; when the fence is 0
   the block mean is used).  Values equal to the fence are kept, as the SI states ("excluding
   outliers p > Q3 + 1.5 IQR"); alabtools keeps only values strictly below it, which zeroes a
   block whose probabilities are all clipped to 1 - ``fence_inclusive=False`` reproduces that.
5. ``f_max`` and the coarse mapping are determined **jointly**: ``f_max`` is found by a
   bracketed bisection (in log space) such that the mean non-zero row sum of the coarse
   matrix, after zeroing entries below ``theta = 0.001``, is ``target_contacts = 24``
   within ``tol = 1 %`` (alabtools ``Contactmatrix.iterativeScaling`` semantics; the
   bracketing is more robust than alabtools' fixed ``[0, 2 f_0]`` interval).
6. **Spurious inter-chromosomal probabilities**: coarse inter-chromosomal entries
   ``> inter_max = 0.2`` are traced back to the fine inter-chromosomal entries ``> 0.2``
   of their block; those fine bins are removed and steps 2-5 are repeated until no coarse
   inter-chromosomal probability exceeds 0.2 (at most ``max_rounds``).
7. Nearest neighbours (consecutive coarse bins of one chromosome) are set to probability 1;
   the coarse diagonal to 1 (as in IGM's demo ``.hcs``).

Output: a :class:`ProbabilityMatrix` with a **symmetric** ``scipy.sparse.csr_matrix`` of
haploid contact probabilities (both triangles and the diagonal stored), the coarse
``bins`` DataFrame (chrom, start, end + bookkeeping columns) and a JSON-serialisable
``provenance`` dict.  ``upper_coo()`` gives the upper-triangular (i, j, p) arrays the
engine consumes.

Input: a sparse raw count matrix + fine ``bins`` (:func:`preprocess_igm`), or a file
(:func:`preprocess_hic`: ``.cool``, ``.mcool[::/resolutions/N]``, ``.hic`` through
``hicstraw`` when installed).  When the file has no level at the fine resolution, the
finest level dividing it is read and summed (e.g. 10 kb -> 20 kb).
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from typing import Optional, Sequence

import numpy as np
import pandas as pd
import scipy.sparse as sp

__all__ = [
    "IGMPreprocessParams",
    "ProbabilityMatrix",
    "canonical_upper",
    "coverage_mask",
    "kr_balance",
    "ice_balance",
    "coarse_index",
    "topmean_summary",
    "fit_fmax",
    "preprocess_igm",
    "preprocess_hic",
    "load_contacts",
    "aggregate_bins",
]


# --------------------------------------------------------------------------- parameters

@dataclass
class IGMPreprocessParams:
    """Parameters of the IGM SI section 6 protocol (defaults = the paper)."""

    fine_resolution: int = 20_000
    coarse_resolution: int = 200_000
    #: step 1: bins below this coverage are discarded
    min_coverage: float = 0.03
    #: "relative_rowsum" (raw contacts of the bin / median over non-empty bins) or
    #: "nonzero_fraction" (fraction of non-zero pixels of the row / median); ignored when
    #: ``sequence_coverage`` is passed to :func:`preprocess_igm`
    coverage: str = "relative_rowsum"
    #: step 2: "kr" | "ice" | "weights" (given multiplicative weights) | "none"
    balance: str = "kr"
    kr_tol: float = 1e-6
    kr_max_iter: int = 500
    #: step 4
    top_fraction: float = 0.1
    iqr_factor: float = 1.5
    #: keep values equal to the fence (SI wording); False = alabtools' strict "<"
    fence_inclusive: bool = True
    #: masked fine bins count as zeros in a block (alabtools) or are left out (PGS NaN rule)
    masked_as_zero: bool = True
    #: step 5
    target_contacts: float = 24.0
    tol: float = 0.01
    theta: float = 0.001
    max_bisection: int = 80
    #: step 6
    inter_max: float = 0.2
    max_rounds: int = 5
    #: step 7
    neighbour_probability: float = 1.0
    diagonal_probability: float = 1.0

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ProbabilityMatrix:
    """Result of the preprocessing.

    ``probabilities``: symmetric CSR (n_coarse x n_coarse) haploid contact probabilities in
    [0, 1]; ``bins``: chrom, start, end, ``n_fine`` (fine bins in the coarse bin),
    ``n_fine_valid`` (after the filters), ``masked`` (no valid fine bin), ``rowsum``;
    ``fine_mask``: bool per fine bin (True = discarded); ``provenance``: parameters and
    per-round diagnostics.
    """

    probabilities: sp.csr_matrix
    bins: pd.DataFrame
    provenance: dict = field(default_factory=dict)
    fine_bins: Optional[pd.DataFrame] = None
    fine_mask: Optional[np.ndarray] = None

    def upper_coo(self, k: int = 0):
        """(i, j, p) of the upper triangle (``k=1`` leaves the diagonal out)."""
        u = sp.triu(self.probabilities, k=k).tocoo()
        return u.row.astype(np.int64), u.col.astype(np.int64), u.data.astype(np.float64)

    def save(self, path) -> None:
        """``.npz`` with ``i, j, p`` (upper triangle incl. diagonal), the bins columns and the
        provenance as JSON."""
        i, j, p = self.upper_coo()
        cols = {}
        for c in self.bins.columns:
            v = self.bins[c].to_numpy()
            cols[f"bins_{c}"] = v.astype(str) if v.dtype == object or str(self.bins[c].dtype) == "category" else v
        np.savez_compressed(path, i=i, j=j, p=p, n=len(self.bins), **cols,
                            provenance=json.dumps(self.provenance, default=_json_default))

    @classmethod
    def load(cls, path) -> "ProbabilityMatrix":
        z = np.load(path, allow_pickle=False)
        n = int(z["n"])
        bins = pd.DataFrame({k[5:]: z[k] for k in z.files if k.startswith("bins_")})
        bins["chrom"] = bins["chrom"].astype(str)
        m = sp.coo_matrix((z["p"], (z["i"], z["j"])), shape=(n, n)).tocsr()
        return cls(probabilities=symmetrize_upper(m), bins=bins,
                   provenance=json.loads(str(z["provenance"])))


def _json_default(o):
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        return float(o)
    if isinstance(o, np.ndarray):
        return o.tolist()
    return str(o)


# --------------------------------------------------------------------------- sparse helpers

def canonical_upper(m) -> sp.csr_matrix:
    """Upper triangle (incl. diagonal) of a square sparse / dense matrix given as upper,
    lower or full symmetric storage (full storage: the upper triangle is used)."""
    m = sp.csr_matrix(m, dtype=np.float64)
    if m.shape[0] != m.shape[1]:
        raise ValueError(f"matrix must be square, got {m.shape}")
    lower = sp.tril(m, k=-1)
    upper = sp.triu(m, k=1)
    if lower.nnz and not upper.nnz:
        m = m.T.tocsr()
    u = sp.triu(m, k=0).tocsr()
    u.eliminate_zeros()
    u.sum_duplicates()
    return u


def symmetrize_upper(u) -> sp.csr_matrix:
    """Full symmetric matrix from its upper triangle (diagonal counted once)."""
    u = sp.csr_matrix(u)
    s = (u + sp.triu(u, k=1).T).tocsr()
    s.sum_duplicates()
    return s


def _fine_coverage(u: sp.csr_matrix, kind: str) -> np.ndarray:
    full = symmetrize_upper(u)
    full = full - sp.diags(full.diagonal())
    if kind == "relative_rowsum":
        return np.asarray(full.sum(1)).ravel()
    if kind == "nonzero_fraction":
        f = full.copy()
        f.data = (f.data > 0).astype(float)
        return np.asarray(f.sum(1)).ravel()
    raise ValueError(f"unknown coverage kind {kind!r}")


def coverage_mask(u: sp.csr_matrix, min_coverage: float = 0.03, kind: str = "relative_rowsum",
                  sequence_coverage: Optional[np.ndarray] = None) -> np.ndarray:
    """Step 1: True for fine bins to discard.

    The SI says "bins with sequence coverage lower than 3 % were discarded".  With
    ``sequence_coverage`` (fraction of the bin covered by mappable / non-N sequence, one value
    per bin) that rule is applied literally.  Without it, coverage is measured from the matrix:
    ``relative_rowsum`` = off-diagonal raw contacts of the bin divided by the median over
    non-empty bins (so unmappable, centromeric and gap bins, which have ~0 contacts, go);
    ``nonzero_fraction`` = the same with the number of non-zero pixels.  Empty rows are always
    masked.
    """
    if sequence_coverage is not None:
        cov = np.asarray(sequence_coverage, float)
        return ~(cov >= min_coverage)
    c = _fine_coverage(u, kind)
    pos = c[c > 0]
    if not len(pos):
        return np.ones(len(c), bool)
    return (c <= 0) | (c / np.median(pos) < min_coverage)


# --------------------------------------------------------------------------- balancing

def kr_balance(u, mask: Optional[np.ndarray] = None, tol: float = 1e-6, max_iter: int = 500,
               delta: float = 0.1, Delta: float = 3.0) -> tuple[np.ndarray, dict]:
    """Knight-Ruiz matrix balancing (Knight & Ruiz 2013, IMA J Numer Anal 33:1029, algorithm
    ``bnewt``: Newton outer iteration, conjugate-gradient inner iteration with a step length
    keeping the scaling in ``[delta, Delta]``).

    ``u``: upper triangle (or full symmetric) sparse matrix; ``mask``: True = excluded bin
    (also bins whose row is empty after masking).  Returns ``(w, info)`` with ``w`` the
    multiplicative weights (NaN for excluded bins) such that ``diag(w) A diag(w)`` has unit
    row sums over the kept bins.  The diagonal of the matrix is included.
    """
    u = canonical_upper(u)
    n = u.shape[0]
    A = symmetrize_upper(u)
    mask = np.zeros(n, bool) if mask is None else np.asarray(mask, bool).copy()
    for _ in range(n):                      # drop bins whose kept row becomes empty
        keep = np.flatnonzero(~mask)
        rs = np.asarray(A[keep][:, keep].sum(1)).ravel()
        if (rs > 0).all():
            break
        mask[keep[rs <= 0]] = True
    keep = np.flatnonzero(~mask)
    B = A[keep][:, keep].tocsr()
    m = len(keep)
    w = np.full(n, np.nan)
    info = {"method": "kr", "n_kept": int(m), "converged": False, "outer": 0, "matvec": 0}
    if m == 0:
        return w, info
    # scale the matrix to mean row sum 1 first (conditioning only; weights rescaled back)
    s0 = float(B.sum()) / m
    B = B / s0
    e = np.ones(m)
    x = e.copy()
    g, etamax = 0.9, 0.1
    eta = etamax
    stop_tol = tol * 0.5
    rt = tol ** 2
    v = x * (B @ x)
    rk = 1.0 - v
    rho_km1 = float(rk @ rk)
    rout = rho_km1
    rold = rout
    mvp = 0
    outer = 0
    while rout > rt and outer < max_iter:
        outer += 1
        k = 0
        y = e.copy()
        innertol = max(eta ** 2 * rout, rt)
        rho_km2 = rho_km1
        Z = p = None
        while rho_km1 > innertol:
            k += 1
            if k == 1:
                Z = rk / v
                p = Z.copy()
                rho_km1 = float(rk @ Z)
            else:
                beta = rho_km1 / rho_km2
                p = Z + beta * p
            wv = x * (B @ (x * p)) + v * p
            alpha = rho_km1 / float(p @ wv)
            ap = alpha * p
            ynew = y + ap
            if ynew.min() <= delta:
                if delta == 0:
                    break
                ind = ap < 0
                gamma = np.min((delta - y[ind]) / ap[ind])
                y = y + gamma * ap
                break
            if ynew.max() >= Delta:
                ind = ynew > Delta
                gamma = np.min((Delta - y[ind]) / ap[ind])
                y = y + gamma * ap
                break
            y = ynew
            rk = rk - alpha * wv
            rho_km2 = rho_km1
            Z = rk / v
            rho_km1 = float(rk @ Z)
            if k > 10 * m:
                break
        x = x * y
        v = x * (B @ x)
        rk = 1.0 - v
        rho_km1 = float(rk @ rk)
        rout = rho_km1
        mvp += k + 1
        rat = rout / rold
        rold = rout
        res_norm = np.sqrt(rout)
        eta_o = eta
        eta = g * rat
        if g * eta_o ** 2 > 0.1:
            eta = max(eta, g * eta_o ** 2)
        eta = max(min(eta, etamax), stop_tol / max(res_norm, 1e-300))
    rows = x * (B @ x)
    info.update({"converged": bool(rout <= rt), "outer": outer, "matvec": int(mvp),
                 "max_row_dev": float(np.max(np.abs(rows - 1.0))), "residual": float(np.sqrt(rout))})
    w[keep] = x / np.sqrt(s0)
    return w, info


def ice_balance(u, mask: Optional[np.ndarray] = None, tol: float = 1e-5, max_iter: int = 1000):
    """Iterative correction (Imakaev et al. 2012) to equal row sums; weights normalised so that
    the balanced matrix has unit mean row sum (for comparison with :func:`kr_balance`)."""
    u = canonical_upper(u)
    A = symmetrize_upper(u)
    n = A.shape[0]
    mask = np.zeros(n, bool) if mask is None else np.asarray(mask, bool).copy()
    rs = np.asarray(A.sum(1)).ravel()
    mask |= rs <= 0
    keep = np.flatnonzero(~mask)
    B = A[keep][:, keep].tocsr()
    b = np.ones(len(keep))
    it = 0
    var = np.inf
    for it in range(1, max_iter + 1):
        r = b * (B @ b)
        r = r / r[r > 0].mean()
        r[r == 0] = 1
        b = b / np.sqrt(r)
        var = float(np.var(r))
        if var < tol:
            break
    rows = b * (B @ b)
    b = b / np.sqrt(rows.mean())
    w = np.full(n, np.nan)
    w[keep] = b
    return w, {"method": "ice", "iterations": it, "variance": var, "converged": bool(var < tol),
               "n_kept": int(len(keep))}


# --------------------------------------------------------------------------- coarse mapping

def coarse_index(fine_bins: pd.DataFrame, coarse: int | pd.DataFrame) -> tuple[np.ndarray, pd.DataFrame]:
    """Map fine bins to coarse bins.

    ``coarse``: a resolution in bp (coarse bin = ``start // coarse`` within each chromosome)
    or a DataFrame of coarse bins (chrom, start, end; fine bins are mapped by their midpoint,
    fine bins outside every coarse bin get -1).  Returns ``(fine -> coarse index, coarse bins)``.
    """
    chrom = fine_bins["chrom"].astype(str).to_numpy()
    start = fine_bins["start"].to_numpy(np.int64)
    end = fine_bins["end"].to_numpy(np.int64)
    if isinstance(coarse, (int, np.integer)):
        res = int(coarse)
        key = pd.MultiIndex.from_arrays([chrom, start // res])
        codes, uniq = pd.factorize(key, sort=False)
        cb = pd.DataFrame({"chrom": [c for c, _ in uniq], "start": [b * res for _, b in uniq]})
        ends = pd.Series(end).groupby(codes).max().to_numpy()
        cb["end"] = np.minimum(cb["start"].to_numpy() + res, ends)
        return codes.astype(np.int64), cb
    cb = coarse[["chrom", "start", "end"]].copy().reset_index(drop=True)
    cb["chrom"] = cb["chrom"].astype(str)
    out = np.full(len(chrom), -1, np.int64)
    mid = (start + end) // 2
    for c, sub in cb.groupby("chrom", sort=False):
        f = np.flatnonzero(chrom == c)
        if not len(f):
            continue
        s = sub.sort_values("start")
        k = np.searchsorted(s["start"].to_numpy(), mid[f], side="right") - 1
        ok = (k >= 0) & (mid[f] < s["end"].to_numpy()[np.clip(k, 0, None)])
        out[f[ok]] = s.index.to_numpy()[k[ok]]
    return out, cb


class _BlockEntries:
    """Fine upper-triangle entries grouped by coarse block and sorted by value (once).

    Scaling by ``1 / f_max`` and clipping at 1 keep the order inside a block, so every
    ``f_max`` evaluation of the top-mean summary is O(nnz) without re-sorting.
    """

    def __init__(self, g_upper: sp.csr_matrix, f2c: np.ndarray, n_coarse: int, n_per_coarse: np.ndarray):
        coo = g_upper.tocoo()
        i, j, v = coo.row.astype(np.int64), coo.col.astype(np.int64), coo.data.astype(np.float64)
        off = i != j                                    # fine diagonal = 0 (alabtools: stored apart)
        i, j, v = i[off], j[off], v[off]
        I, J = f2c[i], f2c[j]
        ok = (I >= 0) & (J >= 0) & (v > 0)
        i, j, v, I, J = i[ok], j[ok], v[ok], I[ok], J[ok]
        lo, hi = np.minimum(I, J), np.maximum(I, J)
        diag = lo == hi                                 # diagonal blocks: both triangles
        I2 = np.concatenate([lo, lo[diag]])
        J2 = np.concatenate([hi, hi[diag]])
        v2 = np.concatenate([v, v[diag]])
        fi = np.concatenate([i, j[diag]])
        fj = np.concatenate([j, i[diag]])
        key = I2 * n_coarse + J2
        order = np.lexsort((v2, key))
        self.key = key[order]
        self.g = v2[order]
        self.fi, self.fj = fi[order], fj[order]
        self.ukey, self.start, self.k = np.unique(self.key, return_index=True, return_counts=True)
        self.bI = self.ukey // n_coarse
        self.bJ = self.ukey % n_coarse
        self.n = n_per_coarse[self.bI].astype(np.int64) * n_per_coarse[self.bJ].astype(np.int64)
        self.block_of = np.repeat(np.arange(len(self.ukey)), self.k)
        self.rank = np.arange(len(self.key)) - self.start[self.block_of]
        self.n_coarse = n_coarse


def _q_at(vals: np.ndarray, blocks: _BlockEntries, m: np.ndarray) -> np.ndarray:
    """Value at sorted position m of each block (zeros first, then the non-zeros)."""
    z = blocks.n - blocks.k
    pos = m - z
    out = np.zeros(len(m))
    ok = pos >= 0
    out[ok] = vals[blocks.start[ok] + pos[ok]]
    return out


def topmean_summary(blocks: _BlockEntries, fmax: float, top_fraction: float = 0.1,
                    iqr_factor: float = 1.5, fence_inclusive: bool = True) -> np.ndarray:
    """Top-mean block summary of ``p = min(g / fmax, 1)`` for every block with entries.

    Per block of ``n`` fine pairs (zeros included): sorted values, ``Q1 = x[int(0.25 n + 0.5)]``,
    ``Q3 = x[int(0.75 n + 0.5)]``, fence ``Q3 + iqr_factor (Q3 - Q1)``; ``t = int(n * top_fraction)``
    (``n`` if 0); summary = (sum of the ``t`` largest values not above the fence - strictly
    below it with ``fence_inclusive=False``) / ``t``; a zero fence means the block mean
    (alabtools ``TopmeanSummaryMatrix``).  Returns one value per ``blocks.ukey``.
    """
    p = np.minimum(blocks.g / fmax, 1.0)
    n = blocks.n
    q1 = _q_at(p, blocks, np.minimum((n * 0.25 + 0.5).astype(np.int64), n - 1))
    q3 = _q_at(p, blocks, np.minimum((n * 0.75 + 0.5).astype(np.int64), n - 1))
    fence = q3 + iqr_factor * (q3 - q1)
    top = np.floor(n * top_fraction + 1e-9).astype(np.int64)
    top[top == 0] = n[top == 0]
    fb = fence[blocks.block_of]
    below = (p <= fb) if fence_inclusive else (p < fb)
    c = np.bincount(blocks.block_of, weights=below, minlength=len(n)).astype(np.int64)
    t = np.minimum(top, c)
    b = blocks.block_of
    sel = below & (blocks.rank >= (c - t)[b]) & (blocks.rank < c[b])
    s = np.bincount(b, weights=np.where(sel, p, 0.0), minlength=len(n))
    out = s / top
    zero_fence = fence <= 0
    if zero_fence.any():
        tot = np.bincount(b, weights=p, minlength=len(n))
        out[zero_fence] = tot[zero_fence] / n[zero_fence]
    return out


def _coarse_matrix(blocks: _BlockEntries, vals: np.ndarray) -> sp.csr_matrix:
    n = blocks.n_coarse
    u = sp.coo_matrix((vals, (blocks.bI, blocks.bJ)), shape=(n, n)).tocsr()
    u.eliminate_zeros()
    return u


def _average_contacts(blocks: _BlockEntries, vals: np.ndarray, theta: float) -> float:
    v = np.where(vals < theta, 0.0, vals)
    n = blocks.n_coarse
    rs = np.bincount(blocks.bI, weights=v, minlength=n)
    off = blocks.bI != blocks.bJ
    rs += np.bincount(blocks.bJ[off], weights=v[off], minlength=n)
    rs = rs[rs > 0]
    return float(rs.mean()) if len(rs) else 0.0


def fit_fmax(blocks: _BlockEntries, target: float = 24.0, tol: float = 0.01, theta: float = 0.001,
             top_fraction: float = 0.1, iqr_factor: float = 1.5, fmax0: Optional[float] = None,
             max_iter: int = 80, fence_inclusive: bool = True) -> tuple[float, float, list]:
    """Step 5: ``f_max`` such that the mean non-zero row sum of the coarse matrix (entries
    < theta zeroed) is ``target`` within ``tol`` (relative).  The average decreases with
    ``f_max``; bracket by doubling / halving, then bisect in log space.
    Returns ``(fmax, average, trace)``."""
    trace = []

    def avg(f):
        a = _average_contacts(blocks, topmean_summary(blocks, f, top_fraction, iqr_factor, fence_inclusive), theta)
        trace.append((float(f), a))
        return a

    if fmax0 is None:
        fmax0 = float(np.median(blocks.g)) if len(blocks.g) else 1.0
    f = fmax0
    a = avg(f)
    if abs(a - target) / target <= tol:
        return f, a, trace
    lo = hi = None
    for _ in range(60):
        if a > target:
            lo = f                # too many contacts -> larger fmax
            f = f * 2.0
        else:
            hi = f
            f = f / 2.0
        if lo is not None and hi is not None:
            break
        a = avg(f)
        if abs(a - target) / target <= tol:
            return f, a, trace
    if lo is None or hi is None:
        # unreachable (e.g. too sparse a matrix: even p = 1 for every observed pair gives fewer
        # contacts than the target): return the closest value, flagged by the caller
        f, a = min(trace, key=lambda t: abs(t[1] - target))
        return f, a, trace
    for _ in range(max_iter):
        f = float(np.sqrt(lo * hi))
        a = avg(f)
        if abs(a - target) / target <= tol:
            break
        if a > target:
            lo = f
        else:
            hi = f
    return f, a, trace


# --------------------------------------------------------------------------- main entry

def preprocess_igm(counts, bins: pd.DataFrame, *, params: Optional[IGMPreprocessParams] = None,
                   coarse_bins: Optional[pd.DataFrame] = None, sequence_coverage=None,
                   weights: Optional[np.ndarray] = None, verbose: bool = False) -> ProbabilityMatrix:
    """Raw fine-resolution counts -> coarse haploid probability matrix (IGM SI section 6).

    Parameters
    ----------
    counts
        square sparse (or dense) raw contact matrix over ``bins`` (upper, lower or full
        symmetric storage).
    bins
        fine bins: chrom, start, end (genome order).
    params
        :class:`IGMPreprocessParams`; ``params.fine_resolution`` is informational here (the
        matrix is taken as given), ``params.coarse_resolution`` defines the coarse bins unless
        ``coarse_bins`` (DataFrame chrom, start, end) is given.
    sequence_coverage
        optional per-fine-bin sequence coverage fraction for step 1.
    weights
        multiplicative balancing weights (``params.balance="weights"``), e.g. a Juicer KR
        vector converted to cooler's convention; NaN = masked.
    """
    P = params or IGMPreprocessParams()
    t0 = time.time()
    bins = bins.reset_index(drop=True)
    u = canonical_upper(counts)
    n = u.shape[0]
    if len(bins) != n:
        raise ValueError(f"{len(bins)} bins for a {n} x {n} matrix")
    f2c, cb = coarse_index(bins, coarse_bins if coarse_bins is not None else P.coarse_resolution)
    nC = len(cb)
    n_fine = np.bincount(f2c[f2c >= 0], minlength=nC)
    mask0 = coverage_mask(u, P.min_coverage, P.coverage, sequence_coverage)
    mask = mask0.copy()
    removed_inter: list[int] = []
    rounds = []
    fmax = None
    res = None
    for rnd in range(1, P.max_rounds + 1):
        # step 2: balancing
        if P.balance == "kr":
            w, binfo = kr_balance(u, mask, tol=P.kr_tol, max_iter=P.kr_max_iter)
        elif P.balance == "ice":
            w, binfo = ice_balance(u, mask)
        elif P.balance == "weights":
            if weights is None:
                raise ValueError("balance='weights' needs weights=")
            w = np.asarray(weights, float).copy()
            w[mask] = np.nan
            binfo = {"method": "weights", "n_kept": int(np.isfinite(w).sum())}
        elif P.balance == "none":
            w = np.where(mask, np.nan, 1.0)
            binfo = {"method": "none"}
        else:
            raise ValueError(f"unknown balance {P.balance!r}")
        valid = np.isfinite(w) & (w > 0)
        mask = mask | ~valid
        wz = np.where(valid, w, 0.0)
        g = sp.diags(wz) @ u @ sp.diags(wz)
        g = sp.csr_matrix(g)
        g.eliminate_zeros()
        n_valid = np.bincount(f2c[(f2c >= 0) & ~mask], minlength=nC)
        blocks = _BlockEntries(g, f2c, nC, n_fine if P.masked_as_zero else n_valid)
        # steps 3-5: joint fmax / coarse mapping
        fmax, avg, trace = fit_fmax(blocks, P.target_contacts, P.tol, P.theta, P.top_fraction,
                                    P.iqr_factor, fmax0=fmax, max_iter=P.max_bisection,
                                    fence_inclusive=P.fence_inclusive)
        vals = topmean_summary(blocks, fmax, P.top_fraction, P.iqr_factor, P.fence_inclusive)
        # step 6: spurious inter-chromosomal probabilities
        cchrom = cb["chrom"].astype(str).to_numpy()
        inter = cchrom[blocks.bI] != cchrom[blocks.bJ]
        bad = np.flatnonzero(inter & (vals > P.inter_max))
        info = {"round": rnd, "balance": binfo, "fmax": float(fmax), "average_contacts": avg,
                "target_reached": bool(abs(avg - P.target_contacts) / P.target_contacts <= P.tol),
                "n_bisection": len(trace), "n_fine_masked": int(mask.sum()),
                "n_coarse_inter_above": int(len(bad))}
        rounds.append(info)
        if verbose:
            print(json.dumps(info, default=_json_default), flush=True)
        if not len(bad):
            res = (vals, blocks)
            break
        badset = np.zeros(len(blocks.ukey), bool)
        badset[bad] = True
        hit = badset[blocks.block_of] & (np.minimum(blocks.g / fmax, 1.0) > P.inter_max)
        fb = np.unique(np.concatenate([blocks.fi[hit], blocks.fj[hit]]))
        fb = fb[~mask[fb]]
        info["fine_bins_removed"] = int(len(fb))
        if not len(fb):
            res = (vals, blocks)
            break
        removed_inter.extend(fb.tolist())
        mask[fb] = True
        res = (vals, blocks)
    vals, blocks = res
    # step 7
    cu = _coarse_matrix(blocks, vals).tolil()
    cchrom = cb["chrom"].astype(str).to_numpy()
    for I in range(nC):
        cu[I, I] = P.diagonal_probability
        if I + 1 < nC and cchrom[I] == cchrom[I + 1]:
            cu[I, I + 1] = P.neighbour_probability
    cu = sp.csr_matrix(cu)
    cu.data = np.clip(cu.data, 0.0, 1.0)
    cu.eliminate_zeros()
    full = symmetrize_upper(cu)
    n_valid = np.bincount(f2c[(f2c >= 0) & ~mask], minlength=nC)
    cb = cb.assign(n_fine=n_fine, n_fine_valid=n_valid, masked=n_valid == 0,
                   rowsum=np.asarray(full.sum(1)).ravel())
    off = sp.triu(full, k=1).tocoo()
    same = cchrom[off.row] == cchrom[off.col]
    thr = {}
    for s in (1.0, 0.2, 0.1, 0.05, 0.02, 0.01):
        thr[str(s)] = {"intra": int(((off.data >= s) & same).sum()), "inter": int(((off.data >= s) & ~same).sum())}
    prov = {
        "protocol": "IGM SI section 6 (Boninsegna et al. 2022, Nat Methods 19:938)",
        "function": "uchrom.recon.bulk.deconv.preprocess.preprocess_igm",
        "params": P.to_dict(),
        "n_fine": int(n), "n_coarse": int(nC),
        "n_fine_masked_coverage": int(mask0.sum()),
        "n_fine_removed_inter": int(len(set(removed_inter))),
        "n_fine_masked_total": int(mask.sum()),
        "n_coarse_masked": int((n_valid == 0).sum()),
        "fmax": float(fmax), "rounds": rounds,
        "average_contacts_final": float(np.asarray(full.sum(1)).ravel()[n_valid > 0].mean()) if (n_valid > 0).any() else 0.0,
        "max_inter_probability": float(off.data[~same].max()) if (~same).any() else 0.0,
        "pairs_at_or_above": thr,
        "seconds": time.time() - t0,
    }
    return ProbabilityMatrix(probabilities=full, bins=cb, provenance=prov, fine_bins=bins, fine_mask=mask)


# --------------------------------------------------------------------------- file input

def aggregate_bins(u: sp.csr_matrix, bins: pd.DataFrame, factor: int) -> tuple[sp.csr_matrix, pd.DataFrame]:
    """Sum a fixed-bin matrix into bins ``factor`` times larger (within chromosomes)."""
    if factor == 1:
        return canonical_upper(u), bins.reset_index(drop=True)
    res0 = int((bins["end"] - bins["start"]).max())
    f2c, cb = coarse_index(bins, res0 * factor)
    u = canonical_upper(u).tocoo()
    I, J = f2c[u.row], f2c[u.col]
    lo, hi = np.minimum(I, J), np.maximum(I, J)
    m = sp.coo_matrix((u.data, (lo, hi)), shape=(len(cb), len(cb))).tocsr()
    m.sum_duplicates()
    return m, cb


def load_contacts(path, resolution: int, chroms: Optional[Sequence[str]] = None, balance_column: Optional[str] = None):
    """Read a raw contact matrix at ``resolution`` from ``.cool`` / ``.mcool`` / ``.hic``.

    If the file has no level at ``resolution``, the coarsest level that divides it is read
    and summed.  ``chroms``: subset (all by default; ``.hic``: names as in the file, a
    ``chr`` prefix is added to the output names when missing).  Returns
    ``(upper csr counts, bins, weights or None)``; ``weights`` is ``bins[balance_column]`` of a
    cooler (e.g. ``"KR"`` in 4DN mcools, ``"weight"``) summed levels have no weights.
    """
    path = str(path)
    if path.endswith(".hic"):
        return _load_hic(path, resolution, chroms)
    import cooler
    if path.startswith(("http://", "https://", "s3://")):      # HTTP range reads of one level
        import fsspec
        import h5py
        h5 = h5py.File(fsspec.open(path, block_size=2 ** 22, cache_type="blockcache").open(), "r")
        avail = sorted(int(r) for r in h5["resolutions"])
        base = resolution if resolution in avail else max(r for r in avail if resolution % r == 0)
        clr = cooler.Cooler(h5[f"resolutions/{base}"])
    else:
        uri = path
        if "::" not in path and path.endswith(".mcool"):
            avail = sorted(int(r.split("/")[-1]) for r in cooler.fileops.list_coolers(path))
            base = resolution if resolution in avail else max(r for r in avail if resolution % r == 0)
            uri = f"{path}::/resolutions/{base}"
        clr = cooler.Cooler(uri)
    base = clr.binsize
    bins = clr.bins()[:]
    names = [str(c) for c in (chroms or clr.chromnames)]
    sel = bins["chrom"].astype(str).isin(names).to_numpy()
    idx = np.flatnonzero(sel)
    b = bins.iloc[idx][["chrom", "start", "end"]].reset_index(drop=True)
    b["chrom"] = b["chrom"].astype(str)
    w = bins.iloc[idx][balance_column].to_numpy(float) if balance_column and balance_column in bins else None
    remap = np.full(len(bins), -1, np.int64)
    remap[idx] = np.arange(len(idx))
    if resolution != base:                  # aggregate every block right away (memory)
        f2c, b = coarse_index(b, resolution)
        remap[idx] = f2c
        w = None
    n = len(b)
    parts = []
    order = {c: k for k, c in enumerate(clr.chromnames)}
    for a, c1 in enumerate(names):
        for c2 in names[a:]:
            x, y = (c1, c2) if order[c1] <= order[c2] else (c2, c1)
            px = clr.matrix(balance=False, as_pixels=True).fetch(x, y)
            if not len(px):
                continue
            i = remap[px["bin1_id"].to_numpy()]
            j = remap[px["bin2_id"].to_numpy()]
            blk = sp.coo_matrix((px["count"].to_numpy(float), (np.minimum(i, j), np.maximum(i, j))), shape=(n, n)).tocsr()
            blk.sum_duplicates()
            c = blk.tocoo()
            parts.append((c.row, c.col, c.data))
    rows = np.concatenate([p[0] for p in parts]) if parts else np.zeros(0, np.int64)
    cols = np.concatenate([p[1] for p in parts]) if parts else np.zeros(0, np.int64)
    vals = np.concatenate([p[2] for p in parts]) if parts else np.zeros(0)
    m = sp.coo_matrix((vals, (rows, cols)), shape=(n, n)).tocsr()
    return canonical_upper(m), b, w


def _load_hic(path: str, resolution: int, chroms):
    import hicstraw
    hic = hicstraw.HiCFile(path)
    avail = sorted(hic.getResolutions())
    base = resolution if resolution in avail else max(r for r in avail if resolution % r == 0)
    sizes = {c.name: c.length for c in hic.getChromosomes() if c.name.lower() != "all"}
    names = list(chroms) if chroms else list(sizes)
    offs, bl = {}, []
    o = 0
    for c in names:
        nb = int(np.ceil(sizes[c] / base))
        st = np.arange(nb) * base
        bl.append(pd.DataFrame({"chrom": c if c.startswith("chr") else f"chr{c}", "start": st,
                                "end": np.minimum(st + base, sizes[c])}))
        offs[c] = o
        o += nb
    rows, cols, vals = [], [], []
    for a, c1 in enumerate(names):
        for c2 in names[a:]:
            zd = hic.getMatrixZoomData(c1, c2, "observed", "NONE", "BP", base)
            recs = zd.getRecords(0, sizes[c1], 0, sizes[c2])
            if not recs:
                continue
            x = np.fromiter((r.binX for r in recs), np.int64, len(recs)) // base
            y = np.fromiter((r.binY for r in recs), np.int64, len(recs)) // base
            v = np.fromiter((r.counts for r in recs), float, len(recs))
            rows.append(x + offs[c1])
            cols.append(y + offs[c2])
            vals.append(v)
    b = pd.concat(bl, ignore_index=True)
    m = sp.coo_matrix((np.concatenate(vals), (np.concatenate(rows), np.concatenate(cols))), shape=(o, o)).tocsr()
    m = canonical_upper(m)
    if resolution != base:
        m, b = aggregate_bins(m, b, resolution // base)
    return m, b, None


def preprocess_hic(path, *, chroms: Optional[Sequence[str]] = None, params: Optional[IGMPreprocessParams] = None,
                   coarse_bins: Optional[pd.DataFrame] = None, verbose: bool = False) -> ProbabilityMatrix:
    """:func:`load_contacts` at ``params.fine_resolution`` + :func:`preprocess_igm`."""
    P = params or IGMPreprocessParams()
    m, b, w = load_contacts(path, P.fine_resolution, chroms,
                            balance_column="KR" if P.balance == "weights" else None)
    out = preprocess_igm(m, b, params=P, coarse_bins=coarse_bins, weights=w, verbose=verbose)
    out.provenance["input"] = {"path": str(path), "chroms": list(chroms) if chroms else None}
    return out
