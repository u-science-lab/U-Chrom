"""Population distance features and ArcFISH axis-variance cube."""
import numpy as np
import pandas as pd
import pytest


def _straight_traces(n_traces=5, n_bins=6):
    """Every trace is the x-axis at unit spacing → |i-j| distances."""
    from uchrom import ChromData

    rows, coords = [], []
    for t in range(n_traces):
        for k in range(n_bins):
            rows.append(("chr1", k * 1000, (k + 1) * 1000, t))
            coords.append((k, 0.0, 0.0))
    spots = pd.DataFrame(rows, columns=["chrom", "start", "end", "trace_id"])
    return ChromData(np.array(coords, float), spots)


def test_mean_distance_matrix_exact():
    from uchrom.fea import mean_distance_matrix

    cd = _straight_traces()
    M, bins, n = mean_distance_matrix(cd.to_dataframe(), chrom="chr1")
    idx = np.arange(6)
    assert n == 5 and len(bins) == 6
    assert np.allclose(M, np.abs(idx[:, None] - idx[None, :]))


def test_mean_distance_matrix_ignores_missing_spots():
    from uchrom.fea import mean_distance_matrix

    cd = _straight_traces()
    cd.coords[3] = np.nan          # trace 0, bin 3 missing
    M, _, _ = mean_distance_matrix(cd.to_dataframe(), chrom="chr1", reduce="mean")
    assert np.isfinite(M).all()
    assert M[0, 3] == pytest.approx(3.0)


def test_contact_frequency_and_rg():
    from uchrom.fea import contact_frequency, radius_of_gyration

    cd = _straight_traces()
    df = cd.to_dataframe()
    out = contact_frequency(df, threshold=1.5, chrom="chr1")
    F = out[0] if isinstance(out, tuple) else out
    assert F[0, 1] == pytest.approx(1.0) and F[0, 2] == pytest.approx(0.0)
    rg = radius_of_gyration(df, chrom="chr1")
    expected = np.sqrt(np.mean((np.arange(6) - 2.5) ** 2))
    assert np.allclose(rg.to_numpy(), expected)


def test_axis_variance_cube_shapes_and_values():
    from uchrom.fea import axis_variance_cube

    rng = np.random.default_rng(0)
    cd = _straight_traces(n_traces=30)
    cd.coords[:, 1] += rng.normal(0, 1.0, cd.n_spots)   # y noise only
    out = axis_variance_cube(cd, "chr1", device="cpu")
    var = out["var"].cpu().numpy() if hasattr(out["var"], "cpu") else out["var"]
    assert var.shape == (3, 6, 6)
    off = ~np.eye(6, dtype=bool)
    assert np.allclose(var[0][off], 0, atol=1e-8)      # x: deterministic
    assert np.allclose(var[2][off], 0, atol=1e-8)      # z: zero
    assert (var[1][off] > 0.5).all()                   # y: var(a-b) ≈ 2
