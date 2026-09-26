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

    path = tmp_path / "annotation_features.h5cd"
    cdata.write(path)
    out = ChromData.read(path)

    assert "gtf.nearest_tss_distance" in out.tracks_spot_view()
    assert "bin_features" in out.results
    assert out.uns["feature_registry"][0]["created_by"] == "uchrom.fea.annotation"
