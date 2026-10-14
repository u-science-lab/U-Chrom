"""uchrom.emb: embed_contacts (scHiCluster on the linked / embedded maps), gene selection, embed_cells on a
subset of cells, aggregate_tracks streamed from a backed store, plot_embedding."""

from __future__ import annotations

import warnings

import numpy as np
import pandas as pd
import pytest

from uchrom import ChromData

from .test_cell_embeddings import _cd_with_tracks


def _no_spots():
    return pd.DataFrame({c: pd.Series(dtype=t) for c, t in
                         [("chrom", str), ("start", np.int64), ("end", np.int64), ("trace_id", str), ("cell_id", str)]})


def _cd_with_scool(tmp_path, n=12, size=6):
    """Cells without spots and a linked .scool: two domain patterns on chr1 / chr2 (``size`` bins each) + chrY."""
    cooler = pytest.importorskip("cooler")
    sizes = {"chr1": size, "chr2": size, "chrY": 3}
    bins = pd.concat([pd.DataFrame({"chrom": c, "start": np.arange(k) * 100, "end": np.arange(k) * 100 + 100})
                      for c, k in sizes.items()], ignore_index=True)
    rng = np.random.default_rng(0)
    maps, names = {}, [f"c{i}" for i in range(n)]
    for i, name in enumerate(names):
        blocks = [(0, size // 2), (size // 2, size)] if i % 2 == 0 else [(0, size)]
        rows = []
        for off in (0, size):                                # chr1, chr2
            for lo, hi in blocks:
                a, b = np.triu_indices(hi - lo)
                keep = rng.random(len(a)) < 0.7
                rows.append(pd.DataFrame({"bin1_id": a[keep] + lo + off, "bin2_id": b[keep] + lo + off,
                                          "count": rng.integers(1, 6, keep.sum())}))
        rows.append(pd.DataFrame({"bin1_id": [0], "bin2_id": [size + 1], "count": [3]}))   # a trans contact
        maps[name] = pd.concat(rows).groupby(["bin1_id", "bin2_id"], as_index=False)["count"].sum()
    cooler.create_scool(str(tmp_path / "cells.scool"), bins, maps, ordered=True)
    cells = pd.DataFrame({"pattern": ["split" if i % 2 == 0 else "one" for i in range(n)]},
                         index=pd.Index(names, name="cell_id"))
    cd = ChromData(np.zeros((0, 3)), _no_spots(), cells=cells, uns={"genome_assembly": "toy"})
    cd.link_scool("cells.scool", key="per_cell", genome_assembly="toy", bin_size=100)
    cd.write(tmp_path / "cells.chromdata.zarr")                 # the link resolves next to the store
    return ChromData.read(tmp_path / "cells.chromdata.zarr"), maps


def test_embed_contacts_is_schicluster_on_the_linked_maps(tmp_path):
    from uchrom.emb import embed_cells, embed_contacts, scool_cell_features

    cd, maps = _cd_with_scool(tmp_path, size=12)    # 12 bins: the top 20 % reaches beyond the diagonal
    out = embed_contacts(cd, n_per_chrom=3, n_pcs=4, methods=("pca", "tsne"))
    assert sorted(out) == ["hic_pca", "hic_tsne"] and out["hic_pca"].shape == (12, 4)
    # the same as the three steps it replaces (chrY left out by default)
    feats, cols, depth = scool_cell_features(str(tmp_path / "cells.scool"), list(cd.cells.index),
                                             chroms=["chr1", "chr2"], n_per_chrom=3)
    ref = ChromData(np.zeros((0, 3)), _no_spots(), cells=cd.cells[[]].copy())
    embed_cells(ref, source="hic", matrix=feats, normalization="none", n_pcs=4, methods=("pca", "tsne"))
    np.testing.assert_allclose(cd.cellm["hic_pca"], ref.cellm["hic_pca"])
    np.testing.assert_allclose(cd.cellm["hic_tsne"], ref.cellm["hic_tsne"])
    np.testing.assert_allclose(cd.results["hic"], feats.astype(np.float32))
    # intra-chromosomal contacts of chr1 / chr2 per cell (no trans, no chrY)
    want = [int(m.loc[(m["bin1_id"] // 12 == m["bin2_id"] // 12) & (m["bin2_id"] < 24), "count"].sum())
            for m in maps.values()]
    assert cd.cells["hic_n_cis_contacts"].tolist() == want
    assert (depth == np.array(want) + 3).all()            # scool_cell_features: every pixel (+ the trans one)
    meta = cd.uns["embeddings"]["hic_pca"]
    assert meta["modality"] == "Hi-C" and meta["normalization_kind"] == "none" and "scHiCluster" in meta["features"]
    assert cd.uns["hic"]["chroms"] == ["chr1", "chr2"] and cd.uns["hic"]["resolution"] == 100
    assert cd.results.record("hic").function == "uchrom.emb.embed_contacts"
    # PC1 separates the two domain patterns completely
    pc1 = pd.Series(cd.cellm["hic_pca"][:, 0], index=cd.cells.index).groupby(cd.cells["pattern"]).agg(["min", "max"])
    assert pc1.loc["one", "max"] < pc1.loc["split", "min"] or pc1.loc["split", "max"] < pc1.loc["one", "min"]


def test_embed_contacts_subset_copy_and_errors(tmp_path):
    from uchrom.emb import embed_contacts

    cd, _ = _cd_with_scool(tmp_path)
    pick = ["c5", "c0", "c2", "c7", "c9", "c4"]
    new = embed_contacts(cd, cells=pick, chroms=["chr2"], n_per_chrom=2, n_pcs=2, methods=("pca",),
                         key_added="hic2", copy=True)
    assert "hic2_pca" not in cd.cellm and "hic2" not in cd.uns            # copy=True leaves cd alone
    x = new.cellm["hic2_pca"]
    rows = [list(cd.cells.index).index(c) for c in pick]
    assert np.isfinite(x[rows]).all() and np.isnan(np.delete(x, rows, axis=0)).all()
    assert new.uns["embeddings"]["hic2_pca"]["n_cells"] == 6 and new.uns["hic2"]["chroms"] == ["chr2"]
    assert new.cells["hic2_n_cis_contacts"].isna().sum() == 6
    with pytest.raises(ValueError, match="embed_higashi"):
        embed_contacts(cd, method="higashi")
    with pytest.raises(KeyError, match="nope"):
        embed_contacts(cd, cells=["c1", "nope"])


def test_embed_contacts_reads_the_maps_embedded_in_a_store(tmp_path):
    pytest.importorskip("anndata")
    from chromdata.embedded import embed_links
    from chromdata.testing import linked_store

    from uchrom.emb import embed_contacts

    _, store = linked_store(tmp_path)
    embed_links(store, verbose=False)
    (tmp_path / "cells.scool").unlink()                          # only the embedded copy is left
    cd = ChromData.read(store, backed=True)
    out = embed_contacts(cd, contacts="cells", n_per_chrom=2, n_pcs=2, methods=("pca",))
    assert out["hic_pca"].shape == (3, 2) and np.isfinite(out["hic_pca"]).all()
    assert (cd.cells["hic_n_cis_contacts"] > 0).all()
    sub = embed_contacts(cd.copy(), contacts="cells", cells=["c2", "c0"], n_per_chrom=1, n_pcs=2, methods=("pca",),
                         copy=True)                               # a subset exported from the embedded copy
    assert np.isnan(sub.cellm["hic_pca"][1]).all() and np.isfinite(sub.cellm["hic_pca"][[0, 2]]).all()


def test_embed_cells_on_a_subset_and_cluster_cells_skips_missing_rows():
    pytest.importorskip("leidenalg")
    from uchrom.emb import cluster_cells, embed_cells

    rng = np.random.default_rng(0)
    n = 40
    lab = np.repeat([0, 1], n // 2)
    counts = rng.poisson(np.where(lab[:, None] == 0, [40, 40, 2, 2], [2, 2, 40, 40]))
    cells = pd.DataFrame(counts, columns=[f"rna.g{j}" for j in range(4)],
                         index=pd.Index([f"c{i}" for i in range(n)], name="cell_id"))
    cd = ChromData(np.zeros((0, 3)), _no_spots(), cells=cells)
    keep = np.arange(n) % 5 != 0                                   # 8 cells left out
    out = embed_cells(cd, methods=("pca",), n_pcs=2, cells=keep)
    x = out["rna_pca"]
    assert np.isnan(x[~keep]).all() and np.isfinite(x[keep]).all()
    full = embed_cells(ChromData(np.zeros((0, 3)), _no_spots(), cells=cells[keep]), methods=("pca",), n_pcs=2)
    np.testing.assert_allclose(x[keep], full["rna_pca"])
    # ids in a given order, with a matrix whose rows follow them
    ids = ["c3", "c1", "c2"]
    m = np.array([[0.0, 1.0], [1.0, 0.0], [2.0, 2.0]])
    new = embed_cells(cd, source="hic", matrix=m, cells=ids, normalization="none", methods=("pca",), copy=True)
    assert "hic_pca" not in cd.cellm and np.isfinite(new.cellm["hic_pca"][[1, 2, 3]]).all()
    with pytest.raises(ValueError, match="len\\(cells\\)"):
        embed_cells(cd, source="hic", matrix=m[:2], cells=ids, normalization="none")
    with pytest.raises(KeyError):
        embed_cells(cd, cells=["c1", "zz"])
    s = cluster_cells(cd, use="rna_pca", n_neighbors=5, resolution=0.3)
    assert s[~keep].isna().all() and s[keep].notna().all()
    assert pd.crosstab(s[keep].to_numpy(), lab[keep]).max(axis=1).tolist() == [16, 16]
    assert cd.uns["clusters"]["leiden_rna_pca"]["n_cells"] == int(keep.sum())


def _counts(rng, n_cells=200):
    """Two populations; genes 0-9 differ between them (variable), 10-59 do not, 60 is almost never seen."""
    a = np.r_[np.full(10, 40.0), np.full(50, 10.0), 0.002]
    b = np.r_[np.full(10, 1.0), np.full(50, 10.0), 0.002]
    lam = np.where((np.arange(n_cells) % 2 == 0)[:, None], a, b)
    return rng.poisson(lam).astype(float)


def _seurat_v1_reference(X, n_top=2000, n_bins=20, min_frac=0.01):
    """The selection of tutorials/cell_embeddings.ipynb before it moved into the library."""
    import scipy.sparse as sp

    totals = np.asarray(X.sum(1)).ravel()
    norm = sp.diags(1e4 / totals) @ X
    norm.data = np.log1p(norm.data)
    mean = np.asarray(norm.mean(0)).ravel()
    var = np.asarray(norm.multiply(norm).mean(0)).ravel() - mean ** 2
    disp = np.log(np.maximum(var, 1e-12) / np.maximum(mean, 1e-12))
    ok = np.asarray((X > 0).mean(0)).ravel() >= min_frac
    frame = pd.DataFrame({"disp": disp, "bin": pd.cut(mean, n_bins)})
    stats = frame[ok].groupby("bin", observed=True)["disp"].agg(["mean", "std"])
    z = (disp - frame["bin"].map(stats["mean"]).astype(float)) / frame["bin"].map(stats["std"]).astype(float)
    z = np.where(ok & np.isfinite(z), z, -np.inf)
    return np.argsort(-z)[:n_top]


def test_highly_variable_genes_ranks_the_genes_that_differ():
    import scipy.sparse as sp

    from uchrom.emb import highly_variable_genes

    x = _counts(np.random.default_rng(0))
    top = highly_variable_genes(x, n_top=10, n_bins=1)            # one bin: the dispersion z-scored over all genes
    assert sorted(top.tolist()) == list(range(10))
    np.testing.assert_array_equal(highly_variable_genes(sp.csr_matrix(x), n_top=10, n_bins=1), top)
    every = highly_variable_genes(x, n_top=1000, n_bins=1, min_frac=0.05)
    assert 60 not in every and len(every) == 60                   # the rare gene is left out
    # binned (Seurat v1) on noisy counts: the same as the recipe it replaces
    rng = np.random.default_rng(2)
    noisy = sp.csr_matrix(rng.negative_binomial(2, rng.uniform(0.05, 0.95, 300), size=(150, 300)).astype(float))
    np.testing.assert_array_equal(highly_variable_genes(noisy, n_top=50), _seurat_v1_reference(noisy, n_top=50))


def test_add_gene_counts_from_the_linked_matrix():
    anndata = pytest.importorskip("anndata")
    from uchrom.emb import add_gene_counts

    rng = np.random.default_rng(1)
    x = _counts(rng)
    names = [f"c{i}" for i in range(len(x))]
    ad = anndata.AnnData(x, obs=pd.DataFrame(index=names[::-1]),          # rows in another order
                         var=pd.DataFrame(index=[f"g{j}" for j in range(x.shape[1])]))
    ad.X = ad.X[::-1].copy()
    cells = pd.DataFrame({"rna.old": 1.0, "cell_type": "t"}, index=pd.Index(names, name="cell_id"))
    cd = ChromData(np.zeros((0, 3)), _no_spots(), cells=cells)
    cd.linked_adata = ad
    genes = add_gene_counts(cd, n_top=10, n_bins=1)
    assert sorted(genes) == [f"g{j}" for j in range(10)]
    assert list(cd.cells.columns) == ["cell_type"] + [f"rna.{g}" for g in genes]     # rna.old replaced
    np.testing.assert_array_equal(cd.cells[f"rna.{genes[0]}"].to_numpy(), x[:, int(genes[0][1:])])
    table = cd.results["rna.genes"]
    assert table["gene"].tolist() == genes and (np.diff(table["dispersion_z"]) <= 0).all()
    # explicit genes, kept next to the others; a cell without counts
    cd.cells = cd.cells.rename(index={"c0": "zz"})
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        add_gene_counts(cd, ["g20", "g11"], prefix="sel", replace=False)
    assert any("no row" in str(m.message) for m in w)
    assert np.isnan(cd.cells.loc["zz", "sel.g20"]) and cd.cells.loc["c1", "sel.g11"] == x[1, 11]
    with pytest.raises(KeyError, match="g999"):
        add_gene_counts(cd, ["g999"])


def test_aggregate_tracks_streams_a_backed_store_in_one_pass(tmp_path):
    from uchrom.emb import aggregate_tracks

    cd = _cd_with_tracks()
    path = tmp_path / "t.chromdata.zarr"
    cd.write(path)
    mem = ChromData.read(path)
    backed = ChromData.read(path, backed=True)
    both = aggregate_tracks(backed, ["A", "B"], stat=["corr", "mean"], write=False, batch=1)
    assert sorted(both) == ["corr", "mean"]
    for s in ("corr", "mean"):
        pd.testing.assert_frame_equal(both[s], aggregate_tracks(mem, ["A", "B"], stat=s, write=False))
    pd.testing.assert_frame_equal(aggregate_tracks(backed, ["A"], by="chrom", write=False, batch=1),
                                  aggregate_tracks(mem, ["A"], by="chrom", write=False))
    aggregate_tracks(backed, ["A", "B"], stat=["corr", "mean"], batch=1)          # write both
    assert list(backed.cells.columns[-3:]) == ["if.A~B", "if.A", "if.B"]
    with pytest.raises(ValueError, match="same name"):
        aggregate_tracks(mem, ["A"], stat=["mean", "std"])
    with pytest.raises(ValueError, match="corr"):
        aggregate_tracks(mem, ["A", "B"], stat=["corr"], by="chrom")


def test_plot_embedding_groups_values_and_missing_rows():
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    from uchrom.emb import plot_embedding

    rng = np.random.default_rng(0)
    n = 30
    xy = rng.normal(size=(n, 3))
    xy[0] = np.nan                                                  # not embedded: not drawn
    cells = pd.DataFrame({"type": np.repeat(["a", "b", "c"], 10), "depth": np.arange(n, dtype=float)},
                         index=pd.Index([f"c{i}" for i in range(n)], name="cell_id"))
    cells.loc["c1", "type"] = None
    cd = ChromData(np.zeros((0, 3)), _no_spots(), cells=cells, cellm={"rna_umap": xy},
                   uns={"embeddings": {"rna_umap": {"label": "RNA UMAP", "axis_prefix": "UMAP"}}})
    fig, axes = plt.subplots(1, 3)
    ax = plot_embedding(cd, "rna_umap", "type", ax=axes[0], legend=True)
    assert ax.get_title() == "RNA UMAP: type" and ax.get_xlabel() == "UMAP1"
    assert [t.get_text() for t in ax.texts] == ["a", "b", "c"]
    drawn = sum(len(c.get_offsets()) for c in ax.collections)
    assert drawn == n - 1                                            # the NaN row is left out, c1 drawn grey
    plot_embedding(cd, "rna_umap", "depth", ax=axes[1], dims=(1, 2), title="depth")
    assert len(fig.axes) == 4                                        # + a colour bar
    plot_embedding(cd, "rna_umap", np.log1p(cells["depth"].to_numpy()), ax=axes[2], colorbar=False)
    with pytest.raises(KeyError):
        plot_embedding(cd, "nope")
    plt.close(fig)
