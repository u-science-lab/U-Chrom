"""Few-cell deconvolution (EMber-mix, in development): plumbing of ``deconvolve_cells`` and the engine.

Synthetic toy pools of two random-walk "cells" check the API, the ChromData layout and that a
partially correct seed (``mix_prior``) is turned into well-separated cells.  The benchmark (imaging
truths, Stevens / Nagano pools) is ``benchmarks/screcon`` (``mix_*.py``, PREREG §12).
"""

import numpy as np
import pandas as pd
import pytest

un = pytest.importorskip("uchrom_nucdyn")

QUICK = dict(particle_sizes=[4e6, 1e6, 4e5], n_models=2, seed=3, device="cpu", n_threads=2,
             robust_temp_steps=[60], robust_dynamics_steps=[50])


def toy_pool(k=2, seed=1, n_try=40_000):
    rng = np.random.default_rng(seed)
    nloc, step = 120, 100_000
    chroms = ("chr1", "chr2", "chr3")
    rows, origin = [], []
    for s in range(k):
        walks = {c: np.cumsum(rng.normal(scale=0.35, size=(nloc, 3)), axis=0) + rng.normal(scale=3, size=3)
                 for c in chroms}
        for _ in range(n_try):
            a = chroms[rng.integers(3)]
            b = a if rng.random() < 0.85 else chroms[rng.integers(3)]
            i, j = rng.integers(nloc, size=2)
            if np.sum((walks[a][i] - walks[b][j]) ** 2) < 0.8:
                rows.append((a, i * step + 1 + rng.integers(step - 1), b, j * step + 1 + rng.integers(step - 1)))
                origin.append(s)
    df = pd.DataFrame(rows, columns=["chrom1", "pos1", "chrom2", "pos2"])
    return df, np.array(origin)


def test_deconvolve_cells_layout_and_seeded_recovery():
    from uchrom.recon.sc import deconvolve_cells
    df, origin = toy_pool()
    rng = np.random.default_rng(0)
    seed_cell = np.where(rng.random(len(origin)) < 0.5, rng.integers(0, 2, len(origin)), origin)
    prior = np.eye(2)[seed_cell]
    cd = deconvolve_cells(df, n_cells=2, mix_prior=prior, mix_seed_keep=0.95, mix_prior_mode="posterior",
                          mix_prior_floor=0.0, **QUICK)
    assert list(cd.cells.index) == ["mix0", "mix1"]
    assert set(cd.spots["cell_id"].astype(str)) == {"mix0", "mix1"}
    assert {"model_0", "model_1"} <= set(cd.layers)
    P = cd.results["ember_mix.cell_probs"]
    assert P.shape == (len(df), 2)
    assert np.allclose(P.sum(1), 1.0)
    rec = cd.results.record("ember_mix.cell_probs")
    assert rec.function.endswith("deconvolve_cells")
    sep = np.where(df.chrom1 == df.chrom2, (df.pos1 - df.pos2).abs(), 10**12)
    lr = sep >= 2_000_000
    acc = np.mean(P[lr].argmax(1) == origin[lr])
    acc = max(acc, 1 - acc)
    assert acc > 0.65, acc


def test_mix_seed_prior_shapes():
    df, _ = toy_pool(n_try=10_000)
    for mode in ("patch", "random", "uniform", "tri"):
        P = un.mix_seed_prior(df.chrom1, df.pos1, df.chrom2, df.pos2, mix_cells=3, mix_seed=mode)
        assert P.shape == (len(df), 3)
        assert np.allclose(P.sum(1), 1.0)


def test_n_cells_must_be_at_least_two():
    from uchrom.recon.sc import deconvolve_cells
    df, _ = toy_pool(n_try=2000)
    with pytest.raises(ValueError):
        deconvolve_cells(df, n_cells=1, **QUICK)
