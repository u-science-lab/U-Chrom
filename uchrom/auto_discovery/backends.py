"""Backend adapters for U-Chrom auto-discovery.

Backends may use CLI agents and scratch files internally, but the runner owns
the final notebook lifecycle.  Adapter outputs are normalized into structured
Python objects that the runner can audit, write, execute, and verify.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
import time
import tomllib
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator, Mapping, Protocol, Sequence

from .ideas import DiscoveryIdea
from .schema import schema_to_agent_context


STRUCTURED_JSON_BEGIN = "BEGIN_UCHROM_JSON"
STRUCTURED_JSON_END = "END_UCHROM_JSON"


@dataclass(frozen=True)
class BackendCapabilities:
    """Capabilities reported by an auto-discovery backend."""

    structured_output: bool
    file_workspace: bool
    prompt_via_stdin: bool
    streaming: bool
    native_skill_loading: bool = False
    resume: bool = False


@dataclass(frozen=True)
class BackendDetection:
    """Best-effort local CLI detection result."""

    backend_id: str
    executable_path: str | None
    version: str | None = None
    available: bool = False
    auth_state: str = "unknown"
    error: str | None = None


@dataclass(frozen=True)
class BackendAgentRecord:
    """Audit record for one backend invocation."""

    agent_name: str
    role: str
    prompt_path: str
    content: Any


@dataclass(frozen=True)
class AnalysisCodeResult:
    """Structured analysis code returned by a backend."""

    analysis_code: str
    agent_records: list[BackendAgentRecord] = field(default_factory=list)
    extra_cells: list[dict[str, Any]] = field(default_factory=list)
    artifact_manifest: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


class DiscoveryBackend(Protocol):
    """Protocol implemented by all auto-discovery backends."""

    backend_id: str
    display_name: str

    def detect(self) -> BackendDetection:
        ...

    def capabilities(self) -> BackendCapabilities:
        ...

    def generate_ideas(
        self,
        schema: Mapping[str, Any],
        *,
        output_dir: str | Path,
        max_ideas: int,
        model: str | None = None,
        reasoning_effort: str | None = None,
        timeout: int = 420,
        idea_agent_count: int = 1,
        prior_graph_path: str | Path | None = None,
        direction_context_path: str | Path | None = None,
    ) -> tuple[list[DiscoveryIdea], list[BackendAgentRecord]]:
        ...

    def generate_analysis_code(
        self,
        idea: DiscoveryIdea,
        schema: Mapping[str, Any],
        *,
        output_dir: str | Path,
        h5cd_path: str | Path,
        model: str | None = None,
        reasoning_effort: str | None = None,
        timeout: int = 420,
    ) -> AnalysisCodeResult:
        ...


_BACKENDS: dict[str, DiscoveryBackend] = {}


def register_backend(backend: DiscoveryBackend) -> None:
    """Register or replace one backend adapter."""
    _BACKENDS[backend.backend_id] = backend


def unregister_backend(backend_id: str) -> None:
    """Remove a backend adapter if it is registered."""
    _BACKENDS.pop(backend_id, None)


def get_backend(backend_id: str) -> DiscoveryBackend:
    """Return a registered backend or raise a user-facing error."""
    try:
        return _BACKENDS[backend_id]
    except KeyError as exc:
        available = ", ".join(sorted(_BACKENDS))
        raise ValueError(f"unknown auto-discovery backend {backend_id!r}; available: {available}") from exc


def list_backends() -> list[str]:
    """Return registered backend ids."""
    return sorted(_BACKENDS)


def extract_structured_json(text: str) -> dict[str, Any]:
    """Extract the first structured JSON object from backend text."""
    marked = re.search(
        rf"{STRUCTURED_JSON_BEGIN}\s*(.*?)\s*{STRUCTURED_JSON_END}",
        text,
        flags=re.DOTALL,
    )
    if marked:
        return _json_object_from_text(marked.group(1))
    return _json_object_from_text(text)


def _json_object_from_text(text: str) -> dict[str, Any]:
    stripped = text.strip()
    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError:
        start = stripped.find("{")
        end = stripped.rfind("}")
        if start < 0 or end <= start:
            raise ValueError("backend output did not contain a JSON object")
        parsed = json.loads(stripped[start : end + 1])
    if not isinstance(parsed, dict):
        raise ValueError("backend output JSON must be an object")
    return dict(parsed)


class PantheonBackend:
    """Adapter around the existing Pantheon implementation."""

    backend_id = "pantheon"
    display_name = "PantheonOS"

    def detect(self) -> BackendDetection:
        try:
            import pantheon  # noqa: F401
        except Exception as exc:
            return BackendDetection(
                backend_id=self.backend_id,
                executable_path=None,
                available=False,
                auth_state="missing",
                error=f"{type(exc).__name__}: {exc}",
            )
        return BackendDetection(
            backend_id=self.backend_id,
            executable_path=None,
            available=True,
            auth_state="unknown",
        )

    def capabilities(self) -> BackendCapabilities:
        return BackendCapabilities(
            structured_output=True,
            file_workspace=True,
            prompt_via_stdin=False,
            streaming=True,
            native_skill_loading=False,
            resume=False,
        )

    def generate_ideas(self, schema: Mapping[str, Any], **kwargs: Any) -> tuple[list[DiscoveryIdea], list[BackendAgentRecord]]:
        from .pantheon import generate_pantheon_ideas
        from .runner import _run_async

        ideas, records = _run_async(generate_pantheon_ideas(
            schema,
            output_dir=kwargs["output_dir"],
            max_ideas=kwargs["max_ideas"],
            model=kwargs.get("model"),
            timeout=kwargs.get("timeout", 420),
            idea_agent_count=kwargs.get("idea_agent_count", 1),
            prior_graph_path=kwargs.get("prior_graph_path"),
            direction_context_path=kwargs.get("direction_context_path"),
        ))
        return ideas, [_coerce_record(record) for record in records]

    def generate_analysis_code(self, idea: DiscoveryIdea, schema: Mapping[str, Any], **kwargs: Any) -> AnalysisCodeResult:
        raise NotImplementedError("Pantheon analysis is notebook-agent based and is handled by runner.")


class CLIBackend:
    """Base adapter for stdin-driven coding-agent CLIs."""

    backend_id = ""
    display_name = ""
    executable = ""

    def detect(self) -> BackendDetection:
        path = shutil.which(self.executable)
        if not path:
            return BackendDetection(
                backend_id=self.backend_id,
                executable_path=None,
                available=False,
                auth_state="missing",
                error=f"{self.executable!r} was not found on PATH",
            )
        version = None
        try:
            completed = subprocess.run(
                [path, "--version"],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=5,
                check=False,
            )
            version = (completed.stdout or completed.stderr).strip() or None
        except Exception as exc:
            return BackendDetection(
                backend_id=self.backend_id,
                executable_path=path,
                available=True,
                version=None,
                auth_state="unknown",
                error=f"{type(exc).__name__}: {exc}",
            )
        return BackendDetection(
            backend_id=self.backend_id,
            executable_path=path,
            version=version,
            available=True,
            auth_state="unknown",
        )

    def capabilities(self) -> BackendCapabilities:
        return BackendCapabilities(
            structured_output=True,
            file_workspace=True,
            prompt_via_stdin=True,
            streaming=True,
            native_skill_loading=False,
            resume=False,
        )

    def generate_ideas(
        self,
        schema: Mapping[str, Any],
        *,
        output_dir: str | Path,
        max_ideas: int,
        model: str | None = None,
        reasoning_effort: str | None = None,
        timeout: int = 420,
        idea_agent_count: int = 1,
        prior_graph_path: str | Path | None = None,
        direction_context_path: str | Path | None = None,
    ) -> tuple[list[DiscoveryIdea], list[BackendAgentRecord]]:
        workdir = Path(output_dir) / self.backend_id / "idea_agents"
        workdir.mkdir(parents=True, exist_ok=True)
        context = _write_backend_context(
            schema,
            workdir,
            prior_graph_path=prior_graph_path,
            direction_context_path=direction_context_path,
        )
        prompt = _idea_prompt(
            max_ideas=max_ideas,
            schema_path=context["schema_path"],
            context_path=context["context_path"],
            prior_graph_path=prior_graph_path,
            direction_context_path=direction_context_path,
        )
        record = self._run_structured(
            role="idea",
            prompt=prompt,
            workdir=workdir,
            model=model,
            reasoning_effort=reasoning_effort,
            timeout=timeout,
        )
        payload = extract_structured_json(str(record.content.get("output", "")))
        raw_ideas = payload.get("ideas", [])
        if not isinstance(raw_ideas, list):
            raise ValueError(f"{self.backend_id} idea output must contain an ideas list")
        return [DiscoveryIdea.from_dict(item) for item in raw_ideas[:max_ideas]], [record]

    def generate_analysis_code(
        self,
        idea: DiscoveryIdea,
        schema: Mapping[str, Any],
        *,
        output_dir: str | Path,
        h5cd_path: str | Path,
        model: str | None = None,
        reasoning_effort: str | None = None,
        timeout: int = 420,
    ) -> AnalysisCodeResult:
        workdir = Path(output_dir) / self.backend_id / "analysis_agents" / idea.idea_id
        workdir.mkdir(parents=True, exist_ok=True)
        context = _write_backend_context(schema, workdir)
        idea_path = workdir / "idea.json"
        idea_path.write_text(json.dumps(idea.to_dict(), indent=2, default=str) + "\n")
        prompt = _analysis_prompt(
            idea_path=idea_path,
            schema_path=context["schema_path"],
            context_path=context["context_path"],
            h5cd_path=Path(h5cd_path),
            output_dir=Path(output_dir),
        )
        record = self._run_structured(
            role="analysis",
            prompt=prompt,
            workdir=workdir,
            model=model,
            reasoning_effort=reasoning_effort,
            timeout=timeout,
        )
        payload = extract_structured_json(str(record.content.get("output", "")))
        code = payload.get("analysis_code")
        if not isinstance(code, str) or not code.strip():
            raise ValueError(f"{self.backend_id} analysis output must contain non-empty analysis_code")
        return AnalysisCodeResult(
            analysis_code=code,
            agent_records=[record],
            extra_cells=_list_of_dicts(payload.get("extra_cells", [])),
            artifact_manifest=_list_of_dicts(payload.get("artifact_manifest", [])),
            warnings=_list_of_strings(payload.get("warnings", [])),
            notes=_list_of_strings(payload.get("notes", [])),
        )

    def _run_structured(
        self,
        *,
        role: str,
        prompt: str,
        workdir: Path,
        model: str | None,
        reasoning_effort: str | None,
        timeout: int,
    ) -> BackendAgentRecord:
        prompt_path = workdir / f"{role}_prompt.md"
        output_schema_path = workdir / f"{role}_schema.json"
        stdout_path = workdir / f"{role}_stdout.jsonl"
        stderr_path = workdir / f"{role}_stderr.log"
        prompt_path.write_text(prompt)
        output_schema_path.write_text(json.dumps(_output_schema_for_role(role), indent=2) + "\n")
        started = time.time()
        try:
            with self._run_environment(workdir) as env:
                codex_config_path = env.get("UCHROM_CODEX_CONFIG_PATH")
                completed = subprocess.run(
                    self._command(
                        workdir=workdir,
                        model=model,
                        reasoning_effort=reasoning_effort,
                        output_schema_path=output_schema_path,
                        codex_config_path=Path(codex_config_path) if codex_config_path else None,
                    ),
                    input=prompt,
                    text=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    cwd=workdir,
                    env=env,
                    timeout=max(1, int(timeout)),
                    check=False,
                )
            returncode = completed.returncode
            stdout = completed.stdout
            stderr = completed.stderr
        except subprocess.TimeoutExpired as exc:
            returncode = -1
            stdout = _decode_timeout_stream(exc.stdout)
            stderr = _decode_timeout_stream(exc.stderr)
        elapsed = time.time() - started
        stdout_path.write_text(stdout)
        stderr_path.write_text(stderr)
        output = self._extract_final_text(stdout)
        structured_output_path = workdir / f"{role}_output.json"
        if not _text_has_structured_json(output) and structured_output_path.exists():
            output = structured_output_path.read_text()
        content = {
            "status": "completed" if returncode == 0 else "failed",
            "returncode": returncode,
            "elapsed_sec": round(elapsed, 3),
            "output_schema_path": str(output_schema_path),
            "stdout_path": str(stdout_path),
            "stderr_path": str(stderr_path),
            "output": output,
        }
        if structured_output_path.exists():
            content["structured_output_path"] = str(structured_output_path)
        if returncode != 0:
            tail = stderr[-4000:] or stdout[-4000:]
            status = "timed out" if returncode == -1 else f"failed with exit {returncode}"
            raise RuntimeError(f"{self.backend_id} {role} backend {status}: {tail}")
        return BackendAgentRecord(
            agent_name=f"{self.backend_id}_{role}_agent",
            role=role,
            prompt_path=str(prompt_path),
            content=content,
        )

    def _command(
        self,
        *,
        workdir: Path,
        model: str | None,
        reasoning_effort: str | None,
        output_schema_path: Path,
        codex_config_path: Path | None = None,
    ) -> list[str]:
        raise NotImplementedError

    def _extract_final_text(self, stdout: str) -> str:
        return stdout

    @contextmanager
    def _run_environment(self, workdir: Path) -> Iterator[dict[str, str]]:
        yield dict(os.environ)


class ClaudeBackend(CLIBackend):
    """Claude Code CLI adapter."""

    backend_id = "claude"
    display_name = "Claude Code"
    executable = "claude"

    def _command(
        self,
        *,
        workdir: Path,
        model: str | None,
        reasoning_effort: str | None,
        output_schema_path: Path,
        codex_config_path: Path | None = None,
    ) -> list[str]:
        cmd = [
            self.executable,
            "--bare",
            "-p",
            "--output-format",
            "json",
            "--input-format",
            "text",
            "--json-schema",
            output_schema_path.read_text(),
            "--permission-mode",
            "default",
            "--disallowedTools",
            "Write,Edit,Bash,NotebookEdit,NotebookRead",
        ]
        if model:
            cmd.extend(["--model", model])
        if reasoning_effort:
            cmd.extend(["--effort", _claude_effort(reasoning_effort)])
        return cmd

    def _extract_final_text(self, stdout: str) -> str:
        last_result = ""
        chunks: list[str] = []
        for event in _iter_json_events(stdout):
            structured_output = _structured_output_from_event(event)
            if structured_output is not None:
                return json.dumps(structured_output)
            if event.get("type") == "result" and event.get("result"):
                last_result = str(event["result"])
            if event.get("type") == "assistant":
                for content in event.get("message", {}).get("content", []) or []:
                    if isinstance(content, Mapping) and content.get("type") == "text":
                        chunks.append(str(content.get("text", "")))
        return last_result or "".join(chunks) or stdout


class CodexBackend(CLIBackend):
    """Codex CLI adapter."""

    backend_id = "codex"
    display_name = "Codex"
    executable = "codex"

    def _command(
        self,
        *,
        workdir: Path,
        model: str | None,
        reasoning_effort: str | None,
        output_schema_path: Path,
        codex_config_path: Path | None = None,
    ) -> list[str]:
        cmd = [
            self.executable,
            "exec",
            "--json",
            "--ignore-user-config",
            "--ignore-rules",
            "--ephemeral",
            "--skip-git-repo-check",
            "--output-schema",
            str(output_schema_path),
            "--sandbox",
            "workspace-write",
            "-C",
            str(workdir),
            "-c",
            "sandbox_workspace_write.network_access=true",
            "-c",
            'web_search="disabled"',
        ]
        if codex_config_path is not None:
            cmd.extend(_codex_config_args(codex_config_path))
        if model:
            cmd.extend(["--model", model])
        if reasoning_effort:
            cmd.extend(["-c", f"model_reasoning_effort={json.dumps(reasoning_effort)}"])
        cmd.append("-")
        return cmd

    @contextmanager
    def _run_environment(self, workdir: Path) -> Iterator[dict[str, str]]:
        with tempfile.TemporaryDirectory(prefix="uchrom-codex-home-", dir=workdir) as codex_home:
            codex_home_path = Path(codex_home)
            _write_minimal_codex_config(codex_home_path)
            env = dict(os.environ)
            env["CODEX_HOME"] = str(codex_home_path)
            env["UCHROM_CODEX_CONFIG_PATH"] = str(codex_home_path / "config.toml")
            yield env

    def _extract_final_text(self, stdout: str) -> str:
        last_message = ""
        chunks: list[str] = []
        for event in _iter_json_events(stdout):
            msg = event.get("msg") if isinstance(event.get("msg"), Mapping) else event
            if not isinstance(msg, Mapping):
                continue
            message = msg.get("message")
            if isinstance(message, str):
                chunks.append(message)
                last_message = message
            item = msg.get("item")
            if isinstance(item, Mapping):
                text = item.get("text") or item.get("content")
                if isinstance(text, str):
                    chunks.append(text)
                    last_message = text
        return last_message or "\n".join(chunks) or stdout


def _output_schema_for_role(role: str) -> dict[str, Any]:
    if role == "idea":
        return {
            "type": "object",
            "properties": {
                "ideas": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "idea_title": {"type": "string"},
                            "biological_hypothesis": {"type": "string"},
                            "computable_parameter": {"type": "string"},
                            "analysis_plan": {"type": "string"},
                            "modalities": {"type": "array", "items": {"type": "string"}},
                            "idea_markdown": {"type": "string"},
                            "cell_types": {"type": "array", "items": {"type": "string"}},
                            "required_fields": {"type": "array", "items": {"type": "string"}},
                            "validation_checks": {"type": "array", "items": {"type": "string"}},
                            "expected_direction": {"type": "string"},
                            "complexity": {"type": "integer", "minimum": 1, "maximum": 5},
                            "metadata": {"type": "object", "additionalProperties": True},
                        },
                        "required": [
                            "idea_title",
                            "biological_hypothesis",
                            "computable_parameter",
                            "analysis_plan",
                            "modalities",
                            "cell_types",
                            "required_fields",
                            "validation_checks",
                            "expected_direction",
                            "complexity",
                        ],
                        "additionalProperties": False,
                    },
                },
            },
            "required": ["ideas"],
            "additionalProperties": False,
        }
    if role == "analysis":
        return {
            "type": "object",
            "properties": {
                "analysis_code": {"type": "string"},
                "extra_cells": {
                    "type": "array",
                    "items": {"type": "object", "additionalProperties": True},
                },
                "artifact_manifest": {
                    "type": "array",
                    "items": {"type": "object", "additionalProperties": True},
                },
                "warnings": {"type": "array", "items": {"type": "string"}},
                "notes": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["analysis_code", "extra_cells", "artifact_manifest", "warnings", "notes"],
            "additionalProperties": False,
        }
    raise ValueError(f"unknown backend role {role!r}")


def _iter_json_events(stdout: str) -> list[dict[str, Any]]:
    try:
        parsed = json.loads(stdout)
    except json.JSONDecodeError:
        parsed = None
    if isinstance(parsed, Mapping):
        return [dict(parsed)]
    if isinstance(parsed, list):
        return [dict(item) for item in parsed if isinstance(item, Mapping)]

    events: list[dict[str, Any]] = []
    for line in stdout.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(event, Mapping):
            events.append(dict(event))
    return events


def _structured_output_from_event(event: Mapping[str, Any]) -> Any:
    structured = event.get("structured_output")
    if structured is not None:
        return structured
    msg = event.get("msg")
    if isinstance(msg, Mapping) and msg.get("structured_output") is not None:
        return msg["structured_output"]
    return None


def _write_minimal_codex_config(codex_home: Path) -> None:
    source_home = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex"))
    source_config = source_home / "config.toml"
    target_config = codex_home / "config.toml"
    if source_config.exists():
        target_config.write_text(_minimal_codex_config_text(source_config.read_text()))
    else:
        target_config.write_text("")
    for filename in ("auth.json", "auth.toml"):
        source = source_home / filename
        if source.exists():
            shutil.copy2(source, codex_home / filename)


def _minimal_codex_config_text(text: str) -> str:
    keep_top_level = {
        "model_provider",
        "model",
        "disable_response_storage",
        "preferred_auth_method",
    }
    lines: list[str] = []
    section: str | None = None
    keep_section = False
    section_lines: list[str] = []

    def flush_section() -> None:
        if keep_section and section_lines:
            if lines and lines[-1] != "":
                lines.append("")
            lines.extend(section_lines)

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if line.startswith("[") and line.endswith("]"):
            flush_section()
            section = line.strip("[]")
            keep_section = section == "model_providers" or section.startswith("model_providers.")
            section_lines = [raw_line] if keep_section else []
            continue
        if section is not None:
            if keep_section:
                section_lines.append(raw_line)
            continue
        if not line or line.startswith("#"):
            continue
        key = line.split("=", 1)[0].strip()
        if key in keep_top_level:
            lines.append(raw_line)
    flush_section()
    return "\n".join(lines).rstrip() + "\n"


def _codex_config_args(config_path: Path) -> list[str]:
    config = tomllib.loads(config_path.read_text()) if config_path.exists() else {}
    args: list[str] = []
    for key in ("model_provider", "model", "disable_response_storage", "preferred_auth_method"):
        if key in config:
            args.extend(["-c", f"{key}={json.dumps(config[key])}"])
    providers = config.get("model_providers")
    if isinstance(providers, Mapping):
        for provider_id, provider_config in providers.items():
            if not isinstance(provider_config, Mapping):
                continue
            for key, value in provider_config.items():
                args.extend(["-c", f"model_providers.{provider_id}.{key}={json.dumps(value)}"])
    return args


def _write_backend_context(
    schema: Mapping[str, Any],
    workdir: Path,
    *,
    prior_graph_path: str | Path | None = None,
    direction_context_path: str | Path | None = None,
) -> dict[str, Path]:
    schema_path = workdir / "schema.json"
    context_path = workdir / "schema_context.md"
    schema_path.write_text(json.dumps(schema, indent=2, default=str) + "\n")
    context_path.write_text(schema_to_agent_context(schema, max_items=80) + "\n")
    manifest = {
        "schema_path": str(schema_path),
        "context_path": str(context_path),
        "prior_graph_path": None if prior_graph_path is None else str(prior_graph_path),
        "direction_context_path": None if direction_context_path is None else str(direction_context_path),
    }
    (workdir / "context_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return {"schema_path": schema_path, "context_path": context_path}


def _idea_prompt(
    *,
    max_ideas: int,
    schema_path: Path,
    context_path: Path,
    prior_graph_path: str | Path | None,
    direction_context_path: str | Path | None,
) -> str:
    extra = []
    if prior_graph_path is not None:
        extra.append(f"- Prior graph JSON: {prior_graph_path}")
    if direction_context_path is not None:
        extra.append(f"- Direction context markdown: {direction_context_path}")
    extra_text = "\n".join(extra) if extra else "- No prior graph or direction context."
    return f"""
You are generating U-Chrom auto-discovery ideas. Return only structured JSON
between {STRUCTURED_JSON_BEGIN} and {STRUCTURED_JSON_END}. Do not write files.

Files:
- Schema JSON: {schema_path}
- Schema context: {context_path}
{extra_text}

Rules:
- Generate at most {max_ideas} diverse, computable ideas.
- Use only fields present in the schema.
- Each idea must be compatible with DiscoveryIdea.from_dict.
- Required fields must be exact schema field paths.
- Include statistical_hypothesis_test in validation_checks unless impossible.

Return this shape exactly:
{{
  "ideas": [
    {{
      "idea_title": "...",
      "biological_hypothesis": "...",
      "computable_parameter": "...",
      "analysis_plan": "...",
      "modalities": ["chromatin_tracing"],
      "cell_types": ["..."],
      "required_fields": ["coords"],
      "validation_checks": ["required_fields_exist", "statistical_hypothesis_test"],
      "expected_direction": "...",
      "complexity": 3
    }}
  ]
}}
""".strip()


def _analysis_prompt(
    *,
    idea_path: Path,
    schema_path: Path,
    context_path: Path,
    h5cd_path: Path,
    output_dir: Path,
) -> str:
    return f"""
You are writing one executable Python notebook analysis cell for U-Chrom
auto-discovery. Read these files:
- Idea JSON: {idea_path}
- Schema JSON: {schema_path}
- Schema context: {context_path}

The final notebook is owned by the U-Chrom runner. Do not edit files or
notebooks. Return the structured JSON in your final message only.

Execution environment:
- H5CD_PATH will be {h5cd_path}
- RUN_OUTPUT_DIR will be {output_dir}
- Variables already defined by the notebook: cdata, adata, IDEA, schema, review,
  RUN_OUTPUT_DIR, np, pd, plt, ChromData.
- IDEA is a DiscoveryIdea object. Prefer attribute access such as IDEA.idea_id
  and IDEA.idea_title over dict-style access.

Return only structured JSON between {STRUCTURED_JSON_BEGIN} and
{STRUCTURED_JSON_END} with this shape:
{{
  "analysis_code": "Python code string",
  "extra_cells": [],
  "artifact_manifest": [],
  "warnings": [],
  "notes": []
}}

analysis_code requirements:
- Define result_table as a pandas DataFrame.
- Define analysis_summary as a JSON-serializable dict.
- Write result_table to RUN_OUTPUT_DIR / f"{{IDEA.idea_id}}_result.csv".
- result_table must include `p_value` and `test_method` columns on every row.
- Include result_path, parameter_value, observed_statistic, effect_size, p_value,
  test_method, null_hypothesis, alternative_hypothesis, hypothesis_test_status,
  n_selected_cells, and n_rows in analysis_summary.
- parameter_value must be a finite numeric scalar that directly summarizes the
  computable parameter, not the parameter name or any other string.
- observed_statistic, effect_size, and p_value must also be finite numeric
  scalars; convert numpy scalar types with float(...) or int(...).
- Perform an explicit statistical hypothesis test or bounded permutation /
  randomization test. Do not set hypothesis_test_status to `insufficient_data`
  when a finite fallback statistic can be computed; use `pass_with_fallback`,
  set p_value to 1.0, and add a note instead.
- If using pd.qcut or pd.cut and you need `.cat`, wrap the input in
  pd.Series(...) first; qcut/cut on numpy arrays returns a Categorical without
  the Series `.cat` accessor.
- Keep runtime small and deterministic.
- Do not modify package source files or notebooks.
""".strip()


def _coerce_record(record: Any) -> BackendAgentRecord:
    return BackendAgentRecord(
        agent_name=str(record.agent_name),
        role=str(record.role),
        prompt_path=str(record.prompt_path),
        content=record.content,
    )


def _list_of_dicts(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [dict(item) for item in value if isinstance(item, Mapping)]


def _list_of_strings(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value]


def _decode_timeout_stream(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def _text_has_structured_json(text: str) -> bool:
    if STRUCTURED_JSON_BEGIN in text and STRUCTURED_JSON_END in text:
        return True
    stripped = text.strip()
    return stripped.startswith("{") and stripped.endswith("}")


def _claude_effort(reasoning_effort: str) -> str:
    if reasoning_effort == "minimal":
        return "low"
    if reasoning_effort == "none":
        return "low"
    return reasoning_effort


register_backend(PantheonBackend())
register_backend(ClaudeBackend())
register_backend(CodexBackend())
