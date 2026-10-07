"""Small synthetic ChromData generators with planted structure.

Everything here is deterministic (fixed seeds) and CPU-cheap so structure
callers can be checked for *recovery* of a known answer, not just "runs".
"""
from __future__ import annotations

import numpy as np
import pandas as pd

RES = 30_000


def _spots(n_traces: int, n_bins: int, chrom: str = "chr1") -> pd.DataFrame:
    rows = [
        (chrom, k * RES, (k + 1) * RES, t)
        for t in range(n_traces)
        for k in range(n_bins)
    ]
    return pd.DataFrame(rows, columns=["chrom", "start", "end", "trace_id"])


def domain_traces(n_traces=150, bounds=(0, 15, 30, 45), seed=0):
    """Chains made of compact random-walk globules (one per domain),
    with a large jump between consecutive domains → TAD boundaries at
    ``bounds[1:-1]`` (bin indices)."""
    from uchrom import ChromData

    rng = np.random.default_rng(seed)
    coords = []
    for _ in range(n_traces):
        pts = []
        for a, b in zip(bounds[:-1], bounds[1:]):
            rw = np.cumsum(rng.normal(0, 0.3, (b - a, 3)), axis=0)
            rw -= rw.mean(0)
            centre = (pts[-1][-1] if pts else np.zeros(3)) + rng.normal(0, 1.5, 3)
            pts.append(centre + rw)
        coords.append(np.concatenate(pts))
    return ChromData(np.concatenate(coords), _spots(n_traces, bounds[-1]))


def chain_traces(n_traces=200, n_bins=40, seed=0, loop=None, a_mask=None):
    """Plain random-walk chains, optionally with

    * ``loop=(i, j)`` — in 80 % of traces bins j-1..j+1 are glued onto
      i-1..i+1 (a planted loop anchor pair);
    * ``a_mask`` — boolean (n_bins,) of "A" bins pulled towards a shared
      hub (a planted compartment).
    """
    from uchrom import ChromData

    rng = np.random.default_rng(seed)
    coords = []
    for _ in range(n_traces):
        X = np.cumsum(rng.normal(0, 0.5, (n_bins, 3)), axis=0)
        if loop is not None and rng.random() < 0.8:
            i, j = loop
            X[j - 1:j + 2] = X[i - 1:i + 2] + rng.normal(0, 0.1, (3, 3))
        if a_mask is not None:
            hub = X.mean(0) + rng.normal(0, 0.1, 3)
            X[a_mask] = 0.3 * X[a_mask] + 0.7 * hub
        coords.append(X)
    return ChromData(np.concatenate(coords), _spots(n_traces, n_bins))


def block_contact_matrix(block_sizes=(30, 30, 30), seed=0):
    """Hi-C-like matrix: power-law decay × 5-fold intra-block enrichment."""
    rng = np.random.default_rng(seed)
    n = sum(block_sizes)
    idx = np.arange(n)
    sep = np.abs(idx[:, None] - idx[None, :]) + 1.0
    mat = 100.0 * sep ** -1.0
    labels = np.repeat(np.arange(len(block_sizes)), block_sizes)
    mat *= np.where(labels[:, None] == labels[None, :], 5.0, 1.0)
    mat *= rng.uniform(0.9, 1.1, mat.shape)
    return (mat + mat.T) / 2
