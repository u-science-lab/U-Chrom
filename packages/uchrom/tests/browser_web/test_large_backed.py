"""A large backed store is never read whole: summaries from the index, geometry / statistics / distance maps
from a sample.  The sample paths are forced on a small store (``LARGE_SPOTS = 0``); with a sample that covers
everything they must give what the whole-store paths give."""

import json
import struct

import numpy as np
import pandas as pd
import pytest

from uchrom import ChromData
from uchrom_browser import data as wd
from uchrom_browser.data import DatasetStore, GeometryFilter, decode_matrix


@pytest.fixture
def store(tmp_path):
    rng = np.random.default_rng(1)
    rows, xyz = [], []
    for cell in [f"c{i}" for i in range(12)]:
        for chrom, n in (("chr1", 30), ("chr2", 20)):
            for copy in ("mat", "pat"):
                for i in range(n):
                    rows.append((chrom, i * 100, i * 100 + 100, f"{cell}_{chrom}_{copy}", cell))
                xyz.append(np.cumsum(rng.normal(size=(n, 3)), 0))
    spots = pd.DataFrame(rows, columns=["chrom", "start", "end", "trace_id", "cell_id"])
    cells = pd.DataFrame({"kind": ["a", "b"] * 6}, index=pd.Index([f"c{i}" for i in range(12)], name="cell_id"))
    ChromData(np.concatenate(xyz), spots, cells=cells).write(tmp_path / "x.chromdata.zarr")
    return tmp_path / "x.chromdata.zarr"


def _header(buf: bytes) -> dict:
    n = struct.unpack("<I", buf[:4])[0]
    return json.loads(buf[4:4 + n])


def _both(store, monkeypatch):
    small = DatasetStore().load(store)
    assert not small._large()                       # decided once, at the first call
    monkeypatch.setattr(wd, "LARGE_SPOTS", 0)
    large = DatasetStore().load(store)
    assert large._large() and not small._large() and "draw_order" not in large._cache
    return small, large


def test_summaries_come_from_the_index(store, monkeypatch):
    small, large = _both(store, monkeypatch)
    assert [(c["name"], c["n_spots"], c["n_traces"]) for c in small.chrom_table()] == \
        [(c["name"], c["n_spots"], c["n_traces"]) for c in large.chrom_table()]
    a, b = small.traces(limit=10_000)["traces"], large.traces(limit=10_000)["traces"]
    assert [(t["trace_id"], t["n_spots"], t["cell_id"]) for t in a] == [(t["trace_id"], t["n_spots"], t["cell_id"]) for t in b]
    assert small.cells(limit=100) == large.cells(limit=100)


def test_geometry_of_a_sample_of_cells(store, monkeypatch):
    small, large = _both(store, monkeypatch)
    full = _header(small.geometry(GeometryFilter()))
    whole = _header(large.geometry(GeometryFilter()))             # the sample covers every cell
    assert whole["n_points"] == full["n_points"] == 1200 and whole["sample"] is None
    part = _header(large.geometry(GeometryFilter(chroms=["chr1"], max_points=700)))
    assert part["truncated"] and part["total_points"] == 720 and part["sample"] == {"cells": 11, "of_cells": 12}
    assert part["n_points"] == 660 and {s["chrom"] for s in part["segments"]} == {"chr1"}
    one = _header(large.geometry(GeometryFilter(cell_ids=["c3"])))
    assert one["n_points"] == 100 and {s["cell_id"] for s in one["segments"]} == {"c3"}


def test_statistics_and_distances_equal_the_whole_store_when_the_sample_covers_it(store, monkeypatch):
    small, large = _both(store, monkeypatch)
    a, b = small.stats_rg("chr1"), large.stats_rg("chr1")
    assert sorted(zip(a["trace_ids"], np.round(a["rg"], 9))) == sorted(zip(b["trace_ids"], np.round(b["rg"], 9)))
    assert b["note"] is None
    x, y = small.stats_scaling("chr2"), large.stats_scaling("chr2")
    assert x["median"] == pytest.approx(y["median"]) and x["n_pairs"] == y["n_pairs"]
    m1, m2 = decode_matrix(small.distance("chr1")), decode_matrix(large.distance("chr1"))
    np.testing.assert_allclose(m1["matrix"], m2["matrix"], equal_nan=True)
    assert m2["header"]["n_traces"] == 24
    monkeypatch.setattr(wd, "STATS_MAX_SPOTS", 120)                 # two cells of chr1
    c = large.stats_rg("chr1")
    assert c["note"] == "2 of 12 cells (random sample)" and len(c["rg"]) == 4
