from pathlib import Path

import numpy as np
import pandas as pd
import pytest


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


def test_macs_poisson_peak_calling_reports_significance():
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
    assert peaks.loc[0, "method"] == "macs_poisson"
    assert peaks.loc[0, "start"] == 50
    assert peaks.loc[0, "end"] == 70
    assert peaks.loc[0, "qvalue"] <= 0.05
    assert peaks.loc[0, "pvalue"] <= peaks.loc[0, "qvalue"]
    assert peaks.loc[0, "fold_enrichment"] > 1.0
    assert peaks.loc[0, "summit"] in {55, 65}


def test_macs_poisson_control_track_suppresses_matching_background():
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


def test_macs_bdgpeakcall_matches_macs3_summit_and_narrowpeak():
    from uchrom.fea.peaks import call_macs_bdgpeaks_from_signal, macs_bdgpeaks_to_narrowpeak

    signal = pd.DataFrame({
        "chrom": ["chr1"] * 8,
        "start": [0, 100, 250, 270, 400, 500, 540, 580],
        "end": [100, 250, 270, 400, 500, 540, 580, 620],
        "score": [0, 6, 0, 8, 0, 9, 0, 9],
    })

    peaks = call_macs_bdgpeaks_from_signal(
        signal,
        cutoff=5,
        min_length=200,
        max_gap=50,
        name="demo",
    )

    assert len(peaks) == 1
    assert peaks.loc[0, "method"] == "macs_bdgpeakcall"
    assert peaks.loc[0, "start"] == 100
    assert peaks.loc[0, "end"] == 400
    assert peaks.loc[0, "score"] == 8
    assert peaks.loc[0, "summit"] == 335
    assert peaks.loc[0, "summit_offset"] == 235

    text = macs_bdgpeaks_to_narrowpeak(peaks, name="demo", trackline=True)
    assert text == (
        'track type=narrowPeak name="demo" description="demo" nextItemButton=on\n'
        "chr1\t100\t400\tdemo_narrowPeak1\t80\t.\t0\t0\t0\t235\n"
    )


def test_macs_bdgpeakcall_matches_macs3_standard_fixture_when_available():
    from uchrom.fea.peaks import (
        call_macs_bdgpeaks_from_bedgraph,
        macs_bdgpeaks_to_narrowpeak,
    )

    fixture_dir = Path("tmp/macs3-source/test")
    input_path = fixture_dir / "standard_results_bdgcmp/run_bdgcmp_FE.bdg"
    expected_path = fixture_dir / "standard_results_bdgpeakcall/run_bdgpeakcall_w_prefix_c2.0_l200_g30_peaks.narrowPeak"
    if not input_path.exists() or not expected_path.exists():
        pytest.skip("MACS3 source fixtures are not available")

    peaks = call_macs_bdgpeaks_from_bedgraph(
        input_path,
        cutoff=2.0,
        min_length=200,
        max_gap=30,
        name="run_bdgpeakcall_w_prefix",
    )
    actual = macs_bdgpeaks_to_narrowpeak(peaks, name="run_bdgpeakcall_w_prefix", trackline=True)

    assert actual == expected_path.read_text()


def test_call_peaks_from_track_defaults_to_macs_bdgpeakcall():
    from uchrom.fea.peaks import call_peaks_from_track

    cdata = _make_cd()

    peaks = call_peaks_from_track(
        cdata,
        "signal.track",
        min_length=1,
    )

    assert len(peaks) == 1
    assert peaks.loc[0, "method"] == "macs_bdgpeakcall"
    assert peaks.loc[0, "start"] == 20
    assert peaks.loc[0, "end"] == 40
    assert cdata.uns["feature_registry"][0]["parameters"]["method"] == "macs_bdgpeakcall"


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
