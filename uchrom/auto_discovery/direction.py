"""Graph-aware direction planning for iterative auto-discovery.

Directions are not ideas themselves.  They are compact prompts that describe
where the next idea agents should search after reading the dataset schema and
the accumulated idea graph.  This keeps the direction layer flexible while
still making diversity, novelty, and prior evidence explicit.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Mapping

from .graph import IdeaGraph


@dataclass(frozen=True)
class DiscoveryDirection:
    """A graph-derived search direction for the next idea-agent batch."""

    direction_id: str
    direction_type: str
    priority: float
    title: str
    prompt: str
    rationale: str
    target_facets: dict[str, Any] = field(default_factory=dict)
    parent_idea_ids: list[str] = field(default_factory=list)
    evidence_basis: list[dict[str, Any]] = field(default_factory=list)
    novelty_notes: list[str] = field(default_factory=list)
    constraints: list[str] = field(default_factory=list)

    @property
    def frontier_id(self) -> str:
        """Legacy alias for callers that have not migrated yet."""
        return self.direction_id

    @property
    def frontier_type(self) -> str:
        """Legacy alias for callers that have not migrated yet."""
        return self.direction_type

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable direction record."""
        return asdict(self)


def plan_discovery_directions(
    graph: IdeaGraph,
    schema: Mapping[str, Any],
    *,
    max_directions: int = 8,
    min_priority: float = 0.0,
) -> list[DiscoveryDirection]:
    """Plan graph-aware directions for the next auto-discovery iteration.

    The planner reads tested idea signatures, hypothesis evidence, and schema
    catalogs.  It then proposes flexible search directions rather than fixed
    hard-coded buckets.  The direction prompts tell idea agents what evidence to
    build on or what coverage gaps to fill, while still allowing free-form idea
    generation and notebook exploration.
    """
    if max_directions <= 0:
        return []

    state = _graph_state(graph)
    schema_facets = _schema_facets(schema)
    candidates: list[DiscoveryDirection] = []

    candidates.extend(_evidence_follow_up_directions(state, schema_facets))
    candidates.extend(_coverage_gap_directions(state, schema_facets))
    candidates.extend(_cross_modal_directions(state, schema_facets, schema))
    candidates.extend(_cell_spatial_context_directions(state, schema_facets, schema))
    candidates.extend(_global_structure_directions(state, schema_facets, schema))
    candidates.extend(_knowledge_context_directions(state, schema))

    unique: dict[str, DiscoveryDirection] = {}
    for direction in candidates:
        if direction.priority < min_priority:
            continue
        key = _direction_key(direction)
        current = unique.get(key)
        if current is None or direction.priority > current.priority:
            unique[key] = direction

    return _diverse_direction_order(list(unique.values()), max_directions)


def directions_to_agent_context(directions: list[DiscoveryDirection]) -> str:
    """Render directions as a Markdown prompt block for idea agents."""
    if not directions:
        return "No graph-derived directions were planned."
    lines = ["# Graph-derived discovery directions", ""]
    for idx, direction in enumerate(directions, start=1):
        lines.extend([
            f"## {idx}. {direction.title}",
            "",
            f"- direction_id: `{direction.direction_id}`",
            f"- type: `{direction.direction_type}`",
            f"- priority: {direction.priority:.1f}",
            f"- parent_idea_ids: {', '.join(direction.parent_idea_ids) or 'none'}",
            f"- target_facets: `{json.dumps(direction.target_facets, sort_keys=True)}`",
            "",
            f"**Rationale.** {direction.rationale}",
            "",
            f"**Prompt.** {direction.prompt}",
        ])
        if direction.novelty_notes:
            lines.append("")
            lines.append("**Novelty notes.**")
            lines.extend(f"- {note}" for note in direction.novelty_notes)
        if direction.constraints:
            lines.append("")
            lines.append("**Constraints.**")
            lines.extend(f"- {constraint}" for constraint in direction.constraints)
        lines.append("")
    return "\n".join(lines).rstrip()


def write_direction_artifacts(
    directions: list[DiscoveryDirection],
    output_dir: str | Path,
    *,
    json_name: str = "next_directions.json",
    markdown_name: str = "next_directions.md",
    directory_name: str = "directions",
) -> dict[str, str]:
    """Write direction JSON and Markdown artifacts into ``output_dir``."""
    output_dir = Path(output_dir)
    direction_dir = output_dir / directory_name
    direction_dir.mkdir(parents=True, exist_ok=True)
    json_path = direction_dir / json_name
    markdown_path = direction_dir / markdown_name
    json_path.write_text(
        json.dumps([f.to_dict() for f in directions], indent=2, sort_keys=True) + "\n"
    )
    markdown_path.write_text(directions_to_agent_context(directions) + "\n")
    return {"directions_json": str(json_path), "directions_markdown": str(markdown_path)}


def _graph_state(graph: IdeaGraph) -> dict[str, Any]:
    ideas: dict[str, Mapping[str, Any]] = {}
    evidence: dict[str, Mapping[str, Any]] = {}
    for node in graph.nodes.values():
        if node.get("kind") == "Idea" and node.get("idea_id"):
            ideas[str(node["idea_id"])] = node
        elif node.get("kind") == "EvidenceResult" and node.get("idea_id"):
            evidence[str(node["idea_id"])] = node

    records = []
    for idea_id, idea in ideas.items():
        signature = dict(idea.get("signature") or {})
        ev = evidence.get(idea_id, {})
        records.append({
            "idea_id": idea_id,
            "title": idea.get("title", idea_id),
            "signature": signature,
            "hypothesis_status": ev.get("hypothesis_status", "Untested"),
            "p_value": ev.get("p_value"),
            "effect_size": ev.get("effect_size"),
            "evidence_summary": ev.get("summary", ""),
        })
    return {
        "ideas": ideas,
        "evidence": evidence,
        "records": records,
        "used_signatures": {_signature_key(r["signature"]) for r in records},
        "coverage": graph.summary().get("coverage", {}),
    }


def _schema_facets(schema: Mapping[str, Any]) -> dict[str, Any]:
    catalogs = schema.get("catalogs", {}) or {}
    modalities = schema.get("modalities", {}) or {}
    field_paths = _schema_field_paths(schema)
    return {
        "modalities": [
            str(name)
            for name, info in modalities.items()
            if isinstance(info, Mapping) and info.get("present")
        ],
        "cell_types": _catalog_values(catalogs.get("cell_types", {})),
        "markers": _catalog_values(catalogs.get("tracks", {})),
        "genes": _catalog_values(catalogs.get("genes", {})),
        "fields": field_paths,
        "cell_axis_fields": _cell_axis_field_paths(field_paths),
        "cell_spatial_fields": _cell_spatial_field_paths(field_paths),
        "spot_coordinate_fields": _spot_coordinate_field_paths(field_paths),
    }


def _evidence_follow_up_directions(
    state: Mapping[str, Any],
    schema_facets: Mapping[str, Any],
) -> list[DiscoveryDirection]:
    directions = []
    records = sorted(
        state["records"],
        key=lambda row: (
            _status_rank(row.get("hypothesis_status")),
            _p_sort(row.get("p_value")),
            str(row.get("title")),
        ),
    )
    for record in records[:8]:
        status = str(record.get("hypothesis_status", "Untested"))
        signature = record.get("signature") or {}
        idea_id = str(record["idea_id"])
        if status in {"Supported", "Borderline"}:
            title = f"Extend {status.lower()} signal: {record['title']}"
            direction_type = "evidence_extension"
            priority = 88.0 if status == "Supported" else 76.0
            prompt = (
                "Generate ideas that test whether this previously observed "
                "signal remains stable under a different cell type, marker, "
                "gene-expression bridge, chromosome subset, or normalization. "
                "Keep the parent signal recognizable, but do not repeat the "
                "same computable parameter."
            )
            novelty = [
                "Must change at least one of cell type, marker/gene, or parameter family.",
                "Prefer an orthogonal validation or a negative-control contrast.",
            ]
        elif status in {"Contradicted", "Not supported"}:
            title = f"Refine negative result: {record['title']}"
            direction_type = "negative_result_refinement"
            priority = 70.0 if status == "Contradicted" else 62.0
            prompt = (
                "Generate ideas that explain or refine this non-supporting "
                "result.  Consider opposite directionality, sparse-cell effects, "
                "cell-type mixing, marker quantile thresholds, or a nearby "
                "multi-omic surrogate.  The new idea must include a clear "
                "hypothesis test and a control against overfitting the previous "
                "negative result."
            )
            novelty = [
                "Treat the previous result as evidence, not as a failure to ignore.",
                "Use a different operational definition or a stronger control.",
            ]
        else:
            continue
        directions.append(_make_direction(
            direction_type=direction_type,
            priority=priority,
            title=title,
            prompt=prompt,
            rationale=(
                f"Prior notebook evidence for `{record['title']}` was classified "
                f"as {status}; p={record.get('p_value')}, effect={record.get('effect_size')}."
            ),
            target_facets=_target_facets_from_signature(signature, schema_facets),
            parent_idea_ids=[idea_id],
            evidence_basis=[_evidence_basis(record)],
            novelty_notes=novelty,
            constraints=_standard_constraints(),
        ))
    return directions


def _coverage_gap_directions(
    state: Mapping[str, Any],
    schema_facets: Mapping[str, Any],
) -> list[DiscoveryDirection]:
    coverage = state.get("coverage", {})
    directions = []
    for facet_name, schema_key, label in [
        ("cell_types", "cell_types", "cell type"),
        ("markers", "markers", "IF marker"),
        ("genes", "genes", "RNA gene"),
    ]:
        available = list(schema_facets.get(schema_key, []))
        if not available:
            continue
        used = set((coverage.get(facet_name) or {}).keys())
        gaps = [value for value in available if value not in used][:5]
        if not gaps:
            continue
        target = {
            facet_name: gaps,
            "modalities": _default_modalities_for_gap(schema_key, schema_facets),
        }
        directions.append(_make_direction(
            direction_type="coverage_gap",
            priority=58.0 + min(12.0, len(gaps) * 2.0),
            title=f"Explore under-tested {label}s",
            prompt=(
                f"Generate diverse ideas around under-tested {label}s: "
                f"{', '.join(gaps[:5])}. Combine them with available chromatin "
                "tracing geometry and, when relevant, IF tracks or linked RNA. "
                "Avoid repeating existing idea signatures in the graph."
            ),
            rationale=(
                f"The graph has little or no tested coverage for these {label}s "
                "despite their presence in the h5cd-backed schema."
            ),
            target_facets=target,
            novelty_notes=[
                "Use the graph coverage counts to avoid already explored facets.",
                "Prefer combinations that add a new modality or parameter family.",
            ],
            constraints=_standard_constraints(),
        ))
    return directions


def _cross_modal_directions(
    state: Mapping[str, Any],
    schema_facets: Mapping[str, Any],
    schema: Mapping[str, Any],
) -> list[DiscoveryDirection]:
    modalities = set(schema_facets.get("modalities", []))
    if not {"chromatin_tracing", "rna_expression"}.issubset(modalities):
        return []
    genes = list(schema_facets.get("genes", []))
    markers = list(schema_facets.get("markers", []))
    if not genes:
        return []
    used_genes = set((state.get("coverage", {}).get("genes") or {}).keys())
    unused_genes = [gene for gene in genes if gene not in used_genes][:8]
    if not unused_genes:
        unused_genes = genes[:5]
    facets = {
        "modalities": ["chromatin_tracing", "rna_expression"],
        "genes": unused_genes[:5],
        "markers": markers[:8],
    }
    if "if_tracks" in modalities:
        facets["modalities"].append("if_tracks")
    return [_make_direction(
        direction_type="cross_modal_bridge",
        priority=74.0,
        title="Link RNA expression to chromatin tracing phenotypes",
        prompt=(
            "Generate ideas that use linked_adata gene expression as the cell-level "
            "variable and chromatin tracing or IF-track features as spatial "
            "responses.  Select genes from the schema, justify why the gene is "
            "biologically meaningful for the cell types, and require a permutation "
            "or rank-based hypothesis test."
        ),
        rationale=(
            "The h5cd has linked RNA observations, so the next iteration should "
            "not only test IF-marker geometry; it should also ask whether cell-level "
            "expression predicts spatial chromatin features."
        ),
        target_facets=facets,
        novelty_notes=[
            "Prefer genes not already used by prior ideas.",
            "Pair expression with a spatial endpoint, not only another expression summary.",
        ],
        constraints=[
            *_standard_constraints(),
            "Validate cell_id alignment between cdata.cells and cdata.linked_adata.obs_names.",
        ],
    )]


def _cell_spatial_context_directions(
    _state: Mapping[str, Any],
    schema_facets: Mapping[str, Any],
    schema: Mapping[str, Any],
) -> list[DiscoveryDirection]:
    modalities = set(schema_facets.get("modalities", []))
    if "chromatin_tracing" not in modalities:
        return []
    usable_modalities = ["chromatin_tracing"]
    if "cell_metadata" in modalities:
        usable_modalities.append("cell_metadata")
    if "if_tracks" in modalities:
        usable_modalities.append("if_tracks")
    if "rna_expression" in modalities:
        usable_modalities.append("rna_expression")

    cell_spatial_fields = list(schema_facets.get("cell_spatial_fields", []))
    coordinate_fields = list(schema_facets.get("spot_coordinate_fields", []))
    cell_axis_fields = list(schema_facets.get("cell_axis_fields", []))
    priority = 82.0 if cell_spatial_fields else 68.0
    if "cell_metadata" not in modalities:
        priority -= 10.0

    field_hint = (
        "The schema exposes candidate cell spatial fields, so prioritize direct "
        "cell position or neighborhood tests."
        if cell_spatial_fields
        else (
            "No explicit tissue XY or cell-centroid field is visible in the "
            "schema summary; the agent must first inspect the h5cd schema and "
            "then use only schema-valid proxies if direct cell spatial context "
            "is absent."
        )
    )
    return [_make_direction(
        direction_type="cell_spatial_context",
        priority=priority,
        title="Add cell-spatial context beyond cell-type labels",
        prompt=(
            "Generate ideas that test whether cell-level spatial context, local "
            "neighborhood composition, tissue position, density, or boundary "
            "proximity predicts chromatin tracing or IF/RNA spatial endpoints. "
            "Do not only compare named cell types. Treat cell_type as a covariate, "
            "matched control, or secondary annotation, and make the primary "
            "computable parameter position- or neighborhood-aware whenever the "
            "schema supports it."
        ),
        rationale=(
            "The current graph can over-concentrate on marker and cell-type "
            f"contrasts. {field_hint}"
        ),
        target_facets={
            "modalities": usable_modalities,
            "cell_spatial_fields": cell_spatial_fields[:12],
            "spot_coordinate_fields": coordinate_fields[:8],
            "cell_axis_fields": cell_axis_fields[:12],
            "candidate_contexts": [
                "cell centroid or tissue position",
                "local cell-type neighborhood composition",
                "cell density or boundary proximity",
                "cellm embedding as a non-physical fallback",
            ],
            "n_cells": (schema.get("summary") or {}).get("n_cells"),
        },
        novelty_notes=[
            "Move beyond single-cell-type stratification toward cell-context tests.",
            "Prefer a local-neighborhood, tissue-position, or spatial-label permutation control.",
        ],
        constraints=[
            *_standard_constraints(),
            (
                "Start by listing schema-valid cell spatial candidates from "
                "target_facets.cell_spatial_fields; if none are available, "
                "explicitly report that no direct tissue XY or centroid field "
                "was found before using a proxy."
            ),
            "Treat cell_type as a control/covariate rather than the only hypothesis axis.",
        ],
    )]


def _global_structure_directions(
    _state: Mapping[str, Any],
    schema_facets: Mapping[str, Any],
    schema: Mapping[str, Any],
) -> list[DiscoveryDirection]:
    modalities = set(schema_facets.get("modalities", []))
    if "chromatin_tracing" not in modalities:
        return []
    usable_modalities = ["chromatin_tracing"]
    if "if_tracks" in modalities:
        usable_modalities.append("if_tracks")
    if "rna_expression" in modalities:
        usable_modalities.append("rna_expression")
    if "cell_metadata" in modalities:
        usable_modalities.append("cell_metadata")

    return [_make_direction(
        direction_type="global_structure",
        priority=80.0,
        title="Search for pan-cell global chromatin structure",
        prompt=(
            "Generate ideas whose primary hypothesis is computed across all "
            "eligible cells or traces rather than within one named cell type. "
            "Build a global or pan-cell metric such as radial organization, "
            "chromosome mixing, assortativity, nuclear compaction, spatial "
            "entropy, or a low-dimensional chromatin-organization axis. Cell "
            "types can be used for sensitivity analysis or annotation, but the "
            "main endpoint should be a dataset-wide structure test."
        ),
        rationale=(
            "The next iteration should include global structure discovery, not "
            "only local follow-ups or under-tested cell-type buckets."
        ),
        target_facets={
            "modalities": usable_modalities,
            "candidate_parameters": [
                "pan-cell radial organization score",
                "chromosome mixing or assortativity",
                "nuclear compaction or spatial entropy",
                "cell-level chromatin organization manifold",
            ],
            "controls": [
                "shuffle genomic labels or cell labels",
                "cell-type sensitivity after the primary pan-cell test",
                "matched missing-data threshold across cells",
            ],
            "n_cells": (schema.get("summary") or {}).get("n_cells"),
            "n_traces": (schema.get("summary") or {}).get("n_traces"),
        },
        novelty_notes=[
            "The primary contrast should be pan-cell/global, not a pairwise cell-type comparison.",
            "Use cell type only after the global statistic is defined.",
        ],
        constraints=[
            *_standard_constraints(),
            "Do not make the primary hypothesis a pairwise cell-type contrast.",
            "Report the cell inclusion rule, missing-data handling, and global null model.",
        ],
    )]


def _knowledge_context_directions(
    state: Mapping[str, Any],
    schema: Mapping[str, Any],
) -> list[DiscoveryDirection]:
    refs = list(schema.get("references") or [])
    anns = list(schema.get("user_annotations") or [])
    if not refs and not anns:
        return []
    labels = []
    for ref in refs[:3]:
        title = str(ref.get("title") or ref.get("doi") or ref.get("url") or "reference")
        labels.append(title)
    for ann in anns[:3]:
        text = str(ann.get("text") or ann.get("scope") or "annotation")
        labels.append(text[:80])
    return [_make_direction(
        direction_type="knowledge_seed_expansion",
        priority=66.0,
        title="Expand from dataset references and user annotations",
        prompt=(
            "Generate ideas grounded in the dataset's associated literature and "
            "user annotations stored in the h5cd schema.  Cite the relevant "
            "reference_id or annotation_id in idea.metadata.source_claim_ids "
            "or idea.metadata.user_annotation_ids when possible."
        ),
        rationale=(
            "The schema includes external knowledge seeds that should influence "
            "idea generation rather than relying only on column names."
        ),
        target_facets={"knowledge_seeds": labels},
        novelty_notes=["Use literature/user priors to motivate a new testable contrast."],
        constraints=_standard_constraints(),
    )]


def _make_direction(
    *,
    direction_type: str,
    priority: float,
    title: str,
    prompt: str,
    rationale: str,
    target_facets: Mapping[str, Any] | None = None,
    parent_idea_ids: list[str] | None = None,
    evidence_basis: list[dict[str, Any]] | None = None,
    novelty_notes: list[str] | None = None,
    constraints: list[str] | None = None,
) -> DiscoveryDirection:
    payload = {
        "direction_type": direction_type,
        "title": title,
        "target_facets": target_facets or {},
        "parent_idea_ids": parent_idea_ids or [],
    }
    digest = hashlib.sha1(
        json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()[:10]
    return DiscoveryDirection(
        direction_id=f"{direction_type}-{digest}",
        direction_type=direction_type,
        priority=float(priority),
        title=str(title),
        prompt=str(prompt),
        rationale=str(rationale),
        target_facets=dict(target_facets or {}),
        parent_idea_ids=list(parent_idea_ids or []),
        evidence_basis=list(evidence_basis or []),
        novelty_notes=list(novelty_notes or []),
        constraints=list(constraints or []),
    )


def _evidence_basis(record: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "idea_id": record.get("idea_id"),
        "title": record.get("title"),
        "hypothesis_status": record.get("hypothesis_status"),
        "p_value": record.get("p_value"),
        "effect_size": record.get("effect_size"),
    }


def _target_facets_from_signature(
    signature: Mapping[str, Any],
    schema_facets: Mapping[str, Any],
) -> dict[str, Any]:
    facets = {
        "modalities": list(signature.get("modalities") or []),
        "cell_types": list(signature.get("cell_types") or []),
        "markers": list(signature.get("markers") or []),
        "genes": list(signature.get("genes") or []),
        "parameter_family": signature.get("parameter_family"),
    }
    if not facets["modalities"]:
        facets["modalities"] = list(schema_facets.get("modalities", []))[:3]
    return facets


def _default_modalities_for_gap(schema_key: str, schema_facets: Mapping[str, Any]) -> list[str]:
    modalities = ["chromatin_tracing"]
    available = set(schema_facets.get("modalities", []))
    if schema_key == "markers" and "if_tracks" in available:
        modalities.append("if_tracks")
    if schema_key == "genes" and "rna_expression" in available:
        modalities.append("rna_expression")
    if schema_key == "cell_types" and "cell_metadata" in available:
        modalities.append("cell_metadata")
    return modalities


def _standard_constraints() -> list[str]:
    return [
        "The final idea must be schema-valid against the h5cd-backed discovery schema.",
        "The notebook agent must run code in a notebook, include a statistical test, and report p-value/effect size.",
        "The analysis should include a control, permutation, bootstrap, or matched comparison when feasible.",
    ]


def _catalog_values(catalog: Mapping[str, Any] | Any) -> list[str]:
    if not isinstance(catalog, Mapping):
        return []
    values = catalog.get("values")
    if isinstance(values, list):
        return [str(value) for value in values]
    counts = catalog.get("counts")
    if isinstance(counts, Mapping):
        return [str(key) for key in counts.keys()]
    return []


def _schema_field_paths(schema: Mapping[str, Any]) -> list[str]:
    paths: set[str] = set()
    fields = schema.get("fields", {}) or {}
    if isinstance(fields, Mapping):
        for field_name, info in fields.items():
            name = str(field_name)
            paths.add(name)
            if not isinstance(info, Mapping):
                continue
            for column in info.get("columns") or []:
                paths.add(f"{name}.{column}")
            for key in info.get("keys") or []:
                paths.add(f"{name}.{key}")

    linked = schema.get("linked_adata", {}) or {}
    if isinstance(linked, Mapping) and linked.get("present"):
        paths.update({"linked_adata", "linked_adata.X", "linked_adata.obs_names"})
        for column in linked.get("obs_columns") or []:
            paths.add(f"linked_adata.obs.{column}")
        for column in linked.get("var_columns") or []:
            paths.add(f"linked_adata.var.{column}")
        for key in linked.get("obsm") or []:
            paths.add(f"linked_adata.obsm.{key}")
        for key in linked.get("layers") or []:
            paths.add(f"linked_adata.layers.{key}")

    modalities = schema.get("modalities", {}) or {}
    if isinstance(modalities, Mapping):
        for info in modalities.values():
            if isinstance(info, Mapping):
                paths.update(str(value) for value in info.get("fields") or [])

    return sorted(path for path in paths if path)


def _cell_axis_field_paths(paths: list[str]) -> list[str]:
    prefixes = ("cells.", "cellm.", "linked_adata.obs.", "linked_adata.obsm.")
    return [path for path in paths if path.startswith(prefixes)]


def _cell_spatial_field_paths(paths: list[str]) -> list[str]:
    tokens = (
        "spatial",
        "coord",
        "coordinate",
        "centroid",
        "position",
        "pos",
        "x",
        "y",
        "z",
        "row",
        "col",
        "pixel",
        "umap",
        "embedding",
        "neighbor",
        "neighbour",
        "density",
    )
    spatial_paths = []
    for path in _cell_axis_field_paths(paths):
        lower = path.lower()
        tail = lower.rsplit(".", 1)[-1]
        if any(_matches_spatial_token(tail, token) for token in tokens):
            spatial_paths.append(path)
    return sorted(spatial_paths, key=_cell_spatial_sort_key)


def _matches_spatial_token(tail: str, token: str) -> bool:
    if len(token) == 1:
        parts = tail.replace("-", "_").split("_")
        return token in parts
    return token == tail or token in tail


def _cell_spatial_sort_key(path: str) -> tuple[int, str]:
    lower = path.lower()
    tail = lower.rsplit(".", 1)[-1]
    direct_coordinate = (
        "centroid" in tail
        or "spatial" in tail
        or "coord" in tail
        or "position" in tail
        or tail in {"x", "y", "z", "row", "col"}
    )
    if lower.startswith("cells.") and direct_coordinate:
        return (0, lower)
    if lower.startswith("linked_adata.obs.") and direct_coordinate:
        return (1, lower)
    if lower.startswith(("cellm.", "linked_adata.obsm.")):
        return (3, lower)
    return (2, lower)


def _spot_coordinate_field_paths(paths: list[str]) -> list[str]:
    out = []
    for path in paths:
        lower = path.lower()
        tail = lower.rsplit(".", 1)[-1]
        if lower == "coords" or (
            lower.startswith("spots.")
            and tail in {"x", "y", "z", "row", "col", "position", "centroid"}
        ):
            out.append(path)
    return out


def _direction_key(direction: DiscoveryDirection) -> str:
    return json.dumps({
        "type": direction.direction_type,
        "target_facets": direction.target_facets,
        "parents": direction.parent_idea_ids,
    }, sort_keys=True, default=str)


def _diverse_direction_order(
    directions: list[DiscoveryDirection],
    max_directions: int,
) -> list[DiscoveryDirection]:
    by_priority = sorted(directions, key=lambda item: (-item.priority, item.title))
    selected: list[DiscoveryDirection] = []
    selected_ids: set[str] = set()
    preferred_types = [
        "evidence_extension",
        "cell_spatial_context",
        "global_structure",
        "cross_modal_bridge",
        "coverage_gap",
        "negative_result_refinement",
        "knowledge_seed_expansion",
    ]
    for direction_type in preferred_types:
        match = next((f for f in by_priority if f.direction_type == direction_type), None)
        if match is not None and match.direction_id not in selected_ids:
            selected.append(match)
            selected_ids.add(match.direction_id)
        if len(selected) >= max_directions:
            return selected
    for direction in by_priority:
        if direction.direction_id in selected_ids:
            continue
        selected.append(direction)
        selected_ids.add(direction.direction_id)
        if len(selected) >= max_directions:
            break
    return selected


def _signature_key(signature: Mapping[str, Any]) -> str:
    return json.dumps({
        "modalities": sorted(map(str, signature.get("modalities", []))),
        "cell_types": sorted(map(str, signature.get("cell_types", []))),
        "markers": sorted(map(str, signature.get("markers", []))),
        "genes": sorted(map(str, signature.get("genes", []))),
        "parameter_family": signature.get("parameter_family"),
    }, sort_keys=True)


def _status_rank(status: Any) -> int:
    order = {
        "Supported": 0,
        "Borderline": 1,
        "Contradicted": 2,
        "Not supported": 3,
        "Inconclusive": 4,
        "Untested": 5,
    }
    return order.get(str(status), 6)


def _p_sort(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float("inf")
