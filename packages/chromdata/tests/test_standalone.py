"""chromdata on its own: the store round trip, backed reads, the one-file .cdz and an atlas catalog, with neither
the analysis library (uchrom) nor any optional dependency installed."""

import json
import sys

import numpy as np
import pandas as pd
import pytest

from chromdata import ChromData, catalog


def _toy(n_cells=3, n_loci=20, seed=0):
    rng = np.random.default_rng(seed)
    rows = []
    for c in range(n_cells):
        for chrom in ("chr1", "chr2"):
            for k in range(n_loci):
                rows.append({"chrom": chrom, "start": k * 1000, "end": (k + 1) * 1000,
                             "trace_id": f"c{c}_{chrom}", "cell_id": f"c{c}"})
    spots = pd.DataFrame(rows)
    cells = pd.DataFrame({"cell_type": ["a", "b", "a"][:n_cells]}, index=[f"c{c}" for c in range(n_cells)])
    return ChromData(rng.normal(size=(len(spots), 3)), spots, cells=cells, uns={"genome_assembly": "toy"})


def _sorted_coords(cd):
    df = cd.to_dataframe().sort_values(["chrom", "start"], kind="stable")
    return df[["x", "y", "z"]].to_numpy()


def test_does_not_need_uchrom():
    assert "uchrom" not in sys.modules


def test_round_trip_and_backed_reads(tmp_path):
    cd = _toy()
    path = tmp_path / "toy.chromdata.zarr"
    cd.write(path)
    back = ChromData.read(path)
    assert len(back.cells) == 3 and back.coords.shape == cd.coords.shape
    one = cd.get_cell("c1")
    backed = ChromData.read(path, backed=True)
    got = backed.get_cell("c1")
    assert got.coords.shape == one.coords.shape
    np.testing.assert_allclose(_sorted_coords(got), _sorted_coords(one))
    assert backed.get_chrom("chr2", columns="coords").coords.shape[0] == 3 * 20


def test_cdz_is_the_same_store(tmp_path):
    cd = _toy()
    cd.write(tmp_path / "toy.chromdata.zarr")
    out = catalog.pack(tmp_path / "toy.chromdata.zarr")
    assert out.name == "toy.cdz"
    back = ChromData.read(out, backed=True)
    np.testing.assert_allclose(_sorted_coords(back.get_cell("c2")), _sorted_coords(cd.get_cell("c2")))


def test_catalog_from_stores(tmp_path):
    _toy().write(tmp_path / "toy.chromdata.zarr")
    config = {"title": "test", "studies": [{"id": "s", "citation": "Test 2026"}],
              "datasets": [{"id": "toy", "store": "toy.chromdata.zarr", "path": "toy.chromdata.zarr", "study": "s", "name": "Toy", "download": False}]}
    (tmp_path / "datasets.json").write_text(json.dumps(config))
    cat = catalog.build_catalog(tmp_path / "datasets.json", tmp_path, tmp_path / "catalog.json")
    assert cat["datasets"][0]["n_cells"] == 3
    got = catalog.fetch_catalog(str(tmp_path))
    assert got["datasets"][0]["url"].endswith("toy.chromdata.zarr")


def test_dataset_loaders_say_what_to_install(monkeypatch):
    monkeypatch.setitem(sys.modules, "uchrom", None)          # as if the analysis library were not installed
    with pytest.raises(ImportError, match="pip install u-chrom"):
        ChromData.from_takei2025_cerebellum()
