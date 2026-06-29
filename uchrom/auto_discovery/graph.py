"""Lightweight idea graph for iterative auto-discovery.

The graph is intentionally stored as plain JSON-friendly nodes and edges so it
can be written to run directories without adding a hard graph dependency.  It
is the shared memory layer between discovery iterations: ideas, reviews,
notebook runs, evidence, data facets, and source priors are represented as
typed nodes with explicit relationships.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

from .evidence import classify_hypothesis_evidence
from .ideas import DiscoveryIdea


@dataclass
class IdeaGraph:
    """A JSON-serializable graph of discovery ideas and evidence."""

    graph_id: str = "idea_graph"
    nodes: dict[str, dict[str, Any]] = field(default_factory=dict)
    edges: list[dict[str, Any]] = field(default_factory=list)

    def add_node(self, node_id: str, kind: str, **attrs: Any) -> dict[str, Any]:
        """Add or update a node and return the stored record."""
        node_id = str(node_id)
        node = self.nodes.setdefault(node_id, {"id": node_id, "kind": str(kind)})
        node["kind"] = str(kind)
        for key, value in attrs.items():
            if value is not None:
                node[key] = _jsonable(value)
        return node

    def add_edge(self, source: str, relation: str, target: str, **attrs: Any) -> dict[str, Any]:
        """Add a typed edge unless the same edge already exists."""
        edge = {
            "source": str(source),
            "relation": str(relation),
            "target": str(target),
        }
        for key, value in attrs.items():
            if value is not None:
                edge[key] = _jsonable(value)
        for existing in self.edges:
            if all(existing.get(k) == edge.get(k) for k in ("source", "relation", "target")):
                existing.update(edge)
                return existing
        self.edges.append(edge)
        return edge

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable graph dict."""
        return {
            "graph_id": self.graph_id,
            "nodes": list(self.nodes.values()),
            "edges": self.edges,
            "summary": self.summary(),
        }

    def summary(self) -> dict[str, Any]:
        """Return lightweight counts useful for planning and h5cd pointers."""
        kinds = Counter(node.get("kind") for node in self.nodes.values())
        relations = Counter(edge.get("relation") for edge in self.edges)
        evidence = Counter(
            node.get("hypothesis_status")
            for node in self.nodes.values()
            if node.get("kind") == "EvidenceResult"
        )
        coverage = {
            "cell_types": _node_label_counts(self.nodes.values(), "CellType"),
            "genes": _node_label_counts(self.nodes.values(), "Gene"),
            "markers": _node_label_counts(self.nodes.values(), "IFMarker"),
            "modalities": _node_label_counts(self.nodes.values(), "Modality"),
            "parameter_families": _node_label_counts(self.nodes.values(), "ParameterFamily"),
        }
        return {
            "n_nodes": len(self.nodes),
            "n_edges": len(self.edges),
            "node_kinds": dict(sorted(kinds.items())),
            "edge_relations": dict(sorted(relations.items())),
            "hypothesis_status": dict(sorted((k, v) for k, v in evidence.items() if k)),
            "coverage": coverage,
        }

    def write_json(self, path: str | Path) -> Path:
        """Write graph JSON to ``path``."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=2, sort_keys=True, default=str) + "\n")
        return path

    def write_summary_markdown(self, path: str | Path) -> Path:
        """Write a human-readable graph summary."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(graph_summary_markdown(self) + "\n")
        return path


def build_idea_graph_from_run(
    run_dir: str | Path,
    *,
    graph_id: str | None = None,
    claims_paths: list[str | Path] | None = None,
    selected_only: bool = False,
) -> IdeaGraph:
    """Build an :class:`IdeaGraph` from a completed auto-discovery run.

    The function reads ``ideas.jsonl``, ``reviews.jsonl``, and
    ``results.jsonl`` when present.  Missing files are tolerated so interrupted
    runs can still produce partial graph snapshots.

    When ``selected_only`` is true and an ``idea_diversity_report.json`` exists,
    the graph is limited to the ideas chosen by the diversity selector.  This
    keeps exported iterative graphs focused on the executed discovery route
    while preserving all generated candidates in the raw run artifacts.
    """
    run_dir = Path(run_dir)
    graph = IdeaGraph(graph_id=graph_id or f"run:{run_dir.name}")
    run_node = f"run:{run_dir.name}"
    selected_idea_ids = _read_selected_idea_ids_if_exists(run_dir) if selected_only else None
    graph.add_node(
        run_node,
        "Run",
        path=str(run_dir),
        selected_only=selected_only,
        selected_idea_count=len(selected_idea_ids) if selected_idea_ids is not None else None,
    )

    ideas = {
        str(row.get("idea_id")): DiscoveryIdea.from_dict(row)
        for row in _read_jsonl_if_exists(run_dir / "ideas.jsonl")
        if (
            isinstance(row, Mapping)
            and row.get("idea_id")
            and _selected_filter_allows(row.get("idea_id"), selected_idea_ids)
        )
    }
    reviews = {
        str(row.get("idea_id")): row
        for row in _read_jsonl_if_exists(run_dir / "reviews.jsonl")
        if (
            isinstance(row, Mapping)
            and row.get("idea_id")
            and _selected_filter_allows(row.get("idea_id"), selected_idea_ids)
        )
    }
    results = {
        str(row.get("idea_id")): row
        for row in _read_jsonl_if_exists(run_dir / "results.jsonl")
        if (
            isinstance(row, Mapping)
            and row.get("idea_id")
            and _selected_filter_allows(row.get("idea_id"), selected_idea_ids)
        )
    }
    directions = _read_directions_if_exists(run_dir)

    for idea_id, idea in ideas.items():
        idea_node = _idea_node_id(idea_id)
        signature = idea_signature(idea)
        review = reviews.get(idea_id)
        result = results.get(idea_id)
        review_accepted = bool(review.get("accepted")) if review is not None else None
        execution_state = _idea_execution_state(review, result)
        direction_id = idea.metadata.get("direction_id") or idea.metadata.get("frontier_id")
        graph.add_node(
            idea_node,
            "Idea",
            idea_id=idea.idea_id,
            title=idea.idea_title,
            biological_hypothesis=idea.biological_hypothesis,
            computable_parameter=idea.computable_parameter,
            expected_direction=idea.expected_direction,
            complexity=idea.complexity,
            metadata=_direction_metadata(idea.metadata),
            direction_id=direction_id,
            iterative_context_status=idea.metadata.get("iterative_context_status"),
            signature=signature,
            review_status=_idea_review_status(review),
            review_accepted=review_accepted,
            execution_state=execution_state,
            hypothesis_status=_idea_graph_status(review, result),
        )
        graph.add_edge(run_node, "generated", idea_node)
        _add_idea_direction(graph, idea_node, idea.metadata, directions.get(str(direction_id)))
        _add_idea_facets(graph, idea_node, signature)

        if review is not None:
            review_node = f"review:{idea_id}"
            graph.add_node(
                review_node,
                "IdeaReview",
                idea_id=idea_id,
                accepted=bool(review.get("accepted")),
                errors=review.get("errors", []),
                warnings=review.get("warnings", []),
                missing_fields=review.get("missing_fields", []),
            )
            graph.add_edge(idea_node, "reviewed_by", review_node)
            graph.add_edge(run_node, "has_review", review_node)

        if result is not None:
            _add_result_nodes(graph, run_node, idea, result)

    for claims_path in _default_claims_paths(run_dir, claims_paths):
        ingest_literature_claims(graph, claims_path)

    _add_run_directions(graph, run_node, directions)

    return graph


def build_idea_graph_from_runs(
    run_dirs: list[str | Path],
    *,
    graph_id: str = "iterative_idea_graph",
    claims_paths: list[str | Path] | None = None,
    selected_only: bool = False,
) -> IdeaGraph:
    """Build one graph by merging several auto-discovery runs."""
    graph = IdeaGraph(graph_id=graph_id)
    for run_dir in run_dirs:
        partial = build_idea_graph_from_run(
            run_dir,
            graph_id=f"run:{Path(run_dir).name}",
            selected_only=selected_only,
        )
        _merge_graph(graph, partial)
    for claims_path in claims_paths or []:
        ingest_literature_claims(graph, claims_path)
    return graph


def ingest_literature_claims(
    graph: IdeaGraph,
    claims_path: str | Path,
) -> int:
    """Ingest browser-agent literature claims into an :class:`IdeaGraph`.

    ``claims_path`` is a JSONL file.  Rows may contain ``claim_id``, ``claim``
    or ``claim_text``, ``source``/``source_title``, ``url``, ``doi``, ``pmid``,
    ``entities``/``genes``, ``cell_types``, ``markers``, ``modalities``,
    ``supports_idea_ids``,
    ``contradicts_idea_ids``, and ``related_idea_ids``.  Extra keys are kept on
    the claim node for auditability.
    """
    path = Path(claims_path)
    if not path.exists():
        return 0
    n = 0
    for row in _read_jsonl_if_exists(path):
        if not isinstance(row, Mapping):
            continue
        source = row.get("source") if isinstance(row.get("source"), Mapping) else {}
        entities = row.get("entities") if isinstance(row.get("entities"), Mapping) else {}
        claim_text = (
            row.get("claim")
            or row.get("claim_text")
            or row.get("text")
            or row.get("summary")
        )
        claim_id = str(row.get("claim_id") or _stable_claim_id(row))
        claim_node = f"literature_claim:{_slug(claim_id)}"
        reference_id = str(
            row.get("reference_id")
            or source.get("reference_id")
            or row.get("doi")
            or source.get("doi")
            or row.get("pmid")
            or source.get("pmid")
            or row.get("url")
            or source.get("url")
            or f"reference_for_{claim_id}"
        )
        reference_node = f"reference:{_slug(reference_id)}"
        graph.add_node(
            reference_node,
            "Reference",
            reference_id=reference_id,
            title=row.get("source_title") or row.get("title") or source.get("title"),
            url=row.get("url") or source.get("url"),
            doi=row.get("doi") or source.get("doi"),
            pmid=row.get("pmid") or source.get("pmid"),
            year=row.get("year") or source.get("year"),
        )
        graph.add_node(
            claim_node,
            "LiteratureClaim",
            claim_id=claim_id,
            claim=claim_text,
            summary=row.get("summary"),
            confidence=row.get("confidence"),
            extraction_method=row.get("extraction_method"),
            source_title=row.get("source_title") or row.get("title") or source.get("title"),
            url=row.get("url") or source.get("url"),
            doi=row.get("doi") or source.get("doi"),
            pmid=row.get("pmid") or source.get("pmid"),
            raw=row,
        )
        graph.add_edge(claim_node, "sourced_from", reference_node)
        for gene in _as_str_list(row.get("genes") or entities.get("genes")):
            node = f"gene:{_slug(gene)}"
            graph.add_node(node, "Gene", label=gene)
            graph.add_edge(claim_node, "mentions_gene", node)
        for cell_type in _as_str_list(row.get("cell_types") or entities.get("cell_types")):
            node = f"cell_type:{_slug(cell_type)}"
            graph.add_node(node, "CellType", label=cell_type)
            graph.add_edge(claim_node, "mentions_cell_type", node)
        for marker in _as_str_list(row.get("markers") or entities.get("markers")):
            node = f"marker:{_slug(marker)}"
            graph.add_node(node, "IFMarker", label=marker)
            graph.add_edge(claim_node, "mentions_marker", node)
        for modality in _as_str_list(row.get("modalities") or entities.get("modalities")):
            node = f"modality:{_slug(modality)}"
            graph.add_node(node, "Modality", label=modality)
            graph.add_edge(claim_node, "mentions_modality", node)
        for idea_id in _as_str_list(row.get("supports_idea_ids")):
            graph.add_edge(claim_node, "literature_supports", _idea_node_id(idea_id))
        for idea_id in _as_str_list(row.get("contradicts_idea_ids")):
            graph.add_edge(claim_node, "literature_contradicts", _idea_node_id(idea_id))
        for idea_id in _as_str_list(row.get("related_idea_ids")):
            graph.add_edge(claim_node, "literature_related_to", _idea_node_id(idea_id))
        n += 1
    return n


def write_idea_graph_artifacts(
    graph: IdeaGraph,
    output_dir: str | Path,
    *,
    json_name: str = "idea_graph.json",
    summary_name: str = "graph_summary.md",
) -> dict[str, str]:
    """Write graph JSON and Markdown summary into a run artifact directory."""
    output_dir = Path(output_dir)
    graph_dir = output_dir / "graph"
    json_path = graph.write_json(graph_dir / json_name)
    summary_path = graph.write_summary_markdown(graph_dir / summary_name)
    return {"graph_json": str(json_path), "graph_summary": str(summary_path)}


def load_idea_graph(path: str | Path) -> IdeaGraph:
    """Load an :class:`IdeaGraph` previously written with ``write_json``."""
    data = json.loads(Path(path).read_text())
    graph = IdeaGraph(graph_id=str(data.get("graph_id", "idea_graph")))
    graph.nodes = {
        str(node["id"]): dict(node)
        for node in data.get("nodes", [])
        if isinstance(node, Mapping) and node.get("id")
    }
    graph.edges = [
        dict(edge)
        for edge in data.get("edges", [])
        if isinstance(edge, Mapping) and edge.get("source") and edge.get("target")
    ]
    return graph


def idea_signature(idea: DiscoveryIdea | Mapping[str, Any]) -> dict[str, Any]:
    """Return structured facets used for novelty and coverage review."""
    if not isinstance(idea, DiscoveryIdea):
        idea = DiscoveryIdea.from_dict(idea)
    fields = list(idea.required_fields)
    markers = []
    genes = []
    for field_name in fields:
        if field_name.startswith("tracks."):
            markers.append(field_name.split(".", 1)[1])
        elif field_name.startswith("linked_adata.var."):
            genes.append(field_name.split(".", 2)[2])
    return {
        "modalities": sorted(set(idea.modalities)),
        "cell_types": sorted(set(idea.cell_types)),
        "markers": sorted(set(markers)),
        "genes": sorted(set(genes)),
        "required_fields": sorted(set(fields)),
        "parameter_family": infer_parameter_family(idea),
        "expected_direction": idea.expected_direction,
        "source_claim_ids": sorted(map(str, idea.metadata.get("source_claim_ids", []))),
        "parent_idea_ids": sorted(map(str, idea.metadata.get("parent_idea_ids", []))),
    }


def infer_parameter_family(idea: DiscoveryIdea | Mapping[str, Any]) -> str:
    """Infer a coarse parameter family from idea text."""
    if not isinstance(idea, DiscoveryIdea):
        idea = DiscoveryIdea.from_dict(idea)
    text = " ".join([
        idea.idea_title,
        idea.computable_parameter,
        idea.analysis_plan,
    ]).lower()
    if any(token in text for token in ("radial", "lamina", "peripheral", "nuclear position")):
        return "radial_position"
    if any(token in text for token in ("inter-chrom", "interchrom", "between chromosomes")):
        return "inter_chromosomal"
    if any(token in text for token in ("pairwise", "distance", "proximity", "compact", "decompact")):
        return "spatial_distance"
    if any(token in text for token in ("expression", "rna", "gene")):
        return "expression_association"
    if any(token in text for token in ("negative", "control", "permutation", "shuffle")):
        return "robustness_control"
    if any(token in text for token in ("marker", "track", "if")):
        return "marker_stratification"
    return "unspecified"


def graph_summary_markdown(graph: IdeaGraph) -> str:
    """Render a compact Markdown summary for humans and agents."""
    summary = graph.summary()
    lines = [
        f"# Idea Graph: {graph.graph_id}",
        "",
        f"- nodes: {summary['n_nodes']}",
        f"- edges: {summary['n_edges']}",
        "",
        "## Node Kinds",
    ]
    for key, value in summary["node_kinds"].items():
        lines.append(f"- {key}: {value}")
    lines.extend(["", "## Evidence"])
    evidence = summary.get("hypothesis_status", {})
    if evidence:
        for key, value in evidence.items():
            lines.append(f"- {key}: {value}")
    else:
        lines.append("- none")
    lines.extend(["", "## Coverage"])
    for facet, values in summary["coverage"].items():
        preview = ", ".join(f"{k}={v}" for k, v in list(values.items())[:12])
        lines.append(f"- {facet}: {preview or 'none'}")
    return "\n".join(lines)


def _add_idea_facets(graph: IdeaGraph, idea_node: str, signature: Mapping[str, Any]) -> None:
    for modality in signature.get("modalities", []):
        node = f"modality:{_slug(modality)}"
        graph.add_node(node, "Modality", label=modality)
        graph.add_edge(idea_node, "uses_modality", node)
    for cell_type in signature.get("cell_types", []):
        node = f"cell_type:{_slug(cell_type)}"
        graph.add_node(node, "CellType", label=cell_type)
        graph.add_edge(idea_node, "uses_cell_type", node)
    for marker in signature.get("markers", []):
        node = f"marker:{_slug(marker)}"
        graph.add_node(node, "IFMarker", label=marker)
        graph.add_edge(idea_node, "uses_marker", node)
    for gene in signature.get("genes", []):
        node = f"gene:{_slug(gene)}"
        graph.add_node(node, "Gene", label=gene)
        graph.add_edge(idea_node, "uses_gene", node)
    family = signature.get("parameter_family")
    if family:
        node = f"parameter_family:{_slug(family)}"
        graph.add_node(node, "ParameterFamily", label=family)
        graph.add_edge(idea_node, "has_parameter_family", node)
    for parent in signature.get("parent_idea_ids", []):
        graph.add_edge(idea_node, "derived_from", _idea_node_id(parent))
    for claim in signature.get("source_claim_ids", []):
        claim_node = f"literature_claim:{_slug(claim)}"
        graph.add_node(claim_node, "LiteratureClaim", claim_id=claim)
        graph.add_edge(idea_node, "motivated_by", claim_node)


def _add_idea_direction(
    graph: IdeaGraph,
    idea_node: str,
    metadata: Mapping[str, Any],
    direction: Mapping[str, Any] | None = None,
) -> None:
    direction_id = (
        metadata.get("direction_id") or metadata.get("frontier_id")
        if isinstance(metadata, Mapping)
        else None
    )
    if not direction_id:
        return
    direction_id = str(direction_id)
    direction_node = _add_direction_node(
        graph,
        direction_id,
        direction=direction,
        iterative_context_status=metadata.get("iterative_context_status"),
    )
    graph.add_edge(direction_node, "direction_proposed", idea_node)


def _direction_metadata(metadata: Mapping[str, Any] | None) -> dict[str, Any]:
    out = dict(metadata or {})
    if out.get("frontier_id") and not out.get("direction_id"):
        out["direction_id"] = out["frontier_id"]
    if out.get("frontier_type") and not out.get("direction_type"):
        out["direction_type"] = out["frontier_type"]
    out.pop("frontier_id", None)
    out.pop("frontier_type", None)
    return out


def _add_run_directions(
    graph: IdeaGraph,
    run_node: str,
    directions: Mapping[str, Mapping[str, Any]],
) -> None:
    for direction_id, direction in directions.items():
        direction_node = _add_direction_node(graph, direction_id, direction=direction)
        graph.add_edge(run_node, "planned_direction", direction_node)
        for parent_idea_id in _as_str_list(direction.get("parent_idea_ids")):
            parent_node = _idea_node_id(parent_idea_id)
            graph.add_edge(direction_node, "direction_based_on", parent_node)
            evidence_node = f"evidence:{parent_idea_id}"
            if evidence_node in graph.nodes:
                graph.add_edge(direction_node, "direction_based_on_evidence", evidence_node)


def _add_direction_node(
    graph: IdeaGraph,
    direction_id: str,
    *,
    direction: Mapping[str, Any] | None = None,
    iterative_context_status: Any = None,
) -> str:
    direction = dict(direction or {})
    direction_id = str(direction.get("direction_id") or direction.get("frontier_id") or direction_id)
    direction_type = str(
        direction.get("direction_type")
        or direction.get("frontier_type")
        or (direction_id.rsplit("-", 1)[0] if "-" in direction_id else direction_id)
    )
    direction_node = f"direction:{_slug(direction_id)}"
    graph.add_node(
        direction_node,
        "Direction",
        direction_id=direction_id,
        direction_type=direction_type,
        label=direction.get("label") or direction_type.replace("_", " "),
        title=direction.get("title"),
        prompt=direction.get("prompt"),
        rationale=direction.get("rationale"),
        priority=direction.get("priority"),
        target_facets=direction.get("target_facets"),
        parent_idea_ids=direction.get("parent_idea_ids"),
        evidence_basis=direction.get("evidence_basis"),
        novelty_notes=direction.get("novelty_notes"),
        constraints=direction.get("constraints"),
        iterative_context_status=iterative_context_status or direction.get("iterative_context_status"),
    )
    return direction_node


def _add_result_nodes(
    graph: IdeaGraph,
    run_node: str,
    idea: DiscoveryIdea,
    result: Mapping[str, Any],
) -> None:
    idea_node = _idea_node_id(idea.idea_id)
    notebook_node = f"notebook:{idea.idea_id}"
    evidence_node = f"evidence:{idea.idea_id}"
    verification = result.get("verification") or {}
    conclusion = classify_hypothesis_evidence(idea, verification)

    graph.add_node(
        notebook_node,
        "NotebookRun",
        idea_id=idea.idea_id,
        path=result.get("notebook"),
        execution_ok=result.get("execution_ok"),
        elapsed_sec=result.get("elapsed_sec"),
        errors=result.get("errors", []),
    )
    graph.add_node(
        evidence_node,
        "EvidenceResult",
        idea_id=idea.idea_id,
        notebook_status=conclusion.notebook_status,
        hypothesis_status=conclusion.hypothesis_status,
        direction_status=conclusion.direction_status,
        p_value=conclusion.p_value,
        effect_size=conclusion.effect_size,
        test_method=verification.get("test_method"),
        observed_statistic=verification.get("observed_statistic"),
        parameter_value=verification.get("parameter_value"),
        result_path=verification.get("result_path"),
        summary=conclusion.summary,
    )
    graph.add_edge(run_node, "has_notebook", notebook_node)
    graph.add_edge(idea_node, "tested_by", notebook_node)
    graph.add_edge(notebook_node, "produced", evidence_node)
    graph.add_edge(evidence_node, _evidence_relation(conclusion.hypothesis_status), idea_node)


def _evidence_relation(status: str) -> str:
    status = str(status).lower()
    if status == "supported":
        return "supports"
    if status == "contradicted":
        return "contradicts"
    if status == "borderline":
        return "borderline_supports"
    if status == "inconclusive":
        return "inconclusive_for"
    return "not_supports"


def _idea_review_status(review: Mapping[str, Any] | None) -> str:
    if review is None:
        return "Not reviewed"
    return "Accepted" if bool(review.get("accepted")) else "Rejected"


def _idea_execution_state(
    review: Mapping[str, Any] | None,
    result: Mapping[str, Any] | None,
) -> str:
    if review is not None and not bool(review.get("accepted")):
        return "Rejected by schema"
    if result is None:
        return "Pending execution" if review is None or bool(review.get("accepted")) else "Rejected by schema"
    if result.get("execution_ok") is True:
        verification = result.get("verification") or {}
        if verification.get("status") == "pass":
            return "Verified"
        return "Verification failed"
    if result.get("execution_ok") is False:
        return "Execution failed"
    return "Not executed"


def _idea_graph_status(
    review: Mapping[str, Any] | None,
    result: Mapping[str, Any] | None,
) -> str:
    if review is not None and not bool(review.get("accepted")):
        return "Rejected"
    if result is None:
        return "Pending"
    if result.get("execution_ok") is False:
        return "Failed"
    return ""


def _read_jsonl_if_exists(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows = []
    with path.open() as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def _read_directions_if_exists(run_dir: Path) -> dict[str, dict[str, Any]]:
    path = run_dir / "directions" / "next_directions.json"
    if not path.exists():
        path = run_dir / "frontiers" / "next_frontiers.json"
    if not path.exists():
        return {}
    try:
        rows = json.loads(path.read_text())
    except json.JSONDecodeError:
        return {}
    if not isinstance(rows, list):
        return {}
    out: dict[str, dict[str, Any]] = {}
    for row in rows:
        if isinstance(row, Mapping):
            direction_id = row.get("direction_id") or row.get("frontier_id")
            if direction_id:
                out[str(direction_id)] = dict(row)
    return out


def _read_selected_idea_ids_if_exists(run_dir: Path) -> set[str] | None:
    path = run_dir / "idea_diversity_report.json"
    if not path.exists():
        return None
    try:
        report = json.loads(path.read_text())
    except json.JSONDecodeError:
        return None
    if not isinstance(report, Mapping):
        return None
    idea_ids = report.get("selected_idea_ids")
    if idea_ids is None and isinstance(report.get("selected_ideas"), list):
        idea_ids = [
            row.get("idea_id")
            for row in report["selected_ideas"]
            if isinstance(row, Mapping) and row.get("idea_id")
        ]
    if not isinstance(idea_ids, list):
        return None
    return {str(idea_id) for idea_id in idea_ids if str(idea_id)}


def _selected_filter_allows(
    idea_id: Any,
    selected_idea_ids: set[str] | None,
) -> bool:
    return selected_idea_ids is None or str(idea_id) in selected_idea_ids


def _default_claims_paths(
    run_dir: Path,
    claims_paths: list[str | Path] | None,
) -> list[Path]:
    paths = [Path(p) for p in claims_paths or []]
    for rel in (
        "browser/claims.jsonl",
        "literature/claims.jsonl",
        "claims.jsonl",
    ):
        path = run_dir / rel
        if path.exists():
            paths.append(path)
    seen = set()
    unique = []
    for path in paths:
        key = str(path)
        if key not in seen:
            unique.append(path)
            seen.add(key)
    return unique


def _merge_graph(target: IdeaGraph, source: IdeaGraph) -> None:
    for node in source.nodes.values():
        attrs = dict(node)
        node_id = str(attrs.pop("id"))
        kind = str(attrs.pop("kind", "Node"))
        target.add_node(node_id, kind, **attrs)
    for edge in source.edges:
        attrs = dict(edge)
        source_id = str(attrs.pop("source"))
        relation = str(attrs.pop("relation"))
        target_id = str(attrs.pop("target"))
        target.add_edge(source_id, relation, target_id, **attrs)


def _node_label_counts(nodes: Any, kind: str) -> dict[str, int]:
    counts = Counter(
        str(node.get("label", node.get("id")))
        for node in nodes
        if node.get("kind") == kind
    )
    return dict(sorted(counts.items()))


def _idea_node_id(idea_id: str) -> str:
    return f"idea:{idea_id}"


def _slug(value: Any) -> str:
    text = str(value).strip().lower()
    slug = re.sub(r"[^a-z0-9_.+-]+", "-", text).strip("-")
    return slug or "unknown"


def _stable_claim_id(row: Mapping[str, Any]) -> str:
    text = str(
        row.get("claim")
        or row.get("claim_text")
        or row.get("summary")
        or row.get("text")
        or "claim"
    )
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:48] or "claim"
    payload = json.dumps(row, sort_keys=True, default=str)
    import hashlib

    digest = hashlib.sha1(payload.encode("utf-8")).hexdigest()[:10]
    return f"{slug}-{digest}"


def _as_str_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value else []
    if isinstance(value, Mapping):
        return [str(k) for k, v in value.items() if v]
    try:
        return [str(item) for item in value if str(item)]
    except TypeError:
        return [str(value)]


def _jsonable(value: Any) -> Any:
    if isinstance(value, str):
        return _normalize_direction_terms(value)
    if isinstance(value, Mapping):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_jsonable(v) for v in value]
    try:
        json.dumps(value)
        return value
    except TypeError:
        return _normalize_direction_terms(str(value))


def _normalize_direction_terms(value: str) -> str:
    return (
        value.replace("Frontiers", "Directions")
        .replace("frontiers", "directions")
        .replace("Frontier", "Direction")
        .replace("frontier", "direction")
    )
