"""Peak calling and peak-derived interval features."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Sequence

import numpy as np
import pandas as pd

from .project import INTERVAL_COLUMNS, project_interval_features_to_spots, unique_spot_intervals
from .registry import append_feature_registry_entry


PEAK_FEATURE_COLUMNS = ("overlap", "count", "distance")


def aggregate_track_by_interval(
    cdata,
    track: str,
    *,
    agg: str = "mean",
    signal_col: str = "signal",
) -> pd.DataFrame:
    """Aggregate a spot-aligned track to unique genomic intervals.

    Multiple spots can share the same genomic bin across cells or traces.  Peak
    callers should operate on the genomic bin signal rather than individual
    spot rows, so this helper collapses duplicate intervals first.
    """
    if track not in cdata.tracks.columns:
        raise ValueError(f"track not found: {track}")
    if agg not in {"mean", "median", "max", "min", "sum"}:
        raise ValueError("agg must be one of: mean, median, max, min, sum")

    frame = cdata.spots.loc[:, list(INTERVAL_COLUMNS)].copy()
    frame["_signal"] = pd.to_numeric(cdata.tracks[track], errors="coerce").to_numpy()
    grouped = frame.groupby(list(INTERVAL_COLUMNS), sort=False, observed=True)["_signal"]
    signal = getattr(grouped, agg)().rename(signal_col)
    counts = grouped.count().rename("n_spots")
    return pd.concat([signal, counts], axis=1).reset_index()


def aggregate_tracks_by_interval(
    cdata,
    tracks: Sequence[str],
    *,
    agg: str = "mean",
) -> pd.DataFrame:
    """Aggregate multiple spot-aligned tracks to unique genomic intervals."""
    tracks = list(tracks)
    missing = [track for track in tracks if track not in cdata.tracks.columns]
    if missing:
        raise ValueError(f"track(s) not found: {missing}")
    if agg not in {"mean", "median", "max", "min", "sum"}:
        raise ValueError("agg must be one of: mean, median, max, min, sum")

    frame = cdata.spots.loc[:, list(INTERVAL_COLUMNS)].copy()
    for track in tracks:
        frame[track] = pd.to_numeric(cdata.tracks[track], errors="coerce").to_numpy()
    grouped = frame.groupby(list(INTERVAL_COLUMNS), sort=False, observed=True)
    out = grouped[tracks].agg(agg).reset_index()
    out["n_spots"] = grouped.size().to_numpy()
    return out


def call_peaks_from_signal(
    signal_table: pd.DataFrame,
    *,
    signal_col: str = "signal",
    threshold: float | None = None,
    quantile: float = 0.95,
    min_width_bins: int = 1,
    max_gap_bins: int = 0,
    name: str = "peak",
) -> pd.DataFrame:
    """Call simple contiguous high-signal peaks from an interval signal table.

    The input table should have ``chrom``, ``start``, ``end``, and
    ``signal_col``.  If ``threshold`` is omitted it is estimated from the
    requested quantile of finite signal values.
    """
    if signal_col not in signal_table.columns:
        raise ValueError(f"signal table missing signal column: {signal_col}")
    if not (0.0 <= float(quantile) <= 1.0):
        raise ValueError("quantile must be between 0 and 1")
    if min_width_bins < 1:
        raise ValueError("min_width_bins must be >= 1")
    if max_gap_bins < 0:
        raise ValueError("max_gap_bins must be >= 0")

    table = _normalise_intervals(signal_table)
    table[signal_col] = pd.to_numeric(signal_table[signal_col], errors="coerce").to_numpy()
    if threshold is None:
        finite = table[signal_col].to_numpy(dtype=float)
        finite = finite[np.isfinite(finite)]
        threshold = float(np.quantile(finite, quantile)) if finite.size else np.inf
    threshold = float(threshold)

    rows: list[dict[str, object]] = []
    for chrom, sub in table.sort_values(["chrom", "start", "end"]).groupby("chrom", sort=False):
        current: list[int] = []
        gap = 0
        for idx, row in sub.iterrows():
            value = float(row[signal_col])
            is_hit = np.isfinite(value) and value >= threshold
            if is_hit:
                current.append(idx)
                gap = 0
                continue
            if current:
                gap += 1
                if gap > max_gap_bins:
                    _append_peak_row(rows, table, current, signal_col, threshold, chrom, name)
                    current = []
                    gap = 0
        if current:
            _append_peak_row(rows, table, current, signal_col, threshold, chrom, name)

    out = pd.DataFrame(rows, columns=_peak_columns())
    if out.empty:
        return out
    out = out[out["n_bins"].astype(int) >= int(min_width_bins)].reset_index(drop=True)
    out["peak_id"] = [f"{name}_{i + 1}" for i in range(len(out))]
    return out.loc[:, _peak_columns()]


def call_macs_peaks_from_signal(
    signal_table: pd.DataFrame,
    *,
    signal_col: str = "signal",
    control_col: str | None = None,
    qvalue: float | None = 0.05,
    pvalue: float | None = None,
    genome_size: int | float | None = None,
    small_local_window_bins: int = 10,
    large_local_window_bins: int = 100,
    fragment_size_bins: int = 1,
    nolambda: bool = False,
    min_width_bins: int = 1,
    max_gap_bins: int = 0,
    signal_scale: float = 1.0,
    control_scale: float | None = None,
    negative: str = "clip",
    name: str = "peak",
) -> pd.DataFrame:
    """Call peaks with U-Chrom's legacy dynamic Poisson approximation.

    Observed binned signal is tested against a dynamic local lambda using
    Poisson tail probabilities, p-values are Benjamini-Hochberg adjusted, and
    significant adjacent bins are merged into peak intervals. Use
    ``call_macs_bdgpeaks_from_signal`` for the MACS3 ``bdgpeakcall`` port.
    """
    if pvalue is not None and qvalue is not None:
        if float(qvalue) == 0.05:
            qvalue = None
        else:
            raise ValueError("pvalue and qvalue are mutually exclusive")
    if pvalue is None and qvalue is None:
        qvalue = 0.05
    if pvalue is not None and not (0.0 < float(pvalue) <= 1.0):
        raise ValueError("pvalue must be in (0, 1]")
    if qvalue is not None and not (0.0 < float(qvalue) <= 1.0):
        raise ValueError("qvalue must be in (0, 1]")
    if min_width_bins < 1:
        raise ValueError("min_width_bins must be >= 1")
    if max_gap_bins < 0:
        raise ValueError("max_gap_bins must be >= 0")

    missing = [c for c in [signal_col, control_col] if c and c not in signal_table.columns]
    if missing:
        raise ValueError(f"signal table missing column(s): {missing}")

    table = _normalise_intervals(signal_table)
    table[signal_col] = pd.to_numeric(signal_table[signal_col], errors="coerce").to_numpy()
    if control_col is not None:
        table[control_col] = pd.to_numeric(signal_table[control_col], errors="coerce").to_numpy()

    lengths = (table["end"].to_numpy(dtype=float) - table["start"].to_numpy(dtype=float))
    observed = _scaled_counts(table[signal_col].to_numpy(dtype=float), signal_scale, negative)
    if control_col is None:
        background = observed.copy()
        control_scale_used = None
    else:
        raw_control = _scaled_counts(table[control_col].to_numpy(dtype=float), 1.0, negative)
        if control_scale is None:
            control_total = float(np.nansum(raw_control))
            signal_total = float(np.nansum(observed))
            control_scale_used = signal_total / control_total if control_total > 0 else 1.0
        else:
            control_scale_used = float(control_scale)
        background = raw_control * control_scale_used

    lambdas = _dynamic_lambda(
        table,
        background,
        lengths,
        genome_size=genome_size,
        window_bins=[fragment_size_bins, small_local_window_bins, large_local_window_bins],
        nolambda=nolambda,
        exclude_self=(control_col is None),
    )
    pvals = _poisson_tail_pvalues(observed, lambdas)
    qvals = _bh_qvalues(pvals)
    if pvalue is not None:
        significant = pvals <= float(pvalue)
    else:
        significant = qvals <= float(qvalue)

    work = table.copy()
    work["_observed"] = observed
    work["_lambda"] = lambdas
    work["_pvalue"] = pvals
    work["_qvalue"] = qvals
    work["_fold_enrichment"] = (observed + 1e-12) / (lambdas + 1e-12)
    work["_significant"] = significant

    rows: list[dict[str, object]] = []
    for chrom, sub in work.sort_values(["chrom", "start", "end"]).groupby("chrom", sort=False):
        _append_macs_peak_rows(
            rows,
            sub,
            chrom=str(chrom),
            name=name,
            signal_col=signal_col,
            max_gap_bins=max_gap_bins,
            pvalue_cutoff=pvalue,
            qvalue_cutoff=qvalue,
            control_col=control_col,
            control_scale=control_scale_used,
        )

    out = pd.DataFrame(rows, columns=_peak_columns())
    if out.empty:
        return out
    out = out[out["n_bins"].astype(int) >= int(min_width_bins)].reset_index(drop=True)
    out["peak_id"] = [f"{name}_{i + 1}" for i in range(len(out))]
    return out.loc[:, _peak_columns()]


def read_bedgraph(path: str | Path, *, signal_col: str = "score") -> pd.DataFrame:
    """Read a MACS-compatible bedGraph score track into an interval table."""
    rows: list[dict[str, object]] = []
    with Path(path).open() as handle:
        for line in handle:
            line = line.strip()
            if not line or line.startswith(("#", "track", "browse")):
                continue
            fields = line.split()
            if len(fields) < 4:
                raise ValueError(f"bedGraph line must have at least 4 columns: {line!r}")
            rows.append({
                "chrom": fields[0],
                "start": int(fields[1]),
                "end": int(fields[2]),
                signal_col: float(fields[3]),
            })
    return pd.DataFrame(rows, columns=["chrom", "start", "end", signal_col])


def call_macs_bdgpeaks_from_signal(
    signal_table: pd.DataFrame,
    *,
    signal_col: str = "score",
    cutoff: float = 5.0,
    min_length: int = 200,
    max_gap: int = 30,
    name: str = "MACS",
    name_prefix: str | None = None,
) -> pd.DataFrame:
    """Call peaks using a Python port of MACS3 ``bdgpeakcall``.

    This mirrors MACS3's ``bedGraphTrackI.call_peaks`` behavior for score
    tracks: regions with values at or above ``cutoff`` are merged when the
    intervening gap is at most ``max_gap`` bases, peaks shorter than
    ``min_length`` bases are discarded, and the summit follows MACS3's
    tie-breaking rule. The port follows MACS3's BSD-licensed ``bdgpeakcall``
    and narrowPeak semantics without vendoring the MACS3 package at runtime.
    """
    if signal_col not in signal_table.columns:
        raise ValueError(f"signal table missing signal column: {signal_col}")
    if min_length < 1:
        raise ValueError("min_length must be >= 1")
    if max_gap < 0:
        raise ValueError("max_gap must be >= 0")

    table = _normalise_intervals(signal_table)
    table[signal_col] = pd.to_numeric(signal_table[signal_col], errors="coerce").to_numpy()
    segments = _macs_bdg_segments(table, signal_col=signal_col, baseline_value=0.0)

    rows: list[dict[str, object]] = []
    for chrom in sorted(segments):
        _append_macs_bdgpeak_rows(
            rows,
            chrom=chrom,
            segments=segments[chrom],
            cutoff=float(cutoff),
            min_length=int(min_length),
            max_gap=int(max_gap),
            signal_col=signal_col,
            name=name,
            name_prefix=name_prefix,
        )

    out = pd.DataFrame(rows, columns=_peak_columns())
    if out.empty:
        return out
    out["peak_id"] = [f"{name}_{i + 1}" for i in range(len(out))]
    return out.loc[:, _peak_columns()]


def call_macs_bdgpeaks_from_bedgraph(
    path: str | Path,
    *,
    signal_col: str = "score",
    cutoff: float = 5.0,
    min_length: int = 200,
    max_gap: int = 30,
    name: str = "MACS",
    name_prefix: str | None = None,
) -> pd.DataFrame:
    """Read a bedGraph file and call MACS3 ``bdgpeakcall``-compatible peaks."""
    return call_macs_bdgpeaks_from_signal(
        read_bedgraph(path, signal_col=signal_col),
        signal_col=signal_col,
        cutoff=cutoff,
        min_length=min_length,
        max_gap=max_gap,
        name=name,
        name_prefix=name_prefix,
    )


def macs_bdgpeaks_to_narrowpeak(
    peaks: pd.DataFrame,
    *,
    name: str = "MACS",
    name_prefix: str | None = None,
    trackline: bool = False,
    score_column: str = "score",
) -> str:
    """Render MACS ``bdgpeakcall``-compatible peaks as narrowPeak text."""
    if name_prefix is None:
        name_prefix = f"{name}_narrowPeak"
    try:
        peak_prefix = name_prefix % name
    except Exception:
        peak_prefix = name_prefix

    lines: list[str] = []
    if trackline:
        lines.append(f'track type=narrowPeak name="{name}" description="{name}" nextItemButton=on')
    if peaks is None or peaks.empty:
        return "\n".join(lines) + ("\n" if lines else "")

    table = _normalise_peaks(peaks).copy()
    for column in [score_column, "fold_enrichment", "summit_pvalue", "summit_qvalue", "summit"]:
        if column in peaks.columns:
            table[column] = pd.to_numeric(peaks[column], errors="coerce").to_numpy()
    table["peak_order"] = np.arange(len(table))

    n_peak = 0
    for chrom in sorted(table["chrom"].unique()):
        sub = table[table["chrom"] == chrom].sort_values(["start", "end", "peak_order"])
        for _, peak in sub.iterrows():
            n_peak += 1
            summit = int(peak["summit"]) if np.isfinite(float(peak.get("summit", np.nan))) else -1
            summit_offset = -1 if summit == -1 else summit - int(peak["start"])
            score = int(10 * float(peak.get(score_column, 0.0)))
            fc = float(peak.get("fold_enrichment", 0.0))
            pscore = float(peak.get("summit_pvalue", 0.0))
            qscore = float(peak.get("summit_qvalue", 0.0))
            lines.append(
                "%s\t%d\t%d\t%s%d\t%d\t.\t%.6g\t%.6g\t%.6g\t%d"
                % (
                    chrom,
                    int(peak["start"]),
                    int(peak["end"]),
                    peak_prefix,
                    n_peak,
                    score,
                    fc,
                    pscore,
                    qscore,
                    summit_offset,
                )
            )
    return "\n".join(lines) + "\n"


def compute_peak_features(
    intervals: pd.DataFrame,
    peaks: pd.DataFrame,
    *,
    name: str = "peak",
) -> pd.DataFrame:
    """Compute overlap/count/distance features from peak intervals."""
    interval_table = _normalise_intervals(intervals)
    out = interval_table.copy()
    prefix = _safe_name(name)
    overlap_col = f"{prefix}_overlap"
    count_col = f"{prefix}_count"
    distance_col = f"distance_to_{prefix}"
    out[overlap_col] = 0.0
    out[count_col] = 0.0
    out[distance_col] = np.nan

    peaks = _normalise_peaks(peaks)
    if peaks.empty:
        return out

    for chrom, idx in interval_table.groupby("chrom").groups.items():
        idx_array = idx.to_numpy()
        sub = peaks[peaks["chrom"] == str(chrom)]
        if sub.empty:
            continue
        start = interval_table.loc[idx_array, "start"].to_numpy()
        end = interval_table.loc[idx_array, "end"].to_numpy()
        peak_start = sub["start"].to_numpy()
        peak_end = sub["end"].to_numpy()
        bp = np.maximum(0, np.minimum(end[:, None], peak_end[None, :]) - np.maximum(start[:, None], peak_start[None, :]))
        hit = bp > 0
        out.loc[idx_array, overlap_col] = hit.any(axis=1).astype(float)
        out.loc[idx_array, count_col] = hit.sum(axis=1).astype(float)
        distances = np.where(
            hit,
            0,
            np.maximum.reduce([
                peak_start[None, :] - end[:, None],
                start[:, None] - peak_end[None, :],
                np.zeros_like(bp),
            ]),
        )
        out.loc[idx_array, distance_col] = np.min(distances, axis=1)
    return out


def add_peak_features(
    cdata,
    peaks: pd.DataFrame,
    *,
    name: str = "peak",
    prefix: str = "peak",
    result_key: str = "bin_features",
    project: bool = True,
    store: bool = True,
    overwrite: bool = False,
    source_peak_key: str | None = None,
) -> pd.DataFrame:
    """Project an existing peak table into interval and spot features."""
    table = compute_peak_features(unique_spot_intervals(cdata), peaks, name=name)
    value_columns = [c for c in table.columns if c not in INTERVAL_COLUMNS]
    if store:
        cdata.results[result_key] = _merge_feature_table(
            cdata.results.get(result_key),
            table,
            value_columns=value_columns,
            overwrite=overwrite,
        )
    projected = [_prefixed_name(col, prefix) for col in value_columns]
    if project:
        cdata.tracks = project_interval_features_to_spots(
            cdata,
            table,
            prefix=prefix,
            value_columns=value_columns,
            into=cdata.tracks,
            overwrite=overwrite,
        )
    append_feature_registry_entry(cdata, {
        "feature_group": "peaks",
        "features": projected if project else value_columns,
        "result_key": result_key if store else None,
        "source_results": [source_peak_key] if source_peak_key else [],
        "coordinate_convention": "0-based half-open",
        "parameters": {
            "name": name,
            "projected_to_tracks": bool(project),
            "track_prefix": prefix,
        },
        "created_by": "uchrom.fea.peaks",
    })
    return table


def call_peaks_from_track(
    cdata,
    track: str,
    *,
    method: str = "auto",
    control_track: str | None = None,
    agg: str = "mean",
    threshold: float | None = None,
    quantile: float = 0.95,
    cutoff: float | None = None,
    min_length: int = 200,
    max_gap: int = 30,
    qvalue: float | None = 0.05,
    pvalue: float | None = None,
    genome_size: int | float | None = None,
    small_local_window_bins: int = 10,
    large_local_window_bins: int = 100,
    fragment_size_bins: int = 1,
    nolambda: bool = False,
    min_width_bins: int = 1,
    max_gap_bins: int = 0,
    signal_scale: float = 1.0,
    control_scale: float | None = None,
    negative: str = "clip",
    peaks_key: str | None = None,
    feature_name: str | None = None,
    prefix: str = "peak",
    result_key: str = "bin_features",
    project: bool = True,
    store: bool = True,
    overwrite: bool = False,
) -> pd.DataFrame:
    """Aggregate a track, call peaks, and project peak features to spots."""
    safe_track = _safe_name(track)
    feature_name = _safe_name(feature_name or safe_track)
    peaks_key = peaks_key or f"peaks:{safe_track}"

    method = str(method).lower()
    if method == "auto":
        method = "threshold" if threshold is not None else "macs"
    method_aliases = {
        "macs": "macs_bdgpeakcall",
        "bdgpeakcall": "macs_bdgpeakcall",
        "macs3_bdgpeakcall": "macs_bdgpeakcall",
        "macs_style": "macs_poisson",
    }
    method = method_aliases.get(method, method)
    if method not in {"threshold", "macs_bdgpeakcall", "macs_poisson"}:
        raise ValueError("method must be one of: auto, threshold, macs, macs_bdgpeakcall, macs_poisson")

    if method == "threshold":
        signal = aggregate_track_by_interval(cdata, track, agg=agg)
        peaks = call_peaks_from_signal(
            signal,
            threshold=threshold,
            quantile=quantile,
            min_width_bins=min_width_bins,
            max_gap_bins=max_gap_bins,
            name=feature_name,
        )
    elif method == "macs_bdgpeakcall":
        if control_track is not None:
            raise ValueError("control_track is only supported by method='macs_poisson'")
        signal = aggregate_track_by_interval(cdata, track, agg=agg, signal_col=track)
        peaks = call_macs_bdgpeaks_from_signal(
            signal,
            signal_col=track,
            cutoff=5.0 if cutoff is None else cutoff,
            min_length=min_length,
            max_gap=max_gap,
            name=feature_name,
        )
    else:
        tracks = [track] if control_track is None else [track, control_track]
        signal = aggregate_tracks_by_interval(cdata, tracks, agg=agg)
        control_col = control_track
        peaks = call_macs_peaks_from_signal(
            signal,
            signal_col=track,
            control_col=control_col,
            qvalue=qvalue,
            pvalue=pvalue,
            genome_size=genome_size,
            small_local_window_bins=small_local_window_bins,
            large_local_window_bins=large_local_window_bins,
            fragment_size_bins=fragment_size_bins,
            nolambda=nolambda,
            min_width_bins=min_width_bins,
            max_gap_bins=max_gap_bins,
            signal_scale=signal_scale,
            control_scale=control_scale,
            negative=negative,
            name=feature_name,
        )
    if store:
        cdata.results[peaks_key] = peaks
    table = compute_peak_features(unique_spot_intervals(cdata), peaks, name=feature_name)
    value_columns = [c for c in table.columns if c not in INTERVAL_COLUMNS]

    if store:
        cdata.results[result_key] = _merge_feature_table(
            cdata.results.get(result_key),
            table,
            value_columns=value_columns,
            overwrite=overwrite,
        )
    projected = [_prefixed_name(col, prefix) for col in value_columns]
    if project:
        cdata.tracks = project_interval_features_to_spots(
            cdata,
            table,
            prefix=prefix,
            value_columns=value_columns,
            into=cdata.tracks,
            overwrite=overwrite,
        )
    append_feature_registry_entry(cdata, {
        "feature_group": "peaks",
        "features": projected if project else value_columns,
        "result_key": result_key if store else None,
        "source_results": [peaks_key] if store else [],
        "source_track": track,
        "control_track": control_track,
        "coordinate_convention": "0-based half-open",
        "parameters": {
            "method": method,
            "aggregation": agg,
            "threshold": threshold,
            "quantile": quantile,
            "cutoff": cutoff,
            "min_length": min_length,
            "max_gap": max_gap,
            "qvalue": qvalue,
            "pvalue": pvalue,
            "genome_size": genome_size,
            "small_local_window_bins": small_local_window_bins,
            "large_local_window_bins": large_local_window_bins,
            "fragment_size_bins": fragment_size_bins,
            "nolambda": nolambda,
            "min_width_bins": min_width_bins,
            "max_gap_bins": max_gap_bins,
            "signal_scale": signal_scale,
            "control_scale": control_scale,
            "negative": negative,
            "projected_to_tracks": bool(project),
            "track_prefix": prefix,
        },
        "created_by": "uchrom.fea.peaks",
    })
    return peaks


def _macs_bdg_segments(
    table: pd.DataFrame,
    *,
    signal_col: str,
    baseline_value: float,
) -> dict[str, list[tuple[int, int, float]]]:
    """Build MACS3-style bedGraph transition segments from sorted intervals."""
    segments: dict[str, list[tuple[int, int, float]]] = {}
    for _, row in table.sort_values(["chrom", "start", "end"]).iterrows():
        chrom = str(row["chrom"])
        start = int(row["start"])
        end = int(row["end"])
        value = float(row[signal_col])
        if end <= 0:
            continue
        if start < 0:
            start = 0
        chrom_segments = segments.setdefault(chrom, [])
        if not chrom_segments:
            if start:
                chrom_segments.append((0, start, float(baseline_value)))
            chrom_segments.append((start, end, value))
            continue
        previous_start, previous_end, previous_value = chrom_segments[-1]
        if previous_value == value:
            chrom_segments[-1] = (previous_start, end, value)
        else:
            chrom_segments.append((previous_end, end, value))
    return segments


def _append_macs_bdgpeak_rows(
    rows: list[dict[str, object]],
    *,
    chrom: str,
    segments: list[tuple[int, int, float]],
    cutoff: float,
    min_length: int,
    max_gap: int,
    signal_col: str,
    name: str,
    name_prefix: str | None,
) -> None:
    peak_content: list[tuple[int, int, float]] | None = None
    x = 0
    for segment in segments:
        x += 1
        if segment[2] >= cutoff:
            peak_content = [segment]
            break

    if peak_content is None:
        return

    for segment in segments[x:]:
        start, _end, value = segment
        if value < cutoff:
            continue
        if start - peak_content[-1][1] <= max_gap:
            peak_content.append(segment)
        else:
            _append_one_macs_bdgpeak(
                rows,
                peak_content,
                chrom=chrom,
                cutoff=cutoff,
                min_length=min_length,
                max_gap=max_gap,
                signal_col=signal_col,
                name=name,
                name_prefix=name_prefix,
            )
            peak_content = [segment]

    _append_one_macs_bdgpeak(
        rows,
        peak_content,
        chrom=chrom,
        cutoff=cutoff,
        min_length=min_length,
        max_gap=max_gap,
        signal_col=signal_col,
        name=name,
        name_prefix=name_prefix,
    )


def _append_one_macs_bdgpeak(
    rows: list[dict[str, object]],
    peak_content: list[tuple[int, int, float]],
    *,
    chrom: str,
    cutoff: float,
    min_length: int,
    max_gap: int,
    signal_col: str,
    name: str,
    name_prefix: str | None,
) -> None:
    peak_start = int(peak_content[0][0])
    peak_end = int(peak_content[-1][1])
    peak_length = peak_end - peak_start
    if peak_length < min_length:
        return

    tsummit: list[int] = []
    summit_value = 0.0
    for start, end, value in peak_content:
        if (not summit_value) or summit_value < value:
            tsummit = [int((end + start) / 2)]
            summit_value = float(value)
        elif summit_value == value:
            tsummit.append(int((end + start) / 2))
    summit = tsummit[int((len(tsummit) + 1) / 2) - 1]
    widths = np.array([end - start for start, end, _value in peak_content], dtype=float)
    values = np.array([value for _start, _end, value in peak_content], dtype=float)
    mean_signal = float(np.average(values, weights=widths)) if widths.sum() else float(np.nanmean(values))
    peak_prefix = f"{name}_narrowPeak" if name_prefix is None else name_prefix
    rows.append({
        "peak_id": f"{name}_{len(rows) + 1}",
        "chrom": str(chrom),
        "start": peak_start,
        "end": peak_end,
        "n_bins": int(len(peak_content)),
        "score": float(summit_value),
        "max_signal": float(np.nanmax(values)),
        "mean_signal": mean_signal,
        "threshold": float(cutoff),
        "signal_col": str(signal_col),
        "method": "macs_bdgpeakcall",
        "pvalue": np.nan,
        "qvalue": np.nan,
        "fold_enrichment": 0.0,
        "lambda": np.nan,
        "pileup": 0.0,
        "summit": int(summit),
        "summit_signal": float(summit_value),
        "summit_pvalue": 0.0,
        "summit_qvalue": 0.0,
        "pvalue_cutoff": np.nan,
        "qvalue_cutoff": np.nan,
        "control_col": "",
        "control_scale": np.nan,
        "min_length": int(min_length),
        "max_gap": int(max_gap),
        "summit_offset": int(summit - peak_start),
        "narrowpeak_score": int(10 * float(summit_value)),
        "macs_name_prefix": peak_prefix,
    })


def _append_peak_row(
    rows: list[dict[str, object]],
    table: pd.DataFrame,
    indices: list[int],
    signal_col: str,
    threshold: float,
    chrom: str,
    name: str,
) -> None:
    sub = table.loc[indices]
    values = sub[signal_col].to_numpy(dtype=float)
    rows.append({
        "peak_id": f"{name}_{len(rows) + 1}",
        "chrom": str(chrom),
        "start": int(sub["start"].min()),
        "end": int(sub["end"].max()),
        "n_bins": int(len(sub)),
        "score": float(np.nanmax(values)),
        "max_signal": float(np.nanmax(values)),
        "mean_signal": float(np.nanmean(values)),
        "threshold": float(threshold),
        "signal_col": str(signal_col),
        "method": "threshold",
        "pvalue": np.nan,
        "qvalue": np.nan,
        "fold_enrichment": np.nan,
        "lambda": np.nan,
        "pileup": float(np.nanmax(values)),
        "summit": int((int(sub["start"].min()) + int(sub["end"].max())) * 0.5),
        "summit_signal": float(np.nanmax(values)),
        "summit_pvalue": np.nan,
        "summit_qvalue": np.nan,
    })


def _append_macs_peak_rows(
    rows: list[dict[str, object]],
    table: pd.DataFrame,
    *,
    chrom: str,
    name: str,
    signal_col: str,
    max_gap_bins: int,
    pvalue_cutoff: float | None,
    qvalue_cutoff: float | None,
    control_col: str | None,
    control_scale: float | None,
) -> None:
    current: list[int] = []
    gap = 0
    for idx, row in table.iterrows():
        if bool(row["_significant"]):
            current.append(idx)
            gap = 0
            continue
        if current:
            gap += 1
            if gap > max_gap_bins:
                _append_one_macs_peak(
                    rows,
                    table.loc[current],
                    chrom=chrom,
                    name=name,
                    signal_col=signal_col,
                    pvalue_cutoff=pvalue_cutoff,
                    qvalue_cutoff=qvalue_cutoff,
                    control_col=control_col,
                    control_scale=control_scale,
                )
                current = []
                gap = 0
    if current:
        _append_one_macs_peak(
            rows,
            table.loc[current],
            chrom=chrom,
            name=name,
            signal_col=signal_col,
            pvalue_cutoff=pvalue_cutoff,
            qvalue_cutoff=qvalue_cutoff,
            control_col=control_col,
            control_scale=control_scale,
        )


def _append_one_macs_peak(
    rows: list[dict[str, object]],
    peak: pd.DataFrame,
    *,
    chrom: str,
    name: str,
    signal_col: str,
    pvalue_cutoff: float | None,
    qvalue_cutoff: float | None,
    control_col: str | None,
    control_scale: float | None,
) -> None:
    if peak.empty:
        return
    qvals = peak["_qvalue"].to_numpy(dtype=float)
    pvals = peak["_pvalue"].to_numpy(dtype=float)
    observed = peak["_observed"].to_numpy(dtype=float)
    lambdas = peak["_lambda"].to_numpy(dtype=float)
    fold = peak["_fold_enrichment"].to_numpy(dtype=float)
    if np.isfinite(qvals).any():
        summit_pos = int(np.nanargmin(qvals))
    else:
        summit_pos = int(np.nanargmax(observed))
    summit = peak.iloc[summit_pos]
    min_q = float(np.nanmin(qvals)) if np.isfinite(qvals).any() else np.nan
    min_p = float(np.nanmin(pvals)) if np.isfinite(pvals).any() else np.nan
    score_source = min_q if np.isfinite(min_q) else min_p
    score = -10.0 * np.log10(max(score_source, 1e-300)) if np.isfinite(score_source) else np.nan
    rows.append({
        "peak_id": f"{name}_{len(rows) + 1}",
        "chrom": str(chrom),
        "start": int(peak["start"].min()),
        "end": int(peak["end"].max()),
        "n_bins": int(len(peak)),
        "score": float(score),
        "max_signal": float(np.nanmax(observed)),
        "mean_signal": float(np.nanmean(observed)),
        "threshold": np.nan,
        "signal_col": str(signal_col),
        "method": "macs_poisson",
        "pvalue": min_p,
        "qvalue": min_q,
        "fold_enrichment": float(np.nanmax(fold)),
        "lambda": float(np.nanmean(lambdas)),
        "pileup": float(np.nanmax(observed)),
        "summit": int((int(summit["start"]) + int(summit["end"])) * 0.5),
        "summit_signal": float(summit["_observed"]),
        "summit_pvalue": float(summit["_pvalue"]),
        "summit_qvalue": float(summit["_qvalue"]),
        "pvalue_cutoff": np.nan if pvalue_cutoff is None else float(pvalue_cutoff),
        "qvalue_cutoff": np.nan if qvalue_cutoff is None else float(qvalue_cutoff),
        "control_col": "" if control_col is None else str(control_col),
        "control_scale": np.nan if control_scale is None else float(control_scale),
    })


def _dynamic_lambda(
    table: pd.DataFrame,
    background: np.ndarray,
    lengths: np.ndarray,
    *,
    genome_size: int | float | None,
    window_bins: Sequence[int],
    nolambda: bool,
    exclude_self: bool,
) -> np.ndarray:
    total_bp = float(genome_size) if genome_size is not None else float(np.nansum(lengths))
    if total_bp <= 0:
        raise ValueError("genome_size/interval lengths must be positive")
    global_rate = float(np.nansum(background)) / total_bp
    lambdas = np.maximum(global_rate * lengths, 1e-12)
    if nolambda:
        return lambdas

    out = lambdas.copy()
    for chrom, idx in table.groupby("chrom").groups.items():
        idx_array = idx.to_numpy()
        chrom_counts = background[idx_array]
        chrom_lengths = lengths[idx_array]
        chrom_lambda = out[idx_array]
        for window in window_bins:
            if int(window) <= 0:
                continue
            local = _centered_window_lambda(
                chrom_counts,
                chrom_lengths,
                int(window),
                exclude_self=exclude_self,
            )
            chrom_lambda = np.maximum(chrom_lambda, local)
        out[idx_array] = chrom_lambda
    return np.maximum(out, 1e-12)


def _centered_window_lambda(
    counts: np.ndarray,
    lengths: np.ndarray,
    window_bins: int,
    *,
    exclude_self: bool,
) -> np.ndarray:
    n = len(counts)
    if n == 0:
        return np.array([], dtype=float)
    half = max(0, int(window_bins) // 2)
    count_prefix = np.concatenate([[0.0], np.cumsum(np.nan_to_num(counts, nan=0.0))])
    length_prefix = np.concatenate([[0.0], np.cumsum(lengths)])
    out = np.zeros(n, dtype=float)
    for i in range(n):
        left = max(0, i - half)
        right = min(n, i + half + 1)
        total_count = count_prefix[right] - count_prefix[left]
        total_bp = length_prefix[right] - length_prefix[left]
        if exclude_self:
            total_count -= np.nan_to_num(counts[i], nan=0.0)
            total_bp -= lengths[i]
        if total_bp <= 0:
            out[i] = 0.0
        else:
            out[i] = total_count / total_bp * lengths[i]
    return np.maximum(out, 1e-12)


def _poisson_tail_pvalues(observed: np.ndarray, lambdas: np.ndarray) -> np.ndarray:
    from scipy.stats import poisson

    counts = np.rint(np.nan_to_num(observed, nan=0.0)).astype(np.int64)
    counts = np.maximum(counts, 0)
    pvals = poisson.sf(counts - 1, lambdas)
    pvals[counts <= 0] = 1.0
    pvals = np.asarray(pvals, dtype=float)
    pvals[~np.isfinite(pvals)] = 1.0
    return np.clip(pvals, 0.0, 1.0)


def _bh_qvalues(pvals: np.ndarray) -> np.ndarray:
    pvals = np.asarray(pvals, dtype=float)
    qvals = np.full_like(pvals, np.nan, dtype=float)
    valid = np.isfinite(pvals)
    if not valid.any():
        return qvals
    pv = np.clip(pvals[valid], 0.0, 1.0)
    order = np.argsort(pv)
    ranked = pv[order]
    n = len(ranked)
    adjusted = ranked * n / np.arange(1, n + 1)
    adjusted = np.minimum.accumulate(adjusted[::-1])[::-1]
    adjusted = np.clip(adjusted, 0.0, 1.0)
    valid_indices = np.flatnonzero(valid)
    qvals[valid_indices[order]] = adjusted
    return qvals


def _scaled_counts(values: np.ndarray, scale: float, negative: str) -> np.ndarray:
    if negative not in {"clip", "raise", "shift"}:
        raise ValueError("negative must be one of: clip, raise, shift")
    out = np.asarray(values, dtype=float) * float(scale)
    if negative == "raise" and np.nanmin(out) < 0:
        raise ValueError("macs_poisson peak calling requires non-negative signal")
    if negative == "clip":
        out = np.where(np.isfinite(out), np.maximum(out, 0.0), np.nan)
    elif negative == "shift":
        finite = out[np.isfinite(out)]
        if finite.size and finite.min() < 0:
            out = out - finite.min()
    out[~np.isfinite(out)] = 0.0
    return out


def _normalise_intervals(frame: pd.DataFrame) -> pd.DataFrame:
    if not isinstance(frame, pd.DataFrame):
        raise TypeError("intervals must be a pandas DataFrame")
    missing = [c for c in INTERVAL_COLUMNS if c not in frame.columns]
    if missing:
        raise ValueError(f"interval table missing columns: {missing}")
    out = frame.copy()
    out["chrom"] = out["chrom"].astype(str)
    out["start"] = out["start"].astype(np.int64)
    out["end"] = out["end"].astype(np.int64)
    bad = out["end"] <= out["start"]
    if bad.any():
        rows = out.loc[bad, list(INTERVAL_COLUMNS)].head(3).to_dict("records")
        raise ValueError(f"intervals must satisfy end > start: {rows}")
    return out.reset_index(drop=True)


def _normalise_peaks(peaks: pd.DataFrame) -> pd.DataFrame:
    if peaks is None:
        return pd.DataFrame(columns=list(INTERVAL_COLUMNS))
    if not isinstance(peaks, pd.DataFrame):
        raise TypeError("peaks must be a pandas DataFrame")
    if peaks.empty:
        return pd.DataFrame(columns=list(INTERVAL_COLUMNS))
    return _normalise_intervals(peaks)


def _merge_feature_table(
    existing,
    table: pd.DataFrame,
    *,
    value_columns: Sequence[str],
    overwrite: bool,
) -> pd.DataFrame:
    if existing is None:
        return table[list(INTERVAL_COLUMNS) + list(value_columns)].copy()
    if not isinstance(existing, pd.DataFrame):
        raise TypeError("existing result table must be a pandas DataFrame")
    missing = [c for c in INTERVAL_COLUMNS if c not in existing.columns]
    if missing:
        raise ValueError(f"existing result table missing interval columns: {missing}")

    out = existing.copy()
    conflicts = [c for c in value_columns if c in out.columns]
    if conflicts and not overwrite:
        raise ValueError(f"result table already contains columns: {conflicts}")
    if conflicts:
        out = out.drop(columns=conflicts)
    return out.merge(table[list(INTERVAL_COLUMNS) + list(value_columns)], on=list(INTERVAL_COLUMNS), how="outer")


def _prefixed_name(name: str, prefix: str | None) -> str:
    if not prefix:
        return str(name)
    prefix = str(prefix).rstrip(".")
    name = str(name)
    if name.startswith(prefix + "."):
        return name
    return f"{prefix}.{name}"


def _safe_name(name: str) -> str:
    return re.sub(r"[^0-9A-Za-z]+", "_", str(name)).strip("_").lower() or "peak"


def _peak_columns() -> list[str]:
    return [
        "peak_id",
        "chrom",
        "start",
        "end",
        "n_bins",
        "score",
        "max_signal",
        "mean_signal",
        "threshold",
        "signal_col",
        "method",
        "pvalue",
        "qvalue",
        "fold_enrichment",
        "lambda",
        "pileup",
        "summit",
        "summit_signal",
        "summit_pvalue",
        "summit_qvalue",
        "pvalue_cutoff",
        "qvalue_cutoff",
        "control_col",
        "control_scale",
        "min_length",
        "max_gap",
        "summit_offset",
        "narrowpeak_score",
        "macs_name_prefix",
    ]


__all__ = [
    "PEAK_FEATURE_COLUMNS",
    "add_peak_features",
    "aggregate_track_by_interval",
    "aggregate_tracks_by_interval",
    "call_macs_bdgpeaks_from_bedgraph",
    "call_macs_bdgpeaks_from_signal",
    "call_macs_peaks_from_signal",
    "call_peaks_from_signal",
    "call_peaks_from_track",
    "compute_peak_features",
    "macs_bdgpeaks_to_narrowpeak",
    "read_bedgraph",
]
