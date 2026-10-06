"""Multi-iteration orchestration for U-Chrom auto-discovery."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from .claims import (
    CLAIM_KNOWLEDGE_MODES,
    ClaimRefreshResult,
    refresh_literature_claims_for_iteration,
)
from .direction import plan_discovery_directions, write_direction_artifacts
from .graph import build_idea_graph_from_runs, write_idea_graph_artifacts
from .runner import DiscoveryRunConfig, DiscoveryRunResult, run_auto_discovery
from .schema import build_discovery_schema
from .visualization import write_idea_graph_html


@dataclass
class IterativeDiscoveryConfig:
    """Configuration for repeated auto-discovery iterations."""

    h5cd_path: str | Path
    output_dir: str | Path
    iterations: int = 2
    ideas_per_iteration: int = 20
    max_generation_attempts: int = 3
    seed_run_dirs: list[str | Path] = field(default_factory=list)
    max_complexity: int = 5
    idea_source: str = "pantheon"
    code_source: str = "pantheon"
    model: str | None = None
    reasoning_effort: str | None = None
    llm_timeout: int = 900
    idea_agent_count: int = 4
    notebook_agent_concurrency: int = 4
    generate_schematic_image: bool = True
    schematic_image_model: str | None = None
    schematic_image_model_args: dict[str, Any] | None = None
    execute: bool = True
    store_schema: bool = False
    dataset_name: str | None = None
    enrichment: dict[str, Any] | None = None
    knowledge_mode: str = "knowledge_guided"
    claims_paths: list[str | Path] = field(default_factory=list)


@dataclass
class IterativeDiscoveryResult:
    """Summary of a multi-iteration auto-discovery run."""

    output_dir: str
    run_dirs: list[str]
    iteration_results: list[DiscoveryRunResult]
    graph_path: str
    graph_summary_path: str
    directions_path: str
    direction_summary_path: str
    html_path: str
    claim_refresh_results: list[ClaimRefreshResult] = field(default_factory=list)

    @property
    def frontiers_path(self) -> str:
        """Legacy alias for ``directions_path``."""
        return self.directions_path

    @property
    def frontier_summary_path(self) -> str:
        """Legacy alias for ``direction_summary_path``."""
        return self.direction_summary_path

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable summary."""
        data = asdict(self)
        data["iteration_results"] = [
            result.__dict__ for result in self.iteration_results
        ]
        return data


def run_iterative_auto_discovery(
    config: IterativeDiscoveryConfig | dict[str, Any],
) -> IterativeDiscoveryResult:
    """Run several graph-guided discovery iterations.

    Each iteration runs ``ideas_per_iteration`` ideas.  Before iteration 2 and
    later, the orchestrator builds a cumulative idea graph from seed and prior
    iteration runs, plans direction prompts, and passes those artifacts to the
    idea agents.
    """
    if not isinstance(config, IterativeDiscoveryConfig):
        config = IterativeDiscoveryConfig(**dict(config))
    if config.knowledge_mode not in CLAIM_KNOWLEDGE_MODES:
        raise ValueError(
            "knowledge_mode must be one of "
            + ", ".join(sorted(CLAIM_KNOWLEDGE_MODES))
        )
    output_dir = Path(config.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    run_dirs = [Path(p) for p in config.seed_run_dirs]
    results: list[DiscoveryRunResult] = []
    claim_refresh_results: list[ClaimRefreshResult] = []

    prior_graph_path: Path | None = None
    prior_direction_path: Path | None = None
    for idx in range(1, int(config.iterations) + 1):
        run_dir = output_dir / f"iteration_{idx:02d}"
        schema = _schema_for_h5cd(
            config.h5cd_path,
            dataset_name=config.dataset_name,
            enrichment=config.enrichment,
        )
        claims_paths = _active_claims_paths(output_dir, config)
        if run_dirs or claims_paths or _schema_has_knowledge_seeds(schema):
            prior_dir = output_dir / f"iteration_{idx:02d}_prior"
            graph = build_idea_graph_from_runs(
                run_dirs,
                graph_id=f"prior_to_iteration_{idx:02d}",
                claims_paths=claims_paths,
            )
            graph_paths = write_idea_graph_artifacts(graph, prior_dir)
            directions = plan_discovery_directions(graph, schema, max_directions=8)
            direction_paths = write_direction_artifacts(directions, prior_dir)
            prior_graph_path = Path(graph_paths["graph_json"])
            prior_direction_path = Path(direction_paths["directions_markdown"])

        result = run_auto_discovery(DiscoveryRunConfig(
            h5cd_path=config.h5cd_path,
            output_dir=run_dir,
            max_ideas=config.ideas_per_iteration,
            accepted_idea_target=config.ideas_per_iteration,
            max_generation_attempts=config.max_generation_attempts,
            max_complexity=config.max_complexity,
            idea_source=config.idea_source,
            code_source=config.code_source,
            model=config.model,
            reasoning_effort=config.reasoning_effort,
            llm_timeout=config.llm_timeout,
            idea_agent_count=config.idea_agent_count,
            notebook_agent_concurrency=config.notebook_agent_concurrency,
            generate_schematic_image=config.generate_schematic_image,
            schematic_image_model=config.schematic_image_model,
            schematic_image_model_args=config.schematic_image_model_args,
            execute=config.execute,
            store_schema=config.store_schema,
            dataset_name=config.dataset_name,
            enrichment=config.enrichment,
            prior_graph_path=prior_graph_path,
            direction_context_path=prior_direction_path,
            claims_paths=claims_paths,
        ))
        results.append(result)
        claims_paths = _active_claims_paths(output_dir, config)
        claim_refresh = refresh_literature_claims_for_iteration(
            run_dir=run_dir,
            schema=schema,
            seed_claim_paths=claims_paths,
            mode=config.knowledge_mode,
        )
        claim_refresh_results.append(claim_refresh)
        run_dirs.append(run_dir)
        _write_iterative_manifest(
            output_dir,
            config,
            run_dirs,
            results,
            claim_refresh_results,
        )

    claims_paths = _active_claims_paths(output_dir, config)
    final_graph = build_idea_graph_from_runs(
        run_dirs,
        graph_id=f"iterative:{output_dir.name}",
        claims_paths=claims_paths,
    )
    final_graph_paths = write_idea_graph_artifacts(final_graph, output_dir)
    final_schema = _schema_for_h5cd(
        config.h5cd_path,
        dataset_name=config.dataset_name,
        enrichment=config.enrichment,
    )
    final_directions = plan_discovery_directions(final_graph, final_schema, max_directions=12)
    final_direction_paths = write_direction_artifacts(final_directions, output_dir)
    html_path = write_idea_graph_html(
        final_graph,
        output_dir / "idea_graph.html",
        title="U-Chrom Iterative Idea Graph",
        notebook_base_url="../_auto_discovery_notebooks",
    )
    result = IterativeDiscoveryResult(
        output_dir=str(output_dir),
        run_dirs=[str(p) for p in run_dirs],
        iteration_results=results,
        graph_path=final_graph_paths["graph_json"],
        graph_summary_path=final_graph_paths["graph_summary"],
        directions_path=final_direction_paths["directions_json"],
        direction_summary_path=final_direction_paths["directions_markdown"],
        html_path=str(html_path),
        claim_refresh_results=claim_refresh_results,
    )
    (output_dir / "iterative_result.json").write_text(
        json.dumps(result.to_dict(), indent=2, default=str) + "\n"
    )
    return result


def _schema_for_h5cd(
    path: str | Path,
    *,
    dataset_name: str | None,
    enrichment: dict[str, Any] | None = None,
) -> dict[str, Any]:
    from uchrom import ChromData

    cdata = ChromData.read(path)
    if enrichment is not None:
        from .enrichment import DiscoveryEnrichmentConfig, enrich_for_discovery

        enrich_for_discovery(cdata, DiscoveryEnrichmentConfig(**dict(enrichment)))
    return build_discovery_schema(cdata, store=False, dataset_name=dataset_name)


def _claims_paths_for_output(
    output_dir: Path,
    *,
    extra_paths: list[str | Path] | None = None,
) -> list[Path]:
    paths: list[Path] = []
    for raw in extra_paths or []:
        path = Path(raw)
        if path.exists():
            paths.append(path)
    for rel in ("browser/claims.jsonl", "literature/claims.jsonl", "claims.jsonl"):
        path = output_dir / rel
        if path.exists():
            paths.append(path)
    seen: set[str] = set()
    unique: list[Path] = []
    for path in paths:
        key = str(path)
        if key not in seen:
            unique.append(path)
            seen.add(key)
    return unique


def _active_claims_paths(
    output_dir: Path,
    config: IterativeDiscoveryConfig,
) -> list[Path]:
    if config.knowledge_mode == "off":
        return []
    return _claims_paths_for_output(output_dir, extra_paths=config.claims_paths)


def _schema_has_knowledge_seeds(schema: dict[str, Any]) -> bool:
    return bool(schema.get("references") or schema.get("user_annotations"))


def _write_iterative_manifest(
    output_dir: Path,
    config: IterativeDiscoveryConfig,
    run_dirs: list[Path],
    results: list[DiscoveryRunResult],
    claim_refresh_results: list[ClaimRefreshResult],
) -> None:
    payload = {
        "config": asdict(config),
        "run_dirs": [str(path) for path in run_dirs],
        "iteration_results": [result.__dict__ for result in results],
        "claim_refresh_results": [
            result.to_dict() for result in claim_refresh_results
        ],
    }
    (output_dir / "iterative_manifest.json").write_text(
        json.dumps(payload, indent=2, default=str) + "\n"
    )
