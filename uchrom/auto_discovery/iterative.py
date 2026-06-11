"""Multi-iteration orchestration for U-Chrom auto-discovery."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from .frontier import plan_discovery_frontiers, write_frontier_artifacts
from .graph import build_idea_graph_from_runs, write_idea_graph_artifacts
from .runner import DiscoveryRunConfig, DiscoveryRunResult, _run_async, run_auto_discovery
from .visualization import write_idea_graph_html


@dataclass
class IterativeDiscoveryConfig:
    """Configuration for repeated auto-discovery iterations."""

    h5cd_path: str | Path
    output_dir: str | Path
    iterations: int = 2
    ideas_per_iteration: int = 20
    seed_run_dirs: list[str | Path] = field(default_factory=list)
    max_complexity: int = 5
    idea_source: str = "pantheon"
    code_source: str = "pantheon"
    model: str | None = None
    reasoning_effort: str | None = None
    llm_timeout: int = 900
    idea_agent_count: int = 4
    notebook_agent_concurrency: int = 4
    generate_schematic_image: bool = False
    schematic_image_model: str | None = None
    schematic_image_model_args: dict[str, Any] | None = None
    schematic_retries: int = 2
    schematic_visual_qa: bool = False
    strict_schematics: bool = False
    execute: bool = True
    store_schema: bool = False
    dataset_name: str | None = None


@dataclass
class IterativeDiscoveryResult:
    """Summary of a multi-iteration auto-discovery run."""

    output_dir: str
    run_dirs: list[str]
    iteration_results: list[DiscoveryRunResult]
    graph_path: str
    graph_summary_path: str
    frontiers_path: str
    frontier_summary_path: str
    html_path: str

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
    iteration runs, plans frontier prompts, and passes those artifacts to the
    idea agents.
    """
    if not isinstance(config, IterativeDiscoveryConfig):
        config = IterativeDiscoveryConfig(**dict(config))
    output_dir = Path(config.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    run_dirs = [Path(p) for p in config.seed_run_dirs]
    results: list[DiscoveryRunResult] = []

    prior_graph_path: Path | None = None
    prior_frontier_path: Path | None = None
    for idx in range(1, int(config.iterations) + 1):
        run_dir = output_dir / f"iteration_{idx:02d}"
        if run_dirs:
            prior_dir = output_dir / f"iteration_{idx:02d}_prior"
            graph = build_idea_graph_from_runs(
                run_dirs,
                graph_id=f"prior_to_iteration_{idx:02d}",
            )
            graph_paths = write_idea_graph_artifacts(graph, prior_dir)
            schema = _schema_for_h5cd(config.h5cd_path, dataset_name=config.dataset_name)
            frontiers = plan_discovery_frontiers(graph, schema, max_frontiers=8)
            frontier_paths = write_frontier_artifacts(frontiers, prior_dir)
            prior_graph_path = Path(graph_paths["graph_json"])
            prior_frontier_path = Path(frontier_paths["frontiers_markdown"])

        result = run_auto_discovery(DiscoveryRunConfig(
            h5cd_path=config.h5cd_path,
            output_dir=run_dir,
            max_ideas=config.ideas_per_iteration,
            max_complexity=config.max_complexity,
            idea_source=config.idea_source,
            code_source=config.code_source,
            model=config.model,
            reasoning_effort=config.reasoning_effort,
            llm_timeout=config.llm_timeout,
            idea_agent_count=config.idea_agent_count,
            notebook_agent_concurrency=config.notebook_agent_concurrency,
            generate_schematic_image=False,
            execute=config.execute,
            store_schema=config.store_schema,
            dataset_name=config.dataset_name,
            prior_graph_path=prior_graph_path,
            frontier_context_path=prior_frontier_path,
        ))
        if config.generate_schematic_image and config.execute and result.n_verified:
            from .pantheon import generate_pantheon_schematic_images_for_run

            _run_async(generate_pantheon_schematic_images_for_run(
                run_dir,
                model=config.schematic_image_model,
                model_args=config.schematic_image_model_args,
                timeout=config.llm_timeout,
                concurrency=1,
                verified_only=True,
                visual_qa=config.schematic_visual_qa,
                retries=config.schematic_retries,
                strict=config.strict_schematics,
            ))
        results.append(result)
        run_dirs.append(run_dir)
        _write_iterative_manifest(output_dir, config, run_dirs, results)

    final_graph = build_idea_graph_from_runs(
        run_dirs,
        graph_id=f"iterative:{output_dir.name}",
    )
    final_graph_paths = write_idea_graph_artifacts(final_graph, output_dir)
    final_schema = _schema_for_h5cd(config.h5cd_path, dataset_name=config.dataset_name)
    final_frontiers = plan_discovery_frontiers(final_graph, final_schema, max_frontiers=12)
    final_frontier_paths = write_frontier_artifacts(final_frontiers, output_dir)
    html_path = write_idea_graph_html(
        final_graph,
        output_dir / "idea_graph.html",
        title="U-Chrom Iterative Idea Graph",
        notebook_base_url="_auto_discovery_notebooks",
    )
    result = IterativeDiscoveryResult(
        output_dir=str(output_dir),
        run_dirs=[str(p) for p in run_dirs],
        iteration_results=results,
        graph_path=final_graph_paths["graph_json"],
        graph_summary_path=final_graph_paths["graph_summary"],
        frontiers_path=final_frontier_paths["frontiers_json"],
        frontier_summary_path=final_frontier_paths["frontiers_markdown"],
        html_path=str(html_path),
    )
    (output_dir / "iterative_result.json").write_text(
        json.dumps(result.to_dict(), indent=2, default=str) + "\n"
    )
    return result


def _schema_for_h5cd(path: str | Path, *, dataset_name: str | None) -> dict[str, Any]:
    from uchrom import ChromData

    cdata = ChromData.read(path)
    return cdata.build_discovery_schema(store=False, dataset_name=dataset_name)


def _write_iterative_manifest(
    output_dir: Path,
    config: IterativeDiscoveryConfig,
    run_dirs: list[Path],
    results: list[DiscoveryRunResult],
) -> None:
    payload = {
        "config": asdict(config),
        "run_dirs": [str(path) for path in run_dirs],
        "iteration_results": [result.__dict__ for result in results],
    }
    (output_dir / "iterative_manifest.json").write_text(
        json.dumps(payload, indent=2, default=str) + "\n"
    )
