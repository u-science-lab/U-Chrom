"""Shared synthetic toys for the screcon tests (synthetic data only check scorer / I/O correctness)."""

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def toy_polymer(n_chrom=3, n_bins=150, res=100_000, seed=0):
    """Confined random-walk chromosomes (nm) as a truth dict (loci = consecutive 100 kb bins)."""
    rng = np.random.default_rng(seed)
    chrom, start, coords = [], [], []
    for c in range(n_chrom):
        steps = rng.normal(size=(n_bins, 3)) * 100.0
        x = np.cumsum(steps, 0)
        x = x - x.mean(0) + rng.normal(size=3) * 400.0
        chrom += [f"chr{c + 1}"] * n_bins
        start += list(np.arange(n_bins) * res + 5 * res)
        coords.append(x)
    start = np.array(start, np.int64)
    return {"chrom": np.array(chrom), "start": start, "end": start + res, "coords": np.concatenate(coords),
            "measured": np.ones(len(start), bool), "meta": {"dataset": "toy"}}


@pytest.fixture
def toy():
    return toy_polymer()
