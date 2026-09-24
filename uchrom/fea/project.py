"""Projection helpers for genomic interval features.

The functions in this module are deliberately independent of
``uchrom_discovery``.  They provide a small shared layer for mapping
canonical interval-level feature tables onto the spot axis of a
``ChromData`` object.
"""

from __future__ import annotations

from typing import Iterable, Sequence

import numpy as np
import pandas as pd


INTERVAL_COLUMNS = ("chrom", "start", "end")


def unique_spot_intervals(cdata_or_spots) -> pd.DataFrame:
    """Return unique ``chrom/start/end`` intervals from a spot table.

    The first occurrence order is preserved.  ``cdata_or_spots`` may be a
    ``ChromData``-like object with a ``spots`` attribute or a DataFrame.
    """
    spots = _spots_dataframe(cdata_or_spots)
    intervals = _normalise_interval_frame(spots, columns=INTERVAL_COLUMNS)
    return intervals.drop_duplicates(list(INTERVAL_COLUMNS), keep="first").reset_index(drop=True)


def project_interval_features_to_spots(
    cdata_or_spots,
    features: pd.DataFrame,
    *,
    prefix: str | None = None,
    value_columns: Sequence[str] | None = None,
    into: pd.DataFrame | None = None,
    overwrite: bool = False,
) -> pd.DataFrame:
    """Project interval-level features onto the spot axis.

    Parameters
    ----------
    cdata_or_spots
        A ``ChromData``-like object or a spot DataFrame with ``chrom``,
        ``start``, and ``end`` columns.
    features
        DataFrame with one row per interval and feature columns.
    prefix
        Optional namespace prefix for projected columns.  For example,
        ``prefix="seq"`` maps ``gc_fraction`` to ``seq.gc_fraction``.
    value_columns
        Feature columns to project.  By default all non-interval columns are
        used.
    into
        Optional existing spot-aligned DataFrame to extend.
    overwrite
        If False, raise when projected columns already exist in ``into``.

    Returns
    -------
    DataFrame
        A spot-aligned DataFrame containing the existing ``into`` columns plus
        projected feature columns.
    """
    spots = _spots_dataframe(cdata_or_spots)
    if features is None:
        raise ValueError("features must be a DataFrame")
    if not isinstance(features, pd.DataFrame):
        raise TypeError("features must be a pandas DataFrame")

    spot_keys = _normalise_interval_frame(spots, columns=INTERVAL_COLUMNS)
    feature_keys = _normalise_interval_frame(features, columns=INTERVAL_COLUMNS)

    if value_columns is None:
        value_columns = [c for c in features.columns if c not in INTERVAL_COLUMNS]
    value_columns = list(value_columns)
    if not value_columns:
        raise ValueError("no feature columns to project")
    missing_values = [c for c in value_columns if c not in features.columns]
    if missing_values:
        raise ValueError(f"features missing value columns: {missing_values}")

    duplicated = feature_keys.duplicated(list(INTERVAL_COLUMNS), keep=False)
    if duplicated.any():
        dup = feature_keys.loc[duplicated, list(INTERVAL_COLUMNS)].head(3).to_dict("records")
        raise ValueError(f"features contain duplicate intervals: {dup}")

    table = pd.concat(
        [
            feature_keys.reset_index(drop=True),
            features[value_columns].reset_index(drop=True),
        ],
        axis=1,
    )
    projected = spot_keys.merge(table, on=list(INTERVAL_COLUMNS), how="left", sort=False)

    out = _empty_or_copy_tracks(into, len(spots))
    for col in value_columns:
        out_col = _prefixed_name(col, prefix)
        if out_col in out.columns and not overwrite:
            raise ValueError(f"projected column already exists: {out_col}")
        out[out_col] = projected[col].to_numpy()
    return out


def _spots_dataframe(cdata_or_spots) -> pd.DataFrame:
    if isinstance(cdata_or_spots, pd.DataFrame):
        return cdata_or_spots
    spots = getattr(cdata_or_spots, "spots", None)
    if isinstance(spots, pd.DataFrame):
        return spots
    raise TypeError("expected a ChromData-like object or a pandas DataFrame")


def _normalise_interval_frame(
    frame: pd.DataFrame,
    *,
    columns: Iterable[str],
) -> pd.DataFrame:
    columns = tuple(columns)
    missing = [c for c in columns if c not in frame.columns]
    if missing:
        raise ValueError(f"interval table missing columns: {missing}")
    out = frame.loc[:, columns].copy()
    out["chrom"] = out["chrom"].astype(str)
    out["start"] = out["start"].astype(np.int64)
    out["end"] = out["end"].astype(np.int64)
    bad = out["end"] <= out["start"]
    if bad.any():
        rows = out.loc[bad, list(columns)].head(3).to_dict("records")
        raise ValueError(f"intervals must satisfy end > start: {rows}")
    return out


def _empty_or_copy_tracks(into: pd.DataFrame | None, n_spots: int) -> pd.DataFrame:
    if into is None:
        return pd.DataFrame(index=pd.RangeIndex(n_spots))
    if len(into) != n_spots:
        raise ValueError(f"into rows ({len(into)}) != n_spots ({n_spots})")
    return into.copy()


def _prefixed_name(name: str, prefix: str | None) -> str:
    if not prefix:
        return str(name)
    prefix = str(prefix).rstrip(".")
    name = str(name)
    if name.startswith(prefix + "."):
        return name
    return f"{prefix}.{name}"


__all__ = [
    "INTERVAL_COLUMNS",
    "project_interval_features_to_spots",
    "unique_spot_intervals",
]
