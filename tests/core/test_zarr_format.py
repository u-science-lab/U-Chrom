"""The ``.chromdata.zarr`` / ``.cdz`` container (format 2.0): round trips,
row order, backed mode, dispatch by path and conversion from ``.h5cd``.

Row order: the zarr writer stores spots sorted by (cell, trace, bin), so a
round trip returns the same spots in another order.  Tests compare
``to_dataframe()`` after sorting by a stable key (``spot_id``), or read with
``original_order=True``, which must be exactly equal.
"""
import json
import shutil
import warnings
import zipfile

import numpy as np
import pandas as pd
import pyarrow.parquet as pq
import pytest

from tests._v1 import write_v1
from uchrom import ChromData
from uchrom.core.zarrcd import write_zarr
from uchrom.core.backed import BackedArray, BackedChromData, BackedFrame
from uchrom.core.zarrcd import container_kind, write_zarr

FORMATS = ["x.chromdata.zarr", "x.cdz"]


def _cd(n_cells=4, seed=0) -> ChromData:
    """Unsorted multi-cell data exercising every attribute."""
    rng = np.random.default_rng(seed)
    rows = []
    for c in rng.permutation(n_cells):
        for t in range(3):
            chrom = ["chr2", "chr1", "chrX"][t]
            for b in rng.permutation(6):
                rows.append((chrom, b * 1000, b * 1000 + 1000, f"c{c}_t{t}", f"c{c}"))
    spots = pd.DataFrame(rows, columns=["chrom", "start", "end", "trace_id", "cell_id"])
    n = len(spots)
    spots["spot_id"] = rng.permutation(n)
    spots["label"] = rng.choice(["a", "b", None], n)
    spots["quality"] = rng.random(n)
    spots["coord_status"] = pd.Categorical(rng.choice(["measured", "imputed"], n))
    coords = rng.normal(size=(n, 3))
    coords[[2, 7]] = np.nan
    cells = pd.DataFrame({"cell_type": pd.Categorical(["A", "B"] * (n_cells // 2)),
                          "volume": rng.random(n_cells)},
                         index=pd.Index([f"c{i}" for i in range(n_cells)], name="cell_id"))
    traces = pd.DataFrame({"allele": rng.integers(0, 2, 3 * n_cells)},
                          index=pd.Index([f"c{c}_t{t}" for c in range(n_cells) for t in range(3)],
                                         name="trace_id"))
    cd = ChromData(
        coords, spots, cells=cells, traces=traces,
        cellm={"umap": rng.normal(size=(n_cells, 2)), "X_emb": rng.random((n_cells, 5)).astype(np.float32)},
        spot_tracks=pd.DataFrame({"IF": rng.normal(size=n), "z": rng.integers(0, 9, n),
                                  "grp": pd.Categorical(rng.choice(["x", "y"], n))}),
        layers={"raw": coords + 1, "Raw": coords * 2},     # case-insensitive clash on disk
        uns={"genome_assembly": "mm10",
             "linked_scool": {"cells": {"path": "c.scool", "format": "scool", "bin_size": 1000000}},
             "xyz_unit": "um", "fovs": [0, 1], "tup": (1, "a"),
             "big": np.arange(500.0), "small": np.arange(3), "names": np.array(["p", "q"]),
             "nested": {"a": 1, "b": {"c": [1.5, None]}, "arr": np.ones((10, 10))},
             "nan": float("nan"),
             "linked_cool": {"bulk": {"path": "bulk.mcool", "format": "mcool", "label": "Bulk"}},
             "linked_anndata": {"path": "rna.h5ad", "obs_key": "cell_id"}},
        points={"rna": pd.DataFrame({"x": [1.0, 2.0], "y": [2.0, 3.0], "z": [3.0, 4.0],
                                     "cell_id": ["c1", "c2"], "gene": ["Actb", "Gapdh"]})},
    )
    cd.bin_tracks = pd.DataFrame({"atac": np.arange(cd.n_bins, dtype=float),
                                  "label": [f"b{i}" for i in range(cd.n_bins)]})
    cd.binm["loading"] = rng.normal(size=(cd.n_bins, 2))
    cd.intervals["tads"] = pd.DataFrame({"chrom": ["chr1"], "start": [0], "end": [3000], "score": [0.5]})
    cd.results.set("tads", cd.intervals["tads"], kind="intervals", function="uchrom.x.f",
                   params={"window": 3, "nan": float("nan")}, inputs={"chrom": ["chr1"]})
    cd.results["table"] = pd.DataFrame({"a": [1, 2], "b": ["x", "y"]}, index=pd.Index([5, 6], name="k"))
    cd.results["series"] = pd.Series([1.0, 2.0], name="s")
    cd.results["arr"] = np.arange(6).reshape(2, 3)
    cd.results["bools"] = np.array([True, False])
    cd.results["strings"] = np.array(["u", "v"])
    cd.results["scalar"] = 3.5
    cd.results["tup"] = (1, 2)
    cd.results["ensemble"] = {"chr1": {"mask": np.ones((2, 2), dtype=bool), "n_traces": 3},
                              "Chr1": {"n": 1}, "__odd": 2}     # names escaped on disk
    cd.results["empty"] = pd.DataFrame({"x": pd.Series([], dtype=float)})
    return cd


def _sorted_df(cd):
    return cd.to_dataframe().sort_values("spot_id").reset_index(drop=True)


def _sorted_tracks(cd):
    df = cd.tracks_spot_view()
    df["spot_id"] = cd.spots["spot_id"].to_numpy()
    return df.sort_values("spot_id").reset_index(drop=True)


def _assert_same_small(a, b):
    pd.testing.assert_frame_equal(a.bins, b.bins)
    pd.testing.assert_frame_equal(a.bin_tracks, b.bin_tracks)
    pd.testing.assert_frame_equal(a.cells, b.cells)
    pd.testing.assert_frame_equal(a.traces, b.traces)
    assert list(a.cellm) == list(b.cellm)
    for k in a.cellm:
        np.testing.assert_array_equal(a.cellm[k], b.cellm[k])
        assert a.cellm[k].dtype == b.cellm[k].dtype
    for k in a.binm:
        np.testing.assert_array_equal(a.binm[k], b.binm[k])
    assert list(a.intervals) == list(b.intervals)
    for k in a.intervals:
        pd.testing.assert_frame_equal(pd.DataFrame(a.intervals[k]), pd.DataFrame(b.intervals[k]))
        assert (a.intervals[k].kind, a.intervals[k].source_result) == \
            (b.intervals[k].kind, b.intervals[k].source_result)
    assert list(a.results) == list(b.results)
    assert a.results == b.results
    for k in a.results:
        ra, rb = a.results.record(k), b.results.record(k)
        pa_, pb_ = ra.provenance, rb.provenance
        assert json.dumps(pa_, sort_keys=True) == json.dumps(pb_, sort_keys=True)
    assert list(a.points) == list(b.points)
    for k in a.points:
        pd.testing.assert_frame_equal(a.points[k], b.points[k])


def _assert_uns_equal(a, b):
    assert list(a) == list(b)
    for k in a:
        x, y = a[k], b[k]
        if isinstance(x, np.ndarray):
            assert isinstance(y, np.ndarray) and x.dtype == y.dtype
            np.testing.assert_array_equal(x, y)
        elif isinstance(x, dict):
            _assert_uns_equal(x, y)
        elif isinstance(x, float) and np.isnan(x):
            assert np.isnan(y)
        else:
            assert x == y and type(x) is type(y), (k, x, y)


# ----------------------------------------------------------------- round trip

@pytest.mark.parametrize("name", FORMATS)
def test_round_trip_every_attribute(tmp_path, name):
    cd = _cd()
    path = tmp_path / name
    cd.write(path)
    back = ChromData.read(path)
    assert type(back) is ChromData and back.n_spots == cd.n_spots
    # same spots, sorted on disk: compare by spot identity
    pd.testing.assert_frame_equal(_sorted_df(back), _sorted_df(cd))
    pd.testing.assert_frame_equal(_sorted_tracks(back), _sorted_tracks(cd))
    assert back.spot_tracks["grp"].dtype == "category"
    assert list(back.spots.columns) == list(cd.spots.columns)
    _assert_same_small(cd, back)
    _assert_uns_equal(cd.uns, back.uns)
    assert back.results["tads"] is back.intervals["tads"]
    assert back.linked_adata is None and back.uns["linked_anndata"]["path"] == "rna.h5ad"
    for k in cd.layers:
        order = np.argsort(back.spots["spot_id"].to_numpy())
        ref = np.argsort(cd.spots["spot_id"].to_numpy())
        np.testing.assert_array_equal(back.layers[k][order], cd.layers[k][ref])

    # the object as written, row for row
    orig = ChromData.read(path, original_order=True)
    pd.testing.assert_frame_equal(orig.to_dataframe(), cd.to_dataframe())
    pd.testing.assert_frame_equal(orig.spot_tracks, cd.spot_tracks)
    np.testing.assert_array_equal(orig.coords, cd.coords)
    for k in cd.layers:
        np.testing.assert_array_equal(orig.layers[k], cd.layers[k])


def test_disk_order_and_index(tmp_path):
    cd = _cd()
    path = tmp_path / "x.chromdata.zarr"
    write_zarr(cd, path, row_group_rows=10, _layout="2.1")      # the 2.1 layout (2.2: test_zarr_v22.py)
    back = ChromData.read(path)
    s = back.spots
    chrom = back.bins["chrom"].cat.codes.to_numpy()[s["bin_id"].to_numpy()]
    key = pd.DataFrame({"ch": chrom, "c": s["cell_id"].cat.codes, "t": s["trace_id"].cat.codes,
                        "b": s["bin_id"]})
    assert key.equals(key.sort_values(["ch", "c", "t", "b"], kind="stable"))
    meta = json.loads((path / "zarr.json").read_text())["attributes"]["uchrom"]
    assert meta["format_version"] == "2.1" and meta["spot_order"] == "chrom,cell,trace,bin"
    assert meta["layout"] == "partitioned" and meta["n_partitions"] == 3
    assert meta["has_source_row"] and meta["n_cells"] == 4 and meta["n_traces"] == 12
    # one directory per chromosome, in chromosome category order
    import zarr
    root = zarr.open_group(str(path), mode="r")
    assert sorted(p.name for p in (path / "tables" / "spots").iterdir()) == \
        ["chrom=chr1", "chrom=chr2", "chrom=chrX"]
    poff = root["index/partition_offsets"][:]
    pgrp = root["index/partition_groups"][:]
    pch = root["index/partition_chrom"][:]
    names = list(back.bins["chrom"].cat.categories)
    assert [names[c] for c in pch] == ["chr1", "chr2", "chrX"]
    np.testing.assert_array_equal(np.diff(poff), [24, 24, 24])
    # row groups hold whole cells of one partition, and every spot-aligned
    # table shares them
    rg = root["index/row_groups"][:]
    cell_off = root["index/cell_offsets"][:]
    assert set(rg) <= set(cell_off) and set(poff) <= set(rg)
    assert len(cell_off) - 1 == 12 and len(root["index/cell_codes"][:]) == 12      # (chrom, cell) runs
    np.testing.assert_array_equal(root["index/cell_partition"][:], np.repeat([0, 1, 2], 4))
    tmeta = root["tables"].attrs["tables"]
    for p, part in enumerate(tmeta["partitions"]):
        for f in ("spots", "spot_tracks", "layers/raw"):
            md = pq.ParquetFile(path / "tables" / part["files"][f]).metadata
            assert [md.row_group(i).num_rows for i in range(md.num_row_groups)] == \
                list(np.diff(rg[pgrp[p]:pgrp[p + 1] + 1]))
    spots0 = path / "tables" / tmeta["partitions"][0]["files"]["spots"]
    assert pq.ParquetFile(spots0).metadata.row_group(0).column(0).compression == "ZSTD"
    # writing an already sorted object keeps the order and stores no permutation
    write_zarr(back, tmp_path / "y.chromdata.zarr", _layout="2.1")
    meta2 = json.loads((tmp_path / "y.chromdata.zarr" / "zarr.json").read_text())["attributes"]["uchrom"]
    assert not meta2["has_source_row"]
    again = ChromData.read(tmp_path / "y.chromdata.zarr")
    pd.testing.assert_frame_equal(again.to_dataframe(), back.to_dataframe())


def test_format_2_0_stores_stay_readable(tmp_path):
    """The unpartitioned 2.0 layout (one file per table, cell › trace › bin)."""
    cd = _cd(n_cells=6)
    old = tmp_path / "old.chromdata.zarr"
    write_zarr(cd, old, row_group_rows=40, _layout="2.0")
    meta = json.loads((old / "zarr.json").read_text())["attributes"]["uchrom"]
    assert meta["format_version"] == "2.0" and meta["spot_order"] == "cell,trace,bin"
    assert (old / "tables" / "spots.parquet").exists()
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        mem = ChromData.read(old)
        bk = ChromData.read(old, backed=True)
    assert bk.format_version == "2.0" and not bk.partitioned
    s = mem.spots
    key = pd.DataFrame({"c": s["cell_id"].cat.codes, "t": s["trace_id"].cat.codes, "b": s["bin_id"]})
    assert key.equals(key.sort_values(["c", "t", "b"], kind="stable"))
    pd.testing.assert_frame_equal(_sorted_df(mem), _sorted_df(cd))
    pd.testing.assert_frame_equal(_sorted_tracks(mem), _sorted_tracks(cd))
    new = tmp_path / "new.chromdata.zarr"
    cd.write(new)
    pd.testing.assert_frame_equal(_sorted_df(ChromData.read(new)), _sorted_df(mem))
    for c in mem.spots["cell_id"].cat.categories:
        pd.testing.assert_frame_equal(bk.get_cell(c).to_dataframe(), mem.get_cell(c).to_dataframe())
    for ch in ("chr1", "chr2", "chrX"):
        pd.testing.assert_frame_equal(bk.get_chrom(ch).to_dataframe(), mem.get_chrom(ch).to_dataframe())
        sel = bk.get_chrom(ch, columns="coords")
        assert list(sel.spots.columns) == ["chrom", "start", "end", "trace_id", "cell_id", "bin_id"]
        assert sel.spot_tracks.shape[1] == 0 and not sel.layers
        pd.testing.assert_frame_equal(sel.to_dataframe(), mem.get_chrom(ch, columns="coords").to_dataframe())
    for t in mem.spots["trace_id"].cat.categories[:5]:
        pd.testing.assert_frame_equal(bk.get_trace(t).to_dataframe(), mem.get_trace(t).to_dataframe())
    # streaming over a 2.0 store: every spot once, whole traces
    got = pd.concat([c.to_dataframe() for c in bk.iter_traces(5)], ignore_index=True)
    pd.testing.assert_frame_equal(got, mem.to_dataframe())
    got = pd.concat([c.to_dataframe() for c in bk.iter_traces(3, chrom="chr2")], ignore_index=True)
    pd.testing.assert_frame_equal(got, mem.get_chrom("chr2").to_dataframe())
    assert sum(c.n_spots for c in bk.iter_cells(4)) == mem.n_spots
    # original order and an upgrade to the current format by rewriting
    ref = ChromData.read(old, original_order=True)
    pd.testing.assert_frame_equal(ref.to_dataframe(), cd.to_dataframe())
    bk.write(tmp_path / "up.chromdata.zarr")
    assert json.loads((tmp_path / "up.chromdata.zarr" / "zarr.json").read_text())["attributes"]["uchrom"][
        "format_version"] == "2.3"
    pd.testing.assert_frame_equal(_sorted_df(ChromData.read(tmp_path / "up.chromdata.zarr")), _sorted_df(cd))


def test_float32_coords_and_options(tmp_path):
    cd = _cd()
    cd.write(tmp_path / "f.chromdata.zarr", coord_dtype="float32", compression_level=1,
             keep_source_order=False)
    back = ChromData.read(tmp_path / "f.chromdata.zarr")
    assert back.coords.dtype == np.float64
    order = np.argsort(back.spots["spot_id"].to_numpy())
    ref = np.argsort(cd.spots["spot_id"].to_numpy())
    np.testing.assert_array_equal(back.coords[order], cd.coords[ref].astype(np.float32).astype(np.float64))
    with pytest.raises(ValueError, match="original_order"):
        ChromData.read(tmp_path / "f.chromdata.zarr", backed=True, original_order=True)
    with pytest.raises(ValueError, match="coord_dtype"):
        cd.write(tmp_path / "g.chromdata.zarr", coord_dtype="int32")


def test_edge_cases(tmp_path):
    # no cell_id, int trace ids, a trace spanning two chromosomes, one spot
    spots = pd.DataFrame({"chrom": ["chr1", "chr2", "chr1", "chr1"], "start": [0, 0, 10, 0],
                          "end": [10, 10, 20, 10], "trace_id": [7, 7, 3, 3]})
    cd = ChromData(np.arange(12.0).reshape(4, 3), spots)
    cd.write(tmp_path / "a.chromdata.zarr")
    back = ChromData.read(tmp_path / "a.chromdata.zarr")
    assert list(back.spots["trace_id"].cat.categories) == [3, 7]
    bk = ChromData.read(tmp_path / "a.chromdata.zarr", backed=True)
    for ch in ("chr1", "chr2", "chrZ"):
        pd.testing.assert_frame_equal(bk.get_chrom(ch).to_dataframe(), back.get_chrom(ch).to_dataframe())
    with pytest.raises(KeyError):
        bk.get_cell("x")
    with pytest.raises(KeyError):
        next(bk.iter_cells())
    assert bk.get_trace(99).n_spots == 0 and bk.get_trace(7).n_spots == 2
    # no spots at all (e.g. sc-Hi-C cells only)
    empty = ChromData(np.zeros((0, 3)), pd.DataFrame({"chrom": [], "start": [], "end": [], "trace_id": []}),
                      cells=pd.DataFrame({"n": [1, 2]}, index=pd.Index(["a", "b"], name="cell_id")))
    empty.write(tmp_path / "e.cdz")
    e = ChromData.read(tmp_path / "e.cdz")
    assert e.n_spots == 0 and list(e.cells.index) == ["a", "b"]
    assert ChromData.read(tmp_path / "e.cdz", backed=True).n_spots == 0
    # trace ids reused across cells (e.g. one trace per chromosome per cell)
    df = pd.DataFrame({"chrom": ["chr1"] * 4, "start": [0, 10, 0, 10], "end": [10, 20, 10, 20],
                       "x": 1.0, "y": 2.0, "z": [1.0, 2, 3, 4], "cell_id": ["a", "a", "b", "b"]})
    shared = ChromData.from_dataframe(df)
    shared.write(tmp_path / "s.chromdata.zarr")
    sb = ChromData.read(tmp_path / "s.chromdata.zarr", backed=True)
    assert sb.get_trace(0).n_spots == 4 and sb.n_traces == 1 and sb.n_cells == 2
    assert [c.n_spots for c in sb.iter_traces(1)] == [2, 2]      # one chunk per (cell, trace)


# ----------------------------------------------------------------- backed mode

def test_backed_matches_in_memory(tmp_path):
    cd = _cd(n_cells=6)
    path = tmp_path / "x.chromdata.zarr"
    cd.write(path, row_group_rows=50)
    mem = ChromData.read(path)
    bk = ChromData.read(path, backed=True)
    assert isinstance(bk, BackedChromData) and bk.backed and not mem.backed
    assert (bk.n_spots, bk.n_traces, bk.n_cells, bk.n_bins) == (mem.n_spots, mem.n_traces, mem.n_cells, mem.n_bins)
    _assert_same_small(mem, bk)

    def same(x, y):
        assert type(y) is ChromData
        pd.testing.assert_frame_equal(x.to_dataframe(), y.to_dataframe())
        pd.testing.assert_frame_equal(x.spot_tracks, y.spot_tracks)
        pd.testing.assert_frame_equal(x.cells, y.cells)
        pd.testing.assert_frame_equal(x.traces, y.traces)
        for k in x.cellm:
            np.testing.assert_array_equal(x.cellm[k], y.cellm[k])
        for k in x.layers:
            np.testing.assert_array_equal(x.layers[k], y.layers[k])
        for k in x.points:
            pd.testing.assert_frame_equal(x.points[k], y.points[k])

    for c in list(mem.spots["cell_id"].cat.categories) + ["nope"]:
        same(mem.get_cell(c), bk.get_cell(c))
    for t in mem.spots["trace_id"].cat.categories:
        same(mem.get_trace(t), bk.get_trace(t))
    for ch in ("chr1", "chr2", "chrX", "chrM"):
        same(mem.get_chrom(ch), bk.get_chrom(ch))
    rows = np.array([5, 0, 17, 3, 3])
    same(mem[rows], bk[rows])
    mask = mem.spots["label"].eq("a").to_numpy()
    same(mem[mask], bk[mask])
    same(mem[10:40], bk[10:40])
    # streaming: identical chunks in memory (any order) and backed
    for batch in (1, 4, 100):
        for x, y, z in zip(mem.iter_traces(batch), bk.iter_traces(batch), cd.iter_traces(batch)):
            same(x, y)
            same(x, z)
        assert sum(c.n_spots for c in bk.iter_traces(batch)) == mem.n_spots
    for x, y, z in zip(mem.iter_cells(2), bk.iter_cells(2), cd.iter_cells(2)):
        same(x, y)
        same(x, z)
    assert len(list(bk.iter_cells(4))) == 2
    # full load
    same(mem, bk.to_memory())
    same(mem, bk.copy())
    pd.testing.assert_frame_equal(bk.to_dataframe(), mem.to_dataframe())
    pd.testing.assert_frame_equal(bk.tracks_spot_view(), mem.tracks_spot_view())
    pd.testing.assert_frame_equal(bk.tracks_spot_view(["IF", "atac"]), mem.tracks_spot_view(["IF", "atac"]))
    t0 = mem.spots["trace_id"].cat.categories[0]
    np.testing.assert_allclose(bk.compute_distances(trace_id=t0), mem.compute_distances(trace_id=t0))


def test_backed_proxies(tmp_path):
    cd = _cd()
    path = tmp_path / "x.cdz"
    cd.write(path, row_group_rows=30)
    mem = ChromData.read(path)
    bk = ChromData.read(path, backed=True)
    assert isinstance(bk.coords, BackedArray) and isinstance(bk.spots, BackedFrame)
    assert bk.coords.shape == mem.coords.shape and len(bk.coords) == mem.n_spots
    np.testing.assert_array_equal(np.asarray(bk.coords), mem.coords)
    np.testing.assert_array_equal(bk.coords[5:60], mem.coords[5:60])
    np.testing.assert_array_equal(bk.coords[::7], mem.coords[::7])
    np.testing.assert_array_equal(bk.coords[[9, 1, 40]], mem.coords[[9, 1, 40]])
    np.testing.assert_array_equal(bk.coords[3], mem.coords[3])
    np.testing.assert_array_equal(bk.coords[-1], mem.coords[-1])
    np.testing.assert_array_equal(bk.coords[:, 2], mem.coords[:, 2])
    np.testing.assert_array_equal(bk.layers["Raw"][2:9], mem.layers["Raw"][2:9])
    assert list(bk.spots.columns) == list(mem.spots.columns) and len(bk.spots) == mem.n_spots
    for col in ("chrom", "start", "bin_id", "trace_id", "label"):
        pd.testing.assert_series_equal(bk.spots[col], mem.spots[col])
    pd.testing.assert_frame_equal(bk.spots[["cell_id", "end"]], mem.spots[["cell_id", "end"]])
    pd.testing.assert_frame_equal(bk.spots.iloc[3:11], mem.spots.iloc[3:11].reset_index(drop=True))
    pd.testing.assert_frame_equal(bk.spots.iloc[[4, 2]], mem.spots.iloc[[4, 2]].reset_index(drop=True))
    pd.testing.assert_frame_equal(bk.spots.to_pandas(), mem.spots)
    pd.testing.assert_series_equal(bk.spot_tracks["IF"], mem.spot_tracks["IF"])
    assert bk.track_names() == mem.track_names()
    assert "backed" in repr(bk)
    for attempt in (lambda: setattr(bk, "coords", mem.coords), lambda: setattr(bk, "spots", mem.spots),
                    lambda: setattr(bk, "spot_tracks", mem.spot_tracks), bk.rebuild_bins):
        with pytest.raises(AttributeError, match="read-only"):
            attempt()
    # small tables are editable and saved by write() (which loads the data)
    bk.results["note"] = "edited"
    bk.write(tmp_path / "y.chromdata.zarr")
    assert ChromData.read(tmp_path / "y.chromdata.zarr").results["note"] == "edited"
    with pytest.raises(ValueError, match="own source"):
        write_zarr(bk, path)


# ----------------------------------------------------------------- dispatch

def test_dispatch_by_path(tmp_path):
    cd = _cd()
    assert container_kind("a.chromdata.zarr") == "zarr" and container_kind("a.zarr") == "zarr"
    assert container_kind("a.cdz") == "cdz" and container_kind("a.h5cd") == "h5cd"
    assert container_kind(tmp_path / "unknown") is None
    cd.write(tmp_path / "a.cdz")
    assert zipfile.is_zipfile(tmp_path / "a.cdz")
    with zipfile.ZipFile(tmp_path / "a.cdz") as zf:
        assert zf.namelist()[0] == "zarr.json"
        assert all(i.compress_type == zipfile.ZIP_STORED for i in zf.infolist())
    shutil.copy(tmp_path / "a.cdz", tmp_path / "noext")
    assert container_kind(tmp_path / "noext") == "cdz"
    assert ChromData.read(tmp_path / "noext").n_spots == cd.n_spots
    # .h5cd: still written (HDF5 2.0) with a DeprecationWarning, read as before
    del cd.results["strings"], cd.uns["names"]   # (HDF5 cannot store str arrays there)
    with pytest.warns(DeprecationWarning, match="deprecated"):
        cd.write(tmp_path / "a.h5cd")
    h = ChromData.read(tmp_path / "a.h5cd")
    # (HDF5 stores the None labels as the string "None"; the zarr container keeps them)
    pd.testing.assert_frame_equal(h.to_dataframe().drop(columns="label"), cd.to_dataframe().drop(columns="label"))
    with pytest.raises(ValueError, match="backed mode"):
        ChromData.read(tmp_path / "a.h5cd", backed=True)
    # format= overrides the suffix, but the path must fit the container
    with pytest.raises(ValueError, match="chromdata.zarr"):
        cd.write(tmp_path / "b.h5cd", format="zarr")
    with pytest.raises(ValueError, match="format"):
        cd.write(tmp_path / "b.chromdata.zarr", format="parquet")
    # overwriting a store is fine; overwriting some other directory is not
    cd.write(tmp_path / "c.chromdata.zarr")
    cd.write(tmp_path / "c.chromdata.zarr")
    other = tmp_path / "d.zarr"
    other.mkdir()
    (other / "keep.txt").write_text("x")
    with pytest.raises(FileExistsError):
        cd.write(other)
    assert (other / "keep.txt").exists()
    assert not [p for p in tmp_path.iterdir() if p.name.startswith(".")]      # no temp leftovers
    with pytest.raises(FileNotFoundError):
        ChromData.read(tmp_path / "missing.chromdata.zarr")


def test_version_checks(tmp_path):
    cd = _cd()
    path = tmp_path / "v.chromdata.zarr"
    cd.write(path)
    meta_path = path / "zarr.json"
    meta = json.loads(meta_path.read_text())
    meta["attributes"]["uchrom"]["format_version"] = "2.9"
    meta_path.write_text(json.dumps(meta))
    with pytest.warns(UserWarning, match="2.9"):
        ChromData.read(path)
    meta["attributes"]["uchrom"]["format_version"] = "3.0"
    meta_path.write_text(json.dumps(meta))
    with pytest.raises(ValueError, match="MAJOR"):
        ChromData.read(path)
    (tmp_path / "plain.zarr").mkdir()
    (tmp_path / "plain.zarr" / "zarr.json").write_text(json.dumps({"zarr_format": 3, "node_type": "group",
                                                                  "attributes": {}}))
    with pytest.raises(ValueError, match="not a ChromData store"):
        ChromData.read(tmp_path / "plain.zarr")


def test_links_follow_a_moved_folder(tmp_path):
    proj = tmp_path / "proj"
    proj.mkdir()
    (proj / "bulk.mcool").write_bytes(b"x")
    cd = _cd()
    cd.link_cool(proj / "bulk.mcool", key="abs")            # absolute path
    cd.write(proj / "d.chromdata.zarr")
    moved = tmp_path / "moved"
    shutil.move(str(proj), str(moved))
    back = ChromData.read(moved / "d.chromdata.zarr")
    assert back.uns["linked_cool"]["abs"]["path"] == str((moved / "bulk.mcool").resolve())
    assert back.uns["linked_cool"]["bulk"]["path"] == "bulk.mcool"     # relative: kept verbatim
    assert back.resolve_link_path("bulk.mcool") == moved / "bulk.mcool"
    import zarr
    root = zarr.open_group(str(moved / "d.chromdata.zarr"), mode="r")
    assert "linked_cool" in root["contacts"].attrs["records"]
    assert "linked_anndata" in root["links"].attrs["records"]


def test_invalid_values_raise(tmp_path):
    cd = _cd()
    cd.cellm["bad"] = np.array([{"a": 1}] * 4, dtype=object)
    with pytest.raises(TypeError, match="object"):
        cd.write(tmp_path / "x.chromdata.zarr")
    assert not (tmp_path / "x.chromdata.zarr").exists()


# ----------------------------------------------------------------- conversion

def _write_1x(path):
    spots = pd.DataFrame({"chrom": ["chr2", "chr1", "chr1", "chr2", "chr1", "chr1"],
                          "start": [0, 10, 0, 0, 10, 0], "end": [10, 20, 10, 10, 20, 10],
                          "trace_id": ["1", "1", "1", "0", "0", "0"],
                          "cell_id": ["b", "b", "b", "a", "a", "a"], "spot_id": np.arange(6)})
    tracks = pd.DataFrame({"IF": [1.0, 2.0, 3.0, 4.0, 5.0, np.nan], "ATAC": [9.0, 7.0, 5.0, 9.0, 7.0, 5.0]})
    coords = np.arange(18, dtype=float).reshape(6, 3)
    write_v1(path, coords, spots, tracks=tracks,
             cells=pd.DataFrame({"t": ["x", "y"]}, index=pd.Index(["a", "b"], name="cell_id")),
             layers={"raw": coords + 1}, uns={"genome_assembly": "mm10"},
             results={"tads": pd.DataFrame({"chrom": ["chr1"], "start": [0], "end": [20]})})


def test_convert_h5cd_1x_and_2x(tmp_path, capsys):
    from uchrom.io import convert_chromdata, file_format_version, upgrade_h5cd
    from uchrom.io.upgrade import main

    src = tmp_path / "old.h5cd"
    _write_1x(src)
    ref = ChromData.read(src)
    info = upgrade_h5cd(src)                                       # default target
    dst = tmp_path / "old.chromdata.zarr"
    assert info["dst"] == str(dst) and info["to_container"] == "zarr" and info["from_version"] == "1.4"
    assert file_format_version(dst) == "2.3" and file_format_version(src) == "1.4"
    new = ChromData.read(dst, original_order=True)
    pd.testing.assert_frame_equal(new.to_dataframe(), ref.to_dataframe())
    pd.testing.assert_frame_equal(new.tracks_spot_view(), ref.tracks_spot_view())
    np.testing.assert_array_equal(new.layers["raw"], ref.layers["raw"])
    assert new.results == ref.results and new.track_names() == {"bin": ["ATAC"], "spot": ["IF"]}
    with pytest.raises(FileExistsError):
        upgrade_h5cd(src)
    # h5cd 2.0 → cdz, and the CLI
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        ref.write(tmp_path / "two.h5cd")
    assert file_format_version(tmp_path / "two.h5cd") == "2.0"
    convert_chromdata(tmp_path / "two.h5cd", tmp_path / "two.cdz")
    assert file_format_version(tmp_path / "two.cdz") == "2.3"
    pd.testing.assert_frame_equal(ChromData.read(tmp_path / "two.cdz", original_order=True).to_dataframe(),
                                  ChromData.read(tmp_path / "two.h5cd").to_dataframe())
    assert main([str(src), str(tmp_path / "two.h5cd"), "--out-dir", str(tmp_path / "out")]) == 0
    out = capsys.readouterr().out
    assert "-> " in out and "zarr" in out
    assert {p.name for p in (tmp_path / "out").iterdir()} == {"old.chromdata.zarr", "two.chromdata.zarr"}
    assert main([str(src), "--out-dir", str(tmp_path / "o2"), "--format", "cdz"]) == 0
    assert (tmp_path / "o2" / "old.cdz").exists()
    with warnings.catch_warnings():
        warnings.simplefilter("error", DeprecationWarning)             # no warning for explicit h5cd
        upgrade_h5cd(src, tmp_path / "again.h5cd")
    assert file_format_version(tmp_path / "again.h5cd") == "2.0"
