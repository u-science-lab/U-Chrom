"""uchrom.strc.tad.insulation: diamond insulation score, boundaries (cooltools definitions), domains."""

import warnings

import numpy as np
import pandas as pd
import pytest

from tests import FIXTURES

cooler = pytest.importorskip("cooler")

RES = 10_000
BOUNDS = (0, 30, 55, 90, 120)          # planted domains (bin indices)


def _planted(n_bounds=BOUNDS, *, scale=200.0, fold=3.0, seed=0, masked=(), chroms=("chr1",)):
    """Pixels of TAD-like maps: contacts ~ scale / (1 + d), x ``fold`` inside a domain; ``masked`` bins empty."""
    rng = np.random.default_rng(seed)
    n = n_bounds[-1]
    dom = np.searchsorted(np.asarray(n_bounds), np.arange(n), side="right")
    i, j = np.triu_indices(n)
    lam = scale / (1.0 + (j - i)) * np.where(dom[i] == dom[j], fold, 1.0)
    bins, pix = [], []
    for k, c in enumerate(chroms):
        cnt = rng.poisson(lam)
        bad = np.isin(i, masked) | np.isin(j, masked)
        cnt[bad] = 0
        keep = cnt > 0
        bins.append(pd.DataFrame({"chrom": c, "start": np.arange(n) * RES, "end": np.arange(1, n + 1) * RES}))
        pix.append(pd.DataFrame({"bin1_id": i[keep] + k * n, "bin2_id": j[keep] + k * n, "count": cnt[keep]}))
    return pd.concat(bins, ignore_index=True), pd.concat(pix, ignore_index=True)


def _cool(tmp_path, bins, pix, name="m.cool", balance=True):
    path = tmp_path / name
    cooler.create_cooler(str(path), bins, pix, ordered=True)
    if balance:
        cooler.balance_cooler(cooler.Cooler(str(path)), store=True)
    return path


def _brute_log2(M, w, ig):
    """cooltools' dense definition: nanmean of the w x w diamond (masked bins NaN, |i - j| < ig NaN),
    / nanmedian, log2."""
    M = M.copy()
    n = len(M)
    k = np.abs(np.subtract.outer(np.arange(n), np.arange(n)))
    M[k < ig] = np.nan
    s = np.full(n, np.nan)
    with warnings.catch_warnings(action="ignore"):
        for b in range(n):
            blk = M[max(0, b - w + 1): b + 1, b: min(n, b + w)]
            s[b] = np.nanmean(blk) if np.isfinite(blk).any() else np.nan
        s = s / np.nanmedian(s)
        s[s == 0] = np.nan
        return np.log2(s)


def _ref_prominence(arr):
    """cooltools ``find_peak_prominence`` (the published loops), for checking the vectorised version."""
    arr = np.asarray(arr, float)
    n = len(arr)
    ok = ~np.isnan(arr)
    x, idx = arr[ok], np.arange(n)[ok]
    with warnings.catch_warnings(action="ignore"):
        lmax = idx[np.flatnonzero(np.r_[False, x[:-1] < x[1:]] & np.r_[x[:-1] > x[1:], False])]
        lmin = idx[np.flatnonzero(np.r_[False, x[:-1] > x[1:]] & np.r_[x[:-1] < x[1:], False])]
        proms = []
        left, right = [], []
        for p in lmax:
            lm = next((j for j in range(p - 1, -1, -1) if arr[j] > arr[p]), -1)
            rm = next((j for j in range(p + 1, n) if arr[j] > arr[p]), -1)
            left.append(lm)
            right.append(rm)
            lp = arr[p] - np.nanmin(arr[lm:p]) if lm >= 0 else np.nan
            rp = arr[p] - np.nanmin(arr[p:rm]) if rm >= 0 else np.nan
            proms.append(np.nanmin([lp, rp]))
        proms = np.array(proms)
        top = [k for k in range(len(lmax)) if left[k] == -1 and right[k] == -1]
        if top:
            proms[top[0]] = arr[lmax[top[0]]] - (np.nanmin(arr[lmin]) if len(lmin) else np.nanmin(arr))
    out = np.full(n, np.nan)
    out[lmax] = proms
    return out


# ------------------------------------------------------------------------------------------------ kernels

def test_n_valid_pixels_and_diamond_sums_match_brute_force():
    from uchrom.strc.tad.insulation import diamond_sums, full_diamond, n_valid_pixels

    rng = np.random.default_rng(1)
    n = 40
    A = rng.gamma(2.0, 1.0, (n, n))
    A = np.triu(A) + np.triu(A, 1).T
    A[rng.random((n, n)) < 0.2] = 0.0                       # unstored pixels
    A = np.triu(A) + np.triu(A, 1).T
    valid = np.ones(n, bool)
    valid[[0, 7, 8, 20, 39]] = False
    M = A.copy()
    M[~valid] = np.nan
    M[:, ~valid] = np.nan
    i, j = np.nonzero(np.triu(A) > 0)
    v = M[i, j]
    for w in (1, 3, 6):
        for ig in (0, 2, 3):
            nv = n_valid_pixels(valid, w, ig)
            sums, nnz = diamond_sums(i, j, v, n, w, ig, chunk=17)      # small chunks
            for b in range(n):
                rows = np.arange(max(0, b - w + 1), b + 1)
                cols = np.arange(b, min(n, b + w))
                R, C = np.meshgrid(rows, cols, indexing="ij")
                keep = (C - R) >= ig
                blk = M[R[keep], C[keep]]
                assert nv[b] == np.isfinite(blk).sum()
                assert sums[b] == pytest.approx(np.nansum(blk), abs=1e-12)
            assert nv.max() <= full_diamond(w, ig)
    assert full_diamond(10, 2) == 97 and full_diamond(10, 0) == 100 and full_diamond(2, 5) == 0


def test_boundary_strength_matches_the_published_loops():
    from uchrom.strc.tad.insulation import boundary_strength

    rng = np.random.default_rng(3)
    for trial in range(20):
        x = np.cumsum(rng.normal(size=300))
        x[rng.random(300) < 0.05] = np.nan
        got = boundary_strength(x)
        ref = _ref_prominence(-x)
        np.testing.assert_allclose(got, ref, equal_nan=True, atol=1e-12)
    assert np.isnan(boundary_strength(np.array([1.0, 2.0]))).all()


def test_thresholds_match_skimage_values():
    from uchrom.strc.tad.insulation import threshold_li, threshold_otsu

    rng = np.random.default_rng(7)
    x = np.r_[rng.exponential(0.2, 400), rng.normal(1.5, 0.3, 60)]
    # skimage 0.26 threshold_li / threshold_otsu on the same values (cooltools uses them)
    assert threshold_li(x) == pytest.approx(0.5208323319552504, rel=1e-12)
    assert threshold_otsu(x) == pytest.approx(0.7822330035039697, rel=1e-12)
    assert threshold_li(np.r_[x, np.nan]) == pytest.approx(threshold_li(x))
    assert threshold_li(np.array([0.5, 0.5])) == 0.5 and np.isnan(threshold_li(np.array([np.nan])))


# ------------------------------------------------------------------------------------------------ maps

def test_insulation_score_equals_the_dense_definition(tmp_path):
    from uchrom.strc.tad.insulation import InsulationParams, insulation_score

    bins, pix = _planted(masked=(60, 61, 62))
    path = _cool(tmp_path, bins, pix)
    clr = cooler.Cooler(str(path))
    M = clr.matrix(balance=True)[:]
    tab = insulation_score(str(path), windows=[30_000, 80_000])
    assert tab["is_bad_bin"].to_numpy()[[60, 61, 62]].all()
    for w in (3, 8):
        ref = _brute_log2(M, w, 2)                                   # ignore_diags = 2 (balancing attrs)
        np.testing.assert_allclose(tab[f"log2_insulation_score_{w * RES}"], ref, atol=1e-10, equal_nan=True)
    raw = insulation_score(str(path), windows=30_000, params=InsulationParams(balance=False, ignore_diags=0))
    R = clr.matrix(balance=False)[:].astype(float)
    np.testing.assert_allclose(raw["log2_insulation_score_30000"], _brute_log2(R, 3, 0), atol=1e-10, equal_nan=True)
    near = insulation_score(str(path), windows=30_000, params=InsulationParams(min_dist_bad_bin=2))
    s = near["log2_insulation_score_30000"].to_numpy()
    assert np.isnan(s[[59, 63]]).all() and np.isfinite(s[[58, 64]]).all()
    with pytest.raises(ValueError, match="multiple of the bin size"):
        insulation_score(str(path), windows=25_000)


def test_planted_boundaries_and_domains(tmp_path):
    from uchrom import ChromData
    from uchrom.strc.tad import compare_boundaries, tad_boundaries
    from uchrom.strc.tad.insulation import InsulationParams, call_tads_insulation

    bins, pix = _planted()
    path = _cool(tmp_path, bins, pix)
    n = BOUNDS[-1]
    spots = pd.DataFrame({"chrom": "chr1", "start": np.arange(n) * RES, "end": np.arange(1, n + 1) * RES,
                          "trace_id": 0})
    cd = ChromData(np.zeros((n, 3)), spots)
    cd.link_cool(str(path), key="hic")
    dom = call_tads_insulation(cd, params=InsulationParams(window_bp=50_000))
    b = cd.results["tads.insulation.boundaries"]
    called = sorted(b["bin_index"])
    # every planted boundary, nothing else; a boundary between bins k-1 | k is equally insulated at both
    assert len(called) == 3 and all(abs(c - t) <= 1 for c, t in zip(called, BOUNDS[1:-1]))
    assert list(dom.columns) == ["chrom", "start", "end", "start_bin", "end_bin"]
    assert list(zip(dom.start_bin, dom.end_bin))[1:-1] == [(called[0], called[1]), (called[1], called[2])]
    assert dom.start_bin.iat[0] < called[0] and dom.end_bin.iat[-1] > called[-1]
    assert (dom.start.to_numpy() == dom.start_bin.to_numpy() * RES).all()
    # the boundaries of the domain table are the called ones; the call agrees with itself
    assert tad_boundaries(cd, "tads.insulation")["bin_index"].tolist() == called
    assert compare_boundaries(cd, "tads.insulation", "tads.insulation")["fraction_near"] == 1.0
    assert cd.intervals["tads.insulation"].kind == "domain"
    assert cd.intervals["tads.insulation.boundaries"].kind == "peak"
    rec = cd.results.record("tads.insulation")
    assert rec.function == "uchrom.strc.tad.call_tads_insulation"
    assert rec.inputs["contacts"] == "hic" and rec.inputs["window_bins"] == 5 and rec.inputs["ignore_diags"] == 2
    assert rec.params["window_bp"] == 50_000 and rec.params["threshold"] == "li"
    score = cd.results["tads.insulation.score"]
    assert len(score) == n and "log2_insulation_score_50000" in score
    # default window: 100 kb (10 bins here), at least 3 bins
    from types import SimpleNamespace

    from uchrom.strc.tad.insulation import _window_bins

    other = call_tads_insulation(cd, copy=True)
    assert other.results.record("tads.insulation").inputs["window_bins"] == 10
    assert cd.results.record("tads.insulation").params["window_bp"] == 50_000
    assert _window_bins(SimpleNamespace(binsize=5_000), [], None) == (100_000, 20)
    assert _window_bins(SimpleNamespace(binsize=25_000), [], None) == (100_000, 4)
    assert _window_bins(SimpleNamespace(binsize=50_000), [], None) == (150_000, 3)


def test_domains_do_not_span_masked_stretches(tmp_path):
    from uchrom.strc.tad.insulation import InsulationParams, call_tads_insulation

    bounds = (0, 30, 60, 100, 130, 160)
    masked = tuple(range(70, 86))                                  # 16 empty bins inside the third domain
    bins, pix = _planted(bounds, masked=masked)
    path = _cool(tmp_path, bins, pix)
    dom = call_tads_insulation(str(path), params=InsulationParams(window_bp=50_000))
    spans = list(zip(dom.start_bin, dom.end_bin))
    assert not any(s < 70 and e > 85 for s, e in spans)
    # the planted boundaries 30, 60, 100, 130 are called; the stretch 60-100 holds the gap: no domain there
    inner = spans[1:-1]
    assert len(inner) == 2 and all(abs(a - x) <= 1 and abs(b - y) <= 1
                                   for (a, b), (x, y) in zip(inner, [(30, 60), (100, 130)]))


def test_convention_chroms_copy_and_loci_tracks(tmp_path):
    from uchrom import ChromData
    from uchrom.strc.tad.insulation import InsulationParams, call_tads_insulation, insulation_score

    bins, pix = _planted(chroms=("chr1", "chr2"))
    path = _cool(tmp_path, bins, pix)
    n = BOUNDS[-1]
    spots = pd.DataFrame({"chrom": "chr2", "start": np.arange(n) * RES, "end": np.arange(1, n + 1) * RES,
                          "trace_id": 0})
    cd = ChromData(np.zeros((n, 3)), spots)
    cd.link_cool(str(path), key="hic")
    p = InsulationParams(window_bp=50_000)
    only2 = call_tads_insulation(cd, params=p, key_added=None)             # chrom=None: the chromosomes of cd
    assert set(only2.chrom) == {"chr2"}
    both = call_tads_insulation(cd, chrom=["chr1", "chr2"], params=p, key_added=None)
    one = call_tads_insulation(cd, chrom="chr1", params=p, key_added=None)
    assert set(both.chrom) == {"chr1", "chr2"} and len(one) > 0
    new = call_tads_insulation(cd, params=p, copy=True)
    assert "tads.insulation" in new.results and "tads.insulation" not in cd.results
    tab = insulation_score(cd, windows=[50_000, 100_000])
    assert list(tab.columns[:5]) == ["chrom", "start", "end", "bin_index", "is_bad_bin"]
    assert {"is_boundary_50000", "boundary_strength_100000", "n_valid_pixels_50000"} <= set(tab.columns)
    track = cd.bin_tracks["insulation.log2_50000"].to_numpy()
    np.testing.assert_allclose(track, tab.loc[tab.chrom == "chr2", "log2_insulation_score_50000"], equal_nan=True)
    assert cd.results.record("insulation").inputs["windows_bins"] == [5, 10]
    with pytest.raises(ValueError, match="not in the map"):
        insulation_score(cd, chrom="chrX")


def test_variable_size_bins_use_the_median_bin(tmp_path):
    from uchrom.strc.tad.insulation import insulation_score

    bins, pix = _planted()
    fixed = _cool(tmp_path, bins, pix, "fixed.cool")
    var = bins.copy()
    edges = np.r_[0, np.cumsum(np.where(np.arange(len(bins)) % 10 == 0, 15_000, RES))]
    var["start"], var["end"] = edges[:-1], edges[1:]
    varp = _cool(tmp_path, var, pix, "var.cool")
    assert cooler.Cooler(str(varp)).binsize is None
    a = insulation_score(str(fixed), windows=50_000)
    b = insulation_score(str(varp), windows=50_000)                 # median bin 10 kb -> 5 bins
    np.testing.assert_allclose(a["log2_insulation_score_50000"], b["log2_insulation_score_50000"], equal_nan=True)


@pytest.mark.skipif(not (FIXTURES / "K562_chr21_30kb.cool").exists(), reason="K562 fixture missing")
def test_real_map_matches_cooltools():
    """K562 chr21 at 30 kb (real, ICE-balanced): cooltools 0.7.1 ``insulation(clr, [300000])`` calls these
    32 boundaries (Li threshold); scores sum to 33.0010806318 over 1,088 finite bins."""
    from uchrom.strc.tad.insulation import insulation_score

    ref = [14400000, 14820000, 15540000, 15930000, 17310000, 18480000, 20970000, 21990000, 22830000, 24090000,
           25500000, 26790000, 28740000, 29400000, 29880000, 31080000, 31590000, 32280000, 32790000, 33900000,
           34680000, 36030000, 36930000, 37650000, 38370000, 39120000, 39480000, 41070000, 41580000, 42120000,
           44940000, 45900000]
    tab = insulation_score(str(FIXTURES / "K562_chr21_30kb.cool"), windows=300_000)
    s = tab["log2_insulation_score_300000"].to_numpy()
    assert np.isfinite(s).sum() == 1088 and np.nansum(s) == pytest.approx(33.00108063181879, abs=1e-9)
    assert np.nansum(tab["boundary_strength_300000"]) == pytest.approx(39.890946154254095, abs=1e-9)
    assert tab.loc[tab["is_boundary_300000"], "start"].tolist() == ref


def test_boundaries_on_the_bins_of_a_map(tmp_path):
    """A ChromData holding only the Hi-C map: boundaries placed on the map's bins (contacts=)."""
    from uchrom import ChromData
    from uchrom.strc.tad import compare_boundaries, tad_boundaries
    from uchrom.strc.tad.insulation import InsulationParams, call_tads_insulation

    bins, pix = _planted()
    hic = ChromData(np.zeros((0, 3)), pd.DataFrame({"chrom": pd.Series(dtype=str), "start": pd.Series(dtype=np.int64),
                                                    "end": pd.Series(dtype=np.int64), "trace_id": pd.Series(dtype=str)}))
    hic.link_cool(str(_cool(tmp_path, bins, pix)), key="hic")
    call_tads_insulation(hic, params=InsulationParams(window_bp=50_000))
    with pytest.raises(KeyError, match="contacts="):
        tad_boundaries(hic, "tads.insulation")
    b = tad_boundaries(hic, "tads.insulation", contacts="hic")
    assert b["bin_index"].tolist() == sorted(hic.results["tads.insulation.boundaries"]["bin_index"])
    truth = pd.DataFrame({"chrom": "chr1", "start": np.array(BOUNDS[:-1]) * RES, "end": np.array(BOUNDS[1:]) * RES})
    out = compare_boundaries(hic, "tads.insulation", truth, tol=1, contacts="hic")
    assert out["n_query"] == 3 and out["fraction_near"] == 1.0 and out["chance"] < 0.5
