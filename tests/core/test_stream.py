"""Streaming writer (``ChromData.writer`` / ``from_fofct(out=)``), memory
budget settings, column selection and the format 2.1 iterators.

The streaming writer must produce the store ``ChromData(...).write()``
writes for the concatenated input: same rows in the same order, same index
and row groups, same small tables.
"""
import json

import numpy as np
import pandas as pd
import pytest
import zarr

from tests.core.test_zarr_format import _assert_same_small, _assert_uns_equal, _cd
from uchrom import ChromData, settings
from uchrom.settings import parse_bytes


def _chunks(cd, n_chunks, seed=1):
    """``cd`` split into row chunks (input order kept) as raw arrays."""
    rng = np.random.default_rng(seed)
    cuts = np.sort(rng.choice(np.arange(1, cd.n_spots), n_chunks - 1, replace=False))
    bounds = np.r_[0, cuts, cd.n_spots]
    spots = cd.spots.drop(columns=["bin_id"])
    for a, b in zip(bounds[:-1], bounds[1:]):
        yield dict(coords=cd.coords[a:b], spots=spots.iloc[a:b].reset_index(drop=True),
                   spot_tracks=cd.spot_tracks.iloc[a:b].reset_index(drop=True),
                   layers={k: v[a:b] for k, v in cd.layers.items()})


def _stream(cd, path, n_chunks=5, budget="1KB", **kw):
    w = ChromData.writer(path, memory_budget=budget, **kw)
    for ch in _chunks(cd, n_chunks):
        w.append(**ch)
    w.finish(cells=cd.cells, cellm=cd.cellm, traces=cd.traces, bin_tracks=cd.bin_tracks,
             binm=cd.binm, intervals=cd.intervals, points=cd.points, results=cd.results, uns=cd.uns)
    return path


def _assert_same_store(a_path, b_path):
    a, b = ChromData.read(a_path), ChromData.read(b_path)
    pd.testing.assert_frame_equal(a.to_dataframe(include_bin_id=True), b.to_dataframe(include_bin_id=True))
    pd.testing.assert_frame_equal(a.spots, b.spots)
    pd.testing.assert_frame_equal(a.spot_tracks, b.spot_tracks)
    for k in a.layers:
        np.testing.assert_array_equal(a.layers[k], b.layers[k])
    _assert_same_small(a, b)
    _assert_uns_equal(a.uns, b.uns)
    ra, rb = zarr.open_group(str(a_path), mode="r"), zarr.open_group(str(b_path), mode="r")
    for name in ("trace_offsets", "trace_codes", "trace_cells", "chrom_trace", "cell_offsets",
                 "cell_codes", "cell_partition", "row_groups", "partition_offsets",
                 "partition_groups", "partition_chrom", "source_row"):
        if name in ra["index"] or name in rb["index"]:
            np.testing.assert_array_equal(ra[f"index/{name}"][:], rb[f"index/{name}"][:], err_msg=name)
    ma, mb = ra.attrs["uchrom"], rb.attrs["uchrom"]
    for key in ("format_version", "spot_order", "n_spots", "n_bins", "n_traces", "n_cells",
                "n_row_groups", "n_partitions", "has_source_row", "has_cell_id"):
        assert ma[key] == mb[key], key
    ta, tb = ra["tables"].attrs["tables"], rb["tables"].attrs["tables"]
    for key in ("partitions", "coords", "primary"):
        assert ta.get(key) == tb.get(key), key
    for key in ("spots", "spot_tracks"):
        if key in ta:
            assert {k: v for k, v in ta[key].items() if k != "spot_view_order"} == \
                {k: v for k, v in tb[key].items() if k != "spot_view_order"}
    return a, b


@pytest.mark.parametrize("n_chunks,budget", [(1, "1GB"), (5, "1KB"), (13, "20KB")])
def test_streaming_writer_equals_in_memory_writer(tmp_path, n_chunks, budget):
    cd = _cd(n_cells=6)
    cd.write(tmp_path / "mem.chromdata.zarr", row_group_rows=20)
    _stream(cd, tmp_path / "st.chromdata.zarr", n_chunks=n_chunks, budget=budget, row_group_rows=20)
    _assert_same_store(tmp_path / "mem.chromdata.zarr", tmp_path / "st.chromdata.zarr")
    # original order survives the streaming sort
    ref = ChromData.read(tmp_path / "st.chromdata.zarr", original_order=True)
    pd.testing.assert_frame_equal(ref.to_dataframe(), cd.to_dataframe())
    assert not any(p.name.endswith(".spill") for p in tmp_path.iterdir())


def test_streaming_writer_chromdata_chunks_and_bins(tmp_path):
    cd = _cd(n_cells=4)
    cd.bin_tracks = pd.DataFrame(index=cd.bins.index)       # per-locus tracks: finish(bin_tracks=)
    cd.intervals.clear() if hasattr(cd.intervals, "clear") else None
    cd.write(tmp_path / "mem.chromdata.zarr")
    rows = np.arange(cd.n_spots)
    with ChromData.writer(tmp_path / "st.chromdata.zarr", bins=cd.bins) as w:
        for part in np.array_split(rows, 3):
            chunk = cd[part]
            chunk.cells, chunk.cellm, chunk.traces, chunk.points = pd.DataFrame(), {}, pd.DataFrame(), {}
            w.append(chunk)
        assert w.n_spots == cd.n_spots
        assert set(w.unique("cell_id")) == set(cd.spots["cell_id"].astype(str))
        w.finish(cells=cd.cells, cellm=cd.cellm, traces=cd.traces, points=cd.points,
                 results=cd.results, uns=cd.uns)
    a = ChromData.read(tmp_path / "mem.chromdata.zarr")
    b = ChromData.read(tmp_path / "st.chromdata.zarr")
    pd.testing.assert_frame_equal(a.to_dataframe(include_bin_id=True), b.to_dataframe(include_bin_id=True))
    pd.testing.assert_frame_equal(a.spot_tracks, b.spot_tracks)


def test_streaming_writer_type_promotion_and_errors(tmp_path):
    spots = pd.DataFrame({"chrom": ["chr1", "chr2", "chr1", "chr1"], "start": [0, 0, 10, 0],
                          "end": [10, 10, 20, 10], "trace_id": [7, 7, 3, 3], "q": [1, 2, 3, 4]})
    coords = np.arange(12.0).reshape(4, 3)
    ref = spots.copy()
    ref["q"] = [1.0, 2.0, 3.0, np.nan]                        # int in chunk 1, float in chunk 2
    ChromData(coords, ref).write(tmp_path / "mem.chromdata.zarr")
    with ChromData.writer(tmp_path / "st.chromdata.zarr") as w:
        w.append(coords=coords[:2], spots=spots.iloc[:2])
        w.append(coords=coords[2:], spots=ref.iloc[2:].reset_index(drop=True))
    _assert_same_store(tmp_path / "mem.chromdata.zarr", tmp_path / "st.chromdata.zarr")
    w = ChromData.writer(tmp_path / "bad.chromdata.zarr")
    w.append(coords=coords[:2], spots=spots.iloc[:2])
    with pytest.raises(ValueError, match="spot columns"):
        w.append(coords=coords[2:], spots=spots.iloc[2:].drop(columns="q"))
    w.abort()
    with pytest.raises(ValueError, match="directory store"):
        ChromData.writer(tmp_path / "x.cdz")
    with pytest.raises(RuntimeError):
        w.append(coords=coords, spots=spots)
    # an exception inside the with-block writes nothing and removes the spill
    with pytest.raises(KeyError):
        with ChromData.writer(tmp_path / "boom.chromdata.zarr") as w:
            w.append(coords=coords, spots=spots)
            raise KeyError("boom")
    assert not (tmp_path / "boom.chromdata.zarr").exists()
    assert not [p for p in tmp_path.iterdir() if p.name.endswith(".spill")]


def _fofct_file(path, n_cells=5, seed=0):
    rng = np.random.default_rng(seed)
    rows = []
    sid = 0
    for c in rng.permutation(n_cells):
        for ch in ("chr2", "chr1"):
            for b in rng.permutation(8):
                sid += 1
                rows.append((sid, f"{ch}_c{c}_t", *rng.normal(size=3).round(6), ch, b * 1000, b * 1000 + 1000,
                             f"cell{c}", "A" if b % 2 else "B", int(rng.integers(0, 5))))
    df = pd.DataFrame(rows, columns=["Spot_ID", "Trace_ID", "X", "Y", "Z", "Chrom", "Chrom_Start",
                                     "Chrom_End", "Cell_ID", "Readout", "FOV_ID"])
    df.loc[3, "FOV_ID"] = np.nan                               # int column with a hole
    header = ["##FOF-CT_version=v0.1", "##Table_namespace=4dn_FOF-CT_core",
              "##genome_assembly=mm10", "##XYZ_unit=micron", "#lab_name:test,,,",
              "##columns=(" + ",".join(df.columns) + ")"]
    with open(path, "w") as fh:
        fh.write("\n".join(header) + "\n")
        df.to_csv(fh, header=False, index=False)


def test_from_fofct_streaming_equals_in_memory(tmp_path):
    src = tmp_path / "core.csv"
    _fofct_file(src)
    mem = ChromData.from_fofct(src)
    mem.write(tmp_path / "mem.chromdata.zarr", row_group_rows=10)
    bk = ChromData.from_fofct(src, out=tmp_path / "st.chromdata.zarr", chunksize=7, memory_budget="2KB")
    assert bk.backed and bk.n_spots == mem.n_spots
    # the streaming writer uses the default row groups; compare data, not files
    a = ChromData.read(tmp_path / "mem.chromdata.zarr")
    b = bk.to_memory()
    pd.testing.assert_frame_equal(a.to_dataframe(include_bin_id=True), b.to_dataframe(include_bin_id=True))
    pd.testing.assert_frame_equal(a.bins, b.bins)
    _assert_uns_equal(a.uns, b.uns)
    ref = ChromData.read(tmp_path / "st.chromdata.zarr", original_order=True)
    pd.testing.assert_frame_equal(ref.to_dataframe(), mem.to_dataframe())
    with pytest.raises(TypeError, match="does not take"):
        ChromData.from_fofct(src, out=tmp_path / "x.chromdata.zarr", tracks=None)


def test_settings_memory_budget():
    old = settings._memory_budget
    try:
        assert parse_bytes("2GB") == 2 << 30 and parse_bytes("512 MiB") == 512 << 20
        assert parse_bytes(1e9) == 10 ** 9
        with pytest.raises(ValueError):
            parse_bytes("lots")
        settings.memory_budget = "3GB"
        assert settings.memory_budget == 3 << 30 and "3.0 GB" in repr(settings)
        settings.memory_budget = None
        assert settings.memory_budget >= 256 << 20
    finally:
        settings._memory_budget = old


def test_columns_selection_and_iterators(tmp_path):
    cd = _cd(n_cells=6)
    path = tmp_path / "x.chromdata.zarr"
    cd.write(path, row_group_rows=15)
    mem = ChromData.read(path)
    bk = ChromData.read(path, backed=True)
    for kw in ({"columns": "coords"}, {"columns": ["label", "IF", "raw"]}, {"tracks": ["z"]},
               {"columns": ["quality"], "tracks": []}):
        for c in list(mem.spots["cell_id"].cat.categories)[:3]:
            x, y = mem.get_cell(c, **kw), bk.get_cell(c, **kw)
            pd.testing.assert_frame_equal(x.spots, y.spots)
            pd.testing.assert_frame_equal(x.spot_tracks, y.spot_tracks)
            assert list(x.layers) == list(y.layers)
        for ch in ("chr1", "chrX"):
            x, y = mem.get_chrom(ch, **kw), bk.get_chrom(ch, **kw)
            pd.testing.assert_frame_equal(x.to_dataframe(), y.to_dataframe())
            pd.testing.assert_frame_equal(x.spot_tracks, y.spot_tracks)
    sel = bk.get_cell("c1", columns=["label", "IF", "raw"])
    assert list(sel.spots.columns) == ["chrom", "start", "end", "trace_id", "cell_id", "label", "bin_id"]
    assert list(sel.spot_tracks.columns) == ["IF"] and list(sel.layers) == ["raw"]
    with pytest.raises(KeyError, match="unknown column"):
        bk.get_cell("c1", columns=["nope"])
    with pytest.raises(KeyError, match="unknown spot track"):
        mem.get_cell("c1", tracks=["nope"])
    # a default selection given to read()
    lite = ChromData.read(path, backed=True, columns="coords")
    assert lite.get_trace(mem.spots["trace_id"].cat.categories[0]).spot_tracks.shape[1] == 0
    assert ChromData.read(path, columns="coords").spot_tracks.shape[1] == 0
    # iterators: chromosome filter, selection, "auto" batches, identical chunks
    for chrom in (None, "chr2"):
        for batch in (1, 4, "auto"):
            xs = list(mem.iter_traces(batch, chrom=chrom, columns="coords"))
            ys = list(bk.iter_traces(batch, chrom=chrom, columns="coords"))
            zs = list(cd.iter_traces(batch, chrom=chrom, columns="coords"))
            assert len(xs) == len(ys) == len(zs)
            for x, y, z in zip(xs, ys, zs):
                pd.testing.assert_frame_equal(x.to_dataframe(), y.to_dataframe())
                pd.testing.assert_frame_equal(x.to_dataframe(), z.to_dataframe())
            whole = mem.get_chrom(chrom) if chrom else mem
            assert sum(x.n_spots for x in xs) == whole.n_spots
    for x, y in zip(mem.iter_cells(4, tracks=["IF"]), bk.iter_cells(4, tracks=["IF"])):
        pd.testing.assert_frame_equal(x.to_dataframe(), y.to_dataframe())
        pd.testing.assert_frame_equal(x.spot_tracks, y.spot_tracks)
    with pytest.raises(ValueError):
        next(bk.iter_traces(0))
