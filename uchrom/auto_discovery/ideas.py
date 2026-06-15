"""Idea records and schema-based review for auto-discovery."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, field
from typing import Any, Mapping


@dataclass
class DiscoveryIdea:
    """A computable multi-omics discovery idea."""

    idea_title: str
    biological_hypothesis: str
    computable_parameter: str
    analysis_plan: str
    modalities: list[str]
    idea_markdown: str = ""
    cell_types: list[str] = field(default_factory=list)
    required_fields: list[str] = field(default_factory=list)
    validation_checks: list[str] = field(default_factory=list)
    expected_direction: str = ""
    complexity: int = 3
    idea_id: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.idea_markdown = str(self.idea_markdown or "")
        self.modalities = [str(x) for x in self.modalities]
        self.cell_types = [str(x) for x in self.cell_types]
        self.required_fields = [str(x) for x in self.required_fields]
        self.validation_checks = [str(x) for x in self.validation_checks]
        self.complexity = int(self.complexity)
        if not 1 <= self.complexity <= 5:
            raise ValueError("complexity must be between 1 and 5")
        if not self.idea_id:
            self.idea_id = stable_idea_id(self.to_dict(include_id=False))

    def to_dict(self, *, include_id: bool = True) -> dict[str, Any]:
        data = asdict(self)
        if not include_id:
            data.pop("idea_id", None)
        return data

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "DiscoveryIdea":
        return cls(**dict(data))


@dataclass
class IdeaReview:
    """Result of reviewing an idea against a discovery schema."""

    accepted: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    missing_fields: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def stable_idea_id(idea: Mapping[str, Any]) -> str:
    """Return a stable short id for an idea dict."""
    title = str(idea.get("idea_title", "idea")).lower()
    slug = re.sub(r"[^a-z0-9]+", "-", title).strip("-")[:48] or "idea"
    payload = json.dumps(idea, sort_keys=True, default=str)
    digest = hashlib.sha1(payload.encode("utf-8")).hexdigest()[:10]
    return f"{slug}-{digest}"


def review_idea_against_schema(
    idea: DiscoveryIdea | Mapping[str, Any],
    schema: Mapping[str, Any],
    *,
    min_complexity: int = 1,
    max_complexity: int = 5,
) -> IdeaReview:
    """Check whether an idea is compatible with a discovery schema."""
    if not isinstance(idea, DiscoveryIdea):
        idea = DiscoveryIdea.from_dict(idea)

    errors: list[str] = []
    warnings: list[str] = []
    missing_fields: list[str] = []

    if not idea.idea_title.strip():
        errors.append("idea_title is empty")
    if not idea.biological_hypothesis.strip():
        errors.append("biological_hypothesis is empty")
    if not idea.computable_parameter.strip():
        errors.append("computable_parameter is empty")
    if not idea.analysis_plan.strip():
        errors.append("analysis_plan is empty")
    if not (min_complexity <= idea.complexity <= max_complexity):
        errors.append(f"complexity {idea.complexity} outside allowed range")

    modalities = schema.get("modalities", {})
    for modality in idea.modalities:
        info = modalities.get(modality)
        if info is None:
            errors.append(f"unknown modality: {modality}")
        elif not info.get("present"):
            errors.append(f"modality is not present in this h5cd: {modality}")

    known_cell_types = set((schema.get("catalogs", {}).get("cell_types", {}) or {}).get("values", []))
    for cell_type in idea.cell_types:
        if known_cell_types and cell_type not in known_cell_types:
            errors.append(f"unknown cell_type: {cell_type}")

    for field_name in idea.required_fields:
        if not _field_exists(field_name, schema):
            missing_fields.append(field_name)
    if missing_fields:
        errors.append("required field(s) not found: " + ", ".join(missing_fields))

    if not idea.validation_checks:
        warnings.append("idea has no explicit validation_checks")
    if "rna_expression" in idea.modalities and "linked_adata.X" not in idea.required_fields:
        errors.append("rna_expression modality requires linked_adata.X in required_fields")
    if len(idea.modalities) >= 2 and "cell_id_alignment" not in idea.validation_checks:
        warnings.append("multi-modal idea should include a cell_id_alignment validation check")

    return IdeaReview(
        accepted=not errors,
        errors=errors,
        warnings=warnings,
        missing_fields=missing_fields,
    )


def _field_exists(field_name: str, schema: Mapping[str, Any]) -> bool:
    if field_name == "coords":
        return bool(schema.get("fields", {}).get("coords"))
    fields = schema.get("fields", {})
    catalogs = schema.get("catalogs", {})
    if "." not in field_name:
        return field_name in fields
    prefix, suffix = field_name.split(".", 1)
    if prefix in {"spots", "tracks", "cells", "traces"}:
        return suffix in (fields.get(prefix, {}) or {}).get("columns", [])
    if prefix in {"cellm", "layers"}:
        return suffix in (fields.get(prefix, {}) or {}).get("keys", [])
    if prefix == "linked_adata":
        linked = schema.get("linked_adata", {})
        if not linked.get("present"):
            return False
        if suffix in {"X", "obs", "var", "obs_names", "var_names"}:
            return True
        if suffix.startswith("obs."):
            return suffix[4:] in linked.get("obs_columns", [])
        if suffix.startswith("var."):
            gene = suffix[4:]
            gene_catalog = catalogs.get("genes", {}) or {}
            return gene in gene_catalog.get("values", [])
        if suffix.startswith("layers."):
            return suffix[7:] in linked.get("layers", [])
    return False
