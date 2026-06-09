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
        ))
        print(json.dumps([asdict(record) for record in records], indent=2))
        return 0
    if args.cmd == "graph":
        from .graph import build_idea_graph_from_run, write_idea_graph_artifacts

        graph = build_idea_graph_from_run(args.run_dir)
        paths = write_idea_graph_artifacts(graph, args.output_dir or args.run_dir)
        print(json.dumps({"summary": graph.summary(), **paths}, indent=2))
        return 0
    return 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
