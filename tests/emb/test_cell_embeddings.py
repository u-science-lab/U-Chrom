"""uchrom.emb.embed_cells on synthetic and real (Takei 2021) RNA counts."""

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from uchrom import ChromData
from uchrom.emb import embed_cells, normalize_counts

DATA = Path(__file__).resolve().parents[2] / "example-data"


def _cd_with_counts(counts: np.ndarray):
    n = counts.shape[0]
    ids = [f"c{i}" for i in range(n)]
    spots = pd.DataFrame({"chrom": ["chr1"] * n, "start": np.zeros(n, int), "end": np.ones(n, int),
                          "trace_id": ids, "cell_id": ids})
    cells = pd.DataFrame(counts, columns=[f"rna.g{j}" for j in range(counts.shape[1])],
                         index=pd.Index(ids, name="cell_id"))
    cells["nucleus_area_um2"] = 100.0  # not part of the rna group
    return ChromData(np.zeros((n, 3)), spots, cells=cells)


def test_two_populations_separate_on_pc1_and_roundtrip(tmp_path):
    rng = np.random.default_rng(0)
    a = rng.poisson([50, 50, 2, 2, 10, 10], size=(30, 6))
    b = rng.poisson([2, 2, 50, 50, 10, 10], size=(30, 6))
    cd = _cd_with_counts(np.vstack([a, b]).astype(float))
    out = embed_cells(cd, methods=("pca", "tsne"), n_pcs=4)
    pc1 = out["rna_pca"][:, 0]
    assert out["rna_pca"].shape == (60, 4) and out["rna_tsne"].shape == (60, 2)
    assert np.sign(pc1[:30]).tolist().count(np.sign(pc1[0])) == 30  # group A on one side
    assert (np.sign(pc1[30:]) == -np.sign(pc1[0])).all()
    meta = cd.uns["embeddings"]["rna_pca"]
    assert meta["fields"] == [f"rna.g{j}" for j in range(6)] and meta["method"] == "pca"
    cd.write(tmp_path / "e.h5cd")
    back = ChromData.read(tmp_path / "e.h5cd")
    np.testing.assert_allclose(back.cellm["rna_tsne"], out["rna_tsne"])
    assert back.uns["embeddings"]["rna_tsne"]["label"] == "RNA t-SNE"


def test_normalize_counts_and_errors():
    x = normalize_counts(np.array([[0, 10], [0, 30], [0, 20]]))
    assert np.allclose(x[:, 0], 0) and np.isclose(x[:, 1].mean(), 0)
    with pytest.raises(ValueError, match="unknown methods"):
        embed_cells(_cd_with_counts(np.ones((5, 3))), methods=("mds",))
    with pytest.raises(ValueError, match="at least 2"):
        embed_cells(_cd_with_counts(np.ones((5, 1))))


@pytest.mark.skipif(not (DATA / "4DNFIFINA2U9.csv").exists(), reason="Takei cell table missing")
def test_takei_rna_pc2_is_naive_vs_primed_axis(tmp_path):
    from uchrom.core.cdata import _fofct_cell_table

    cells, _ = _fofct_cell_table(DATA / "4DNFIFINA2U9.csv", "rna.")
    n = len(cells)
    spots = pd.DataFrame({"chrom": ["chr1"] * n, "start": 0, "end": 1,
                          "trace_id": cells.index, "cell_id": cells.index})
    cd = ChromData(np.zeros((n, 3)), spots, cells=cells)
    out = embed_cells(cd, methods=("pca",))
    x = normalize_counts(cells[[c for c in cells.columns if c.startswith("rna.")]].to_numpy(float))
    genes = [c[4:] for c in cells.columns if c.startswith("rna.")]
    r = {g: np.corrcoef(x[:, j], out["rna_pca"][:, 1])[0, 1] for j, g in enumerate(genes)}
    naive = np.mean([r[g] for g in ("Nanog", "Esrrb", "Tfcp2l1", "Tbx3")])
    primed = np.mean([r[g] for g in ("Otx2", "Lin28a", "Lin28b", "Dnmt3a")])
    # PC2 separates naive from primed/formative markers (sign is arbitrary)
    assert abs(naive - primed) > 0.8 and np.sign(naive) != np.sign(primed)
