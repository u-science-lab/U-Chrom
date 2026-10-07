import numpy as np
import pandas as pd
import pytest


ad = pytest.importorskip("anndata")


def _write_takei_like_inputs(tmp_path):
    dna = pd.DataFrame({
        "rep": [1, 1, 1, 1],
        "fov": [0, 0, 0, 0],
        "cellID": [1, 1, 2, 2],
        "name": ["chr19-1", "chr19-2", "chr19-1", "chr19-2"],
        "chrom": ["chr19"] * 4,
        "dbscan_allele": [0, 0, 0, 0],
        "dbscan_ldp_allele": [0, 0, 0, 0],
        "dbscan_ldp_nbr_allele": [0, 0, 0, 0],
        "x_um": [0.1, 0.2, 1.1, 1.2],
        "y_um": [0.3, 0.4, 1.3, 1.4],
        "z_um": [0.5, 0.6, 1.5, 1.6],
        "SOX2": [1.0, 2.0, 3.0, 4.0],
        "Malat1_RNA": [0.1, 0.2, 0.3, 0.4],
        "dot_int": [10, 11, 12, 13],
        "n_rad_score": [0.1, 0.2, 0.3, 0.4],
        "n_per_dist(um)": [1.0, 1.1, 1.2, 1.3],
    })
    dna_path = tmp_path / "cerebellum_rep1_pos0.csv"
    dna.to_csv(dna_path, index=False)

    locus = pd.DataFrame({
        "name": ["chr19-1", "chr19-2"],
        "chrom": ["chr19", "chr19"],
        "start": [0, 25_000],
        "end": [25_000, 50_000],
    })
    locus_path = tmp_path / "locus_annotation.csv"
    locus.to_csv(locus_path, index=False)

    clustering = pd.DataFrame({
        "rep": [1, 1],
        "fov": [0, 0],
        "cellID": [1, 2],
        "leiden": [0, 2],
        "umap_1": [5.0, 6.0],
        "umap_2": [7.0, 8.0],
        "x": [1.0, 2.0],
        "y": [3.0, 4.0],
        "z": [5.0, 6.0],
        "nuc_volume(um3)": [100.0, 200.0],
        "doublet": [0, 0],
        "batch": [1, 1],
    })
    clustering_path = tmp_path / "clustering.csv"
    clustering.to_csv(clustering_path, index=False)

    rna = pd.DataFrame({
        "fov": [0, 0, 0, 0, 0],
        "cellID": [1, 1, 2, 2, 2],
        "geneID": ["GeneA", "GeneB", "GeneA", "GeneA", "GeneC"],
        "intensity": [1.0, 2.0, 3.0, 4.0, 5.0],
        "x": [1, 2, 3, 4, 5],
        "y": [1, 2, 3, 4, 5],
        "z": [1, 2, 3, 4, 5],
    })
    rna_path = tmp_path / "cerebellum-replicate1-mRNA-seqFISH-non-barcoded-ch1.csv"
    rna.to_csv(rna_path, index=False)
    return dna_path, locus_path, clustering_path, rna_path


def test_read_seqfish_transcriptome_aggregates_spots(tmp_path):
    from uchrom.io.seqfish_multiomics import read_seqfish_transcriptome

    _, _, _, rna_path = _write_takei_like_inputs(tmp_path)

    adata = read_seqfish_transcriptome(
        rna_path,
        observed_cell_ids=["1_0_1", "1_0_2", "1_0_3"],
        chunksize=2,
    )

    assert list(adata.obs_names) == ["1_0_1", "1_0_2", "1_0_3"]
    assert set(adata.var_names) == {"GeneA", "GeneB", "GeneC"}
    dense = pd.DataFrame(
        adata.X.toarray(),
        index=adata.obs_names,
        columns=adata.var_names,
    )
    assert dense.loc["1_0_1", "GeneA"] == 1
    assert dense.loc["1_0_2", "GeneA"] == 2
    assert dense.loc["1_0_2", "GeneC"] == 1
    assert dense.loc["1_0_3"].sum() == 0


def test_load_seqfish_multiomics_linked_writes_store_and_h5ad(tmp_path):
    from uchrom import ChromData
    from uchrom.io.seqfish_multiomics import load_seqfish_multiomics_linked

    dna_path, locus_path, clustering_path, rna_path = _write_takei_like_inputs(tmp_path)
    cd_path = tmp_path / "takei.chromdata.zarr"
    h5ad_path = tmp_path / "takei_rna.h5ad"

    cd = load_seqfish_multiomics_linked(
        dna_path,
        locus_annotation=locus_path,
        cell_clustering=clustering_path,
        transcriptomic_data=rna_path,
        cd_path=cd_path,
        h5ad_path=h5ad_path,
        transcriptome_chunksize=2,
    )
    adata = cd.linked_adata

    assert cd_path.exists()
    assert h5ad_path.exists()
    assert adata is not None
    assert list(cd.cells.index) == list(adata.obs_names) == ["1_0_1", "1_0_2"]
    np.testing.assert_allclose(cd.cellm["umap"], [[5.0, 7.0], [6.0, 8.0]])
    assert "n_transcripts" in cd.cells.columns
    assert adata.shape == (2, 3)

    cd2 = ChromData.read(cd_path)
    adata2 = cd2.linked_adata
    assert adata2 is not None
    assert list(cd2.cells.index) == list(adata2.obs_names)
