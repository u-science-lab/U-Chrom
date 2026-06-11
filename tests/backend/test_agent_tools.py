"""Tests for agent_tools definitions."""
from webapp.backend.agent_tools import TOOLS, SYSTEM_PROMPT


def test_all_tools_defined():
    """All planned tools should be defined (plus later additions)."""
    names = {t["name"] for t in TOOLS}
    expected = {
        "render_gosling", "patch_gosling", "color_embedding",
        "select_cells", "show_structure", "color_structure",
        "add_notebook_cell", "run_analysis",
    }
    # The 8 planned tools must all exist; newer tools (export_view,
    # write_analysis_function, ...) may extend the set.
    assert expected <= names, f"missing planned tools: {expected - names}"


def test_each_tool_has_schema():
    """Each tool must have name, description, input_schema."""
    for t in TOOLS:
        assert "name" in t
        assert "description" in t
        assert "input_schema" in t
        assert t["input_schema"]["type"] == "object"


def test_system_prompt_mentions_gosling():
    assert "Gosling" in SYSTEM_PROMPT
