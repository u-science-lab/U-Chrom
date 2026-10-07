"""Exact streaming distance maps (``uchrom.fea.distance_map``) against the
dense in-memory reference (``mean_distance_matrix``)."""
import numpy as np
import pandas as pd
import pytest

from uchrom import ChromData
from uchrom.fea import distance_map, mean_distance_matrix


def _tracing(n_cells=7, n_bins=12, seed=0):
    rng = np.random.default_rng(seed)
    rows = []
    for c in rng.permutation(n_cells):
        for chrom in ("chr2", "chr1"):
            for a in range(2):                              # two homologs
                obs = np.sort(rng.choice(n_bins, rng.integers(2, n_bins), replace=False))
                obs = rng.permutation(np.r_[obs, rng.choice(obs, 2)])   # duplicated loci
                for b in obs:
                    rows.append((chrom, int(b) * 1000, int(b) * 1000 + 1000, f"c{c}_{chrom}_{a}", f"c{c}"))
    spots = pd.DataFrame(rows, columns=["chrom", "start", "end", "trace_id", "cell_id"])
    coords = rng.normal(size=(len(spots), 3)) * 3
    coords[rng.choice(len(spots), 5, replace=False), rng.integers(0, 3, 5)] = np.nan
    return ChromData(coords, spots)


def _dense(cd, chrom, reduce):
    # the dense reference pivots the stored order (last duplicate wins)
    df = cd.to_dataframe()
    with np.errstate(all="ignore"), pd.option_context("mode.chained_assignment", None):
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            return mean_distance_matrix(df, chrom=chrom, reduce=reduce)


@pytest.mark.parametrize("stat", ["median", "mean"])
def test_distance_map_equals_dense_reference(tmp_path, stat):
    cd = _tracing()
    path = tmp_path / "t.chromdata.zarr"
    cd.write(path, row_group_rows=16)
    mem = ChromData.read(path)
    bk = ChromData.read(path, backed=True)
    for chrom in ("chr1", "chr2"):
        ref, bins, n_traces = _dense(mem, chrom, stat)
        variants = [distance_map(mem, chrom, stat, streaming=False),
                    distance_map(cd, chrom, stat, streaming=False),         # unsorted object
                    distance_map(bk, chrom, stat, batch=3, memory_budget=2_000),   # many bands
                    distance_map(bk, chrom, stat)]
        for res in variants:
            assert res.n_traces == n_traces
            assert list(zip(res.bins["start"], res.bins["end"])) == bins
            np.testing.assert_array_equal(res.matrix, ref)            # bitwise, NaN == NaN
            assert (res.count == res.count.T).all()
        if stat == "median":
            assert variants[2].n_bands > 1 and variants[2].n_passes == variants[2].n_bands + 1
            assert variants[0].n_bands == 1


def test_distance_map_all_bins_and_errors(tmp_path):
    cd = _tracing(n_cells=3)
    res = distance_map(cd, "chr1", observed=False)
    assert res.matrix.shape == (int((cd.bins["chrom"] == "chr1").sum()),) * 2
    with pytest.raises(ValueError, match="stat"):
        distance_map(cd, "chr1", "max")
    with pytest.raises(ValueError, match="No spots"):
        distance_map(cd, "chrZ")


@pytest.mark.parametrize("how", ["last", "first", "mean", "median"])
def test_distance_map_duplicates_equal_merge_duplicate_spots(tmp_path, how):
    from uchrom.im import merge_duplicate_spots

    cd = _tracing()
    assert cd.spots.duplicated(["trace_id", "bin_id"]).any()
    path = tmp_path / "t.chromdata.zarr"
    cd.write(path, row_group_rows=16)
    bk = ChromData.read(path, backed=True)
    merged = merge_duplicate_spots(cd, how=how)
    for chrom in ("chr1", "chr2"):
        for stat in ("median", "mean"):
            ref = distance_map(merged, chrom, stat)
            for res in (distance_map(cd, chrom, stat, duplicates=how),
                        distance_map(bk, chrom, stat, duplicates=how, batch=3, memory_budget=2_000)):
                np.testing.assert_array_equal(res.matrix, ref.matrix)
                np.testing.assert_array_equal(res.count, ref.count)
                assert res.duplicates == how
    with pytest.raises(ValueError, match="duplicates"):
        distance_map(cd, "chr1", duplicates="max")


def test_distance_map_selection_and_chrom_inference():
    cd = _tracing()
    traces = [t for t in cd.spots["trace_id"].astype(str).unique() if t.endswith("_0")]
    sub = cd[cd.spots["trace_id"].astype(str).isin(traces).to_numpy()]
    np.testing.assert_array_equal(distance_map(cd, "chr1", trace_ids=traces).matrix,
                                  distance_map(sub, "chr1").matrix)
    cells = ["c0", "c3"]
    np.testing.assert_array_equal(distance_map(cd, "chr2", cells=cells).matrix,
                                  distance_map(cd.get_cells(cells), "chr2").matrix)
    with pytest.raises(ValueError, match="pass chrom="):
        distance_map(cd)
    one = cd.get_chrom("chr2")
    np.testing.assert_array_equal(distance_map(one).matrix, distance_map(cd, "chr2").matrix)


def test_contact_frequency_and_rg_take_a_chromdata(tmp_path):
    from uchrom.fea import contact_frequency, radius_of_gyration

    cd = _tracing()
    path = tmp_path / "t.chromdata.zarr"
    cd.write(path, row_group_rows=16)
    bk = ChromData.read(path, backed=True)
    for chrom in ("chr1", "chr2"):
        ref, bins, n = contact_frequency(cd.to_dataframe(), 3.0, chrom=chrom)        # the dense table form
        for data, kw in ((cd, {}), (bk, {"batch": 2, "memory_budget": 2_000})):
            freq, b, m = contact_frequency(data, 3.0, chrom=chrom, **kw)
            np.testing.assert_array_equal(freq, ref)
            assert b == bins and m == n
        rg = radius_of_gyration(cd, chrom=chrom)
        table = cd.to_dataframe().dropna(subset=["x", "y", "z"])             # the ChromData form skips NaN spots
        pd.testing.assert_series_equal(rg, radius_of_gyration(table, chrom=chrom))
        pd.testing.assert_series_equal(radius_of_gyration(bk, chrom=chrom), rg)
        ref_m = _dense(cd, chrom, "median")[0]
        np.testing.assert_array_equal(mean_distance_matrix(cd, chrom=chrom)[0], ref_m)
    sel = ["c1"]
    f1 = contact_frequency(cd, 3.0, chrom="chr1", cells=sel)
    f2 = contact_frequency(cd.to_dataframe(), 3.0, chrom="chr1", cells=sel)
    np.testing.assert_array_equal(f1[0], f2[0])
    all_rg = radius_of_gyration(cd)
    assert len(all_rg) == cd.spots["trace_id"].nunique()
    merged_cf = contact_frequency(cd, 3.0, chrom="chr1", duplicates="mean")[0]
    from uchrom.im import merge_duplicate_spots
    np.testing.assert_array_equal(merged_cf, contact_frequency(merge_duplicate_spots(cd), 3.0, chrom="chr1")[0])
    with pytest.raises(ValueError, match="needs a ChromData"):
        contact_frequency(cd.to_dataframe(), 3.0, chrom="chr1", duplicates="mean")
    with pytest.raises(ValueError, match="pass chrom="):
        contact_frequency(cd, 3.0)


def test_distance_map_coarsen():
    cd = _tracing(n_bins=12)
    dm = distance_map(cd, "chr1")
    n = len(dm.matrix)
    c = dm.coarsen(5)
    nb = -(-n // 5)
    assert c.matrix.shape == (nb, nb) and c.block_size == 5 and c.n_traces == dm.n_traces
    assert list(c.bins["n_bins"]) == [min(5, n - 5 * k) for k in range(nb)]
    assert c.bins["start"].iloc[0] == dm.bins["start"].iloc[0] and c.bins["end"].iloc[-1] == dm.bins["end"].iloc[-1]
    m = dm.matrix.copy()
    np.fill_diagonal(m, np.nan)
    for a in range(nb):
        for b in range(nb):
            block = m[5 * a:5 * a + 5, 5 * b:5 * b + 5]
            want = np.nanmedian(block) if np.isfinite(block).any() else np.nan
            np.testing.assert_equal(c.matrix[a, b], want)
    cnt = dm.count.copy()
    np.fill_diagonal(cnt, 0)
    assert c.count[0, 1] == cnt[:5, 5:10].sum()
    with_diag = dm.coarsen(5, stat="mean", diagonal=True)
    assert with_diag.matrix[0, 0] == pytest.approx(np.nanmean(dm.matrix[:5, :5]))
    assert np.array_equal(dm.coarsen(1).matrix[~np.eye(n, dtype=bool)], dm.matrix[~np.eye(n, dtype=bool)],
                          equal_nan=True)
    with pytest.raises(ValueError):
        dm.coarsen(0)


def test_trace_distance_matrix():
    from uchrom.fea import trace_distance_matrix
    from uchrom.im import merge_duplicate_spots

    cd = _tracing(n_cells=3)
    counts = cd.spots.groupby("trace_id", observed=True)["bin_id"].agg(lambda s: s.duplicated().sum())
    tid = counts.idxmax()
    assert counts[tid] > 0                                  # a trace with a repeated locus
    chrom = str(cd.get_trace(tid).spots_with_loci()["chrom"].iloc[0])
    for how in ("last", "first", "mean", "median"):
        d, loci = trace_distance_matrix(cd, tid, duplicates=how)
        assert list(loci.columns) == ["bin_id", "chrom", "start", "end"]
        assert len(loci) == int((cd.bins["chrom"] == chrom).sum()) and loci["start"].is_monotonic_increasing
        ref = distance_map(merge_duplicate_spots(cd, how=how).get_trace(tid), chrom, observed=False)
        np.testing.assert_array_equal(np.diag(d) == 0, np.isfinite(np.diag(ref.matrix)))
        off = ~np.eye(len(d), dtype=bool)
        np.testing.assert_allclose(d[off], ref.matrix[off], rtol=1e-12)
    ints = ChromData(np.zeros((2, 3)), pd.DataFrame({"chrom": "chr1", "start": [0, 1000], "end": [1000, 2000],
                                                     "trace_id": [12, 12]}))
    d, _ = trace_distance_matrix(ints, "12")
    assert d.shape == (2, 2)
    with pytest.raises(KeyError):
        trace_distance_matrix(cd, "no-such-trace")
