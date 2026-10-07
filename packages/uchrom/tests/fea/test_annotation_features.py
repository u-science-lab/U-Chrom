import numpy as np
import pandas as pd


def _write_gtf(path):
    path.write_text(
        'chr1\ttest\tgene\t3\t12\t.\t+\t.\tgene_id "g1"; gene_name "A"; gene_biotype "pc";\n'
        'chr1\ttest\texon\t3\t5\t.\t+\t.\tgene_id "g1"; gene_name "A";\n'
        'chr1\ttest\tgene\t21\t30\t.\t-\t.\tgene_id "g2"; gene_name "B"; gene_biotype "pc";\n'
        'chr1\ttest\texon\t25\t30\t.\t-\t.\tgene_id "g2"; gene_name "B";\n'
    )


def _make_cd():
    from uchrom import ChromData

    coords = np.zeros((4, 3), dtype=float)
    spots = pd.DataFrame({
        "chrom": ["chr1", "chr1", "chr1", "chr2"],
        "start": [0, 12, 28, 0],
        "end": [10, 20, 32, 10],
        "trace_id": ["t1", "t1", "t1", "t2"],
    })
    return ChromData(coords, spots, uns={"genome_assembly": "toy"})


def test_read_gtf_normalizes_coordinates_and_attributes(tmp_path):
    from uchrom.fea.annotation import read_gtf

    gtf = tmp_path / "genes.gtf"
    _write_gtf(gtf)

    out = read_gtf(gtf)

    assert list(out["feature"]) == ["gene", "exon", "gene", "exon"]
    assert out.loc[0, "start"] == 2
    assert out.loc[0, "end"] == 12
    assert out.loc[0, "gene_id"] == "g1"
    assert out.loc[0, "gene_name"] == "A"
    assert out.loc[0, "gene_biotype"] == "pc"


def test_compute_annotation_features_from_gtf(tmp_path):
    from uchrom.fea.annotation import compute_annotation_features

    gtf = tmp_path / "genes.gtf"
    _write_gtf(gtf)
    intervals = pd.DataFrame({
        "chrom": ["chr1", "chr1", "chr1", "chr2"],
        "start": [0, 12, 28, 0],
        "end": [10, 20, 32, 10],
    })

    out = compute_annotation_features(intervals, gtf, promoter_window=(-2, 2))

    assert out.loc[0, "gene_body_overlap_bp"] == 8
    assert out.loc[0, "gene_body_overlap_fraction"] == 0.8
    assert out.loc[0, "gene_count"] == 1
    assert out.loc[0, "exon_overlap_bp"] == 3
    assert out.loc[0, "promoter_overlap_bp"] == 4
    assert out.loc[0, "nearest_tss_distance"] == 0

    assert out.loc[1, "gene_body_overlap_bp"] == 0
    assert out.loc[1, "nearest_tss_distance"] == 10

    assert out.loc[2, "gene_body_overlap_bp"] == 2
    assert out.loc[2, "promoter_overlap_bp"] == 4
    assert out.loc[2, "nearest_tss_distance"] == 0

    assert out.loc[3, "gene_body_overlap_bp"] == 0
    assert np.isnan(out.loc[3, "nearest_tss_distance"])


def test_add_annotation_features_updates_tracks_results_and_registry(tmp_path):
    from uchrom import ChromData
    from uchrom.fea.annotation import add_annotation_features

    gtf = tmp_path / "genes.gtf"
    _write_gtf(gtf)
    cdata = _make_cd()

    table = add_annotation_features(
        cdata,
        gtf,
        features=["gene_body_overlap_fraction", "nearest_tss_distance"],
        promoter_window=(-2, 2),
    )

    assert len(table) == 4
    assert "bin_features" in cdata.results
    assert "gtf.gene_body_overlap_fraction" in cdata.tracks_spot_view()
    assert "gtf.nearest_tss_distance" in cdata.tracks_spot_view()
    assert cdata.tracks_spot_view().loc[0, "gtf.gene_body_overlap_fraction"] == 0.8
    assert cdata.uns["feature_registry"][0]["feature_group"] == "annotation"
    assert cdata.uns["feature_registry"][0]["genome_assembly"] == "toy"

    path = tmp_path / "annotation_features.chromdata.zarr"
    cdata.write(path)
    out = ChromData.read(path)

    assert "gtf.nearest_tss_distance" in out.tracks_spot_view()
    assert "bin_features" in out.results
    assert out.uns["feature_registry"][0]["created_by"] == "uchrom.fea.annotation"


def _write_refgene_like(path):
    """Transcripts and exons but no gene rows (as UCSC refGene): g1 has two overlapping transcripts and a
    second copy further on; g2 one transcript on the minus strand."""
    path.write_text(
        'chr1\tr\ttranscript\t3\t10\t.\t+\t.\tgene_id "g1"; transcript_id "t1";\n'
        'chr1\tr\texon\t3\t5\t.\t+\t.\tgene_id "g1"; transcript_id "t1";\n'
        'chr1\tr\ttranscript\t6\t12\t.\t+\t.\tgene_id "g1"; transcript_id "t2";\n'
        'chr1\tr\ttranscript\t21\t30\t.\t-\t.\tgene_id "g2"; transcript_id "t3";\n'
        'chr1\tr\texon\t25\t30\t.\t-\t.\tgene_id "g2"; transcript_id "t3";\n'
        'chr1\tr\ttranscript\t41\t45\t.\t+\t.\tgene_id "g1"; transcript_id "t4";\n'
    )


def test_read_gtf_derives_gene_bodies_from_transcripts(tmp_path):
    from uchrom.fea.annotation import gene_bodies, read_gtf

    gtf = tmp_path / "refgene.gtf"
    _write_refgene_like(gtf)
    table = read_gtf(gtf)
    genes = table[table["feature"] == "gene"].reset_index(drop=True)
    assert list(zip(genes["gene_id"], genes["start"], genes["end"], genes["strand"])) == [
        ("g1", 2, 12, "+"), ("g1", 40, 45, "+"), ("g2", 20, 30, "-")]
    assert set(genes["source"]) == {"r:derived"}
    assert len(table) == 6 + 3 and list(table.columns) == list(read_gtf(gtf, derive_genes=False).columns)
    assert not (read_gtf(gtf, derive_genes=False)["feature"] == "gene").any()
    pd.testing.assert_frame_equal(gene_bodies(read_gtf(gtf, derive_genes=False)), genes)
    # a GTF with gene rows is left alone
    plain = tmp_path / "genes.gtf"
    _write_gtf(plain)
    assert list(read_gtf(plain)["feature"]) == ["gene", "exon", "gene", "exon"]


def test_annotation_features_from_a_gtf_without_gene_rows(tmp_path):
    from uchrom.fea.annotation import compute_annotation_features, read_gtf

    gtf = tmp_path / "refgene.gtf"
    _write_refgene_like(gtf)
    intervals = pd.DataFrame({"chrom": ["chr1", "chr1", "chr1"], "start": [0, 12, 38], "end": [10, 20, 48]})
    from_path = compute_annotation_features(intervals, gtf, promoter_window=(-2, 2))
    no_genes = read_gtf(gtf, derive_genes=False)                 # a table without gene rows: derived too
    pd.testing.assert_frame_equal(compute_annotation_features(intervals, no_genes, promoter_window=(-2, 2)),
                                  from_path)
    assert from_path.loc[0, "gene_body_overlap_bp"] == 8 and from_path.loc[0, "gene_count"] == 1
    assert from_path.loc[2, "gene_body_overlap_bp"] == 5 and from_path.loc[2, "nearest_tss_distance"] == 0
    assert from_path.loc[1, "nearest_tss_distance"] == 10        # the minus-strand TSS at 30
