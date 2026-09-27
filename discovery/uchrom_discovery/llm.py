"""Provider-agnostic prompt builders for U-Chrom auto-discovery."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from .schema import schema_to_agent_context


STRUCTURED_JSON_BEGIN = "BEGIN_UCHROM_JSON"
STRUCTURED_JSON_END = "END_UCHROM_JSON"


def allowed_required_fields(schema: Mapping[str, Any], *, max_items: int) -> list[str]:
    """Return schema field paths that agents may use in ``required_fields``."""
    fields = ["coords"]
    for table in ("spots", "tracks", "cells", "traces"):
        for column in (schema.get("fields", {}).get(table, {}) or {}).get("columns", []):
            fields.append(f"{table}.{column}")
    for mapping in ("cellm", "layers"):
        for key in (schema.get("fields", {}).get(mapping, {}) or {}).get("keys", []):
            fields.append(f"{mapping}.{key}")
    linked = schema.get("linked_adata", {}) or {}
    if linked.get("present"):
        fields.append("linked_adata.X")
        for col in linked.get("obs_columns", [])[:max_items]:
            fields.append(f"linked_adata.obs.{col}")
        for gene in (schema.get("catalogs", {}).get("genes", {}) or {}).get("values", [])[:max_items]:
            fields.append(f"linked_adata.var.{gene}")
        for layer in linked.get("layers", [])[:max_items]:
            fields.append(f"linked_adata.layers.{layer}")
    return fields[:max_items]


def build_required_fields_prompt_block(schema: Mapping[str, Any], *, max_items: int = 80) -> str:
    """Build the legacy required-field guardrails shared by all idea backends."""
    allowed_fields = allowed_required_fields(schema, max_items=max_items)
    missing = schema.get("known_missing", [])
    return (
        "Important required_fields rules:\n"
        "- required_fields must be exact field paths from the allowed list below.\n"
        "- Do not put operation names such as gene_expression_lookup in required_fields.\n"
        "- Do not use known_missing entries as required_fields.\n"
        "- For RNA expression, include linked_adata.X and linked_adata.var.<gene>.\n\n"
        f"Allowed required_fields:\n{json.dumps(allowed_fields, indent=2)}\n\n"
        f"Known missing data that must not be used:\n{json.dumps(missing, indent=2)}"
    )


def build_idea_prompt(
    schema: Mapping[str, Any],
    *,
    max_ideas: int,
    prior_graph_path: str | Path | None = None,
    direction_context_path: str | Path | None = None,
) -> str:
    """Build the structured idea-generation prompt used by CLI backends."""
    extra = []
    if prior_graph_path is not None:
        extra.append(f"- Prior graph JSON: {prior_graph_path}")
    if direction_context_path is not None:
        extra.append(f"- Direction context markdown: {direction_context_path}")
    extra_text = "\n".join(extra) if extra else "- No prior graph or direction context."
    required_fields_block = build_required_fields_prompt_block(schema)
    return f"""
You are an autonomous scientific idea generator for chromatin tracing and
multi-omics data. Generate diverse, computable U-Chrom discovery ideas for this
ChromData dataset. Return only structured JSON between {STRUCTURED_JSON_BEGIN}
and {STRUCTURED_JSON_END}. Do not write files.

Files:
- Schema JSON and compact schema context are available in the backend workdir.
{extra_text}

{required_fields_block}

Rules:
- Generate at most {max_ideas} diverse, computable ideas.
- Use only modalities, fields, cell types, tracks, and genes present in schema.
- Each idea must define exactly one measurable parameter.
- Each idea must be compatible with DiscoveryIdea.from_dict.
- Vary cell types and modality combinations across ideas.
- Include statistical_hypothesis_test in validation_checks unless impossible.
- Include idea_markdown when useful to explain rationale, data used, analysis
  sketch, expected result, and validation checks in human-readable prose.
- Complexity must be 1-5.

Schema summary:
{schema_to_agent_context(schema, max_items=60)}

Return this shape exactly:
{{
  "ideas": [
    {{
      "idea_title": "...",
      "idea_markdown": "### Rationale\\n...",
      "biological_hypothesis": "...",
      "computable_parameter": "...",
      "analysis_plan": "...",
      "modalities": ["chromatin_tracing"],
      "cell_types": ["..."],
      "required_fields": ["coords"],
      "validation_checks": ["required_fields_exist", "finite_numeric_output", "statistical_hypothesis_test"],
      "expected_direction": "...",
      "complexity": 3,
      "metadata": {{}}
    }}
  ]
}}
""".strip()


def build_analysis_prompt(
    *,
    idea_path: Path,
    schema_path: Path,
    context_path: Path,
    h5cd_path: Path,
    output_dir: Path,
) -> str:
    """Build the structured analysis-code prompt used by CLI backends."""
    return f"""
You are a careful Python data scientist writing one executable Python notebook
analysis cell for chromatin tracing multi-omics analysis. Read these files:
- Idea JSON: {idea_path}
- Schema JSON: {schema_path}
- Schema context: {context_path}

The final notebook is owned by the U-Chrom runner. Do not edit files or
notebooks. Return the structured JSON in your final message only.

Execution environment:
- H5CD_PATH will be {h5cd_path}
- RUN_OUTPUT_DIR will be {output_dir}
- Variables already defined by the notebook: cdata, adata, IDEA, schema, review,
  RUN_OUTPUT_DIR, np, pd, plt, ChromData.
- IDEA is a DiscoveryIdea object. Prefer attribute access such as IDEA.idea_id
  and IDEA.idea_title over dict-style access.

Return only structured JSON between {STRUCTURED_JSON_BEGIN} and
{STRUCTURED_JSON_END} with this shape:
{{
  "analysis_code": "Python code string",
  "extra_cells": [],
  "artifact_manifest": [],
  "warnings": [],
  "notes": []
}}

analysis_code requirements:
- Define result_table as a pandas DataFrame.
- Define analysis_summary as a JSON-serializable dict.
- Write result_table to RUN_OUTPUT_DIR / f"{{IDEA.idea_id}}_result.csv".
- result_table must include `p_value` and `test_method` columns on every row.
- Include result_path, parameter_value, observed_statistic, effect_size, p_value,
  test_method, null_hypothesis, alternative_hypothesis, hypothesis_test_status,
  n_selected_cells, and n_rows in analysis_summary.
- parameter_value must be a finite numeric scalar that directly summarizes the
  computable parameter, not the parameter name or any other string.
- observed_statistic, effect_size, and p_value must also be finite numeric
  scalars; convert numpy scalar types with float(...) or int(...).
- Perform an explicit statistical hypothesis test or bounded permutation /
  randomization test. Do not set hypothesis_test_status to `insufficient_data`
  when a finite fallback statistic can be computed; use `pass_with_fallback`,
  set p_value to 1.0, and add a note instead.
- Use a bounded permutation/randomization test or a suitable nonparametric test
  when possible. Keep runtime small by using aggregation or subsampling.
- If using pd.qcut or pd.cut and you need `.cat`, wrap the input in
  pd.Series(...) first; qcut/cut on numpy arrays returns a Categorical without
  the Series `.cat` accessor.
- Do not modify package source files or notebooks.

ChromData access rules:
- Do not index ChromData with string field paths like cdata['tracks.H3K27me3'].
- Use cdata.spots, cdata.cells, cdata.cellm, cdata.coords directly.  For
  tracks use cdata.tracks_spot_view() (every track aligned to spots; the
  schema's tracks.* fields), cdata.bin_tracks (per locus, indexed by
  spots['bin_id']) or cdata.spot_tracks (per spot).
- To select spots by cell type, get cell IDs from cdata.cells and mask
  cdata.spots['cell_id'].
- To combine spot-level tracks with RNA expression, aggregate tracks per cell_id first, then align to adata.obs_names.
- AnnData access is allowed as adata[:, gene].X; convert sparse matrices with
  toarray().
- Verification requires a finite numeric parameter_value. If the requested
  statistic is undefined because the selected sample is too small or an input is
  constant, compute a finite descriptive fallback effect size and record the
  fallback in analysis_summary['notes'].
""".strip()


def idea_output_schema(*, max_ideas: int | None = None) -> dict[str, Any]:
    """Return the structured-output schema for idea-generation backends."""
    ideas_schema: dict[str, Any] = {
        "type": "array",
        "items": {
            "type": "object",
            "properties": {
                "idea_title": {"type": "string"},
                "biological_hypothesis": {"type": "string"},
                "computable_parameter": {"type": "string"},
                "analysis_plan": {"type": "string"},
                "modalities": {"type": "array", "items": {"type": "string"}},
                "idea_markdown": {"type": "string"},
                "cell_types": {"type": "array", "items": {"type": "string"}},
                "required_fields": {"type": "array", "items": {"type": "string"}},
                "validation_checks": {"type": "array", "items": {"type": "string"}},
                "expected_direction": {"type": "string"},
                "complexity": {"type": "integer", "minimum": 1, "maximum": 5},
                "metadata": {"type": "object", "additionalProperties": True},
            },
            "required": [
                "idea_title",
                "biological_hypothesis",
                "computable_parameter",
                "analysis_plan",
                "modalities",
                "cell_types",
                "required_fields",
                "validation_checks",
                "expected_direction",
                "complexity",
            ],
            "additionalProperties": False,
        },
    }
    if max_ideas is not None:
        ideas_schema["maxItems"] = max_ideas
    return {
        "type": "object",
        "properties": {"ideas": ideas_schema},
        "required": ["ideas"],
        "additionalProperties": False,
    }


def analysis_output_schema() -> dict[str, Any]:
    """Return the structured-output schema for analysis-code backends."""
    return {
        "type": "object",
        "properties": {
            "analysis_code": {"type": "string"},
            "extra_cells": {
                "type": "array",
                "items": {"type": "object", "additionalProperties": True},
            },
            "artifact_manifest": {
                "type": "array",
                "items": {"type": "object", "additionalProperties": True},
            },
            "warnings": {"type": "array", "items": {"type": "string"}},
            "notes": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["analysis_code", "extra_cells", "artifact_manifest", "warnings", "notes"],
        "additionalProperties": False,
    }
