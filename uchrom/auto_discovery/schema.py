"""Agent-readable discovery schema for :class:`uchrom.core.ChromData`.

The schema is intentionally stored inside ``cd.uns`` as a JSON payload so
it round-trips through ``.h5cd`` without requiring a new HDF5 layout.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Mapping

import numpy as np
import pandas as pd


DISCOVERY_SCHEMA_KEY = "auto_discovery_schema"
DISCOVERY_SCHEMA_VERSION = "0.1"
DISCOVERY_SCHEMA_FORMAT = "uchrom.auto_discovery.schema+json"


def build_discovery_schema(
    cdata,
    *,
    dataset_name: str | None = None,
    include_linked_adata: bool = True,
    max_catalog_items: int = 500,
) -> dict[str, Any]:
    """Build an agent-readable schema from a ``ChromData`` object.

    The returned dict is JSON-serializable and can be persisted via
    :func:`pack_schema` under ``cd.uns['auto_discovery_schema']``.
    """
    fields = {
        "coords": {
            "axis": "spot",
            "shape": _shape(cdata.coords),
            "dtype": str(getattr(cdata.coords, "dtype", "")),
            "description": "Spot-level 3D coordinates.",
        },
        "spots": _dataframe_field(cdata.spots, axis="spot"),
        "tracks": _dataframe_field(cdata.tracks, axis="spot"),
        "cells": _dataframe_field(cdata.cells, axis="cell"),
        "traces": _dataframe_field(cdata.traces, axis="trace"),
        "cellm": _array_mapping_field(cdata.cellm, axis="cell"),
        "layers": _array_mapping_field(cdata.layers, axis="spot"),
        "results": {"keys": sorted(map(str, cdata.results.keys()))},
        "uns": {
            "keys": sorted(k for k in map(str, cdata.uns.keys()) if k != DISCOVERY_SCHEMA_KEY)
        },
    }

    chroms = _as_str_list(getattr(cdata, "chroms", []))
    cell_type_counts = _cell_type_counts(cdata)
    linked = _linked_anndata_field(
        cdata,
        include_linked_adata=include_linked_adata,
        max_catalog_items=max_catalog_items,
    )

    tracks = _columns(cdata.tracks)
    genes = linked.get("var_names", {"n": 0, "values": [], "truncated": False, "sha1": ""})
    schema = {
        "schema_version": DISCOVERY_SCHEMA_VERSION,
        "schema_type": "uchrom_multiomics_auto_discovery",
        "created_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "dataset": {
            "name": dataset_name
            or str(cdata.uns.get("source") or cdata.uns.get("dataset") or "ChromData"),
            "genome_assembly": _json_scalar(cdata.uns.get("genome_assembly")),
            "xyz_unit": _json_scalar(cdata.uns.get("xyz_unit")),
        },
        "summary": {
            "n_spots": int(cdata.n_spots),
            "n_traces": int(cdata.n_traces),
            "n_cells": int(cdata.n_cells),
            "n_chroms": len(chroms),
            "n_tracks": len(tracks),
        },
        "axes": {
            "spot": "Rows of coords/spots/tracks; one observed genomic bin in one trace.",
            "trace": "A chromatin fiber or allele-specific chromosome trace.",
            "cell": "Cell-level metadata, embeddings, and linked RNA observations.",
            "gene": "Variables in linked_adata when RNA expression is available.",
            "marker": "Columns in tracks when per-spot IF/RNA marker scores are available.",
        },
        "modalities": {
            "chromatin_tracing": {
                "present": True,
                "fields": ["coords", "spots", "traces"],
                "operations": [
                    "chromosome_subset",
                    "cell_subset",
                    "trace_subset",
                    "pairwise_3d_distance",
                    "intra_chromatin_distance",
                    "inter_chromatin_distance",
                ],
            },
            "if_tracks": {
                "present": bool(tracks),
                "fields": ["tracks"],
                "operations": [
                    "marker_high_low_bin_selection",
                    "marker_stratified_distance",
                    "per_cell_marker_summary",
                    "per_cell_type_marker_summary",
                ],
            },
            "cell_metadata": {
                "present": len(cdata.cells) > 0,
                "fields": ["cells", "cellm"],
                "operations": ["cell_type_stratification", "embedding_visualization"],
            },
            "rna_expression": {
                "present": bool(linked.get("present")),
                "fields": ["linked_adata"],
                "operations": [
                    "gene_expression_lookup",
                    "expression_stratification",
                    "gene_marker_correlation",
                    "chromatin_expression_association",
                ],
            },
        },
        "fields": fields,
        "linked_adata": linked,
        "catalogs": {
            "chroms": _catalog(chroms, max_catalog_items),
            "tracks": _catalog(tracks, max_catalog_items),
            "cell_types": {
                "n": len(cell_type_counts),
                "counts": cell_type_counts,
                "values": list(cell_type_counts.keys()),
            },
            "genes": genes,
        },
        "constraints": {
            "cell_axis_alignment": (
                "cells.index, cellm arrays, and linked_adata.obs_names should share "
                "the same cell_id order when linked_adata is present."
            ),
            "spot_axis_alignment": "coords, spots, and tracks are row-aligned on the spot axis.",
            "free_code_policy": (
                "Discovery code agents may write new Python code, but exploratory "
                "runs should be recorded in notebooks with data checks and verification."
            ),
        },
        "known_missing": _known_missing(cdata, linked),
        "recommended_verification": [
            "required_fields_exist",
            "minimum_cell_count",
            "minimum_spot_or_trace_count",
            "finite_numeric_output",
            "statistical_hypothesis_test",
            "runtime_under_budget",
            "deterministic_rerun",
            "negative_control_or_permutation",
            "redundancy_against_existing_parameters",
        ],
    }
    schema["schema_hash"] = _hash_json(schema)
    return schema


def pack_schema(schema: Mapping[str, Any]) -> dict[str, str]:
    """Pack a schema as an HDF5-friendly ``uns`` entry."""
    payload = json.dumps(schema, sort_keys=True, separators=(",", ":"), default=_json_default)
    return {
        "format": DISCOVERY_SCHEMA_FORMAT,
        "version": str(schema.get("schema_version", DISCOVERY_SCHEMA_VERSION)),
        "payload": payload,
    }


def unpack_schema(raw: Any) -> dict[str, Any]:
    """Unpack a schema from ``cd.uns['auto_discovery_schema']``."""
    if raw is None:
        return {}
    if isinstance(raw, Mapping):
        payload = raw.get("payload")
        if payload is not None:
            if isinstance(payload, bytes):
                payload = payload.decode("utf-8")
            return json.loads(str(payload))
        return _json_roundtrip(raw)
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")
    if isinstance(raw, str):
        return json.loads(raw)
    return _json_roundtrip(raw)


def validate_discovery_schema(schema: Mapping[str, Any], cdata=None) -> list[str]:
    """Return validation issues for a discovery schema."""
    issues: list[str] = []
    for key in ("schema_version", "schema_type", "summary", "modalities", "fields", "catalogs"):
        if key not in schema:
            issues.append(f"missing top-level key: {key}")
    if schema.get("schema_type") != "uchrom_multiomics_auto_discovery":
        issues.append("schema_type is not uchrom_multiomics_auto_discovery")
    if cdata is not None and "summary" in schema:
        summary = schema["summary"]
        expected = {
            "n_spots": int(cdata.n_spots),
            "n_traces": int(cdata.n_traces),
            "n_cells": int(cdata.n_cells),
        }
        for key, value in expected.items():
            if int(summary.get(key, -1)) != value:
                issues.append(f"summary.{key}={summary.get(key)!r} != {value}")
    return issues


def schema_to_agent_context(schema: Mapping[str, Any], *, max_items: int = 40) -> str:
    """Render a compact, prompt-ready schema summary."""
    dataset = schema.get("dataset", {})
    summary = schema.get("summary", {})
    catalogs = schema.get("catalogs", {})
    linked = schema.get("linked_adata", {})
    lines = [
        "# ChromData discovery schema",
        "",
        f"dataset: {dataset.get('name', 'ChromData')}",
        f"genome: {dataset.get('genome_assembly') or 'unknown'}",
        f"xyz_unit: {dataset.get('xyz_unit') or 'unknown'}",
        (
            "shape: "
            f"{summary.get('n_spots', 0)} spots, "
            f"{summary.get('n_traces', 0)} traces, "
            f"{summary.get('n_cells', 0)} cells"
        ),
        "",
        "modalities:",
    ]
    for name, info in schema.get("modalities", {}).items():
        status = "present" if info.get("present") else "missing"
        ops = ", ".join(info.get("operations", [])[:6])
        lines.append(f"- {name}: {status}; operations: {ops}")

    lines.extend([
        "",
        f"chroms: {_format_catalog(catalogs.get('chroms', {}), max_items)}",
        f"cell_types: {_format_cell_types(catalogs.get('cell_types', {}), max_items)}",
        f"tracks: {_format_catalog(catalogs.get('tracks', {}), max_items)}",
    ])
    if linked.get("present"):
        lines.append(f"linked_adata: shape={linked.get('shape')}, X={linked.get('x_type')}")
        lines.append(f"genes: {_format_catalog(catalogs.get('genes', {}), max_items)}")
    else:
        lines.append("linked_adata: missing")

    missing = schema.get("known_missing", [])
    if missing:
        lines.extend(["", "known_missing:"])
        for item in missing:
            lines.append(f"- {item}")

    lines.extend(["", "verification_required:"])
    for item in schema.get("recommended_verification", []):
        lines.append(f"- {item}")
    return "\n".join(lines)


def _dataframe_field(df: pd.DataFrame | None, *, axis: str) -> dict[str, Any]:
    if df is None:
        return {"present": False, "axis": axis, "shape": [0, 0], "columns": []}
    return {
        "present": True,
        "axis": axis,
        "shape": [int(df.shape[0]), int(df.shape[1])],
        "columns": _columns(df),
        "dtypes": {str(k): str(v) for k, v in df.dtypes.items()},
        "index_name": None if df.index.name is None else str(df.index.name),
    }


def _array_mapping_field(mapping: Mapping[str, Any], *, axis: str) -> dict[str, Any]:
    return {
        "present": bool(mapping),
        "axis": axis,
        "keys": sorted(map(str, mapping.keys())),
        "shapes": {str(k): _shape(v) for k, v in mapping.items()},
        "dtypes": {str(k): str(getattr(v, "dtype", "")) for k, v in mapping.items()},
    }


def _linked_anndata_field(cdata, *, include_linked_adata: bool, max_catalog_items: int) -> dict[str, Any]:
    meta = dict(cdata.uns.get("linked_anndata", {}) or {})
    out = {
        "present": False,
        "path": _json_scalar(meta.get("path")),
        "n_obs": _maybe_int(meta.get("n_obs")),
        "n_vars": _maybe_int(meta.get("n_vars")),
        "cell_id_axis": _json_scalar(meta.get("cell_id_axis")),
    }
    if not include_linked_adata:
        return out
    adata = cdata.linked_adata
    if adata is None:
        return out
    out.update({
        "present": True,
        "shape": [int(adata.n_obs), int(adata.n_vars)],
        "x_type": type(adata.X).__name__,
        "obs_columns": _columns(adata.obs),
        "var_columns": _columns(adata.var),
        "layers": sorted(map(str, adata.layers.keys())),
        "obsm": sorted(map(str, adata.obsm.keys())),
        "uns_keys": sorted(map(str, adata.uns.keys())),
        "obs_names": _catalog(_as_str_list(adata.obs_names), max_catalog_items),
        "var_names": _catalog(_as_str_list(adata.var_names), max_catalog_items),
    })
    return out


def _cell_type_counts(cdata) -> dict[str, int]:
    if len(cdata.cells) == 0 or "cell_type" not in cdata.cells.columns:
        return {}
    counts = cdata.cells["cell_type"].astype(str).value_counts(dropna=False)
    return {str(k): int(v) for k, v in counts.items()}


def _known_missing(cdata, linked: Mapping[str, Any]) -> list[str]:
    missing = []
    if "if_mean" not in cdata.cellm:
        missing.append("cellm['if_mean'] per-cell IF mean matrix")
    if linked.get("present") and not cdata.uns.get("raw_rna_spots"):
        missing.append("raw RNA seqFISH spot geometry as a first-class ChromData component")
    if not cdata.uns.get("scrna_reference"):
        missing.append("scRNA reference matrix for external expression comparison")
    if not cdata.uns.get("gene_annotation"):
        missing.append("gene annotation cache for gene-neighborhood analyses")
    return missing


def _catalog(values: list[str], max_items: int) -> dict[str, Any]:
    values = list(values)
    return {
        "n": len(values),
        "values": values[:max_items],
        "truncated": len(values) > max_items,
        "sha1": _hash_names(values),
    }


def _format_catalog(catalog: Mapping[str, Any], max_items: int) -> str:
    values = list(catalog.get("values", []))[:max_items]
    suffix = " ..." if catalog.get("truncated") or catalog.get("n", 0) > len(values) else ""
    return f"{catalog.get('n', len(values))} [{', '.join(map(str, values))}{suffix}]"


def _format_cell_types(catalog: Mapping[str, Any], max_items: int) -> str:
    counts = catalog.get("counts", {}) or {}
    items = list(counts.items())[:max_items]
    suffix = " ..." if len(counts) > len(items) else ""
    return f"{len(counts)} [" + ", ".join(f"{k}={v}" for k, v in items) + suffix + "]"


def _columns(df: pd.DataFrame | None) -> list[str]:
    if df is None:
        return []
    return [str(c) for c in df.columns]


def _shape(value: Any) -> list[int]:
    return [int(x) for x in getattr(value, "shape", [])]


def _as_str_list(values: Any) -> list[str]:
    return [str(v) for v in list(values)]


def _maybe_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except Exception:
        return None


def _json_scalar(value: Any) -> Any:
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, bytes):
        return value.decode("utf-8")
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _json_default(value: Any) -> Any:
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, (pd.Index, pd.Series)):
        return value.tolist()
    if isinstance(value, bytes):
        return value.decode("utf-8")
    return str(value)


def _json_roundtrip(value: Any) -> dict[str, Any]:
    return json.loads(json.dumps(value, default=_json_default))


def _hash_names(values: list[str]) -> str:
    h = hashlib.sha1()
    for value in values:
        h.update(value.encode("utf-8"))
        h.update(b"\0")
    return h.hexdigest()


def _hash_json(value: Mapping[str, Any]) -> str:
    clone = dict(value)
    clone.pop("schema_hash", None)
    clone.pop("created_utc", None)
    payload = json.dumps(clone, sort_keys=True, separators=(",", ":"), default=_json_default)
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()
