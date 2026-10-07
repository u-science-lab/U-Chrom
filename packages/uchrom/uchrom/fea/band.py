"""Banded access to large contact maps: what the Hi-C structure callers share.

A 5 kb map of a large chromosome is too big for a dense matrix (chr1: 50,000 bins), but the callers only
look near the diagonal — insulation within a window, loops within a few Mb, the expected contact frequency
per separation.  :func:`read_band` reads one chromosome's pixels up to ``max_dist`` from the diagonal, in
chunks of the cooler's pixel table, and keeps them as a sparse :class:`Band` (raw counts, balancing
weights).  :func:`expected_cis` is the mean balanced contact per diagonal over the valid (unmasked) pairs —
the "expected" of observed / expected.

``cd`` is a ``ChromData`` with the map linked (``contacts=`` its key), the path of a ``.cool`` / ``.mcool``,
or an open ``cooler.Cooler``, as for :func:`uchrom.fea.contact_matrix`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional, Sequence

import numpy as np
import pandas as pd

__all__ = ["Band", "read_band", "expected_cis", "band_observed_over_expected"]

#: pixels read per chunk of the cooler's pixel table (larger chunks are no faster and cost ~170 B per pixel)
CHUNK = 2_000_000


@dataclass
class Band:
    """One chromosome's pixels within ``max_diag`` bins of the diagonal (upper triangle, ``i <= j``)."""

    chrom: str
    binsize: int
    starts: np.ndarray            # (n,) bin starts (bp)
    i: np.ndarray                 # (m,) chromosome-local row bins, int64
    j: np.ndarray                 # (m,) column bins, j >= i
    count: np.ndarray             # (m,) raw counts, float64
    weight: Optional[np.ndarray]  # (n,) balancing weights (NaN: masked bin); None = unbalanced
    max_diag: int

    @property
    def n(self) -> int:
        return len(self.starts)

    @property
    def valid(self) -> np.ndarray:
        """Bins with a finite weight (all bins of an unbalanced map)."""
        if self.weight is None:
            return np.ones(self.n, bool)
        return np.isfinite(self.weight)

    def values(self, balance: bool = True) -> np.ndarray:
        """Balanced (``weight[i] * weight[j] * count``; NaN on masked bins) or raw values of the pixels."""
        if not balance or self.weight is None:
            return self.count
        return self.count * self.weight[self.i] * self.weight[self.j]

    @property
    def diag(self) -> np.ndarray:
        return self.j - self.i

    def dense(self, lo: int = 0, hi: Optional[int] = None, *, balance: bool = True) -> np.ndarray:
        """The symmetric dense matrix of bins ``[lo, hi)`` (pixels beyond the band are 0; masked bins NaN)."""
        hi = self.n if hi is None else hi
        m = np.zeros((hi - lo, hi - lo))
        sel = (self.i >= lo) & (self.j < hi)
        v = self.values(balance)[sel]
        ii, jj = self.i[sel] - lo, self.j[sel] - lo
        m[ii, jj] = v
        m[jj, ii] = v
        if balance and self.weight is not None:
            bad = ~self.valid[lo:hi]
            m[bad, :] = np.nan
            m[:, bad] = np.nan
        return m


def _cooler(cd, contacts, resolution):
    from .maps import _is_cooler, open_map

    return cd if _is_cooler(cd) else open_map(cd, contacts, resolution=resolution)


def read_band(cd, contacts: Optional[str] = None, *, chrom: str, resolution: Optional[int] = None,
              max_dist: Optional[int] = None, balance: bool = True, chunk: int = CHUNK) -> Band:
    """The pixels of ``chrom`` within ``max_dist`` bp of the diagonal (default: all) as a :class:`Band`.

    Reads the chromosome's rows of the pixel table in chunks of ``chunk`` pixels, so memory stays at the
    band.  ``balance=True`` keeps the ``weight`` column (an unbalanced map warns and gives ``weight=None``).
    """
    import warnings

    clr = _cooler(cd, contacts, resolution)
    if chrom not in clr.chromnames:
        raise ValueError(f"{chrom!r} is not in the map ({list(clr.chromnames)[:10]})")
    lo, hi = clr.extent(chrom)
    n = hi - lo
    bins = clr.bins()[lo:hi]
    if clr.binsize:
        binsize = int(clr.binsize)
    else:                     # anchored map (rebin_map(anchor=)): regular bins between shorter end bins
        sizes, counts = np.unique((bins["end"] - bins["start"]).to_numpy(dtype=np.int64), return_counts=True)
        binsize = int(sizes[counts.argmax()]) if len(sizes) else 1
    max_diag = n if max_dist is None else int(np.ceil(max_dist / binsize))
    weight = None
    if balance:
        if "weight" in bins.columns:
            weight = bins["weight"].to_numpy(dtype=np.float64)
        else:
            warnings.warn(f"{clr.uri}: not balanced (no 'weight' column); using raw counts", stacklevel=2)
    with clr.open("r") as h5:
        # the pixel table is sorted by bin1: its row bins follow from the index, which saves decompressing the
        # bin1_id column (a third of the read)
        offsets = h5["indexes"]["bin1_offset"][lo: hi + 1].astype(np.int64)
        p0, p1 = int(offsets[0]), int(offsets[-1])
        pix = h5["pixels"]
        ii, jj, cc = [], [], []
        for s in range(p0, p1, chunk):
            e = min(s + chunk, p1)
            r0 = int(np.searchsorted(offsets, s, side="right")) - 1
            r1 = int(np.searchsorted(offsets, e, side="left"))
            per_row = np.minimum(offsets[r0 + 1: r1 + 1], e) - np.maximum(offsets[r0: r1], s)
            bin1 = np.repeat(np.arange(lo + r0, lo + r1, dtype=np.int64), per_row)
            bin2 = pix["bin2_id"][s:e].astype(np.int64)
            keep = (bin2 < hi) & (bin2 - bin1 <= max_diag)
            ii.append(bin1[keep] - lo)
            jj.append(bin2[keep] - lo)
            cc.append(pix["count"][s:e][keep].astype(np.float64))
    i = np.concatenate(ii) if ii else np.zeros(0, np.int64)
    j = np.concatenate(jj) if jj else np.zeros(0, np.int64)
    c = np.concatenate(cc) if cc else np.zeros(0)
    return Band(chrom=str(chrom), binsize=binsize, starts=bins["start"].to_numpy(dtype=np.int64), i=i, j=j,
                count=c, weight=weight, max_diag=max_diag)


def _valid_pairs(valid: np.ndarray, max_diag: int) -> np.ndarray:
    """#{i : valid[i] and valid[i + d]} for d = 0..max_diag (an autocorrelation, by FFT)."""
    from scipy.signal import fftconvolve

    v = valid.astype(np.float64)
    full = fftconvolve(v, v[::-1])                        # lag d at index n - 1 + d
    n = len(v)
    return np.rint(full[n - 1: n + max_diag]).astype(np.int64)


def _expected_one(band: Band, balance: bool) -> pd.DataFrame:
    n = band.n
    D = min(band.max_diag, n - 1)
    valid = band.valid if balance else np.ones(n, bool)
    n_valid = _valid_pairs(valid, D)
    v = band.values(balance)
    d = band.diag
    ok = np.isfinite(v) & (d <= D)
    s = np.bincount(d[ok], weights=v[ok], minlength=D + 1)[: D + 1]
    raw = np.bincount(d[ok], weights=band.count[ok], minlength=D + 1)[: D + 1]
    with np.errstate(invalid="ignore", divide="ignore"):
        avg = np.where(n_valid > 0, s / np.maximum(n_valid, 1), np.nan)
    return pd.DataFrame({"chrom": band.chrom, "diag": np.arange(D + 1), "dist": np.arange(D + 1) * band.binsize,
                         "n_valid": n_valid, "count_sum": raw, "balanced_sum": s, "balanced_avg": avg})


def expected_cis(cd, contacts: Optional[str] = None, *, chroms: Optional[Sequence[str]] = None,
                 resolution: Optional[int] = None, max_dist: Optional[int] = None, balance: bool = True,
                 bands: Optional[Iterable[Band]] = None) -> pd.DataFrame:
    """Mean contact per separation, per chromosome: ``chrom, diag, dist, n_valid, count_sum, balanced_sum,
    balanced_avg`` (``balanced_avg = balanced_sum / n_valid`` over the pairs of unmasked bins).

    Give ``bands`` (:func:`read_band` results) to reuse pixels already read; otherwise every chromosome of
    the map (or ``chroms``) is read up to ``max_dist``.
    """
    if bands is None:
        clr = _cooler(cd, contacts, resolution)
        names = list(chroms) if chroms is not None else list(clr.chromnames)
        bands = (read_band(clr, chrom=c, max_dist=max_dist, balance=balance) for c in names)
    return pd.concat([_expected_one(b, balance) for b in bands], ignore_index=True)


def band_observed_over_expected(band: Band, expected: Optional[pd.DataFrame] = None) -> np.ndarray:
    """Observed / expected (balanced) of every pixel of ``band``: the expected per diagonal of its
    chromosome (:func:`expected_cis`; computed from the band when not given).  NaN where the expected is 0
    or a bin is masked."""
    if band.weight is None:
        raise ValueError("observed / expected needs a balanced map (a 'weight' column)")
    exp = expected if expected is not None else _expected_one(band, True)
    exp = exp[exp["chrom"] == band.chrom].set_index("diag")["balanced_avg"]
    e = exp.reindex(np.arange(band.max_diag + 1)).to_numpy()
    d = np.minimum(band.diag, len(e) - 1)
    with np.errstate(invalid="ignore", divide="ignore"):
        return band.values(True) / e[d]
