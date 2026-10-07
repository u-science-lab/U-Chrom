"""uchrom.strc.loop.hiccups: HiCCUPS loop calling (Rao 2014 / cooltools dots) on small synthetic maps."""

import numpy as np
import pandas as pd
import pytest

cooler = pytest.importorskip("cooler")

from chromdata import ChromData  # noqa: E402

from uchrom.strc.loop.hiccups import (  # noqa: E402
    KERNELS,
    HiccupsParams,
    call_loops_hiccups,
    cluster_pixels,
    hiccups_pixels,
    kernel_masks,
    kernel_rects,
    kernel_sizes,
    merge_resolutions,
)

RES = 10_000
LOOPS = [(60, 100), (150, 230), (200, 330), (300, 340)]     # planted loops (bins), separations 40-130


def _synthetic(path, *, n=420, res=RES, loops=LOOPS, fold=6.0, seed=0, chrom="chr1", balance=True,
               masked=()):
    """One chromosome: Poisson counts decaying as 300 / (d + 1), loops planted as 3x3 blobs (centre x fold,
    the 8 neighbours x fold / 2); ``masked`` bins get no contacts."""
    rng = np.random.default_rng(seed)
    i, j = np.triu_indices(n)
    lam = 300.0 / (j - i + 1.0)
    boost = np.ones(len(i))
    for a, b in loops:
        for di in (-1, 0, 1):
            for dj in (-1, 0, 1):
                k = (i == a + di) & (j == b + dj)
                boost[k] = fold if (di, dj) == (0, 0) else fold / 2
    cnt = rng.poisson(lam * boost)
    for m in masked:
        cnt[(i == m) | (j == m)] = 0
    keep = cnt > 0
    s = np.arange(n) * res
    bins = pd.DataFrame({"chrom": chrom, "start": s, "end": s + res})
    cooler.create_cooler(str(path), bins, pd.DataFrame({"bin1_id": i[keep], "bin2_id": j[keep], "count": cnt[keep]}),
                         ordered=True, assembly="toy")
    if balance:
        cooler.balance_cooler(cooler.Cooler(str(path)), store=True)
    return str(path)


def _cd():
    return ChromData(np.zeros((0, 3)), pd.DataFrame({"chrom": pd.Series(dtype=str), "start": pd.Series(dtype=np.int64),
                                                     "end": pd.Series(dtype=np.int64),
                                                     "trace_id": pd.Series(dtype=str)}),
                     uns={"genome_assembly": "toy"})


def test_kernels_follow_rao2014():
    assert kernel_sizes(5000) == (4, 7) and kernel_sizes(10_000) == (2, 5) and kernel_sizes(25_000) == (1, 3)
    assert kernel_sizes(10_000, HiccupsParams(p=1, w=4)) == (1, 4)
    with pytest.raises(ValueError, match="kernel sizes"):
        kernel_sizes(100_000)
    p, w = 2, 5
    m = kernel_masks(p, w)
    assert set(m) == set(KERNELS) and all(set(np.unique(k)) <= {0, 1} for k in m.values())
    c = w                                                      # centre index
    # donut: the window minus the peak square and the cross through the pixel
    assert m["donut"].sum() == (2 * w + 1) ** 2 - (2 * p + 1) ** 2 - 4 * (w - p)
    assert m["donut"][c].sum() == 0 and m["donut"][:, c].sum() == 0
    assert m["donut"][c - p: c + p + 1, c - p: c + p + 1].sum() == 0
    # vertical / horizontal: 3-wide strips outside the peak square
    assert m["vertical"].sum() == m["horizontal"].sum() == 3 * 2 * (w - p)
    assert np.array_equal(m["vertical"], m["horizontal"].T)
    # lower-left: rows below (towards the diagonal), columns left, outside the peak square
    ll = m["lowleft"]
    assert ll.sum() == w * w - p * p and ll[: c + 1].sum() == 0 and ll[:, c:].sum() == 0
    assert ll[c + 1: c + p + 1, c - p: c].sum() == 0
    # the rectangles are what the masks are built from: no overlaps (values stay 0 / 1)
    assert len(kernel_rects(p, w)["donut"]) == 6


def test_locally_adjusted_expected_matches_a_direct_sum(tmp_path):
    """λ of the enriched pixels = E_raw * Σ_K(O_bal) / Σ_K(E_bal) summed directly over the kernel masks."""
    from uchrom.fea.band import expected_cis

    path = _synthetic(tmp_path / "s.cool")
    clr = cooler.Cooler(path)
    params = HiccupsParams(max_dist=2_000_000)
    px, info = hiccups_pixels(clr, ["chr1"], params)
    assert info["p"] == 2 and info["w"] == 5 and len(px) > 0
    O = np.array(clr.matrix(balance=True)[:])
    wgt = clr.bins()[:]["weight"].to_numpy()
    raw = clr.matrix(balance=False)[:]
    exp = expected_cis(clr).set_index("diag")["balanced_avg"].to_numpy().copy()
    exp[:2] = np.nan
    n = len(wgt)
    d = np.abs(np.subtract.outer(np.arange(n), np.arange(n)))
    E = exp[d]
    E[np.tril_indices(n, -1)] = np.nan
    O = O.copy()
    O[np.tril_indices(n, -1)] = np.nan
    masks = kernel_masks(2, 5)
    for _, r in px.head(25).iterrows():
        i, j = int(r["i"]), int(r["j"])
        sl = (slice(i - 5, i + 6), slice(j - 5, j + 6))
        assert raw[i, j] == r["count"]
        for k in KERNELS:
            mk = masks[k].astype(bool)
            o, e = O[sl][mk], E[sl][mk]
            assert np.isfinite(o).all() and np.isfinite(e).all()     # tested pixels have NaN-free kernels
            lam = E[i, j] / (wgt[i] * wgt[j]) * o.sum() / e.sum()
            assert r[f"exp_{k}"] == pytest.approx(lam, rel=1e-9)


def test_planted_loops_are_called(tmp_path):
    cd = _cd()
    cd.link_cool(_synthetic(tmp_path / "s.cool"), key="bulk", genome_assembly="toy")
    loops = call_loops_hiccups(cd, params=HiccupsParams(max_dist=2_000_000))
    assert list(loops.columns[:6]) == ["chrom1", "start1", "end1", "chrom2", "start2", "end2"]
    called = set(zip(loops["summit_i"], loops["summit_j"]))
    for a, b in LOOPS:
        assert any(abs(a - x) <= 1 and abs(b - y) <= 1 for x, y in called), (a, b, sorted(called))
    assert len(loops) <= len(LOOPS) + 1                               # few false positives on a noise map
    assert (loops["count"] > 1.75 * loops["exp_donut"]).all() and (loops["fdr"] <= 0.1).all()
    assert (loops["end1"] - loops["start1"] == RES).all() and (loops["resolution"] == RES).all()
    # stored as a pair interval table with provenance
    assert "loops.hiccups" in cd.intervals and cd.results.record("loops.hiccups").kind == "intervals"
    rec = cd.results.record("loops.hiccups")
    assert rec.function == "uchrom.strc.loop.call_loops_hiccups" and rec.inputs["resolution"] == [RES]


def test_no_loops_in_a_map_without_loops(tmp_path):
    cd = _cd()
    cd.link_cool(_synthetic(tmp_path / "s.cool", loops=[], seed=3), key="bulk")
    loops = call_loops_hiccups(cd, params=HiccupsParams(max_dist=2_000_000), key_added=None)
    assert len(loops) <= 1 and "loops.hiccups" not in cd.results


def test_pvalue_conventions_and_masked_bins(tmp_path):
    path = _synthetic(tmp_path / "s.cool", masked=(150,))
    clr = cooler.Cooler(path)
    strict, info_s = hiccups_pixels(clr, ["chr1"], HiccupsParams(max_dist=2_000_000))
    loose, info_l = hiccups_pixels(clr, ["chr1"], HiccupsParams(max_dist=2_000_000, pvalue="cooltools"))
    assert info_s["n_tested"] == info_l["n_tested"]
    # P(X > obs) <= P(X >= obs): the cooltools convention passes at least the same pixels
    assert set(zip(strict["i"], strict["j"])) <= set(zip(loose["i"], loose["j"]))
    # no tested pixel has a masked bin in a kernel's reach (5 bins)
    for t in (strict, loose):
        assert ((t["i"] - 150).abs() > 5).all() and ((t["j"] - 150).abs() > 5).all()
        assert ((t["j"] - t["i"]) >= 2 * 5 + 2).all()                  # kernels off the ignored diagonals
    # the planted loop (150, 230) touches the masked bin: not called, the others are
    assert not any(abs(i - 150) <= 1 for i in strict["i"])
    with pytest.raises(ValueError, match="pvalue"):
        HiccupsParams(pvalue="other")


def test_unbalanced_map_is_refused(tmp_path):
    cd = _cd()
    cd.link_cool(_synthetic(tmp_path / "raw.cool", balance=False), key="raw")
    with pytest.warns(UserWarning, match="not balanced"), pytest.raises(ValueError, match="balanced"):
        call_loops_hiccups(cd, contacts="raw", params=HiccupsParams(max_dist=1_000_000))


def test_copy_and_two_resolutions_merge(tmp_path):
    cd = _cd()
    cd.link_cool(_synthetic(tmp_path / "a.cool"), key="r10")
    cd.link_cool(_synthetic(tmp_path / "b.cool", n=170, res=25_000,
                            loops=[(a * 2 // 5, b * 2 // 5) for a, b in LOOPS]), key="r25")
    out = call_loops_hiccups(cd, contacts=["r10", "r25"], params=HiccupsParams(max_dist=3_000_000), copy=True)
    assert out is not cd and "loops.hiccups" not in cd.results and "loops.hiccups" in out.intervals
    t = out.results["loops.hiccups"]
    assert set(t["resolution"]) <= {10_000, 25_000} and (t["resolution"] == 10_000).any()
    # a 25-kb loop is only kept when no 10-kb loop lies within 50 kb
    t10, t25 = t[t["resolution"] == 10_000], t[t["resolution"] == 25_000]
    for _, r in t25.iterrows():
        assert (np.hypot(t10["start1"] - r["start1"], t10["start2"] - r["start2"]) > 50_000).all()
    with pytest.raises(ValueError, match="copy=True"):
        call_loops_hiccups(cd, contacts="r10", key_added=None, copy=True)


def test_cluster_pixels_greedy():
    # two blobs 200 kb apart, and a pixel 30 kb from the first blob's brightest (beyond 20 kb + radius)
    s1 = np.array([1_000_000, 1_010_000, 1_000_000, 1_200_000, 1_210_000, 1_000_000])
    s2 = np.array([2_000_000, 2_000_000, 2_010_000, 2_500_000, 2_500_000, 2_045_000])
    cnt = np.array([50, 40, 30, 60, 10, 45])
    cl = cluster_pixels(s1, s2, cnt, radius=20_000, resolution=10_000)
    labels = cl.attrs["labels"]
    assert len(cl) == 3
    assert labels[0] == labels[1] == labels[2] and labels[3] == labels[4] and labels[5] not in (labels[0], labels[3])
    first = cl[cl["summit"] == 0].iloc[0]
    assert first["cluster_size"] == 3 and first["radius"] > 0
    assert first["centroid1"] == int((1_000_000 + 1_010_000 + 1_000_000) / 3) + 5_000
    assert cl.iloc[0]["summit"] == 3                                    # brightest first
    empty = cluster_pixels([], [], [], radius=20_000, resolution=10_000)
    assert len(empty) == 0


def test_merge_resolutions_rao2014_rules():
    def t(res, rows):
        return pd.DataFrame([{"chrom1": "chr1", "start1": a, "start2": b, "count": c, "resolution": res}
                             for a, b, c in rows])

    five = t(5000, [(1_000_000, 1_300_000, 50),      # reproduced at 10 kb -> kept
                    (2_000_000, 2_400_000, 50),      # not reproduced, far from the diagonal, weak -> dropped
                    (3_000_000, 3_100_000, 50),      # not reproduced but < 110 kb from the diagonal -> kept
                    (4_000_000, 4_500_000, 150)])    # not reproduced but > 100 contacts -> kept
    ten = t(10_000, [(1_010_000, 1_300_000, 80),     # near a 5-kb loop -> replaced by it
                     (6_000_000, 6_400_000, 80)])    # unique -> kept
    tf = t(25_000, [(6_025_000, 6_400_000, 90),      # within 50 kb of the 10-kb loop -> dropped
                    (8_000_000, 8_600_000, 90)])     # unique -> kept
    m = merge_resolutions({5000: five, 10_000: ten, 25_000: tf})
    got = set(zip(m["resolution"], m["start1"]))
    assert got == {(5000, 1_000_000), (5000, 3_000_000), (5000, 4_000_000), (10_000, 6_000_000),
                   (25_000, 8_000_000)}
    assert len(merge_resolutions({10_000: ten})) == 2
    with pytest.raises(ValueError):
        merge_resolutions({})
