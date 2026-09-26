"""Framework-free tests for the web browser's data layer."""

import numpy as np
import pandas as pd
import pytest

from uchrom import ChromData
from uchrom.datasets import example_path
from uchrom.browser.web.data import (
    DatasetStore,
    GeometryFilter,
    decode_geometry,
    natural_chrom_key,
)

SOX2 = example_path("mesc_sox2", "mESC_Sox2_5cells_wnan.h5cd")


def _toy():
    """Two traces on chr2 / chr10 plus one on chr1, with a NaN spot in t_a."""
    rows = []
    coords = []
    for trace, chrom, n in [("t_b", "chr10", 3), ("t_a", "chr2", 5), ("t_c", "chr1", 2)]:
        for i in range(n):
            rows.append({"chrom": chrom, "start": 1000 * i, "end": 1000 * (i + 1),
                         "trace_id": trace, "cell_id": f"cell_{trace}"})
            coords.append([i, len(rows), 0.0])
    coords = np.array(coords, dtype=float)
    coords[3 + 2] = np.nan  # t_a, third spot → splits t_a into 2 + 2
    cd = ChromData(coords, pd.DataFrame(rows), uns={"xyz_unit": "um"})
    store = DatasetStore()
    return store, store.add(cd, name="toy")


def test_natural_chrom_order():
    names = ["chrX", "chr10", "chr2", "chrM", "chr1", "scaffold_7", "chrY"]
    assert sorted(names, key=natural_chrom_key) == [
        "chr1", "chr2", "chr10", "chrX", "chrY", "chrM", "scaffold_7"]


def test_summary_and_traces():
    _, ds = _toy()
    s = ds.summary()
    assert s["n_spots"] == 10 and s["n_traces"] == 3 and s["xyz_unit"] == "um"
    assert [c["name"] for c in s["chroms"]] == ["chr1", "chr2", "chr10"]
    assert s["chroms"][1] == {"name": "chr2", "start": 0, "end": 5000,
                              "n_spots": 5, "n_traces": 1}
    assert s["trace_mode"] is False  # one trace per chromosome

    t = ds.traces()
    assert t["total"] == 3
    assert [r["trace_id"] for r in t["traces"]] == ["t_c", "t_a", "t_b"]
    assert t["traces"][1] == {"trace_id": "t_a", "chrom": "chr2", "cell_id": "cell_t_a",
                              "n_spots": 5, "start": 0, "end": 5000}
    assert ds.traces(chrom="chr10")["total"] == 1
    assert ds.traces(offset=2, limit=5)["traces"][0]["trace_id"] == "t_b"


def test_geometry_segments_split_on_nan_and_trace():
    _, ds = _toy()
    g = decode_geometry(ds.geometry(GeometryFilter()))
    h = g["header"]
    # t_c (2) | t_a (2 + 2 after dropping the NaN spot) | t_b (3)
    assert [(s["trace_id"], s["n_points"]) for s in h["segments"]] == [
        ("t_c", 2), ("t_a", 2), ("t_a", 2), ("t_b", 3)]
    assert h["n_points"] == 9 and h["total_points"] == 9 and not h["truncated"]
    assert list(g["offsets"]) == [0, 2, 4, 6, 9]
    assert np.isfinite(g["positions"]).all()
    assert list(g["starts"][2:6]) == [0, 1000, 3000, 4000]  # bin 2000 dropped
    assert h["segments"][2] == {"trace_id": "t_a", "chrom": "chr2", "cell_id": "cell_t_a",
                                "n_points": 2, "start": 3000, "end": 5000}
    assert h["chrom_extent"]["chr10"] == [0, 3000]
    assert h["bbox"]["min"][0] == 0.0


def test_geometry_filters_combine():
    _, ds = _toy()

    def seg_traces(**kw):
        h = decode_geometry(ds.geometry(GeometryFilter(**kw)))["header"]
        return [(s["trace_id"], s["n_points"]) for s in h["segments"]]

    assert seg_traces(chroms=["chr10"]) == [("t_b", 3)]
    assert seg_traces(trace_ids=["t_a", "t_c"]) == [("t_c", 2), ("t_a", 2), ("t_a", 2)]
    # region overlaps bins [1000,2000) and [3000,4000) of chr2 → NaN bin in between
    assert seg_traces(region={"chrom": "chr2", "start": 1500, "end": 3500}) == [
        ("t_a", 1), ("t_a", 1)]
    assert seg_traces(chroms=["chr1"], trace_ids=["t_a"]) == []
    empty = decode_geometry(ds.geometry(GeometryFilter(chroms=["chrZ"])))
    assert empty["header"]["n_points"] == 0 and empty["header"]["bbox"] is None
    assert list(empty["offsets"]) == [0]


def test_geometry_truncation_keeps_whole_segments():
    _, ds = _toy()
    h = decode_geometry(ds.geometry(GeometryFilter(max_points=5)))["header"]
    assert h["truncated"] and h["total_points"] == 9
    assert [s["n_points"] for s in h["segments"]] == [2, 2]  # third segment would hit 6
    one = decode_geometry(ds.geometry(GeometryFilter(max_points=1)))
    assert one["header"]["n_points"] == 1 and list(one["offsets"]) == [0, 1]


def test_invalid_filters():
    with pytest.raises(ValueError):
        GeometryFilter(region={"chrom": "chr1", "start": 5})
    with pytest.raises(ValueError):
        GeometryFilter(region={"chrom": "chr1", "start": 5, "end": 5})
    with pytest.raises(ValueError):
        GeometryFilter(max_points=0)


def test_store_load_csv_and_missing(tmp_path):
    store = DatasetStore()
    df = pd.DataFrame({"chrom": ["chr1"] * 3, "start": [0, 10, 20], "end": [10, 20, 30],
                       "x": [0.0, 1, 2], "y": [0.0, 0, 0], "z": [0.0, 0, 1]})
    csv = tmp_path / "recon.csv"
    df.to_csv(csv)
    ds = store.load(csv)
    assert ds.name == "recon" and ds.summary()["n_spots"] == 3
    assert [d.id for d in store.list()] == [ds.id]
    store.remove(ds.id)
    assert store.list() == []
    with pytest.raises(FileNotFoundError):
        store.load(tmp_path / "nope.h5cd")


@pytest.mark.skipif(not SOX2.exists(), reason="in-repo Sox2 FISH fixture missing")
def test_real_fish_data_with_missing_spots():
    """mESC Sox2 DNA FISH (5 cells, 41 loci, 49 missing spots)."""
    store = DatasetStore()
    ds = store.load(SOX2)
    s = ds.summary()
    assert s["n_spots"] == 205 and s["n_traces"] == 5 and s["trace_mode"] is True

    g = decode_geometry(ds.geometry(GeometryFilter()))
    h = g["header"]
    finite = np.isfinite(ds.cd.coords).all(axis=1)
    assert h["n_points"] == int(finite.sum()) == 156
    assert {s["trace_id"] for s in h["segments"]} == set(ds.cd.spots["trace_id"].astype(str))
    # every segment is a gap-free, start-ordered run of one trace
    for i, seg in enumerate(h["segments"]):
        lo, hi = g["offsets"][i], g["offsets"][i + 1]
        starts = g["starts"][lo:hi]
        assert (np.diff(starts.astype(np.int64)) > 0).all()
        sel = ds.cd.spots["trace_id"].astype(str) == seg["trace_id"]
        expected = ds.cd.coords[sel.to_numpy()]
        expected = expected[np.isin(ds.cd.spots["start"][sel], starts)]
        np.testing.assert_allclose(g["positions"][lo:hi], expected, rtol=1e-6)
    # positions match the float32 cast of the source coordinates
    assert g["positions"].dtype == np.float32


def test_cells_table_and_filter():
    _, ds = _toy()
    c = ds.cells()
    assert c["total"] == 3
    assert [r["cell_id"] for r in c["cells"]] == ["cell_t_a", "cell_t_b", "cell_t_c"]
    assert c["cells"][0] == {"cell_id": "cell_t_a", "n_spots": 5, "n_traces": 1, "n_chroms": 1}
    h = decode_geometry(ds.geometry(GeometryFilter(cell_ids=["cell_t_b"])))["header"]
    assert [(s["trace_id"], s["cell_id"]) for s in h["segments"]] == [("t_b", "cell_t_b")]


def test_cells_natural_order_and_missing_column():
    from uchrom.browser.web.data import natural_key
    assert sorted(["c10", "c2", "c1", "b"], key=natural_key) == ["b", "c1", "c2", "c10"]
    store = DatasetStore()
    spots = pd.DataFrame({"chrom": ["chr1"] * 2, "start": [0, 10], "end": [10, 20],
                          "trace_id": ["t"] * 2})
    ds = store.add(ChromData(np.zeros((2, 3)), spots), name="nocell")
    assert ds.cells() == {"total": 0, "cells": []}
    h = decode_geometry(ds.geometry(GeometryFilter(cell_ids=["x"])))["header"]
    assert h["n_points"] == 0
