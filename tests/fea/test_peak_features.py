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
        method="threshold",
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


def test_macs_style_peak_calling_reports_significance():
    from uchrom.fea.peaks import call_macs_peaks_from_signal

    signal = pd.DataFrame({
        "chrom": ["chr1"] * 12,
        "start": [i * 10 for i in range(12)],
        "end": [(i + 1) * 10 for i in range(12)],
        "signal": [1, 1, 1, 1, 1, 30, 32, 1, 1, 1, 1, 1],
    })

    peaks = call_macs_peaks_from_signal(
        signal,
        qvalue=0.05,
        small_local_window_bins=3,
        large_local_window_bins=9,
        name="macs",
    )

    assert len(peaks) == 1
    assert peaks.loc[0, "method"] == "macs_style"
    assert peaks.loc[0, "start"] == 50
    assert peaks.loc[0, "end"] == 70
    assert peaks.loc[0, "qvalue"] <= 0.05
    assert peaks.loc[0, "pvalue"] <= peaks.loc[0, "qvalue"]
    assert peaks.loc[0, "fold_enrichment"] > 1.0
    assert peaks.loc[0, "summit"] in {55, 65}


def test_macs_style_control_track_suppresses_matching_background():
    from uchrom.fea.peaks import call_macs_peaks_from_signal

    signal = pd.DataFrame({
        "chrom": ["chr1"] * 12,
        "start": [i * 10 for i in range(12)],
        "end": [(i + 1) * 10 for i in range(12)],
        "signal": [1, 1, 1, 1, 1, 30, 32, 1, 1, 1, 1, 1],
        "control": [1, 1, 1, 1, 1, 30, 32, 1, 1, 1, 1, 1],
    })

    peaks = call_macs_peaks_from_signal(
        signal,
        signal_col="signal",
        control_col="control",
        qvalue=0.05,
        small_local_window_bins=3,
        large_local_window_bins=9,
    )

    assert peaks.empty


def test_call_peaks_from_track_defaults_to_macs_style():
    from uchrom.fea.peaks import call_peaks_from_track

    cdata = _make_cd()

    peaks = call_peaks_from_track(
        cdata,
        "signal.track",
        qvalue=0.2,
        small_local_window_bins=3,
        large_local_window_bins=5,
    )

    assert len(peaks) == 1
    assert peaks.loc[0, "method"] == "macs_style"
    assert "qvalue" in cdata.results["peaks:signal_track"]
    assert cdata.uns["feature_registry"][0]["parameters"]["method"] == "macs_style"


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
