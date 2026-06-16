"""Runnable auto-discovery pipeline for ChromData."""

from __future__ import annotations

import asyncio
import json
import math
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Awaitable

from .ideas import DiscoveryIdea, review_idea_against_schema
from .notebooks import (
    create_exploration_notebook,
    execute_notebook_python,
    upsert_structured_conclusion,
)


@dataclass
class DiscoveryRunConfig:
    """Configuration for a local auto-discovery run."""

    h5cd_path: str | Path
    output_dir: str | Path
    max_ideas: int = 12
    accepted_idea_target: int | None = None
    max_generation_attempts: int = 3
    ideas_path: str | Path | None = None
    max_complexity: int = 5
    idea_source: str = "pantheon"
    code_source: str = "pantheon"
    model: str | None = None
    reasoning_effort: str | None = None
    llm_timeout: int = 420
    idea_agent_count: int = 3
    notebook_agent_concurrency: int = 3
    generate_schematic_image: bool = False
    schematic_image_model: str | None = None
    schematic_image_model_args: dict[str, Any] | None = None
    execute: bool = True
    stop_on_error: bool = False
    store_schema: bool = False
    dataset_name: str | None = None
    enrichment: dict[str, Any] | None = None
    prior_graph_path: str | Path | None = None
    direction_context_path: str | Path | None = None
    frontier_context_path: str | Path | None = None
    claims_paths: list[str | Path] = field(default_factory=list)


@dataclass
class DiscoveryRunResult:
    """Summary of an auto-discovery run."""

    output_dir: str
    n_generated: int
    n_accepted: int
    n_executed: int
    n_verified: int
    report_path: str
    ideas_path: str
    reviews_path: str
    results_path: str
    notebooks: list[str] = field(default_factory=list)
    agent_records_path: str | None = None
    graph_path: str | None = None
    graph_summary_path: str | None = None
    graph_html_path: str | None = None
    directions_path: str | None = None
    direction_summary_path: str | None = None
    enriched_h5cd_path: str | None = None
    enrichment_summary_path: str | None = None

    @property
    def frontiers_path(self) -> str | None:
        """Legacy alias for ``directions_path``."""
        return self.directions_path

    @property
    def frontier_summary_path(self) -> str | None:
        """Legacy alias for ``direction_summary_path``."""
        return self.direction_summary_path


def run_auto_discovery(config: DiscoveryRunConfig | dict[str, Any]) -> DiscoveryRunResult:
    """Run schema → idea → notebook → verification for one ``.h5cd``."""
    if not isinstance(config, DiscoveryRunConfig):
        config = DiscoveryRunConfig(**dict(config))

    from uchrom import ChromData

    input_h5cd_path = Path(config.h5cd_path)
    h5cd_path = input_h5cd_path
    output_dir = Path(config.output_dir)
    notebooks_dir = output_dir / "notebooks"
    output_dir.mkdir(parents=True, exist_ok=True)
    notebooks_dir.mkdir(parents=True, exist_ok=True)

    cdata = ChromData.read(input_h5cd_path)
    enrichment_summary: dict[str, Any] = {"enabled": False}
    enrichment_summary_path: Path | None = None
    enriched_h5cd_path: Path | None = None
    if config.enrichment is not None:
        from .enrichment import DiscoveryEnrichmentConfig, enrich_for_discovery

        enrichment_config = (
            config.enrichment
            if isinstance(config.enrichment, DiscoveryEnrichmentConfig)
            else DiscoveryEnrichmentConfig(**dict(config.enrichment))
        )
        enrichment_summary = enrich_for_discovery(cdata, enrichment_config)
        if enrichment_summary.get("enabled"):
            enriched_h5cd_path = output_dir / "enriched.h5cd"
            h5cd_path = enriched_h5cd_path
            enrichment_summary["enriched_h5cd_path"] = str(enriched_h5cd_path)
            enrichment_summary_path = output_dir / "enrichment_summary.json"
            enrichment_summary_path.write_text(
                json.dumps(enrichment_summary, indent=2, default=_json_default) + "\n"
            )
    schema = cdata.build_discovery_schema(store=config.store_schema, dataset_name=config.dataset_name)
    if config.store_schema or enriched_h5cd_path is not None:
        cdata.write(h5cd_path)

    agent_records_path = output_dir / "agent_records.jsonl"
    agent_records: list[dict[str, Any]] = []
    if config.ideas_path is not None:
        ideas = [
            DiscoveryIdea.from_dict(row)
            for row in _read_jsonl(Path(config.ideas_path))
        ][:config.max_ideas]
    elif config.idea_source == "pantheon":
        from .pantheon import generate_pantheon_ideas

        ideas = []
        seen_idea_ids: set[str] = set()
        accepted_target = int(config.accepted_idea_target or 0)
        max_attempts = max(1, int(config.max_generation_attempts))
        for attempt in range(max_attempts):
            accepted_preview = [
                idea for idea in ideas
                if review_idea_against_schema(
                    idea, schema, max_complexity=config.max_complexity
                ).accepted
            ]
            if accepted_target and len(accepted_preview) >= accepted_target:
                break
            if not accepted_target and ideas:
                break
            remaining = max(1, accepted_target - len(accepted_preview)) if accepted_target else config.max_ideas
            batch_size = max(config.idea_agent_count, config.max_ideas if attempt == 0 else remaining * 2)
            generated, records = _run_async(generate_pantheon_ideas(
                schema,
                output_dir=output_dir,
                max_ideas=batch_size,
                model=config.model,
                timeout=config.llm_timeout,
                idea_agent_count=config.idea_agent_count,
                prior_graph_path=config.prior_graph_path,
                direction_context_path=(
                    config.direction_context_path or config.frontier_context_path
                ),
            ))
            agent_records.extend(_agent_record_rows(records))
            before = len(ideas)
            for idea in generated:
                if idea.idea_id in seen_idea_ids:
                    continue
                seen_idea_ids.add(idea.idea_id)
                ideas.append(idea)
            if len(ideas) == before:
                break
    elif config.idea_source == "openai":
        from .llm import generate_openai_ideas

        ideas = generate_openai_ideas(
            schema,
            max_ideas=config.max_ideas,
            model=config.model,
            reasoning_effort=config.reasoning_effort,
            timeout=config.llm_timeout,
        )
    else:
        raise ValueError("idea_source must be 'pantheon' or 'openai'")
    ideas_path = output_dir / "ideas.jsonl"
    reviews_path = output_dir / "reviews.jsonl"
    results_path = output_dir / "results.jsonl"
    report_path = output_dir / "report.md"

    reviews = []
    results = []
    notebooks = []
    accepted: list[DiscoveryIdea] = []
    accepted_target = int(config.accepted_idea_target or 0)
    for idea in ideas:
        review = review_idea_against_schema(idea, schema, max_complexity=config.max_complexity)
        reviews.append({"idea_id": idea.idea_id, **review.to_dict()})
        if review.accepted and (not accepted_target or len(accepted) < accepted_target):
            accepted.append(idea)

    # Persist generation/review outputs before notebook agents run. Long
    # notebook batches may hit transient provider errors, and these files make
    # the generated idea set auditable even if exploration is interrupted.
    _write_jsonl(ideas_path, [idea.to_dict() for idea in ideas])
    _write_jsonl(reviews_path, reviews)

    if config.code_source == "pantheon":
        for idea in accepted:
            notebook_path = notebooks_dir / f"{idea.idea_id}.ipynb"
            verification_code = _verification_code_for_idea(idea, output_dir)
            create_exploration_notebook(
                idea,
                notebook_path,
                h5cd_path=h5cd_path,
                run_output_dir=output_dir,
                analysis_code=_pantheon_analysis_placeholder(),
                verification_code=verification_code,
            )
            notebooks.append(str(notebook_path))

        if accepted:
            from .pantheon import run_pantheon_notebook_agents

            records = _run_async(run_pantheon_notebook_agents(
                accepted,
                schema=schema,
                h5cd_path=h5cd_path,
                output_dir=output_dir,
                notebooks_dir=notebooks_dir,
                model=config.model,
                timeout=config.llm_timeout,
                concurrency=config.notebook_agent_concurrency,
                generate_schematic_image=config.generate_schematic_image,
                schematic_image_model=config.schematic_image_model,
                schematic_image_model_args=config.schematic_image_model_args,
            ))
            agent_records.extend(_agent_record_rows(records))
    elif config.code_source != "openai":
        raise ValueError("code_source must be 'pantheon' or 'openai'")

    for idea in accepted:
        notebook_path = notebooks_dir / f"{idea.idea_id}.ipynb"
        if config.code_source == "openai":
            from .llm import generate_openai_analysis_code

            analysis_code = generate_openai_analysis_code(
                idea,
                schema,
                model=config.model,
                reasoning_effort=config.reasoning_effort,
                timeout=config.llm_timeout,
            )
            verification_code = _verification_code_for_idea(idea, output_dir)
            create_exploration_notebook(
                idea,
                notebook_path,
                h5cd_path=h5cd_path,
                run_output_dir=output_dir,
                analysis_code=analysis_code,
                verification_code=verification_code,
            )
            notebooks.append(str(notebook_path))
        if config.execute:
            started = time.time()
            execution = execute_notebook_python(notebook_path, stop_on_error=config.stop_on_error)
            elapsed = time.time() - started
            verification = execution.get("verification") or {}
            _complete_runner_verification(
                notebook_path,
                verification,
                elapsed_sec=elapsed,
                stop_on_error=config.stop_on_error,
            )
            upsert_structured_conclusion(notebook_path, idea, verification)
            result = {
                "idea_id": idea.idea_id,
                "notebook": str(notebook_path),
                "execution_ok": bool(execution.get("ok")),
                "elapsed_sec": round(elapsed, 3),
                "verification": verification,
                "errors": execution.get("errors", []),
            }
        else:
            result = {
                "idea_id": idea.idea_id,
                "notebook": str(notebook_path),
                "execution_ok": None,
                "elapsed_sec": None,
                "verification": {"status": "not_executed"},
                "errors": [],
            }
        results.append(result)

    _write_jsonl(ideas_path, [idea.to_dict() for idea in ideas])
    _write_jsonl(reviews_path, reviews)
    _write_jsonl(results_path, results)
    _write_jsonl(agent_records_path, agent_records)
    _write_report(report_path, config, schema, ideas, reviews, results)

    from .direction import plan_discovery_directions, write_direction_artifacts
    from .graph import build_idea_graph_from_run, write_idea_graph_artifacts
    from .visualization import write_idea_graph_html

    graph = build_idea_graph_from_run(output_dir, claims_paths=config.claims_paths)
    graph_artifacts = write_idea_graph_artifacts(graph, output_dir)
    graph_html_path = write_idea_graph_html(
        graph,
        output_dir / "graph" / "idea_graph.html",
        notebook_base_url="../../_auto_discovery_notebooks",
    )
    directions = plan_discovery_directions(graph, schema)
    direction_artifacts = write_direction_artifacts(directions, output_dir)

    verified = [
        r for r in results
        if (r.get("verification") or {}).get("status") == "pass"
    ]
    if config.store_schema:
        graph_summary = graph.summary()
        cdata.uns["auto_discovery_graph"] = {
            "schema_hash": schema.get("schema_hash"),
            "latest_graph_path": graph_artifacts["graph_json"],
            "graph_summary_path": graph_artifacts["graph_summary"],
            "graph_html_path": str(graph_html_path),
            "directions_path": direction_artifacts["directions_json"],
            "direction_summary_path": direction_artifacts["directions_markdown"],
            "n_directions": len(directions),
            "n_ideas": len(ideas),
            "n_accepted": len(accepted),
            "n_executed": len(results) if config.execute else 0,
            "n_verified": len(verified),
            "coverage_summary": graph_summary.get("coverage", {}),
            "hypothesis_status": graph_summary.get("hypothesis_status", {}),
        }
        runs = cdata.uns.get("auto_discovery_runs")
        if not isinstance(runs, list):
            runs = []
        runs.append({
            "output_dir": str(output_dir),
            "schema_hash": schema.get("schema_hash"),
            "ideas_path": str(ideas_path),
            "reviews_path": str(reviews_path),
            "results_path": str(results_path),
            "report_path": str(report_path),
            "graph_path": graph_artifacts["graph_json"],
            "graph_summary_path": graph_artifacts["graph_summary"],
            "graph_html_path": str(graph_html_path),
            "directions_path": direction_artifacts["directions_json"],
            "direction_summary_path": direction_artifacts["directions_markdown"],
            "n_generated": len(ideas),
            "n_accepted": len(accepted),
            "n_executed": len(results) if config.execute else 0,
            "n_verified": len(verified),
        })
        cdata.uns["auto_discovery_runs"] = runs
        cdata.write(input_h5cd_path)
        if enriched_h5cd_path is not None:
            cdata.write(enriched_h5cd_path)
    return DiscoveryRunResult(
        output_dir=str(output_dir),
        n_generated=len(ideas),
        n_accepted=len(accepted),
        n_executed=len(results) if config.execute else 0,
        n_verified=len(verified),
        report_path=str(report_path),
        ideas_path=str(ideas_path),
        reviews_path=str(reviews_path),
        results_path=str(results_path),
        notebooks=notebooks,
        agent_records_path=str(agent_records_path),
        graph_path=graph_artifacts["graph_json"],
        graph_summary_path=graph_artifacts["graph_summary"],
        graph_html_path=str(graph_html_path),
        directions_path=direction_artifacts["directions_json"],
        direction_summary_path=direction_artifacts["directions_markdown"],
        enriched_h5cd_path=str(enriched_h5cd_path) if enriched_h5cd_path is not None else None,
        enrichment_summary_path=str(enrichment_summary_path) if enrichment_summary_path is not None else None,
    )


def _run_async(coro: Awaitable[Any]) -> Any:
    """Run an async backend call from scripts or active notebook loops."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(_await_with_cleanup(coro))

    result: dict[str, Any] = {}

    def _target() -> None:
        try:
            result["value"] = asyncio.run(_await_with_cleanup(coro))
        except BaseException as exc:  # pragma: no cover - active loop fallback
            result["error"] = exc

    thread = threading.Thread(target=_target, daemon=True)
    thread.start()
    thread.join()
    if "error" in result:
        raise result["error"]
    return result.get("value")


async def _await_with_cleanup(coro: Awaitable[Any]) -> Any:
    loop = asyncio.get_running_loop()
    previous_handler = loop.get_exception_handler()

    def _ignore_async_client_close(loop: asyncio.AbstractEventLoop, context: dict[str, Any]) -> None:
        exc = context.get("exception")
        future = context.get("future")
        future_name = ""
        if future is not None and hasattr(future, "get_coro"):
            future_name = getattr(future.get_coro(), "__qualname__", "")
        is_httpx_close = "AsyncClient.aclose" in future_name
        is_closed_loop = isinstance(exc, RuntimeError) and str(exc) == "Event loop is closed"
        if is_httpx_close and is_closed_loop:
            return
        if previous_handler is not None:
            previous_handler(loop, context)
        else:
            loop.default_exception_handler(context)

    loop.set_exception_handler(_ignore_async_client_close)
    try:
        return await coro
    finally:
        # Pantheon/OpenAI clients may schedule async close tasks just after the
        # final response. Let them drain before asyncio.run closes the loop.
        await asyncio.sleep(0.5)
        loop.set_exception_handler(previous_handler)


def _agent_record_rows(records: list[Any]) -> list[dict[str, Any]]:
    return [
        {
            "agent_name": record.agent_name,
            "role": record.role,
            "prompt_path": record.prompt_path,
            "content": record.content,
        }
        for record in records
    ]


def _pantheon_analysis_placeholder() -> str:
    return (
        "# PantheonOS notebook agent must edit this cell with executable analysis.\n"
        "# It may also insert Markdown and additional code cells around it.\n"
        "raise RuntimeError('PantheonOS notebook agent did not replace the exploration placeholder')\n"
    )

def _verification_code_for_idea(idea: DiscoveryIdea, output_dir: Path) -> str:
    return """
checks = {check: 'not_run' for check in IDEA.validation_checks}
notes = []
checks.setdefault('statistical_hypothesis_test', 'not_run')

def _check_keys(prefix):
    return [key for key in checks if key == prefix or key.startswith(prefix + ':')]

def _set_check(prefix, value):
    keys = _check_keys(prefix)
    if not keys:
        checks[prefix] = value
        return
    for key in keys:
        checks[key] = value

def _check_status(prefix):
    values = [checks[key] for key in _check_keys(prefix)]
    if not values:
        return None
    if 'fail' in values:
        return 'fail'
    if all(value == 'pass' for value in values):
        return 'pass'
    return values[0]

_set_check('required_fields_exist', 'pass' if review is not None and review.accepted else 'fail')
if _check_keys('cell_id_alignment'):
    aligned = True
    if cdata is not None and adata is not None and len(cdata.cells) == len(adata.obs_names):
        aligned = list(map(str, cdata.cells.index)) == list(map(str, adata.obs_names))
    _set_check('cell_id_alignment', 'pass' if aligned else 'fail')
if _check_keys('minimum_cell_count'):
    n_cells = analysis_summary.get('n_selected_cells')
    if n_cells is None and 'cell_type' in getattr(result_table, 'columns', []):
        n_cells = len(result_table)
    if n_cells is None:
        n_cells = len(cdata.cells) if cdata is not None and getattr(cdata, 'n_cells', 0) else 0
    _set_check('minimum_cell_count', 'pass' if n_cells >= 1 else 'fail')
if _check_keys('minimum_spot_or_trace_count'):
    n_rows = analysis_summary.get('n_rows')
    if n_rows is None:
        n_rows = len(result_table) if result_table is not None else 0
    _set_check('minimum_spot_or_trace_count', 'pass' if n_rows >= 1 else 'fail')
if _check_keys('finite_numeric_output'):
    value = analysis_summary.get('parameter_value')
    _set_check('finite_numeric_output', 'pass' if value is not None and np.isfinite(value) else 'fail')
if _check_keys('statistical_hypothesis_test'):
    p_value = analysis_summary.get('p_value')
    test_method = analysis_summary.get('test_method')
    null_hypothesis = analysis_summary.get('null_hypothesis')
    alternative_hypothesis = analysis_summary.get('alternative_hypothesis')
    observed_statistic = analysis_summary.get('observed_statistic')
    effect_size = analysis_summary.get('effect_size')
    hypothesis_test_status = analysis_summary.get('hypothesis_test_status', 'pass')
    try:
        p_float = float(p_value)
    except Exception:
        p_float = np.nan
    try:
        stat_float = float(observed_statistic)
    except Exception:
        stat_float = np.nan
    try:
        effect_float = float(effect_size)
    except Exception:
        effect_float = np.nan
    has_required_test = (
        test_method is not None
        and str(test_method).strip() != ''
        and null_hypothesis is not None
        and str(null_hypothesis).strip() != ''
        and alternative_hypothesis is not None
        and str(alternative_hypothesis).strip() != ''
        and np.isfinite(p_float)
        and 0.0 <= p_float <= 1.0
        and np.isfinite(stat_float)
        and np.isfinite(effect_float)
        and hypothesis_test_status != 'insufficient_data'
    )
    if result_table is not None and hasattr(result_table, 'columns'):
        has_required_test = has_required_test and 'p_value' in result_table.columns and 'test_method' in result_table.columns
    else:
        has_required_test = False
    _set_check('statistical_hypothesis_test', 'pass' if has_required_test else 'fail')
    if not has_required_test:
        notes.append('statistical_hypothesis_test failed: analysis_summary must include null_hypothesis, alternative_hypothesis, test_method, observed_statistic, effect_size, finite p_value in [0,1], and result_table columns p_value/test_method')
if _check_keys('negative_control_or_permutation'):
    test_method_text = str(analysis_summary.get('test_method', '')).lower()
    summary_keys_text = ' '.join(str(key).lower() for key in analysis_summary.keys())
    result_columns_text = ''
    if result_table is not None and hasattr(result_table, 'columns'):
        result_columns_text = ' '.join(str(col).lower() for col in result_table.columns)
    control_text = ' '.join([test_method_text, summary_keys_text, result_columns_text])
    has_control_or_permutation = any(
        token in control_text
        for token in ['permutation', 'randomization', 'shuffle', 'negative_control', 'null_distribution', 'control']
    )
    _set_check(
        'negative_control_or_permutation',
        'pass' if has_control_or_permutation else 'not_implemented',
    )
for check in list(checks):
    if checks[check] == 'not_run' and ('negative_control' in check or check.endswith('_control')):
        checks[check] = 'not_implemented'

required_for_pass = ['required_fields_exist', 'minimum_cell_count', 'finite_numeric_output', 'statistical_hypothesis_test']
status = 'pass'
for check in required_for_pass:
    if _check_status(check) == 'fail':
        status = 'fail'
        notes.append(f'{check} failed')
n_rows_for_status = analysis_summary.get('n_rows')
if n_rows_for_status is None:
    n_rows_for_status = len(result_table) if result_table is not None else 0
if n_rows_for_status == 0:
    status = 'fail'
    notes.append('analysis produced no result rows')

verification = {
    'idea_id': IDEA.idea_id,
    'status': status,
    'checks': checks,
    'parameter_value': analysis_summary.get('parameter_value'),
    'p_value': analysis_summary.get('p_value'),
    'test_method': analysis_summary.get('test_method'),
    'effect_size': analysis_summary.get('effect_size'),
    'observed_statistic': analysis_summary.get('observed_statistic'),
    'null_hypothesis': analysis_summary.get('null_hypothesis'),
    'alternative_hypothesis': analysis_summary.get('alternative_hypothesis'),
    'hypothesis_test_status': analysis_summary.get('hypothesis_test_status'),
    'n_selected_cells': analysis_summary.get('n_selected_cells'),
    'n_rows': analysis_summary.get('n_rows'),
    'result_path': analysis_summary.get('result_path'),
    'notes': notes + analysis_summary.get('notes', []),
}
print(json.dumps(verification, indent=2))
"""


def _complete_runner_verification(
    notebook_path: Path,
    verification: dict[str, Any],
    *,
    elapsed_sec: float,
    stop_on_error: bool,
) -> None:
    checks = verification.setdefault("checks", {})
    def _check_keys(prefix: str) -> list[str]:
        return [key for key in checks if key == prefix or key.startswith(prefix + ":")]

    def _set_check(prefix: str, value: str) -> None:
        keys = _check_keys(prefix)
        if not keys:
            return
        for key in keys:
            checks[key] = value

    runtime_keys = _check_keys("runtime_under_budget")
    if runtime_keys and any(checks.get(key) == "not_run" for key in runtime_keys):
        _set_check("runtime_under_budget", "pass" if elapsed_sec <= 60 else "fail")
    rerun_keys = _check_keys("deterministic_rerun")
    if rerun_keys and any(checks.get(key) == "not_run" for key in rerun_keys):
        first_value = verification.get("parameter_value")
        rerun = execute_notebook_python(notebook_path, stop_on_error=stop_on_error)
        second = rerun.get("verification") or {}
        second_value = second.get("parameter_value")
        same = _same_numeric(first_value, second_value)
        _set_check("deterministic_rerun", "pass" if rerun.get("ok") and same else "fail")
        verification.setdefault("notes", []).append(
            f"deterministic_rerun parameter_value={second_value!r}"
        )
    if any(v == "fail" for v in checks.values()):
        verification["status"] = "fail"


def _same_numeric(a: Any, b: Any, *, tol: float = 1e-9) -> bool:
    try:
        af = float(a)
        bf = float(b)
    except Exception:
        return a == b
    if math.isnan(af) and math.isnan(bf):
        return True
    return abs(af - bf) <= tol


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w") as fh:
        for row in rows:
            fh.write(json.dumps(row, default=_json_default, sort_keys=True) + "\n")


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open() as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def _write_report(
    path: Path,
    config: DiscoveryRunConfig,
    schema: dict[str, Any],
    ideas: list[DiscoveryIdea],
    reviews: list[dict[str, Any]],
    results: list[dict[str, Any]],
) -> None:
    verified = [
        r for r in results
        if (r.get("verification") or {}).get("status") == "pass"
    ]
    lines = [
        "# U-Chrom Auto-Discovery Run",
        "",
        f"h5cd: `{config.h5cd_path}`",
        f"schema_hash: `{schema.get('schema_hash')}`",
        f"generated ideas: {len(ideas)}",
        f"accepted ideas: {sum(1 for r in reviews if r.get('accepted'))}",
        f"executed notebooks: {len(results) if config.execute else 0}",
        f"verified ideas: {len(verified)}",
        "",
        "## Verified Ideas",
    ]
    if not verified:
        lines.append("")
        lines.append("None.")
    for result in verified:
        verification = result.get("verification") or {}
        idea = next((i for i in ideas if i.idea_id == result["idea_id"]), None)
        lines.extend([
            "",
            f"### {idea.idea_title if idea else result['idea_id']}",
            f"- idea_id: `{result['idea_id']}`",
            f"- parameter_value: `{verification.get('parameter_value')}`",
            f"- test_method: `{verification.get('test_method')}`",
            f"- p_value: `{verification.get('p_value')}`",
            f"- effect_size: `{verification.get('effect_size')}`",
            f"- notebook: `{result.get('notebook')}`",
            f"- result_path: `{verification.get('result_path')}`",
        ])
    rejected = [r for r in reviews if not r.get("accepted")]
    if rejected:
        lines.extend(["", "## Rejected Ideas"])
        for review in rejected:
            lines.append(f"- `{review['idea_id']}`: {'; '.join(review.get('errors', []))}")
    path.write_text("\n".join(lines) + "\n")


def _json_default(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    return str(value)
