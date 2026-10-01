"""Synthetic toys for the bulk benchmark tests (they check the scorers / I/O only)."""

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import _common  # noqa: E402,F401  (paths)
from population import Population  # noqa: E402


def toy_population(S=60, n_chrom=2, n_loci=25, res=3_000_000, seed=0, two_states=False, missing=0.0):
    """Diploid confined random walks (nm); with ``two_states`` half of the cells have a compact
    chr1 (a subpopulation)."""
    rng = np.random.default_rng(seed)
    chrom = np.repeat([f"chr{c + 1}" for c in range(n_chrom)], n_loci)
    start = np.tile(np.arange(n_loci) * res, n_chrom).astype(np.int64)
    L = len(chrom)
    X = np.zeros((S, 2, L, 3))
    for s in range(S):
        for p in range(2):
            for c in range(n_chrom):
                k = np.flatnonzero(chrom == f"chr{c + 1}")
                step = 300.0 if not (two_states and s % 2 and c == 0) else 120.0
                X[s, p, k] = np.cumsum(rng.normal(scale=step, size=(len(k), 3)), 0) + rng.normal(scale=1500, size=3)
    if missing:
        X[rng.random((S, 2, L)) < missing] = np.nan
    return Population(chrom, start, start + 100_000, X, meta={"dataset": "toy", "unit": "nm"})

