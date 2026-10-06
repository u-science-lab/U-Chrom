import numpy as np
import pandas as pd


def _make_cd():
    from uchrom import ChromData

    coords = np.zeros((4, 3), dtype=float)
    spots = pd.DataFrame({
        "chrom": ["chr1", "chr1", "chr1", "chr1"],
        "start": [0, 10, 20, 30],
        "end": [10, 20, 30, 40],
        "trace_id": ["t1", "t1", "t1", "t1"],
    })
    return ChromData(coords, spots, uns={"genome_assembly": "toy"})


def test_compute_structural_features_from_result_tables():
    from uchrom.strc import compute_structural_features

    intervals = pd.DataFrame({
        "chrom": ["chr1", "chr1", "chr1", "chr1"],
        "start": [0, 10, 20, 30],
        "end": [10, 20, 30, 40],
    })
    tads = pd.DataFrame({
        "chrom": ["chr1", "chr1"],
        "start": [0, 20],
        "end": [20, 40],
    })
    loops = pd.DataFrame({
        "chrom1": ["chr1"],
        "start1": [10],
        "end1": [20],
        "chrom2": ["chr1"],
        "start2": [30],
        "end2": [40],
    })
    compartments = pd.DataFrame({
        "chrom": ["chr1", "chr1"],
        "start": [0, 20],
        "end": [20, 40],
        "compartment": ["A", "B"],
        "pc2": [0.5, -0.25],
    })

    out = compute_structural_features(
        intervals,
        tads=tads,
        loops=loops,
        compartments=compartments,
    )

    assert list(out["distance_to_tad_boundary"]) == [5.0, 5.0, 5.0, 5.0]
    assert list(out["inside_tad"]) == [1.0, 1.0, 1.0, 1.0]
    assert list(out["loop_anchor_overlap"]) == [0.0, 1.0, 0.0, 1.0]
    assert list(out["loop_anchor_count"]) == [0.0, 1.0, 0.0, 1.0]
    assert list(out["distance_to_loop_anchor"]) == [10.0, 0.0, 10.0, 0.0]
    assert list(out["compartment_label"]) == ["A", "A", "B", "B"]
    assert list(out["compartment_pc2"]) == [0.5, 0.5, -0.25, -0.25]


def test_add_structural_features_updates_tracks_results_and_registry():
    from uchrom.strc import add_structural_features

    cdata = _make_cd()
    cdata.results["tads"] = pd.DataFrame({
        "chrom": ["chr1"],
        "start": [0],
        "end": [40],
    })
    cdata.results["loops"] = pd.DataFrame({
        "chrom1": ["chr1"],
        "start1": [10],
        "end1": [20],
        "chrom2": ["chr1"],
        "start2": [30],
        "end2": [40],
    })

    table = add_structural_features(cdata)

    assert "strc.distance_to_tad_boundary" in cdata.tracks_spot_view()
    assert "strc.loop_anchor_overlap" in cdata.tracks_spot_view()
    assert "bin_features" in cdata.results
    assert cdata.tracks_spot_view().loc[1, "strc.loop_anchor_overlap"] == 1.0
    assert "strc.loop_anchor_overlap" in cdata.bin_tracks.columns
    assert cdata.uns["feature_registry"][0]["feature_group"] == "structure"
    assert cdata.uns["feature_registry"][0]["source_results"] == ["tads", "loops"]
    assert "distance_to_tad_boundary" in table


def test_add_structural_features_projects_empty_result_tables():
    from uchrom.strc import add_structural_features

    cdata = _make_cd()
    cdata.results["loops"] = pd.DataFrame(
        columns=["chrom1", "start1", "end1", "chrom2", "start2", "end2"]
    )

    table = add_structural_features(cdata)

    assert "loop_anchor_overlap" in table
    assert list(table["loop_anchor_overlap"]) == [0.0, 0.0, 0.0, 0.0]
    assert "strc.loop_anchor_overlap" in cdata.tracks_spot_view()
    assert cdata.uns["feature_registry"][0]["source_results"] == ["loops"]
