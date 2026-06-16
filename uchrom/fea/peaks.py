"""Peak calling and peak-derived interval features."""

from __future__ import annotations

import re
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
    agg: str = "mean",
    threshold: float | None = None,
    quantile: float = 0.95,
    min_width_bins: int = 1,
    max_gap_bins: int = 0,
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

    signal = aggregate_track_by_interval(cdata, track, agg=agg)
    peaks = call_peaks_from_signal(
        signal,
        threshold=threshold,
        quantile=quantile,
        min_width_bins=min_width_bins,
        max_gap_bins=max_gap_bins,
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
        "coordinate_convention": "0-based half-open",
        "parameters": {
            "aggregation": agg,
            "threshold": threshold,
            "quantile": quantile,
            "min_width_bins": min_width_bins,
            "max_gap_bins": max_gap_bins,
            "projected_to_tracks": bool(project),
            "track_prefix": prefix,
        },
        "created_by": "uchrom.fea.peaks",
    })
    return peaks


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
    })


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
    ]


__all__ = [
    "PEAK_FEATURE_COLUMNS",
    "add_peak_features",
    "aggregate_track_by_interval",
    "call_peaks_from_signal",
    "call_peaks_from_track",
    "compute_peak_features",
]
