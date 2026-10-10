"""uchrom.spatial: neighbour graphs, Moran's I / Geary's C (against their definitions and the exact permutation
moments) and SPARK-X (against the R package's algorithm written out literally, and calibration under the null)."""

import numpy as np
import pandas as pd
import pytest
from scipy import stats

from uchrom import ChromData
from uchrom.spatial import (acat, by_adjust, coordinate_kernels, sparkx, spatial_autocorr, spatial_neighbors,
                            spatially_variable)


def _grid_cd(nx=12, ny=10, regions=("s1",), seed=0):
    """Spatial Hi-C-like spots on a barcode grid (no 3-D spots), positions in spot units, one frame per section."""
    rng = np.random.default_rng(seed)
    ids, xs, ys, rs = [], [], [], []
    for r in regions:
        for i in range(nx):
            for j in range(ny):
                ids.append(f"{r}_{i}_{j}")
                xs.append(i)
                ys.append(j)
                rs.append(r)
    cells = pd.DataFrame({"cell_id": ids, "section": rs})
    x, y = np.array(xs, float), np.array(ys, float)
    cells["gradient"] = x / nx + 0.1 * rng.normal(size=len(x))         # varies in space
    cells["noise"] = rng.normal(size=len(x))                          # does not
    cells["type"] = np.where(x < nx / 2, "A", "B")
    cells["by_type"] = (cells["type"] == "B") * 1.0 + 0.1 * rng.normal(size=len(x))
    spots = pd.DataFrame({"chrom": pd.Series([], dtype=str), "start": [], "end": [], "trace_id": []})
    cd = ChromData(coords=np.zeros((0, 3)), spots=spots, cells=cells)
    cd.set_cell_positions(np.c_[x, y], cell_ids=ids, unit="spot", frame="tissue", region_col="section")
    return cd


def test_neighbors_grid_regions():
    cd = _grid_cd(regions=("s1", "s2"))
    g4 = spatial_neighbors(cd, method="radius", radius=1.0)
    g8 = spatial_neighbors(cd, method="radius", radius=1.5)
    deg4, deg8 = g4.neighbour_counts(), g8.neighbour_counts()
    assert g4.n == 240 and deg4.max() == 4 and deg4.min() == 2 and deg8.max() == 8 and deg8.min() == 3
    assert (g4.adjacency != g4.adjacency.T).nnz == 0 and g4.adjacency.diagonal().sum() == 0
    reg = g4.regions
    i, j = g8.adjacency.nonzero()
    assert (reg[i] == reg[j]).all()                                  # no edges between sections
    gk = spatial_neighbors(cd, method="knn", n_neighbors=4)
    assert gk.neighbour_counts().min() >= 4
    gd = spatial_neighbors(cd, method="delaunay")
    assert gd.neighbour_counts().min() >= 2
    w = g8.weights("r")
    assert np.allclose(np.asarray(w.sum(axis=1)).ravel(), 1.0)
    sub = g8.subset(reg == "s1")
    assert sub.n == 120 and sub.adjacency.nnz == g8.adjacency.nnz // 2


def _moran_dense(x, W):
    z = x - x.mean()
    return len(x) / W.sum() * z @ W @ z / (z @ z)


def _geary_dense(x, W):
    n = len(x)
    z = x - x.mean()
    d = (x[:, None] - x[None, :]) ** 2
    return (n - 1) * (W * d).sum() / (2 * W.sum() * (z @ z))


@pytest.mark.parametrize("transform", ["r", "b"])
def test_moran_geary_definitions_and_permutation_moments(transform):
    cd = _grid_cd(nx=6, ny=5)
    g = spatial_neighbors(cd, method="radius", radius=1.5)
    W = g.weights(transform).toarray()
    rng = np.random.default_rng(1)
    x = rng.gamma(2.0, size=g.n) + np.arange(g.n) / g.n             # skewed (kurtosis matters for VI_rand)
    vals = pd.DataFrame({"x": x}, index=g.cell_ids.astype(str))
    mi = spatial_autocorr(values=vals, graph=g, transform=transform)
    gc = spatial_autocorr(values=vals, graph=g, method="geary", transform=transform)
    assert mi.loc["x", "I"] == pytest.approx(_moran_dense(x, W), rel=1e-12)
    assert gc.loc["x", "C"] == pytest.approx(_geary_dense(x, W), rel=1e-12)
    assert mi.loc["x", "expected"] == pytest.approx(-1 / (g.n - 1))
    # the randomisation moments are the exact moments of the permutation distribution
    perms = np.array([rng.permutation(x) for _ in range(20000)])
    pi = np.array([_moran_dense(p, W) for p in perms])
    pc = np.array([_geary_dense(p, W) for p in perms])
    assert pi.mean() == pytest.approx(-1 / (g.n - 1), abs=4 * pi.std() / np.sqrt(len(pi)))
    assert pi.var() == pytest.approx(mi.loc["x", "var_rand"], rel=0.04)
    assert pc.mean() == pytest.approx(1.0, abs=4 * pc.std() / np.sqrt(len(pc)))
    assert pc.var() == pytest.approx(gc.loc["x", "var_rand"], rel=0.04)


def test_autocorr_features_missing_and_permutations():
    cd = _grid_cd()
    g = spatial_neighbors(cd, method="radius", radius=1.5)
    res = spatial_autocorr(cd, ["gradient", "noise"], graph=g, n_perms=199, seed=3)
    assert res.loc["gradient", "pval"] < 0.01 and res.loc["gradient", "I"] > 0.5
    assert res.loc["noise", "pval"] > 0.01
    assert res.loc["gradient", "p_perm"] == pytest.approx(1 / 200)
    # missing values: the feature is tested on the cells that have it, over the restricted graph
    vals = cd.cells.set_index("cell_id")[["gradient"]].copy()
    vals.iloc[::3, 0] = np.nan
    a = spatial_autocorr(values=vals, graph=g)
    keep = np.isfinite(vals["gradient"].reindex(g.cell_ids.astype(str)).to_numpy())
    W = g.subset(keep).weights("r").toarray()
    assert a.loc["gradient", "n"] == keep.sum()
    assert a.loc["gradient", "I"] == pytest.approx(_moran_dense(vals["gradient"].dropna()
                                                                .reindex(g.cell_ids[keep].astype(str)).to_numpy(), W))


def _sparkx_r_literal(y, coords, X=None):
    """SPARK::sparkx.sk for one coordinate kernel, written out as the R code does it (stat, p via the
    eigenvalues of the kernel and chi-square — Davies' answer for equal weights)."""
    n = len(y)
    if X is None:
        Xi = coords - coords.mean(axis=0)
        loc_inv = np.linalg.inv(Xi.T @ Xi)
        klam = np.linalg.eigvals(Xi.T @ (Xi @ loc_inv)).real
        stat = (y @ Xi) @ loc_inv @ (Xi.T @ y) * n / (y @ y)
        lam = 1 - n * y.mean() ** 2 / (y @ y)
    else:
        xtx_inv = np.linalg.inv(X.T @ X)
        Xi = coords - (coords.T @ X @ xtx_inv @ X.T).T
        loc_inv = np.linalg.inv(Xi.T @ Xi)
        klam = np.linalg.eigvals(Xi.T @ (Xi @ loc_inv)).real
        gtx = y @ X
        lam = (y @ y - gtx @ xtx_inv @ gtx) / (y @ y)
        stat = (y @ Xi) @ loc_inv @ (Xi.T @ y) * n / (y @ y)
    assert np.allclose(klam, 1.0)
    return stat, stats.chi2.sf(stat / lam, len(klam))


def test_sparkx_matches_r_algorithm():
    rng = np.random.default_rng(5)
    n = 300
    xy = rng.uniform(0, 50, size=(n, 2))
    y = np.exp(-((xy[:, 0] - 25) ** 2) / 200) * 3 + rng.poisson(2, n)       # counts with a hot spot
    cov = np.c_[rng.normal(size=n), rng.integers(0, 2, n)]
    res = sparkx(pd.DataFrame({"y": y, "flat": rng.poisson(2, n).astype(float)}), xy)
    for name, S in coordinate_kernels(xy):
        stat, p = _sparkx_r_literal(y, S)
        assert res.loc["y", f"stat_{name}"] == pytest.approx(stat, rel=1e-10)
        assert res.loc["y", f"pval_{name}"] == pytest.approx(p, rel=1e-8)
    assert res.loc["y", "pval"] < 1e-6 and res.loc["flat", "pval"] > 1e-3
    # covariate path: the package's X_in with an intercept column
    X = np.c_[np.ones(n), cov]
    rc = sparkx(pd.DataFrame({"y": y}), xy, covariates=X, intercept=False)
    rc2 = sparkx(pd.DataFrame({"y": y}), xy, covariates=cov)
    for name, S in coordinate_kernels(xy):
        stat, p = _sparkx_r_literal(y, S, X)
        assert rc.loc["y", f"stat_{name}"] == pytest.approx(stat, rel=1e-10)
        assert rc.loc["y", f"pval_{name}"] == pytest.approx(p, rel=1e-8)
    assert rc2.loc["y", "pval"] == pytest.approx(rc.loc["y", "pval"], rel=1e-10)


def test_sparkx_calibrated_under_null():
    rng = np.random.default_rng(11)
    n, p = 400, 300
    xy = rng.uniform(0, 1, size=(n, 2))
    Y = rng.normal(size=(n, p))
    res = sparkx(Y, xy, kernels="single")
    assert stats.kstest(res["pval_projection"], "uniform").pvalue > 0.01
    res = sparkx(Y, xy)
    assert (res["pval"] < 0.05).mean() < 0.12                           # ACAT of dependent kernels: roughly
    assert (res["padj"] < 0.05).sum() == 0


def test_acat_and_by():
    p = np.array([[0.01, 0.2, 0.5], [1e-20, 0.5, 0.9], [0.0, 0.3, 0.4], [1.0, 0.1, 0.2]])
    c = acat(p)
    t = np.mean(np.tan((0.5 - p[0]) * np.pi))
    assert c[0] == pytest.approx(stats.cauchy.sf(t))
    assert c[1] < 1e-19 and c[2] == 0.0 and c[3] == 1.0
    q = np.array([0.01, 0.04, 0.03, 0.5, np.nan])
    adj = by_adjust(q)
    n = 4
    cn = sum(1 / i for i in range(1, n + 1))
    ref = np.minimum(1, np.minimum.accumulate((cn * n / np.arange(n, 0, -1) * np.sort(q[:4])[::-1])))[::-1]
    assert np.allclose(np.sort(adj[:4]), np.sort(ref)) and np.isnan(adj[4])


def test_spatially_variable_per_region_and_covariates():
    cd = _grid_cd(regions=("s1", "s2"))
    t = spatially_variable(cd, ["gradient", "noise", "by_type"])
    assert set(t["region"]) == {"s1", "s2"} and len(t) == 6
    sig = t.set_index(["region", "feature"])["padj"]
    assert sig[("s1", "gradient")] < 1e-6 and sig[("s2", "gradient")] < 1e-6
    assert sig[("s1", "noise")] > 0.05
    assert sig[("s1", "by_type")] < 1e-6
    # adjusted for the cell type, the feature that only follows the type no longer varies in space
    adj = spatially_variable(cd, ["by_type", "gradient"], covariates=["type"], key_added="sv.adjusted")
    a = adj.set_index(["region", "feature"])["padj"]
    assert a[("s1", "by_type")] > 0.05 and a[("s1", "gradient")] < 1e-3
    assert "sv.adjusted" in cd.results and cd.results.record("sv.adjusted").params["covariates"] == ["type_B"]
    m = spatially_variable(cd, ["gradient"], method="moran", graph_kwargs={"method": "radius", "radius": 1.5},
                           key_added=None)
    assert (m["pval"] < 1e-6).all() and "spatially_variable.moran" not in cd.results


def test_destripe_removes_channel_offsets_keeps_anatomy():
    from uchrom.spatial import destripe, smooth_basis, smooth_share

    rng = np.random.default_rng(2)
    nx, ny = 60, 50
    x, y = np.meshgrid(np.arange(nx), np.arange(ny), indexing="ij")
    x, y = x.ravel(), y.ravel()
    anatomy = np.sin(x / 8.0) + 0.5 * (y / ny) ** 2 + np.exp(-((x - 20) ** 2 + (y - 30) ** 2) / 50)
    row_off, col_off = rng.normal(0, 0.3, ny), rng.normal(0, 0.3, nx)
    v = anatomy + row_off[y] + col_off[x] + rng.normal(0, 0.05, len(x))
    d = destripe(v, rows=y, cols=x)
    S = smooth_basis(np.c_[x, y])

    def rough(u):                       # what a smooth surface does not carry: stripes and noise
        b, *_ = np.linalg.lstsq(S, u, rcond=None)
        return u - S @ b

    assert np.std(rough(v - anatomy)) > 0.3                   # stripes before
    assert np.std(rough(d - anatomy)) < 0.06                  # noise after
    assert np.corrcoef(d, anatomy)[0, 1] > max(0.9, np.corrcoef(v, anatomy)[0, 1])   # slow drift stays
    assert smooth_share(d, np.c_[x, y])[0] > smooth_share(v, np.c_[x, y])[0]
    # a DataFrame with a missing value, two arrays; an unstriped feature is left as it is
    df = pd.DataFrame({"a": v, "b": anatomy})
    df.iloc[5, 0] = np.nan
    out = destripe(df, rows=y, cols=x, regions=np.where(np.arange(len(x)) < 1500, "s1", "s2"))
    assert np.isnan(out.iloc[5, 0]) and np.abs(out["b"] - anatomy).max() < 0.02
