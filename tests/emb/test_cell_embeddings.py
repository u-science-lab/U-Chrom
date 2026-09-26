"""uchrom.emb.embed_cells / aggregate_tracks / scHiCluster on synthetic data and
real (Takei 2021) RNA counts."""

import numpy as np
import pandas as pd
import pytest

from uchrom import ChromData
from uchrom.datasets import example_path
from uchrom.emb import aggregate_tracks, embed_cells, normalize_counts, schicluster_features, tfidf_lsi

DATA = example_path("takei2021_mesc")


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
    cd.write(tmp_path / "e.chromdata.zarr")
    back = ChromData.read(tmp_path / "e.chromdata.zarr")
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


def _separates(x: np.ndarray, n_a: int) -> bool:
    """1-NN of every cell is in its own group."""
    from sklearn.neighbors import NearestNeighbors

    y = np.r_[np.zeros(n_a), np.ones(len(x) - n_a)]
    idx = NearestNeighbors(n_neighbors=2).fit(x).kneighbors(x, return_distance=False)[:, 1]
    return bool((y[idx] == y).mean() > 0.95)


def test_if_zscore_embedding_modality_and_log():
    rng = np.random.default_rng(1)
    a = rng.normal([2, 2, 0, 0], 0.3, size=(20, 4))
    b = rng.normal([0, 0, 2, 2], 0.3, size=(20, 4))
    cd = _cd_with_counts(np.ones((40, 2)))
    for j in range(4):
        cd.cells[f"if.m{j}"] = np.vstack([a, b])[:, j]
    out = embed_cells(cd, source="if", methods=("pca",), n_pcs=3)
    meta = cd.uns["embeddings"]["if_pca"]
    assert meta["normalization_kind"] == "zscore" and meta["modality"] == "Histone/IF"
    assert meta["label"] == "Histone/IF PCA" and meta["fields"] == [f"if.m{j}" for j in range(4)]
    assert _separates(out["if_pca"], 20)
    with pytest.raises(ValueError, match="non-negative"):
        embed_cells(cd, source="if", methods=("pca",), log=True)


def test_tfidf_lsi_drops_depth_component_and_separates():
    import scipy.sparse as sp

    rng = np.random.default_rng(2)
    n, n_peaks = 80, 400
    group = np.r_[np.zeros(40, int), np.ones(40, int)]
    prof = np.full((2, n_peaks), 0.02)
    prof[0, :150] = 0.3  # group-specific peaks
    prof[1, 150:300] = 0.3
    depth = rng.uniform(0.3, 3.0, size=n)  # strongly varying sequencing depth
    x = rng.poisson(prof[group] * depth[:, None] * 2)
    lsi, info = tfidf_lsi(sp.csr_matrix(x), n_components=10)
    assert info["dropped"] in ([1], [])
    assert lsi.shape[0] == n and _separates(lsi[:, :5], 40)
    # all components kept when asked
    lsi_all, info_all = tfidf_lsi(x, n_components=10, drop_depth_r=None)
    assert info_all["dropped"] == [] and lsi_all.shape[1] == 10
    # depth-dominated component 1 is dropped: fake depth-only signal
    y = rng.poisson(np.outer(np.linspace(0.2, 5, n), np.full(n_peaks, 0.5)))
    _, info_d = tfidf_lsi(y, n_components=5)
    assert abs(info_d["depth_r"][0]) > 0.5 and info_d["dropped"] == [1]

    cd = _cd_with_counts(np.ones((n, 2)))
    out = embed_cells(cd, source="atac", matrix=sp.csr_matrix(x), methods=("pca", "tsne"),
                      n_lsi=8, features="synthetic peaks")
    assert set(out) == {"atac_lsi", "atac_tsne"}
    meta = cd.uns["embeddings"]["atac_lsi"]
    assert meta["method"] == "lsi" and meta["axis_prefix"] == "LSI" and meta["modality"] == "ATAC"
    assert meta["normalization_kind"] == "tfidf" and "fields" not in meta
    assert meta["features"] == "synthetic peaks" and meta["n_features"] == n_peaks
    assert cd.uns["embeddings"]["atac_tsne"]["input"] == "lsi"
    with pytest.raises(ValueError, match="n_cells"):
        embed_cells(cd, source="atac", matrix=x[:5])
    with pytest.raises(ValueError, match="normalization"):
        embed_cells(cd, source="atac", matrix=x, normalization="magic")


def _cd_with_tracks():
    # 2 cells × 2 chroms × 3 spots; mark A tracks mark B in c0, anti in c1
    cell = ["c0"] * 6 + ["c1"] * 6
    chrom = (["chr1"] * 3 + ["chr2"] * 3) * 2
    start = [0, 5_000_000, 15_000_000] * 4
    spots = pd.DataFrame({"chrom": chrom, "start": start, "end": np.array(start) + 1,
                          "trace_id": [f"{c}_{h}" for c, h in zip(cell, chrom)], "cell_id": cell})
    a = np.array([1, 2, 3, 4, 5, 6, 1, 2, 3, 4, 5, 6], float)
    b = np.r_[a[:6] * 2, -a[6:]]
    tracks = pd.DataFrame({"A": a, "B": b})
    cells = pd.DataFrame({"cell_type": ["x", "y"]}, index=pd.Index(["c0", "c1"], name="cell_id"))
    return ChromData(np.zeros((12, 3)), spots, cells=cells, tracks=tracks)


def test_aggregate_tracks_mean_by_and_corr(tmp_path):
    cd = _cd_with_tracks()
    m = aggregate_tracks(cd, ["A", "B"], prefix="if")
    assert list(m.columns) == ["if.A", "if.B"]
    assert m.loc["c0", "if.A"] == 3.5 and m.loc["c1", "if.B"] == -3.5
    assert list(cd.cells.columns) == ["cell_type", "if.A", "if.B"]
    byc = aggregate_tracks(cd, ["A"], prefix="if", by="chrom", write=False)
    assert list(byc.columns) == ["if.A@chr1", "if.A@chr2"] and byc.loc["c0", "if.A@chr2"] == 5.0
    byb = aggregate_tracks(cd, ["A"], prefix="if", by=10_000_000, write=False)
    assert list(byb.columns) == ["if.A@chr1:0", "if.A@chr1:1", "if.A@chr2:0", "if.A@chr2:1"]
    assert byb.loc["c0", "if.A@chr1:0"] == 1.5
    corr = aggregate_tracks(cd, ["A", "B"], prefix="if", stat="corr", write=False)
    assert list(corr.columns) == ["if.A~B"]
    np.testing.assert_allclose(corr["if.A~B"].to_numpy(), [1.0, -1.0])
    sd = aggregate_tracks(cd, ["A"], prefix="if", stat="std", min_spots=7, write=False)
    assert sd.isna().all().all()  # every cell has 6 spots < min_spots
    # rerunning replaces columns instead of duplicating them
    aggregate_tracks(cd, ["A", "B"], prefix="if")
    assert list(cd.cells.columns) == ["cell_type", "if.A", "if.B"]
    cd.write(tmp_path / "t.chromdata.zarr")
    assert ChromData.read(tmp_path / "t.chromdata.zarr").cells["if.A"].tolist() == [3.5, 3.5]
    with pytest.raises(ValueError, match="stat"):
        aggregate_tracks(cd, ["A"], stat="max")
    with pytest.raises(KeyError):
        aggregate_tracks(cd, ["nope"])


def test_schicluster_separates_domain_patterns():
    rng = np.random.default_rng(3)
    n = 30

    def maps(blocks, count):
        out = np.zeros((count, n, n))
        for c in range(count):
            m = np.zeros((n, n))
            for lo, hi in blocks:
                k = rng.poisson(4, size=(hi - lo, hi - lo)).astype(float)
                m[lo:hi, lo:hi] += np.triu(k) + np.triu(k, 1).T
            keep = rng.random((n, n)) < 0.3  # sparse single-cell sampling
            keep = np.triu(keep) | np.triu(keep, 1).T
            out[c] = m * keep
        return out

    a = maps([(0, 10), (10, 20), (20, 30)], 15)
    b = maps([(0, 15), (15, 30)], 15)
    feats, cols = schicluster_features({"chr1": np.concatenate([a, b])}, n_per_chrom=5)
    assert feats.shape == (30, 5) and cols[0] == "chr1_PC1"
    assert _separates(feats, 15)
    cd = _cd_with_counts(np.ones((30, 2)))
    embed_cells(cd, source="hic", matrix=feats, methods=("pca",), n_pcs=3)
    assert cd.uns["embeddings"]["hic_pca"]["modality"] == "Hi-C"
    assert cd.uns["embeddings"]["hic_pca"]["normalization_kind"] == "none"


def test_scool_cell_features_roundtrip(tmp_path):
    cooler = pytest.importorskip("cooler")
    from uchrom.emb import scool_cell_features

    bins = pd.DataFrame({"chrom": ["chr1"] * 6 + ["chr2"] * 4, "start": [0, 1, 2, 3, 4, 5, 0, 1, 2, 3],
                         "end": [1, 2, 3, 4, 5, 6, 1, 2, 3, 4]})
    rng = np.random.default_rng(4)
    cells = {}
    for i in range(6):
        b1 = rng.integers(0, 6, 20)
        b2 = rng.integers(0, 6, 20)
        lo, hi = np.minimum(b1, b2), np.maximum(b1, b2)
        px = pd.DataFrame({"bin1_id": lo, "bin2_id": hi, "count": 1}).groupby(
            ["bin1_id", "bin2_id"], as_index=False)["count"].sum()
        cells[f"cell{i}"] = px
    path = str(tmp_path / "c.scool")
    cooler.create_scool(path, bins, cells, ordered=True)
    names = [f"cell{i}" for i in range(6)] + ["absent"]
    feats, cols, depth = scool_cell_features(path, names, n_per_chrom=2)
    assert feats.shape == (7, 2) and cols == ["chr1_PC1", "chr1_PC2"]  # chr2 empty: skipped
    assert depth[-1] == 0 and depth[0] == 20
