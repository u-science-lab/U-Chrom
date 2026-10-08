"""uchrom.fea.impute_rwr: random walk with restart on single-cell maps (SnapHiC / scHiCluster), the numpy
reference against the definition and against the native kernel (``uchrom_maps``, skipped without it)."""

from __future__ import annotations

import sys

import numpy as np
import pandas as pd
import pytest

from uchrom.fea import impute_rwr as IM

try:
    import uchrom_maps
    HAVE_NATIVE = hasattr(uchrom_maps, "rwr_band")
except ImportError:                                       # pragma: no cover - the crate is optional
    HAVE_NATIVE = False

native = pytest.mark.skipif(not HAVE_NATIVE, reason="uchrom_maps with rwr_band is not installed")


def _cell(n, k, seed, long=3):
    rng = np.random.default_rng(seed)
    a = rng.integers(0, n, k)
    d = (rng.random(k) ** long * n).astype(int) + 2
    b = a + d
    ok = b < n
    return a[ok], b[ok]


def _rwr_definition(n, i, j, rp, s=0, e=None):
    """R = Q + Q^T, Q = rp (I - (1 - rp) P)^-1, P the row-normalised binary adjacency (chain + contacts at
    least 2 bins apart) of the bins s..e-1 — SnapHiC's formulation, solved directly."""
    e = n if e is None else e
    m = e - s
    A = np.zeros((m, m))
    for a, b in zip(i, j):
        a, b = min(a, b), max(a, b)
        if b - a >= 2 and a >= s and b < e:
            A[a - s, b - s] = A[b - s, a - s] = 1
    for k in range(m - 1):
        A[k, k + 1] = A[k + 1, k] = 1
    P = A / A.sum(axis=1, keepdims=True)
    Q = rp * np.linalg.inv(np.eye(m) - (1 - rp) * P)
    return Q + Q.T


def test_whole_chromosome_is_the_definition():
    n = 90
    i, j = _cell(n, 60, 1)
    band = IM.rwr_band(i, j, n, rp=0.05, window=0, max_diag=20, backend="numpy")
    R = _rwr_definition(n, i, j, 0.05)
    assert band.shape == (n, 21)
    for d in range(21):
        assert np.allclose(band[:n - d, d], np.diagonal(R, d), rtol=1e-11, atol=0)
        assert np.isnan(band[n - d:, d]).all()


def test_windows_own_every_pixel_once_from_the_nearest_window():
    n, w, step, D = 230, 60, 30, 20
    i, j = _cell(n, 200, 2)
    band = IM.rwr_band(i, j, n, rp=0.05, window=w, step=step, max_diag=D, backend="numpy")
    starts, ends, lo, hi = IM.plan_windows(n, w, step, D)
    assert starts[0] == 0 and (np.diff(starts) == step).all()
    # every pixel of the band inside the chromosome is filled (SnapHiC's sliding windows leave some at 0)
    rows = np.arange(n)[:, None] + np.arange(D + 1)[None, :]
    assert np.isfinite(band[rows < n]).all()
    for k, (s, e) in enumerate(zip(starts, ends)):
        R = _rwr_definition(n, i, j, 0.05, s, e)
        for a in range(s, e):
            for d in range(D + 1):
                c = 2 * a + d
                if a + d < e and lo[k] <= c < hi[k]:
                    assert band[a, d] == pytest.approx(R[a - s, a - s + d], rel=1e-11)
                    centre = starts + w / 2
                    assert abs(s + w / 2 - c / 2) == pytest.approx(np.abs(centre - c / 2).min())


def test_plan_windows_checks_the_band():
    with pytest.raises(ValueError, match="too small"):
        IM.plan_windows(500, 40, 20, 25)
    s, e, lo, hi = IM.plan_windows(30, 100, 50, 10)              # a chromosome smaller than a window
    assert list(s) == [0] and list(e) == [30]


def test_zscores_per_diagonal_trim_the_top_values():
    n, D = 400, 6
    band = IM.rwr_band(*_cell(n, 300, 5), n, max_diag=D, window=0, backend="numpy")
    z = IM.zscore_band(band, edge=5, trim=0.01, backend="numpy")
    d = 3
    v = band[5:n - 5 - d, d]
    t = round(0.01 * len(v)) - 1                                   # 390 values: round(3.9) - 1 = 3 left out
    rest = np.sort(v)[::-1][t:]
    assert t == 3
    assert np.allclose(z[5:n - 5 - d, d], (v - rest.mean()) / rest.std())
    assert (z[:5, d] == 0).all() and (z[n - 5 - d:n - d, d] == 0).all()
    assert np.isnan(z[:, 0]).all() and np.isnan(z[n - 2, 3])


def test_auto_window_is_snaphic2s_rule():
    d = np.r_[np.full(81, 100), np.full(19, 5000)]                # bins of 10 kb: 1 Mb and 50 Mb
    assert IM.auto_window(d, binsize=10_000) == 10_000_000
    d = np.r_[np.full(79, 100), np.full(21, 2500)]                # 25 Mb: the 30 Mb window holds all
    assert IM.auto_window(d, binsize=10_000) == 30_000_000
    with pytest.raises(ValueError):
        IM.auto_window(np.full(10, 20_000), binsize=10_000)


def test_rwr_dense_iterates_to_the_exact_solution():
    rng = np.random.default_rng(1)
    m = rng.poisson(0.4, (3, 25, 25)).astype(float)
    m = m + np.swapaxes(m, 1, 2)
    it = IM.rwr_dense(m, rp=0.5, tol=1e-12, max_iter=500)
    ex = IM.rwr_dense(m, rp=0.5, method="exact")
    assert np.allclose(it, ex, atol=1e-10)
    c = IM.convolve_maps(m, 1)
    assert c[0, 5, 5] == pytest.approx(m[0, 4:7, 4:7].mean())


def test_numpy_fallback_without_the_crate(monkeypatch):
    monkeypatch.setitem(sys.modules, "uchrom_maps", None)
    assert IM._maps_kernels("auto") is None
    with pytest.raises(ImportError, match="uchrom-maps"):
        IM._maps_kernels("native")
    with pytest.raises(ValueError, match="backend"):
        IM._maps_kernels("gpu")


@native
@pytest.mark.parametrize("window,step,D", [(0, 0, 40), (300, 150, 60), (400, 160, 120)])
def test_native_equals_numpy(window, step, D):
    n = 1100
    i, j = _cell(n, 1500, 3)
    a = IM.rwr_band(i, j, n, window=window, step=step, max_diag=D, backend="numpy")
    b = IM.rwr_band(i, j, n, window=window, step=step, max_diag=D, backend="native")
    assert np.array_equal(np.isnan(a), np.isnan(b))
    ok = np.isfinite(a)
    assert np.abs(a[ok] - b[ok]).max() <= 1e-11 * np.abs(a[ok]).max()
    za = IM.zscore_band(a, backend="numpy")
    zb = IM.zscore_band(b, backend="native")
    assert np.array_equal(np.isnan(za), np.isnan(zb))
    assert np.nanmax(np.abs(za - zb)) < 1e-9


@native
def test_native_rejects_bad_input():
    with pytest.raises(ValueError, match="outside"):
        IM.rwr_band([0], [50], 10, backend="native")
    with pytest.raises(ValueError, match="too small"):
        IM.rwr_band([0], [5], 100, window=20, step=10, max_diag=15, backend="native")


def _scool_cd(tmp_path, n_cells=6, n_bins=(120, 80)):
    cooler = pytest.importorskip("cooler")
    from uchrom import ChromData

    res = 10_000
    sizes = {"chr1": n_bins[0] * res, "chr2": n_bins[1] * res, "chrX": 30 * res}
    from uchrom.io.pairs_maps import genome_bins

    bins = genome_bins(sizes, res)
    first = {"chr1": 0, "chr2": n_bins[0], "chrX": n_bins[0] + n_bins[1]}
    maps, names = {}, [f"c{k}" for k in range(n_cells)]
    for k, name in enumerate(names):
        rows = []
        for c, nb in (("chr1", n_bins[0]), ("chr2", n_bins[1]), ("chrX", 30)):
            a, b = _cell(nb, 3 * nb, 10 * k + len(c))
            rows.append(pd.DataFrame({"bin1_id": a + first[c], "bin2_id": b + first[c], "count": 1}))
        maps[name] = pd.concat(rows).groupby(["bin1_id", "bin2_id"], as_index=False)["count"].sum()
    cooler.create_scool(str(tmp_path / "cells.scool"), bins, maps, ordered=True)
    no = pd.DataFrame({c: pd.Series(dtype=t) for c, t in [("chrom", str), ("start", np.int64), ("end", np.int64),
                                                          ("trace_id", str), ("cell_id", str)]})
    cd = ChromData(np.zeros((0, 3)), no, cells=pd.DataFrame(index=pd.Index(names, name="cell_id")))
    cd.link_scool(str(tmp_path / "cells.scool"), key="per_cell", bin_size=res)
    return cd, maps, first


def test_impute_maps_reads_the_linked_cells(tmp_path):
    cd, maps, first = _scool_cd(tmp_path)
    params = IM.ImputeParams(window=600_000, max_dist=150_000, normalize=False)
    got = list(IM.impute_maps(cd, cells=["c1", "c3"], params=params, backend="numpy"))
    assert [(c, ch) for c, ch, _ in got] == [("c1", "chr1"), ("c3", "chr1"), ("c1", "chr2"), ("c3", "chr2")]
    cell, chrom, band = got[2]
    px = maps["c1"]
    sel = (px["bin1_id"] >= first["chr2"]) & (px["bin1_id"] < first["chr2"] + 80)
    i = px["bin1_id"][sel].to_numpy() - first["chr2"]
    j = px["bin2_id"][sel].to_numpy() - first["chr2"]
    want = IM.rwr_band(i, j, 80, window=60, step=30, max_diag=15, backend="numpy")
    assert band.shape == (80, 16) and np.allclose(band, want, equal_nan=True)
    z = next(IM.impute_maps(cd, cells=["c0"], chrom="chr2", params=IM.ImputeParams(window=None, max_dist=100_000),
                            backend="numpy"))[2]
    assert np.isnan(z[:, 0]).all() and np.isfinite(z[10, 1:]).all()
