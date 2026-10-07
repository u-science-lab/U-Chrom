"""Sequence-derived genomic interval features."""

from __future__ import annotations

import gzip
import re
from pathlib import Path
from typing import Iterable, Sequence

import numpy as np
import pandas as pd

from .project import INTERVAL_COLUMNS, project_interval_features_to_bins, unique_spot_intervals
from .registry import append_feature_registry_entry, table_provenance


DEFAULT_SEQUENCE_FEATURES = (
    "gc_fraction",
    "cpg_density",
    "n_fraction",
    "g4_motif_count",
    "g4_motif_density",
)
DEFAULT_G4_PATTERN = r"G{3,}[ACGTN]{1,7}G{3,}[ACGTN]{1,7}G{3,}[ACGTN]{1,7}G{3,}"


def compute_sequence_features(
    intervals: pd.DataFrame,
    fasta: str | Path,
    *,
    features: Sequence[str] | None = None,
    g4_pattern: str = DEFAULT_G4_PATTERN,
    missing: str = "raise",
) -> pd.DataFrame:
    """Compute FASTA-derived features for genomic intervals.

    Parameters
    ----------
    intervals
        DataFrame with ``chrom``, ``start``, and ``end`` columns.
    fasta
        FASTA file path. Plain text and ``.gz`` files are supported.
    features
        Sequence feature names. Defaults to ``DEFAULT_SEQUENCE_FEATURES``.
    g4_pattern
        Regular expression used for G-quadruplex motif counting.
    missing
        ``"raise"`` to reject intervals whose chromosomes are absent from the
        FASTA, or ``"ignore"`` to leave their feature values as NaN.

    Returns
    -------
    DataFrame
        Interval columns plus requested feature columns, preserving the input
        row order.
    """
    if missing not in {"raise", "ignore"}:
        raise ValueError("missing must be 'raise' or 'ignore'")
    requested = _validate_features(features)
    interval_table = _normalise_intervals(intervals)
    out = interval_table.copy()
    for feature in requested:
        out[feature] = np.nan

    groups = {chrom: idx.to_numpy() for chrom, idx in interval_table.groupby("chrom").groups.items()}
    seen: set[str] = set()
    g4_regex = re.compile(g4_pattern)

    for chrom, seq in _iter_fasta_records(fasta):
        if chrom not in groups:
            continue
        seen.add(chrom)
        indices = groups[chrom]
        for i in indices:
            start = int(interval_table.at[i, "start"])
            end = int(interval_table.at[i, "end"])
            if end > len(seq):
                raise ValueError(
                    f"interval {chrom}:{start}-{end} extends past FASTA sequence length {len(seq)}"
                )
            values = _compute_one_sequence(seq[start:end], requested, g4_regex)
            for feature, value in values.items():
                out.at[i, feature] = value

    missing_chroms = sorted(set(groups) - seen)
    if missing_chroms and missing == "raise":
        raise ValueError(f"FASTA missing chromosomes: {missing_chroms}")
    return out


def add_sequence_features(
    cdata,
    fasta: str | Path,
    *,
    features: Sequence[str] | None = None,
    prefix: str = "seq",
    result_key: str = "bin_features",
    project: bool = True,
    store: bool = True,
    overwrite: bool = False,
    hash_source: bool = False,
    g4_pattern: str = DEFAULT_G4_PATTERN,
) -> pd.DataFrame:
    """Compute sequence features for a ``ChromData`` object.

    The canonical interval table is returned.  When ``store=True`` it is also
    merged into ``cdata.results[result_key]``.  When ``project=True`` feature
    columns are projected onto ``cdata.bin_tracks`` using ``prefix``.
    """
    requested = _validate_features(features)
    intervals = unique_spot_intervals(cdata)
    table = compute_sequence_features(
        intervals,
        fasta,
        features=requested,
        g4_pattern=g4_pattern,
    )

    if store:
        existing = cdata.results.get(result_key)
        cdata.results[result_key] = _merge_feature_table(
            existing,
            table,
            value_columns=requested,
            overwrite=overwrite,
        )

    projected_columns = [_prefixed_name(col, prefix) for col in requested]
    if project:
        cdata.bin_tracks = project_interval_features_to_bins(
            cdata,
            table,
            prefix=prefix,
            value_columns=requested,
            into=cdata.bin_tracks,
            overwrite=overwrite,
        )

    entry = {
        "feature_group": "sequence",
        "features": projected_columns if project else list(requested),
        "result_key": result_key if store else None,
        "source_path": str(fasta),
        "coordinate_convention": "0-based half-open",
        "parameters": {
            "g4_pattern": g4_pattern,
            "projected_to_tracks": bool(project),
            "track_prefix": prefix,
        },
        "outputs": table_provenance(table, value_columns=requested),
        "created_by": "uchrom.fea.sequence",
        "hash_source": bool(hash_source),
    }
    genome = cdata.uns.get("genome_assembly")
    if genome is not None:
        entry["genome_assembly"] = str(genome)
    append_feature_registry_entry(cdata, entry)
    return table


def _validate_features(features: Sequence[str] | None) -> list[str]:
    requested = list(DEFAULT_SEQUENCE_FEATURES if features is None else features)
    supported = set(DEFAULT_SEQUENCE_FEATURES)
    unknown = [f for f in requested if f not in supported]
    if unknown:
        raise ValueError(f"unsupported sequence features: {unknown}")
    return requested


def _normalise_intervals(intervals: pd.DataFrame) -> pd.DataFrame:
    if not isinstance(intervals, pd.DataFrame):
        raise TypeError("intervals must be a pandas DataFrame")
    missing = [c for c in INTERVAL_COLUMNS if c not in intervals.columns]
    if missing:
        raise ValueError(f"intervals missing columns: {missing}")
    out = intervals.loc[:, INTERVAL_COLUMNS].copy()
    out["chrom"] = out["chrom"].astype(str)
    out["start"] = out["start"].astype(np.int64)
    out["end"] = out["end"].astype(np.int64)
    bad = out["end"] <= out["start"]
    if bad.any():
        rows = out.loc[bad, list(INTERVAL_COLUMNS)].head(3).to_dict("records")
        raise ValueError(f"intervals must satisfy end > start: {rows}")
    return out.reset_index(drop=True)


def _compute_one_sequence(seq: str, features: Iterable[str], g4_regex: re.Pattern[str]) -> dict[str, float]:
    seq = seq.upper()
    length = len(seq)
    if length == 0:
        return {feature: np.nan for feature in features}

    values: dict[str, float] = {}
    bases = {base: seq.count(base) for base in "ACGTN"}
    valid_acgt = bases["A"] + bases["C"] + bases["G"] + bases["T"]
    g4_count = None

    for feature in features:
        if feature == "gc_fraction":
            values[feature] = (
                (bases["G"] + bases["C"]) / valid_acgt if valid_acgt > 0 else np.nan
            )
        elif feature == "cpg_density":
            values[feature] = _count_overlapping_literal(seq, "CG") / length
        elif feature == "n_fraction":
            values[feature] = bases["N"] / length
        elif feature == "g4_motif_count":
            if g4_count is None:
                g4_count = _count_overlapping_regex(seq, g4_regex)
            values[feature] = float(g4_count)
        elif feature == "g4_motif_density":
            if g4_count is None:
                g4_count = _count_overlapping_regex(seq, g4_regex)
            values[feature] = g4_count / length
    return values


def _count_overlapping_literal(seq: str, motif: str) -> int:
    count = 0
    start = 0
    while True:
        idx = seq.find(motif, start)
        if idx < 0:
            return count
        count += 1
        start = idx + 1


def _count_overlapping_regex(seq: str, regex: re.Pattern[str]) -> int:
    return sum(1 for _ in re.finditer(f"(?=({regex.pattern}))", seq))


def _iter_fasta_records(path: str | Path):
    name = None
    parts: list[str] = []
    with _open_text(path) as handle:
        for raw in handle:
            line = raw.strip()
            if not line:
                continue
            if line.startswith(">"):
                if name is not None:
                    yield name, "".join(parts).upper()
                name = line[1:].split()[0]
                parts = []
            else:
                parts.append(line)
    if name is not None:
        yield name, "".join(parts).upper()


def _open_text(path: str | Path):
    path = Path(path)
    if path.suffix == ".gz":
        return gzip.open(path, "rt")
    return path.open("rt")


def _merge_feature_table(
    existing,
    table: pd.DataFrame,
    *,
    value_columns: Sequence[str],
    overwrite: bool,
) -> pd.DataFrame:
    if existing is None:
        return table.copy()
    if not isinstance(existing, pd.DataFrame):
        raise TypeError("existing result table must be a pandas DataFrame")
    missing = [c for c in INTERVAL_COLUMNS if c not in existing.columns]
    if missing:
        raise ValueError(f"existing result table missing interval columns: {missing}")

    out = existing.copy()
    conflicts = [c for c in value_columns if c in out.columns]
    if conflicts and not overwrite:
        raise ValueError(f"result table already contains columns: {conflicts}")
    if conflicts and overwrite:
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


__all__ = [
    "DEFAULT_G4_PATTERN",
    "DEFAULT_SEQUENCE_FEATURES",
    "add_sequence_features",
    "compute_sequence_features",
]
