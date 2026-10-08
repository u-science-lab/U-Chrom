"""The tracing callers' kernels after the changes that let them run on whole chromosomes of reconstructed
structures (thousands of bins): every changed kernel gives what the former (B x B mask / Python loop)
implementation gave, kept here as the reference."""

import numpy as np
import pandas as pd
import pytest

from tests._synth import RES, domain_traces


# ---------------------------------------------------------------- former implementations (references)

def _boundary_pvals_former(norm_var, count, mids, axis_weights, window_bp):
    from scipy.stats import f as f_dist

    from uchrom.utils.stats import cauchy_combination

    B = len(mids)
    pvals = np.full(B, np.nan)
    per_axis = np.zeros((3, B))
    half = 0.5 * window_bp
    w_var = np.where(np.isfinite(norm_var), norm_var * count, 0.0)
    w_cnt = np.where(np.isfinite(norm_var), count, 0.0)
    for b in range(B):
        lm = (mids >= mids[b] - half) & (mids < mids[b])
        rm = (mids > mids[b]) & (mids <= mids[b] + half)
        if lm.sum() < 1 or rm.sum() < 1:
            continue
        li, ri = np.where(lm)[0], np.where(rm)[0]
        intra = np.zeros((B, B), bool)
        inter = np.zeros((B, B), bool)
        for group in (li, ri):
            for i in group:
                for j in group:
                    if i < j:
                        intra[i, j] = True
        for i in li:
            for j in ri:
                if i < j:
                    inter[i, j] = True
        logp = np.zeros(3)
        ok = True
        for ax in range(3):
            vi, ci = w_var[ax][intra].sum(), w_cnt[ax][intra].sum()
            vo, co = w_var[ax][inter].sum(), w_cnt[ax][inter].sum()
            if ci <= 0 or co <= 0 or vi / ci <= 0 or vo / co <= 0:
                ok = False
                break
            logp[ax] = f_dist.logcdf((vi / ci) / (vo / co), dfn=max(ci, 1.0), dfd=max(co, 1.0))
        if not ok:
            continue
        per_axis[:, b] = logp
        p = np.clip(np.exp(logp), 1e-300, 1 - 1e-15)
        pvals[b] = float(cauchy_combination(p[None, :], weights=axis_weights, axis=1)[0])
    return pvals, per_axis


def _ring_former(v, c, i, j, inner, outer):
    B = v.shape[0]
    mask = np.zeros((B, B), bool)
    mask[max(0, i - outer):min(B, i + outer + 1), max(0, j - outer):min(B, j + outer + 1)] = True
    mask[max(0, i - inner):min(B, i + inner + 1), max(0, j - inner):min(B, j + inner + 1)] = False
    mask[i, :] = False
    mask[:, j] = False
    vals, cnts = v[mask], c[mask]
    fin = np.isfinite(vals) & (cnts > 0)
    if not fin.any():
        return np.nan, 0
    w = cnts[fin].astype(np.float64)
    return float((w * vals[fin]).sum() / w.sum()), float(w.sum())


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
def test_boundary_pvals_equal_former(window_bp):
    from uchrom.fea.arc import axis_weight  # noqa: F401  (the module the caller imports)
    from uchrom.strc.tad.arc_pval import _boundary_pvals

    rng = np.random.default_rng(1)
    B = 40
    v, c = _cube(rng, B)
    mids = (np.arange(B) + 0.5) * RES
    mids[25:] += RES                                    # a gap: uneven loci
    w = np.array([0.4, 0.35, 0.25])
    p_new, lp_new = _boundary_pvals(v, c, mids, w, window_bp)
    p_old, lp_old = _boundary_pvals_former(v, c, mids, w, window_bp)
    assert np.array_equal(np.isnan(p_new), np.isnan(p_old))
    np.testing.assert_allclose(p_new, p_old, rtol=1e-10, atol=0, equal_nan=True)
    np.testing.assert_allclose(lp_new, lp_old, rtol=1e-10, atol=1e-300)


def test_background_ring_equal_former():
    from uchrom.strc.loop.axiswise_f import _background_ring

    rng = np.random.default_rng(2)
    B = 30
    v, c = _cube(rng, B)
    for i in range(B):
        for j in range(i + 1, B):
            for inner, outer in ((1, 2), (1, 3), (2, 4)):
                assert _background_ring(v[0], c[0], i, j, inner, outer) == _ring_former(v[0], c[0], i, j, inner, outer)


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



def test_axes_pc_per_arm_equals_each_arm_alone():
    """``centromeres=``: each arm is called as if it were its own chromosome (the q arm's ``bin_index``
    continues the p arm's)."""
    from chromdata import ChromData

    from tests._synth import chain_traces
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
    for region, mask in (("chr1_p", ~q), ("chr1_q", q)):
        alone = call_compartments_axes_pc(cd[mask], chrom="chr1", device="cpu", key_added=None)
        got = arms[arms["region"] == region]
        np.testing.assert_allclose(got["pc2"].to_numpy(), alone["pc2"].to_numpy())
        assert list(got["compartment"]) == list(alone["compartment"])
