"""Contact sources, balancing and expected frequencies for the consensus reconstruction.

Two access patterns keep memory bounded from 1 Mb to 10 kb genome-wide:

* ``genome(res)`` — the whole (selected) genome at one resolution, cis and trans
  (coarse stages only: ≤ a few thousand bins);
* ``cis(res, chrom, max_sep)`` — one chromosome, pixels with ``j - i <= max_sep``
  only (fine stages), read from a cooler in row chunks.

Counts are raw (unbalanced) reads; balancing is done here per stage.
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd
import scipy.sparse as sp

from ..deconv import preprocess as pp


# --------------------------------------------------------------------------- sources

def _resolution_of(bins: pd.DataFrame) -> int:
    w = (bins["end"] - bins["start"]).to_numpy()
    return int(np.max(w)) if len(w) else 0


def _aggregate_index(bins: pd.DataFrame, res: int) -> Tuple[np.ndarray, pd.DataFrame]:
    """Fine → coarse bin index (``start // res`` within each chromosome)."""
    return pp.coarse_index(bins.reset_index(drop=True), int(res))


class MatrixSource:
    """An in-memory raw count matrix (``scipy.sparse`` / dense, any triangle) + its bins."""

    kind = "matrix"

    def __init__(self, counts, bins: pd.DataFrame):
        b = bins[["chrom", "start", "end"]].copy().reset_index(drop=True)
        b["chrom"] = b["chrom"].astype(str)
        b["start"] = pd.to_numeric(b["start"]).astype(np.int64)
        b["end"] = pd.to_numeric(b["end"]).astype(np.int64)
        u = pp.canonical_upper(counts)
        if u.shape[0] != len(b):
            raise ValueError(f"matrix has {u.shape[0]} bins, bins has {len(b)}")
        self.u = u
        self.bins = b
        self.base_res = _resolution_of(b)
        self.chrom_names = list(pd.unique(b["chrom"]))

    def describe(self) -> dict:
        return {"kind": "matrix", "n_bins": int(len(self.bins)), "nnz": int(self.u.nnz), "resolution": self.base_res}

    def _select(self, chroms: Sequence[str]) -> Tuple[sp.csr_matrix, pd.DataFrame]:
        keep = np.flatnonzero(self.bins["chrom"].isin(list(chroms)).to_numpy())
        u = self.u[keep][:, keep].tocsr()
        return u, self.bins.iloc[keep].reset_index(drop=True)

    def genome(self, res: int, chroms: Sequence[str]) -> Tuple[sp.csr_matrix, pd.DataFrame]:
        u, b = self._select(chroms)
        return self._aggregate(u, b, res)

    def _aggregate(self, u, b, res):
        if res == self.base_res:
            return pp.canonical_upper(u), b
        if res % self.base_res:
            raise ValueError(f"stage resolution {res} is not a multiple of the input resolution {self.base_res}")
        f2c, cb = _aggregate_index(b, res)
        c = u.tocoo()
        i, j = f2c[c.row], f2c[c.col]
        m = sp.coo_matrix((c.data, (np.minimum(i, j), np.maximum(i, j))), shape=(len(cb), len(cb))).tocsr()
        m.sum_duplicates()
        return m, cb

    def cis(self, res: int, chrom: str, max_sep: int) -> Tuple[np.ndarray, np.ndarray, np.ndarray, pd.DataFrame]:
        u, b = self.genome(res, [chrom])
        c = sp.triu(u, k=0).tocoo()
        k = (c.col - c.row) <= max_sep
        return c.row[k].astype(np.int64), c.col[k].astype(np.int64), c.data[k].astype(np.float64), b


def _open_cooler(path: str, resolution: int):
    """(cooler.Cooler, base resolution) — the coarsest stored level dividing ``resolution``;
    local ``.cool`` / ``.mcool`` / ``uri::group`` or an http(s) URL (range reads)."""
    import cooler

    if path.startswith(("http://", "https://", "s3://")):
        import fsspec
        import h5py
        h5 = h5py.File(fsspec.open(path, block_size=2 ** 22, cache_type="blockcache").open(), "r")
        if "resolutions" in h5:
            avail = sorted(int(r) for r in h5["resolutions"])
            base = max(r for r in avail if resolution % r == 0)
            return cooler.Cooler(h5[f"resolutions/{base}"]), base
        clr = cooler.Cooler(h5)
        return clr, clr.binsize
    if "::" not in path and path.endswith(".mcool"):
        avail = sorted(int(r.split("/")[-1]) for r in cooler.fileops.list_coolers(path))
        ok = [r for r in avail if resolution % r == 0]
        if not ok:
            raise ValueError(f"{path}: no resolution divides {resolution} (available {avail})")
        base = max(ok)
        return cooler.Cooler(f"{path}::/resolutions/{base}"), base
    clr = cooler.Cooler(path)
    if resolution % clr.binsize:
        raise ValueError(f"{path}: stage resolution {resolution} is not a multiple of {clr.binsize}")
    return clr, clr.binsize


class CoolerSource:
    """A ``.cool`` / ``.mcool`` file or URL (4DN mcools are read by HTTP range requests)."""

    kind = "cooler"

    def __init__(self, path, chunk_bp: int = 20_000_000):
        self.path = str(path)
        self.chunk_bp = int(chunk_bp)
        clr, base = self._probe()
        self.base_res = base
        self.chrom_names = [str(c) for c in clr.chromnames]
        self.chromsizes = {str(k): int(v) for k, v in clr.chromsizes.items()}
        self._cache = {}

    def _probe(self):
        import cooler

        p = self.path
        if p.startswith(("http://", "https://", "s3://")):
            import fsspec
            import h5py
            h5 = h5py.File(fsspec.open(p, block_size=2 ** 22, cache_type="blockcache").open(), "r")
            if "resolutions" in h5:
                base = min(int(r) for r in h5["resolutions"])
                return cooler.Cooler(h5[f"resolutions/{base}"]), base
            c = cooler.Cooler(h5)
            return c, c.binsize
        if "::" not in p and p.endswith(".mcool"):
            base = min(int(r.split("/")[-1]) for r in cooler.fileops.list_coolers(p))
            return cooler.Cooler(f"{p}::/resolutions/{base}"), base
        c = cooler.Cooler(p)
        return c, c.binsize

    def describe(self) -> dict:
        return {"kind": "cooler", "path": self.path, "finest_resolution": self.base_res}

    def _clr(self, res: int):
        if res not in self._cache:
            self._cache[res] = _open_cooler(self.path, res)
        return self._cache[res]

    def genome(self, res: int, chroms: Sequence[str]) -> Tuple[sp.csr_matrix, pd.DataFrame]:
        u, b, _ = pp.load_contacts(self.path, int(res), list(chroms))
        return u, b

    def cis(self, res: int, chrom: str, max_sep: int) -> Tuple[np.ndarray, np.ndarray, np.ndarray, pd.DataFrame]:
        clr, base = self._clr(int(res))
        L = self.chromsizes[chrom]
        f = res // base
        nb = int(np.ceil(L / res))
        st = np.arange(nb, dtype=np.int64) * res
        b = pd.DataFrame({"chrom": chrom, "start": st, "end": np.minimum(st + res, L)})
        off = int(clr.offset(chrom))
        sel = clr.matrix(balance=False, as_pixels=True)
        span = (max_sep + 1) * res
        rows, cols, vals = [], [], []
        step = max(self.chunk_bp // res, 1) * res
        for a in range(0, L, step):
            e = min(a + step, L)
            px = sel.fetch((chrom, a, e), (chrom, a, min(e + span, L)))
            if not len(px):
                continue
            b1 = px["bin1_id"].to_numpy(np.int64) - off
            b2 = px["bin2_id"].to_numpy(np.int64) - off
            flo, fhi = np.minimum(b1, b2), np.maximum(b1, b2)
            # each stored pixel once (a query overlapping the diagonal may return both
            # orientations), and only when its lower fine bin lies in this row chunk
            _, first = np.unique(flo * (L // base + 2) + fhi, return_index=True)
            keep = np.zeros(len(flo), bool)
            keep[first] = True
            lo, hi = flo // f, fhi // f
            own = keep & (flo * base >= a) & (flo * base < e) & (hi - lo <= max_sep)
            rows.append(lo[own])
            cols.append(hi[own])
            vals.append(px["count"].to_numpy(np.float64)[own])
        if rows:
            r, c, v = np.concatenate(rows), np.concatenate(cols), np.concatenate(vals)
            m = sp.coo_matrix((v, (r, c)), shape=(nb, nb)).tocoo()
            m.sum_duplicates()
            return m.row.astype(np.int64), m.col.astype(np.int64), m.data.astype(np.float64), b
        z = np.zeros(0, np.int64)
        return z, z, np.zeros(0), b


def resolve_chroms(names: Sequence[str], chroms=None, exclude: Sequence[str] = ()) -> List[str]:
    """Chromosomes to model: ``chroms`` (str or list, in input order) or every
    input chromosome except ``exclude`` and unplaced / random / alt contigs."""
    if chroms is not None:
        want = [chroms] if isinstance(chroms, str) else list(chroms)
        missing = [c for c in want if c not in names]
        if missing:
            raise ValueError(f"chromosomes not in the input: {missing}")
        return [c for c in names if c in want]
    bad = ("_", "random", "Un", "EBV", "alt", "hap")
    return [c for c in names if c not in set(exclude) and not any(t in c for t in bad)]


# --------------------------------------------------------------------------- balancing

def balance_weights(u: sp.csr_matrix, method: str = "kr", min_coverage: float = 0.05):
    """Per-bin multiplicative weights (NaN = masked) of an upper-triangular raw matrix.
    Coverage filter: bins whose off-diagonal row sum is below ``min_coverage`` x the median
    are masked (``deconv.preprocess.coverage_mask``)."""
    mask = pp.coverage_mask(u, min_coverage=min_coverage)
    if method == "kr":
        w, info = pp.kr_balance(u, mask=mask)
    elif method == "ice":
        w, info = pp.ice_balance(u, mask=mask)
    elif method == "none":
        w = np.where(mask, np.nan, 1.0)
        info = {"method": "none", "n_kept": int((~mask).sum())}
    else:
        raise ValueError(f"unknown balance {method!r}")
    info = {k: (float(v) if isinstance(v, (np.floating, float)) else v) for k, v in info.items()}
    return w, info


def balance_coo(i, j, n, nbins: int, method: str, min_coverage: float):
    """Balance a pixel list (upper triangle, local indices); returns (weights, info)."""
    u = sp.coo_matrix((n, (i, j)), shape=(nbins, nbins)).tocsr()
    return balance_weights(u, method, min_coverage)


# --------------------------------------------------------------------------- expected

def _valid_pairs_per_sep(valid: np.ndarray, max_sep: int) -> np.ndarray:
    """Number of (i, i + s) pairs with both bins valid, s = 0 .. max_sep (one chromosome)."""
    v = valid.astype(np.float64)
    n = len(v)
    if n == 0:
        return np.zeros(max_sep + 1)
    m = 1 << int(np.ceil(np.log2(2 * n)))
    F = np.fft.rfft(v, m)
    ac = np.fft.irfft(F * np.conj(F), m)[: n]
    out = np.zeros(max_sep + 1)
    k = min(max_sep + 1, n)
    out[:k] = np.rint(ac[:k])
    return out


def cis_expected(sep: np.ndarray, val: np.ndarray, valid_by_chrom: Sequence[np.ndarray], max_sep: int) -> np.ndarray:
    """Mean balanced frequency at each separation (zeros included) over valid pairs."""
    tot = np.bincount(sep, weights=val, minlength=max_sep + 1)[: max_sep + 1]
    cnt = np.zeros(max_sep + 1)
    for v in valid_by_chrom:
        cnt += _valid_pairs_per_sep(v, max_sep)
    with np.errstate(invalid="ignore", divide="ignore"):
        e = np.where(cnt > 0, tot / np.maximum(cnt, 1), np.nan)
    return e


def fit_decay(expected: np.ndarray, res: int, max_bp: int, min_sep: int = 2) -> Tuple[float, dict]:
    """Contact-decay exponent gamma of ``E(s) ~ s^-gamma`` (least squares in log-log over
    ``min_sep`` bins .. ``max_bp``)."""
    s = np.arange(len(expected))
    k = (s >= min_sep) & (s * res <= max_bp) & np.isfinite(expected) & (expected > 0)
    if k.sum() < 3:
        return float("nan"), {"n_points": int(k.sum())}
    x, y = np.log(s[k] * res), np.log(expected[k])
    slope, icpt = np.polyfit(x, y, 1)
    return float(-slope), {"n_points": int(k.sum()), "range_bp": [int(s[k].min() * res), int(s[k].max() * res)],
                           "resolution": int(res)}


def fit_power_law(freq: np.ndarray, dist: np.ndarray) -> Tuple[float, float]:
    """Calibration helper: fit ``dist = d0 * freq^(-1/alpha)`` (log-log least squares on
    positive pairs, e.g. imaging median distances vs the same pairs' contact
    frequencies).  Returns ``(alpha, d0)``."""
    f, d = np.asarray(freq, float), np.asarray(dist, float)
    k = np.isfinite(f) & np.isfinite(d) & (f > 0) & (d > 0)
    slope, icpt = np.polyfit(np.log(f[k]), np.log(d[k]), 1)
    return float(-1.0 / slope), float(np.exp(icpt))


def is_local_source(x) -> bool:
    return isinstance(x, (str, Path)) and not str(x).startswith(("http://", "https://", "s3://"))
