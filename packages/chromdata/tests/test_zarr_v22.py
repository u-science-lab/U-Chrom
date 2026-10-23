"""Format 2.2 of the ``.chromdata.zarr`` container: coordinates + keys stored
once, partitioned by chromosome; every other spot-aligned column in
cell-sorted primary tables; spot columns that are a function of the bin /
cell / trace stored once per key; lossless decimal encoding of floats.

Every test compares against the in-memory object (bitwise for floats)."""
import json

import numpy as np
import pandas as pd
import pyarrow.parquet as pq
import pytest

from chromdata.testing import (assert_same_small as _assert_same_small, assert_uns_equal as _assert_uns_equal,
                               example_chromdata as _cd, sorted_frame as _sorted_df, sorted_tracks as _sorted_tracks)
from chromdata import ChromData
from chromdata.zarrcd import derive_spot_columns, write_zarr


def _decimal_cd(n_cells=6, seed=0):
    """``_cd`` with coordinates / tracks that look measured (a few decimals,
    plus arithmetic noise, NaN, -0.0, a huge value) and spot columns that
    are functions of the bin, the cell or the trace."""
    cd = _cd(n_cells=n_cells, seed=seed)
    rng = np.random.default_rng(seed + 1)
    n = cd.n_spots
    co = np.round(rng.normal(100, 20, size=(n, 3)), 6)
    co[:, 2] = np.round(co[:, 2], 3) * 0.25          # arithmetic on decimals: ulp corrections
    co[[2, 7]] = np.nan
    co[5, 0] = -0.0
    co[6, 1] = 1e300
    cd.coords = co
    st = cd.spot_tracks
    st["IF"] = np.round(rng.normal(0, 2, n), 5) - np.round(rng.normal(0, 1, n), 5)
    st["plain"] = rng.normal(size=n)                      # full precision: stays float64
    cd.spot_tracks = st
    cd.layers["raw"] = np.round(co + 0.5, 4)
    s = cd.spots
    bid = s["bin_id"].to_numpy()
    s["name"] = np.array([f"{c}-{a}" for c, a in zip(cd.bins["chrom"], cd.bins["start"])], dtype=object)[bid]
    s["sample"] = "mouse_1"                                           # constant string
    s["fov"] = s["cell_id"].cat.codes.to_numpy().astype(np.int64) * 7 + 3   # a function of the cell
    s["allele"] = pd.Categorical(np.where(s["trace_id"].cat.codes.to_numpy() % 2, "a1", "a2"))  # of the trace
    s["order"] = (bid * 0.5).astype(np.float64)                        # float, of the bin
    cd.spots = s[[c for c in s.columns if c != "bin_id"] + ["bin_id"]]
    return cd


def _bits(a):
    return np.ascontiguousarray(a, dtype=np.float64).view(np.int64)


def _same(x, y):
    assert type(y) is ChromData
    pd.testing.assert_frame_equal(x.spots, y.spots)
    pd.testing.assert_frame_equal(x.to_dataframe(), y.to_dataframe())
    np.testing.assert_array_equal(_bits(x.coords), _bits(y.coords))
    pd.testing.assert_frame_equal(x.spot_tracks, y.spot_tracks)
    for c in x.spot_tracks.columns:
        if x.spot_tracks[c].dtype == np.float64:
            np.testing.assert_array_equal(_bits(x.spot_tracks[c]), _bits(y.spot_tracks[c]))
    pd.testing.assert_frame_equal(x.cells, y.cells)
    pd.testing.assert_frame_equal(x.traces, y.traces)
    assert list(x.layers) == list(y.layers)
    for k in x.layers:
        np.testing.assert_array_equal(_bits(x.layers[k]), _bits(y.layers[k]))


@pytest.fixture(params=["x.chromdata.zarr", "x.cdz"])
def store(request, tmp_path):
    cd = _decimal_cd()
    path = tmp_path / request.param
    write_zarr(cd, path, row_group_rows=40, coords_row_group_rows=10, _layout="2.2")
    return cd, path


def test_layout_and_encoding(tmp_path):
    cd = _decimal_cd()
    path = tmp_path / "x.chromdata.zarr"
    write_zarr(cd, path, row_group_rows=40, coords_row_group_rows=10, _layout="2.2", float_encoding=True)
    meta = json.loads((path / "zarr.json").read_text())["attributes"]["uchrom"]
    assert meta["format_version"] == "2.4" and meta["layout"] == "primary+coords"
    assert meta["spot_order"] == "cell,trace,chrom,bin" and meta["coords_order"] == "chrom,cell,trace,bin"
    t = path / "tables"
    assert (t / "primary" / "spots.parquet").exists() and (t / "primary" / "spot_tracks.parquet").exists()
    assert sorted(p.name for p in (t / "coords").iterdir()) == ["chrom=chr1", "chrom=chr2", "chrom=chrX"]
    import zarr
    root = zarr.open_group(str(path), mode="r")
    tmeta = root["tables"].attrs["tables"]
    enc = tmeta["coords"]["encoding"]
    assert set(enc) == {"x", "y", "z"} and enc["x"]["exp"] == 6
    assert "IF" in tmeta["spot_tracks"]["encoding"] and "plain" not in tmeta["spot_tracks"]["encoding"]
    # coordinates live only in the chromosome partitions (keys + x, y, z)
    part = t / "coords" / "chrom=chr1" / "part-0.parquet"
    assert set(pq.ParquetFile(part).schema_arrow.names) == {"bin_id", "trace_id", "cell_id", "x", "x#exc",
                                                             "y", "y#exc", "z", "z#exc"}
    assert str(pq.ParquetFile(part).schema_arrow.field("x").type) == "int64"
    prim = set(pq.ParquetFile(t / "primary" / "spots.parquet").schema_arrow.names)
    assert prim.isdisjoint({"x", "y", "z", "bin_id", "trace_id", "cell_id"})
    assert {"spot_id", "label", "quality", "coord_status"} <= prim
    # derived spot columns: one value per key, not per spot
    der = tmeta["spots"]["derived"]
    assert {c: d["key"] for c, d in der.items()} == {"name": "bin_id", "sample": "bin_id", "fov": "cell_id",
                                                     "allele": "trace_id", "order": "bin_id"}
    assert prim.isdisjoint(der)
    assert pq.ParquetFile(t / "derived" / "bin_id.parquet").metadata.num_rows == cd.n_bins
    # row groups of the primary hold whole cells; runs match one to one
    rg = root["index/row_groups"][:]
    assert set(rg) <= set(root["index/cell_offsets"][:])
    prun = root["index/coords/primary_run"][:]
    assert sorted(prun) == list(range(len(root["index/trace_offsets"][:]) - 1))


def test_round_trip_bitwise(store):
    cd, path = store
    back = ChromData.read(path)
    pd.testing.assert_frame_equal(_sorted_df(back), _sorted_df(cd))
    pd.testing.assert_frame_equal(_sorted_tracks(back), _sorted_tracks(cd))
    _assert_same_small(cd, back)
    _assert_uns_equal(cd.uns, back.uns)
    orig = ChromData.read(path, original_order=True)
    pd.testing.assert_frame_equal(orig.spots, cd.spots)
    assert orig.spots["name"].dtype == cd.spots["name"].dtype and orig.spots["fov"].dtype == np.int64
    np.testing.assert_array_equal(_bits(orig.spots["order"]), _bits(cd.spots["order"]))
    np.testing.assert_array_equal(_bits(orig.coords), _bits(cd.coords))
    for c in cd.spot_tracks.columns:
        if cd.spot_tracks[c].dtype == np.float64:
            np.testing.assert_array_equal(_bits(orig.spot_tracks[c]), _bits(cd.spot_tracks[c]))
    for k in cd.layers:
        np.testing.assert_array_equal(_bits(orig.layers[k]), _bits(cd.layers[k]))
    pd.testing.assert_frame_equal(orig.to_dataframe(), cd.to_dataframe())
    # in memory: the primary order (cell › trace › chromosome › bin)
    s = back.spots
    key = pd.DataFrame({"c": s["cell_id"].cat.codes, "t": s["trace_id"].cat.codes,
                        "ch": s["chrom"].cat.codes, "b": s["bin_id"]})
    assert key.equals(key.sort_values(["c", "t", "ch", "b"], kind="stable"))


def test_backed_matches_in_memory(store):
    cd, path = store
    mem = ChromData.read(path)
    bk = ChromData.read(path, backed=True)
    assert bk.has_coords_table and bk.format_version == "2.4" and not bk.partitioned
    _assert_same_small(mem, bk)
    for c in list(mem.spots["cell_id"].cat.categories) + ["nope"]:
        _same(mem.get_cell(c), bk.get_cell(c))
        _same(mem.get_cell(c, columns="coords"), bk.get_cell(c, columns="coords"))
    for t in mem.spots["trace_id"].cat.categories:
        _same(mem.get_trace(t), bk.get_trace(t))
    for ch in ("chr1", "chr2", "chrX", "chrM"):
        _same(mem.get_chrom(ch), bk.get_chrom(ch))
        _same(mem.get_chrom(ch, columns="coords"), bk.get_chrom(ch, columns="coords"))
        _same(mem.get_chrom(ch, columns=["IF", "name"]), bk.get_chrom(ch, columns=["IF", "name"]))
    rows = np.array([5, 0, 17, 3, 3])
    _same(mem[rows], bk[rows])
    _same(mem[10:40], bk[10:40])
    for batch in (1, 4, 100):
        for sel in (None, "coords"):
            got = list(bk.iter_traces(batch, columns=sel))
            ref = list(mem.iter_traces(batch, columns=sel))
            assert len(got) == len(ref)
            for x, y in zip(ref, got):
                _same(x, y)
            for ch in ("chr2", "chrX"):
                for x, y in zip(mem.iter_traces(batch, chrom=ch, columns=sel),
                                bk.iter_traces(batch, chrom=ch, columns=sel)):
                    _same(x, y)
    for b in (1, 2, 5):
        got, ref = list(bk.iter_cells(b)), list(mem.iter_cells(b))
        assert len(got) == len(ref)
        for x, y in zip(ref, got):
            _same(x, y)
    _same(mem, bk.to_memory())
    _same(mem.to_memory(columns="coords"), bk.to_memory(columns="coords"))
    _same(mem.to_memory(columns=["name", "fov"]), bk.to_memory(columns=["name", "fov"]))
    np.testing.assert_array_equal(_bits(np.asarray(bk.coords)), _bits(mem.coords))
    np.testing.assert_array_equal(_bits(bk.coords[[9, 1, 40]]), _bits(mem.coords[[9, 1, 40]]))
    np.testing.assert_array_equal(_bits(bk.coords[3:30]), _bits(mem.coords[3:30]))
    pd.testing.assert_frame_equal(bk.spot_tracks.to_pandas(), mem.spot_tracks)
    pd.testing.assert_frame_equal(bk.spots.to_pandas(), mem.spots)
    pd.testing.assert_frame_equal(bk.spots.iloc[[4, 2]], mem.spots.iloc[[4, 2]].reset_index(drop=True))
    pd.testing.assert_series_equal(bk.spots["name"], mem.spots["name"])
    pd.testing.assert_series_equal(bk.spots["bin_id"], mem.spots["bin_id"])          # key-only fast path
    pd.testing.assert_frame_equal(bk.spots.iloc[3:30][["bin_id", "chrom", "end"]],
                                  mem.spots.iloc[3:30][["bin_id", "chrom", "end"]].reset_index(drop=True))
    assert bk.spots.dtypes.to_dict() == mem.spots.dtypes.to_dict()


def test_trace_over_two_chromosomes(tmp_path):
    spots = pd.DataFrame({"chrom": ["chr1", "chr2", "chr1", "chr1", "chr2"], "start": [0, 0, 10, 0, 10],
                          "end": [10, 10, 20, 10, 20], "trace_id": [7, 7, 3, 3, 7]})
    cd = ChromData(np.round(np.arange(15.0).reshape(5, 3) * 0.1, 2), spots,
                   spot_tracks=pd.DataFrame({"s": [0.5, 1.25, 2.0, -3.5, 4.0]}))
    path = tmp_path / "a.chromdata.zarr"
    write_zarr(cd, path, _layout="2.2")
    mem = ChromData.read(path)
    bk = ChromData.read(path, backed=True)
    for ch in ("chr1", "chr2", "chrZ"):
        _same(mem.get_chrom(ch), bk.get_chrom(ch))
        _same(mem.get_chrom(ch, columns="coords"), bk.get_chrom(ch, columns="coords"))
    for sel in (None, "coords"):
        for x, y in zip(mem.iter_traces(1, columns=sel), bk.iter_traces(1, columns=sel)):
            _same(x, y)
    assert bk.get_trace(7).n_spots == 3
    _same(mem.get_trace(7), bk.get_trace(7))
    orig = ChromData.read(path, original_order=True)
    np.testing.assert_array_equal(_bits(orig.coords), _bits(cd.coords))


def test_empty_and_no_encoding(tmp_path):
    empty = ChromData(np.zeros((0, 3)), pd.DataFrame({"chrom": [], "start": [], "end": [], "trace_id": []}),
                      cells=pd.DataFrame({"n": [1, 2]}, index=pd.Index(["a", "b"], name="cell_id")))
    write_zarr(empty, tmp_path / "e.cdz", _layout="2.2")
    e = ChromData.read(tmp_path / "e.cdz")
    assert e.n_spots == 0 and list(e.cells.index) == ["a", "b"]
    bk = ChromData.read(tmp_path / "e.cdz", backed=True)
    assert bk.n_spots == 0 and bk.get_chrom("chr1", columns="coords").n_spots == 0
    cd = _decimal_cd()
    write_zarr(cd, tmp_path / "p.chromdata.zarr", _layout="2.2", float_encoding=False,
               normalize_spot_columns=False)
    back = ChromData.read(tmp_path / "p.chromdata.zarr", original_order=True)
    np.testing.assert_array_equal(_bits(back.coords), _bits(cd.coords))
    pd.testing.assert_frame_equal(back.spots, cd.spots)
    import zarr
    tmeta = zarr.open_group(str(tmp_path / "p.chromdata.zarr"), mode="r")["tables"].attrs["tables"]
    assert tmeta["coords"]["encoding"] == {} and tmeta["spots"]["derived"] == {}


def test_no_primary_tables(tmp_path):
    """Coordinates + keys only (every other column derived): no primary files."""
    cd = _cd()
    cd.spots = cd.spots[["chrom", "start", "end", "trace_id", "cell_id", "bin_id"]]
    cd.spot_tracks = pd.DataFrame(index=range(cd.n_spots))
    cd.layers = {}
    path = tmp_path / "k.chromdata.zarr"
    write_zarr(cd, path, _layout="2.2", coords_row_group_rows=16)
    assert not (path / "tables" / "primary").exists()
    back = ChromData.read(path, original_order=True)
    pd.testing.assert_frame_equal(back.spots, cd.spots)
    np.testing.assert_array_equal(_bits(back.coords), _bits(cd.coords))
    mem, bk = ChromData.read(path), ChromData.read(path, backed=True)
    for c in mem.spots["cell_id"].cat.categories:
        _same(mem.get_cell(c), bk.get_cell(c))
    _same(mem, bk.to_memory())


def test_derive_spot_columns_rules():
    n = 8
    bins = pd.DataFrame({"chrom": ["chr1"] * 4, "start": [0, 1, 2, 3], "end": [1, 2, 3, 4],
                         "name": ["b0", "b1", "b2", "b3"]})
    bid = np.array([0, 1, 2, 3, 0, 1, 2, 3])
    cell = np.array([0, 0, 0, 0, 1, 1, 1, 1])
    spots = pd.DataFrame({
        "name": np.array(["b0", "b1", "b2", "b3"] * 2, dtype=object),        # = bins.name
        "mixed": np.array(["a", None, "a", None] * 2, dtype=object),        # not all str: stays per spot
        "signed0": np.array([0.0, 1, 2, 3, -0.0, 1, 2, 3]),                 # -0.0 != 0.0 bitwise
        "percell": np.array([5, 5, 5, 5, 6, 6, 6, 6]),
        "nanbin": np.array([np.nan, 1, 2, 3, np.nan, 1, 2, 3]),             # NaN == NaN bitwise
    })
    d = derive_spot_columns(spots, list(spots.columns),
                            {"bin_id": (bid, 4), "cell_id": (cell, 2), "trace_id": (cell, 2)}, bins=bins)
    assert d["name"]["key"] == "bin_id" and d["name"]["bins_column"] == "name"
    assert "mixed" not in d and "signed0" not in d
    assert d["percell"]["key"] == "cell_id" and list(d["percell"]["values"]) == [5, 6]
    assert d["nanbin"]["key"] == "bin_id"


def test_bins_column_is_reused(tmp_path):
    cd = _cd()
    s = cd.spots
    cd.bins["probe"] = [f"p{i}" for i in range(cd.n_bins)]
    s["probe"] = cd.bins["probe"].to_numpy()[s["bin_id"].to_numpy()]
    cd.spots = s
    path = tmp_path / "b.chromdata.zarr"
    write_zarr(cd, path, _layout="2.2")
    import zarr
    tmeta = zarr.open_group(str(path), mode="r")["tables"].attrs["tables"]
    d = tmeta["spots"]["derived"]["probe"]
    assert d["key"] == "bin_id" and d["bins_column"] == "probe" and "file" not in d
    back = ChromData.read(path, original_order=True)
    pd.testing.assert_frame_equal(back.spots, cd.spots)
    pd.testing.assert_frame_equal(back.bins, cd.bins)


@pytest.mark.parametrize("n_chunks,budget", [(1, "1GB"), (5, "1KB"), (13, "20KB")])
@pytest.mark.parametrize("opts", [dict(float_encoding=True, float_dictionary=False),
                                  dict(float_encoding=False, float_dictionary=True)])
def test_streaming_writer_equals_in_memory_writer(tmp_path, n_chunks, budget, opts):
    """The streaming writer makes the store the in-memory writer makes."""
    import zarr

    from chromdata.testing import stream_write as _stream

    cd = _decimal_cd(n_cells=6)
    write_zarr(cd, tmp_path / "mem.chromdata.zarr", row_group_rows=20, coords_row_group_rows=8, _layout="2.2",
               **opts)
    _stream(cd, tmp_path / "st.chromdata.zarr", n_chunks=n_chunks, budget=budget, row_group_rows=20,
            coords_row_group_rows=8, layout="2.2", **opts)
    a, b = ChromData.read(tmp_path / "mem.chromdata.zarr"), ChromData.read(tmp_path / "st.chromdata.zarr")
    _same(a, b)
    _assert_same_small(a, b)
    ra = zarr.open_group(str(tmp_path / "mem.chromdata.zarr"), mode="r")
    rb = zarr.open_group(str(tmp_path / "st.chromdata.zarr"), mode="r")
    for grp in ("index", "index/coords"):
        for name in ra[grp].array_keys():
            np.testing.assert_array_equal(ra[f"{grp}/{name}"][:], rb[f"{grp}/{name}"][:], err_msg=f"{grp}/{name}")
    ta, tb = ra["tables"].attrs["tables"], rb["tables"].attrs["tables"]
    for key in ("coords", "primary", "spots", "layer_encoding"):
        assert ta[key] == tb[key], key
    assert {k: v for k, v in ta["spot_tracks"].items() if k != "spot_view_order"} == \
        {k: v for k, v in tb["spot_tracks"].items() if k != "spot_view_order"}
    ref = ChromData.read(tmp_path / "st.chromdata.zarr", original_order=True)
    pd.testing.assert_frame_equal(ref.spots, cd.spots)
    np.testing.assert_array_equal(_bits(ref.coords), _bits(cd.coords))


def test_sorted_rewrite_and_default_layout(tmp_path):
    """2.2 is the default; rewriting a store read in stored order keeps the
    order and stores no permutation."""
    cd = _decimal_cd()
    cd.write(tmp_path / "a.chromdata.zarr")
    back = ChromData.read(tmp_path / "a.chromdata.zarr")
    meta = json.loads((tmp_path / "a.chromdata.zarr" / "zarr.json").read_text())["attributes"]["uchrom"]
    assert meta["format_version"] == "2.4" and meta["has_source_row"]
    back.write(tmp_path / "b.chromdata.zarr")
    meta2 = json.loads((tmp_path / "b.chromdata.zarr" / "zarr.json").read_text())["attributes"]["uchrom"]
    assert not meta2["has_source_row"]
    _same(back, ChromData.read(tmp_path / "b.chromdata.zarr"))
