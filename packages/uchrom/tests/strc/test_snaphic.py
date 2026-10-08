"""uchrom.strc.loop.snaphic: SnapHiC on synthetic single cells — planted loops found, the numpy and native
paths agree, the statistics are those of a paired t-test, the clustering is Rodriguez & Laio's."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

cooler = pytest.importorskip("cooler")

from uchrom import ChromData  # noqa: E402
from uchrom.strc.loop import snaphic as S  # noqa: E402

try:
    import uchrom_maps
    HAVE_NATIVE = hasattr(uchrom_maps, "snaphic_chrom")
except ImportError:                                       # pragma: no cover
    HAVE_NATIVE = False

native = pytest.mark.skipif(not HAVE_NATIVE, reason="uchrom_maps with snaphic_chrom is not installed")

RES = 10_000
N1 = 320                                                  # bins of chr1
LOOPS = [(60, 75), (150, 172), (250, 270)]                # bin pairs (separations 150-220 kb)
PARAMS = S.SnapHiCParams(window=1_000_000, max_dist=300_000)


def _cells(n_cells=40, seed=0):
    rng = np.random.default_rng(seed)
    out = []
    for _ in range(n_cells):
        a = rng.integers(0, N1, 500)
        d = np.minimum((rng.pareto(1.0, 500) * 3).astype(int) + 2, N1)
        b = a + d
        ok = b < N1
        a, b = list(a[ok]), list(b[ok])
        for x, y in LOOPS:
            if rng.random() < 0.7:
                a.append(x + rng.integers(0, 2))
                b.append(y)
        out.append((np.asarray(a), np.asarray(b)))
    return out


@pytest.fixture(scope="module")
def cd(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("snaphic")
    from uchrom.io.pairs_maps import genome_bins

    sizes = {"chr1": N1 * RES, "chr2": 60 * RES, "chrX": 50 * RES}
    bins = genome_bins(sizes, RES)
    rng = np.random.default_rng(1)
    maps = {}
    for k, (a, b) in enumerate(_cells()):
        a2 = rng.integers(0, 60, 80)
        b2 = np.minimum(a2 + rng.integers(2, 20, 80), 59)
        px = pd.DataFrame({"bin1_id": np.r_[np.minimum(a, b), N1 + a2],
                           "bin2_id": np.r_[np.maximum(a, b), N1 + b2], "count": 1})
        maps[f"cell{k:02d}"] = px.groupby(["bin1_id", "bin2_id"], as_index=False)["count"].sum()
    cooler.create_scool(str(tmp / "cells.scool"), bins, maps, ordered=True)
    no = pd.DataFrame({c: pd.Series(dtype=t) for c, t in [("chrom", str), ("start", np.int64), ("end", np.int64),
                                                          ("trace_id", str), ("cell_id", str)]})
    cd = ChromData(np.zeros((0, 3)), no, cells=pd.DataFrame(index=pd.Index(list(maps), name="cell_id")))
    cd.link_scool(str(tmp / "cells.scool"), key="per_cell", bin_size=RES, genome_assembly="toy")
    return cd


def _found(table, tol=1):
    got = set(zip(table["start1"] // RES, table["start2"] // RES))
    return [any(abs(x - a) <= tol and abs(y - b) <= tol for a, b in got) for x, y in LOOPS]


def test_planted_loops_are_called(cd):
    tm = {}
    t = S.call_loops_snaphic(cd, chrom="chr1", params=PARAMS, backend="numpy", key_added=None, timing=tm)
    assert all(_found(t)), t
    assert len(t) <= 3 * len(LOOPS)
    assert tm["backend"] == "numpy"
    assert {"chrom1", "start1", "end1", "chrom2", "start2", "end2", "outlier_count", "tstat", "fdr_dist",
            "cluster_size", "score"} <= set(t.columns)
    assert (t["cluster_size"] > 1).all() and (t["fdr_dist"] < 0.1).all() and (t["tstat"] > 3).all()
    assert (t["outlier_count"] > 0.1 * 40).all()


def test_autosomes_by_default_and_storage(cd):
    out = S.call_loops_snaphic(cd.copy(), params=PARAMS, backend="numpy", copy=True)
    rec = out.results.record("loops.snaphic")
    assert rec.function == "uchrom.strc.loop.call_loops_snaphic"
    assert rec.inputs["chrom"] == ["chr1", "chr2"]                     # chrX left out (autosomes)
    assert rec.inputs["window_bp"] == 1_000_000 and rec.inputs["n_cells"] == 40
    assert "loops.snaphic" in out.intervals and "loops.snaphic.candidates" in out.results
    assert "loops.snaphic" not in cd.results


def test_default_is_whole_chromosomes(cd):
    assert S.SnapHiCParams().window is None
    out = S.call_loops_snaphic(cd.copy(), chrom="chr1", params=S.SnapHiCParams(max_dist=300_000), backend="numpy",
                               copy=True)
    assert out.results.record("loops.snaphic").inputs["window_bp"] is None
    assert all(_found(out.results["loops.snaphic"]))


def test_exclude_drops_anchors(cd):
    a, b = LOOPS[0]
    ex = pd.DataFrame({"chrom": ["chr1"], "start": [(a - 3) * RES], "end": [(a + 4) * RES]})
    t = S.call_loops_snaphic(cd, chrom="chr1", params=PARAMS, backend="numpy", key_added=None, exclude=ex)
    assert _found(t) == [False, True, True]


@native
def test_native_and_numpy_give_the_same_calls(cd):
    a = S.call_loops_snaphic(cd, chrom="chr1", params=PARAMS, backend="numpy", key_added=None)
    b = S.call_loops_snaphic(cd, chrom="chr1", params=PARAMS, backend="native", key_added=None)
    pd.testing.assert_frame_equal(a[["chrom1", "start1", "start2", "outlier_count", "cluster_size"]],
                                  b[["chrom1", "start1", "start2", "outlier_count", "cluster_size"]])
    assert np.allclose(a["tstat"], b["tstat"], rtol=1e-9) and np.allclose(a["fdr_dist"], b["fdr_dist"], rtol=1e-9)


@native
def test_native_sums_equal_numpy_sums():
    cells = _cells(12, seed=4)
    kw = dict(rp=0.05, window=100, step=50, max_diag=35, out_diag=30, edge=5)
    A = S.snaphic_sums(N1, cells, backend="numpy", **kw)
    B = S.snaphic_sums(N1, cells, backend="native", batch=5, **kw)
    for k in ("sum_z", "sum_l", "sum_d", "sum_dd"):
        assert np.allclose(A[k], B[k], rtol=0, atol=1e-10 * np.abs(A[k]).max())
    assert np.array_equal(A["n_out"], B["n_out"]) and A["n_cells"] == B["n_cells"] == 12


@native
def test_snaphic_holes_are_the_same_on_both_paths():
    from uchrom.fea.impute_rwr import _snaphic_holes, rwr_band

    cells = _cells(6, seed=5)
    a, b = cells[0]
    x = rwr_band(a, b, N1, window=100, step=50, max_diag=35, backend="numpy", holes=True)
    y = rwr_band(a, b, N1, window=100, step=50, max_diag=35, backend="native", holes=True)
    h = _snaphic_holes(N1, 36, 50) & np.isfinite(x)
    assert (x[h] == 0).all() and (y[h] == 0).all() and h[:, 1].sum() > 3
    assert np.allclose(x, y, equal_nan=True, rtol=1e-11)
    kw = dict(rp=0.05, window=100, step=50, max_diag=35, out_diag=30, edge=5, holes=True)
    A = S.snaphic_sums(N1, cells, backend="numpy", **kw)
    B = S.snaphic_sums(N1, cells, backend="native", **kw)
    assert np.array_equal(A["n_out"], B["n_out"]) and np.allclose(A["sum_d"], B["sum_d"], atol=1e-9)


def test_sums_give_a_paired_t_test():
    from scipy.stats import ttest_rel

    from uchrom.fea.impute_rwr import _rwr_band_numpy, _zscore_numpy

    cells = _cells(8, seed=2)
    kw = dict(rp=0.05, window=100, step=50, max_diag=35, out_diag=30, edge=5)
    acc = S.snaphic_sums(N1, cells, backend="numpy", **kw)
    px = S._pixel_table(acc, N1, 5, 5)
    z, lb = [], []
    for a, b in cells:
        zz = _zscore_numpy(_rwr_band_numpy(N1, a, b, rp=0.05, window=100, step=50, max_diag=35, min_sep=2,
                                           chain=True), 5, 0.01, 1e-6)
        z.append(zz)
        lb.append(S._local_background_numpy(zz, 30, 2, 5))
    for i, j in [(40, 52), (100, 130), (5, 6), (300, 314)]:
        row = px[(px["i"] == i) & (px["j"] == j)].iloc[0]
        x = np.array([q[i, j - i] for q in z])
        y = np.array([q[i, j - i] for q in lb])
        r = ttest_rel(x, y)
        assert row["tstat"] == pytest.approx(r.statistic, rel=1e-8)
        assert row["pvalue"] == pytest.approx(r.pvalue, rel=1e-6)
        assert row["outlier_count"] == (x > 1.96).sum()
        assert row["case_avg"] == pytest.approx(x.mean()) and row["control_avg"] == pytest.approx(y.mean())
    # BH per distance
    d = px[px["j"] - px["i"] == 12]
    p = np.sort(d["pvalue"].to_numpy())
    q = np.minimum.accumulate((p * len(p) / np.arange(1, len(p) + 1))[::-1])[::-1]
    assert np.allclose(np.sort(d["fdr_dist"].to_numpy()), np.minimum(q, 1))


def test_local_background_is_the_ring_mean():
    rng = np.random.default_rng(0)
    n, D = 50, 12
    z = rng.normal(size=(n, D + 1))
    z[:, 0] = np.nan
    z[(np.arange(n)[:, None] + np.arange(D + 1)[None, :]) >= n] = np.nan
    lb = S._local_background_numpy(z, 7, 2, 5)

    def val(a, b):
        if a < 0 or b >= n or b <= a:
            return None
        return 0.0 if b - a > D else z[a, b - a]
    for i, d in [(0, 1), (3, 4), (20, 7), (44, 5), (25, 1)]:
        j = i + d
        v = [val(a, b) for a in range(i - 5, i + 6) for b in range(j - 5, j + 6)
             if not (abs(a - i) <= 2 and abs(b - j) <= 2)]
        v = [x for x in v if x is not None]
        assert lb[i, d] == pytest.approx(np.mean(v))
    if HAVE_NATIVE:
        nat = uchrom_maps.local_background(np.ascontiguousarray(z), 7, 2, 5)
        assert np.allclose(nat, lb, equal_nan=True, rtol=1e-12)


def test_density_peak_clustering_and_summits():
    # Worked by hand.  Densities (candidates within sqrt(2), self included): blob A (10,30) 4, (10,31) 4,
    # (11,30) 5, (11,31) 5, (12,31) 3; blob B 3 each.  The two densest points have no denser one: delta = their
    # largest distance (~72); A's others point to their nearest denser neighbour (delta 1); B's points have
    # no denser point nearby: delta ~71 to blob A.  eta = density x delta; the elbow of (rank, eta) falls at
    # eta = 4, so the centres are (11,30), (11,31) and the three points of B — B splits into singletons —, and
    # (10,30) joins (11,30), (10,31) and (12,31) join (11,31).  (80,140): no candidate within 2 bins, dropped.
    pts = [(10, 30), (10, 31), (11, 30), (11, 31), (12, 31), (50, 90), (50, 91), (51, 91), (80, 140)]
    fdr = [0.01, 0.02, 0.03, 0.001, 0.05, 0.02, 0.02, 0.01, 0.001]
    cand = pd.DataFrame({"i": [p[0] for p in pts], "j": [p[1] for p in pts], "fdr_dist": fdr})
    cl = S.cluster_candidates(cand, clustering_gap=1, summit_gap_bins=2)
    assert len(cl) == 8
    groups = {tuple(sorted(zip(g["i"], g["j"]))) for _, g in cl.groupby("eta_cluster")}
    assert groups == {((10, 30), (11, 30)), ((10, 31), (11, 31), (12, 31)), ((50, 90),), ((50, 91),), ((51, 91),)}
    loops = cl[(cl["summit"] == 1) & (cl["cluster_size"] > 1)]
    assert set(zip(loops["i"], loops["j"])) == {(10, 30), (11, 31)}             # the lowest FDR of each
    a = cl[cl["i"] == 12]
    assert a["neg_log10_fdr"].iloc[0] == pytest.approx(-np.log10([0.02, 0.001, 0.05]).sum())
    assert S.cluster_candidates(cand.iloc[:1]).empty
