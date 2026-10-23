"""Dependency-free checks for Atlas's client-side Continue locally flow."""

import ast
from pathlib import Path


REPO = Path(__file__).resolve().parents[3]
ATLAS = REPO / "apps" / "atlas"


def test_site_build_has_no_agent_handoff_endpoint_or_cli_option():
    source = (ATLAS / "build.py").read_text()
    tree = ast.parse(source)
    build_site = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "build_site")
    parameters = {arg.arg for arg in (*build_site.args.posonlyargs, *build_site.args.args, *build_site.args.kwonlyargs)}

    assert "agent_handoff" not in parameters
    assert "--agent-handoff" not in source
    assert "agentHandoff" not in source


def test_continue_locally_uses_catalog_url_and_prepares_local_mcp_prompt():
    app = (ATLAS / "site" / "app.js").read_text()
    html = (ATLAS / "site" / "index.html").read_text()

    assert "python -m uchrom_browser " in app
    assert "urlOf(d)" in app
    assert "U-Chrom MCP" in app
    assert "fetch(HANDOFF)" not in app
    assert "api/agent/handoffs" not in app
    assert "token" not in app.lower()
    assert "not on PyPI" in html
    assert "packages/chromdata" in html and "packages/uchrom-browser" in html
    assert "handoff-copy-command" in html and "handoff-copy-instruction" in html
    assert "localhost" in html


def test_atlas_publish_docs_do_not_require_a_handoff_endpoint():
    publish = (ATLAS / "PUBLISH.md").read_text()
    apps_readme = (ATLAS.parent / "README.md").read_text()

    assert "--agent-handoff" not in publish
    assert "--agent-handoff" not in apps_readme
