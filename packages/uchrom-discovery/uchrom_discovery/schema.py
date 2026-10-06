"""Agent-readable discovery schema for :class:`chromdata.ChromData`.

The schema is intentionally stored inside ``cd.uns`` as a JSON payload so
it round-trips through a ChromData store without a new storage layout.
"""

from __future__ import annotations

import re

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Mapping

import numpy as np
import pandas as pd


DISCOVERY_SCHEMA_KEY = "auto_discovery_schema"
DISCOVERY_SCHEMA_VERSION = "0.1"
DISCOVERY_SCHEMA_FORMAT = "uchrom_discovery.schema+json"
ENRICHED_TRACK_PREFIXES = frozenset({"seq", "gtf", "strc", "peak"})


def build_discovery_schema(
    cdata,
    *,
    store: bool = False,
    dataset_name: str | None = None,
    include_linked_adata: bool = True,
    max_catalog_items: int = 500,
) -> dict[str, Any]:
    """Build an agent-readable schema from a ``ChromData`` object.

    The returned dict is JSON-serializable.  With ``store=True`` it is also
    packed (:func:`pack_schema`) into ``cd.uns['auto_discovery_schema']`` so
    it round-trips with the store.
    """
    schema = _build_discovery_schema(
        cdata,
        dataset_name=dataset_name,
        include_linked_adata=include_linked_adata,
        max_catalog_items=max_catalog_items,
    )
    if store:
        cdata.uns[DISCOVERY_SCHEMA_KEY] = pack_schema(schema)
    return schema


def get_discovery_schema(cdata) -> dict[str, Any]:
    """Return the schema stored in ``cd.uns``, or build one without storing."""
    raw = cdata.uns.get(DISCOVERY_SCHEMA_KEY)
    if raw is not None:
        return unpack_schema(raw)
    return build_discovery_schema(cdata)


def store_discovery_schema(cdata, schema: Mapping[str, Any] | None = None, **kwargs) -> dict[str, Any]:
    """Store a supplied (or newly built) schema in ``cd.uns``."""
    if schema is None:
        return build_discovery_schema(cdata, store=True, **kwargs)
    cdata.uns[DISCOVERY_SCHEMA_KEY] = pack_schema(schema)
    return dict(schema)


def describe_for_agent(cdata, *, max_items: int = 40) -> str:
    """Compact, prompt-ready description of the data available in ``cdata``."""
    return schema_to_agent_context(get_discovery_schema(cdata), max_items=max_items)


def _build_discovery_schema(
    cdata,
    *,
    dataset_name: str | None,
    include_linked_adata: bool,
    max_catalog_items: int,
) -> dict[str, Any]:
    fields = {
        "coords": {
            "axis": "spot",
            "shape": _shape(cdata.coords),
            "dtype": str(getattr(cdata.coords, "dtype", "")),
            "description": "Spot-level 3D coordinates.",
        },
        "spots": _dataframe_field(cdata.spots, axis="spot"),
        "tracks": _dataframe_field(_tracks_view(cdata), axis="spot"),
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
    linked_mudata = _linked_modality_records(cdata.uns.get("linked_mudata"))
    linked_scool = _linked_modality_records(cdata.uns.get("linked_scool"))
    cell_spatial = _linked_modality_records(cdata.uns.get("cell_spatial"))

    tracks = _columns(_tracks_view(cdata))
    track_groups = _track_groups(tracks)
    result_tables = _result_tables(cdata.results)
    feature_registry = _metadata_records(cdata.uns.get("feature_registry"))
    feature_summary = _feature_summary(feature_registry, track_groups, result_tables)
    genes = linked.get("var_names", {"n": 0, "values": [], "truncated": False, "sha1": ""})
    references = _metadata_records(cdata.uns.get("dataset_references"))
    user_annotations = _metadata_records(cdata.uns.get("user_annotations"))
    fields["results"]["tables"] = result_tables
    sequence_present = _has_feature_group(feature_registry, "sequence") or "seq" in track_groups
    annotation_present = (
        _has_feature_group(feature_registry, "annotation")
        or "gtf" in track_groups
        or "gene_annotations" in result_tables
    )
    structure_present = (
        _has_feature_group(feature_registry, "structure")
        or _has_feature_group(feature_registry, "structural")
        or "strc" in track_groups
        or any(_result_family(key) in {"tads", "loops", "compartments"} for key in result_tables)
    )
    peaks_present = (
        _has_feature_group(feature_registry, "peaks")
        or "peak" in track_groups
        or any(_result_family(key) == "peaks" for key in result_tables)
    )
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
        "references": references,
        "user_annotations": user_annotations,
        "knowledge_seed_context": _knowledge_seed_context(references, user_annotations),
        "summary": {
            "n_spots": int(cdata.n_spots),
            "n_traces": int(cdata.n_traces),
            "n_cells": int(cdata.n_cells),
            "n_chroms": len(chroms),
            "n_tracks": len(tracks),
            "n_track_groups": len(track_groups),
            "n_feature_registry_entries": len(feature_registry),
            "n_enriched_feature_tracks": int(sum(info.get("n_tracks", 0) for info in feature_summary.values())),
            "n_references": len(references),
            "n_user_annotations": len(user_annotations),
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
            "cell_spatial_coordinates": {
                "present": bool(cell_spatial.get("present")),
                "fields": ["cells", "uns.cell_spatial"],
                "operations": [
                    "cell_spatial_visualization",
                    "spatial_neighborhood_lookup",
                    "inferred_coordinate_quality_check",
                ],
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
            "mudata_multiomics": {
                "present": bool(linked_mudata.get("present")),
                "fields": ["linked_mudata"],
                "operations": [
                    "multi_modal_cell_metadata_lookup",
                    "modality_embedding_visualization",
                    "cross_modality_association",
                    "spatial_inference_lookup",
                ],
            },
            "single_cell_hic_contacts": {
                "present": bool(linked_scool.get("present")),
                "fields": ["linked_scool"],
                "operations": [
                    "per_cell_contact_matrix_lookup",
                    "contact_derived_feature_association",
                    "scool_cell_subset",
                    "contact_map_visualization",
                ],
            },
            "sequence_features": {
                "present": bool(sequence_present),
                "fields": ["tracks", "results.bin_features", "uns.feature_registry"],
                "operations": [
                    "sequence_track_stratified_distance",
                    "gc_content_association",
                    "g4_density_association",
                    "sequence_feature_correlation",
                ],
            },
            "genome_annotations": {
                "present": bool(annotation_present),
                "fields": ["tracks", "results.bin_features", "results.gene_annotations", "uns.feature_registry"],
                "operations": [
                    "annotation_overlap_enrichment",
                    "nearest_tss_distance_association",
                    "gene_body_or_promoter_stratification",
                ],
            },
            "structure_annotations": {
                "present": bool(structure_present),
                "fields": ["results.tads", "results.loops", "results.compartments", "tracks"],
                "operations": [
                    "tad_boundary_distance",
                    "loop_anchor_proximity",
                    "compartment_stratified_radial_position",
                ],
            },
            "peak_features": {
                "present": bool(peaks_present),
                "fields": ["tracks", "results.bin_features", "results.peaks:*", "uns.feature_registry"],
                "operations": [
                    "peak_overlap_enrichment",
                    "peak_distance_association",
                    "peak_stratified_distance",
                ],
            },
        },
        "fields": fields,
        "feature_registry": feature_registry,
        "feature_summary": feature_summary,
        "linked_adata": linked,
        "linked_mudata": linked_mudata,
        "linked_scool": linked_scool,
        "cell_spatial": cell_spatial,
        "catalogs": {
            "chroms": _catalog(chroms, max_catalog_items),
            "tracks": _catalog(tracks, max_catalog_items),
            "track_groups": {
                name: _catalog(values, max_catalog_items)
                for name, values in sorted(track_groups.items())
            },
            "cell_types": {
                "n": len(cell_type_counts),
                "counts": cell_type_counts,
                "values": list(cell_type_counts.keys()),
            },
            "genes": genes,
        },
        "constraints": {
            "cell_axis_alignment": (
                "cells.index, cellm arrays, linked_adata.obs_names, linked_mudata "
                "cell axes, and linked_scool cell names must be explicitly mapped "
                "when more than one cell identifier system is present."
            ),
            "spot_axis_alignment": "coords, spots, and tracks are row-aligned on the spot axis.",
            "coordinate_semantics": (
                "Raw scool contacts are not xyz coordinates. Tangram or other "
                "mapped spatial coordinates should be marked as inferred unless "
                "directly measured."
            ),
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


def validate_discovery_schema(
    schema: Mapping[str, Any] | None = None,
    cdata=None,
    *,
    raise_on_error: bool = False,
) -> list[str]:
    """Return validation issues for a discovery schema.

    With ``schema=None`` the schema of ``cdata`` is validated
    (:func:`get_discovery_schema`).  ``raise_on_error=True`` raises
    ``ValueError`` when any issue is found.
    """
    if schema is None:
        if cdata is None:
            raise ValueError("validate_discovery_schema needs a schema or a cdata")
        schema = get_discovery_schema(cdata)
    issues = _validate_discovery_schema(schema, cdata)
    if issues and raise_on_error:
        raise ValueError("; ".join(issues))
    return issues


def _validate_discovery_schema(schema: Mapping[str, Any], cdata=None) -> list[str]:
    issues: list[str] = []
    for key in ("schema_version", "schema_type", "summary", "modalities", "fields", "catalogs"):
        if key not in schema:
            issues.append(f"missing top-level key: {key}")
    if schema.get("schema_type") != "uchrom_multiomics_auto_discovery":
        issues.append("schema_type is not uchrom_multiomics_auto_discovery")
    if "references" in schema and not isinstance(schema["references"], list):
        issues.append("references must be a list")
    if "user_annotations" in schema and not isinstance(schema["user_annotations"], list):
        issues.append("user_annotations must be a list")
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
    linked_mudata = schema.get("linked_mudata", {})
    linked_scool = schema.get("linked_scool", {})
    cell_spatial = schema.get("cell_spatial", {})
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
    track_groups = catalogs.get("track_groups", {})
    if track_groups:
        group_bits = []
        for name, info in sorted(track_groups.items()):
            group_bits.append(f"{name}={info.get('n', 0)}")
        lines.append(f"track_groups: {', '.join(group_bits)}")
    result_tables = schema.get("fields", {}).get("results", {}).get("tables", {})
    if result_tables:
        table_bits = []
        for name, info in sorted(result_tables.items()):
            cols = info.get("columns", [])
            table_bits.append(f"{name}({len(cols)} cols)")
        lines.append(f"result_tables: {', '.join(table_bits[:max_items])}")
    registry = schema.get("feature_registry", [])
    if registry:
        groups = sorted({
            str(item.get("feature_group"))
            for item in registry
            if item.get("feature_group")
        })
        lines.append(f"feature_registry: {len(registry)} entries; groups={', '.join(groups)}")
    feature_summary = schema.get("feature_summary", {})
    if feature_summary:
        lines.extend(["", "enriched_features:"])
        for name, info in sorted(feature_summary.items()):
            tracks = _format_catalog({"n": info.get("n_tracks", 0), "values": info.get("tracks", [])}, max_items)
            features = _format_catalog({"n": info.get("n_features", 0), "values": info.get("features", [])}, max_items)
            sources = ", ".join(map(str, info.get("source_paths", [])[:3])) or "none"
            lines.append(
                f"- {name}: tracks={tracks}; features={features}; "
                f"results={', '.join(map(str, info.get('result_keys', []))) or 'none'}; sources={sources}"
            )
    if linked.get("present"):
        lines.append(f"linked_adata: shape={linked.get('shape')}, X={linked.get('x_type')}")
        lines.append(f"genes: {_format_catalog(catalogs.get('genes', {}), max_items)}")
    else:
        lines.append("linked_adata: missing")
    if linked_mudata.get("present"):
        lines.append(f"linked_mudata: records={', '.join(sorted(linked_mudata.get('records', {})))}")
    else:
        lines.append("linked_mudata: missing")
    if linked_scool.get("present"):
        lines.append(f"linked_scool: records={', '.join(sorted(linked_scool.get('records', {})))}")
    else:
        lines.append("linked_scool: missing")
    if cell_spatial.get("present"):
        lines.append(f"cell_spatial: records={', '.join(sorted(cell_spatial.get('records', {})))}")
    else:
        lines.append("cell_spatial: missing")

    references = list(schema.get("references", []) or [])
    annotations = list(schema.get("user_annotations", []) or [])
    if references:
        lines.extend(["", "dataset_references:"])
        for ref in references[:max_items]:
            lines.append(f"- {_format_reference(ref)}")
        if len(references) > max_items:
            lines.append(f"- ... {len(references) - max_items} more")
    if annotations:
        lines.extend(["", "user_annotations:"])
        for ann in annotations[:max_items]:
            lines.append(f"- {_format_annotation(ann)}")
        if len(annotations) > max_items:
            lines.append(f"- ... {len(annotations) - max_items} more")

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


def _result_tables(results: Mapping[str, Any]) -> dict[str, Any]:
    tables: dict[str, Any] = {}
    for key, value in results.items():
        if isinstance(value, pd.DataFrame):
            tables[str(key)] = _dataframe_field(value, axis="result_row")
        elif isinstance(value, np.ndarray):
            tables[str(key)] = {
                "present": True,
                "axis": "result_array",
                "shape": _shape(value),
                "dtype": str(value.dtype),
            }
    return tables


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


def _linked_modality_records(raw: Any) -> dict[str, Any]:
    records = _normalize_link_records(raw)
    return {
        "present": bool(records),
        "records": records,
    }


def _normalize_link_records(raw: Any) -> dict[str, Any]:
    if raw is None:
        return {}
    if not isinstance(raw, Mapping):
        return {"default": {"value": _json_scalar(raw)}}
    raw_dict = dict(raw)
    if "path" in raw_dict:
        return {"default": _json_roundtrip(raw_dict)}
    records = {}
    for key, value in raw_dict.items():
        if isinstance(value, Mapping):
            records[str(key)] = _json_roundtrip(value)
        else:
            records[str(key)] = {"value": _json_scalar(value)}
    return records


def _metadata_records(raw: Any) -> list[dict[str, Any]]:
    if raw is None:
        return []
    if isinstance(raw, Mapping):
        raw = [raw]
    if not isinstance(raw, (list, tuple)):
        return []
    records = []
    for item in raw:
        if not isinstance(item, Mapping):
            continue
        records.append(_json_roundtrip(dict(item)))
    return records


def _knowledge_seed_context(
    references: list[Mapping[str, Any]],
    annotations: list[Mapping[str, Any]],
) -> dict[str, Any]:
    roles: dict[str, int] = {}
    annotation_scopes: dict[str, int] = {}
    citation_seeds = []
    annotation_seeds = []
    for ref in references:
        role = str(ref.get("role") or "unspecified")
        roles[role] = roles.get(role, 0) + 1
        seed = {
            "reference_id": ref.get("reference_id"),
            "role": ref.get("role"),
            "title": ref.get("title"),
            "doi": ref.get("doi"),
            "pmid": ref.get("pmid"),
            "url": ref.get("url"),
        }
        citation_seeds.append({k: v for k, v in seed.items() if v not in (None, "")})
    for ann in annotations:
        scope = str(ann.get("scope") or "unspecified")
        annotation_scopes[scope] = annotation_scopes.get(scope, 0) + 1
        seed = {
            "annotation_id": ann.get("annotation_id"),
            "scope": ann.get("scope"),
            "target": ann.get("target"),
            "text": ann.get("text"),
            "tags": ann.get("tags", []),
            "confidence": ann.get("confidence"),
        }
        annotation_seeds.append({k: v for k, v in seed.items() if v not in (None, "")})
    return {
        "n_references": len(references),
        "reference_roles": roles,
        "n_user_annotations": len(annotations),
        "annotation_scopes": annotation_scopes,
        "citation_seeds": citation_seeds,
        "annotation_seeds": annotation_seeds,
    }


def _feature_summary(
    feature_registry: list[dict[str, Any]],
    track_groups: Mapping[str, list[str]],
    result_tables: Mapping[str, Any],
) -> dict[str, Any]:
    mapping = {
        "sequence": ("seq", {"sequence"}),
        "annotation": ("gtf", {"annotation"}),
        "structure": ("strc", {"structure", "structural"}),
        "peaks": ("peak", {"peaks"}),
    }
    summary: dict[str, Any] = {}
    for name, (prefix, registry_names) in mapping.items():
        records = [
            record for record in feature_registry
            if str(record.get("feature_group")) in registry_names
        ]
        tracks = sorted(set(map(str, track_groups.get(prefix, []))))
        features = sorted(set(
            str(feature)
            for record in records
            for feature in (record.get("features") or [])
            if feature not in (None, "")
        ) | set(tracks))
        result_keys = sorted(set(
            str(record.get("result_key"))
            for record in records
            if record.get("result_key")
        ))
        source_results = sorted(set(
            str(source)
            for record in records
            for source in (record.get("source_results") or [])
            if source not in (None, "")
        ))
        source_paths = sorted(set(
            str(record.get("source_path"))
            for record in records
            if record.get("source_path")
        ))
        source_hashes = sorted(set(
            str(record.get("source_sha256"))
            for record in records
            if record.get("source_sha256")
        ))
        created_by = sorted(set(
            str(record.get("created_by"))
            for record in records
            if record.get("created_by")
        ))
        present = bool(records or tracks or result_keys or source_results)
        if not present and name == "structure":
            present = any(_result_family(key) in {"tads", "loops", "compartments"} for key in result_tables)
        if not present and name == "peaks":
            present = any(_result_family(key) == "peaks" for key in result_tables)
        summary[name] = {
            "present": bool(present),
            "n_registry_entries": len(records),
            "n_tracks": len(tracks),
            "tracks": tracks,
            "n_features": len(features),
            "features": features,
            "result_keys": result_keys,
            "source_results": source_results,
            "source_paths": source_paths,
            "source_sha256": source_hashes,
            "created_by": created_by,
        }
    return summary


def _format_reference(ref: Mapping[str, Any]) -> str:
    label = ref.get("reference_id") or ref.get("title") or ref.get("doi") or ref.get("url") or "reference"
    bits = [str(label)]
    if ref.get("title") and ref.get("title") != label:
        bits.append(f"title={ref.get('title')}")
    if ref.get("role"):
        bits.append(f"role={ref.get('role')}")
    if ref.get("year"):
        bits.append(f"year={ref.get('year')}")
    if ref.get("doi"):
        bits.append(f"doi={ref.get('doi')}")
    if ref.get("pmid"):
        bits.append(f"pmid={ref.get('pmid')}")
    if ref.get("url") and not ref.get("doi"):
        bits.append(f"url={ref.get('url')}")
    if ref.get("notes"):
        bits.append(f"notes={_truncate(str(ref.get('notes')), 160)}")
    return "; ".join(bits)


def _format_annotation(annotation: Mapping[str, Any]) -> str:
    label = annotation.get("annotation_id") or annotation.get("scope") or "annotation"
    bits = [str(label)]
    if annotation.get("scope"):
        bits.append(f"scope={annotation.get('scope')}")
    if annotation.get("target"):
        bits.append(f"target={annotation.get('target')}")
    if annotation.get("tags"):
        bits.append("tags=" + ",".join(map(str, annotation.get("tags", []))))
    if annotation.get("confidence"):
        bits.append(f"confidence={annotation.get('confidence')}")
    if annotation.get("text"):
        bits.append(f"text={_truncate(str(annotation.get('text')), 220)}")
    return "; ".join(bits)


def _truncate(text: str, max_chars: int) -> str:
    text = " ".join(text.split())
    if len(text) <= max_chars:
        return text
    return text[: max(0, max_chars - 4)].rstrip() + " ..."


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


def _track_groups(columns: list[str]) -> dict[str, list[str]]:
    groups: dict[str, list[str]] = {}
    for col in columns:
        name = str(col)
        if "." in name:
            group, _ = name.split(".", 1)
            if group not in ENRICHED_TRACK_PREFIXES:
                group = "marker"
        else:
            group = "marker"
        groups.setdefault(group, []).append(name)
    return groups


def _has_feature_group(records: list[dict[str, Any]], name: str) -> bool:
    return any(str(record.get("feature_group")) == name for record in records)


def _tracks_view(cdata):
    """All tracks aligned to spots (bin-level tracks broadcast), or None."""
    if hasattr(cdata, "tracks_spot_view"):
        view = cdata.tracks_spot_view()
        return view if len(view.columns) else None
    return getattr(cdata, "tracks", None)


def _result_family(key: str) -> str:
    """``"tads:chr1"`` / ``"tads.arcfish"`` / ``"tads"`` → ``"tads"``."""
    return re.split(r"[:.]", str(key), maxsplit=1)[0]


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
