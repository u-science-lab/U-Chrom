"""Format 2.2 of the ``.chromdata.zarr`` container: a cell-sorted primary
(all columns) + a coordinate projection partitioned by chromosome, and the
lossless decimal encoding of float columns.

Every test compares against the in-memory object (bitwise for floats)."""
import json

import numpy as np
import pandas as pd
import pyarrow.parquet as pq
import pytest

from tests.core.test_zarr_format import _assert_same_small, _assert_uns_equal, _cd, _sorted_df, _sorted_tracks
from uchrom import ChromData
from uchrom.core.zarrcd import write_zarr


def _decimal_cd(n_cells=6, seed=0):
    """``_cd`` with coordinates / tracks that look measured (a few decimals,
    plus arithmetic noise, NaN, -0.0, a huge value)."""
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
    return cd


def _bits(a):
    return np.ascontiguousarray(a, dtype=np.float64).view(np.int64)


def _same(x, y):
    assert type(y) is ChromData
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
    write_zarr(cd, path, row_group_rows=40, projection_row_group_rows=10, _layout="2.2")
    return cd, path


def test_layout_and_encoding(tmp_path):
    cd = _decimal_cd()
    path = tmp_path / "x.chromdata.zarr"
    write_zarr(cd, path, row_group_rows=40, projection_row_group_rows=10, _layout="2.2")
    meta = json.loads((path / "zarr.json").read_text())["attributes"]["uchrom"]
    assert meta["format_version"] == "2.2" and meta["layout"] == "primary+projection"
    assert meta["spot_order"] == "cell,trace,bin" and meta["projection_order"] == "chrom,cell,trace,bin"
    t = path / "tables"
    assert (t / "spots.parquet").exists() and (t / "spot_tracks.parquet").exists()
    assert sorted(p.name for p in (t / "coords_by_chrom").iterdir()) == ["chrom=chr1", "chrom=chr2", "chrom=chrX"]
    import zarr
    root = zarr.open_group(str(path), mode="r")
    tmeta = root["tables"].attrs["tables"]
    enc = tmeta["spots"]["encoding"]
    assert set(enc) == {"x", "y", "z"} and enc["x"]["exp"] == 6
    assert "IF" in tmeta["spot_tracks"]["encoding"] and "plain" not in tmeta["spot_tracks"]["encoding"]
    names = pq.ParquetFile(t / "spots.parquet").schema_arrow.names
    assert {"x", "x#ulp", "x#exc"} <= set(names)
    assert str(pq.ParquetFile(t / "spots.parquet").schema_arrow.field("x").type) == "int32"
    # projection: keys + coordinates only
    part = t / "coords_by_chrom" / "chrom=chr1" / "part-0.parquet"
    assert set(pq.ParquetFile(part).schema_arrow.names) == {"bin_id", "trace_id", "cell_id", "x", "x#ulp",
                                                             "x#exc", "y", "y#ulp", "y#exc", "z", "z#ulp", "z#exc"}
    # row groups of the primary hold whole cells
    rg = root["index/row_groups"][:]
    assert set(rg) <= set(root["index/cell_offsets"][:])
    # projection row i of chromosome c = the i-th primary row of c
    pi = root["index/coords_by_chrom/trace_offsets"][:]
    prun = root["index/coords_by_chrom/primary_run"][:]
    assert len(prun) == len(pi) - 1


def test_round_trip_bitwise(store):
    cd, path = store
    back = ChromData.read(path)
    pd.testing.assert_frame_equal(_sorted_df(back), _sorted_df(cd))
    pd.testing.assert_frame_equal(_sorted_tracks(back), _sorted_tracks(cd))
    _assert_same_small(cd, back)
    _assert_uns_equal(cd.uns, back.uns)
    orig = ChromData.read(path, original_order=True)
    np.testing.assert_array_equal(_bits(orig.coords), _bits(cd.coords))
    for c in cd.spot_tracks.columns:
        if cd.spot_tracks[c].dtype == np.float64:
            np.testing.assert_array_equal(_bits(orig.spot_tracks[c]), _bits(cd.spot_tracks[c]))
    for k in cd.layers:
        np.testing.assert_array_equal(_bits(orig.layers[k]), _bits(cd.layers[k]))
    pd.testing.assert_frame_equal(orig.to_dataframe(), cd.to_dataframe())
    # in memory: the 2.0 order (cell › trace › bin)
    s = back.spots
    key = pd.DataFrame({"c": s["cell_id"].cat.codes, "t": s["trace_id"].cat.codes, "b": s["bin_id"]})
    assert key.equals(key.sort_values(["c", "t", "b"], kind="stable"))


def test_backed_matches_in_memory(store):
    cd, path = store
    mem = ChromData.read(path)
    bk = ChromData.read(path, backed=True)
    assert bk.has_projection and bk.format_version == "2.2" and not bk.partitioned
    _assert_same_small(mem, bk)
    for c in list(mem.spots["cell_id"].cat.categories) + ["nope"]:
        _same(mem.get_cell(c), bk.get_cell(c))
        _same(mem.get_cell(c, columns="coords"), bk.get_cell(c, columns="coords"))
    for t in mem.spots["trace_id"].cat.categories:
        _same(mem.get_trace(t), bk.get_trace(t))
    for ch in ("chr1", "chr2", "chrX", "chrM"):
        _same(mem.get_chrom(ch), bk.get_chrom(ch))                               # primary, via the index
        _same(mem.get_chrom(ch, columns="coords"), bk.get_chrom(ch, columns="coords"))   # projection
        _same(mem.get_chrom(ch, columns=["IF"]), bk.get_chrom(ch, columns=["IF"]))
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
    for x, y in zip(mem.iter_cells(2), bk.iter_cells(2)):
        _same(x, y)
    _same(mem, bk.to_memory())
    _same(mem.to_memory(columns="coords"), bk.to_memory(columns="coords"))
    np.testing.assert_array_equal(_bits(np.asarray(bk.coords)), _bits(mem.coords))
    np.testing.assert_array_equal(_bits(bk.coords[[9, 1, 40]]), _bits(mem.coords[[9, 1, 40]]))
    pd.testing.assert_frame_equal(bk.spot_tracks.to_pandas(), mem.spot_tracks)
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


def test_empty_and_no_encoding(tmp_path):
    empty = ChromData(np.zeros((0, 3)), pd.DataFrame({"chrom": [], "start": [], "end": [], "trace_id": []}),
                      cells=pd.DataFrame({"n": [1, 2]}, index=pd.Index(["a", "b"], name="cell_id")))
    write_zarr(empty, tmp_path / "e.cdz", _layout="2.2")
    e = ChromData.read(tmp_path / "e.cdz")
    assert e.n_spots == 0 and list(e.cells.index) == ["a", "b"]
    bk = ChromData.read(tmp_path / "e.cdz", backed=True)
    assert bk.n_spots == 0 and bk.get_chrom("chr1", columns="coords").n_spots == 0
    cd = _decimal_cd()
    write_zarr(cd, tmp_path / "p.chromdata.zarr", _layout="2.2", float_encoding=False)
    back = ChromData.read(tmp_path / "p.chromdata.zarr", original_order=True)
    np.testing.assert_array_equal(_bits(back.coords), _bits(cd.coords))
    import zarr
    tmeta = zarr.open_group(str(tmp_path / "p.chromdata.zarr"), mode="r")["tables"].attrs["tables"]
    assert tmeta["spots"]["encoding"] == {}
