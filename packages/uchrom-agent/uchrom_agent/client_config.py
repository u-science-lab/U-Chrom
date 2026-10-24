"""Preview and explicitly write the Claude Code and Codex stdio MCP entries."""

from __future__ import annotations

import difflib
import json
import os
import re
import tempfile
import tomllib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _toml_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=True)


def _codex_entry(command: str, args: list[str]) -> str:
    return ("[mcp_servers.uchrom]\n"
            f"command = {_toml_string(command)}\n"
            f"args = [{', '.join(_toml_string(arg) for arg in args)}]\n")


def _replace_codex_entry(original: str, command: str, args: list[str]) -> str:
    try:
        parsed = tomllib.loads(original)
    except tomllib.TOMLDecodeError as exc:
        raise ValueError(f"Codex config must be valid TOML: {exc}") from None
    servers = parsed.get("mcp_servers", {})
    if not isinstance(servers, dict):
        raise ValueError("Codex config mcp_servers value must be a table")
    start_pattern = re.compile(r"^\s*\[mcp_servers\.(?:uchrom|\"uchrom\")\]\s*(?:#.*)?$")
    header_pattern = re.compile(r"^\s*\[\[?.+\]\]?\s*(?:#.*)?$")
    lines = original.splitlines(keepends=True)
    starts = [i for i, line in enumerate(lines) if start_pattern.match(line.rstrip("\r\n"))]
    if len(starts) > 1:
        raise ValueError("Codex config has duplicate mcp_servers.uchrom tables")
    entry = _codex_entry(command, args)
    if starts:
        start = starts[0]
        end = next((i for i in range(start + 1, len(lines))
                    if header_pattern.match(lines[i].rstrip("\r\n"))), len(lines))
        replacement = entry + ("\n" if end < len(lines) else "")
        lines[start:end] = [replacement]
        result = "".join(lines)
    else:
        if re.search(r"^\s*mcp_servers\s*=", original, flags=re.MULTILINE):
            raise ValueError("Codex config defines mcp_servers as an inline value; refusing to rewrite it")
        result = original
        if result and not result.endswith("\n"):
            result += "\n"
        if result and not result.endswith("\n\n"):
            result += "\n"
        result += entry
    try:
        readback = tomllib.loads(result)
    except tomllib.TOMLDecodeError as exc:
        raise ValueError(f"generated Codex config is invalid TOML: {exc}") from None
    expected = {"command": command, "args": args}
    if readback.get("mcp_servers", {}).get("uchrom") != expected:
        raise ValueError("Codex config readback did not match the U-Chrom MCP entry")
    return result


def _updated_content(client: str, original: str, command: str, args: list[str]) -> str:
    if client == "claude":
        try:
            config = json.loads(original or "{}")
        except json.JSONDecodeError as exc:
            raise ValueError(f"Claude Code config must be valid JSON: {exc}") from None
        if not isinstance(config, dict):
            raise ValueError("Claude Code config must contain a JSON object")
        servers = config.setdefault("mcpServers", {})
        if not isinstance(servers, dict):
            raise ValueError("Claude Code mcpServers value must be an object")
        servers["uchrom"] = {"command": command, "args": args}
        return json.dumps(config, indent=2, ensure_ascii=True) + "\n"
    if client == "codex":
        return _replace_codex_entry(original, command, args)
    raise ValueError("client must be 'claude' or 'codex'")


def _atomic_write(path: Path, content: str) -> None:
    mode = path.stat().st_mode & 0o777 if path.exists() else 0o600
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as output:
            output.write(content)
            output.flush()
            os.fsync(output.fileno())
        os.chmod(temp_name, mode)
        os.replace(temp_name, path)
    except Exception:
        Path(temp_name).unlink(missing_ok=True)
        raise


def _backup(path: Path) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    backup = path.with_name(f"{path.name}.bak-{stamp}")
    backup.write_bytes(path.read_bytes())
    return backup


def configure_client(client: str, config_path: str | Path | None, *, command: str | None = None,
                     args: list[str] | None = None, write: bool = False) -> str:
    """Return a unified diff; write only when requested, then verify exact readback."""
    if config_path is None:
        raise ValueError("a config path is required; pass --config PATH")
    path = Path(config_path).expanduser().resolve()
    executable = command or os.sys.executable
    server_args = args if args is not None else ["mcp"]
    original = path.read_text(encoding="utf-8") if path.exists() else ""
    updated = _updated_content(client, original, executable, server_args)
    diff = "".join(difflib.unified_diff(original.splitlines(keepends=True), updated.splitlines(keepends=True),
                                        fromfile=str(path), tofile=f"{path} (U-Chrom MCP)"))
    if not write:
        return diff or "Already configured; no changes needed.\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        _backup(path)
    _atomic_write(path, updated)
    written = path.read_text(encoding="utf-8")
    if written != updated or _updated_content(client, written, executable, server_args) != updated:
        raise OSError("configuration readback did not match the requested U-Chrom entry")
    return diff or "Already configured; no changes needed.\n"
