"""Backend adapters for U-Chrom auto-discovery.

Backends may use CLI agents and scratch files internally, but the runner owns
the final notebook lifecycle.  Adapter outputs are normalized into structured
Python objects that the runner can audit, write, execute, and verify.
"""

from __future__ import annotations

import json
import math
import os
import re
import shutil
import subprocess
import tempfile
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator, Mapping, Protocol

try:
    import tomllib
except ImportError:  # Python < 3.11
    import tomli as tomllib

from .ideas import DiscoveryIdea
from .llm import (
    STRUCTURED_JSON_BEGIN,
    STRUCTURED_JSON_END,
    analysis_output_schema,
    build_analysis_prompt,
    build_idea_prompt,
    idea_output_schema,
)
from .schema import schema_to_agent_context


class BackendError(RuntimeError):
    """A classified backend failure.

    ``category`` is one of ``backend_unavailable`` (missing/exited binary or an
    auth failure that a retry will not fix), ``failed`` (ran but exited
    non-zero for another reason), ``bad_output`` (ran but produced output that
    could not be parsed), or ``timeout``.  ``retryable`` tells the run loop
    whether a transient retry is worthwhile.
    """

    def __init__(self, message: str, *, category: str, retryable: bool) -> None:
        super().__init__(message)
        self.category = category
        self.retryable = retryable


@dataclass(frozen=True)
class BackendCapabilities:
    """Capabilities reported by an auto-discovery backend."""

    structured_output: bool
    file_workspace: bool
    prompt_via_stdin: bool
    streaming: bool
    native_skill_loading: bool = False
    resume: bool = False
    # When True the backend owns the notebook lifecycle end to end (it edits
    # the notebook itself via an agentic loop); the runner must not generate
    # an analysis cell for it.  When False the backend only returns an
    # ``analysis_code`` string and the runner owns the notebook.  The runner
    # dispatches on this capability instead of branching on backend id, so a
    # new notebook-owning backend works without touching the runner.
    owns_notebook_lifecycle: bool = False


@dataclass(frozen=True)
class BackendDetection:
    """Best-effort local CLI detection result."""

    backend_id: str
    executable_path: str | None
    version: str | None = None
    available: bool = False
    auth_state: str = "unknown"
    error: str | None = None
    # CLI feature flags discovered by probing ``--help`` (flag substring ->
    # present?).  Empty when the help text could not be read; ``build_command``
    # treats "unknown" as "assume present" to preserve legacy behavior.
    cli_flags: Mapping[str, bool] = field(default_factory=dict)


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
            owns_notebook_lifecycle=True,
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


def _flag_present(cli_flags: Mapping[str, bool] | None, key: str) -> bool:
    """Return whether a probed CLI flag is available.

    ``cli_flags`` maps a capability key to whether the corresponding flag was
    found in the CLI ``--help`` output.  An unknown key (help not probed, or
    probe failed) is treated as present so behavior matches the pre-probe
    default and a probe failure never silently strips a required flag.
    """
    if cli_flags is None:
        return True
    return cli_flags.get(key, True)


def _build_claude_command(
    *,
    workdir: Path,
    model: str | None,
    reasoning_effort: str | None,
    output_schema_path: Path,
    codex_config_path: Path | None = None,
    cli_flags: Mapping[str, bool] | None = None,
) -> list[str]:
    cmd = [
        "claude",
        "--bare",
        "-p",
        "--output-format",
        "json",
        "--input-format",
        "text",
    ]
    if _flag_present(cli_flags, "json_schema"):
        cmd.extend(["--json-schema", output_schema_path.read_text()])
    cmd.extend(["--permission-mode", "default"])
    cmd.extend(["--disallowedTools", "Write,Edit,Bash,NotebookEdit,NotebookRead"])
    if model:
        cmd.extend(["--model", model])
    if reasoning_effort and _flag_present(cli_flags, "effort"):
        cmd.extend(["--effort", _claude_effort(reasoning_effort)])
    return cmd


def _build_codex_command(
    *,
    workdir: Path,
    model: str | None,
    reasoning_effort: str | None,
    output_schema_path: Path,
    codex_config_path: Path | None = None,
    cli_flags: Mapping[str, bool] | None = None,
) -> list[str]:
    cmd = ["codex", "exec", "--json"]
    if _flag_present(cli_flags, "ignore_user_config"):
        cmd.append("--ignore-user-config")
    if _flag_present(cli_flags, "ignore_rules"):
        cmd.append("--ignore-rules")
    if _flag_present(cli_flags, "ephemeral"):
        cmd.append("--ephemeral")
    cmd.extend([
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
    ])
    if codex_config_path is not None:
        cmd.extend(_codex_config_args(codex_config_path))
    if model:
        cmd.extend(["--model", model])
    if reasoning_effort:
        cmd.extend(["-c", f"model_reasoning_effort={json.dumps(reasoning_effort)}"])
    cmd.append("-")
    return cmd


def _parse_claude_stream(stdout: str) -> str:
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


def _parse_codex_events(stdout: str) -> str:
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


_STREAM_PARSERS: dict[str, Any] = {
    "claude-stream-json": _parse_claude_stream,
    "codex-json-event": _parse_codex_events,
}


@contextmanager
def _default_run_environment(workdir: Path) -> Iterator[dict[str, str]]:
    yield dict(os.environ)


@contextmanager
def _codex_run_environment(workdir: Path) -> Iterator[dict[str, str]]:
    with tempfile.TemporaryDirectory(prefix="uchrom-codex-home-", dir=workdir) as codex_home:
        codex_home_path = Path(codex_home)
        _write_minimal_codex_config(codex_home_path)
        env = dict(os.environ)
        env["CODEX_HOME"] = str(codex_home_path)
        env["UCHROM_CODEX_CONFIG_PATH"] = str(codex_home_path / "config.toml")
        yield env


@dataclass(frozen=True)
class CLISpec:
    """Data describing one stdin-driven coding-agent CLI backend.

    Per-CLI differences are expressed as data here rather than as subclass
    overrides, mirroring open-design's data-driven adapter model: the generic
    ``CLIBackend`` consumes a spec and the core never branches on backend id.
    """

    backend_id: str
    display_name: str
    executable: str
    build_command: Any  # callable(**kwargs) -> list[str]
    stream_format: str
    run_environment: Any = _default_run_environment  # callable(Path) -> ctx mgr
    fallback_bins: tuple[str, ...] = ()
    # capability key -> ``--help`` substring whose presence enables the flag.
    capability_probe: Mapping[str, str] = field(default_factory=dict)


class CLIBackend:
    """Generic adapter for stdin-driven coding-agent CLIs, driven by a spec."""

    def __init__(self, spec: CLISpec) -> None:
        self.spec = spec
        self.backend_id = spec.backend_id
        self.display_name = spec.display_name
        self.executable = spec.executable

    def _resolve_executable(self) -> str | None:
        for candidate in (self.executable, *self.spec.fallback_bins):
            path = shutil.which(candidate)
            if path:
                return path
        return None

    def detect(self) -> BackendDetection:
        path = self._resolve_executable()

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
            cli_flags=self._probe_cli_flags(path),
        )

    def _probe_cli_flags(self, path: str) -> dict[str, bool]:
        """Probe ``--help`` and report which capability flags are supported.

        Returns an empty dict when ``capability_probe`` is empty or the help
        text cannot be read, so ``build_command`` falls back to assuming every
        flag is present (legacy behavior).
        """
        if not self.spec.capability_probe:
            return {}
        try:
            completed = subprocess.run(
                [path, "--help"],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=5,
                check=False,
            )
        except Exception:
            return {}
        help_text = (completed.stdout or "") + (completed.stderr or "")
        if not help_text.strip():
            return {}
        return {
            key: substring in help_text
            for key, substring in self.spec.capability_probe.items()
        }

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
        _write_backend_context(
            schema,
            workdir,
            prior_graph_path=prior_graph_path,
            direction_context_path=direction_context_path,
        )
        # Fan out across ``idea_agent_count`` independent agents and dedup by
        # idea_id, matching the Pantheon backend.  Previously the CLI backends
        # accepted ``idea_agent_count`` but ran a single agent, so the same
        # config value silently meant different things per backend.
        agent_count = max(1, int(idea_agent_count))
        ideas_per_agent = max(1, math.ceil(max_ideas / agent_count))
        prompt = build_idea_prompt(
            schema,
            max_ideas=ideas_per_agent,
            prior_graph_path=prior_graph_path,
            direction_context_path=direction_context_path,
        )
        cli_flags = self._detect_cli_flags()
        ideas: list[DiscoveryIdea] = []
        records: list[BackendAgentRecord] = []
        seen: set[str] = set()
        for idx in range(agent_count):
            agent_workdir = workdir if agent_count == 1 else workdir / f"agent_{idx}"
            agent_workdir.mkdir(parents=True, exist_ok=True)
            record = self._run_structured(
                role="idea",
                prompt=prompt,
                workdir=agent_workdir,
                model=model,
                reasoning_effort=reasoning_effort,
                timeout=timeout,
                cli_flags=cli_flags,
            )
            records.append(record)
            payload = extract_structured_json(str(record.content.get("output", "")))
            raw_ideas = payload.get("ideas", [])
            if not isinstance(raw_ideas, list):
                raise ValueError(f"{self.backend_id} idea output must contain an ideas list")
            for item in raw_ideas:
                idea = DiscoveryIdea.from_dict(item)
                if idea.idea_id in seen:
                    continue
                seen.add(idea.idea_id)
                ideas.append(idea)
                if len(ideas) >= max_ideas:
                    return ideas, records
        return ideas, records

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
        prompt = build_analysis_prompt(
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
            cli_flags=self._detect_cli_flags(),
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
        cli_flags: Mapping[str, bool] | None = None,
        max_attempts: int = 2,
    ) -> BackendAgentRecord:
        """Run one structured backend invocation, retrying transient failures.

        Failures are classified so callers and audit logs can tell apart a
        missing/exited binary, a run that produced unparseable output, and a
        timeout.  Transient failures (timeout, non-zero exit that is not an
        auth error) are retried once; auth and bad-output failures are not.
        """
        last_exc: BackendError | None = None
        for attempt in range(1, max(1, int(max_attempts)) + 1):
            try:
                return self._run_structured_once(
                    role=role,
                    prompt=prompt,
                    workdir=workdir,
                    model=model,
                    reasoning_effort=reasoning_effort,
                    timeout=timeout,
                    cli_flags=cli_flags,
                    attempt=attempt,
                )
            except BackendError as exc:
                last_exc = exc
                if not exc.retryable or attempt >= max(1, int(max_attempts)):
                    raise
        assert last_exc is not None  # loop always sets it before raising
        raise last_exc

    def _run_structured_once(
        self,
        *,
        role: str,
        prompt: str,
        workdir: Path,
        model: str | None,
        reasoning_effort: str | None,
        timeout: int,
        cli_flags: Mapping[str, bool] | None,
        attempt: int,
    ) -> BackendAgentRecord:
        suffix = "" if attempt == 1 else f"_attempt{attempt}"
        prompt_path = workdir / f"{role}_prompt.md"
        output_schema_path = workdir / f"{role}_schema.json"
        stdout_path = workdir / f"{role}{suffix}_stdout.jsonl"
        stderr_path = workdir / f"{role}{suffix}_stderr.log"
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
                        cli_flags=cli_flags,
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
            "attempt": attempt,
            "output_schema_path": str(output_schema_path),
            "stdout_path": str(stdout_path),
            "stderr_path": str(stderr_path),
            "output": output,
        }
        if structured_output_path.exists():
            content["structured_output_path"] = str(structured_output_path)
        if returncode != 0:
            tail = stderr[-4000:] or stdout[-4000:]
            if returncode == -1:
                raise BackendError(
                    f"{self.backend_id} {role} backend timed out: {tail}",
                    category="timeout",
                    retryable=True,
                )
            auth = _looks_like_auth_failure(stderr or stdout)
            raise BackendError(
                f"{self.backend_id} {role} backend "
                f"{'failed (auth)' if auth else f'failed with exit {returncode}'}: {tail}",
                category="backend_unavailable" if auth else "failed",
                retryable=not auth,
            )
        return BackendAgentRecord(
            agent_name=f"{self.backend_id}_{role}_agent",
            role=role,
            prompt_path=str(prompt_path),
            content=content,
        )

    def _detect_cli_flags(self) -> Mapping[str, bool]:
        if not self.spec.capability_probe:
            return {}
        path = self._resolve_executable()
        if not path:
            return {}
        return self._probe_cli_flags(path)

    def _command(
        self,
        *,
        workdir: Path,
        model: str | None,
        reasoning_effort: str | None,
        output_schema_path: Path,
        codex_config_path: Path | None = None,
        cli_flags: Mapping[str, bool] | None = None,
    ) -> list[str]:
        return self.spec.build_command(
            workdir=workdir,
            model=model,
            reasoning_effort=reasoning_effort,
            output_schema_path=output_schema_path,
            codex_config_path=codex_config_path,
            cli_flags=cli_flags,
        )

    def _extract_final_text(self, stdout: str) -> str:
        parser = _STREAM_PARSERS.get(self.spec.stream_format)
        if parser is None:
            return stdout
        return parser(stdout)

    @contextmanager
    def _run_environment(self, workdir: Path) -> Iterator[dict[str, str]]:
        with self.spec.run_environment(workdir) as env:
            yield env


CLAUDE_SPEC = CLISpec(
    backend_id="claude",
    display_name="Claude Code",
    executable="claude",
    build_command=_build_claude_command,
    stream_format="claude-stream-json",
    capability_probe={"json_schema": "--json-schema", "effort": "--effort"},
)

CODEX_SPEC = CLISpec(
    backend_id="codex",
    display_name="Codex",
    executable="codex",
    build_command=_build_codex_command,
    stream_format="codex-json-event",
    run_environment=_codex_run_environment,
    capability_probe={
        "ignore_user_config": "--ignore-user-config",
        "ignore_rules": "--ignore-rules",
        "ephemeral": "--ephemeral",
    },
)


class ClaudeBackend(CLIBackend):
    """Claude Code CLI adapter (thin spec-backed wrapper)."""

    def __init__(self) -> None:
        super().__init__(CLAUDE_SPEC)


class CodexBackend(CLIBackend):
    """Codex CLI adapter (thin spec-backed wrapper)."""

    def __init__(self) -> None:
        super().__init__(CODEX_SPEC)


def _output_schema_for_role(role: str) -> dict[str, Any]:
    if role == "idea":
        return idea_output_schema()
    if role == "analysis":
        return analysis_output_schema()
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


_AUTH_FAILURE_MARKERS = (
    "not logged in",
    "please log in",
    "please login",
    "run `claude login`",
    "run `codex login`",
    "authentication required",
    "unauthorized",
    "invalid api key",
    "missing api key",
    "no api key",
    "credentials",
)


def _looks_like_auth_failure(text: str) -> bool:
    """Heuristically detect an auth failure from CLI stderr/stdout.

    Auth failures will not be fixed by retrying, so they are reported as
    ``backend_unavailable`` and not retried.  Kept deliberately conservative:
    a bare HTTP status is too noisy, so only explicit auth phrasing counts.
    """
    lowered = text.lower()
    return any(marker in lowered for marker in _AUTH_FAILURE_MARKERS)


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
