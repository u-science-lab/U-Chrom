import numpy as np
import pandas as pd
import pytest


def _write_fasta(path):
    path.write_text(
        ">chr1 some header text\n"
        "ACGTNNGGGAAAGGGCCCGGGTTTGGG\n"
        ">chr2\n"
        "CCCCAAAAGGGG\n"
    )


def _make_cd():
    from uchrom import ChromData

    coords = np.zeros((5, 3), dtype=float)
    spots = pd.DataFrame({
        "chrom": ["chr1", "chr1", "chr1", "chr1", "chr2"],
        "start": [0, 0, 4, 6, 0],
        "end": [4, 4, 10, 27, 4],
        "trace_id": ["t1", "t2", "t1", "t1", "t3"],
    })
    tracks = pd.DataFrame({"existing": [1, 2, 3, 4, 5]})
    return ChromData(
        coords,
        spots,
        tracks=tracks,
        uns={"genome_assembly": "toy"},
    )


def test_compute_sequence_features_from_fasta(tmp_path):
    from uchrom.fea.sequence import compute_sequence_features

    fasta = tmp_path / "genome.fa"
    _write_fasta(fasta)
    intervals = pd.DataFrame({
        "chrom": ["chr1", "chr1", "chr1", "chr2"],
        "start": [0, 4, 6, 0],
        "end": [4, 10, 27, 4],
    })

    out = compute_sequence_features(intervals, fasta)

    assert list(out.columns) == [
        "chrom",
        "start",
        "end",
        "gc_fraction",
        "cpg_density",
        "n_fraction",
        "g4_motif_count",
        "g4_motif_density",
    ]
    assert out.loc[0, "gc_fraction"] == 0.5
    assert out.loc[0, "cpg_density"] == 0.25
    assert out.loc[0, "n_fraction"] == 0.0
    assert out.loc[1, "gc_fraction"] == 0.75
    assert out.loc[1, "n_fraction"] == pytest.approx(2 / 6)
    assert out.loc[2, "g4_motif_count"] == 1.0
    assert out.loc[2, "g4_motif_density"] == pytest.approx(1 / 21)
    assert out.loc[3, "gc_fraction"] == 1.0


def test_project_interval_features_to_duplicate_spots():
    from uchrom.fea.project import project_interval_features_to_spots

    cdata = _make_cd()
    features = pd.DataFrame({
        "chrom": ["chr1", "chr1", "chr2"],
        "start": [0, 4, 0],
        "end": [4, 10, 4],
        "gc_fraction": [0.5, 0.75, 1.0],
    })

    tracks = project_interval_features_to_spots(
        cdata,
        features,
        prefix="seq",
        into=cdata.tracks,
    )

    assert list(tracks["existing"]) == [1, 2, 3, 4, 5]
    assert list(tracks["seq.gc_fraction"][:3]) == [0.5, 0.5, 0.75]
    assert np.isnan(tracks.loc[3, "seq.gc_fraction"])
    assert tracks.loc[4, "seq.gc_fraction"] == 1.0


def test_project_interval_features_rejects_duplicate_feature_rows():
    from uchrom.fea.project import project_interval_features_to_spots

    cdata = _make_cd()
    features = pd.DataFrame({
        "chrom": ["chr1", "chr1"],
        "start": [0, 0],
        "end": [4, 4],
        "gc_fraction": [0.5, 0.6],
    })

    with pytest.raises(ValueError, match="duplicate intervals"):
        project_interval_features_to_spots(cdata, features)


def test_add_sequence_features_updates_tracks_results_and_registry(tmp_path):
    from uchrom import ChromData
    from uchrom.fea.sequence import add_sequence_features

    fasta = tmp_path / "genome.fa"
    _write_fasta(fasta)
    cdata = _make_cd()

    table = add_sequence_features(
        cdata,
        fasta,
        features=["gc_fraction", "g4_motif_count"],
    )

    assert len(table) == 4
    assert "bin_features" in cdata.results
    assert list(cdata.results["bin_features"].columns) == [
        "chrom",
        "start",
        "end",
        "gc_fraction",
        "g4_motif_count",
    ]
    assert "seq.gc_fraction" in cdata.tracks
    assert "seq.g4_motif_count" in cdata.tracks
    assert cdata.tracks.loc[0, "seq.gc_fraction"] == 0.5
    assert cdata.tracks.loc[1, "seq.gc_fraction"] == 0.5
    assert cdata.uns["feature_registry"][0]["feature_group"] == "sequence"
    assert cdata.uns["feature_registry"][0]["genome_assembly"] == "toy"

    path = tmp_path / "sequence_features.h5cd"
    cdata.write(path)
    out = ChromData.read(path)

    assert "seq.gc_fraction" in out.tracks
    assert "bin_features" in out.results
    assert out.uns["feature_registry"][0]["created_by"] == "uchrom.fea.sequence"
