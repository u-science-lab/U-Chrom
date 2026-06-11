"""Graph-aware frontier planning for iterative auto-discovery.

Frontiers are not ideas themselves.  They are compact prompts that describe
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
class DiscoveryFrontier:
    """A graph-derived search direction for the next idea-agent batch."""

    frontier_id: str
    frontier_type: str
    priority: float
    title: str
    prompt: str
    rationale: str
    target_facets: dict[str, Any] = field(default_factory=dict)
    parent_idea_ids: list[str] = field(default_factory=list)
    evidence_basis: list[dict[str, Any]] = field(default_factory=list)
    novelty_notes: list[str] = field(default_factory=list)
    constraints: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable frontier record."""
        return asdict(self)


def plan_discovery_frontiers(
    graph: IdeaGraph,
    schema: Mapping[str, Any],
    *,
    max_frontiers: int = 8,
    min_priority: float = 0.0,
) -> list[DiscoveryFrontier]:
    """Plan graph-aware frontiers for the next auto-discovery iteration.

    The planner reads tested idea signatures, hypothesis evidence, and schema
    catalogs.  It then proposes flexible search frontiers rather than fixed
    hard-coded buckets.  The frontier prompts tell idea agents what evidence to
    build on or what coverage gaps to fill, while still allowing free-form idea
    generation and notebook exploration.
    """
    if max_frontiers <= 0:
        return []

    state = _graph_state(graph)
    schema_facets = _schema_facets(schema)
    candidates: list[DiscoveryFrontier] = []

    candidates.extend(_evidence_follow_up_frontiers(state, schema_facets))
    candidates.extend(_coverage_gap_frontiers(state, schema_facets))
    candidates.extend(_cross_modal_frontiers(state, schema_facets, schema))
    candidates.extend(_knowledge_context_frontiers(state, schema))

    unique: dict[str, DiscoveryFrontier] = {}
    for frontier in candidates:
        if frontier.priority < min_priority:
            continue
        key = _frontier_key(frontier)
        current = unique.get(key)
        if current is None or frontier.priority > current.priority:
            unique[key] = frontier

    return _diverse_frontier_order(list(unique.values()), max_frontiers)


def frontiers_to_agent_context(frontiers: list[DiscoveryFrontier]) -> str:
    """Render frontiers as a Markdown prompt block for idea agents."""
    if not frontiers:
        return "No graph-derived frontiers were planned."
    lines = ["# Graph-derived discovery frontiers", ""]
    for idx, frontier in enumerate(frontiers, start=1):
        lines.extend([
            f"## {idx}. {frontier.title}",
            "",
            f"- frontier_id: `{frontier.frontier_id}`",
            f"- type: `{frontier.frontier_type}`",
            f"- priority: {frontier.priority:.1f}",
            f"- parent_idea_ids: {', '.join(frontier.parent_idea_ids) or 'none'}",
            f"- target_facets: `{json.dumps(frontier.target_facets, sort_keys=True)}`",
            "",
            f"**Rationale.** {frontier.rationale}",
            "",
            f"**Prompt.** {frontier.prompt}",
        ])
        if frontier.novelty_notes:
            lines.append("")
            lines.append("**Novelty notes.**")
            lines.extend(f"- {note}" for note in frontier.novelty_notes)
        if frontier.constraints:
            lines.append("")
            lines.append("**Constraints.**")
            lines.extend(f"- {constraint}" for constraint in frontier.constraints)
        lines.append("")
    return "\n".join(lines).rstrip()


def write_frontier_artifacts(
    frontiers: list[DiscoveryFrontier],
    output_dir: str | Path,
    *,
    json_name: str = "next_frontiers.json",
    markdown_name: str = "next_frontiers.md",
) -> dict[str, str]:
    """Write frontier JSON and Markdown artifacts into ``output_dir``."""
    output_dir = Path(output_dir)
    frontier_dir = output_dir / "frontiers"
    frontier_dir.mkdir(parents=True, exist_ok=True)
    json_path = frontier_dir / json_name
    markdown_path = frontier_dir / markdown_name
    json_path.write_text(
        json.dumps([f.to_dict() for f in frontiers], indent=2, sort_keys=True) + "\n"
    )
    markdown_path.write_text(frontiers_to_agent_context(frontiers) + "\n")
    return {"frontiers_json": str(json_path), "frontiers_markdown": str(markdown_path)}


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
    return {
        "modalities": [
            str(name)
            for name, info in modalities.items()
            if isinstance(info, Mapping) and info.get("present")
        ],
        "cell_types": _catalog_values(catalogs.get("cell_types", {})),
        "markers": _catalog_values(catalogs.get("tracks", {})),
        "genes": _catalog_values(catalogs.get("genes", {})),
    }


def _evidence_follow_up_frontiers(
    state: Mapping[str, Any],
    schema_facets: Mapping[str, Any],
) -> list[DiscoveryFrontier]:
    frontiers = []
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
            frontier_type = "evidence_extension"
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
            frontier_type = "negative_result_refinement"
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
        frontiers.append(_make_frontier(
            frontier_type=frontier_type,
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
    return frontiers


def _coverage_gap_frontiers(
    state: Mapping[str, Any],
    schema_facets: Mapping[str, Any],
) -> list[DiscoveryFrontier]:
    coverage = state.get("coverage", {})
    frontiers = []
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
        frontiers.append(_make_frontier(
            frontier_type="coverage_gap",
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
    return frontiers


def _cross_modal_frontiers(
    state: Mapping[str, Any],
    schema_facets: Mapping[str, Any],
    schema: Mapping[str, Any],
) -> list[DiscoveryFrontier]:
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
    return [_make_frontier(
        frontier_type="cross_modal_bridge",
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


def _knowledge_context_frontiers(
    state: Mapping[str, Any],
    schema: Mapping[str, Any],
) -> list[DiscoveryFrontier]:
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
    return [_make_frontier(
        frontier_type="knowledge_seed_expansion",
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


def _make_frontier(
    *,
    frontier_type: str,
    priority: float,
    title: str,
    prompt: str,
    rationale: str,
    target_facets: Mapping[str, Any] | None = None,
    parent_idea_ids: list[str] | None = None,
    evidence_basis: list[dict[str, Any]] | None = None,
    novelty_notes: list[str] | None = None,
    constraints: list[str] | None = None,
) -> DiscoveryFrontier:
    payload = {
        "frontier_type": frontier_type,
        "title": title,
        "target_facets": target_facets or {},
        "parent_idea_ids": parent_idea_ids or [],
    }
    digest = hashlib.sha1(
        json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()[:10]
    return DiscoveryFrontier(
        frontier_id=f"{frontier_type}-{digest}",
        frontier_type=frontier_type,
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


def _frontier_key(frontier: DiscoveryFrontier) -> str:
    return json.dumps({
        "type": frontier.frontier_type,
        "target_facets": frontier.target_facets,
        "parents": frontier.parent_idea_ids,
    }, sort_keys=True, default=str)


def _diverse_frontier_order(
    frontiers: list[DiscoveryFrontier],
    max_frontiers: int,
) -> list[DiscoveryFrontier]:
    by_priority = sorted(frontiers, key=lambda item: (-item.priority, item.title))
    selected: list[DiscoveryFrontier] = []
    selected_ids: set[str] = set()
    preferred_types = [
        "evidence_extension",
        "cross_modal_bridge",
        "coverage_gap",
        "negative_result_refinement",
        "knowledge_seed_expansion",
    ]
    for frontier_type in preferred_types:
        match = next((f for f in by_priority if f.frontier_type == frontier_type), None)
        if match is not None and match.frontier_id not in selected_ids:
            selected.append(match)
            selected_ids.add(match.frontier_id)
        if len(selected) >= max_frontiers:
            return selected
    for frontier in by_priority:
        if frontier.frontier_id in selected_ids:
            continue
        selected.append(frontier)
        selected_ids.add(frontier.frontier_id)
        if len(selected) >= max_frontiers:
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
