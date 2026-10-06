"""FOF-CT ``##columns=`` parsing and the seqFISH+ loader's trace table."""
import numpy as np
import pandas as pd
import pytest

from uchrom import ChromData


def test_fofct_last_column_keeps_closing_parenthesis(tmp_path):
    path = tmp_path / "core.csv"
    path.write_text(
        "##FOF-CT_version=v0.1\n"
        "##columns=(Spot_ID,Trace_ID,X,Y,Z,Chrom,Chrom_Start,Chrom_End,n_per_dist(um))\n"
        "1,t1,0.1,0.2,0.3,chr1,0,100,1.5\n"
        "2,t1,0.4,0.5,0.6,chr1,100,200,2.5\n"
    )
    cd = ChromData.from_fofct(path)
    assert "n_per_dist(um)" in cd.spots.columns
    assert "n_per_dist(um" not in cd.spots.columns
    assert cd.spots["n_per_dist(um)"].tolist() == [1.5, 2.5]


def _takei_like(tmp_path):
    # one cell, one chromosome: dbscan_ldp_nbr_allele merges two homologs into
    # allele 0 (loci chr19-1 / chr19-2 each seen twice); dbscan_ldp_allele
    # keeps them apart (0 / 1)
    dna = pd.DataFrame({
        "rep": [1] * 5, "fov": [0] * 5, "cellID": [1] * 5,
        "name": ["chr19-1", "chr19-2", "chr19-1", "chr19-2", "chr19-3"],
        "chrom": ["chr19"] * 5,
        "dbscan_allele": [0, 0, 1, 1, -1],
        "dbscan_ldp_allele": [0, 0, 1, 1, 1],
        "dbscan_ldp_nbr_allele": [0, 0, 0, 0, 0],
        "x_um": [0.1, 0.2, 5.1, 5.2, 5.3], "y_um": [0.0] * 5, "z_um": [0.0] * 5,
        "SOX2": [1.0, 2.0, 3.0, 4.0, 5.0],
        "dot_int": [10, 11, 12, 13, 14], "n_rad_score": [0.1] * 5,
        "n_per_dist(um)": [1.0, 1.1, 1.2, 1.3, 1.4],
    })
    dna.to_csv(tmp_path / "cerebellum_rep1_pos0.csv", index=False)
    pd.DataFrame({
        "name": ["chr19-1", "chr19-2", "chr19-3", "chr19-4"], "chrom": ["chr19"] * 4,
        "start": [0, 25_000, 50_000, 75_000], "end": [25_000, 50_000, 75_000, 100_000],
    }).to_csv(tmp_path / "locus.csv", index=False)
    return tmp_path / "cerebellum_rep1_pos0.csv", tmp_path / "locus.csv"


def test_seqfish_trace_table_reports_merged_homologs(tmp_path):
    from uchrom.io import read_seqfish_multiomics

    spots, locus = _takei_like(tmp_path)
    with pytest.warns(UserWarning):          # the toy CSV lacks most z-score columns
        cd = read_seqfish_multiomics(str(spots), locus_annotation=locus)
    tr = cd.traces
    assert list(tr.index) == ["1_0_1_chr19_a0"]
    row = tr.iloc[0]
    assert row["allele"] == 0 and row["n_spots"] == 5 and row["n_loci"] == 3
    assert row["n_duplicate_loci"] == 2                     # homologs merged
    assert row["dbscan_ldp_allele_majority"] == 1          # 3 of 5 spots
    assert row["dbscan_ldp_allele_agreement"] == pytest.approx(0.6)
    assert "dbscan_ldp_nbr_allele_majority" not in tr.columns
    # the probe panel is the bin table (with names); per-spot z-scores are spot tracks
    assert cd.n_bins == 4 and cd.bins["name"].tolist() == ["chr19-1", "chr19-2", "chr19-3", "chr19-4"]
    assert "SOX2" in cd.spot_tracks.columns

    with pytest.warns(UserWarning):
        cd2 = read_seqfish_multiomics(str(spots), locus_annotation=locus,
                                      allele_col="dbscan_ldp_allele")
    assert cd2.traces["n_duplicate_loci"].tolist() == [0, 0]
    assert cd2.traces["allele"].tolist() == [0, 1]
    np.testing.assert_allclose(cd2.traces["dbscan_ldp_nbr_allele_agreement"], [1.0, 1.0])


def test_seqfish_streaming_import_equals_in_memory(tmp_path):
    """out= streams FOV by FOV; the store equals the in-memory result."""
    import warnings

    from uchrom.io import read_seqfish_multiomics

    rng = np.random.default_rng(3)
    names = [f"chr{c}-{i}" for c in (7, 19) for i in range(1, 7)]
    pd.DataFrame({"name": names, "chrom": [n.split("-")[0] for n in names],
                  "start": [(int(n.split("-")[1]) - 1) * 25_000 for n in names],
                  "end": [int(n.split("-")[1]) * 25_000 for n in names]}).to_csv(tmp_path / "locus.csv",
                                                                                   index=False)
    for fov in range(3):
        rows = []
        for cell in rng.permutation(4) + 1:
            for nm in rng.permutation(names):
                rows.append({"rep": 1, "fov": fov, "cellID": int(cell), "name": nm,
                             "chrom": nm.split("-")[0], "dbscan_allele": 0, "dbscan_ldp_allele": 0,
                             "dbscan_ldp_nbr_allele": int(rng.integers(-1, 2)),
                             "x_um": rng.normal(), "y_um": rng.normal(), "z_um": rng.normal(),
                             "SOX2": rng.normal(), "dot_int": int(rng.integers(0, 100)),
                             "n_rad_score": rng.random(), "n_per_dist(um)": rng.random()})
        pd.DataFrame(rows).to_csv(tmp_path / f"cerebellum_rep1_pos{fov}.csv", index=False)
    pd.DataFrame({"rep": 1, "fov": [0, 1, 2, 2], "cellID": [1, 2, 3, 9], "leiden": [0, 2, 4, 6],
                  "umap_1": [0.1, 0.2, 0.3, 0.4], "umap_2": [1.0, 2.0, 3.0, 4.0], "x": 1.0, "y": 2.0,
                  "z": 3.0, "nuc_volume(um3)": 100.0, "doublet": 0, "batch": 1}).to_csv(
        tmp_path / "clusters.csv", index=False)
    glob = str(tmp_path / "cerebellum_rep1_pos*.csv")
    kw = dict(locus_annotation=tmp_path / "locus.csv", cell_clustering=tmp_path / "clusters.csv")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        mem = read_seqfish_multiomics(glob, **kw)
        bk = read_seqfish_multiomics(glob, out=tmp_path / "st.chromdata.zarr", memory_budget="4KB", **kw)
    mem.write(tmp_path / "mem.chromdata.zarr")
    a = ChromData.read(tmp_path / "mem.chromdata.zarr")
    b = bk.to_memory()
    assert bk.backed and b.n_spots == a.n_spots
    pd.testing.assert_frame_equal(a.to_dataframe(include_bin_id=True), b.to_dataframe(include_bin_id=True))
    pd.testing.assert_frame_equal(a.spot_tracks, b.spot_tracks)
    for key in ("bins", "cells", "traces"):
        pd.testing.assert_frame_equal(getattr(a, key), getattr(b, key))
    np.testing.assert_array_equal(a.cellm["umap"], b.cellm["umap"])
    assert a.uns == b.uns
