"""Genome annotation-derived interval features."""

from __future__ import annotations

import gzip
from pathlib import Path
from typing import Sequence

import numpy as np
import pandas as pd

from .project import INTERVAL_COLUMNS, project_interval_features_to_spots, unique_spot_intervals
from .registry import append_feature_registry_entry


DEFAULT_ANNOTATION_FEATURES = (
    "gene_body_overlap_bp",
    "gene_body_overlap_fraction",
    "gene_count",
    "exon_overlap_bp",
    "exon_overlap_fraction",
    "promoter_overlap_bp",
    "promoter_overlap_fraction",
    "nearest_tss_distance",
)


def read_gtf(path: str | Path) -> pd.DataFrame:
    """Read a GTF/GFF-like file into a normalized annotation table.

    Coordinates are converted from 1-based inclusive GTF convention to
    0-based half-open intervals.
    """
    rows = []
    with _open_text(path) as handle:
        for raw in handle:
            if not raw.strip() or raw.startswith("#"):
                continue
            parts = raw.rstrip("\n").split("\t")
            if len(parts) < 9:
                continue
            attrs = _parse_gtf_attributes(parts[8])
            rows.append({
                "chrom": parts[0],
                "source": parts[1],
                "feature": parts[2],
                "start": int(parts[3]) - 1,
                "end": int(parts[4]),
                "score": parts[5],
                "strand": parts[6],
                "frame": parts[7],
                "attribute": parts[8],
                "gene_id": attrs.get("gene_id"),
                "gene_name": attrs.get("gene_name") or attrs.get("Name"),
                "gene_biotype": (
                    attrs.get("gene_biotype")
                    or attrs.get("gene_type")
                    or attrs.get("transcript_biotype")
                ),
            })
    return pd.DataFrame(rows)


def compute_annotation_features(
    intervals: pd.DataFrame,
    gtf: str | Path | pd.DataFrame,
    *,
    features: Sequence[str] | None = None,
    promoter_window: tuple[int, int] = (-2000, 500),
    gene_feature: str = "gene",
    exon_feature: str = "exon",
) -> pd.DataFrame:
    """Compute GTF-derived features for genomic intervals.

    The returned table preserves the input interval order and uses 0-based
    half-open coordinates.
    """
    requested = _validate_features(features)
    interval_table = _normalise_intervals(intervals)
    annotations = read_gtf(gtf) if not isinstance(gtf, pd.DataFrame) else gtf.copy()
    annotations = _normalise_annotations(annotations)

    out = interval_table.copy()
    for feature in requested:
        out[feature] = np.nan

    genes = annotations[annotations["feature"].astype(str) == str(gene_feature)].copy()
    exons = annotations[annotations["feature"].astype(str) == str(exon_feature)].copy()
    promoters = _promoter_table(genes, promoter_window)

    for chrom, idx in interval_table.groupby("chrom").groups.items():
        idx_array = idx.to_numpy()
        chrom_intervals = interval_table.loc[idx_array]
        chrom_genes = genes[genes["chrom"].astype(str) == str(chrom)]
        chrom_exons = exons[exons["chrom"].astype(str) == str(chrom)]
        chrom_promoters = promoters[promoters["chrom"].astype(str) == str(chrom)]

        gene_overlap_bp, gene_count = _overlap_bp_and_count(chrom_intervals, chrom_genes)
        exon_overlap_bp, _ = _overlap_bp_and_count(chrom_intervals, chrom_exons)
        promoter_overlap_bp, _ = _overlap_bp_and_count(chrom_intervals, chrom_promoters)
        nearest_tss = _nearest_tss_distance(chrom_intervals, chrom_genes)
        lengths = (chrom_intervals["end"].to_numpy() - chrom_intervals["start"].to_numpy()).astype(float)

        values = {
            "gene_body_overlap_bp": gene_overlap_bp,
            "gene_body_overlap_fraction": gene_overlap_bp / lengths,
            "gene_count": gene_count,
            "exon_overlap_bp": exon_overlap_bp,
            "exon_overlap_fraction": exon_overlap_bp / lengths,
            "promoter_overlap_bp": promoter_overlap_bp,
            "promoter_overlap_fraction": promoter_overlap_bp / lengths,
            "nearest_tss_distance": nearest_tss,
        }
        for feature in requested:
            out.loc[idx_array, feature] = values[feature]

    return out


def add_annotation_features(
    cdata,
    gtf: str | Path | pd.DataFrame,
    *,
    features: Sequence[str] | None = None,
    prefix: str = "gtf",
    result_key: str = "bin_features",
    project: bool = True,
    store: bool = True,
    overwrite: bool = False,
    promoter_window: tuple[int, int] = (-2000, 500),
) -> pd.DataFrame:
    """Compute annotation features for a ``ChromData`` object."""
    requested = _validate_features(features)
    intervals = unique_spot_intervals(cdata)
    table = compute_annotation_features(
        intervals,
        gtf,
        features=requested,
        promoter_window=promoter_window,
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
        cdata.tracks = project_interval_features_to_spots(
            cdata,
            table,
            prefix=prefix,
            value_columns=requested,
            into=cdata.tracks,
            overwrite=overwrite,
        )

    entry = {
        "feature_group": "annotation",
        "features": projected_columns if project else list(requested),
        "result_key": result_key if store else None,
        "source_path": str(gtf) if not isinstance(gtf, pd.DataFrame) else None,
        "coordinate_convention": "0-based half-open",
        "parameters": {
            "promoter_window": list(promoter_window),
            "projected_to_tracks": bool(project),
            "track_prefix": prefix,
        },
        "created_by": "uchrom.fea.annotation",
    }
    genome = cdata.uns.get("genome_assembly")
    if genome is not None:
        entry["genome_assembly"] = str(genome)
    append_feature_registry_entry(cdata, entry)
    return table


def _validate_features(features: Sequence[str] | None) -> list[str]:
    requested = list(DEFAULT_ANNOTATION_FEATURES if features is None else features)
    supported = set(DEFAULT_ANNOTATION_FEATURES)
    unknown = [f for f in requested if f not in supported]
    if unknown:
        raise ValueError(f"unsupported annotation features: {unknown}")
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


def _normalise_annotations(annotations: pd.DataFrame) -> pd.DataFrame:
    missing = [c for c in ("chrom", "feature", "start", "end") if c not in annotations.columns]
    if missing:
        raise ValueError(f"annotation table missing columns: {missing}")
    out = annotations.copy()
    out["chrom"] = out["chrom"].astype(str)
    out["feature"] = out["feature"].astype(str)
    out["start"] = out["start"].astype(np.int64)
    out["end"] = out["end"].astype(np.int64)
    if "strand" not in out:
        out["strand"] = "."
    out["strand"] = out["strand"].astype(str)
    bad = out["end"] <= out["start"]
    if bad.any():
        rows = out.loc[bad, ["chrom", "start", "end"]].head(3).to_dict("records")
        raise ValueError(f"annotations must satisfy end > start: {rows}")
    return out


def _overlap_bp_and_count(intervals: pd.DataFrame, annotations: pd.DataFrame):
    overlap_bp = np.zeros(len(intervals), dtype=float)
    count = np.zeros(len(intervals), dtype=float)
    if annotations.empty:
        return overlap_bp, count
    ann_start = annotations["start"].to_numpy()
    ann_end = annotations["end"].to_numpy()
    for pos, (_, row) in enumerate(intervals.iterrows()):
        start = int(row["start"])
        end = int(row["end"])
        overlaps = np.maximum(0, np.minimum(end, ann_end) - np.maximum(start, ann_start))
        hit = overlaps > 0
        if hit.any():
            starts = np.maximum(start, ann_start[hit])
            ends = np.minimum(end, ann_end[hit])
            overlap_bp[pos] = float(_covered_bp(starts, ends))
        count[pos] = float(hit.sum())
    return overlap_bp, count


def _covered_bp(starts: np.ndarray, ends: np.ndarray) -> int:
    order = np.argsort(starts, kind="mergesort")
    merged = 0
    cur_start = int(starts[order[0]])
    cur_end = int(ends[order[0]])
    for idx in order[1:]:
        start = int(starts[idx])
        end = int(ends[idx])
        if start <= cur_end:
            cur_end = max(cur_end, end)
        else:
            merged += cur_end - cur_start
            cur_start, cur_end = start, end
    merged += cur_end - cur_start
    return merged


def _nearest_tss_distance(intervals: pd.DataFrame, genes: pd.DataFrame) -> np.ndarray:
    if genes.empty:
        return np.full(len(intervals), np.nan, dtype=float)
    tss = _gene_tss(genes)
    distances = np.zeros(len(intervals), dtype=float)
    for pos, (_, row) in enumerate(intervals.iterrows()):
        start = int(row["start"])
        end = int(row["end"])
        left = np.maximum(0, start - tss)
        right = np.maximum(0, tss - end)
        distances[pos] = float(np.min(left + right))
    return distances


def _promoter_table(genes: pd.DataFrame, promoter_window: tuple[int, int]) -> pd.DataFrame:
    if genes.empty:
        return genes.loc[:, ["chrom", "start", "end", "strand"]].copy()
    upstream, downstream = promoter_window
    rows = []
    for _, row in genes.iterrows():
        tss = int(row["start"]) if str(row.get("strand", "+")) != "-" else int(row["end"])
        if str(row.get("strand", "+")) == "-":
            start = tss - downstream
            end = tss - upstream
        else:
            start = tss + upstream
            end = tss + downstream
        rows.append({
            "chrom": row["chrom"],
            "start": max(0, int(start)),
            "end": max(0, int(end)),
            "strand": row.get("strand", "."),
        })
    out = pd.DataFrame(rows)
    return out[out["end"] > out["start"]].reset_index(drop=True)


def _gene_tss(genes: pd.DataFrame) -> np.ndarray:
    starts = genes["start"].to_numpy(dtype=np.int64)
    ends = genes["end"].to_numpy(dtype=np.int64)
    strand = genes["strand"].astype(str).to_numpy()
    return np.where(strand == "-", ends, starts)


def _parse_gtf_attributes(raw: str) -> dict[str, str]:
    attrs: dict[str, str] = {}
    for part in raw.strip().strip(";").split(";"):
        part = part.strip()
        if not part:
            continue
        if "=" in part and " " not in part.split("=", 1)[0]:
            key, value = part.split("=", 1)
        elif " " in part:
            key, value = part.split(" ", 1)
        else:
            continue
        attrs[key.strip()] = value.strip().strip('"')
    return attrs


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
    "DEFAULT_ANNOTATION_FEATURES",
    "add_annotation_features",
    "compute_annotation_features",
    "read_gtf",
]
