"""Command-line entry point for U-Chrom auto-discovery."""

from __future__ import annotations

import argparse
import asyncio
import json
from dataclasses import asdict

from .runner import DiscoveryRunConfig, run_auto_discovery


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m uchrom.auto_discovery")
    sub = parser.add_subparsers(dest="cmd", required=True)

    run_p = sub.add_parser("run", help="Run schema -> idea -> notebook -> verification")
    run_p.add_argument("h5cd_path")
    run_p.add_argument("output_dir")
    run_p.add_argument("--max-ideas", type=int, default=12)
    run_p.add_argument(
        "--ideas-path",
        default=None,
        help="Reuse a JSONL file of DiscoveryIdea objects instead of generating new ideas.",
    )
    run_p.add_argument("--max-complexity", type=int, default=5)
    run_p.add_argument("--idea-source", choices=["pantheon", "openai"], default="pantheon")
    run_p.add_argument("--code-source", choices=["pantheon", "openai"], default="pantheon")
    run_p.add_argument("--model", default=None)
    run_p.add_argument(
        "--reasoning-effort",
        choices=["none", "minimal", "low", "medium", "high", "xhigh"],
        default=None,
    )
    run_p.add_argument("--llm-timeout", type=int, default=420)
    run_p.add_argument("--idea-agent-count", type=int, default=3)
    run_p.add_argument("--notebook-agent-concurrency", type=int, default=3)
    run_p.add_argument(
        "--generate-schematic-image",
        action="store_true",
        help="Ask the Pantheon notebook agent to generate a scientific schematic via the file toolset.",
    )
    run_p.add_argument(
        "--schematic-image-model",
        default=None,
        help="Pantheon image model selector, e.g. openai, gpt-image-2, or gemini.",
    )
    run_p.add_argument(
        "--schematic-image-model-args",
        default=None,
        help="JSON object with provider image args, e.g. '{\"size\":\"1536x1024\",\"quality\":\"high\"}'.",
    )
    run_p.add_argument("--dataset-name", default=None)
    run_p.add_argument("--store-schema", action="store_true")
    run_p.add_argument("--no-execute", action="store_true")

    schem_p = sub.add_parser(
        "schematics",
        help="Generate and insert graphical abstracts for a completed run",
    )
    schem_p.add_argument("run_dir")
    schem_p.add_argument("--model", default=None)
    schem_p.add_argument(
        "--model-args",
        default=None,
        help="JSON object with provider image args, e.g. '{\"size\":\"1536x1024\"}'.",
    )
    schem_p.add_argument("--timeout", type=int, default=420)
    schem_p.add_argument("--concurrency", type=int, default=1)
    schem_p.add_argument("--max-images", type=int, default=None)
    schem_p.add_argument("--include-unverified", action="store_true")
    schem_p.add_argument("--force", action="store_true")
    schem_p.add_argument(
        "--visual-qa",
        action="store_true",
        help="Also ask Pantheon observe_images to QA generated schematics.",
    )
    schem_p.add_argument(
        "--retries",
        type=int,
        default=2,
        help="Additional generation attempts for notebooks still missing a graphical abstract.",
    )
    schem_p.add_argument(
        "--strict",
        action="store_true",
        help="Fail if any target notebook still lacks a graphical abstract after retries.",
    )

    graph_p = sub.add_parser(
        "graph",
        help="Build graph artifacts from an existing auto-discovery run",
    )
    graph_p.add_argument("run_dir")
    graph_p.add_argument(
        "--output-dir",
        default=None,
        help="Directory that will receive graph/idea_graph.json and graph/graph_summary.md. Defaults to run_dir.",
    )
    frontier_p = sub.add_parser(
        "frontiers",
        help="Plan next-iteration discovery frontiers from a run graph and h5cd schema",
    )
    frontier_p.add_argument("run_dir")
    frontier_p.add_argument("h5cd_path")
    frontier_p.add_argument("--output-dir", default=None)
    frontier_p.add_argument("--max-frontiers", type=int, default=8)
    frontier_p.add_argument("--dataset-name", default=None)

    view_p = sub.add_parser(
        "view",
        help="Write a self-contained interactive HTML viewer for an idea graph",
    )
    view_p.add_argument("graph_json")
    view_p.add_argument("html_path")
    view_p.add_argument("--title", default="U-Chrom Idea Graph")
    view_p.add_argument("--notebook-base-url", default=None)

    claims_p = sub.add_parser(
        "claims",
        help="Ingest browser-agent claims JSONL into a graph artifact",
    )
    claims_p.add_argument("graph_json")
    claims_p.add_argument("claims_jsonl")
    claims_p.add_argument("--output-dir", default=None)
    claims_p.add_argument("--html-path", default=None)
    claims_p.add_argument("--notebook-base-url", default=None)

    iter_p = sub.add_parser(
        "iterate",
        help="Run multiple graph-guided auto-discovery iterations",
    )
    iter_p.add_argument("h5cd_path")
    iter_p.add_argument("output_dir")
    iter_p.add_argument("--iterations", type=int, default=2)
    iter_p.add_argument("--ideas-per-iteration", type=int, default=20)
    iter_p.add_argument("--seed-run-dir", action="append", default=[])
    iter_p.add_argument("--max-complexity", type=int, default=5)
    iter_p.add_argument("--idea-source", choices=["pantheon", "openai"], default="pantheon")
    iter_p.add_argument("--code-source", choices=["pantheon", "openai"], default="pantheon")
    iter_p.add_argument("--model", default=None)
    iter_p.add_argument(
        "--reasoning-effort",
        choices=["none", "minimal", "low", "medium", "high", "xhigh"],
        default=None,
    )
    iter_p.add_argument("--llm-timeout", type=int, default=900)
    iter_p.add_argument("--idea-agent-count", type=int, default=4)
    iter_p.add_argument("--notebook-agent-concurrency", type=int, default=4)
    iter_p.add_argument("--generate-schematic-image", action="store_true")
    iter_p.add_argument("--schematic-image-model", default=None)
    iter_p.add_argument(
        "--schematic-image-model-args",
        default=None,
        help="JSON object with provider image args, e.g. '{\"size\":\"1536x1024\"}'.",
    )
    iter_p.add_argument("--schematic-retries", type=int, default=2)
    iter_p.add_argument(
        "--schematic-visual-qa",
        action="store_true",
        help="Also ask Pantheon observe_images to QA generated schematics.",
    )
    iter_p.add_argument("--strict-schematics", action="store_true")
    iter_p.add_argument("--dataset-name", default=None)
    iter_p.add_argument("--store-schema", action="store_true")
    iter_p.add_argument("--no-execute", action="store_true")

    args = parser.parse_args(argv)
    if args.cmd == "run":
        result = run_auto_discovery(DiscoveryRunConfig(
            h5cd_path=args.h5cd_path,
            output_dir=args.output_dir,
            max_ideas=args.max_ideas,
            ideas_path=args.ideas_path,
            max_complexity=args.max_complexity,
            idea_source=args.idea_source,
            code_source=args.code_source,
            model=args.model,
            reasoning_effort=args.reasoning_effort,
            llm_timeout=args.llm_timeout,
            idea_agent_count=args.idea_agent_count,
            notebook_agent_concurrency=args.notebook_agent_concurrency,
            generate_schematic_image=args.generate_schematic_image,
            schematic_image_model=args.schematic_image_model,
            schematic_image_model_args=(
                json.loads(args.schematic_image_model_args)
                if args.schematic_image_model_args
                else None
            ),
            execute=not args.no_execute,
            store_schema=args.store_schema,
            dataset_name=args.dataset_name,
        ))
        print(json.dumps(result.__dict__, indent=2))
        return 0
    if args.cmd == "schematics":
        from .pantheon import generate_pantheon_schematic_images_for_run

        records = asyncio.run(generate_pantheon_schematic_images_for_run(
            args.run_dir,
            model=args.model,
            model_args=(json.loads(args.model_args) if args.model_args else None),
            timeout=args.timeout,
            concurrency=args.concurrency,
            max_images=args.max_images,
            verified_only=not args.include_unverified,
            force=args.force,
            visual_qa=args.visual_qa,
            retries=args.retries,
            strict=args.strict,
        ))
        print(json.dumps([asdict(record) for record in records], indent=2))
        return 0
    if args.cmd == "graph":
        from .graph import build_idea_graph_from_run, write_idea_graph_artifacts

        graph = build_idea_graph_from_run(args.run_dir)
        paths = write_idea_graph_artifacts(graph, args.output_dir or args.run_dir)
        print(json.dumps({"summary": graph.summary(), **paths}, indent=2))
        return 0
    if args.cmd == "frontiers":
        from uchrom import ChromData

        from .frontier import plan_discovery_frontiers, write_frontier_artifacts
        from .graph import build_idea_graph_from_run, write_idea_graph_artifacts

        cdata = ChromData.read(args.h5cd_path)
        schema = cdata.build_discovery_schema(store=False, dataset_name=args.dataset_name)
        graph = build_idea_graph_from_run(args.run_dir)
        graph_paths = write_idea_graph_artifacts(graph, args.output_dir or args.run_dir)
        frontiers = plan_discovery_frontiers(
            graph,
            schema,
            max_frontiers=args.max_frontiers,
        )
        frontier_paths = write_frontier_artifacts(
            frontiers,
            args.output_dir or args.run_dir,
        )
        print(json.dumps({
            "n_frontiers": len(frontiers),
            "frontier_ids": [f.frontier_id for f in frontiers],
            **graph_paths,
            **frontier_paths,
        }, indent=2))
        return 0
    if args.cmd == "view":
        from .visualization import write_idea_graph_html

        path = write_idea_graph_html(
            args.graph_json,
            args.html_path,
            title=args.title,
            notebook_base_url=args.notebook_base_url,
        )
        print(json.dumps({"html_path": str(path)}, indent=2))
        return 0
    if args.cmd == "claims":
        from .graph import ingest_literature_claims, load_idea_graph, write_idea_graph_artifacts
        from .visualization import write_idea_graph_html

        graph = load_idea_graph(args.graph_json)
        n_claims = ingest_literature_claims(graph, args.claims_jsonl)
        output_dir = args.output_dir or str(__import__("pathlib").Path(args.graph_json).parent.parent)
        paths = write_idea_graph_artifacts(graph, output_dir)
        out = {"n_claims": n_claims, **paths}
        if args.html_path:
            html_path = write_idea_graph_html(
                graph,
                args.html_path,
                notebook_base_url=args.notebook_base_url,
            )
            out["html_path"] = str(html_path)
        print(json.dumps(out, indent=2))
        return 0
    if args.cmd == "iterate":
        from .iterative import IterativeDiscoveryConfig, run_iterative_auto_discovery

        result = run_iterative_auto_discovery(IterativeDiscoveryConfig(
            h5cd_path=args.h5cd_path,
            output_dir=args.output_dir,
            iterations=args.iterations,
            ideas_per_iteration=args.ideas_per_iteration,
            seed_run_dirs=args.seed_run_dir,
            max_complexity=args.max_complexity,
            idea_source=args.idea_source,
            code_source=args.code_source,
            model=args.model,
            reasoning_effort=args.reasoning_effort,
            llm_timeout=args.llm_timeout,
            idea_agent_count=args.idea_agent_count,
            notebook_agent_concurrency=args.notebook_agent_concurrency,
            generate_schematic_image=args.generate_schematic_image,
            schematic_image_model=args.schematic_image_model,
            schematic_image_model_args=(
                json.loads(args.schematic_image_model_args)
                if args.schematic_image_model_args
                else None
            ),
            schematic_retries=args.schematic_retries,
            schematic_visual_qa=args.schematic_visual_qa,
            strict_schematics=args.strict_schematics,
            execute=not args.no_execute,
            store_schema=args.store_schema,
            dataset_name=args.dataset_name,
        ))
        print(json.dumps(result.to_dict(), indent=2))
        return 0
    return 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
