"""The native kernels of the Hi-C map callers (``uchrom_maps``, packages/uchrom-maps) against the numpy reference.

HiCCUPS scoring (``hiccups._score_chrom``) and the Mustache scan (``mustache._scan``) must give the numpy /
scipy results bit for bit: the same candidates, histograms, λ values, responses, layers and statistics, hence
the same enriched pixels and calls.  Tests needing the native package skip without it; the fallback to numpy
is tested either way.
"""

import sys

import numpy as np
import pandas as pd
import pytest

cooler = pytest.importorskip("cooler")

from uchrom.fea.band import read_band  # noqa: E402
from uchrom.strc.loop import hiccups as H  # noqa: E402
from uchrom.strc.loop import mustache as M  # noqa: E402

from .test_hiccups import _synthetic as _hiccups_map  # noqa: E402
from .test_mustache import LOOPS as M_LOOPS, PARAMS as M_PARAMS, _cool as _mustache_map  # noqa: E402

try:
    import uchrom_maps
except ImportError:                                       # pragma: no cover - the crate is optional
    uchrom_maps = None

native = pytest.mark.skipif(uchrom_maps is None, reason="uchrom_maps (packages/uchrom-maps) is not installed")

RES = 10_000                                              # the HiCCUPS test maps' bin size


@pytest.fixture
def backend(monkeypatch):
    """Set both modules' BACKEND for one test."""
    def set_(name):
        monkeypatch.setattr(H, "BACKEND", name)
        monkeypatch.setattr(M, "BACKEND", name)
    return set_


# ----------------------------------------------------------------------------------------------------- dispatch

def test_numpy_fallback_without_the_crate(tmp_path, monkeypatch):
    monkeypatch.setitem(sys.modules, "uchrom_maps", None)         # import uchrom_maps -> ImportError
    assert H._maps_kernels("auto") is None and H._maps_kernels("numpy") is None
    with pytest.raises(ImportError, match="uchrom-maps"):
        H._maps_kernels("native")
    with pytest.raises(ValueError, match="backend"):
        H._maps_kernels("gpu")
    clr = cooler.Cooler(_hiccups_map(tmp_path / "s.cool"))
    tm = {}
    px, info = H.hiccups_pixels(clr, ["chr1"], H.HiccupsParams(max_dist=2_000_000), timing=tm)
    assert tm["backend"] == "numpy" and len(px) > 0
    cool = _mustache_map(tmp_path / "m.cool", {"chrA": (640, M_LOOPS)})
    assert len(M.call_loops_mustache(cool, params=M_PARAMS)) == len(M_LOOPS)


@native
def test_backend_switch(tmp_path, backend):
    clr = cooler.Cooler(_hiccups_map(tmp_path / "s.cool"))
    for name in ("numpy", "native", "auto"):
        backend(name)
        tm = {}
        H.hiccups_pixels(clr, ["chr1"], H.HiccupsParams(max_dist=1_000_000), timing=tm)
        assert tm["backend"] == ("numpy" if name == "numpy" else "native")


# ----------------------------------------------------------------------------------------------------- HiCCUPS

def _score_both(band, params, binsize):
    p, w = H.kernel_sizes(binsize, params)
    D = int(params.max_dist / binsize)
    edges = H._lambda_edges(params.lambda_base)
    cmin = H._min_counts(edges, params.fdr, params.pvalue)
    out = {}
    for b in ("numpy", "native"):
        hist = H._Hist()
        out[b] = (H._score_chrom(band, p, w, D, params, hist, edges, cmin, backend=b), hist)
    return out


@native
@pytest.mark.parametrize("max_dist,pw", [(1_000_000, None), (2_000_000, None), (3_000_000, (1, 4)), (2_500_000, (3, 6))])
def test_hiccups_scoring_is_the_reference(tmp_path, max_dist, pw):
    """Candidates, λ values (bit for bit), histograms and the tested-pixel count of one chromosome."""
    clr = cooler.Cooler(_hiccups_map(tmp_path / "s.cool", masked=(150, 151, 300)))
    params = H.HiccupsParams(max_dist=max_dist, **({} if pw is None else {"p": pw[0], "w": pw[1]}))
    p, w = H.kernel_sizes(RES, params)
    band = read_band(clr, chrom="chr1", max_dist=(int(max_dist / RES) + 2 * w + 1) * RES, balance=True)
    (ra, ha), (rb, hb) = _score_both(band, params, RES).values()
    assert ra["n_tested"] == rb["n_tested"] > 10_000 and len(rb["i"]) > 100
    for k in ("i", "j", "count"):
        np.testing.assert_array_equal(np.asarray(ra[k], dtype=np.int64), rb[k])
    for k in H.KERNELS:
        np.testing.assert_array_equal(ra[k], rb[k])                     # λ bit for bit
        np.testing.assert_array_equal(ha.h[k], hb.h[k])


@native
def test_hiccups_scoring_of_an_unsorted_band(tmp_path):
    clr = cooler.Cooler(_hiccups_map(tmp_path / "s.cool"))
    params = H.HiccupsParams(max_dist=2_000_000)
    band = read_band(clr, chrom="chr1", max_dist=(200 + 11) * RES, balance=True)
    order = np.random.default_rng(0).permutation(len(band.i))
    band.i, band.j, band.count = band.i[order], band.j[order], band.count[order]
    (ra, ha), (rb, hb) = _score_both(band, params, RES).values()
    np.testing.assert_array_equal(np.asarray(ra["j"], dtype=np.int64), rb["j"])
    for k in H.KERNELS:
        np.testing.assert_array_equal(ra[k], rb[k])
        np.testing.assert_array_equal(ha.h[k], hb.h[k])


def _two_chromosomes(path):
    """chrA (planted loops) and chrB (noise, a masked bin) in one balanced cooler: one genome-wide FDR."""
    a, b = tmp = (path.with_name("a.cool"), path.with_name("b.cool"))
    _hiccups_map(a, chrom="chrA", balance=False)
    _hiccups_map(b, n=300, chrom="chrB", loops=[(50, 120)], seed=5, balance=False, masked=(77,))
    ca, cb = cooler.Cooler(str(a)), cooler.Cooler(str(b))
    bins = pd.concat([ca.bins()[:], cb.bins()[:]], ignore_index=True)
    pa, pb = ca.pixels()[:], cb.pixels()[:]
    pb[["bin1_id", "bin2_id"]] += len(ca.bins())
    cooler.create_cooler(str(path), bins, pd.concat([pa, pb], ignore_index=True), ordered=True, assembly="toy")
    cooler.balance_cooler(cooler.Cooler(str(path)), store=True)
    for t in tmp:
        t.unlink()
    return str(path)


@native
def test_hiccups_pixels_and_calls_are_the_reference(tmp_path, backend):
    """Through the public API, two chromosomes pooled (histograms of both added), both p-value conventions."""
    clr = cooler.Cooler(_two_chromosomes(tmp_path / "two.cool"))
    for params in (H.HiccupsParams(max_dist=2_000_000), H.HiccupsParams(max_dist=1_500_000, pvalue="cooltools")):
        got = {}
        for name in ("numpy", "native"):
            backend(name)
            px, info = H.hiccups_pixels(clr, ["chrA", "chrB"], params)
            calls, cinfo = H._call_one(clr, ["chrA", "chrB"], params)
            got[name] = (px, info, calls, cinfo)
        (pa, ia, ca, ja), (pb, ib, cb, jb) = got["numpy"], got["native"]
        assert len(pa) > 0 and len(ca) > 0
        pd.testing.assert_frame_equal(pa, pb, check_exact=True)
        pd.testing.assert_frame_equal(ca, cb, check_exact=True)
        assert ia == ib and ja == jb


@native
def test_hiccups_threads_do_not_change_the_result(tmp_path):
    clr = cooler.Cooler(_hiccups_map(tmp_path / "s.cool"))
    params = H.HiccupsParams(max_dist=2_000_000)
    p, w = H.kernel_sizes(RES, params)
    D = 200
    band = read_band(clr, chrom="chr1", max_dist=(D + 2 * w + 1) * RES, balance=True)
    e = H._expected_vector(band, params.ignore_diags, D + 2 * w + 2)
    edges = H._lambda_edges(params.lambda_base)
    cmin = H._min_counts(edges, params.fdr, params.pvalue)
    args = (band.n, band.i, band.j, band.count, band.weight, e, p, w, D, 40, edges, cmin)
    one, many = uchrom_maps.hiccups_score(*args, n_threads=1), uchrom_maps.hiccups_score(*args, n_threads=3)
    for k in ("i", "j", "count"):
        np.testing.assert_array_equal(one[k], many[k])
    for a, b in zip(one["lam"] + one["hist"], many["lam"] + many["hist"]):
        np.testing.assert_array_equal(a, b)
    with pytest.raises(ValueError, match="sorted"):
        uchrom_maps.hiccups_score(band.n, band.i[::-1].copy(), *args[2:])


# ----------------------------------------------------------------------------------------------------- Mustache

def _mustache_pixels(path):
    clr = cooler.Cooler(path)
    D = M_PARAMS.max_dist // 1000
    band = read_band(clr, chrom="chrA", max_dist=M_PARAMS.max_dist)
    v = band.values()
    keep = np.isfinite(v) & (v > 0) & (band.diag <= D)
    x, y, v = band.i[keep], band.j[keep], v[keep]
    z = M._normalize(x, y, v, band.n, D, 1000, M_PARAMS)
    el = np.flatnonzero((z != 0) & ((y - x) >= M_PARAMS.min_diag))
    return x, y, z, x[el], y[el], band.n, D


@native
@pytest.mark.parametrize("tile", [7, 64, 256, 10_000])
def test_mustache_scan_is_the_reference(tmp_path, tile):
    """Best responses and layers bit for bit, for any tile size; the per-layer |L| statistics too, except the sums:
    numpy sums in an order that depends on the CPU's SIMD (x86-64 differs from arm64 in the last bit)."""
    x, y, z, ex, ey, n, D = _mustache_pixels(_mustache_map(tmp_path / "m.cool", {"chrA": (640, M_LOOPS)}, seed=3))
    a = M._scan(x, y, z, ex, ey, n, D, M_PARAMS, tile, backend="numpy")
    b = M._scan(x, y, z, ex, ey, n, D, M_PARAMS, tile, backend="native")
    assert (a[1] >= 0).sum() > 100
    np.testing.assert_array_equal(a[0], b[0])
    np.testing.assert_array_equal(a[1], b[1])
    assert a[1].dtype == b[1].dtype
    np.testing.assert_allclose(a[2][0], b[2][0], rtol=1e-12)          # sums
    np.testing.assert_array_equal(a[2][1], b[2][1])                    # counts
    np.testing.assert_array_equal(a[2][2], b[2][2])                    # minima
    np.testing.assert_array_equal(a[3], b[3])


@native
def test_mustache_calls_are_the_reference(tmp_path, backend):
    cool = _mustache_map(tmp_path / "two.cool", {"chrA": (640, M_LOOPS), "chrB": (400, [(100, 160), (250, 300)])},
                         seed=1)
    other = M.MustacheParams(max_dist=100_000, norm_window=200_000, min_pixels=1000, octaves=3, scales=6)
    got = {}
    for name in ("numpy", "native"):
        backend(name)
        got[name] = (M.call_loops_mustache(cool, params=M_PARAMS), M.call_loops_mustache(cool, params=other))
    assert len(got["numpy"][0]) >= len(M_LOOPS)
    for a, b in zip(got["numpy"], got["native"]):                      # the same loops; scores to the last bits
        pd.testing.assert_frame_equal(a, b, check_exact=False, rtol=1e-12)
        pd.testing.assert_frame_equal(a.select_dtypes(exclude="float"), b.select_dtypes(exclude="float"),
                                      check_exact=True)


# ----------------------------------------------------------------------------------------------------- building blocks

@native
def test_gaussian_filter_is_scipy_s():
    """Every radius (the arm64 wheels change their arithmetic at 10 terms), short lines (repeated reflection)."""
    from scipy.ndimage import gaussian_filter

    arith = uchrom_maps.scipy_arithmetic()
    rng = np.random.default_rng(4)
    for shape in ((31, 47), (5, 60), (60, 3), (1, 9)):
        img = rng.normal(size=shape) * 10.0 ** rng.uniform(-2, 2, size=shape)
        for sigma in (0.7, 1.6, 2.6, 3.43, 4.6, 6.86, 9.5):
            for truncate in (2.0, 4.0):
                w = M._gaussian_weights(sigma, truncate)
                want = gaussian_filter(img, sigma, mode="reflect", truncate=truncate)
                got = uchrom_maps.gaussian_filter(img, w.tolist(), arith["fma"], arith["block"], arith["min_terms"])
                np.testing.assert_array_equal(got, want, err_msg=f"{shape} sigma {sigma} truncate {truncate}")


@native
def test_pairwise_sum_is_numpy_s():
    """numpy's pairwise summation (exactly so where numpy runs it without SIMD reordering, e.g. arm64; on x86-64
    numpy's vector loops add in another order, so only to the last bits)."""
    import platform

    exact = platform.machine().lower() in ("arm64",)
    rng = np.random.default_rng(5)
    for n in [0, 1, 7, 8, 9, 64, 127, 128, 129, 255, 1000, 8192, 8193, 100_003]:
        a = np.abs(rng.normal(size=n)) * 10.0 ** rng.uniform(-6, 6, size=n)
        if exact:
            assert uchrom_maps.pairwise_sum(a) == a.sum(), n
        else:
            assert uchrom_maps.pairwise_sum(a) == pytest.approx(a.sum(), rel=1e-13), n
