"""An atlas: catalog.json built from stores, read from a folder or over HTTP, served by the web browser."""

import functools
import http.server
import json
import shutil
import threading
from pathlib import Path

import pytest

pytest.importorskip("cooler")
pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from tests.core.test_embedded import RES, _store  # noqa: E402
from tests.core.test_remote import _RangeHandler  # noqa: E402
from uchrom.browser.web.data import DatasetStore  # noqa: E402
from uchrom.browser.web.server import create_app  # noqa: E402
from uchrom.core import atlas, embedded  # noqa: E402


@pytest.fixture
def atlas_dir(tmp_path):
    _, emb = _store(tmp_path)
    embedded.embed_links(emb, verbose=False, trans_min_resolution=RES)
    root = tmp_path / "atlas"
    root.mkdir()
    emb.rename(root / "toy.chromdata.zarr")
    cfg = {"title": "Toy atlas", "datasets": [
        {"id": "toy", "store": "toy.chromdata.zarr", "path": "toy.chromdata.zarr", "title": "A toy dataset",
         "paper": "nobody 2026", "license": "CC0"}]}
    (tmp_path / "datasets.json").write_text(json.dumps(cfg))
    atlas.build_catalog(tmp_path / "datasets.json", root, root / "catalog.json")
    return root


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


def test_api_atlas_and_off_switch(atlas_dir):
    c = TestClient(create_app(DatasetStore(), atlas=str(atlas_dir)))
    r = c.get("/api/atlas").json()
    assert r["root"] == str(atlas_dir) and r["catalog"]["datasets"][0]["id"] == "toy"
    assert TestClient(create_app(DatasetStore(), atlas="")).get("/api/atlas").json() == {"root": None, "catalog": None}
    assert TestClient(create_app(DatasetStore(), atlas="/no/such/atlas")).get("/api/atlas").status_code == 502


def test_over_http_to_an_open_dataset(atlas_dir):
    pytest.importorskip("aiohttp")
    handler = functools.partial(_RangeHandler, directory=str(atlas_dir))
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        root = f"http://127.0.0.1:{srv.server_address[1]}"
        client = TestClient(create_app(DatasetStore(), atlas=root))
        d = client.get("/api/atlas").json()["catalog"]["datasets"][0]
        assert d["url"] == f"{root}/toy.chromdata.zarr"
        opened = client.post("/api/datasets", json={"path": d["url"]})
        assert opened.status_code == 200 and opened.json()["name"] == "toy" and opened.json()["n_cells"] == 3
        assert {m["key"] for m in opened.json()["contact_maps"]} == {"bulk", "cells"}
    finally:
        srv.shutdown()


def _figure_config(tmp_path, root, **figure):
    cfg = {"title": "Toy atlas", "hero": ["toy"],
           "studies": [{"id": "s1", "citation": "Nobody 2026", "kind": "Spatial Hi-C", "category": "Spatial"}],
           "datasets": [{"id": "toy", "store": "toy.chromdata.zarr", "path": "toy.chromdata.zarr", "study": "s1",
                         "name": "Toy", "title": "A toy dataset", "figure": figure}]}
    path = tmp_path / "figures.json.cfg"
    path.write_text(json.dumps(cfg))
    return path


def test_figures_from_positions_and_a_bulk_map(atlas_dir, tmp_path):
    from PIL import Image

    from uchrom import ChromData

    store = atlas_dir / "toy.chromdata.zarr"
    cd = ChromData.read(store)
    cd.cells["centroid_x"], cd.cells["centroid_y"] = [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]
    cd.write(store)                                   # same store: the embedded maps stay
    cfg = _figure_config(tmp_path, atlas_dir, caption="three spots")
    out = tmp_path / "site_figures"
    info = atlas.render_figures(cfg, atlas_dir, out, size=64, hero_size=96)["toy"]
    assert info["layout"] == "space" and info["color_by"] == "cell_type" and info["caption"] == "three spots"
    assert info["map_key"] == "bulk" and info["chrom"] == "chr2" and (info["start"], info["end"]) == (0, 600)
    assert Image.open(out / info["space"]).size == (64, 64) and Image.open(out / info["hero.space"]).size == (96, 96)
    assert Image.open(out / info["map"]).size == (6, 6)          # one pixel per bin
    # the site gets the figures and the study list
    template = tmp_path / "tpl"
    shutil.copytree(Path(atlas.__file__).resolve().parents[2] / "apps" / "atlas" / "site", template,
                    ignore=shutil.ignore_patterns("figures"))
    shutil.copytree(out, template / "figures")
    atlas.build_catalog(cfg, atlas_dir, tmp_path / "catalog.json")
    site = atlas.build_site(tmp_path / "site", tmp_path / "catalog.json", template=template, hosted="https://x.test")
    cat = json.loads((site / "catalog.json").read_text())
    assert cat["studies"][0]["id"] == "s1" and cat["hero"] == ["toy"]
    assert cat["datasets"][0]["figures"]["space"] == info["space"] and (site / "figures" / info["map"]).is_file()
    assert '"hosted": "https://x.test"' in (site / "config.js").read_text()


def test_figures_fall_back_to_an_embedding_and_cell_sums(atlas_dir, tmp_path):
    import numpy as np

    from uchrom import ChromData

    store = atlas_dir / "toy.chromdata.zarr"
    cd = ChromData.read(store)
    cd.cellm["rna_umap"] = np.array([[0.0, 0.0], [1.0, 2.0], [2.0, 1.0]])
    cd.write(store)
    info = atlas.render_figures(_figure_config(tmp_path, atlas_dir), atlas_dir, tmp_path / "f", size=32)["toy"]
    assert info["layout"] == "embedding" and info["layout_key"] == "rna_umap" and "space" in info
    cells = embedded.EmbeddedContacts(str(store), embedded.list_embedded(str(store))["cells"])
    got = atlas._map_png(cells, "chr1", tmp_path / "sum.webp")
    assert got["resolution"] == RES and (got["start"], got["end"]) == (0, 600) and (tmp_path / "sum.webp").is_file()


def test_figures_draw_a_cell_structure(tmp_path):
    import numpy as np
    import pandas as pd
    from PIL import Image

    from uchrom import ChromData

    rng = np.random.default_rng(0)
    rows = [(c, i * 100, i * 100 + 100, f"{cell}_{c}", cell) for cell in ("a", "b") for c in ("chr1", "chr2")
            for i in range(10)]
    spots = pd.DataFrame(rows, columns=["chrom", "start", "end", "trace_id", "cell_id"])
    cd = ChromData(np.cumsum(rng.normal(size=(len(spots), 3)), 0), spots,
                   cells=pd.DataFrame({"rmsd_20k": [2.0, 1.0]}, index=pd.Index(["a", "b"], name="cell_id")))
    cd.write(tmp_path / "xyz.chromdata.zarr")
    cfg = tmp_path / "cfg.json"
    cfg.write_text(json.dumps({"datasets": [{"id": "xyz", "store": "xyz.chromdata.zarr", "path": "xyz", "title": "x"}]}))
    info = atlas.render_figures(cfg, tmp_path, tmp_path / "f", size=48)["xyz"]
    assert info["layout"] == "structure" and info["layout_key"] == "b"      # the lowest RMSD
    assert info["color_by"] == "chromosome" and info["n"] == 20 and "map" not in info
    assert Image.open(tmp_path / "f" / info["space"]).size == (48, 48)


def test_download_is_the_store_as_one_cdz(atlas_dir):
    from uchrom import ChromData

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

    from uchrom import ChromData

    spots = pd.DataFrame({"chrom": pd.Series(dtype=str), "start": pd.Series(dtype=np.int64),
                          "end": pd.Series(dtype=np.int64), "trace_id": pd.Series(dtype=str),
                          "cell_id": pd.Series(dtype=str)})
    cells = pd.DataFrame({"cell_type": ["a", "b"], "atac.Gad1": [3.0, 0.0]}, index=pd.Index(["c1", "c2"], name="cell_id"))
    ChromData(np.zeros((0, 3)), spots, cells=cells).write(tmp_path / "atac.chromdata.zarr")
    ChromData(np.zeros((0, 3)), spots, cells=cells[["cell_type"]]).write(tmp_path / "plain.chromdata.zarr")
    assert "ATAC per cell" in atlas.describe_store(tmp_path / "atac.chromdata.zarr")["modalities"]
    assert "ATAC per cell" not in atlas.describe_store(tmp_path / "plain.chromdata.zarr")["modalities"]
