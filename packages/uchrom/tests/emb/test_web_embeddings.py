"""Embeddings from ``uchrom.emb.embed_cells`` carry the modality and method the web browser shows."""

import numpy as np
import pandas as pd
import pytest

pytest.importorskip("uchrom_browser")
pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402

from chromdata import ChromData  # noqa: E402
from uchrom_browser import create_app  # noqa: E402
from uchrom_browser.data import DatasetStore  # noqa: E402


def test_embedding_modalities(tmp_path):
    """Embeddings from embed_cells (RNA, IF, ATAC) carry modality + method;
    unknown keys fall back to 'Published' / 'Other'."""
    from uchrom.emb import embed_cells

    rng = np.random.default_rng(0)
    n = 12
    ids = [f"c{i}" for i in range(n)]
    spots = pd.DataFrame({"chrom": "chr1", "start": 0, "end": 1, "trace_id": ids, "cell_id": ids})
    cells = pd.DataFrame(rng.poisson(5, size=(n, 4)), columns=[f"rna.g{j}" for j in range(4)],
                         index=pd.Index(ids, name="cell_id"))
    for j in range(3):
        cells[f"if.m{j}"] = rng.normal(size=n)
    cd = ChromData(np.zeros((n, 3)), spots, cells=cells,
                   cellm={"paper_umap": rng.normal(size=(n, 2)), "umap": rng.normal(size=(n, 2))})
    embed_cells(cd, source="rna", methods=("pca",))
    embed_cells(cd, source="if", methods=("pca",))
    embed_cells(cd, source="atac", matrix=rng.poisson(1, size=(n, 40)), methods=("pca",), drop_depth_r=None)
    path = tmp_path / "mod.chromdata.zarr"
    cd.write(path)
    store = DatasetStore()
    store.load(path)
    c = TestClient(create_app(store))
    embs = {e["key"]: e for e in c.get("/api/datasets").json()[0]["embeddings"]}
    assert {k: (e["modality"], e["method"]) for k, e in embs.items()} == {
        "paper_umap": ("Published", "umap"), "umap": ("Other", "umap"),
        "rna_pca": ("RNA", "pca"), "if_pca": ("Histone/IF", "pca"), "atac_lsi": ("ATAC", "lsi")}
    assert embs["atac_lsi"]["label"] == "ATAC LSI"
    e = c.get("/api/datasets/d1/embedding/atac_lsi").json()
    assert e["axis_labels"] == ["LSI1", "LSI2"]
