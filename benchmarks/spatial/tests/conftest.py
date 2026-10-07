"""Synthetic toys for the spatial tests (they check the code, not the method on data)."""

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import tissue as ts  # noqa: E402

TOY_CHROMS = ["chr1", "chr2", "chr3"]
TOY_SIZES = {"chr1": 60_000_000, "chr2": 50_000_000, "chr3": 40_000_000}
TOY_LAYERS = [(0.33, {"T0": 0.7, "T1": 0.2, "T2": 0.1}), (0.66, {"T0": 0.2, "T1": 0.6, "T2": 0.2}),
              (1.0, {"T0": 0.1, "T1": 0.2, "T2": 0.7})]


def toy_layout(res=1_000_000):
    return ts.Layout(res, chroms=list(TOY_CHROMS), sizes=dict(TOY_SIZES))


def toy_type_probs(n_types=3, res=1_000_000, seed=0, gamma=0.6, n_flip=0.25):
    """Per type a pair-probability vector on the toy layout: P(s) ~ s^-1 x exp(gamma v_i v_j),
    v = shared +-1 compartments with a type-specific fraction of bins flipped."""
    lay = toy_layout(res)
    rng = np.random.default_rng(seed)
    base_v = np.sign(np.sin(np.arange(lay.n_bins) / 4.0) + 0.2 * rng.normal(size=lay.n_bins))
    a = lay.bin_off[lay.pair_chrom] + lay.pair_i
    b = lay.bin_off[lay.pair_chrom] + lay.pair_j
    s = np.maximum(lay.pair_sep, 0.5) * res
    probs = []
    for _t in range(n_types):
        v = base_v.copy()
        v[rng.random(lay.n_bins) < n_flip] *= -1
        w = s ** -1.0 * np.exp(gamma * v[a] * v[b])
        probs.append(w / w.sum())
    return lay, np.array(probs)


def toy_pool(n_cells_per_type=6, n_contacts=40_000, n_types=3, seed=1):
    """(layout, true type probabilities, {name: (type, (n, 2) bins)}, types); base layout = the layout."""
    lay, probs = toy_type_probs(n_types)
    types = [f"T{k}" for k in range(n_types)]
    rng = np.random.default_rng(seed)
    a = lay.bin_off[lay.pair_chrom] + lay.pair_i
    b = lay.bin_off[lay.pair_chrom] + lay.pair_j
    pool = {}
    for t in range(n_types):
        for k in range(n_cells_per_type):
            idx = rng.choice(lay.n_pairs, size=n_contacts, p=probs[t])
            pool[f"c{t}_{k}"] = (types[t], np.stack([a[idx], b[idx]], 1).astype(np.int32))
    return lay, probs, pool, types


@pytest.fixture
def toy_layers(monkeypatch):
    monkeypatch.setattr(ts, "LAYERS", TOY_LAYERS)
    return TOY_LAYERS


@pytest.fixture(scope="session")
def toy():
    return toy_pool()
