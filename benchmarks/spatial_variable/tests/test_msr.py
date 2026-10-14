"""Moran spectral randomisation of stage cnv_null keeps the variance and Moran's I, not the place."""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

pytest.importorskip("uchrom")
import spatial_variable as SV  # noqa: E402


@pytest.fixture(scope="module")
def grid():
    yy, xx = np.mgrid[0:36, 0:40]
    g = pd.DataFrame({"centroid_x": xx.ravel().astype(float), "centroid_y": yy.ravel().astype(float)},
                     index=[f"s{i}" for i in range(xx.size)])
    V, lam, A = SV._msr_basis(g)
    rng = np.random.default_rng(0)
    # two smooth covariates with noise, like copy-number components
    x = np.c_[np.sin(xx.ravel() / 5.0) + 0.3 * rng.standard_normal(xx.size),
              np.exp(-((xx.ravel() - 25) ** 2 + (yy.ravel() - 12) ** 2) / 60.0) + 0.1 * rng.standard_normal(xx.size)]
    return g, V, lam, A, x - x.mean(axis=0)


def _moran(A, v):
    return len(v) / A.sum() * (v * (A @ v)).sum(0) / (v ** 2).sum(0)


def test_basis(grid):
    g, V, lam, A, x = grid
    assert V.shape == (len(g), len(g) - 1) and np.all(np.diff(lam) >= -1e-9)
    assert np.allclose(V.sum(axis=0), 0, atol=1e-8)                     # orthogonal to the constant


def test_signs_keep_variance_and_moran_exactly(grid):
    g, V, lam, A, x = grid
    r = SV.msr(x, V, np.random.default_rng(1))
    assert np.allclose(r.var(axis=0), x.var(axis=0))
    assert np.allclose(_moran(A, r), _moran(A, x))


def test_bands_keep_variance_and_moran_and_lose_the_place(grid):
    g, V, lam, A, x = grid
    rng = np.random.default_rng(2)
    rs = [SV.msr(x, V, rng, band=20) for _ in range(50)]
    assert all(np.allclose(r.var(axis=0), x.var(axis=0)) for r in rs)
    mor = np.array([_moran(A, r) for r in rs])
    assert np.allclose(mor.mean(axis=0), _moran(A, x), rtol=0.05)
    cor = np.array([[abs(np.corrcoef(r[:, j], x[:, j])[0, 1]) for j in range(x.shape[1])] for r in rs])
    assert cor.mean() < 0.3                                             # a new map each time
