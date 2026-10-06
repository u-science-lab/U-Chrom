"""Hi-C helpers for GEM-FISH.

- :func:`load_contact_matrix` pulls a chromosome-restricted, square
  contact matrix from a ``.cool`` / ``.mcool`` file at the requested
  resolution, returning ``(matrix, bin_df)`` with ``bin_df`` carrying
  ``(chrom, start, end)`` for each row / column.
- :func:`aggregate_over_tads` collapses a bin-resolution matrix into a
  TAD-resolution matrix given a list of ``(start, end)`` TAD windows.
- :func:`contact_to_distance` applies Abbas et al. 2019 Eqn. 10 to
  convert inter-TAD contact counts to initial distance estimates used
  by the Stage-3 assembly step.
"""

from __future__ import annotations

from typing import List, Optional, Tuple

import numpy as np
import pandas as pd


def load_contact_matrix(
    path: str,
    chrom: str,
    resolution: Optional[int] = None,
    normalize: bool = True,
) -> Tuple[np.ndarray, pd.DataFrame]:
    """Load a single-chromosome contact matrix from ``.cool`` / ``.mcool``.

    Parameters
    ----------
    path : str
        Path to a ``.cool`` (single resolution) or ``.mcool`` file.  For
        ``.mcool``, pass ``resolution`` to pick the resolution group;
        the function prepends ``::resolutions/{resolution}`` as needed.
    chrom : str
        Chromosome name as stored in the cooler.
    resolution : int, optional
        Required for ``.mcool`` files; ignored for ``.cool`` files that
        already fix the resolution.
    normalize : bool
        Apply cooler's weight column (KR / ICE as stored) when
        available.  Falls back to raw counts if no weights are present.

    Returns
    -------
    matrix : ndarray (n_bins, n_bins), float64
    bin_df : DataFrame with ``chrom, start, end`` per row.
    """
    try:
        from cooler import Cooler
    except ImportError as exc:  # pragma: no cover
        raise ImportError(
            "cooler is required to read .cool/.mcool files"
        ) from exc

    if path.endswith(".mcool"):
        if resolution is None:
            raise ValueError("resolution must be provided for .mcool files")
        uri = f"{path}::/resolutions/{int(resolution)}"
    else:
        uri = path
    c = Cooler(uri)
    if chrom not in c.chromnames:
        raise ValueError(
            f"chromosome '{chrom}' not found in {uri}; "
            f"available: {list(c.chromnames)[:10]}…"
        )
    mat = c.matrix(balance=normalize).fetch(chrom)
    mat = np.asarray(mat, dtype=np.float64)
    mat[~np.isfinite(mat)] = 0.0
    bins = c.bins().fetch(chrom)[["chrom", "start", "end"]].reset_index(drop=True)
    return mat, bins


def aggregate_over_tads(
    matrix: np.ndarray,
    bin_df: pd.DataFrame,
    tads: pd.DataFrame,
) -> Tuple[np.ndarray, List[Tuple[int, int]]]:
    """Collapse a bin-resolution matrix into a TAD-resolution matrix.

    Parameters
    ----------
    matrix : ndarray (n_bins, n_bins)
        Row / column ordering matches ``bin_df``.
    bin_df : DataFrame with ``chrom, start, end``.
    tads : DataFrame with ``start, end`` (bp).  Assumed sorted by start
        and on the same chromosome as the matrix.

    Returns
    -------
    tad_matrix : ndarray (n_tads, n_tads)
        Sum of bin-level contacts over each ``(TAD_i, TAD_j)`` window.
    tad_bin_indices : list of (start_idx, end_idx) into ``bin_df``
        Bin-index range covered by each TAD (end exclusive).
    """
    starts = bin_df["start"].to_numpy()
    ends = bin_df["end"].to_numpy()
    tad_bins = []
    for _, row in tads.iterrows():
        lo = int(row["start"])
        hi = int(row["end"])
        s_idx = int(np.searchsorted(ends, lo + 1, side="left"))
        e_idx = int(np.searchsorted(starts, hi, side="left"))
        if e_idx <= s_idx:
            e_idx = s_idx + 1  # keep at least one bin
        tad_bins.append((s_idx, e_idx))

    n_tads = len(tad_bins)
    agg = np.zeros((n_tads, n_tads), dtype=np.float64)
    for i, (si, ei) in enumerate(tad_bins):
        for j, (sj, ej) in enumerate(tad_bins):
            agg[i, j] = matrix[si:ei, sj:ej].sum()
    return agg, tad_bins


def contact_to_distance(
    contacts: np.ndarray,
    genomic_distances: Optional[np.ndarray] = None,
    alpha: float = 0.25,
    fallback_c: float = 1.0,
    fallback_beta: float = 0.5,
) -> np.ndarray:
    """Abbas 2019 Eqn. 10 — convert contact counts to initial distances.

    ``d_ij = f_ij^{-α}`` when ``f_ij > 0``.  For zero-contact pairs the
    paper falls back to a genomic-distance-based estimate
    ``d_ij = c · g_ij^{β}`` where ``g_ij`` is the genomic separation in
    bp.  We use the two fallback parameters in the same sense.

    Parameters
    ----------
    contacts : ndarray (N, N)
    genomic_distances : ndarray (N, N), optional
        Absolute genomic separation of each TAD pair in bp.  Must be
        supplied if any zero contacts need the fallback estimate.
    alpha : float
        Power-law exponent; 0.25 from Wang 2016 (empirical for IMR90).
    fallback_c, fallback_beta : float
        Parameters of the power-law fallback for zero-contact pairs.

    Returns
    -------
    d : ndarray (N, N)
        Symmetric, non-negative.  Diagonal is 0.
    """
    f = np.asarray(contacts, dtype=np.float64)
    d = np.zeros_like(f)
    mask_pos = f > 0
    with np.errstate(invalid="ignore", divide="ignore"):
        d[mask_pos] = f[mask_pos] ** (-alpha)
    if (~mask_pos).any():
        if genomic_distances is None:
            # Best we can do: leave at 0 and let the caller handle.
            pass
        else:
            g = np.asarray(genomic_distances, dtype=np.float64)
            fallback = fallback_c * np.power(
                np.maximum(g, 1.0), fallback_beta,
            )
            d[~mask_pos] = fallback[~mask_pos]
    np.fill_diagonal(d, 0.0)
    # Symmetrise defensively
    d = 0.5 * (d + d.T)
    return d


__all__ = [
    "load_contact_matrix",
    "aggregate_over_tads",
    "contact_to_distance",
]
