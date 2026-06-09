"""Optional LLM-backed idea generation."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Mapping

from .ideas import DiscoveryIdea
from .schema import schema_to_agent_context


OPENAI_RESPONSES_URL = "https://api.openai.com/v1/responses"
DEFAULT_OPENAI_MODEL = "gpt-5.5"
DEFAULT_OPENAI_REASONING_EFFORT = "medium"
OPENAI_IDEA_MAX_OUTPUT_TOKENS = 8000
OPENAI_CODE_MAX_OUTPUT_TOKENS = 12000


def generate_openai_ideas(
    schema: Mapping[str, Any],
    *,
    max_ideas: int = 8,
    model: str | None = None,
    reasoning_effort: str | None = None,
    api_key: str | None = None,
    env_path: str | Path = "~/.env",
    timeout: int = 120,
) -> list[DiscoveryIdea]:
    """Generate structured ideas with the OpenAI Responses API.

    This function intentionally avoids a hard dependency on the OpenAI
    Python SDK so the package remains lightweight.  It uses the API key
    from ``api_key``, ``OPENAI_API_KEY``, or ``~/.env``.
    """
    env = _read_env(env_path)
    api_key = api_key or os.environ.get("OPENAI_API_KEY") or env.get("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY was not found in the environment or ~/.env")
    model = _resolve_model(model, env)
    reasoning_effort = _resolve_reasoning_effort(reasoning_effort, env)
    allowed_fields = _allowed_required_fields(schema, max_items=80)
    missing = schema.get("known_missing", [])

    prompt = (
        "Generate diverse, computable multi-omics discovery ideas for this U-Chrom "
        "ChromData dataset. Use only modalities and fields listed in the schema. "
        "Each idea must be a single measurable parameter and must include concrete "
        "required_fields and validation_checks. Vary cell types and modality "
        "combinations across ideas.\n\n"
        "Important required_fields rules:\n"
        "- required_fields must be exact field paths from the allowed list below.\n"
        "- Do not put operation names such as gene_expression_lookup in required_fields.\n"
        "- Do not use known_missing entries as required_fields.\n"
        "- For RNA expression, include linked_adata.X and linked_adata.var.<gene>.\n\n"
        f"Allowed required_fields:\n{json.dumps(allowed_fields, indent=2)}\n\n"
        f"Known missing data that must not be used:\n{json.dumps(missing, indent=2)}\n\n"
        f"{schema_to_agent_context(schema, max_items=60)}"
    )
    payload = {
        "model": model,
        "max_output_tokens": OPENAI_IDEA_MAX_OUTPUT_TOKENS,
        "input": [
            {
                "role": "system",
                "content": (
                    "You are an autonomous scientific idea generator for chromatin "
                    "tracing and multi-omics data. Return only schema-valid JSON."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        "text": {
            "format": {
                "type": "json_schema",
                "name": "uchrom_discovery_ideas",
                "strict": True,
                "schema": _ideas_json_schema(max_ideas=max_ideas),
            }
        },
    }
    _add_reasoning(payload, model=model, reasoning_effort=reasoning_effort)
    req = urllib.request.Request(
        OPENAI_RESPONSES_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"OpenAI request failed with HTTP {exc.code}: {body}") from exc
    text = _extract_response_text(data)
    parsed = json.loads(text)
    return [DiscoveryIdea.from_dict(item) for item in parsed.get("ideas", [])[:max_ideas]]


def generate_openai_analysis_code(
    idea: DiscoveryIdea,
    schema: Mapping[str, Any],
    *,
    model: str | None = None,
    reasoning_effort: str | None = None,
    api_key: str | None = None,
    env_path: str | Path = "~/.env",
    timeout: int = 180,
) -> str:
    """Generate free-form notebook analysis code for one idea."""
    env = _read_env(env_path)
    api_key = api_key or os.environ.get("OPENAI_API_KEY") or env.get("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY was not found in the environment or ~/.env")
    model = _resolve_model(model, env)
    reasoning_effort = _resolve_reasoning_effort(reasoning_effort, env)
    prompt = (
        "Write one executable Python notebook cell for this U-Chrom discovery idea. "
        "The cell will run after variables cdata, adata, IDEA, schema, review, and "
        "RUN_OUTPUT_DIR are already defined. You may write arbitrary Python using "
        "numpy, pandas, scipy if installed, matplotlib, and U-Chrom APIs. Do not "
        "modify package source files. Keep runtime small by using aggregation or "
        "subsampling when needed. The cell must define result_table as a pandas "
        "DataFrame and analysis_summary as a JSON-serializable dict. It must write "
        "result_table to RUN_OUTPUT_DIR / f'{IDEA.idea_id}_result.csv' and include "
        "result_path and parameter_value in analysis_summary. It must perform an "
        "explicit statistical hypothesis test, not only descriptive aggregation: "
        "define null_hypothesis, alternative_hypothesis, test_method, "
        "observed_statistic, effect_size, p_value, and hypothesis_test_status in "
        "analysis_summary, and include p_value/test_method columns in result_table. "
        "Use a bounded permutation/randomization test or a suitable nonparametric "
        "test when possible. Return only Python code.\n\n"
        "ChromData access rules:\n"
        "- Do not index ChromData with string field paths like cdata['tracks.H3K27me3'].\n"
        "- Use cdata.spots, cdata.tracks, cdata.cells, cdata.cellm, cdata.coords directly.\n"
        "- To select spots by cell type, get cell IDs from cdata.cells and mask cdata.spots['cell_id'].\n"
        "- To combine spot-level tracks with RNA expression, aggregate tracks per cell_id first, then align to adata.obs_names.\n"
        "- AnnData access is allowed as adata[:, gene].X; convert sparse matrices with toarray().\n"
        "- Verification requires a finite numeric parameter_value. If the requested statistic is undefined because the selected sample is too small or an input is constant, compute a finite descriptive fallback effect size and record the fallback in analysis_summary['notes'].\n\n"
        f"IDEA JSON:\n{json.dumps(idea.to_dict(), indent=2)}\n\n"
        f"Schema summary:\n{schema_to_agent_context(schema, max_items=60)}"
    )
    payload = {
        "model": model,
        "max_output_tokens": OPENAI_CODE_MAX_OUTPUT_TOKENS,
        "input": [
            {
                "role": "system",
                "content": (
                    "You are a careful Python data scientist writing executable "
                    "notebook code for chromatin tracing multi-omics analysis."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        "text": {
            "format": {
                "type": "json_schema",
                "name": "uchrom_analysis_code",
                "strict": True,
                "schema": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["analysis_code"],
                    "properties": {"analysis_code": {"type": "string"}},
                },
            }
        },
    }
    _add_reasoning(payload, model=model, reasoning_effort=reasoning_effort)
    req = urllib.request.Request(
        OPENAI_RESPONSES_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"OpenAI request failed with HTTP {exc.code}: {body}") from exc
    parsed = json.loads(_extract_response_text(data))
    return str(parsed["analysis_code"])


def _resolve_model(model: str | None, env: Mapping[str, str]) -> str:
    return model or os.environ.get("OPENAI_MODEL") or env.get("OPENAI_MODEL") or DEFAULT_OPENAI_MODEL


def _resolve_reasoning_effort(reasoning_effort: str | None, env: Mapping[str, str]) -> str:
    return (
        reasoning_effort
        or os.environ.get("OPENAI_REASONING_EFFORT")
        or env.get("OPENAI_REASONING_EFFORT")
        or DEFAULT_OPENAI_REASONING_EFFORT
    )


def _add_reasoning(payload: dict[str, Any], *, model: str, reasoning_effort: str) -> None:
    if _supports_reasoning(model):
        payload["reasoning"] = {"effort": reasoning_effort}


def _supports_reasoning(model: str) -> bool:
    return model.startswith(("gpt-5", "o"))


def _read_env(path: str | Path) -> dict[str, str]:
    path = Path(path).expanduser()
    if not path.exists():
        return {}
    values: dict[str, str] = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip().strip('"').strip("'")
        values[key.strip()] = value
    return values


def _extract_response_text(data: Mapping[str, Any]) -> str:
    if data.get("output_text"):
        return str(data["output_text"])
    chunks: list[str] = []
    for item in data.get("output", []) or []:
        for content in item.get("content", []) or []:
            if "text" in content:
                chunks.append(str(content["text"]))
    if chunks:
        return "".join(chunks)
    output_types = [str(item.get("type", "")) for item in data.get("output", []) or []]
    details = {
        "status": data.get("status"),
        "incomplete_details": data.get("incomplete_details"),
        "output_types": output_types,
    }
    raise RuntimeError(f"OpenAI response did not contain output text: {json.dumps(details)}")


def _allowed_required_fields(schema: Mapping[str, Any], *, max_items: int) -> list[str]:
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


def _ideas_json_schema(*, max_ideas: int) -> dict[str, Any]:
    idea = {
        "type": "object",
        "additionalProperties": False,
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
        "properties": {
            "idea_title": {"type": "string"},
            "biological_hypothesis": {"type": "string"},
            "computable_parameter": {"type": "string"},
            "analysis_plan": {"type": "string"},
            "modalities": {
                "type": "array",
                "items": {"type": "string"},
                "minItems": 1,
            },
            "cell_types": {
                "type": "array",
                "items": {"type": "string"},
            },
            "required_fields": {
                "type": "array",
                "items": {"type": "string"},
                "minItems": 1,
            },
            "validation_checks": {
                "type": "array",
                "items": {"type": "string"},
                "minItems": 1,
            },
            "expected_direction": {"type": "string"},
            "complexity": {"type": "integer", "minimum": 1, "maximum": 5},
        },
    }
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["ideas"],
        "properties": {
            "ideas": {
                "type": "array",
                "items": idea,
                "minItems": 1,
                "maxItems": max_ideas,
            }
        },
    }
