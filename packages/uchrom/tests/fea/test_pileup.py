"""uchrom.fea.pileup: aggregate peak analysis (APA) of loops, on-diagonal pileups of boundaries."""

import numpy as np
import pandas as pd
import pytest

cooler = pytest.importorskip("cooler")

from chromdata import ChromData  # noqa: E402

from uchrom.fea import pileup, pileup_scores  # noqa: E402

RES = 10_000
N = 500
LOOPS = [(40, 90), (120, 180), (210, 260), (300, 370), (400, 440)]
BOUNDS = [100, 200, 300, 400]                                   # domains [0,100), [100,200), ...


def _map(path, *, loops=LOOPS, fold=5.0, domains=True, depth=1.0, seed=0, balance=True):
    """chr1 at 10 kb: counts ~ depth * 200 / (d + 1), x 1.8 within domains, loops planted as single pixels."""
    rng = np.random.default_rng(seed)
    i, j = np.triu_indices(N)
    lam = depth * 200.0 / (j - i + 1.0)
    if domains:
        dom = np.searchsorted(BOUNDS, np.arange(N), side="right")
        lam = lam * np.where(dom[i] == dom[j], 1.8, 1.0)
    for a, b in loops:
        lam[(i == a) & (j == b)] *= fold
    cnt = rng.poisson(lam)
    keep = cnt > 0
    s = np.arange(N) * RES
    cooler.create_cooler(str(path), pd.DataFrame({"chrom": "chr1", "start": s, "end": s + RES}),
                         pd.DataFrame({"bin1_id": i[keep], "bin2_id": j[keep], "count": cnt[keep]}), ordered=True)
    if balance:
        cooler.balance_cooler(cooler.Cooler(str(path)), store=True)
    return str(path)


def _cd(path):
    cd = ChromData(np.zeros((0, 3)), pd.DataFrame({"chrom": pd.Series(dtype=str), "start": pd.Series(dtype=np.int64),
                                                   "end": pd.Series(dtype=np.int64), "trace_id": pd.Series(dtype=str)}))
    cd.link_cool(path, key="bulk")
    return cd


def _pairs(pairs, chrom="chr1"):
    a, b = np.asarray(pairs).T
    return pd.DataFrame({"chrom1": chrom, "start1": a * RES, "end1": a * RES + RES,
                         "chrom2": chrom, "start2": b * RES, "end2": b * RES + RES})


def test_apa_of_planted_loops(tmp_path):
    cd = _cd(_map(tmp_path / "m.cool", domains=False))
    out = pileup(cd, _pairs(LOOPS), flank=50_000)
    assert out["kind"] == "pair" and out["n"] == len(LOOPS) and out["flank_bins"] == 5
    M = out["matrix"]
    assert M.shape == (11, 11)
    assert out["apa"] > 3 and M[5, 5] == pytest.approx(out["center"])
    assert np.nanmean(np.delete(M.ravel(), 60)) == pytest.approx(1.0, abs=0.15)   # O/E ~ 1 off the loops
    # per-feature centres: the planted pixels; the mean of the windows agrees on a homogeneous set
    assert (out["features"]["center"] > 2.5).all()
    mean = pileup(cd, _pairs(LOOPS), flank=50_000, aggregate="mean", key_added=None)
    assert mean["apa"] == pytest.approx(out["apa"], rel=0.25) and mean["matrix"][5, 5] == pytest.approx(
        out["features"]["center"].mean())
    # random pairs at the same separations: no enrichment
    rng = np.random.default_rng(1)
    sep = [b - a for a, b in LOOPS]
    rand = [(int(s), int(s) + d) for s, d in zip(rng.integers(20, 400, 40), np.resize(sep, 40))]
    ctrl = pileup(cd, _pairs(rand), flank=50_000, key_added=None)
    assert 0.6 < ctrl["apa"] < 1.5
    # stored with provenance; the result survives a write / read
    rec = cd.results.record("pileup")
    assert rec.kind == "mapping" and rec.function == "uchrom.fea.pileup"
    cd.write(tmp_path / "x.chromdata.zarr")
    back = ChromData.read(tmp_path / "x.chromdata.zarr")
    assert back.results["pileup"]["apa"] == pytest.approx(out["apa"])
    np.testing.assert_allclose(back.results["pileup"]["matrix"], M)


def test_aggregate_sum_resists_far_outliers(tmp_path):
    """A far pair (tiny expected) with a few contacts has a huge O/E: it shifts the mean of the windows, not
    the pooled ratio."""
    cd = _cd(_map(tmp_path / "m.cool", domains=False))
    base = _pairs(LOOPS)
    far = pd.concat([base, _pairs([(10, 480)])], ignore_index=True)          # 470 bins apart: expected ~0.4
    s0 = pileup(cd, base, flank=50_000, key_added=None)
    s1 = pileup(cd, far, flank=50_000, key_added=None)
    m0 = pileup(cd, base, flank=50_000, aggregate="mean", key_added=None)
    assert s1["n"] == m0["n"] + 1
    assert abs(s1["apa"] - s0["apa"]) / s0["apa"] < 0.1
    assert m0["apa"] > 3 and s0["apa"] > 3
    with pytest.raises(ValueError, match="aggregate"):
        pileup(cd, base, aggregate="median", key_added=None)


def test_observed_pileup_scores_and_corner():
    M = np.ones((21, 21))
    M[10, 10] = 4.0
    M[15:, :6] = 2.0                                                # the lower-left corner (towards the diagonal)
    s = pileup_scores(M, kind="pair", corner=6)
    assert s["apa"] == pytest.approx(2.0) and s["lower_left"] == pytest.approx(2.0)
    assert s["p2m"] == pytest.approx(4.0 / np.delete(M.ravel(), 220).mean())
    P = np.ones((11, 11))
    P[:5, :5] = P[6:, 6:] = 2.0
    assert pileup_scores(P, kind="point")["score"] == pytest.approx(2.0)


def test_boundary_pileup(tmp_path):
    cd = _cd(_map(tmp_path / "m.cool", loops=[]))
    pts = pd.DataFrame({"chrom": "chr1", "start": np.array(BOUNDS) * RES, "end": np.array(BOUNDS) * RES + 1})
    out = pileup(cd, pts, flank=100_000, key_added=None)
    assert out["kind"] == "point" and out["n"] == len(BOUNDS)
    assert out["score"] > 1.4
    mid = pts.assign(start=pts["start"] + 50 * RES, end=pts["end"] + 50 * RES)       # domain centres
    assert pileup(cd, mid, flank=100_000, key_added=None)["score"] < 1.15


def test_sparse_map_and_options(tmp_path):
    """A map at 2 % depth: too sparse to call loops pixel by pixel, the pileup still shows them."""
    path = _map(tmp_path / "sparse.cool", depth=0.02, domains=False, fold=8.0, seed=4, balance=False)
    cd = _cd(path)
    many = [(a + k, b + k) for k in range(0, 40, 4) for a, b in LOOPS if b + k < N - 10]
    path2 = _map(tmp_path / "sparse2.cool", loops=many, depth=0.02, domains=False, fold=8.0, seed=4, balance=False)
    cd2 = _cd(path2)
    out = pileup(cd2, _pairs(many), flank=30_000, balance=False, key_added=None)
    assert out["n"] == len(many) and out["apa"] > 2
    # chromosome names without 'chr' (published lists) are mapped onto the map's
    out2 = pileup(cd2, _pairs(many, chrom="1"), flank=30_000, balance=False, key_added=None)
    assert out2["n"] == len(many) and out2["apa"] == pytest.approx(out["apa"])
    # observed instead of observed / expected; too-close pairs are dropped by default
    close = pileup(cd, _pairs([(100, 104), (40, 90)]), flank=30_000, balance=False, expected=False, key_added=None)
    assert close["n"] == 1 and close["n_dropped"] == 1 and not close["expected"]
    kept = pileup(cd, _pairs([(100, 104)]), flank=30_000, balance=False, min_separation=0, key_added=None)
    assert kept["n"] == 1 and np.isnan(kept["matrix"]).any()        # ignored diagonals are NaN
    # copy=True returns a new object
    new = pileup(cd, _pairs(LOOPS), flank=30_000, balance=False, key_added="apa", copy=True)
    assert "apa" in new.results and "apa" not in cd.results
    with pytest.raises(KeyError):
        pileup(cd, pd.DataFrame({"x": [1]}), key_added=None)
    with pytest.raises(KeyError, match="neither"):
        pileup(cd, "no_such_key", key_added=None)
