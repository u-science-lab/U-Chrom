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


def build_idea_graph_from_run(run_dir: str | Path, *, graph_id: str | None = None) -> IdeaGraph:
    """Build an :class:`IdeaGraph` from a completed auto-discovery run.

    The function reads ``ideas.jsonl``, ``reviews.jsonl``, and
    ``results.jsonl`` when present.  Missing files are tolerated so interrupted
    runs can still produce partial graph snapshots.
    """
    run_dir = Path(run_dir)
    graph = IdeaGraph(graph_id=graph_id or f"run:{run_dir.name}")
    run_node = f"run:{run_dir.name}"
    graph.add_node(run_node, "Run", path=str(run_dir))

    ideas = {
        str(row.get("idea_id")): DiscoveryIdea.from_dict(row)
        for row in _read_jsonl_if_exists(run_dir / "ideas.jsonl")
        if isinstance(row, Mapping) and row.get("idea_id")
    }
    reviews = {
        str(row.get("idea_id")): row
        for row in _read_jsonl_if_exists(run_dir / "reviews.jsonl")
        if isinstance(row, Mapping) and row.get("idea_id")
    }
    results = {
        str(row.get("idea_id")): row
        for row in _read_jsonl_if_exists(run_dir / "results.jsonl")
        if isinstance(row, Mapping) and row.get("idea_id")
    }

    for idea_id, idea in ideas.items():
        idea_node = _idea_node_id(idea_id)
        signature = idea_signature(idea)
        graph.add_node(
            idea_node,
            "Idea",
            idea_id=idea.idea_id,
            title=idea.idea_title,
            biological_hypothesis=idea.biological_hypothesis,
            computable_parameter=idea.computable_parameter,
            expected_direction=idea.expected_direction,
            complexity=idea.complexity,
            signature=signature,
        )
        graph.add_edge(run_node, "generated", idea_node)
        _add_idea_facets(graph, idea_node, signature)

        review = reviews.get(idea_id)
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

        result = results.get(idea_id)
        if result is not None:
            _add_result_nodes(graph, run_node, idea, result)

    return graph


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


def _jsonable(value: Any) -> Any:
    try:
        json.dumps(value)
        return value
    except TypeError:
        if isinstance(value, Mapping):
            return {str(k): _jsonable(v) for k, v in value.items()}
        if isinstance(value, (list, tuple, set)):
            return [_jsonable(v) for v in value]
        return str(value)
