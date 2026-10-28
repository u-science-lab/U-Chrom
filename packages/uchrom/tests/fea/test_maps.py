"""uchrom.fea.maps: contact maps linked to a ChromData (read, rebin, observed / expected) on small coolers."""

import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

cooler = pytest.importorskip("cooler")

from chromdata import ChromData  # noqa: E402

from uchrom.fea import contact_matrix, map_path, observed_over_expected, rebin_map  # noqa: E402

RES = 1000
SIZES = {"chrA": 40_500, "chrB": 23_000}


def _toy_cool(path, *, seed=0, balance=True):
    """Two chromosomes at 1 kb, counts decaying with separation, some inter-chromosomal pixels."""
    rng = np.random.default_rng(seed)
    bins = []
    for c, size in SIZES.items():
        s = np.arange(0, size, RES)
        bins.append(pd.DataFrame({"chrom": c, "start": s, "end": np.minimum(s + RES, size)}))
    bins = pd.concat(bins, ignore_index=True)
    n = len(bins)
    chrom = bins["chrom"].to_numpy()
    i, j = np.triu_indices(n)
    same = chrom[i] == chrom[j]
    lam = np.where(same, 50.0 / (j - i + 1.0), 0.5)
    counts = rng.poisson(lam)
    keep = counts > 0
    px = pd.DataFrame({"bin1_id": i[keep], "bin2_id": j[keep], "count": counts[keep]})
    cooler.create_cooler(str(path), bins, px, ordered=True, assembly="toy1")
    if balance:
        cooler.balance_cooler(cooler.Cooler(str(path)), store=True)
    return path


def _linked(tmp_path, **kw):
    cool = _toy_cool(tmp_path / "toy.cool", **kw)
    cd = ChromData(np.zeros((0, 3)), pd.DataFrame({"chrom": pd.Series(dtype=str), "start": pd.Series(dtype=np.int64),
                                                   "end": pd.Series(dtype=np.int64), "trace_id": pd.Series(dtype=str)}),
                   uns={"genome_assembly": "toy1"})
    cd.link_cool(str(cool), key="bulk", genome_assembly="toy1")
    return cd, cool


def test_map_path_and_contact_matrix(tmp_path):
    cd, cool = _linked(tmp_path)
    assert map_path(cd) == map_path(cd, "bulk") == str(cool)
    assert map_path(str(cool)) == str(cool)
    bins, M = contact_matrix(cd, chrom="chrA")
    clr = cooler.Cooler(str(cool))
    assert len(bins) == 41 and list(bins.columns) == ["chrom", "start", "end"]
    assert np.allclose(M, np.nan_to_num(clr.matrix(balance=True).fetch("chrA")))
    _, raw = contact_matrix(cd, "bulk", chrom="chrB", balance=False)
    assert np.array_equal(raw, clr.matrix(balance=False).fetch("chrB"))
    with pytest.raises(ValueError, match="1000 bp, not 5000"):
        contact_matrix(cd, chrom="chrA", resolution=5000)
    cd.link_cool(str(cool), key="other")
    with pytest.raises(KeyError, match="pass contacts"):
        map_path(cd)
    with pytest.raises(KeyError, match="not a linked map"):
        map_path(cd, "missing")


def test_contact_matrix_unbalanced_map_warns(tmp_path):
    cd, _ = _linked(tmp_path, balance=False)
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        contact_matrix(cd, chrom="chrA")
    assert any("not balanced" in str(x.message) for x in w)


def test_rebin_map_at_zero_is_cooler_coarsen(tmp_path):
    cd, cool = _linked(tmp_path)
    path = rebin_map(cd, "bulk", resolution=5000, out=tmp_path / "new.cool")
    assert path == str(tmp_path / "new.cool")
    rec = cd.uns["linked_cool"]["bulk_5kb"]
    assert rec["bin_size"] == 5000 and rec["rebinned_from"] == "bulk" and rec["genome_assembly"] == "toy1"
    assert map_path(cd, "bulk_5kb") == str((tmp_path / "new.cool").resolve())
    ref = tmp_path / "ref.cool"
    cooler.coarsen_cooler(str(cool), str(ref), factor=5, chunksize=10_000_000)
    cooler.balance_cooler(cooler.Cooler(str(ref)), store=True)
    a, b = cooler.Cooler(path), cooler.Cooler(str(ref))
    assert a.bins()[["chrom", "start", "end"]][:].astype(str).equals(b.bins()[["chrom", "start", "end"]][:].astype(str))
    pa, pb = a.pixels()[:], b.pixels()[:]
    assert np.array_equal(pa[["bin1_id", "bin2_id"]].to_numpy(), pb[["bin1_id", "bin2_id"]].to_numpy())
    assert np.array_equal(pa["count"].to_numpy(), pb["count"].to_numpy())
    for c in SIZES:
        assert np.allclose(a.matrix(balance=True).fetch(c), b.matrix(balance=True).fetch(c), equal_nan=True)
    assert int(pa["count"].sum()) == int(cooler.Cooler(str(cool)).pixels()[:]["count"].sum())


def test_rebin_map_on_an_anchored_grid(tmp_path):
    cd, cool = _linked(tmp_path)
    out = rebin_map(cd, "bulk", resolution=3000, anchor=10_250, chrom="chrA", key_added="grid",
                    out=tmp_path / "grid.cool", balance=False)
    clr = cooler.Cooler(out)
    assert list(clr.chromnames) == ["chrA"]
    starts = clr.bins()[:]["start"].to_numpy()
    assert starts[:4].tolist() == [0, 1000, 4000, 7000]        # anchor 10,250 snaps to 10,000 = 1,000 mod 3,000
    assert clr.bins()[:]["end"].iloc[-1] == SIZES["chrA"]
    fine = cooler.Cooler(str(cool)).matrix(balance=False).fetch("chrA")
    coarse = clr.matrix(balance=False).fetch("chrA")
    edges = np.r_[starts, SIZES["chrA"]] // RES
    upper = np.add.reduceat(np.add.reduceat(np.triu(fine), edges[:-1], axis=0), edges[:-1], axis=1)
    expect = upper + upper.T - np.diag(np.diag(upper))         # every pair of loci counted once
    assert np.array_equal(coarse, expect)
    assert "weight" not in clr.bins().columns and cd.uns["linked_cool"]["grid"]["balanced"] is False


def test_rebin_map_options(tmp_path):
    cd, cool = _linked(tmp_path)
    new = rebin_map(cd, "bulk", resolution=2000, copy=True)
    assert "bulk_2kb" in new.uns["linked_cool"] and "bulk_2kb" not in cd.uns["linked_cool"]
    p = rebin_map(cd, "bulk", resolution=4000, key_added=None)
    assert "bulk_4kb" not in cd.uns["linked_cool"] and cooler.Cooler(p).binsize == 4000
    assert cooler.Cooler(rebin_map(str(cool), resolution=10_000)).binsize == 10_000
    with pytest.raises(ValueError, match="multiple"):
        rebin_map(cd, "bulk", resolution=2500)
    mcool = tmp_path / "toy.mcool"
    cooler.zoomify_cooler(str(cool), str(mcool), resolutions=[1000, 2000], chunksize=10_000_000)
    cd.link_cool(str(mcool), key="multi")
    out = rebin_map(cd, "multi", resolution=6000, balance=False)      # read from the 2 kb level
    assert cooler.Cooler(out).info["metadata"]["rebinned_from"].endswith("/resolutions/2000")
    assert contact_matrix(cd, "multi", chrom="chrB", resolution=2000)[1].shape == (12, 12)
    with pytest.raises(ValueError, match="pass resolution"):
        contact_matrix(cd, "multi", chrom="chrB")


def test_observed_over_expected():
    rng = np.random.default_rng(1)
    A = rng.uniform(1, 2, (6, 6))
    A = A + A.T
    A[1, 3] = A[3, 1] = 0.0
    oe = observed_over_expected(A)
    for k in range(1, 6):
        v = np.diagonal(A, k)
        pos = v > 0
        assert np.allclose(np.diagonal(oe, k)[pos], v[pos] / v[pos].mean())
    assert np.isnan(oe[1, 3]) and np.isnan(np.diagonal(oe)).all()
    assert np.allclose(observed_over_expected(A, positions=np.arange(6) * 7), oe, equal_nan=True)
    # a gap: rows at 0, 1, 2, 5 -> separations 1, 2, 3, 4, 5
    B = np.array([[0, 2, 4, 6], [2, 0, 8, 10], [4, 8, 0, 12], [6, 10, 12, 0]], dtype=float)
    g = observed_over_expected(B, positions=[0, 1, 2, 5])
    assert np.isclose(g[0, 1], 2 / 5) and np.isclose(g[1, 2], 8 / 5)       # separation 1: mean(2, 8)
    assert np.isclose(g[0, 2], 1.0) and np.isclose(g[2, 3], 1.0)           # separations 2 and 3: alone
    assert np.isclose(g[1, 3], 1.0) and np.isclose(g[0, 3], 1.0)           # 4, 5


def test_open_map_and_a_path_as_contacts(tmp_path):
    from uchrom.fea import open_map

    cd, cool = _linked(tmp_path)
    other = _toy_cool(tmp_path / "other.cool", seed=1)
    assert map_path(cd, str(other)) == str(other)                    # not a linked key: the path itself
    clr = open_map(cd, str(other))
    assert isinstance(clr, cooler.Cooler) and clr.binsize == RES
    assert open_map(cd).filename == str(cool)
    bins, M = contact_matrix(clr, chrom="chrA")                       # an open cooler
    _, M2 = contact_matrix(cd, str(other), chrom="chrA")
    assert np.array_equal(M, M2) and len(bins) == 41
    assert not np.array_equal(M, contact_matrix(cd, chrom="chrA")[1])
    with pytest.raises(KeyError, match="not a linked map"):
        map_path(cd, str(tmp_path / "missing.cool"))
    assert rebin_map(cd, str(other), resolution=5000, key_added=None).endswith("other.cool")


def test_thin_map(tmp_path):
    from uchrom.fea import thin_map

    cd, path = _linked(tmp_path)
    full = cooler.Cooler(str(path)).pixels()[:]
    out = thin_map(cd, "bulk", fraction=0.3, seed=1)
    rec = cd.uns["linked_cool"]["bulk_30pct"]
    assert rec["path"] == str(Path(out).resolve()) and rec["fraction"] == 0.3 and rec["thinned_from"] == "bulk" and rec["balanced"]
    clr = cooler.Cooler(out)
    assert clr.bins()[:][["chrom", "start", "end"]].equals(cooler.Cooler(str(path)).bins()[:][["chrom", "start", "end"]])
    thin = clr.pixels()[:].merge(full, on=["bin1_id", "bin2_id"], suffixes=("", "_full"))
    assert len(thin) == clr.info["nnz"] and (thin["count"] <= thin["count_full"]).all()   # a subset of the contacts
    assert clr.info["sum"] == pytest.approx(0.3 * full["count"].sum(), rel=0.05)
    assert "weight" in clr.bins().columns
    # the same seed gives the same map; n_contacts= sets the fraction; a raw thinned map
    again = thin_map(str(path), fraction=0.3, seed=1, out=tmp_path / "again.cool", key_added=None)
    assert cooler.Cooler(again).pixels()[:].equals(clr.pixels()[:])
    raw = thin_map(cd, "bulk", n_contacts=int(full["count"].sum()) // 10, balance=False, key_added="tenth")
    assert "weight" not in cooler.Cooler(raw).bins().columns
    assert cd.uns["linked_cool"]["tenth"]["fraction"] == pytest.approx(0.1, rel=1e-3)
    with pytest.raises(ValueError, match="exactly one"):
        thin_map(cd, "bulk")
    with pytest.raises(ValueError, match="not in"):
        thin_map(cd, "bulk", fraction=1.5)


def test_rebin_scool_sums_each_cells_pixels(tmp_path):
    import cooler
    from chromdata import ChromData
    from uchrom.fea import rebin_scool

    rng = np.random.default_rng(3)
    sizes = {"chr1": 95_000, "chr2": 42_000}
    res = 5_000
    bins = pd.concat([pd.DataFrame({"chrom": c, "start": np.arange(0, n, res)}) for c, n in sizes.items()],
                     ignore_index=True)
    bins["end"] = np.minimum(bins["start"] + res, bins["chrom"].map(sizes))
    maps = {}
    for cell in ("a", "b", "c"):
        b1 = rng.integers(0, len(bins), 300)
        b2 = rng.integers(0, len(bins), 300)
        px = pd.DataFrame({"bin1_id": np.minimum(b1, b2), "bin2_id": np.maximum(b1, b2), "count": rng.integers(1, 5, 300)})
        maps[cell] = px.groupby(["bin1_id", "bin2_id"], as_index=False)["count"].sum()
    src = tmp_path / "m.scool"
    cooler.create_scool(str(src), bins, maps, ordered=True, symmetric_upper=True)
    cells = pd.DataFrame(index=pd.Index(list(maps), name="cell_id"))
    empty = pd.DataFrame({"chrom": pd.Series([], dtype=str), "start": pd.Series([], dtype=np.int64),
                          "end": pd.Series([], dtype=np.int64), "trace_id": pd.Series([], dtype=str)})
    cd = ChromData(np.zeros((0, 3)), empty, cells=cells, uns={"genome_assembly": "test"})
    cd.link_scool(str(src), key="per_cell", cell_name="cell_id", bin_size=res)
    out = rebin_scool(cd, "per_cell", resolution=20_000, out=tmp_path / "m_20kb.scool")
    assert cd.uns["linked_scool"]["per_cell_20kb"]["bin_size"] == 20_000
    for cell, px in maps.items():
        got = cooler.Cooler(f"{out}::/cells/{cell}")
        assert got.binsize == 20_000 and int(got.pixels()[:]["count"].sum()) == int(px["count"].sum())
        # brute force: each fine bin into the coarse bin of its start
        coarse = got.bins()[:]
        key = {(c, s // 20_000): i for i, (c, s) in enumerate(zip(coarse["chrom"], coarse["start"]))}
        f = bins.iloc
        want = {}
        for b1, b2, n in px.itertuples(index=False):
            k = tuple(sorted((key[(f[b1]["chrom"], f[b1]["start"] // 20_000)], key[(f[b2]["chrom"], f[b2]["start"] // 20_000)])))
            want[k] = want.get(k, 0) + n
        g = got.pixels()[:]
        assert dict(zip(zip(g["bin1_id"], g["bin2_id"]), g["count"])) == want
    with pytest.raises(ValueError, match="multiple"):
        rebin_scool(cd, "per_cell", resolution=7_000, out=tmp_path / "x.scool")
