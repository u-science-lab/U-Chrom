"""uchrom.strc.loop.mustache: scale-space loop calling (Mustache) on small synthetic maps with planted loops."""

import math

import numpy as np
import pandas as pd
import pytest

cooler = pytest.importorskip("cooler")

from chromdata import ChromData  # noqa: E402

from uchrom.strc.loop.mustache import (  # noqa: E402
    MustacheParams, _normalize, call_loops_mustache, default_max_dist,
)

RES = 1000
LOOPS = [(100, 140), (220, 290), (380, 460), (520, 545)]
#: a 640-kb chromosome at 1 kb: the band and the normalisation window scaled down with it
PARAMS = MustacheParams(max_dist=100_000, norm_window=200_000, min_pixels=1000)


def _pixels(n, loops, seed, A=400.0, D=120, amp=3.0, offset=0):
    """Poisson counts decaying with separation, each loop a Gaussian blob (sd 2 bins, peak x (1 + amp))."""
    rng = np.random.default_rng(seed)
    i, j = np.triu_indices(n)
    k = (j - i) <= D
    i, j = i[k], j[k]
    lam = A / (1.0 + j - i)
    for a, b in loops:
        lam = lam * (1 + amp * np.exp(-((i - a) ** 2 + (j - b) ** 2) / (2 * 2.0 ** 2)))
    c = rng.poisson(lam)
    keep = c > 0
    return pd.DataFrame({"bin1_id": i[keep] + offset, "bin2_id": j[keep] + offset, "count": c[keep]})


def _ice(i, j, c, n, iters=100):
    """Matrix-balancing weights (``count * w[i] * w[j]`` has equal row sums), in memory: a fast stand-in
    for ``cooler balance`` on these small maps."""
    w = np.ones(n)
    off = i != j
    for _ in range(iters):
        val = c * w[i] * w[j]
        marg = np.bincount(i, val, n) + np.bincount(j[off], val[off], n)
        w /= np.sqrt(marg / marg.mean())
    return w


def _cool(path, chroms, seed=0):
    """``chroms``: {name: (n_bins, loops)}; balanced (``weight`` column)."""
    bins, px, off = [], [], 0
    for k, (c, (n, loops)) in enumerate(chroms.items()):
        p = _pixels(n, loops, seed + k, offset=off)
        w = _ice(p["bin1_id"].to_numpy() - off, p["bin2_id"].to_numpy() - off, p["count"].to_numpy(float), n)
        bins.append(pd.DataFrame({"chrom": c, "start": np.arange(n) * RES, "end": np.arange(1, n + 1) * RES,
                                  "weight": w}))
        px.append(p)
        off += n
    cooler.create_cooler(str(path), pd.concat(bins, ignore_index=True), pd.concat(px, ignore_index=True),
                         ordered=True, assembly="toy1")
    return str(path)


def test_planted_loops_are_found_and_noise_gives_none(tmp_path):
    cool = _cool(tmp_path / "loops.cool", {"chrA": (640, LOOPS)})
    loops = call_loops_mustache(cool, params=PARAMS)                 # a path: returned, not stored
    assert list(loops.columns[:6]) == ["chrom1", "start1", "end1", "chrom2", "start2", "end2"]
    got = set(zip(loops["summit_i"], loops["summit_j"]))
    for a, b in LOOPS:
        assert any(abs(a - i) <= 1 and abs(b - j) <= 1 for i, j in got), (a, b, got)
    assert len(loops) == len(LOOPS)
    assert (loops["fdr"] < PARAMS.fdr).all() and (loops["start1"] == loops["summit_i"] * RES).all()
    assert (loops["end2"] - loops["start2"] == RES).all() and (loops["scale"] >= PARAMS.sigma0).all()
    noise = _cool(tmp_path / "noise.cool", {"chrA": (640, [])})
    assert call_loops_mustache(noise, params=PARAMS).empty


def test_results_do_not_depend_on_the_tiling(tmp_path):
    cool = _cool(tmp_path / "loops.cool", {"chrA": (640, LOOPS)}, seed=3)
    dense = call_loops_mustache(cool, params=PARAMS, tile=10_000)     # one tile = the whole dense image
    for tile in (7, 64):
        pd.testing.assert_frame_equal(call_loops_mustache(cool, params=PARAMS, tile=tile), dense)


def test_normalisation_is_the_reference_sliding_window_zscore():
    """Against a direct transcription of the reference (np.convolve windows on every diagonal)."""
    rng = np.random.default_rng(1)
    n, D, res = 300, 20, 1000
    p = MustacheParams(norm_window=50_000, min_window_pixels=10)
    i, j = np.triu_indices(n)
    k = (j - i) <= D
    i, j = i[k], j[k]
    keep = rng.random(len(i)) < 0.7                                    # some pixels absent
    x, y = i[keep], j[keep]
    v = rng.gamma(2.0, 0.01, len(x))
    z = _normalize(x, y, v, n, D, res, p)

    want = v.copy()
    M = int(p.norm_window / res)
    for d in range(D + 1):
        sel = (y - x) == d
        vals = np.zeros(n - d)
        vals[x[sel]] = v[sel] + 1e-3
        mean, std = v[sel].mean(), v[sel].std()
        kern = np.ones(M)
        with np.errstate(all="ignore"):
            cnt = np.convolve(vals != 0, kern, mode="same")
            s = np.convolve(vals, kern, mode="same")
            s2 = np.convolve(vals ** 2, kern, mode="same")
            var = (s2 - s ** 2 / cnt) / (cnt - 1)
            var = np.nan_to_num(var, nan=std ** 2, posinf=std ** 2, neginf=std ** 2)
            mu = s / cnt
            mu[cnt < p.min_window_pixels] = mean
            var[cnt < p.min_window_pixels] = std ** 2
            out = (vals - mu) / np.sqrt(var)
        out = np.nan_to_num(out, nan=0, posinf=0, neginf=0) * (1 + math.log(1 + mean, 30))
        want[sel] = out[x[sel]]
    np.testing.assert_allclose(z, want, rtol=1e-9, atol=1e-9)


def test_linked_map_is_stored_with_provenance(tmp_path):
    cool = _cool(tmp_path / "two.cool", {"chrA": (640, LOOPS), "chrB": (90, [])})   # chrB: too few pixels
    cd = ChromData(np.zeros((0, 3)), pd.DataFrame({"chrom": pd.Series(dtype=str), "start": pd.Series(dtype=np.int64),
                                                   "end": pd.Series(dtype=np.int64),
                                                   "trace_id": pd.Series(dtype=str)}))
    cd.link_cool(cool, key="bulk")
    out = call_loops_mustache(cd, params=PARAMS, copy=True)          # chrom=None: every chromosome of the map
    assert "loops.mustache" not in cd.results
    table = out.intervals["loops.mustache"]
    assert len(table) == len(LOOPS) and set(table["chrom1"]) == {"chrA"}
    rec = out.results.record("loops.mustache")
    assert rec.function == "uchrom.strc.loop.call_loops_mustache"
    assert rec.inputs["contacts"] == "bulk" and rec.inputs["chrom"] == ["chrA", "chrB"]
    assert rec.inputs["resolution"] == RES and rec.inputs["max_dist"] == 100_000
    assert rec.params["max_dist"] == 100_000
    one = call_loops_mustache(cd, contacts="bulk", chrom="chrA", params=PARAMS, key_added="loops.m")
    pd.testing.assert_frame_equal(one, table.reset_index(drop=True), check_dtype=False)
    assert "loops.m" in cd.intervals
    with pytest.raises(ValueError, match="not in the map"):
        call_loops_mustache(cd, chrom="chrZ", params=PARAMS)


def test_default_distance_follows_the_reference():
    assert [default_max_dist(r) for r in (500, 1000, 5000, 10_000, 25_000)] == \
        [1_000_000, 2_000_000, 2_000_000, 2_000_000, 5_000_000]
    with pytest.raises(ValueError):
        MustacheParams(fdr=0)


def test_max3_is_the_zero_padded_maximum_filter():
    from scipy.ndimage import maximum_filter

    from uchrom.strc.loop.mustache import _max3

    a = np.random.default_rng(2).normal(size=(37, 53))
    np.testing.assert_array_equal(_max3(a), maximum_filter(a, size=3, mode="constant"))
