"""Diversity-aware selection for generated discovery ideas."""

from __future__ import annotations

import json
import math
import re
from dataclasses import asdict, dataclass, field
from typing import Any, Mapping, Sequence

from .ideas import DiscoveryIdea, IdeaReview


FEATURE_FAMILY_ORDER = (
    "sequence_features",
    "structure_annotations",
    "cell_spatial_context",
    "radial_positioning",
    "local_compaction",
    "inter_chromosomal_organization",
    "cell_state_metadata",
    "genomic_scale",
    "regulatory_context",
    "literature_prior",
    "genome_annotations",
    "chromatin_geometry",
    "peak_features",
    "gene_expression",
    "marker_tracks",
)
SATURATING_FAMILIES = frozenset({"gene_expression", "peak_features"})
PRIORITY_DIVERSITY_FAMILIES = frozenset(
    family
    for family in FEATURE_FAMILY_ORDER
    if family not in {"peak_features", "gene_expression", "marker_tracks"}
)
ENRICHED_TRACK_PREFIXES = ("seq.", "gtf.", "strc.", "peak.")
TEXT_STOPWORDS = frozenset({
    "with",
    "from",
    "that",
    "this",
    "into",
    "between",
    "around",
    "using",
    "cells",
    "cell",
    "bins",
    "chromatin",
    "expression",
    "signal",
    "association",
    "predicts",
    "linked",
    "links",
})


@dataclass
class IdeaDiversitySelection:
    """Selection report for one generated idea pool."""

    policy: str
    target: int
    candidate_count: int
    accepted_candidate_count: int
    selected_idea_ids: list[str]
    family_counts: dict[str, int]
    candidates: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    ideas: list[DiscoveryIdea] = field(default_factory=list, repr=False)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data.pop("ideas", None)
        return data


def idea_diversity_signature(idea: DiscoveryIdea | Mapping[str, Any]) -> dict[str, Any]:
    """Infer diversity metadata from an idea's fields, modalities, and text."""
    if not isinstance(idea, DiscoveryIdea):
        idea = DiscoveryIdea.from_dict(idea)
    fields = [str(field) for field in idea.required_fields]
    lower_fields = [field.lower() for field in fields]
    modalities = [str(modality).lower() for modality in idea.modalities]
    text = _idea_text(idea)
    metadata = idea.metadata if isinstance(idea.metadata, Mapping) else {}

    families: set[str] = set()
    genes: set[str] = set()
    markers: set[str] = set()
    enriched_tracks: set[str] = set()

    for family in metadata.get("feature_families", []) or []:
        family = _normalise_family(str(family))
        if family:
            families.add(family)

    if "rna_expression" in modalities:
        families.add("gene_expression")
    if "sequence_features" in modalities:
        families.add("sequence_features")
    if "genome_annotations" in modalities:
        families.add("genome_annotations")
    if "structure_annotations" in modalities:
        families.add("structure_annotations")
    if "peak_features" in modalities:
        families.add("peak_features")
    if "if_tracks" in modalities:
        families.add("marker_tracks")
    if "cell_metadata" in modalities and _mentions_cell_spatial(text, lower_fields):
        families.add("cell_spatial_context")
    if "cell_metadata" in modalities and _mentions_cell_state(text, lower_fields):
        families.add("cell_state_metadata")

    for raw_field, field_name in zip(fields, lower_fields):
        if field_name.startswith("linked_adata."):
            families.add("gene_expression")
            if field_name.startswith("linked_adata.var."):
                genes.add(raw_field.split(".", 2)[-1])
        if field_name.startswith("tracks."):
            track = raw_field.split(".", 1)[1]
            track_lower = track.lower()
            if track_lower.startswith("seq."):
                families.add("sequence_features")
                enriched_tracks.add(track)
            elif track_lower.startswith("gtf."):
                families.add("genome_annotations")
                enriched_tracks.add(track)
            elif track_lower.startswith("strc."):
                families.add("structure_annotations")
                enriched_tracks.add(track)
            elif track_lower.startswith("peak."):
                families.add("peak_features")
                enriched_tracks.add(track)
            else:
                families.add("marker_tracks")
                markers.add(track)
        if field_name.startswith("results."):
            result = field_name.split(".", 1)[1]
            result_family = result.split(":", 1)[0].split(".", 1)[0]
            if result_family == "peaks":
                families.add("peak_features")
            elif result_family in {"tads", "loops", "compartments"}:
                families.add("structure_annotations")
            elif result_family in {"gene_annotations", "annotations"}:
                families.add("genome_annotations")
            elif result_family == "bin_features":
                families.update(_bin_feature_families(result))
        if field_name == "uns.feature_registry":
            families.add("genome_annotations")
        if field_name.startswith(("cellm.", "cells.")) and _mentions_cell_spatial(text, [field_name]):
            families.add("cell_spatial_context")
        if field_name.startswith(("cellm.", "cells.")) and _mentions_cell_state(text, [field_name]):
            families.add("cell_state_metadata")
        if _mentions_regulatory_context(field_name):
            families.add("regulatory_context")
        if _mentions_radial_positioning(field_name):
            families.add("radial_positioning")
        if _mentions_inter_chromosomal(field_name):
            families.add("inter_chromosomal_organization")
        if _mentions_local_compaction(field_name):
            families.add("local_compaction")

    if _mentions_structure(text):
        families.add("structure_annotations")
    if _mentions_sequence(text):
        families.add("sequence_features")
    if _mentions_annotation(text):
        families.add("genome_annotations")
    if _mentions_regulatory_context(text):
        families.add("regulatory_context")
    if _mentions_peak(text):
        families.add("peak_features")
    if _mentions_cell_spatial(text, lower_fields):
        families.add("cell_spatial_context")
    if _mentions_cell_state(text, lower_fields):
        families.add("cell_state_metadata")
    if _mentions_chromatin_geometry(text, lower_fields):
        families.add("chromatin_geometry")
    if _mentions_radial_positioning(text):
        families.add("radial_positioning")
    if _mentions_local_compaction(text):
        families.add("local_compaction")
    if _mentions_inter_chromosomal(text):
        families.add("inter_chromosomal_organization")
    if _mentions_genomic_scale(text):
        families.add("genomic_scale")
    if _mentions_literature_prior(idea, text):
        families.add("literature_prior")

    for gene in _regex_terms(text, r"\b([A-Z][A-Za-z0-9-]{2,})\s+(?:expression|RNA)\b"):
        genes.add(gene)
    for marker in _regex_terms(text, r"\b(H[0-9][A-Za-z0-9.-]*|LaminB1|RNAPII[A-Za-z0-9-]*)\b"):
        markers.add(marker)

    if not families:
        families.add("unknown")

    scope = _idea_scope(idea, text)
    return {
        "families": _ordered_families(families),
        "fields": sorted(set(fields)),
        "modalities": sorted(set(idea.modalities)),
        "cell_types": sorted(set(map(str, idea.cell_types))),
        "genes": sorted(genes),
        "markers": sorted(markers),
        "enriched_tracks": sorted(enriched_tracks),
        "scope": scope,
        "text_terms": _text_terms(text),
    }


def select_diverse_ideas(
    ideas: Sequence[DiscoveryIdea],
    reviews: Sequence[IdeaReview | Mapping[str, Any]] | None = None,
    *,
    target: int | None = None,
    policy: str = "balanced",
) -> IdeaDiversitySelection:
    """Select a balanced subset from schema-accepted generated ideas."""
    if policy not in {"off", "balanced"}:
        raise ValueError("policy must be 'off' or 'balanced'")
    target = max(0, int(target if target is not None else len(ideas)))
    review_rows = _review_rows(ideas, reviews)
    accepted = [
        {
            "index": index,
            "idea": idea,
            "review": review_rows[index],
            "signature": idea_diversity_signature(idea),
        }
        for index, idea in enumerate(ideas)
        if bool(review_rows[index].get("accepted", True))
    ]

    if policy == "off" or target == 0:
        selected_rows = accepted[:target]
    elif len(accepted) <= target:
        selected_rows = accepted
    else:
        selected_rows = _greedy_balanced_selection(accepted, target)

    selected_ids = {row["idea"].idea_id for row in selected_rows}
    family_counts = _family_counts(row["signature"] for row in selected_rows)
    candidate_records = []
    for row in accepted:
        candidate_records.append({
            "idea_id": row["idea"].idea_id,
            "order": row["index"],
            "selected": row["idea"].idea_id in selected_ids,
            **row["signature"],
        })
    warnings = _diversity_warnings(
        policy=policy,
        target=target,
        accepted_count=len(accepted),
        family_counts=family_counts,
    )
    return IdeaDiversitySelection(
        policy=policy,
        target=target,
        candidate_count=len(ideas),
        accepted_candidate_count=len(accepted),
        selected_idea_ids=[row["idea"].idea_id for row in selected_rows],
        family_counts=family_counts,
        candidates=candidate_records,
        warnings=warnings,
        ideas=[row["idea"] for row in selected_rows],
    )


def _greedy_balanced_selection(rows: list[dict[str, Any]], target: int) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    remaining = list(rows)
    field_sets: list[set[str]] = []
    marker_counts: dict[str, int] = {}
    gene_counts: dict[str, int] = {}
    cell_type_counts: dict[str, int] = {}
    scope_counts: dict[str, int] = {}
    family_counts: dict[str, int] = {}
    family_cap = max(1, math.ceil(target * 0.5))

    while remaining and len(selected) < target:
        best_index = 0
        best_score = -float("inf")
        for index, row in enumerate(remaining):
            score = _candidate_score(
                row,
                selected=selected,
                field_sets=field_sets,
                marker_counts=marker_counts,
                gene_counts=gene_counts,
                cell_type_counts=cell_type_counts,
                scope_counts=scope_counts,
                family_counts=family_counts,
                family_cap=family_cap,
                target=target,
            )
            if score > best_score:
                best_score = score
                best_index = index
        chosen = remaining.pop(best_index)
        selected.append(chosen)
        signature = chosen["signature"]
        field_sets.append(set(signature.get("fields", [])))
        for family in signature.get("families", []):
            family_counts[family] = family_counts.get(family, 0) + 1
        for marker in signature.get("markers", []):
            marker_counts[marker] = marker_counts.get(marker, 0) + 1
        for gene in signature.get("genes", []):
            gene_counts[gene] = gene_counts.get(gene, 0) + 1
        for cell_type in signature.get("cell_types", []):
            cell_type_counts[cell_type] = cell_type_counts.get(cell_type, 0) + 1
        scope = str(signature.get("scope") or "unknown")
        scope_counts[scope] = scope_counts.get(scope, 0) + 1
    return selected


def _candidate_score(
    row: Mapping[str, Any],
    *,
    selected: Sequence[Mapping[str, Any]],
    field_sets: Sequence[set[str]],
    marker_counts: Mapping[str, int],
    gene_counts: Mapping[str, int],
    cell_type_counts: Mapping[str, int],
    scope_counts: Mapping[str, int],
    family_counts: Mapping[str, int],
    family_cap: int,
    target: int,
) -> float:
    signature = row["signature"]
    families = set(signature.get("families", []))
    score = -float(row["index"]) * 0.001

    for family in families:
        count = int(family_counts.get(family, 0))
        score += 4.0 / (1.0 + count)
        if count == 0 and family in PRIORITY_DIVERSITY_FAMILIES:
            score += 2.5
        if family in SATURATING_FAMILIES and count >= family_cap:
            score -= 5.0 + count
    if not (families & SATURATING_FAMILIES):
        score += 1.5
    if len(families & SATURATING_FAMILIES) == len(families):
        score -= 0.8

    candidate_fields = set(signature.get("fields", []))
    if field_sets and candidate_fields:
        score -= 2.5 * max(_jaccard(candidate_fields, fields) for fields in field_sets)
    for token in signature.get("markers", []):
        score -= 0.8 * int(marker_counts.get(token, 0))
    for token in signature.get("genes", []):
        score -= 1.0 * int(gene_counts.get(token, 0))
    for token in signature.get("cell_types", []):
        score -= 0.35 * int(cell_type_counts.get(token, 0))

    scope = str(signature.get("scope") or "unknown")
    if scope in {"global", "broad"} and not scope_counts.get(scope):
        score += 1.2
    if scope == "cell_type_specific" and int(scope_counts.get(scope, 0)) > math.ceil(target * 0.6):
        score -= 1.5

    text_terms = set(signature.get("text_terms", []))
    if selected and text_terms:
        overlap = max(
            _jaccard(text_terms, set(item["signature"].get("text_terms", [])))
            for item in selected
        )
        score -= 1.2 * overlap
    return score


def _review_rows(
    ideas: Sequence[DiscoveryIdea],
    reviews: Sequence[IdeaReview | Mapping[str, Any]] | None,
) -> list[dict[str, Any]]:
    if reviews is None:
        return [{"idea_id": idea.idea_id, "accepted": True} for idea in ideas]
    by_id: dict[str, dict[str, Any]] = {}
    positional: list[dict[str, Any]] = []
    for review in reviews:
        row = review.to_dict() if isinstance(review, IdeaReview) else dict(review)
        positional.append(row)
        if row.get("idea_id"):
            by_id[str(row["idea_id"])] = row
    rows = []
    for index, idea in enumerate(ideas):
        rows.append(by_id.get(idea.idea_id) or (positional[index] if index < len(positional) else {"accepted": True}))
    return rows


def _family_counts(signatures: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for signature in signatures:
        for family in signature.get("families", []):
            counts[family] = counts.get(family, 0) + 1
    return {key: counts[key] for key in sorted(counts, key=_family_sort_key)}


def _diversity_warnings(
    *,
    policy: str,
    target: int,
    accepted_count: int,
    family_counts: Mapping[str, int],
) -> list[str]:
    warnings: list[str] = []
    if accepted_count < target:
        warnings.append(f"accepted candidates below target: {accepted_count}/{target}")
    if policy == "balanced" and target:
        for family in sorted(SATURATING_FAMILIES):
            count = int(family_counts.get(family, 0))
            if count > math.ceil(target * 0.6):
                warnings.append(f"{family} still dominates selected ideas: {count}/{target}")
    return warnings


def _idea_text(idea: DiscoveryIdea) -> str:
    parts = [
        idea.idea_title,
        idea.biological_hypothesis,
        idea.computable_parameter,
        idea.analysis_plan,
        idea.expected_direction,
        idea.idea_markdown,
        json.dumps(idea.metadata, sort_keys=True, default=str) if idea.metadata else "",
    ]
    return " ".join(str(part) for part in parts if part).lower()


def _normalise_family(name: str) -> str:
    normalised = name.strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "sequence": "sequence_features",
        "annotation": "genome_annotations",
        "annotations": "genome_annotations",
        "structure": "structure_annotations",
        "structural": "structure_annotations",
        "radial": "radial_positioning",
        "radial_position": "radial_positioning",
        "radial_positioning": "radial_positioning",
        "lamina": "radial_positioning",
        "periphery": "radial_positioning",
        "compaction": "local_compaction",
        "compactness": "local_compaction",
        "local_distance": "local_compaction",
        "interchromosomal": "inter_chromosomal_organization",
        "inter_chromosomal": "inter_chromosomal_organization",
        "trans": "inter_chromosomal_organization",
        "territory": "inter_chromosomal_organization",
        "cell_state": "cell_state_metadata",
        "cell_metadata": "cell_state_metadata",
        "metadata": "cell_state_metadata",
        "genomic_scale": "genomic_scale",
        "scale": "genomic_scale",
        "regulatory": "regulatory_context",
        "regulatory_context": "regulatory_context",
        "promoter": "regulatory_context",
        "literature": "literature_prior",
        "literature_prior": "literature_prior",
        "claim": "literature_prior",
        "prior": "literature_prior",
        "peaks": "peak_features",
        "rna": "gene_expression",
        "genes": "gene_expression",
        "spatial": "cell_spatial_context",
        "geometry": "chromatin_geometry",
        "markers": "marker_tracks",
    }
    return aliases.get(normalised, normalised)


def _bin_feature_families(result: str) -> set[str]:
    name = result.lower()
    families: set[str] = set()
    if any(token in name for token in ("gc", "cpg", "g4", "n_fraction")):
        families.add("sequence_features")
    if any(token in name for token in ("tss", "gene_body", "promoter", "exon", "intron")):
        families.add("genome_annotations")
        families.add("regulatory_context")
    if any(token in name for token in ("tad", "loop", "compartment")):
        families.add("structure_annotations")
    if "peak" in name:
        families.add("peak_features")
    if _mentions_radial_positioning(name):
        families.add("radial_positioning")
    if _mentions_local_compaction(name):
        families.add("local_compaction")
    if _mentions_inter_chromosomal(name):
        families.add("inter_chromosomal_organization")
    return families


def _mentions_structure(text: str) -> bool:
    return any(token in text for token in ("tad", "loop", "compartment", "boundary", "anchor"))


def _mentions_sequence(text: str) -> bool:
    return any(token in text for token in ("gc", "cpg", "g4", "quadruplex", "sequence"))


def _mentions_annotation(text: str) -> bool:
    return any(token in text for token in ("gtf", "promoter", "gene body", "tss", "exon", "intron", "annotation"))


def _mentions_regulatory_context(text: str) -> bool:
    return any(
        token in text
        for token in (
            "promoter",
            "enhancer",
            "gene body",
            "gene_body",
            "tss",
            "transcription start",
            "exon",
            "intron",
            "regulatory",
            "cre",
            "cpg island",
        )
    )


def _mentions_peak(text: str) -> bool:
    return any(token in text for token in ("peak", "h3k27ac", "h3k9me3", "h3k36", "h4k"))


def _mentions_cell_spatial(text: str, fields: Sequence[str]) -> bool:
    if any(token in text for token in ("cell centroid", "cell position", "spatial context", "cell neighborhood", "cellm.", "umap")):
        return True
    return any(
        any(token in field for token in ("centroid", "position", "umap", "spatial", "x_", "y_", "z_"))
        for field in fields
    )


def _mentions_cell_state(text: str, fields: Sequence[str]) -> bool:
    if any(
        token in text
        for token in (
            "cell state",
            "cell-state",
            "nuclear volume",
            "nuc_volume",
            "transcript count",
            "n_transcripts",
            "gene count",
            "n_genes",
            "batch",
            "doublet",
            "leiden",
            "cluster",
            "cell type",
            "cell_type",
        )
    ):
        return True
    return any(
        any(
            token in field
            for token in (
                "cell_type",
                "leiden",
                "batch",
                "doublet",
                "nuc_volume",
                "n_transcripts",
                "n_genes",
            )
        )
        for field in fields
    )


def _mentions_chromatin_geometry(text: str, fields: Sequence[str]) -> bool:
    if any(token in text for token in ("radial", "lamina", "periphery", "pairwise", "3d", "distance", "trace", "chromosome")):
        return True
    return any(field in {"coords", "spots.trace_id"} for field in fields)


def _mentions_radial_positioning(text: str) -> bool:
    return any(
        token in text
        for token in (
            "radial",
            "lamina",
            "laminb1",
            "periphery",
            "peripheral",
            "interior",
            "nuclear edge",
            "nuclear envelope",
            "n_rad",
            "n_per_dist",
        )
    )


def _mentions_local_compaction(text: str) -> bool:
    return any(
        token in text
        for token in (
            "compaction",
            "compact",
            "local distance",
            "local-distance",
            "neighbor distance",
            "neighbour distance",
            "nearest neighbor",
            "nearest-neighbor",
            "within-trace",
            "within trace",
            "intra-chromatin",
            "intra chromatin",
            "pairwise distance",
        )
    )


def _mentions_inter_chromosomal(text: str) -> bool:
    return any(
        token in text
        for token in (
            "inter-chromosomal",
            "inter chromosomal",
            "interchromosomal",
            "trans proximity",
            "trans-proximity",
            "chromosome territory",
            "territory",
            "chromosome assortativity",
            "assortativity",
            "hub",
            "inter-chromatin",
            "inter chromatin",
        )
    )


def _mentions_genomic_scale(text: str) -> bool:
    return any(
        token in text
        for token in (
            "bin-level",
            "bin level",
            "locus-level",
            "locus level",
            "chromosome-level",
            "chromosome level",
            "genome-wide",
            "genome wide",
            "pan-genome",
            "pan genome",
            "global",
            "whole chromosome",
        )
    )


def _mentions_literature_prior(idea: DiscoveryIdea, text: str) -> bool:
    metadata = idea.metadata if isinstance(idea.metadata, Mapping) else {}
    metadata_keys = {
        "source_claim_ids",
        "claim_ids",
        "literature_claim_ids",
        "reference_ids",
        "parent_idea_ids",
        "direction_id",
    }
    if any(metadata.get(key) for key in metadata_keys):
        return True
    return any(
        token in text
        for token in (
            "literature",
            "claim",
            "reference",
            "prior result",
            "prior supported",
            "prior contradicted",
            "supported result",
            "contradicted result",
            "parent idea",
            "direction_id",
            "source_claim",
        )
    )


def _idea_scope(idea: DiscoveryIdea, text: str) -> str:
    cell_types = [str(cell_type) for cell_type in idea.cell_types if str(cell_type).strip()]
    if not cell_types or any(token in text for token in ("pan-cell", "pan cell", "global", "all cell", "cell-type dependence")):
        return "global"
    if len(set(cell_types)) >= 3:
        return "broad"
    return "cell_type_specific"


def _regex_terms(text: str, pattern: str) -> set[str]:
    return {match.group(1) for match in re.finditer(pattern, text, flags=re.IGNORECASE)}


def _text_terms(text: str) -> list[str]:
    tokens = re.findall(r"[a-zA-Z][a-zA-Z0-9-]{3,}", text)
    counts: dict[str, int] = {}
    for token in tokens:
        token = token.lower()
        if token in TEXT_STOPWORDS or token.startswith(tuple(ENRICHED_TRACK_PREFIXES)):
            continue
        counts[token] = counts.get(token, 0) + 1
    return [
        token for token, _ in sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:16]
    ]


def _ordered_families(families: set[str]) -> list[str]:
    return sorted(families, key=_family_sort_key)


def _family_sort_key(family: str) -> tuple[int, str]:
    try:
        return (FEATURE_FAMILY_ORDER.index(family), family)
    except ValueError:
        return (len(FEATURE_FAMILY_ORDER), family)


def _jaccard(left: set[str], right: set[str]) -> float:
    if not left and not right:
        return 0.0
    union = left | right
    return len(left & right) / len(union) if union else 0.0


__all__ = [
    "FEATURE_FAMILY_ORDER",
    "IdeaDiversitySelection",
    "idea_diversity_signature",
    "select_diverse_ideas",
]
