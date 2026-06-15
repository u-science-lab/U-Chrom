"""Feature registry helpers for ``ChromData.uns``."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
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


__all__ = ["append_feature_registry_entry"]
