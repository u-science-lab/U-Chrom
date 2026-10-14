"""The tracing callers' kernels against plain reference implementations: the ArcFISH boundary and loop tests
against a pair-by-pair (B x B mask) reading of the published definitions, FISHnet's box-car mean against its former
Python loop, and the per-arm compartment call."""

import numpy as np
import pandas as pd
import pytest

from tests._synth import RES, domain_traces


# ---------------------------------------------------------------- former implementations (references)

def _boundary_stats_reference(norm_var, count, starts, w, window):
    """ArcFISH's boundary test read pair by pair (``uchrom.strc.tad.arc_pval`` module docstring)."""
    from scipy import stats

    B = len(starts)
    stat, pval = np.full(B, np.nan), np.full(B, np.nan)
    for i in range(B):
        if starts[i] - starts[0] < window / 2 or starts[-1] - starts[i] < window / 2:
            continue
        L = [k for k in range(i) if abs(starts[k] - starts[i]) <= window]
        R = [k for k in range(i + 1, B) if abs(starts[k] - starts[i]) <= window]
        intra = [(k, l) for grp in (L, R) for k in grp for l in grp if k < l]
        inter = [(k, l) for k in L for l in R]
        p = np.empty(3)
        for a in range(3):
            ci = sum(count[a, k, l] for k, l in intra)
            co = sum(count[a, k, l] for k, l in inter)
            vi = sum(count[a, k, l] * norm_var[a, k, l] for k, l in intra if np.isfinite(norm_var[a, k, l]))
            vo = sum(count[a, k, l] * norm_var[a, k, l] for k, l in inter if np.isfinite(norm_var[a, k, l]))
            with np.errstate(invalid="ignore", divide="ignore"):
                p[a] = stats.f.cdf((vi / ci) / (vo / co), ci, co)
        stat[i] = np.sum(w * np.tan((0.5 - p) * np.pi))
        pval[i] = 1 - stats.cauchy.cdf(stat[i])
    return stat, pval


def _loop_background_reference(starts, i, j, inner, outer):
    """ArcFISH's local background of the pair (i, j), as a B x B mask."""
    B = len(starts)
    m = np.zeros((B, B), bool)
    for k in range(B):
        for l in range(B):
            dk, dl = abs(starts[k] - starts[i]), abs(starts[l] - starts[j])
            m[k, l] = dk <= outer and dl <= outer and not (dk <= inner and dl <= inner) and k != i and l != j and k < l
    return m


def _boxcar_former(mat, window):
    n = mat.shape[0]
    out = np.zeros_like(mat, dtype=np.float64)
    for i in range(n):
        lf, uf = max(0, i - window), min(n, i + window)
        for j in range(n):
            ls, us = max(0, j - window), min(n, j + window)
            block = mat[lf:uf, ls:us]
            with np.errstate(invalid="ignore"):
                out[i, j] = np.nan if block.size == 0 else np.nanmean(block)
    return np.nan_to_num(out, nan=0.0)


def _cube(rng, B):
    v = rng.gamma(2.0, 0.5, (3, B, B))
    v = (v + v.transpose(0, 2, 1)) / 2
    v[:, rng.random((B, B)) < 0.05] = np.nan
    c = rng.integers(0, 30, (3, B, B))
    return v, c


# ---------------------------------------------------------------- tests

@pytest.mark.parametrize("window_bp", [6e4, 1.5e5, 3e5])
def test_boundary_statistics_equal_reference(window_bp):
    from uchrom.strc.tad.arc_pval import boundary_statistics

    rng = np.random.default_rng(1)
    B = 40
    v, c = _cube(rng, B)
    starts = np.arange(B) * RES
    starts[25:] += RES                                  # a gap: uneven loci
    w = np.array([0.4, 0.35, 0.25])
    got = boundary_statistics(v, c, starts, w, window_bp)
    stat, pval = _boundary_stats_reference(v, c, starts, w, window_bp)
    assert np.isfinite(got["stat"]).sum() > 10
    np.testing.assert_allclose(got["stat"], stat, rtol=1e-10, atol=0, equal_nan=True)
    np.testing.assert_allclose(got["pval"], pval, rtol=1e-10, atol=0, equal_nan=True)


def test_loop_tests_equal_reference():
    from scipy import stats

    from uchrom.strc.loop.axiswise_f import LoopCallerParams, loop_tests

    rng = np.random.default_rng(2)
    B = 30
    v, c = _cube(rng, B)
    starts = np.arange(B) * 25_000
    starts[18:] += 25_000
    w = np.array([0.4, 0.35, 0.25])
    p = LoopCallerParams()
    got = loop_tests(v, c, starts, w, p)
    n_tested = 0
    for i in range(B):
        for j in range(i + 1, B):
            if not (p.cut_lo <= starts[j] - starts[i] <= p.cut_up):
                assert np.isnan(got["pval"][i, j])
                continue
            m = _loop_background_reference(starts, i, j, p.inner_cut, p.outer_cut)
            if m.sum() <= 3:
                assert np.isnan(got["axis_pval"][:, i, j]).all()
                continue
            n_tested += 1
            for a in range(3):
                n_bg = c[a][m].sum()
                den = np.nansum(c[a][m] / n_bg * v[a][m])
                ref = stats.f.cdf(v[a, i, j] / den, c[a, i, j], n_bg)
                np.testing.assert_allclose(got["axis_pval"][a, i, j], ref, rtol=1e-12, equal_nan=True)
                assert got["axis_pval"][a, j, i] == got["axis_pval"][a, i, j] or np.isnan(ref)
    assert n_tested > 50


@pytest.mark.parametrize("window", [1, 2, 3])
def test_boxcar_equal_former(window):
    from uchrom.strc.tad.fishnet import _boxcar_nanmean

    rng = np.random.default_rng(3)
    binary = (rng.random((37, 37)) < 0.4).astype(float)
    assert np.array_equal(_boxcar_nanmean(binary, window), _boxcar_former(binary, window))
    floats = rng.normal(size=(23, 23))
    floats[rng.random((23, 23)) < 0.3] = np.nan
    floats[:, 5] = np.nan
    np.testing.assert_allclose(_boxcar_nanmean(floats, window), _boxcar_former(floats, window), rtol=1e-12,
                               atol=1e-14)


def test_fishnet_chromosome_of_a_larger_object():
    """The per-chromosome kernel reads only its chromosome: two chromosomes together give the rows each
    gives alone."""
    from chromdata import ChromData

    from uchrom.strc.tad import FISHnetParams, call_domains_fishnet

    a = domain_traces(n_traces=2, bounds=(0, 12, 24, 36), seed=4)
    b = domain_traces(n_traces=2, bounds=(0, 10, 25), seed=5)
    spots_b = b.spots_with_loci().assign(chrom="chr2", trace_id=lambda d: d["trace_id"].astype(str) + "b")
    both = ChromData(np.concatenate([a.coords, b.coords]),
                     pd.concat([a.spots_with_loci()[["chrom", "start", "end", "trace_id"]].astype({"trace_id": str}),
                                spots_b[["chrom", "start", "end", "trace_id"]]], ignore_index=True))
    params = FISHnetParams(n_louvain_runs=2, max_thresholds=15)
    together = call_domains_fishnet(both, params=params, key_added=None)
    alone = call_domains_fishnet(a, chrom="chr1", params=params, key_added=None)
    t1 = together[together["chrom"] == "chr1"].reset_index(drop=True)
    pd.testing.assert_frame_equal(t1[["start", "end", "start_bin", "end_bin"]].astype("int64"),
                                  alone[["start", "end", "start_bin", "end_bin"]].astype("int64"))



def test_axes_pc_per_arm_uses_the_whole_chromosome_normalisation():
    """``centromeres=`` follows the authors' per-arm call: the normalised variances of the whole chromosome, the
    p arm the loci ending at or before the centromere, each arm's eigenvectors from its block of that matrix and its
    own axis weights."""
    from chromdata import ChromData

    from tests._synth import chain_traces
    from uchrom.fea.arc import _axis_weight_cube, _coord_cube_for_chrom, axis_variance_cube, filter_normalize
    from uchrom.strc.comp import call_compartments_axes_pc

    n, cen = 40, 20
    a_mask = np.zeros(n, bool)
    a_mask[[2, 3, 4, 10, 11, 12, 22, 23, 24, 30, 31, 32]] = True
    base = chain_traces(n_traces=120, n_bins=n, a_mask=a_mask, seed=7)
    loci = base.spots_with_loci()[["chrom", "start", "end", "trace_id"]]
    q = (loci["start"] >= cen * RES).to_numpy()
    xyz = np.asarray(base.coords).copy()
    xyz[q] += np.array([40.0, 0.0, 0.0])                             # the q arm far from the p arm
    cd = ChromData(xyz, loci)
    arms = call_compartments_axes_pc(cd, chrom="chr1", device="cpu", key_added=None,
                                     centromeres={"chr1": cen * RES})
    assert list(arms["region"].unique()) == ["chr1_p", "chr1_q"]
    assert list(arms["bin_index"]) == list(range(n))
    assert (arms.loc[arms["region"] == "chr1_p", "end"] <= cen * RES).all()
    assert (arms.loc[arms["region"] == "chr1_q", "end"] > cen * RES).all()

    nv = filter_normalize(axis_variance_cube(cd, "chr1", device="cpu"))["norm_var"]
    nv = np.where(np.isnan(nv), 1.0, nv)
    coords, bin_ids, _ = _coord_cube_for_chrom(cd, "chr1")
    ends = np.array([e for _, e in bin_ids])
    for region, idx in (("chr1_p", np.flatnonzero(ends <= cen * RES)), ("chr1_q", np.flatnonzero(ends > cen * RES))):
        V = np.linalg.eigh(np.exp(-nv[:, idx][:, :, idx]))[1][:, :, -2]
        got = arms[arms["region"] == region]
        for a, c in enumerate("xyz"):
            r = np.corrcoef(got[f"eig_{c}"].to_numpy(), V[a])[0, 1]
            assert abs(abs(r) - 1) < 1e-10, (region, c, r)
        assert np.isfinite(_axis_weight_cube(coords[:, idx])).all()
    # an arm of fewer than 2 loci: the whole chromosome, with a warning
    with pytest.warns(UserWarning, match="centromere"):
        whole = call_compartments_axes_pc(cd, chrom="chr1", device="cpu", key_added=None,
                                          centromeres={"chr1": int(ends[0])})
    assert set(whole["region"]) == {"chr1"}
