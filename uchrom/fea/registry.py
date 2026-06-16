"""Feature registry helpers for ``ChromData.uns``."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import hashlib
from pathlib import Path
from typing import Any, Mapping


def append_feature_registry_entry(
    cdata,
    entry: Mapping[str, Any],
    *,
    key: str = "feature_registry",
) -> dict[str, Any]:
    """Append a provenance record to ``cdata.uns[key]``.

    The registry is stored as a list of JSON-like dicts so it round-trips
    through the existing ``uns`` serializer.
    """
    record = deepcopy(dict(entry))
    record.setdefault(
        "created_utc",
        datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
    )
    try:
        from uchrom import __version__ as uchrom_version
    except Exception:
        uchrom_version = "unknown"
    record.setdefault("uchrom_version", uchrom_version)
    if "features" in record and "n_features" not in record:
        try:
            record["n_features"] = len(record.get("features") or [])
        except Exception:
            pass
    if record.get("hash_source") and record.get("source_path") and "source_sha256" not in record:
        source_path = Path(str(record["source_path"]))
        if source_path.exists() and source_path.is_file():
            record["source_sha256"] = file_sha256(source_path)
    if record.get("hash_source") and record.get("source_paths") and "source_sha256s" not in record:
        hashes = {}
        for raw in record.get("source_paths") or []:
            source_path = Path(str(raw))
            if source_path.exists() and source_path.is_file():
                hashes[str(raw)] = file_sha256(source_path)
        if hashes:
            record["source_sha256s"] = hashes
    record.pop("hash_source", None)

    existing = cdata.uns.get(key, [])
    if existing is None:
        records = []
    elif isinstance(existing, list):
        records = list(existing)
    elif isinstance(existing, tuple):
        records = list(existing)
    else:
        records = [existing]
    records.append(record)
    cdata.uns[key] = records
    return record


def file_sha256(path: str | Path, *, chunk_size: int = 1024 * 1024) -> str:
    """Return the SHA-256 digest for a local source file."""
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def table_provenance(table, *, value_columns=None) -> dict[str, Any]:
    """Small JSON-friendly summary for an enrichment output table."""
    value_columns = list(value_columns or [])
    out = {"n_rows": int(len(table)), "value_columns": value_columns}
    finite_counts = {}
    for column in value_columns:
        if column not in table:
            continue
        try:
            finite_counts[str(column)] = int(table[column].notna().sum())
        except Exception:
            pass
    if finite_counts:
        out["non_null_counts"] = finite_counts
    return out


__all__ = ["append_feature_registry_entry", "file_sha256", "table_provenance"]
