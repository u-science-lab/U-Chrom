"""Su et al. 2020 tracing / binned Hi-C readers and the locus ``.cool`` writer (offline, miniature files in
the layouts of Zenodo 3928890; the real files are checked in tests/test_load_tracing.py)."""

import numpy as np
import pandas as pd
import pytest

from uchrom.io import read_su2020_hic, read_su2020_tracing, write_locus_cool

CHR_HEADER = ("Z(nm)\tX(nm)\tY(nm)\tGenomic coordinate\tChromosome copy number\tGene names\tTranscription\t"
              "TSS ZXY(nm)\tCell cycle state\n")
CHR_LOCI = ["chr21:10400001-10450001", "chr21:10500001-10550001", "chr21:13250001-13300001"]

GEN_HEADER = ("z(nm)\ty(nm)\tx(nm)\tgenomic coordinate\thomolog number\tcell number\texperiment number\t"
              "gene names\ttransciption\tdistance to lamina (nm)\tdistance to nucleoli (nm)\n")
GEN_LOCI = ["chr1:2950000-3050000", "chr1:5950000-6050000", "chr2:1000-101000"]


def _chromosome_scale(path):
    rows = []
    for copy, phase in ((1, "G1"), (2, "G2/S"), (3, "G1")):
        for k, locus in enumerate(CHR_LOCI):
            z, x, y = 100 * copy + k, 200 + k, 300 + k
            if (copy == 2 and k == 1) or (k == 2):                  # locus 3 never detected
                z = x = y = "nan"
            genes, tx, tss = {0: ("", "", ""), 1: ("GENE1;GENE2;", "on;off;", "[1 2 3];[4 5 6];"),
                              2: ("GENE3;", "off;", "[nan nan nan];")}[k]
            rows.append(f"{z}\t{x}\t{y}\t{locus}\t{copy}\t{genes}\t{tx}\t{tss}\t{phase}\n")
    path.write_text(CHR_HEADER + "".join(rows))
    return path


def _genome_scale(path):
    rows = []
    for cell, exp in ((7, 1), (9, 2)):
        for hom in (1, 2):
            for k, locus in enumerate(GEN_LOCI):
                z, y, x = 1000 * hom + k, 2000 * cell, 3000 + k
                if cell == 9 and hom == 2 and k == 0:
                    z = y = x = "nan"
                genes, tx = ("ENSG1,ENSG2", "off,on") if k == 1 else ("", "")
                rows.append(f"{z}\t{y}\t{x}\t{locus}\t{hom}\t{cell}\t{exp}\t{genes}\t{tx}\t{500 + k}\t{1500 + k}\n")
    path.write_text(GEN_HEADER + "".join(rows))
    return path


def test_chromosome_scale_table(tmp_path):
    cd = read_su2020_tracing(_chromosome_scale(tmp_path / "chromosome21.tsv"))
    assert (cd.n_spots, cd.n_traces, cd.n_bins) == (5, 3, 3)       # the never-detected locus is still a bin
    assert cd.bins["start"].tolist() == [10_400_000, 10_500_000, 13_250_000]
    assert cd.bins["end"].tolist() == [10_450_000, 10_550_000, 13_300_000]
    assert sorted(cd.spots["trace_id"].unique().tolist()) == [1, 2, 3]
    assert "cell_id" not in cd.spots.columns
    first = cd.get_trace(1).to_dataframe().sort_values("start")
    assert np.allclose(first[["x", "y", "z"]].to_numpy(), [[0.2, 0.3, 0.1], [0.201, 0.301, 0.101]])
    assert cd.uns["xyz_unit"] == "micron" and cd.uns["genome_assembly"] == "hg38"
    assert cd.bin_tracks["genes"].tolist() == ["", "GENE1;GENE2", "GENE3"]
    assert cd.bin_tracks["n_genes"].tolist() == [0, 2, 1]
    tx = cd.spot_tracks["transcription"].to_numpy()
    assert sorted(tx.tolist()) == ["", "", "", "on;off", "on;off"]
    assert cd.traces.loc[2, "cell_cycle"] == "G2/S"


def test_chromosome_scale_options(tmp_path):
    path = _chromosome_scale(tmp_path / "chromosome21.tsv")
    cd = read_su2020_tracing(path, keep_missing=True, unit="nm", extras=["n_genes"])
    assert cd.n_spots == 9 and int(np.isnan(cd.coords[:, 0]).sum()) == 4
    assert cd.uns["xyz_unit"] == "nm" and np.nanmax(cd.coords) == 301
    assert list(cd.bin_tracks.columns) == ["n_genes"] and cd.spot_tracks.shape[1] == 0 and len(cd.traces) == 0
    bare = read_su2020_tracing(path, extras=False)
    assert bare.bin_tracks.shape[1] == 0
    shifted = read_su2020_tracing(path, label_offset=0, extras=False)
    assert shifted.bins["start"].iat[0] == 10_400_001
    with pytest.raises(ValueError, match="unknown"):
        read_su2020_tracing(path, extras=["lamina"])
    with pytest.raises(ValueError, match="not in this file"):
        read_su2020_tracing(path, extras=["distance_to_lamina"])
    with pytest.raises(ValueError, match="unit"):
        read_su2020_tracing(path, unit="mm")
    (tmp_path / "other.tsv").write_text("a\tb\n1\t2\n")
    with pytest.raises(ValueError, match="not a Su 2020 tracing table"):
        read_su2020_tracing(tmp_path / "other.tsv")


def test_genome_scale_table(tmp_path):
    cd = read_su2020_tracing(_genome_scale(tmp_path / "genomic-scale.tsv"))
    assert cd.n_bins == 3 and cd.n_spots == 11 and cd.n_cells == 2
    assert cd.bins[["chrom", "start", "end"]].astype({"chrom": str}).values.tolist() == [
        ["chr1", 2_950_000, 3_050_000], ["chr1", 5_950_000, 6_050_000], ["chr2", 1000, 101_000]]
    # one trace per (cell, chromosome, homolog)
    assert cd.n_traces == 8
    assert cd.traces.loc["9_chr1_h2"].to_dict() == {"cell_id": 9, "chrom": "chr1", "homolog": 2}
    assert cd.cells["experiment"].to_dict() == {7: 1, 9: 2}
    t = cd.get_trace("7_chr1_h2").to_dataframe().sort_values("start")
    assert np.allclose(t[["x", "y", "z"]].to_numpy(), [[3.0, 14.0, 2.0], [3.001, 14.0, 2.001]])
    assert cd.get_trace("9_chr1_h2").n_spots == 1                   # its first locus was not detected
    assert cd.bin_tracks["genes"].tolist() == ["", "ENSG1;ENSG2", ""]
    s = cd.spots_with_loci().join(cd.spot_tracks)
    assert set(s.loc[s["start"] == 5_950_000, "transcription"]) == {"off;on"}
    assert np.allclose(s.loc[s["start"] == 1000, "distance_to_lamina"], 0.502)
    assert np.allclose(s.loc[s["start"] == 1000, "distance_to_nucleoli"], 1.502)


def test_tables_round_trip_through_a_store(tmp_path):
    from chromdata import ChromData

    cd = read_su2020_tracing(_chromosome_scale(tmp_path / "chromosome21.tsv"))
    cd.write(tmp_path / "x.chromdata.zarr")
    back = ChromData.read(tmp_path / "x.chromdata.zarr", original_order=True)
    assert back.bin_tracks["genes"].tolist() == ["", "GENE1;GENE2", "GENE3"]
    assert back.spot_tracks["transcription"].tolist() == cd.spot_tracks["transcription"].tolist()
    assert back.traces["cell_cycle"].to_dict() == cd.traces["cell_cycle"].to_dict()


def test_hic_table(tmp_path):
    counts = np.array([[10, 4, 1], [4, 12, 3], [1, 3, 9]])
    pd.DataFrame(counts, index=CHR_LOCI, columns=CHR_LOCI).to_csv(tmp_path / "chr.tsv", sep="\t")
    loci, m = read_su2020_hic(tmp_path / "chr.tsv")
    assert loci["start"].tolist() == [10_400_000, 10_500_000, 13_250_000] and np.array_equal(m, counts)
    assert m.dtype == np.float64
    pd.DataFrame(counts, index=GEN_LOCI, columns=GEN_LOCI).to_csv(tmp_path / "gen.tsv", sep="\t")
    loci, _ = read_su2020_hic(tmp_path / "gen.tsv")                 # mixed parity: labels as given
    assert loci["start"].tolist() == [2_950_000, 5_950_000, 1000]
    assert read_su2020_hic(tmp_path / "chr.tsv", label_offset=0)[0]["start"].iat[0] == 10_400_001
    pd.DataFrame(counts, index=CHR_LOCI, columns=GEN_LOCI).to_csv(tmp_path / "bad.tsv", sep="\t")
    with pytest.raises(ValueError, match="row and column labels differ"):
        read_su2020_hic(tmp_path / "bad.tsv")


def test_write_locus_cool(tmp_path):
    import cooler

    loci = pd.DataFrame({"chrom": ["chr2", "chr1", "chr1", "chr2"], "start": [0, 500, 100, 300],
                         "end": [50, 550, 150, 350]})                  # unsorted; chr2 starts at 0
    counts = np.array([[5, 0, 0, 2], [0, 7, 3, 0], [0, 3, 4, 0], [2, 0, 0, 6]])
    path = write_locus_cool(loci, counts, tmp_path / "m.cool", assembly="toy")
    clr = cooler.Cooler(path)
    bins = clr.bins()[:]
    # chromosomes in order of first appearance; chr2 needs no leading bin
    assert bins[["chrom", "start", "end"]].astype({"chrom": str}).values.tolist() == [
        ["chr2", 0, 300], ["chr2", 300, 350], ["chr1", 0, 100], ["chr1", 100, 500], ["chr1", 500, 550]]
    assert "weight" in bins.columns and clr.info["genome-assembly"] == "toy"
    assert clr.pixels()[:]["count"].dtype.kind == "i"
    m = clr.matrix(balance=False)[:]
    assert np.array_equal(m[np.ix_([3, 4], [3, 4])], [[4, 3], [3, 7]])
    assert np.array_equal(m[np.ix_([0, 1], [0, 1])], [[5, 2], [2, 6]]) and m[2].sum() == 0
    # fetching a region returns the loci that start in it
    assert clr.bins().fetch("chr1:100-501")["start"].tolist() == [100, 500]
    assert not list((tmp_path).glob(".*tmp"))

    tuned = cooler.Cooler(write_locus_cool(loci, counts, tmp_path / "d.cool", balance={"ignore_diags": 0, "min_nnz": 0}))
    w = tuned.bins()[:]["weight"].to_numpy()
    assert np.isfinite(w[[0, 1, 3, 4]]).all() and np.isnan(w[2])      # the empty leading bin is masked

    frac = write_locus_cool(loci, counts / 2.0, tmp_path / "f.cool", balance=False)
    f = cooler.Cooler(frac)
    assert f.pixels()[:]["count"].dtype.kind == "f" and "weight" not in f.bins().columns
    assert np.isclose(f.matrix(balance=False)[:][0, 1], 1.0)


@pytest.mark.slow
def test_genome_scale_real_file():
    from tests import DATA_DIR

    path = DATA_DIR / "su2020_imr90" / "genomic-scale.tsv"
    if not path.exists():
        pytest.skip("Su 2020 genome-scale table not in the data directory (python -m uchrom.datasets fetch "
                    "su2020_genome)")
    cd = read_su2020_tracing(path)
    assert (cd.n_cells, cd.n_bins, cd.n_traces) == (1_787, 1_041, 1_787 * 23 * 2)
    assert cd.cells["experiment"].value_counts().sort_index().tolist() == [431, 917, 439]
    assert cd.n_spots == 3_116_441                                    # 16 % of 3,720,534 positions missing
    assert set(cd.bins.eval("end - start")) == {100_000}
    loci, counts = read_su2020_hic(path.with_name("Hi-C_contacts_genome-scale.tsv"))
    assert counts.shape == (1_041, 1_041) and loci["start"].iat[0] == 2_950_000


def test_write_locus_cool_checks(tmp_path):
    loci = pd.DataFrame({"chrom": ["chr1", "chr1"], "start": [100, 200], "end": [150, 250]})
    with pytest.raises(ValueError, match="symmetric"):
        write_locus_cool(loci, [[1, 2], [3, 1]], tmp_path / "a.cool")
    with pytest.raises(ValueError, match="2 loci"):
        write_locus_cool(loci, np.ones((3, 3)), tmp_path / "a.cool")
    with pytest.raises(ValueError, match="non-negative"):
        write_locus_cool(loci, [[1, -1], [-1, 1]], tmp_path / "a.cool")
    with pytest.raises(ValueError, match="different starts"):
        write_locus_cool(loci.assign(start=[100, 100]), np.ones((2, 2)), tmp_path / "a.cool")
