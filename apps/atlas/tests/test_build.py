"""The atlas app (apps/atlas/build.py): thumbnails drawn from the stores and the static page.

Run from apps/atlas: ``pytest tests`` (needs chromdata with cooler / anndata, matplotlib, Pillow)."""

import importlib.util
import inspect
import json
import shutil
import sys
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


def test_build_site_has_no_agent_handoff_endpoint_setting(tmp_path, monkeypatch):
    catalog = tmp_path / "catalog.json"
    catalog.write_text(json.dumps({"datasets": [{"id": "toy", "path": "toy.zarr"}]}))

    site = build.build_site(tmp_path / "site", catalog)
    config = json.loads((site / "config.js").read_text().split("=", 1)[1].strip().removesuffix(";"))
    assert "agentHandoff" not in config
    assert "agent_handoff" not in inspect.signature(build.build_site).parameters

    monkeypatch.setattr(sys, "argv", ["build.py", "site", str(tmp_path / "cli-site"), "--catalog", str(catalog),
                                       "--agent-handoff", "https://browser.example/api/agent/handoffs"])
    with pytest.raises(SystemExit) as exc:
        build.main()
    assert exc.value.code == 2


def test_atlas_template_builds_local_browser_command_and_mcp_instruction(tmp_path):
    catalog = tmp_path / "catalog.json"
    catalog.write_text(json.dumps({"datasets": [{"id": "toy", "path": "toy.zarr"}]}))
    site = build.build_site(tmp_path / "site", catalog)
    app = (site / "app.js").read_text()
    html = (site / "index.html").read_text()

    assert "Continue locally" in app
    assert "python -m uchrom_browser " in app
    assert "urlOf(d)" in app
    assert "handoff-instruction" in app and "handoff-copy-command" in app and "handoff-copy-instruction" in app
    assert "fetch(HANDOFF)" not in app and "agentHandoff" not in app and "token" not in app.lower()
    assert "dataRoot + '/' + d.path" not in app
    assert "not on PyPI" in html
    assert "packages/chromdata" in html and "packages/uchrom-browser" in html
    assert "U-Chrom MCP" in html and "Claude Code" in html and "Codex" in html


def test_atlas_publish_docs_do_not_require_a_handoff_endpoint():
    publish = (HERE.parent / "PUBLISH.md").read_text()
    apps_readme = (HERE.parents[1] / "README.md").read_text()

    assert "--agent-handoff" not in publish
    assert "--agent-handoff" not in apps_readme


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
