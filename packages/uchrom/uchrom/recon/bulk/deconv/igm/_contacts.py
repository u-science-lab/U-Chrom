"""Contact probabilities of a population with IGM's contact definition."""

from __future__ import annotations

from typing import Optional, Tuple

import numpy as np
import pandas as pd


def population_array(cd) -> Tuple[np.ndarray, pd.DataFrame, np.ndarray]:
    """Coordinates of a population ChromData as an array (S, n_bins, n_copies, 3)
    (NaN where a bin has fewer copies), with the bins and the cell ids."""
    spots = cd.spots_with_loci() if hasattr(cd, "spots_with_loci") else cd.spots
    coords = np.asarray(cd.coords, dtype=np.float64)
    tr = cd.traces
    copy_of = pd.Series(tr["copy"].to_numpy(), index=tr.index.astype(str))
    cell = spots["cell_id"].astype(str).to_numpy()
    cells, ci = np.unique(cell, return_inverse=True)
    cp = copy_of.reindex(spots["trace_id"].astype(str).to_numpy()).to_numpy().astype(np.int64)
    b = spots["bin_id"].to_numpy().astype(np.int64)
    nb = len(cd.bins)
    nc = int(cp.max()) + 1 if len(cp) else 1
    X = np.full((len(cells), nb, nc, 3), np.nan)
    X[ci, b, cp] = coords
    return X, cd.bins, cells


def contact_probabilities(
    cd,
    *,
    pairs: Optional[Tuple[np.ndarray, np.ndarray]] = None,
    contact_range: float = 2.0,
    mode: str = "mean",
    chunk: int = 20000,
) -> np.ndarray:
    """Population contact probability of haploid bin pairs.

    A copy pair is in contact when the centre distance is at most
    ``contact_range * (r_i + r_j)`` (``bin_tracks["radius_nm"]``).
    ``mode="mean"``: the fraction over structures and copy combinations —
    same-copy combinations for intra-chromosomal pairs, all combinations for
    inter-chromosomal ones — i.e. the quantity IGM's A-step fits
    (``p_now``).  ``mode="sum"``: IGM's reporting map (contacts summed over
    the copy combinations per structure, averaged, clipped at 1;
    alabtools ``sumCopies``).

    ``pairs``: ``(i, j)`` bin index arrays; default every pair i < j
    (returned as a dense symmetric matrix with 1 on the diagonal).
    """
    X, bins, _ = population_array(cd)
    r = np.asarray(cd.bin_tracks["radius_nm"], dtype=np.float64)
    chrom = bins["chrom"].astype(str).to_numpy()
    dense = pairs is None
    if dense:
        ii, jj = np.triu_indices(len(bins), 1)
    else:
        ii, jj = (np.asarray(pairs[0], dtype=np.int64), np.asarray(pairs[1], dtype=np.int64))
    out = np.zeros(len(ii))
    nc = X.shape[2]
    for a in range(0, len(ii), chunk):
        i, j = ii[a:a + chunk], jj[a:a + chunk]
        rc2 = (contact_range * (r[i] + r[j])) ** 2
        intra = chrom[i] == chrom[j]
        hit = np.zeros((X.shape[0], len(i)))
        tot = np.zeros((X.shape[0], len(i)))
        for c1 in range(nc):
            for c2 in range(nc):
                d2 = ((X[:, i, c1] - X[:, j, c2]) ** 2).sum(-1)
                valid = np.isfinite(d2)
                use = valid & ((c1 == c2) | ~intra)[None, :]
                hit += use & (d2 <= rc2[None, :])
                tot += use
        if mode == "mean":
            out[a:a + chunk] = hit.sum(0) / np.maximum(tot.sum(0), 1)
        elif mode == "sum":
            out[a:a + chunk] = np.minimum(hit.mean(0), 1.0)
        else:
            raise ValueError("mode must be 'mean' or 'sum'")
    if not dense:
        return out
    M = np.eye(len(bins))
    M[ii, jj] = out
    M[jj, ii] = out
    return M
