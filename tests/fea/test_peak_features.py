import numpy as np
import pandas as pd


def _make_cd():
    from uchrom import ChromData

    coords = np.zeros((6, 3), dtype=float)
    spots = pd.DataFrame({
        "chrom": ["chr1", "chr1", "chr1", "chr1", "chr1", "chr1"],
        "start": [0, 0, 10, 20, 30, 40],
        "end": [10, 10, 20, 30, 40, 50],
        "trace_id": ["t1", "t2", "t1", "t1", "t1", "t1"],
    })
    tracks = pd.DataFrame({
        "signal.track": [1.0, 3.0, 2.0, 10.0, 11.0, 1.0],
    })
    return ChromData(coords, spots, tracks=tracks, uns={"genome_assembly": "toy"})


def test_call_peaks_from_track_projects_peak_features():
    from uchrom.fea.peaks import call_peaks_from_track

    cdata = _make_cd()

    peaks = call_peaks_from_track(
        cdata,
        "signal.track",
        threshold=9.0,
    )

    assert len(peaks) == 1
    assert peaks.loc[0, "chrom"] == "chr1"
    assert peaks.loc[0, "start"] == 20
    assert peaks.loc[0, "end"] == 40
    assert peaks.loc[0, "n_bins"] == 2
    assert "peaks:signal_track" in cdata.results
    assert "peak.signal_track_overlap" in cdata.tracks
    assert "peak.distance_to_signal_track" in cdata.tracks
    assert list(cdata.tracks["peak.signal_track_overlap"]) == [0.0, 0.0, 0.0, 1.0, 1.0, 0.0]
    assert list(cdata.tracks["peak.distance_to_signal_track"]) == [10.0, 10.0, 0.0, 0.0, 0.0, 0.0]
    assert cdata.uns["feature_registry"][0]["feature_group"] == "peaks"


def test_compute_peak_features_handles_no_peaks():
    from uchrom.fea.peaks import compute_peak_features

    intervals = pd.DataFrame({
        "chrom": ["chr1"],
        "start": [0],
        "end": [10],
    })
    out = compute_peak_features(intervals, pd.DataFrame(), name="empty")

    assert out.loc[0, "empty_overlap"] == 0.0
    assert out.loc[0, "empty_count"] == 0.0
    assert np.isnan(out.loc[0, "distance_to_empty"])
