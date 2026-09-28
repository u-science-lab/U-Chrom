"""Cells in tissue without 3-D spots (spatial Hi-C): cell positions, section images and a linked
cell x bin matrix shown as genome tracks (API.md: spatial, images, cell_bin tracks)."""

import numpy as np
import pandas as pd
import pytest

from uchrom import ChromData
from uchrom.browser.web.data import DatasetStore

ad = pytest.importorskip("anndata")


def _spatial_store(tmp_path):
    """Two sections of 2 spots each; section s1 has an image; spots of s1 have a score per bin."""
    cells = pd.DataFrame({"section": pd.Categorical(["s1", "s1", "s2", "s2"])},
                         index=pd.Index(["s1:1x1", "s1:2x1", "s2:1x1", "s2:1x2"], name="cell_id"))
    bins = pd.DataFrame({"chrom": pd.Categorical(["chr1", "chr1", "chr2", "chr1", "chr1", "chr1", "chr1"]),
                         "start": [0, 100, 0, 0, 50, 100, 150], "end": [100, 200, 100, 50, 100, 150, 200],
                         "resolution": [100, 100, 100, 50, 50, 50, 50]})
    empty = pd.DataFrame({c: pd.Series(dtype=t) for c, t in
                          [("chrom", str), ("start", np.int64), ("end", np.int64), ("trace_id", str), ("cell_id", str)]})
    cd = ChromData(np.zeros((0, 3)), empty, bins=bins, cells=cells)
    cd.set_cell_positions(np.array([[10.0, 20.0], [30.0, 20.0], [1.0, 1.0], [1.0, 2.0]]), unit="px", frame="tissue",
                          region_col="section", y_axis="down")
    from PIL import Image

    (tmp_path / "img").mkdir()
    Image.new("L", (40, 30)).save(tmp_path / "img" / "s1.png")
    cd.uns["linked_images"] = {"s1": {"path": "img/s1.png", "positions": "default", "region": "s1",
                                      "extent": [0, 40, 0, 30]}}
    # s1 spots x (chr1 100 bp, chr2 100 bp, chr1 50 bp) bins; NaN = no value
    x = np.array([[1.0, 2.0, 5.0, 1.0, 1.0, 1.0, 1.0],
                  [3.0, np.nan, 7.0, 3.0, 3.0, 3.0, 3.0]], dtype=np.float32)
    var = pd.DataFrame({"bin_id": np.arange(7), "resolution": bins["resolution"].to_numpy()},
                       index=[f"b{i}" for i in range(7)])
    ad.AnnData(X=x, obs=pd.DataFrame(index=["s1:1x1", "s1:2x1"]), var=var).write_h5ad(tmp_path / "score.h5ad")
    cd.uns["linked_bin_matrices"] = {"score": {"path": "score.h5ad", "label": "Score"}}
    cd.write(tmp_path / "d.chromdata.zarr")
    return DatasetStore().load(tmp_path / "d.chromdata.zarr")


def test_spatial_listing_points_and_image(tmp_path):
    ds = _spatial_store(tmp_path)
    s = ds.summary()
    assert s["has_coords"] is False
    [info] = s["spatial"]
    assert info["key"] == "default" and info["unit"] == "px" and info["y_axis"] == "down"
    assert info["regions"] == [{"name": "s1", "n_cells": 2, "image": "s1"}, {"name": "s2", "n_cells": 2, "image": None}]
    p = ds.spatial_points("default", "s1")
    assert p["cell_ids"] == ["s1:1x1", "s1:2x1"] and p["x"] == [10.0, 30.0] and p["y"] == [20.0, 20.0]
    assert p["image"] == {"name": "s1", "extent": [0.0, 40.0, 0.0, 30.0], "kind": None}
    assert ds.spatial_points("default", "s2")["image"] is None
    every = ds.spatial_points("default")
    assert every["cell_ids"] == ["s1:1x1", "s1:2x1", "s2:1x1", "s2:1x2"] and every["regions"] == ["s1", "s1", "s2", "s2"]
    assert every["images"] == {"s1": {"name": "s1", "extent": [0.0, 40.0, 0.0, 30.0], "kind": None}}
    assert ds.image_path("s1") == tmp_path / "img" / "s1.png"
    with pytest.raises(KeyError):
        ds.spatial_points("nope")
    with pytest.raises(KeyError):
        ds.image_path("s2")


def test_chromosomes_come_from_bins_without_spots(tmp_path):
    chroms = _spatial_store(tmp_path).summary()["chroms"]
    assert [(c["name"], c["start"], c["end"], c["n_spots"]) for c in chroms] == [("chr1", 0, 200, 0), ("chr2", 0, 100, 0)]


def test_cell_bin_matrix_tracks_by_scope_and_resolution(tmp_path):
    ds = _spatial_store(tmp_path)
    tracks = {t["name"]: t for t in ds.summary()["tracks"]}
    # one track per resolution, each on its own grid
    assert {n: (v["level"], v["resolution"], v["label"]) for n, v in tracks.items()} == {
        "score@100bp": ("cell_bin", 100, "Score 100 bp"), "score@50bp": ("cell_bin", 50, "Score 50 bp")}
    by_res = {v["resolution"]: n for n, v in tracks.items()}
    coarse, fine = by_res[100], by_res[50]
    assert tracks[coarse]["grid"] != tracks[fine]["grid"]
    # all cells: mean over the spots with a value; RNA-like spots (not in the matrix) add nothing
    r = ds.tracks([coarse], "chr1")
    assert r["bin_starts"] == [0, 100] and r["bin_ends"] == [100, 200]
    assert r["values"][coarse] == [2.0, 2.0] and r["n_spots"] == [2, 1]
    # one cell, a group, a cell without values
    assert ds.tracks([coarse], "chr1", cell_id="s1:2x1")["values"][coarse] == [3.0, None]
    g = ds.register_group(["s1:1x1", "s2:1x1"])
    assert ds.tracks([coarse], "chr1", group=g["id"])["values"][coarse] == [1.0, 2.0]
    none = ds.tracks([coarse], "chr1", cell_id="s2:1x1")
    assert none["values"][coarse] == [None, None] and none["n_spots"] == [0, 0]
    # the finer grid and a locus window
    f = ds.tracks([fine], "chr1", 60, 160)
    assert f["bin_starts"] == [50, 100, 150] and f["values"][fine] == [2.0, 2.0, 2.0]
    assert ds.tracks([coarse], "chr2")["values"][coarse] == [6.0]
    with pytest.raises(ValueError, match="different bins"):
        ds.tracks([coarse, fine], "chr1")
