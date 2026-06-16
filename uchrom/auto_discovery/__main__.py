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
    run_p.add_argument(
        "--claim-path",
        action="append",
        default=[],
        help="Existing literature/browser claims JSONL to ingest into the run graph.",
    )

    enrich_p = sub.add_parser(
        "enrich",
        help="Add reusable sequence, annotation, structure, and peak features to an h5cd file",
    )
    enrich_p.add_argument("h5cd_path")
    enrich_p.add_argument("output_h5cd_path")
    enrich_p.add_argument("--fasta", default=None, help="FASTA path for sequence-derived features.")
    enrich_p.add_argument(
        "--sequence-feature",
        action="append",
        default=None,
        help="Sequence feature to compute. Repeatable; defaults to all built-in sequence features.",
    )
    enrich_p.add_argument("--gtf", default=None, help="GTF/GFF path for genome annotation features.")
    enrich_p.add_argument(
        "--annotation-feature",
        action="append",
        default=None,
        help="Annotation feature to compute. Repeatable; defaults to all built-in annotation features.",
    )
    enrich_p.add_argument("--promoter-upstream", type=int, default=-2000)
    enrich_p.add_argument("--promoter-downstream", type=int, default=500)
    enrich_p.add_argument(
        "--structure",
        action="append",
        choices=["tads", "loops", "compartments"],
        default=[],
        help="Run an existing structural caller and project its features. Repeatable.",
    )
    enrich_p.add_argument(
        "--project-existing-structure",
        action="store_true",
        help="Project existing results['tads'/'loops'/'compartments'] without running callers.",
    )
    enrich_p.add_argument("--chrom", action="append", default=None, help="Chromosome for structural callers.")
    enrich_p.add_argument("--device", default="auto", help="Device for structural callers.")
    enrich_p.add_argument(
        "--peak-track",
        action="append",
        default=[],
        help="Track column to aggregate and call peaks from. Repeatable.",
    )
    enrich_p.add_argument(
        "--peak-control-track",
        action="append",
        default=[],
        help="Optional control/background track for MACS-style peak calling. Repeatable.",
    )
    enrich_p.add_argument("--peak-method", default="auto", choices=["auto", "macs", "threshold"])
    enrich_p.add_argument("--peak-agg", default="mean", choices=["mean", "median", "max", "min", "sum"])
    enrich_p.add_argument("--peak-threshold", type=float, default=None)
    enrich_p.add_argument("--peak-quantile", type=float, default=0.95)
    enrich_p.add_argument("--peak-qvalue", type=float, default=0.05)
    enrich_p.add_argument("--peak-pvalue", type=float, default=None)
    enrich_p.add_argument("--peak-genome-size", type=float, default=None)
    enrich_p.add_argument("--peak-small-local-window-bins", type=int, default=10)
    enrich_p.add_argument("--peak-large-local-window-bins", type=int, default=100)
    enrich_p.add_argument("--peak-fragment-size-bins", type=int, default=1)
    enrich_p.add_argument("--peak-min-width-bins", type=int, default=1)
    enrich_p.add_argument("--peak-max-gap-bins", type=int, default=0)
    enrich_p.add_argument("--peak-signal-scale", type=float, default=1.0)
    enrich_p.add_argument("--peak-control-scale", type=float, default=None)
    enrich_p.add_argument("--peak-negative", default="clip", choices=["clip", "raise", "shift"])
    enrich_p.add_argument("--peak-nolambda", action="store_true")
    enrich_p.add_argument("--store-schema", action="store_true")
    enrich_p.add_argument("--overwrite", action="store_true")
    enrich_p.add_argument("--no-project", action="store_true")
    enrich_p.add_argument("--verbose", action="store_true")

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
    direction_p = sub.add_parser(
        "directions",
        aliases=["frontiers"],
        help="Plan next-iteration discovery directions from a run graph and h5cd schema",
    )
    direction_p.add_argument("run_dir")
    direction_p.add_argument("h5cd_path")
    direction_p.add_argument("--output-dir", default=None)
    direction_p.add_argument(
        "--max-directions",
        "--max-frontiers",
        dest="max_directions",
        type=int,
        default=8,
    )
    direction_p.add_argument("--dataset-name", default=None)

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
    iter_p.add_argument("--max-generation-attempts", type=int, default=3)
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
    iter_p.add_argument(
        "--generate-schematic-image",
        action=argparse.BooleanOptionalAction,
        default=True,
        help=(
            "Ask the Pantheon notebook agent to generate a graphical abstract "
            "during each iterative notebook run. Enabled by default; use "
            "--no-generate-schematic-image for a faster evidence-only run."
        ),
    )
    iter_p.add_argument("--schematic-image-model", default=None)
    iter_p.add_argument(
        "--schematic-image-model-args",
        default=None,
        help="JSON object with provider image args, e.g. '{\"size\":\"1536x1024\"}'.",
    )
    iter_p.add_argument("--dataset-name", default=None)
    iter_p.add_argument("--store-schema", action="store_true")
    iter_p.add_argument("--no-execute", action="store_true")
    iter_p.add_argument(
        "--knowledge-mode",
        choices=["off", "knowledge_guided", "browser_refresh"],
        default="knowledge_guided",
        help=(
            "External-knowledge behavior for iterative runs. "
            "knowledge_guided is enabled by default and uses cached claims, "
            "h5cd references, and user annotations."
        ),
    )
    iter_p.add_argument(
        "--claim-path",
        action="append",
        default=[],
        help="Existing literature/browser claims JSONL to seed every iteration.",
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
            claims_paths=args.claim_path,
        ))
        print(json.dumps(result.__dict__, indent=2))
        return 0
    if args.cmd == "enrich":
        from pathlib import Path

        from uchrom import ChromData
        from uchrom.fea import add_annotation_features, add_sequence_features, call_peaks_from_track
        from uchrom.strc import add_structural_features, call_structures_multi

        cdata = ChromData.read(args.h5cd_path)
        project = not args.no_project
        summary = {
            "input_h5cd_path": str(args.h5cd_path),
            "output_h5cd_path": str(args.output_h5cd_path),
            "sequence_features": [],
            "annotation_features": [],
            "structures": [],
            "peak_tracks": {},
            "schema_stored": False,
        }
        if args.fasta:
            table = add_sequence_features(
                cdata,
                args.fasta,
                features=args.sequence_feature,
                project=project,
                overwrite=args.overwrite,
            )
            summary["sequence_features"] = [c for c in table.columns if c not in {"chrom", "start", "end"}]
        if args.gtf:
            table = add_annotation_features(
                cdata,
                args.gtf,
                features=args.annotation_feature,
                promoter_window=(args.promoter_upstream, args.promoter_downstream),
                project=project,
                overwrite=args.overwrite,
            )
            summary["annotation_features"] = [c for c in table.columns if c not in {"chrom", "start", "end"}]
        if args.structure:
            called = call_structures_multi(
                cdata,
                structures=args.structure,
                chroms=args.chrom,
                device=args.device,
                store=True,
                verbose=args.verbose,
            )
            table = add_structural_features(cdata, project=project, overwrite=args.overwrite)
            summary["structures"] = sorted(called.keys())
            summary["structural_features"] = [c for c in table.columns if c not in {"chrom", "start", "end"}]
        elif args.project_existing_structure:
            table = add_structural_features(cdata, project=project, overwrite=args.overwrite)
            summary["structures"] = ["existing"]
            summary["structural_features"] = [c for c in table.columns if c not in {"chrom", "start", "end"}]
        controls = list(args.peak_control_track or [])
        if len(controls) > 1 and len(controls) != len(args.peak_track):
            raise ValueError("--peak-control-track must be provided once or once per --peak-track")
        for i, track in enumerate(args.peak_track):
            control_track = None
            if len(controls) == 1:
                control_track = controls[0]
            elif len(controls) == len(args.peak_track):
                control_track = controls[i]
            peaks = call_peaks_from_track(
                cdata,
                track,
                method=args.peak_method,
                control_track=control_track,
                agg=args.peak_agg,
                threshold=args.peak_threshold,
                quantile=args.peak_quantile,
                qvalue=(None if args.peak_pvalue is not None else args.peak_qvalue),
                pvalue=args.peak_pvalue,
                genome_size=args.peak_genome_size,
                small_local_window_bins=args.peak_small_local_window_bins,
                large_local_window_bins=args.peak_large_local_window_bins,
                fragment_size_bins=args.peak_fragment_size_bins,
                nolambda=args.peak_nolambda,
                min_width_bins=args.peak_min_width_bins,
                max_gap_bins=args.peak_max_gap_bins,
                signal_scale=args.peak_signal_scale,
                control_scale=args.peak_control_scale,
                negative=args.peak_negative,
                project=project,
                overwrite=args.overwrite,
            )
            method = "threshold" if args.peak_method == "auto" and args.peak_threshold is not None else args.peak_method
            if method == "auto":
                method = "macs"
            summary["peak_tracks"][track] = {
                "n_peaks": int(len(peaks)),
                "method": "macs_style" if method == "macs" else method,
                "control_track": control_track,
            }
        if args.store_schema:
            cdata.build_discovery_schema(store=True)
            summary["schema_stored"] = True
        out_path = Path(args.output_h5cd_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        cdata.write(out_path)
        print(json.dumps(summary, indent=2))
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
    if args.cmd in {"frontiers", "directions"}:
        from uchrom import ChromData

        from .direction import plan_discovery_directions, write_direction_artifacts
        from .graph import build_idea_graph_from_run, write_idea_graph_artifacts

        cdata = ChromData.read(args.h5cd_path)
        schema = cdata.build_discovery_schema(store=False, dataset_name=args.dataset_name)
        graph = build_idea_graph_from_run(args.run_dir)
        graph_paths = write_idea_graph_artifacts(graph, args.output_dir or args.run_dir)
        directions = plan_discovery_directions(
            graph,
            schema,
            max_directions=args.max_directions,
        )
        direction_paths = write_direction_artifacts(
            directions,
            args.output_dir or args.run_dir,
        )
        print(json.dumps({
            "n_directions": len(directions),
            "direction_ids": [d.direction_id for d in directions],
            **graph_paths,
            **direction_paths,
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
            max_generation_attempts=args.max_generation_attempts,
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
            execute=not args.no_execute,
            store_schema=args.store_schema,
            dataset_name=args.dataset_name,
            knowledge_mode=args.knowledge_mode,
            claims_paths=args.claim_path,
        ))
        print(json.dumps(result.to_dict(), indent=2))
        return 0
    return 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
