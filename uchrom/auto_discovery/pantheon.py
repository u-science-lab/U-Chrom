"""PantheonOS-backed auto-discovery orchestration."""

from __future__ import annotations

import asyncio
import base64
import inspect
import json
import math
import mimetypes
import os
import re
import shutil
import sys
import warnings
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from .ideas import DiscoveryIdea
from .schema import schema_to_agent_context


warnings.filterwarnings(
    "ignore",
    message='Field name "validate" in "read_notebook" shadows.*',
    category=UserWarning,
)


PANTHEON_IDEA_DIRECTIONS = [
    "cell-type-specific chromatin tracing and IF marker hypotheses",
    "RNA-expression-linked chromatin or IF hypotheses",
    "radial, lamina, and nuclear-position hypotheses",
    "chromosome-specific and inter-chromosomal organization hypotheses",
    "negative-control-aware robustness hypotheses",
]


@dataclass
class PantheonAgentRecord:
    """Audit record for one Pantheon agent call."""

    agent_name: str
    role: str
    prompt_path: str
    content: Any


@dataclass
class PantheonSchematicRecord:
    """Audit record for one post-hoc Pantheon schematic generation."""

    idea_id: str
    notebook: str
    prompt_path: str
    image_path: str | None
    status: str
    model: str | None = None
    attempt: int = 1
    visual_qa: Any = None
    error: str | None = None


async def generate_pantheon_ideas(
    schema: Mapping[str, Any],
    *,
    output_dir: str | Path,
    max_ideas: int,
    model: str | None = None,
    timeout: int = 420,
    idea_agent_count: int = 3,
    prior_graph_path: str | Path | None = None,
    frontier_context_path: str | Path | None = None,
) -> tuple[list[DiscoveryIdea], list[PantheonAgentRecord]]:
    """Generate ideas by running multiple Pantheon idea agents in parallel.

    Each idea agent receives only a file-access toolset. The schema and
    prompt are written to disk, and agents are instructed to read those files
    before returning DiscoveryIdea-compatible JSON.
    """
    workdir = Path(output_dir) / "pantheon" / "idea_agents"
    workdir.mkdir(parents=True, exist_ok=True)
    _write_pantheon_context(schema, workdir)

    idea_agent_count = max(1, int(idea_agent_count))
    ideas_per_agent = max(1, math.ceil(max_ideas / idea_agent_count))
    tasks = []
    for idx in range(idea_agent_count):
        direction = PANTHEON_IDEA_DIRECTIONS[idx % len(PANTHEON_IDEA_DIRECTIONS)]
        tasks.append(_run_one_idea_agent(
            idx=idx,
            direction=direction,
            schema=schema,
            workdir=workdir,
            ideas_per_agent=ideas_per_agent,
            model=model,
            timeout=timeout,
            prior_graph_path=Path(prior_graph_path) if prior_graph_path is not None else None,
            frontier_context_path=(
                Path(frontier_context_path)
                if frontier_context_path is not None
                else None
            ),
        ))

    records = list(await asyncio.gather(*tasks))
    ideas: list[DiscoveryIdea] = []
    seen: set[str] = set()
    for record in records:
        for idea in _ideas_from_agent_content(record.content):
            if idea.idea_id in seen:
                continue
            seen.add(idea.idea_id)
            ideas.append(idea)
            if len(ideas) >= max_ideas:
                return ideas, records
    return ideas, records


async def run_pantheon_notebook_agents(
    ideas: Sequence[DiscoveryIdea],
    *,
    schema: Mapping[str, Any],
    h5cd_path: str | Path,
    output_dir: str | Path,
    notebooks_dir: str | Path,
    model: str | None = None,
    timeout: int = 420,
    concurrency: int = 3,
    generate_schematic_image: bool = False,
    schematic_image_model: str | None = None,
    schematic_image_model_args: Mapping[str, Any] | None = None,
) -> list[PantheonAgentRecord]:
    """Run notebook exploration agents in parallel for accepted ideas.

    The caller is responsible for creating scaffold notebooks first. Each
    Pantheon notebook agent receives file-access and notebook toolsets, edits
    its assigned notebook, executes exploration cells, and returns a JSON
    status summary.
    """
    output_dir = Path(output_dir)
    workdir = output_dir / "pantheon" / "notebook_agents"
    workdir.mkdir(parents=True, exist_ok=True)
    _write_pantheon_context(schema, workdir)

    semaphore = asyncio.Semaphore(max(1, int(concurrency)))

    async def _guarded(idea: DiscoveryIdea) -> PantheonAgentRecord:
        async with semaphore:
            try:
                return await _run_one_notebook_agent(
                    idea=idea,
                    schema=schema,
                    h5cd_path=Path(h5cd_path),
                    output_dir=output_dir,
                    notebooks_dir=Path(notebooks_dir),
                    workdir=workdir,
                    model=model,
                    timeout=timeout,
                    generate_schematic_image=generate_schematic_image,
                    schematic_image_model=schematic_image_model,
                    schematic_image_model_args=schematic_image_model_args,
                )
            except BaseException as exc:
                agent_name = f"uchrom_notebook_agent_{idea.idea_id[:32]}"
                return PantheonAgentRecord(
                    agent_name=agent_name,
                    role="notebook_error",
                    prompt_path=str(workdir / f"{agent_name}_prompt.md"),
                    content={
                        "idea_id": idea.idea_id,
                        "status": "fail",
                        "error_type": type(exc).__name__,
                        "error": str(exc),
                    },
                )

    return list(await asyncio.gather(*[_guarded(idea) for idea in ideas]))


async def generate_pantheon_schematic_images_for_run(
    run_dir: str | Path,
    *,
    model: str | None = None,
    model_args: Mapping[str, Any] | None = None,
    timeout: int = 420,
    concurrency: int = 1,
    max_images: int | None = None,
    verified_only: bool = True,
    force: bool = False,
    visual_qa: bool = False,
    retries: int = 2,
    strict: bool = False,
) -> list[PantheonSchematicRecord]:
    """Generate and insert graphical abstracts for a completed discovery run.

    This is intentionally separate from notebook execution. Image generation is
    slow and provider-dependent, so completed/verified notebooks can be exported
    quickly first and then decorated with generated schematics in a bounded pass.
    """
    _load_env_file_if_needed(Path.home() / ".env")
    try:
        from pantheon.toolsets.file import FileManagerToolSet
    except ImportError as exc:  # pragma: no cover - depends on optional runtime
        raise ImportError(
            "PantheonOS is required for schematic image generation. Install it "
            "with `pip install pantheon-agents` or install PantheonOS from "
            "https://github.com/aristoteleo/PantheonOS in the agent runtime."
        ) from exc

    run_dir = Path(run_dir)
    workdir = run_dir / "pantheon" / "schematic_images"
    workdir.mkdir(parents=True, exist_ok=True)
    schema_path = workdir / "schematic_schema.json"
    if (run_dir / "ideas.jsonl").exists():
        schema_path.write_text(json.dumps({
            "run_dir": str(run_dir),
            "source": "completed U-Chrom auto-discovery run",
        }, indent=2))

    ideas = _ideas_by_id_for_run(run_dir)
    rows = _schematic_target_rows(run_dir, verified_only=verified_only, ideas=ideas)
    if max_images is not None:
        rows = rows[:max(0, int(max_images))]

    sem = asyncio.Semaphore(max(1, int(concurrency)))

    async def _one(row: Mapping[str, Any], *, attempt: int) -> PantheonSchematicRecord:
        idea = ideas[str(row["idea_id"])]
        notebook_path = _notebook_path_for_result(row, run_dir)
        prompt_path = workdir / f"{idea.idea_id}_prompt.md"
        prompt = _posthoc_schematic_prompt(
            idea=idea,
            result=row,
            stats_figure_path=run_dir / f"{idea.idea_id}_statistical_summary.png",
        )
        prompt_path.write_text(prompt)
        if not force and _notebook_has_cell(notebook_path, "schematic_image"):
            return PantheonSchematicRecord(
                idea_id=idea.idea_id,
                notebook=str(notebook_path),
                prompt_path=str(prompt_path),
                image_path=None,
                status="already_present",
                model=model,
                attempt=attempt,
            )
        async with sem:
            try:
                file_tool = FileManagerToolSet("file_manager", path=run_dir)
                response = await asyncio.wait_for(
                    file_tool.generate_image(
                        prompt=prompt,
                        reference_images=None,
                        model=model or "openai",
                        model_args=dict(model_args or {
                            "size": "1536x1024",
                            "quality": "high",
                            "output_format": "png",
                        }),
                    ),
                    timeout=max(1, int(timeout)),
                )
                image_path = _first_image_path_from_generation(response)
                if not image_path:
                    return PantheonSchematicRecord(
                        idea_id=idea.idea_id,
                        notebook=str(notebook_path),
                        prompt_path=str(prompt_path),
                        image_path=None,
                        status="fail",
                        model=model,
                        attempt=attempt,
                        error=json.dumps(response, default=str)[:1000],
                    )
                qa_result = None
                if visual_qa:
                    qa_result = await _observe_generated_schematic(
                        file_tool,
                        image_path,
                        timeout=timeout,
                    )
                _insert_schematic_image_from_agent_content(
                    {"schematic_image_path": image_path},
                    notebook_path,
                    run_dir,
                )
                status = (
                    "inserted"
                    if _notebook_has_cell(notebook_path, "schematic_image")
                    else "generated_not_inserted"
                )
                return PantheonSchematicRecord(
                    idea_id=idea.idea_id,
                    notebook=str(notebook_path),
                    prompt_path=str(prompt_path),
                    image_path=str(image_path),
                    status=status,
                    model=model,
                    attempt=attempt,
                    visual_qa=qa_result,
                )
            except BaseException as exc:
                return PantheonSchematicRecord(
                    idea_id=idea.idea_id,
                    notebook=str(notebook_path),
                    prompt_path=str(prompt_path),
                    image_path=None,
                    status="fail",
                    model=model,
                    attempt=attempt,
                    error=f"{type(exc).__name__}: {exc}",
                )

    records: list[PantheonSchematicRecord] = []
    max_attempts = max(1, int(retries) + 1)
    for attempt in range(1, max_attempts + 1):
        pending = [
            row for row in rows
            if (
                (force and attempt == 1)
                or not _notebook_has_cell(
                    _notebook_path_for_result(row, run_dir),
                    "schematic_image",
                )
            )
        ]
        if not pending:
            break
        records.extend(await asyncio.gather(*[
            _one(row, attempt=attempt) for row in pending
        ]))
        force = False

    coverage = schematic_coverage_for_run(
        run_dir,
        verified_only=verified_only,
        max_images=max_images,
    )
    _write_jsonl(workdir / "schematics.jsonl", [asdict(record) for record in records])
    (workdir / "schematic_coverage.json").write_text(
        json.dumps(coverage, indent=2, default=str) + "\n"
    )
    if strict and coverage["n_missing"] > 0:
        missing = ", ".join(Path(p).name for p in coverage["missing_notebooks"][:8])
        extra = "" if coverage["n_missing"] <= 8 else f", ... +{coverage['n_missing'] - 8} more"
        raise RuntimeError(
            "Graphical abstract generation incomplete: "
            f"{coverage['n_present']}/{coverage['n_targets']} notebooks contain "
            f"`schematic_image`; missing {coverage['n_missing']}: {missing}{extra}"
        )
    return records


def schematic_coverage_for_run(
    run_dir: str | Path,
    *,
    verified_only: bool = True,
    max_images: int | None = None,
) -> dict[str, Any]:
    """Return graphical-abstract coverage for a completed discovery run."""
    run_dir = Path(run_dir)
    ideas = _ideas_by_id_for_run(run_dir)
    rows = _schematic_target_rows(run_dir, verified_only=verified_only, ideas=ideas)
    if max_images is not None:
        rows = rows[:max(0, int(max_images))]
    present: list[str] = []
    missing: list[str] = []
    for row in rows:
        notebook_path = _notebook_path_for_result(row, run_dir)
        if _notebook_has_cell(notebook_path, "schematic_image"):
            present.append(str(notebook_path))
        else:
            missing.append(str(notebook_path))
    n_targets = len(rows)
    return {
        "run_dir": str(run_dir),
        "verified_only": verified_only,
        "n_targets": n_targets,
        "n_present": len(present),
        "n_missing": len(missing),
        "coverage": (len(present) / n_targets) if n_targets else 1.0,
        "present_notebooks": present,
        "missing_notebooks": missing,
    }


def _ideas_by_id_for_run(run_dir: Path) -> dict[str, DiscoveryIdea]:
    return {
        row["idea_id"]: DiscoveryIdea.from_dict(row)
        for row in _read_jsonl(run_dir / "ideas.jsonl")
        if isinstance(row, Mapping) and row.get("idea_id")
    }


def _schematic_target_rows(
    run_dir: Path,
    *,
    verified_only: bool,
    ideas: Mapping[str, DiscoveryIdea],
) -> list[dict[str, Any]]:
    rows = [
        row for row in _read_jsonl(run_dir / "results.jsonl")
        if isinstance(row, Mapping) and row.get("idea_id") in ideas
    ]
    if verified_only:
        rows = [
            row for row in rows
            if ((row.get("verification") or {}).get("status") == "pass")
        ]
    return rows


def _notebook_path_for_result(row: Mapping[str, Any], run_dir: Path) -> Path:
    idea_id = str(row.get("idea_id") or "")
    raw = str(row.get("notebook") or "")
    candidates: list[Path] = []
    if raw:
        raw_path = Path(raw)
        candidates.append(raw_path if raw_path.is_absolute() else Path.cwd() / raw_path)
        candidates.append(raw_path if raw_path.is_absolute() else run_dir / raw_path)
    if idea_id:
        candidates.append(run_dir / "notebooks" / f"{idea_id}.ipynb")
    for path in candidates:
        if path.exists():
            return path
    return candidates[0] if candidates else run_dir / "notebooks" / f"{idea_id}.ipynb"


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        row = json.loads(line)
        if isinstance(row, Mapping):
            rows.append(dict(row))
    return rows


def _write_jsonl(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as handle:
        for row in rows:
            handle.write(json.dumps(dict(row), default=str, sort_keys=True) + "\n")


def _notebook_has_cell(notebook_path: Path, cell_id: str) -> bool:
    try:
        nb = json.loads(notebook_path.read_text())
    except OSError:
        return False
    return any(cell.get("id") == cell_id for cell in nb.get("cells", []))


def _first_image_path_from_generation(response: Any) -> str | None:
    if not isinstance(response, Mapping):
        return None
    images = response.get("images")
    if isinstance(images, str):
        return images
    if isinstance(images, Sequence):
        for image in images:
            if image:
                return str(image)
    for key in ("image_path", "path", "output_path"):
        value = response.get(key)
        if value:
            return str(value)
    return None


async def _observe_generated_schematic(
    file_tool: Any,
    image_path: str,
    *,
    timeout: int,
) -> Any:
    question = (
        "Is this generated graphical abstract non-blank, readable, white/light "
        "background, scientific rather than decorative, and consistent with "
        "the stated U-Chrom hypothesis-test result? Flag overclaiming."
    )
    try:
        return await asyncio.wait_for(
            file_tool.observe_images(question=question, image_paths=[image_path]),
            timeout=max(1, int(timeout)),
        )
    except BaseException as exc:
        return {"success": False, "error": f"{type(exc).__name__}: {exc}"}


def _posthoc_schematic_prompt(
    *,
    idea: DiscoveryIdea,
    result: Mapping[str, Any],
    stats_figure_path: Path,
) -> str:
    verification = result.get("verification") or {}
    p_value = verification.get("p_value")
    effect_size = verification.get("effect_size", verification.get("parameter_value"))
    statistic = verification.get("observed_statistic", verification.get("parameter_value"))
    status = verification.get("status", "unknown")
    test_method = verification.get("test_method", "unknown statistical test")
    interpretation = _schematic_interpretation(
        expected_direction=idea.expected_direction,
        p_value=p_value,
        effect_size=effect_size,
        status=status,
    )
    stats_ref = str(stats_figure_path) if stats_figure_path.exists() else "not available"
    return f"""
Create a clean scientific graphical abstract for a U-Chrom auto-discovery
notebook. This is a schematic summary, not the quantitative evidence figure.

Composition and style:
- White or very light background, landscape 3:2 composition.
- Vector-like biomedical diagram style with crisp shapes and high contrast.
- Three left-to-right panels with simple arrows:
  1. Data: chromatin tracing loci as connected dots inside a nucleus, with the
     cell type and modality labels that are actually used.
  2. Analysis: marker-high versus marker-low or expression/position strata,
     mapped to 3D distance or spatial-coupling statistics.
  3. Result: observed effect compared with permutation/control/null. The
     conclusion must match the statistics below; do not overstate support.
- Use only a few large readable labels: "data", "analysis", "observed",
  "control", "3D distance", and the most important cell/marker names.
- Avoid tiny text, numeric tables, logos, UI chrome, citations, fake microscopy
  textures, photorealism, decorative gradients, and unverified molecular
  structures.

Idea:
- Title: {idea.idea_title}
- Hypothesis: {idea.biological_hypothesis}
- Parameter: {idea.computable_parameter}
- Modalities: {", ".join(idea.modalities)}
- Cell types: {", ".join(idea.cell_types)}
- Expected direction: {idea.expected_direction}

Hypothesis-test result to depict accurately:
- Verification status: {status}
- Test method: {test_method}
- Observed statistic: {statistic}
- Effect size: {effect_size}
- p-value: {p_value}
- Interpretation for the schematic: {interpretation}
- Quantitative figure path, for context only: {stats_ref}

If p-value is not significant or the observed direction contradicts the
expected direction, the schematic must show "not supported in this subset" or
"exploratory / no strong support" rather than a positive discovery claim.
""".strip()


def _schematic_interpretation(
    *,
    expected_direction: str,
    p_value: Any,
    effect_size: Any,
    status: Any,
) -> str:
    if status != "pass":
        return "exploratory result only; verification did not pass"
    try:
        p = float(p_value)
    except (TypeError, ValueError):
        return "exploratory result; p-value unavailable"
    try:
        effect = float(effect_size)
    except (TypeError, ValueError):
        effect = float("nan")
    significant = p <= 0.05
    expected_text = str(expected_direction).lower()
    contradicts_positive = "positive" in expected_text and effect < 0
    contradicts_negative = "negative" in expected_text and effect > 0
    if significant and not (contradicts_positive or contradicts_negative):
        return "statistically supported exploratory signal"
    if contradicts_positive or contradicts_negative:
        return "observed effect does not match the expected direction"
    return "not statistically supported in this subset"


async def _run_one_idea_agent(
    *,
    idx: int,
    direction: str,
    schema: Mapping[str, Any],
    workdir: Path,
    ideas_per_agent: int,
    model: str | None,
    timeout: int,
    prior_graph_path: Path | None = None,
    frontier_context_path: Path | None = None,
) -> PantheonAgentRecord:
    agent_name = f"uchrom_idea_agent_{idx + 1}"
    prompt = _idea_prompt(
        direction=direction,
        ideas_per_agent=ideas_per_agent,
        schema_path=workdir / "schema.json",
        context_path=workdir / "schema_context.md",
        prior_graph_path=prior_graph_path,
        frontier_context_path=frontier_context_path,
    )
    prompt_path = workdir / f"{agent_name}_prompt.md"
    prompt_path.write_text(prompt)
    agent = await _create_agent_with_tools(
        name=agent_name,
        role="idea",
        instructions=_idea_agent_instructions(direction),
        workdir=workdir,
        toolsets=("file",),
        model=model,
        timeout=timeout,
    )
    response = await agent.run(prompt, tool_use=True)
    return PantheonAgentRecord(
        agent_name=agent_name,
        role="idea",
        prompt_path=str(prompt_path),
        content=_agent_content(response),
    )


async def _run_one_notebook_agent(
    *,
    idea: DiscoveryIdea,
    schema: Mapping[str, Any],
    h5cd_path: Path,
    output_dir: Path,
    notebooks_dir: Path,
    workdir: Path,
    model: str | None,
    timeout: int,
    generate_schematic_image: bool,
    schematic_image_model: str | None,
    schematic_image_model_args: Mapping[str, Any] | None,
) -> PantheonAgentRecord:
    agent_name = f"uchrom_notebook_agent_{idea.idea_id[:32]}"
    idea_path = workdir / f"{idea.idea_id}.json"
    idea_path.write_text(json.dumps(idea.to_dict(), indent=2, sort_keys=True))
    notebook_path = notebooks_dir / f"{idea.idea_id}.ipynb"
    prompt = _notebook_prompt(
        idea=idea,
        schema=schema,
        idea_path=idea_path,
        schema_path=workdir / "schema.json",
        context_path=workdir / "schema_context.md",
        h5cd_path=h5cd_path,
        output_dir=output_dir,
        notebook_path=notebook_path,
        generate_schematic_image=generate_schematic_image,
        schematic_image_model=schematic_image_model,
        schematic_image_model_args=schematic_image_model_args,
    )
    prompt_path = workdir / f"{agent_name}_prompt.md"
    prompt_path.write_text(prompt)
    agent = await _create_agent_with_tools(
        name=agent_name,
        role="notebook",
        instructions=_notebook_agent_instructions(),
        workdir=output_dir,
        toolsets=("file", "notebook"),
        model=model,
        timeout=timeout,
    )
    response = await agent.run(prompt, tool_use=True)
    _recover_nested_notebook_copy(notebook_path)
    content = _agent_content(response)
    _apply_notebook_agent_content(content, notebook_path)
    _insert_statistical_figure_from_agent_content(content, notebook_path, output_dir)
    if generate_schematic_image:
        _insert_schematic_image_from_agent_content(content, notebook_path, output_dir)
    return PantheonAgentRecord(
        agent_name=agent_name,
        role="notebook",
        prompt_path=str(prompt_path),
        content=content,
    )


async def _create_agent_with_tools(
    *,
    name: str,
    role: str,
    instructions: str,
    workdir: Path,
    toolsets: Sequence[str],
    model: str | None,
    timeout: int,
):
    """Create a Pantheon agent with the requested restricted toolsets."""
    _load_env_file_if_needed(Path.home() / ".env")
    try:
        from pantheon.agent import Agent
        from pantheon.toolsets.file import FileManagerToolSet
        from pantheon.toolsets.notebook import IntegratedNotebookToolSet
    except ImportError as exc:  # pragma: no cover - depends on optional runtime
        raise ImportError(
            "PantheonOS is required for the Pantheon backend. Install it with "
            "`pip install pantheon-agents` or install PantheonOS from "
            "https://github.com/aristoteleo/PantheonOS in the agent runtime."
        ) from exc

    agent = Agent(
        name=name,
        instructions=instructions,
        model=model,
        tool_timeout=timeout,
        use_memory=False,
    )
    for toolset_name in toolsets:
        if toolset_name == "file":
            toolset = FileManagerToolSet("file_manager", path=workdir)
        elif toolset_name == "notebook":
            toolset = IntegratedNotebookToolSet(
                "notebook",
                workdir=str(workdir),
                streaming_mode="local",
            )
        else:
            raise ValueError(f"unknown Pantheon toolset: {toolset_name}")
        result = agent.toolset(toolset)
        if inspect.isawaitable(result):
            await result
    return agent


def _load_env_file_if_needed(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key in os.environ:
            continue
        os.environ[key] = value.strip().strip('"').strip("'")


def _write_pantheon_context(schema: Mapping[str, Any], workdir: Path) -> None:
    workdir.mkdir(parents=True, exist_ok=True)
    (workdir / "schema.json").write_text(json.dumps(schema, indent=2, default=str))
    (workdir / "schema_context.md").write_text(schema_to_agent_context(schema, max_items=80))


def _idea_agent_instructions(direction: str) -> str:
    return (
        "You are a U-Chrom PantheonOS idea-generation agent. You only have "
        "file access tools. Read the schema files from disk before proposing "
        "ideas. Do not assume unavailable data. Return JSON only. Each idea "
        "must include a concise, readable idea_markdown field for notebook "
        "display; do not put raw JSON in idea_markdown.\n\n"
        f"Focus direction: {direction}."
    )


def _notebook_agent_instructions() -> str:
    return (
        "You are a U-Chrom PantheonOS notebook exploration agent. You have "
        "file access and notebook tools. Keep all exploration in the assigned "
        "notebook. Use notebook_edit, notebook_execute, and notebook_read to "
        "insert Markdown notes, insert or update code cells, run code, inspect "
        "outputs, and refine the analysis. Do not modify package source files. "
        "Return a short JSON audit summary only after the notebook itself has "
        "been edited and executed."
    )


def _idea_prompt(
    *,
    direction: str,
    ideas_per_agent: int,
    schema_path: Path,
    context_path: Path,
    prior_graph_path: Path | None = None,
    frontier_context_path: Path | None = None,
) -> str:
    iterative_inputs = []
    if prior_graph_path is not None:
        iterative_inputs.append(f"- prior idea graph JSON: {prior_graph_path}")
    if frontier_context_path is not None:
        iterative_inputs.append(f"- graph-derived frontier markdown: {frontier_context_path}")
    iterative_block = ""
    if iterative_inputs:
        iterative_block = "\nIterative discovery context:\n" + "\n".join(iterative_inputs) + "\n"
    return f"""
Read these files with your file tool before answering:
- schema JSON: {schema_path}
- schema context: {context_path}
{iterative_block}

Generate up to {ideas_per_agent} diverse, computable U-Chrom discovery ideas.
Your focus direction is: {direction}

Rules:
- Use only modalities, fields, cell types, tracks, and genes present in schema.
- If iterative context files are provided, use them to avoid near-duplicate
  ideas and to build on supported, contradicted, under-tested, or literature-
  motivated graph frontiers.
- For child ideas derived from a prior result, include
  metadata.parent_idea_ids with the parent idea id and mention the frontier in
  idea_markdown.
- Each idea must define exactly one measurable parameter.
- Include idea_markdown as 3-6 short Markdown paragraphs or bullets. It should
  explain the hypothesis, data used, analysis sketch, expected result, and
  validation checks in human-readable prose.
- required_fields must be exact paths such as coords, spots.cell_id,
  tracks.H3K27ac, linked_adata.X, linked_adata.var.Pcp2.
- Include validation checks for required fields, cell counts, finite numeric
  output, a statistical hypothesis test with p-value, runtime,
  deterministic rerun, and a negative/permutation control when possible.
- Complexity must be 1-5.

Return JSON only:
{{
  "ideas": [
    {{
      "idea_title": "...",
      "idea_markdown": "### Rationale\\n...",
      "biological_hypothesis": "...",
      "computable_parameter": "...",
      "analysis_plan": "...",
      "modalities": ["chromatin_tracing", "if_tracks", "cell_metadata"],
      "cell_types": ["Granule"],
      "required_fields": ["coords", "spots.cell_id"],
      "validation_checks": ["required_fields_exist", "finite_numeric_output", "statistical_hypothesis_test"],
      "expected_direction": "...",
      "complexity": 4,
      "metadata": {{"parent_idea_ids": [], "frontier_id": "..."}}
    }}
  ]
}}
""".strip()


def _notebook_prompt(
    *,
    idea: DiscoveryIdea,
    schema: Mapping[str, Any],
    idea_path: Path,
    schema_path: Path,
    context_path: Path,
    h5cd_path: Path,
    output_dir: Path,
    notebook_path: Path,
    generate_schematic_image: bool = False,
    schematic_image_model: str | None = None,
    schematic_image_model_args: Mapping[str, Any] | None = None,
) -> str:
    notebook_tool_path = f"notebooks/{notebook_path.name}"
    result_path = output_dir / (idea.idea_id + "_result.csv")
    stats_figure_path = output_dir / (idea.idea_id + "_statistical_summary.png")
    kernel_name = "uchrom_auto_discovery"
    python_path = sys.executable
    schematic_task = _schematic_image_prompt_block(
        idea=idea,
        enabled=generate_schematic_image,
        image_model=schematic_image_model,
        image_model_args=schematic_image_model_args,
    )
    return f"""
Files available to you for audit and optional detail checks:
- idea JSON: {idea_path}
- schema JSON: {schema_path}
- schema context: {context_path}

The idea JSON and compact schema context you need are included below, so do
not spend time rereading every file unless a specific detail is missing.

First use the notebook content tool to inspect this scaffold notebook:
- notebook path: {notebook_tool_path}

Data paths:
- h5cd: {h5cd_path}
- run output directory: {output_dir}
- Python executable for the U-Chrom runtime: {python_path}
- Recommended kernel name: {kernel_name}

Task:
1. Use notebook_execute(action="setup_kernel", python_path={json.dumps(python_path)},
   kernel_name={json.dumps(kernel_name)}, display_name="U-Chrom auto-discovery").
2. Use notebook_edit(action="create", notebook_path={json.dumps(notebook_tool_path)},
   kernel_spec={json.dumps(kernel_name)}) to open the assigned notebook.
3. Use notebook_read(action="read_cells", notebook_path={json.dumps(notebook_tool_path)},
   include_details=true) to inspect the scaffold and current cell ids.
4. Keep the existing idea metadata and data-check cells. Add at least one
   Markdown critique/plan cell directly under "Exploration" before the main
   analysis code.
5. Replace the scaffold cell with cell_id "exploration_code" using
   notebook_edit(action="update_cell", cell_id="exploration_code", execute=true).
6. Add and execute at least one separate data-inspection code cell before the
   main exploration_code cell. Use it to preview selected columns, counts,
   finite-value coverage, or alignment assumptions. Keep this cell lightweight.
7. You may insert additional Markdown/code cells before or after the main
   analysis with notebook_edit(action="add_cell", execute=true for code cells).
8. The executed main exploration must define:
   - result_table: pandas DataFrame
   - analysis_summary: JSON-serializable dict
   The existing final scaffold cell will compute verification from these objects.
9. The main exploration must perform an explicit statistical hypothesis test,
   not only descriptive aggregation. In Markdown and/or analysis_summary,
   define:
   - null_hypothesis
   - alternative_hypothesis
   - test_method
   - observed_statistic
   - p_value
   - effect_size
   Use a lightweight test appropriate for the data, such as a bounded
   permutation/randomization test, bootstrap sign test, Mann-Whitney test,
   Spearman correlation test, or Fisher/exact test. For permutation-style
   tests, use a reproducible local RNG and keep the number of permutations
   between 100 and 1,000 unless sample size is too small. If the data are too
   small for the intended test, still return a finite exploratory effect size
   and set hypothesis_test_status="insufficient_data" with a clear note.
10. result_table must include p_value and test_method columns, plus the
   observed statistic/effect size or enough columns to reconstruct them.
   analysis_summary must include p_value, test_method, observed_statistic,
   effect_size, null_hypothesis, alternative_hypothesis, and
   hypothesis_test_status ("pass" or "insufficient_data").
11. Use a non-interactive matplotlib backend. Before importing pyplot in any
   added code cell, set:
   import os; os.environ.setdefault("MPLBACKEND", "Agg")
   import matplotlib; matplotlib.use("Agg", force=True)
   Do not switch to a GUI backend. Do not rely on an interactive window for
   display; save the figure and leave it visible in notebook output.
12. Create at least one clear matplotlib statistical figure that explains the
   idea and observed statistic. Save it to: {stats_figure_path}
   Also display the figure in the notebook output. Use restrained scientific
   styling: white background, labeled axes with units when available,
   readable title, explicit legend, and no decorative effects.
13. After saving the statistical figure, call
    file_manager.observe_images(image_paths=[{json.dumps(str(stats_figure_path))}],
    question="Is this a non-blank, clear scientific statistical figure with
    readable labels, visible data/control comparison, and no misleading
    decoration? Mention any fixes needed."). If the visual QA says the figure
    is blank, unreadable, mislabeled, or not matched to the idea/result, revise
    the plotting code and re-run the relevant cell.
14. The statistical figure must show the hypothesis-test evidence: observed
   statistic versus null/control distribution or group comparison, and annotate
   p-value, effect size, sample size, and test method when space allows.
15. Write result_table to: {result_path}
16. Execute the final verification cell with notebook_execute(action="execute",
   cell_id="verification") after the exploration succeeds.
17. Use notebook_read(..., include_details=true) to inspect outputs and add one
   final Markdown interpretation cell with the heading "## Final interpretation".
   Make it concrete and structured, not a vague narrative. It must include:
   - Hypothesis: restate the biological idea in one sentence.
   - Exploration: state the operational parameter, strata/groups, and data
     fields actually used.
   - Statistical evidence: test method, observed statistic, p-value,
     effect size, sample size or row count.
   - Conclusion: explicitly classify the idea as supported, not supported,
     contradicted, borderline, or inconclusive in this subset. Be clear that
     notebook verification is not the same as biological truth.
   - Caveat: one specific limitation of this exploratory test.
   Include a short "Visual QA" note for the statistical figure and optional
   schematic.
18. Keep the exploration compact: simple aggregation, bounded sampling,
   statistical plotting, no expensive pairwise all-vs-all loops over more than
   5,000 rows, and no unbounded permutation test.
   If the idea asks for a complex control, record a concise note instead.
19. Do not invent unavailable fields; use the schema.
20. Stop only after the notebook file contains your Markdown notes, at least two
    executed exploration code cells (inspection + main analysis),
    result_table/analysis_summary output with p-value/effect size,
    a statistical figure, and
    verification output, and visual QA notes.

{schematic_task}

Idea JSON:
{json.dumps(idea.to_dict(), indent=2)}

Compact schema context:
{schema_to_agent_context(schema, max_items=60)}

Return JSON only:
{{
  "idea_id": {json.dumps(idea.idea_id)},
  "notebook": {json.dumps(notebook_tool_path)},
  "result_path": {json.dumps(str(result_path))},
  "notebook_edited": true,
  "executed_cells": ["data_inspection", "exploration_code", "verification"],
  "statistical_figure_path": {json.dumps(str(stats_figure_path))},
  "schematic_image_path": "generated image path or null",
  "hypothesis_test": {{
    "test_method": "short test name",
    "p_value": 0.05,
    "effect_size": 0.0,
    "status": "pass|insufficient_data"
  }},
  "visual_qa": {{
    "statistical_figure": "short QA summary",
    "schematic_image": "short QA summary or null"
  }},
  "status": "executed|fail",
  "notes": ["brief audit notes"]
}}
""".strip()


def _schematic_image_prompt_block(
    *,
    idea: DiscoveryIdea,
    enabled: bool,
    image_model: str | None,
    image_model_args: Mapping[str, Any] | None,
) -> str:
    if not enabled:
        return (
            "Optional graphical abstract: disabled for this run. Do not call "
            "file_manager.generate_image."
        )
    model_text = json.dumps(image_model or "openai")
    model_args_text = json.dumps(dict(image_model_args or {
        "size": "1536x1024",
        "quality": "high",
        "output_format": "png",
    }), sort_keys=True)
    style_prompt = f"""
After the statistical analysis and verification, call file_manager.generate_image
exactly once to create a scientific graphical abstract for this idea and result.
Use model={model_text} and model_args={model_args_text}. Return the first image
path as schematic_image_path in your final JSON. U-Chrom will embed that image
near the top of the notebook after your agent call.

After generation, call file_manager.observe_images on the generated image path
with a QA question asking whether the schematic is non-blank, scientifically
clear, readable, white/light background, organized into the requested panels,
and consistent with the idea/result. If the QA says labels are unreadable,
the image is decorative, or the result is misleading, call generate_image one
more time with a corrected prompt and QA the replacement.

Image-generation prompt requirements:
- Make a clean scientific schematic / graphical abstract, not a decorative poster
  and not photorealistic microscopy.
- White or very light background, vector-like biomedical style, high contrast,
  colorblind-friendly palette.
- Landscape 3:2 or 16:9 composition suitable for a methods/results notebook.
- Three left-to-right panels:
  1. Data inputs: chromatin tracing loci as simple connected dots inside a
     nucleus, plus IF/RNA/multi-omics markers actually used by the idea.
  2. Computation: top-vs-bottom marker bins or expression strata, arrows to
     adjacent or pairwise 3D distance statistics.
  3. Result: direction of the observed effect and control/permutation contrast
     as a simple visual summary.
- Use only a few large, readable labels. Prefer labels like "cell type",
  "marker high", "marker low", "3D distance", "observed", "control".
- Do not include dense numeric tables, tiny text, logos, UI chrome, citations,
  fake microscopy texture, or unverified molecular structures.
- The image should communicate the hypothesis and result, while the statistical
  matplotlib plot remains the quantitative evidence.

Idea title: {idea.idea_title}
Hypothesis: {idea.biological_hypothesis}
Parameter: {idea.computable_parameter}
Expected direction: {idea.expected_direction}
""".strip()
    return style_prompt


def _agent_content(response: Any) -> Any:
    if hasattr(response, "content"):
        return response.content
    return response


def _ideas_from_agent_content(content: Any) -> list[DiscoveryIdea]:
    data = _coerce_json_content(content)
    if isinstance(data, Mapping):
        rows = data.get("ideas", data.get("Ideas", data.get("items", [])))
        if isinstance(rows, Mapping):
            rows = [rows]
    elif isinstance(data, list):
        rows = data
    else:
        rows = []
    ideas: list[DiscoveryIdea] = []
    for row in rows:
        if hasattr(row, "model_dump"):
            row = row.model_dump()
        if not isinstance(row, Mapping):
            continue
        ideas.append(DiscoveryIdea.from_dict(row))
    return ideas


def _coerce_json_content(content: Any) -> Any:
    if hasattr(content, "model_dump"):
        return content.model_dump()
    if isinstance(content, (Mapping, list)):
        return content
    text = str(content)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    match = re.search(r"```(?:json)?\s*(.*?)```", text, flags=re.DOTALL | re.IGNORECASE)
    if match:
        return json.loads(match.group(1))
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        return json.loads(text[start:end + 1])
    start = text.find("[")
    end = text.rfind("]")
    if start >= 0 and end > start:
        return json.loads(text[start:end + 1])
    raise ValueError(f"Pantheon agent response did not contain JSON: {text[:500]}")


def _recover_nested_notebook_copy(notebook_path: Path) -> None:
    """Recover when a notebook tool treats an absolute path as relative."""
    if not notebook_path.exists():
        return
    if _notebook_placeholder_replaced(notebook_path):
        return
    candidates = [
        path for path in notebook_path.parent.rglob(notebook_path.name)
        if path != notebook_path
    ]
    for candidate in sorted(candidates, key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            text = candidate.read_text()
        except OSError:
            continue
        if "PantheonOS notebook agent did not replace" in text:
            continue
        shutil.copyfile(candidate, notebook_path)
        return


def _notebook_placeholder_replaced(notebook_path: Path) -> bool:
    try:
        text = notebook_path.read_text()
    except OSError:
        return False
    return "PantheonOS notebook agent did not replace" not in text


def _apply_notebook_agent_content(content: Any, notebook_path: Path) -> None:
    if _notebook_placeholder_replaced(notebook_path):
        return
    data = _coerce_json_content(content)
    if not isinstance(data, Mapping) or "analysis_code" not in data:
        raise ValueError(
            "Pantheon notebook agent did not edit the notebook placeholder "
            "or return legacy analysis_code JSON"
        )
    analysis_code = str(data["analysis_code"]).strip()
    if not analysis_code:
        raise ValueError("Pantheon notebook agent returned empty analysis_code")
    nb = json.loads(notebook_path.read_text())
    for cell in nb.get("cells", []):
        if cell.get("id") == "exploration_code":
            cell["source"] = (analysis_code + "\n").splitlines(keepends=True)
            cell["outputs"] = []
            cell["execution_count"] = None
            notebook_path.write_text(json.dumps(nb, indent=2))
            return
    raise ValueError(f"Notebook missing exploration_code cell: {notebook_path}")


def _insert_schematic_image_from_agent_content(
    content: Any,
    notebook_path: Path,
    output_dir: Path,
) -> None:
    data = _coerce_json_content(content)
    if not isinstance(data, Mapping):
        return
    image_path = (
        data.get("schematic_image_path")
        or data.get("schematic_image")
        or data.get("graphical_abstract_path")
    )
    if isinstance(image_path, list):
        image_path = image_path[0] if image_path else None
    if not image_path:
        return
    image_ref = _image_markdown_reference(str(image_path), output_dir)
    if not image_ref:
        return
    _insert_markdown_image_cell(
        notebook_path,
        cell_id="schematic_image",
        heading="Graphical abstract",
        alt_prefix="Scientific schematic",
        image_ref=image_ref,
        note=(
            "Generated after notebook exploration with Pantheon "
            "`file_manager.generate_image`."
        ),
        insert_after_cell_id="idea_metadata",
    )


def _insert_statistical_figure_from_agent_content(
    content: Any,
    notebook_path: Path,
    output_dir: Path,
) -> None:
    data = _coerce_json_content(content)
    if not isinstance(data, Mapping):
        return
    figure_path = data.get("statistical_figure_path") or data.get("figure_path")
    if isinstance(figure_path, list):
        figure_path = figure_path[0] if figure_path else None
    if not figure_path:
        return
    image_ref = _image_markdown_reference(str(figure_path), output_dir)
    if not image_ref:
        return
    _insert_markdown_image_cell(
        notebook_path,
        cell_id="statistical_figure",
        heading="Statistical figure",
        alt_prefix="Statistical figure",
        image_ref=image_ref,
        note="Agent-generated quantitative figure saved during exploration.",
        insert_after_cell_id="exploration_code",
    )


def _insert_markdown_image_cell(
    notebook_path: Path,
    *,
    cell_id: str,
    heading: str,
    alt_prefix: str,
    image_ref: str,
    note: str,
    insert_after_cell_id: str,
) -> None:
    nb = json.loads(notebook_path.read_text())
    cells = nb.get("cells", [])
    if any(cell.get("id") == cell_id for cell in cells):
        return
    title = nb.get("metadata", {}).get("uchrom_auto_discovery", {}).get("idea_title", "idea")
    cell = {
        "cell_type": "markdown",
        "id": cell_id,
        "metadata": {"generated_by": "pantheon_auto_discovery"},
        "source": (
            f"## {heading}\n\n"
            f"![{alt_prefix} for {title}]({image_ref})\n\n"
            f"*{note}*\n"
        ).splitlines(keepends=True),
    }
    insert_at = 1 if cells else 0
    for idx, existing in enumerate(cells):
        if existing.get("id") == insert_after_cell_id:
            insert_at = idx + 1
            break
    cells.insert(insert_at, cell)
    notebook_path.write_text(json.dumps(nb, indent=2))


def _image_markdown_reference(image_path: str, output_dir: Path) -> str | None:
    if image_path.startswith(("http://", "https://", "data:")):
        return image_path
    candidates = [Path(image_path)]
    if not Path(image_path).is_absolute():
        candidates.extend([output_dir / image_path, Path.cwd() / image_path])
    existing = next((path for path in candidates if path.exists()), None)
    if existing is None:
        return None
    mime = mimetypes.guess_type(str(existing))[0] or "image/png"
    try:
        payload = base64.b64encode(existing.read_bytes()).decode("ascii")
    except OSError:
        return None
    return f"data:{mime};base64,{payload}"
