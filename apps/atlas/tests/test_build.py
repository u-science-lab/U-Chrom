"""The atlas app (apps/atlas/build.py): thumbnails drawn from the stores and the static page.

Run from apps/atlas: ``pytest tests`` (needs chromdata with cooler / anndata, matplotlib, Pillow)."""

import importlib.util
import json
import shutil
from pathlib import Path

import pytest

pytest.importorskip("cooler")

from chromdata import catalog as atlas, embedded  # noqa: E402
from chromdata.testing import LINKED_RES as RES, example_atlas  # noqa: E402

HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("atlas_build", HERE.parent / "build.py")
build = importlib.util.module_from_spec(_spec)      # the atlas app: thumbnails and the static page
_spec.loader.exec_module(build)


@pytest.fixture
def atlas_dir(tmp_path):
    return example_atlas(tmp_path)


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

    from chromdata import ChromData

    store = atlas_dir / "toy.chromdata.zarr"
    cd = ChromData.read(store)
    cd.cells["centroid_x"], cd.cells["centroid_y"] = [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]
    cd.write(store)                                   # same store: the embedded maps stay
    cfg = _figure_config(tmp_path, atlas_dir, caption="three spots")
    out = tmp_path / "site_figures"
    info = build.render_figures(cfg, atlas_dir, out, size=64, hero_size=96)["toy"]
    assert info["layout"] == "space" and info["color_by"] == "cell_type" and info["caption"] == "three spots"
    assert info["map_key"] == "bulk" and info["chrom"] == "chr2" and (info["start"], info["end"]) == (0, 600)
    assert Image.open(out / info["space"]).size == (64, 64) and Image.open(out / info["hero.space"]).size == (96, 96)
    assert Image.open(out / info["map"]).size == (6, 6)          # one pixel per bin
    # the site gets the figures and the study list
    template = tmp_path / "tpl"
    shutil.copytree(HERE.parent / "site", template,
                    ignore=shutil.ignore_patterns("figures"))
    shutil.copytree(out, template / "figures")
    atlas.build_catalog(cfg, atlas_dir, tmp_path / "catalog.json")
    site = build.build_site(tmp_path / "site", tmp_path / "catalog.json", template=template, hosted="https://x.test")
    cat = json.loads((site / "catalog.json").read_text())
    assert cat["studies"][0]["id"] == "s1" and cat["hero"] == ["toy"]
    assert cat["datasets"][0]["figures"]["space"] == info["space"] and (site / "figures" / info["map"]).is_file()
    assert '"hosted": "https://x.test"' in (site / "config.js").read_text()


def test_figures_fall_back_to_an_embedding_and_cell_sums(atlas_dir, tmp_path):
    import numpy as np

    from chromdata import ChromData

    store = atlas_dir / "toy.chromdata.zarr"
    cd = ChromData.read(store)
    cd.cellm["rna_umap"] = np.array([[0.0, 0.0], [1.0, 2.0], [2.0, 1.0]])
    cd.write(store)
    info = build.render_figures(_figure_config(tmp_path, atlas_dir), atlas_dir, tmp_path / "f", size=32)["toy"]
    assert info["layout"] == "embedding" and info["layout_key"] == "rna_umap" and "space" in info
    cells = embedded.EmbeddedContacts(str(store), embedded.list_embedded(str(store))["cells"])
    got = build._map_png(cells, "chr1", tmp_path / "sum.webp")
    assert got["resolution"] == RES and (got["start"], got["end"]) == (0, 600) and (tmp_path / "sum.webp").is_file()


def test_figures_draw_a_cell_structure(tmp_path):
    import numpy as np
    import pandas as pd
    from PIL import Image

    from chromdata import ChromData

    rng = np.random.default_rng(0)
    rows = [(c, i * 100, i * 100 + 100, f"{cell}_{c}", cell) for cell in ("a", "b") for c in ("chr1", "chr2")
            for i in range(10)]
    spots = pd.DataFrame(rows, columns=["chrom", "start", "end", "trace_id", "cell_id"])
    cd = ChromData(np.cumsum(rng.normal(size=(len(spots), 3)), 0), spots,
                   cells=pd.DataFrame({"rmsd_20k": [2.0, 1.0]}, index=pd.Index(["a", "b"], name="cell_id")))
    cd.write(tmp_path / "xyz.chromdata.zarr")
    cfg = tmp_path / "cfg.json"
    cfg.write_text(json.dumps({"datasets": [{"id": "xyz", "store": "xyz.chromdata.zarr", "path": "xyz", "title": "x"}]}))
    info = build.render_figures(cfg, tmp_path, tmp_path / "f", size=48)["xyz"]
    assert info["layout"] == "structure" and info["layout_key"] == "b"      # the lowest RMSD
    assert info["color_by"] == "chromosome" and info["n"] == 20 and "map" not in info
    assert Image.open(tmp_path / "f" / info["space"]).size == (48, 48)


def test_figures_colour_one_locus_along_the_genome(tmp_path):
    import numpy as np
    import pandas as pd
    from PIL import Image

    from chromdata import ChromData

    spots = pd.DataFrame({"chrom": "chr5", "start": np.arange(30) * 10_000, "end": np.arange(30) * 10_000 + 10_000,
                          "trace_id": "t1", "cell_id": "a"})
    cd = ChromData(np.c_[np.arange(30.0), 4 * np.sin(np.arange(30) / 3), np.cos(np.arange(30) / 5)], spots)
    cd.write(tmp_path / "locus.chromdata.zarr")
    cfg = tmp_path / "cfg.json"
    cfg.write_text(json.dumps({"datasets": [{"id": "locus", "store": "locus.chromdata.zarr", "path": "locus",
                                             "title": "x", "figure": {"layout": "structure", "trace": "t1"}}]}))
    info = build.render_figures(cfg, tmp_path, tmp_path / "f", size=240)["locus"]
    assert info["color_by"] == "genomic position" and info["categories"] == 1
    px = np.asarray(Image.open(tmp_path / "f" / info["space"]).convert("RGBA")).reshape(-1, 4)
    drawn = px[px[:, 3] > 0, :3].astype(int)
    assert len(drawn) and (drawn[:, 0] - drawn[:, 2]).max() > 100 and (drawn[:, 2] - drawn[:, 0]).max() > 100  # red to blue


def test_figures_draw_a_set_of_reads_as_dots(tmp_path):
    import numpy as np
    import pandas as pd
    from PIL import Image

    from chromdata import ChromData

    # reads of one territory, two of them in one bin: a set, not a chain
    spots = pd.DataFrame({"chrom": ["chr1"] * 4 + ["chr2"] * 2, "start": [0, 0, 100, 200, 0, 100],
                          "end": [100, 100, 200, 300, 100, 200], "trace_id": ["c_chr1"] * 4 + ["c_chr2"] * 2,
                          "cell_id": ["c"] * 6})
    xyz = np.array([[0, 0, 0], [9, 0, 0], [0, 9, 0], [9, 9, 1], [4, 4, 4], [5, 5, 2]], float)
    out = tmp_path / "set.webp"
    info = build._structure_png(ChromData(xyz, spots, uns={"trace_kind": "set"}), out, 48)
    assert info["n"] == 6 and info["categories"] == 2
    lines = tmp_path / "fibre.webp"
    build._structure_png(ChromData(xyz, spots), lines, 48)
    a, b = (np.asarray(Image.open(p).convert("RGBA"))[..., 3] > 0 for p in (out, lines))
    assert a.sum() and not np.array_equal(a, b)                 # dots, not the polyline of a fibre


def test_every_study_has_a_publication_date():
    """The page lists the studies newest first by ``published`` (YYYY-MM[-DD]); the year agrees with the citation's
    or comes before it (online ahead of print)."""
    import datetime
    import re

    cfg = json.loads((HERE.parent / "datasets.json").read_text())
    for s in cfg["studies"]:
        date = s.get("published", "")
        assert re.fullmatch(r"\d{4}-\d{2}(-\d{2})?", date), (s["id"], date)
        datetime.date.fromisoformat(date if len(date) == 10 else date + "-01")
        year = int(re.search(r"\b(?:19|20)\d\d\b", s["citation"]).group())
        assert year - 1 <= int(date[:4]) <= year, (s["id"], date, s["citation"])
