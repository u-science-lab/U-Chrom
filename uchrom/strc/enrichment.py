"""Structural feature enrichment helpers for ``ChromData``.

This module wraps existing structure callers and projects their interval
outputs back onto the spot axis.  It is deliberately independent of
``uchrom.auto_discovery`` so browser, plotting, notebooks, and discovery can
share the same structural feature layer.
"""

from __future__ import annotations

from typing import Sequence

import numpy as np
import pandas as pd

from uchrom.fea.project import INTERVAL_COLUMNS, project_interval_features_to_spots, unique_spot_intervals
from uchrom.fea.registry import append_feature_registry_entry


STRUCTURAL_FEATURE_COLUMNS = (
    "distance_to_tad_boundary",
    "inside_tad",
    "loop_anchor_overlap",
    "loop_anchor_count",
    "distance_to_loop_anchor",
    "compartment_label",
    "compartment_pc2",
)


def call_tads_multi(
    cdata,
    *,
    chroms: Sequence[str] | None = None,
    params=None,
    device: str = "auto",
    result_key: str = "tads",
    store: bool = True,
    verbose: bool = False,
) -> pd.DataFrame:
    """Call TADs on multiple chromosomes and optionally store one merged table."""
    from uchrom.strc.tad import call_tads_by_pval

    rows = []
    for chrom in _chroms(cdata, chroms):
        df = call_tads_by_pval(
            cdata,
            chrom=chrom,
            params=params,
            device=device,
            store=False,
            verbose=verbose,
        )
        if not df.empty:
            rows.append(df)
    out = _concat_or_empty(rows, _empty_tads())
    if store:
        cdata.results[result_key] = out
    return out


def call_loops_multi(
    cdata,
    *,
    chroms: Sequence[str] | None = None,
    params=None,
    device: str = "auto",
    result_key: str = "loops",
    store: bool = True,
    verbose: bool = False,
) -> pd.DataFrame:
    """Call loops on multiple chromosomes and optionally store one merged table."""
    from uchrom.strc.loop import call_loops_axiswise_f

    rows = []
    for chrom in _chroms(cdata, chroms):
        df = call_loops_axiswise_f(
            cdata,
            chrom=chrom,
            params=params,
            device=device,
            store=False,
            verbose=verbose,
        )
        if not df.empty:
            rows.append(df)
    out = _concat_or_empty(rows, _empty_loops())
    if store:
        cdata.results[result_key] = out
    return out


def call_compartments_multi(
    cdata,
    *,
    chroms: Sequence[str] | None = None,
    params=None,
    device: str = "auto",
    result_key: str = "compartments",
    store: bool = True,
    verbose: bool = False,
) -> pd.DataFrame:
    """Call compartments on multiple chromosomes and store one merged table."""
    from uchrom.strc.comp import call_compartments_axes_pc

    rows = []
    for chrom in _chroms(cdata, chroms):
        df = call_compartments_axes_pc(
            cdata,
            chrom=chrom,
            params=params,
            device=device,
            store=False,
            verbose=verbose,
        )
        if not df.empty:
            rows.append(df)
    out = _concat_or_empty(rows, _empty_compartments())
    if store:
        cdata.results[result_key] = out
    return out


def call_structures_multi(
    cdata,
    *,
    structures: Sequence[str] = ("tads", "loops", "compartments"),
    chroms: Sequence[str] | None = None,
    device: str = "auto",
    store: bool = True,
    verbose: bool = False,
) -> dict[str, pd.DataFrame]:
    """Run selected structural callers on multiple chromosomes."""
    selected = {str(name) for name in structures}
    unknown = selected - {"tads", "loops", "compartments"}
    if unknown:
        raise ValueError(f"unknown structural callers: {sorted(unknown)}")
    out: dict[str, pd.DataFrame] = {}
    if "tads" in selected:
        out["tads"] = call_tads_multi(cdata, chroms=chroms, device=device, store=store, verbose=verbose)
    if "loops" in selected:
        out["loops"] = call_loops_multi(cdata, chroms=chroms, device=device, store=store, verbose=verbose)
    if "compartments" in selected:
        out["compartments"] = call_compartments_multi(
            cdata,
            chroms=chroms,
            device=device,
            store=store,
            verbose=verbose,
        )
    return out


def compute_structural_features(
    intervals: pd.DataFrame,
    *,
    tads: pd.DataFrame | None = None,
    loops: pd.DataFrame | None = None,
    compartments: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Compute spot-bin structural features from interval result tables."""
    out = _normalise_intervals(intervals)

    if tads is not None:
        distance, inside = _tad_features(out, tads)
        out["distance_to_tad_boundary"] = distance
        out["inside_tad"] = inside
    if loops is not None:
        overlap, count, distance = _loop_anchor_features(out, loops)
        out["loop_anchor_overlap"] = overlap
        out["loop_anchor_count"] = count
        out["distance_to_loop_anchor"] = distance
    if compartments is not None:
        labels, pc2 = _compartment_features(out, compartments)
        out["compartment_label"] = labels
        out["compartment_pc2"] = pc2
    return out


def add_structural_features(
    cdata,
    *,
    tads: pd.DataFrame | None = None,
    loops: pd.DataFrame | None = None,
    compartments: pd.DataFrame | None = None,
    tads_key: str = "tads",
    loops_key: str = "loops",
    compartments_key: str = "compartments",
    prefix: str = "strc",
    result_key: str = "bin_features",
    project: bool = True,
    store: bool = True,
    overwrite: bool = False,
) -> pd.DataFrame:
    """Project TAD/loop/compartment outputs into ``cdata.tracks``."""
    tads = _result_or_arg(cdata, tads, tads_key)
    loops = _result_or_arg(cdata, loops, loops_key)
    compartments = _result_or_arg(cdata, compartments, compartments_key)
    if tads is None and loops is None and compartments is None:
        raise ValueError("no structural result tables were provided or found in cdata.results")

    table = compute_structural_features(
        unique_spot_intervals(cdata),
        tads=tads,
        loops=loops,
        compartments=compartments,
    )
    value_columns = [c for c in STRUCTURAL_FEATURE_COLUMNS if c in table.columns]

    if store:
        cdata.results[result_key] = _merge_feature_table(
            cdata.results.get(result_key),
            table,
            value_columns=value_columns,
            overwrite=overwrite,
        )
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
        "feature_group": "structure",
        "features": [_prefixed_name(c, prefix) for c in value_columns],
        "result_key": result_key if store else None,
        "source_results": [
            key for key, value in (
                (tads_key, tads),
                (loops_key, loops),
                (compartments_key, compartments),
            )
            if value is not None
        ],
        "coordinate_convention": "0-based half-open",
        "parameters": {
            "projected_to_tracks": bool(project),
            "track_prefix": prefix,
        },
        "created_by": "uchrom.strc.enrichment",
    })
    return table


def _tad_features(intervals: pd.DataFrame, tads: pd.DataFrame):
    if tads.empty:
        return np.full(len(intervals), np.nan), np.zeros(len(intervals), dtype=float)
    tads = _normalise_intervals(tads)
    distances = np.full(len(intervals), np.nan, dtype=float)
    inside = np.zeros(len(intervals), dtype=float)
    for chrom, idx in intervals.groupby("chrom").groups.items():
        idx_array = idx.to_numpy()
        sub = tads[tads["chrom"] == str(chrom)]
        if sub.empty:
            continue
        boundaries = np.unique(np.concatenate([sub["start"].to_numpy(), sub["end"].to_numpy()]))
        mids = _midpoints(intervals.loc[idx_array])
        distances[idx_array] = np.min(np.abs(mids[:, None] - boundaries[None, :]), axis=1)
        start = intervals.loc[idx_array, "start"].to_numpy()
        end = intervals.loc[idx_array, "end"].to_numpy()
        tad_start = sub["start"].to_numpy()
        tad_end = sub["end"].to_numpy()
        overlaps = (np.minimum(end[:, None], tad_end[None, :]) - np.maximum(start[:, None], tad_start[None, :])) > 0
        inside[idx_array] = overlaps.any(axis=1).astype(float)
    return distances, inside


def _loop_anchor_features(intervals: pd.DataFrame, loops: pd.DataFrame):
    anchors = _loop_anchor_table(loops)
    overlap = np.zeros(len(intervals), dtype=float)
    count = np.zeros(len(intervals), dtype=float)
    distance = np.full(len(intervals), np.nan, dtype=float)
    if anchors.empty:
        return overlap, count, distance
    for chrom, idx in intervals.groupby("chrom").groups.items():
        idx_array = idx.to_numpy()
        sub = anchors[anchors["chrom"] == str(chrom)]
        if sub.empty:
            continue
        start = intervals.loc[idx_array, "start"].to_numpy()
        end = intervals.loc[idx_array, "end"].to_numpy()
        anchor_start = sub["start"].to_numpy()
        anchor_end = sub["end"].to_numpy()
        bp = np.maximum(0, np.minimum(end[:, None], anchor_end[None, :]) - np.maximum(start[:, None], anchor_start[None, :]))
        hit = bp > 0
        count[idx_array] = hit.sum(axis=1).astype(float)
        overlap[idx_array] = hit.any(axis=1).astype(float)
        mids = _midpoints(intervals.loc[idx_array])
        anchor_mids = _midpoints(sub)
        distance[idx_array] = np.min(np.abs(mids[:, None] - anchor_mids[None, :]), axis=1)
    return overlap, count, distance


def _compartment_features(intervals: pd.DataFrame, compartments: pd.DataFrame):
    compartments = _normalise_intervals(compartments)
    labels = np.full(len(intervals), "", dtype=object)
    pc2 = np.full(len(intervals), np.nan, dtype=float)
    if compartments.empty:
        return labels, pc2
    for chrom, idx in intervals.groupby("chrom").groups.items():
        idx_array = idx.to_numpy()
        sub = compartments[compartments["chrom"] == str(chrom)].reset_index(drop=True)
        if sub.empty:
            continue
        start = intervals.loc[idx_array, "start"].to_numpy()
        end = intervals.loc[idx_array, "end"].to_numpy()
        comp_start = sub["start"].to_numpy()
        comp_end = sub["end"].to_numpy()
        overlaps = np.maximum(0, np.minimum(end[:, None], comp_end[None, :]) - np.maximum(start[:, None], comp_start[None, :]))
        best = np.argmax(overlaps, axis=1)
        ok = overlaps[np.arange(len(idx_array)), best] > 0
        if "compartment" in sub.columns:
            comp_labels = sub["compartment"].astype(str).to_numpy()
            labels[idx_array[ok]] = comp_labels[best[ok]]
        if "pc2" in sub.columns:
            comp_pc2 = sub["pc2"].to_numpy(dtype=float)
            pc2[idx_array[ok]] = comp_pc2[best[ok]]
    return labels, pc2


def _loop_anchor_table(loops: pd.DataFrame) -> pd.DataFrame:
    if loops is None or loops.empty:
        return pd.DataFrame(columns=list(INTERVAL_COLUMNS))
    required = {"chrom1", "start1", "end1", "chrom2", "start2", "end2"}
    missing = required - set(loops.columns)
    if missing:
        raise ValueError(f"loop table missing columns: {sorted(missing)}")
    left = loops.rename(columns={"chrom1": "chrom", "start1": "start", "end1": "end"})[
        list(INTERVAL_COLUMNS)
    ]
    right = loops.rename(columns={"chrom2": "chrom", "start2": "start", "end2": "end"})[
        list(INTERVAL_COLUMNS)
    ]
    anchors = pd.concat([left, right], ignore_index=True)
    return _normalise_intervals(anchors).drop_duplicates(list(INTERVAL_COLUMNS)).reset_index(drop=True)


def _normalise_intervals(frame: pd.DataFrame) -> pd.DataFrame:
    missing = [c for c in INTERVAL_COLUMNS if c not in frame.columns]
    if missing:
        raise ValueError(f"interval table missing columns: {missing}")
    out = frame.loc[:, list(frame.columns)].copy()
    out["chrom"] = out["chrom"].astype(str)
    out["start"] = out["start"].astype(np.int64)
    out["end"] = out["end"].astype(np.int64)
    bad = out["end"] <= out["start"]
    if bad.any():
        rows = out.loc[bad, list(INTERVAL_COLUMNS)].head(3).to_dict("records")
        raise ValueError(f"intervals must satisfy end > start: {rows}")
    return out


def _merge_feature_table(existing, table: pd.DataFrame, *, value_columns: Sequence[str], overwrite: bool) -> pd.DataFrame:
    if existing is None:
        return table[list(INTERVAL_COLUMNS) + list(value_columns)].copy()
    out = existing.copy()
    conflicts = [c for c in value_columns if c in out.columns]
    if conflicts and not overwrite:
        raise ValueError(f"result table already contains columns: {conflicts}")
    if conflicts:
        out = out.drop(columns=conflicts)
    return out.merge(table[list(INTERVAL_COLUMNS) + list(value_columns)], on=list(INTERVAL_COLUMNS), how="outer")


def _result_or_arg(cdata, value, key: str):
    if value is not None:
        return value
    if key not in cdata.results:
        return None
    found = cdata.results.get(key)
    return found if isinstance(found, pd.DataFrame) else None


def _chroms(cdata, chroms: Sequence[str] | None) -> list[str]:
    return [str(c) for c in (chroms if chroms is not None else cdata.chroms)]


def _concat_or_empty(frames: list[pd.DataFrame], empty: pd.DataFrame) -> pd.DataFrame:
    if not frames:
        return empty
    return pd.concat(frames, ignore_index=True)


def _midpoints(frame: pd.DataFrame) -> np.ndarray:
    return (frame["start"].to_numpy(dtype=float) + frame["end"].to_numpy(dtype=float)) * 0.5


def _prefixed_name(name: str, prefix: str | None) -> str:
    if not prefix:
        return str(name)
    return f"{str(prefix).rstrip('.')}.{name}"


def _empty_tads() -> pd.DataFrame:
    return pd.DataFrame(columns=["chrom", "start", "end", "level", "score", "pval", "fdr"])


def _empty_loops() -> pd.DataFrame:
    return pd.DataFrame(columns=[
        "chrom1", "start1", "end1", "chrom2", "start2", "end2",
        "score", "pval", "fdr", "cluster_size", "contact_freq", "summit_i", "summit_j",
    ])


def _empty_compartments() -> pd.DataFrame:
    return pd.DataFrame(columns=["chrom", "start", "end", "bin_index", "cluster", "compartment", "pc2"])


__all__ = [
    "STRUCTURAL_FEATURE_COLUMNS",
    "add_structural_features",
    "call_compartments_multi",
    "call_loops_multi",
    "call_structures_multi",
    "call_tads_multi",
    "compute_structural_features",
]
