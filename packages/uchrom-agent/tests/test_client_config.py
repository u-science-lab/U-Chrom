import json
from pathlib import Path

import pytest

from uchrom_agent.client_config import configure_client


def test_claude_preview_does_not_write_and_shows_json_diff(tmp_path):
    config = tmp_path / "claude.json"
    original = '{\n  "theme": "dark"\n}\n'
    config.write_text(original)

    diff = configure_client("claude", config, command="/venv/bin/uchrom-agent")

    assert config.read_text() == original
    assert '"mcpServers"' in diff
    assert '"uchrom"' in diff
    assert not list(tmp_path.glob("*.bak-*"))


def test_claude_write_makes_backup_merges_entry_and_reads_back_json(tmp_path):
    config = tmp_path / "claude.json"
    original = {"theme": "dark", "mcpServers": {"other": {"command": "other"}}}
    config.write_text(json.dumps(original, indent=2) + "\n")

    diff = configure_client("claude", config, command="/venv/bin/uchrom-agent", write=True)

    saved = json.loads(config.read_text())
    assert saved["theme"] == "dark"
    assert saved["mcpServers"]["other"] == {"command": "other"}
    assert saved["mcpServers"]["uchrom"] == {
        "command": "/venv/bin/uchrom-agent", "args": ["mcp"]}
    backups = list(tmp_path.glob("claude.json.bak-*"))
    assert len(backups) == 1
    assert backups[0].read_text() == json.dumps(original, indent=2) + "\n"
    assert '"uchrom"' in diff


def test_claude_write_replaces_only_uchrom_entry_and_is_idempotent(tmp_path):
    config = tmp_path / "claude.json"
    config.write_text(json.dumps({"mcpServers": {
        "other": {"command": "other"}, "uchrom": {"command": "old"}}}))

    configure_client("claude", config, command="uchrom-agent", write=True)
    first = json.loads(config.read_text())
    configure_client("claude", config, command="uchrom-agent", write=True)
    second = json.loads(config.read_text())

    assert second == first
    assert second["mcpServers"]["other"] == {"command": "other"}


def test_codex_preview_and_write_merge_toml_config(tmp_path):
    config = tmp_path / "config.toml"
    original = '[model]\nmodel = "gpt-6"\n'
    config.write_text(original)

    diff = configure_client("codex", config, command="/venv/bin/uchrom-agent")
    assert config.read_text() == original
    assert "[mcp_servers.uchrom]" in diff

    configure_client("codex", config, command="/venv/bin/uchrom-agent", write=True)
    saved = config.read_text()
    assert 'model = "gpt-6"' in saved
    assert 'command = "/venv/bin/uchrom-agent"' in saved
    assert 'args = ["mcp"]' in saved
    assert len(list(tmp_path.glob("config.toml.bak-*"))) == 1


def test_config_path_is_required_and_invalid_json_is_preserved(tmp_path):
    with pytest.raises(ValueError, match="config path"):
        configure_client("claude", None)

    config = tmp_path / "invalid.json"
    config.write_text("not json")
    with pytest.raises(ValueError, match="valid JSON"):
        configure_client("claude", config, write=True)
    assert config.read_text() == "not json"
