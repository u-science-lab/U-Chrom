"""An atlas: catalog.json built from stores and read from a folder; the one-file download.

The web browser's /api/atlas: uchrom-browser's tests/test_atlas_api.py; the thumbnails and the
static page: apps/atlas/tests/test_build.py."""

import json

import pytest

pytest.importorskip("cooler")

from chromdata import catalog as atlas  # noqa: E402
from chromdata.testing import example_atlas  # noqa: E402


@pytest.fixture
def atlas_dir(tmp_path):
    return example_atlas(tmp_path)


def test_catalog_is_read_from_the_stores(atlas_dir):
    cat = json.loads((atlas_dir / "catalog.json").read_text())
    d = cat["datasets"][0]
    assert cat["version"] == 1 and d["title"] == "A toy dataset" and d["license"] == "CC0"
    assert d["n_cells"] == 3 and d["contact_maps"] == 2 and d["images"] == 1
    assert {"Hi-C per cell", "Hi-C bulk", "RNA", "A/B per spot", "images"} <= set(d["modalities"])  # no positions
    assert d["size_mb"] > 0 and d["files"] > 10


def test_fetch_from_a_folder_gives_urls(atlas_dir):
    cat = atlas.fetch_catalog(str(atlas_dir))
    assert cat["datasets"][0]["url"] == f"{atlas_dir}/toy.chromdata.zarr"


def test_download_is_the_store_as_one_cdz(atlas_dir):
    from chromdata import ChromData

    d = json.loads((atlas_dir / "catalog.json").read_text())["datasets"][0]
    assert d["download"] == "toy.cdz" and d["download_mb"] == d["size_mb"]
    out = atlas.pack(atlas_dir / "toy.chromdata.zarr", atlas_dir / d["download"])
    cd = ChromData.read(out, backed=True)
    assert cd.n_cells == 3 and set(cd.embedded_links()["contacts"]) == {"bulk", "cells"}
    assert out.stat().st_size / 1e6 >= d["size_mb"] * 0.9


def test_accessibility_of_dissociated_cells(tmp_path):
    """Cells with gene activity of their own (``atac.<gene>``) list ATAC per cell; a store without it does not."""
    import numpy as np
    import pandas as pd

    from chromdata import ChromData

    spots = pd.DataFrame({"chrom": pd.Series(dtype=str), "start": pd.Series(dtype=np.int64),
                          "end": pd.Series(dtype=np.int64), "trace_id": pd.Series(dtype=str),
                          "cell_id": pd.Series(dtype=str)})
    cells = pd.DataFrame({"cell_type": ["a", "b"], "atac.Gad1": [3.0, 0.0]}, index=pd.Index(["c1", "c2"], name="cell_id"))
    ChromData(np.zeros((0, 3)), spots, cells=cells).write(tmp_path / "atac.chromdata.zarr")
    ChromData(np.zeros((0, 3)), spots, cells=cells[["cell_type"]]).write(tmp_path / "plain.chromdata.zarr")
    assert "ATAC per cell" in atlas.describe_store(tmp_path / "atac.chromdata.zarr")["modalities"]
    assert "ATAC per cell" not in atlas.describe_store(tmp_path / "plain.chromdata.zarr")["modalities"]
