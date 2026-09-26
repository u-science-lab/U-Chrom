import numpy as np
import pandas as pd
import pytest


ad = pytest.importorskip("anndata")


def _make_cd_with_takei_like_cells():
    from uchrom import ChromData

    coords = np.zeros((4, 3), dtype=float)
    spots = pd.DataFrame({
        "chrom": ["chr1", "chr1", "chr2", "chr2"],
        "start": [0, 25_000, 0, 25_000],
        "end": [25_000, 50_000, 25_000, 50_000],
        "trace_id": ["c1_chr1_a0", "c2_chr1_a0", "c1_chr2_a0", "c2_chr2_a0"],
        "cell_id": ["c1", "c2", "c1", "c2"],
    })
    cells = pd.DataFrame({
        "leiden": [0, 2],
        "cell_type": ["Granule", "Bergmann"],
    }, index=pd.Index(["c1", "c2"], name="cell_id"))
    cellm = {"umap": np.array([[1.0, 1.1], [2.0, 2.2]])}
    tracks = pd.DataFrame({
        "SOX2": [0.1, 0.2, 0.3, 0.4],
        "Malat1_RNA": [1.0, 2.0, 3.0, 4.0],
    })
    return ChromData(coords, spots, cells=cells, cellm=cellm, tracks=tracks)


def test_link_anndata_preserves_existing_cells_and_aligns_obsm():
    cd = _make_cd_with_takei_like_cells()
    adata = ad.AnnData(
        X=np.ones((2, 3)),
        obs=pd.DataFrame(
            {"rna_cluster": ["B", "A"]},
            index=pd.Index(["c2", "c1"], name="rna_cell"),
        ),
        obsm={"X_pca": np.array([[20.0, 21.0], [10.0, 11.0]])},
    )

    matched = cd.link_anndata(adata)

    assert matched == 2
    assert list(cd.cells.index) == ["c1", "c2"]
    assert list(cd.cells["cell_type"]) == ["Granule", "Bergmann"]
    assert list(cd.cells["rna_cluster"]) == ["A", "B"]
    np.testing.assert_allclose(cd.cellm["umap"], [[1.0, 1.1], [2.0, 2.2]])
    np.testing.assert_allclose(cd.cellm["X_pca"], [[10.0, 11.0], [20.0, 21.0]])


def test_link_anndata_with_cell_id_column():
    cd = _make_cd_with_takei_like_cells()
    adata = ad.AnnData(
        X=np.ones((2, 1)),
        obs=pd.DataFrame({
            "external_id": ["c2", "c1"],
            "rna_cluster": ["B", "A"],
        }, index=["rna2", "rna1"]),
        obsm={"X_umap_rna": np.array([[8.0, 9.0], [6.0, 7.0]])},
    )

    cd.link_anndata(adata, cell_id_col="external_id")

    assert list(cd.cells.index) == ["c1", "c2"]
    assert list(cd.cells["rna_cluster"]) == ["A", "B"]
    np.testing.assert_allclose(cd.cellm["X_umap_rna"], [[6.0, 7.0], [8.0, 9.0]])


def test_to_anndata_exports_existing_cell_axis_without_tracks_in_x():
    cd = _make_cd_with_takei_like_cells()

    out = cd.to_anndata()

    assert out.shape == (2, 0)
    assert list(out.obs_names) == ["c1", "c2"]
    assert list(out.obs["cell_type"]) == ["Granule", "Bergmann"]
    np.testing.assert_allclose(out.obsm["umap"], [[1.0, 1.1], [2.0, 2.2]])
    assert cd.tracks is not None
    assert list(cd.tracks.columns) == ["SOX2", "Malat1_RNA"]


def test_to_anndata_builds_obs_from_spot_cell_ids_when_cells_empty():
    from uchrom import ChromData

    spots = pd.DataFrame({
        "chrom": ["chr1", "chr1", "chr1"],
        "start": [0, 1, 2],
        "end": [1, 2, 3],
        "trace_id": ["t1", "t2", "t1"],
        "cell_id": ["b", "a", "b"],
    })
    cd = ChromData(np.zeros((3, 3)), spots)

    out = cd.to_anndata()

    assert out.shape == (2, 0)
    assert list(out.obs_names) == ["b", "a"]


def test_link_anndata_rejects_duplicate_ann_data_ids():
    cd = _make_cd_with_takei_like_cells()
    adata = ad.AnnData(
        X=np.ones((2, 1)),
        obs=pd.DataFrame(index=["c1", "c1"]),
    )

    with pytest.raises(ValueError, match="duplicate"):
        cd.link_anndata(adata)


def test_anndata_link_roundtrips_h5cd_cell_axis(tmp_path):
    from uchrom import ChromData

    cd = _make_cd_with_takei_like_cells()
    adata = ad.AnnData(
        X=np.ones((2, 1)),
        obs=pd.DataFrame({"rna_cluster": ["B", "A"]}, index=["c2", "c1"]),
        obsm={"X_pca": np.array([[20.0, 21.0], [10.0, 11.0]])},
    )
    cd.link_anndata(adata)

    path = tmp_path / "linked.chromdata.zarr"
    cd.write(path)
    out = ChromData.read(path)

    assert list(out.cells.index) == ["c1", "c2"]
    assert list(out.cells["rna_cluster"]) == ["A", "B"]
    np.testing.assert_allclose(out.cellm["umap"], [[1.0, 1.1], [2.0, 2.2]])
    np.testing.assert_allclose(out.cellm["X_pca"], [[10.0, 11.0], [20.0, 21.0]])
