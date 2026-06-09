import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest


def _make_cd():
    from uchrom import ChromData

    coords = np.arange(18, dtype=float).reshape(6, 3)
    spots = pd.DataFrame({
        "chrom": ["chr1", "chr1", "chr1", "chr2", "chr2", "chr2"],
        "start": [0, 25_000, 50_000, 0, 25_000, 50_000],
        "end": [25_000, 50_000, 75_000, 25_000, 50_000, 75_000],
        "trace_id": ["c1_chr1", "c1_chr1", "c2_chr1", "c1_chr2", "c2_chr2", "c2_chr2"],
        "cell_id": ["c1", "c1", "c2", "c1", "c2", "c2"],
    })
    cells = pd.DataFrame({
        "cell_type": ["Granule", "Bergmann"],
        "batch": [1, 1],
    }, index=pd.Index(["c1", "c2"], name="cell_id"))
    tracks = pd.DataFrame({
        "H3K27me3": np.linspace(0, 1, 6),
        "LaminB1": np.linspace(1, 0, 6),
    })
    cellm = {"umap": np.array([[0.0, 1.0], [2.0, 3.0]])}
    return ChromData(
        coords,
        spots,
        cells=cells,
        tracks=tracks,
        cellm=cellm,
        uns={"genome_assembly": "mm10", "xyz_unit": "um", "source": "unit-test"},
    )


def test_discovery_schema_roundtrips_inside_h5cd(tmp_path):
    from uchrom import ChromData
    from uchrom.auto_discovery.schema import DISCOVERY_SCHEMA_KEY

    cdata = _make_cd()
    schema = cdata.build_discovery_schema(store=True)

    assert DISCOVERY_SCHEMA_KEY in cdata.uns
    assert schema["modalities"]["chromatin_tracing"]["present"]
    assert schema["modalities"]["if_tracks"]["present"]
    assert schema["catalogs"]["tracks"]["values"] == ["H3K27me3", "LaminB1"]
    assert "statistical_hypothesis_test" in schema["recommended_verification"]
    assert cdata.validate_discovery_schema() == []

    path = tmp_path / "schema.h5cd"
    cdata.write(path)
    out = ChromData.read(path)

    assert DISCOVERY_SCHEMA_KEY in out.uns
    assert out.discovery_schema["schema_hash"] == schema["schema_hash"]
    assert out.discovery_schema["catalogs"]["cell_types"]["counts"]["Granule"] == 1
    assert "H3K27me3" in out.describe_for_agent(max_items=10)


def test_discovery_schema_includes_linked_anndata():
    ad = pytest.importorskip("anndata")

    cdata = _make_cd()
    adata = ad.AnnData(
        X=np.array([[1.0, 0.0], [0.0, 2.0]]),
        obs=pd.DataFrame(index=pd.Index(["c1", "c2"], name="cell_id")),
        var=pd.DataFrame(index=pd.Index(["Aldoc", "Pcp2"], name="gene")),
    )
    cdata.linked_adata = adata

    schema = cdata.build_discovery_schema(store=True)

    assert schema["modalities"]["rna_expression"]["present"]
    assert schema["linked_adata"]["shape"] == [2, 2]
    assert schema["catalogs"]["genes"]["values"] == ["Aldoc", "Pcp2"]
    assert "linked_adata" in cdata.describe_for_agent()


def test_review_idea_against_schema_accepts_and_rejects_fields():
    from uchrom.auto_discovery import DiscoveryIdea, review_idea_against_schema

    cdata = _make_cd()
    schema = cdata.build_discovery_schema(store=False)
    idea = DiscoveryIdea(
        idea_title="Granule H3K27me3 compaction",
        biological_hypothesis="H3K27me3-high bins are compacted in Granule cells.",
        computable_parameter="Median high-marker pairwise distance.",
        analysis_plan="Subset Granule cells and compare distances by marker rank.",
        modalities=["chromatin_tracing", "if_tracks", "cell_metadata"],
        cell_types=["Granule"],
        required_fields=["coords", "spots.cell_id", "tracks.H3K27me3", "cells.cell_type"],
        validation_checks=["required_fields_exist", "cell_id_alignment"],
    )

    review = review_idea_against_schema(idea, schema)

    assert review.accepted
    assert review.errors == []

    bad = idea.to_dict()
    bad["required_fields"] = ["tracks.DOES_NOT_EXIST"]
    review = review_idea_against_schema(bad, schema)

    assert not review.accepted
    assert review.missing_fields == ["tracks.DOES_NOT_EXIST"]


def _make_idea(*, title: str = "Granule H3K27me3 compaction", cell_type: str = "Granule"):
    from uchrom.auto_discovery import DiscoveryIdea

    return DiscoveryIdea(
        idea_title=title,
        biological_hypothesis=f"H3K27me3-high bins are compacted in {cell_type} cells.",
        computable_parameter="Median high-marker pairwise distance.",
        analysis_plan=f"Subset {cell_type} cells and compare distances by marker rank.",
        modalities=["chromatin_tracing", "if_tracks", "cell_metadata"],
        cell_types=[cell_type],
        required_fields=["coords", "spots.cell_id", "tracks.H3K27me3", "cells.cell_type"],
        validation_checks=[
            "required_fields_exist",
            "cell_id_alignment",
            "minimum_cell_count",
            "minimum_spot_or_trace_count",
            "finite_numeric_output",
            "statistical_hypothesis_test",
            "runtime_under_budget",
            "deterministic_rerun",
        ],
    )


def test_notebook_scaffold(tmp_path):
    from uchrom.auto_discovery import create_exploration_notebook

    idea = _make_idea()
    idea.idea_markdown = (
        "## Readable hypothesis\n\n"
        "This idea links Granule-cell H3K27me3 signal to local chromatin distance."
    )

    notebook = create_exploration_notebook(
        idea,
        tmp_path / "idea.ipynb",
        h5cd_path=tmp_path / "data.h5cd",
    )
    nb = json.loads(notebook.read_text())
    first_cell = "".join(nb["cells"][0]["source"])
    setup_cell = "".join(next(c["source"] for c in nb["cells"] if c.get("id") == "setup"))

    assert nb["metadata"]["uchrom_auto_discovery"]["idea_id"] == idea.idea_id
    assert first_cell.startswith(f"# Auto-discovery idea: {idea.idea_title}")
    assert "Readable hypothesis" in first_cell
    assert "```json" not in first_cell
    assert any("Runner verification summary" in "".join(c["source"]) for c in nb["cells"])
    assert "os.environ.setdefault('MPLBACKEND', 'Agg')" in setup_cell
    assert "matplotlib.use('Agg', force=True)" in setup_cell
    assert setup_cell.index("matplotlib.use('Agg', force=True)") < setup_cell.index("matplotlib.pyplot")


def test_pantheon_notebook_prompt_requires_live_notebook_editing(tmp_path):
    from uchrom.auto_discovery.pantheon import _notebook_prompt

    cdata = _make_cd()
    schema = cdata.build_discovery_schema(store=False)
    idea = _make_idea()

    prompt = _notebook_prompt(
        idea=idea,
        schema=schema,
        idea_path=tmp_path / "idea.json",
        schema_path=tmp_path / "schema.json",
        context_path=tmp_path / "schema_context.md",
        h5cd_path=tmp_path / "data.h5cd",
        output_dir=tmp_path / "run",
        notebook_path=tmp_path / "run" / "notebooks" / f"{idea.idea_id}.ipynb",
    )

    assert "notebook_edit" in prompt
    assert "notebook_execute" in prompt
    assert "notebook_read" in prompt
    assert "analysis_code" not in prompt
    assert "data-inspection code cell" in prompt
    assert "at least two" in prompt
    assert "matplotlib statistical figure" in prompt
    assert "non-interactive matplotlib backend" in prompt
    assert "MPLBACKEND" in prompt
    assert 'matplotlib.use("Agg", force=True)' in prompt
    assert "Do not switch to a GUI backend" in prompt
    assert "statistical hypothesis test" in prompt
    assert "null_hypothesis" in prompt
    assert "alternative_hypothesis" in prompt
    assert "p_value" in prompt
    assert "effect_size" in prompt
    assert "result_table must include p_value and test_method" in prompt
    assert "file_manager.observe_images" in prompt
    assert "Visual QA" in prompt
    assert "visual_qa" in prompt
    assert "Optional graphical abstract: disabled" in prompt
    assert "U-Chrom auto-discovery" in prompt

    image_prompt = _notebook_prompt(
        idea=idea,
        schema=schema,
        idea_path=tmp_path / "idea.json",
        schema_path=tmp_path / "schema.json",
        context_path=tmp_path / "schema_context.md",
        h5cd_path=tmp_path / "data.h5cd",
        output_dir=tmp_path / "run",
        notebook_path=tmp_path / "run" / "notebooks" / f"{idea.idea_id}.ipynb",
        generate_schematic_image=True,
        schematic_image_model="openai",
        schematic_image_model_args={"size": "1536x1024", "quality": "high"},
    )

    assert "file_manager.generate_image" in image_prompt
    assert "scientific graphical abstract" in image_prompt
    assert "schematic_image_path" in image_prompt
    assert "call file_manager.observe_images on the generated image path" in image_prompt
    assert "1536x1024" in image_prompt


def test_runner_verification_requires_hypothesis_test():
    from uchrom.auto_discovery.runner import _verification_code_for_idea

    code = _verification_code_for_idea(_make_idea(), output_dir=Path("/tmp"))

    assert "checks.setdefault('statistical_hypothesis_test', 'not_run')" in code
    assert "'statistical_hypothesis_test'" in code
    assert "p_value" in code
    assert "null_hypothesis" in code
    assert "alternative_hypothesis" in code
    assert "negative_control_or_permutation" in code
    assert "permutation" in code
    assert "required_for_pass" in code


def test_insert_schematic_image_cell_embeds_local_image(tmp_path):
    from uchrom.auto_discovery import create_exploration_notebook
    from uchrom.auto_discovery.pantheon import (
        _insert_schematic_image_from_agent_content,
        _insert_statistical_figure_from_agent_content,
    )

    idea = _make_idea()
    notebook = create_exploration_notebook(idea, tmp_path / "idea.ipynb")
    image = tmp_path / "schematic.png"
    image.write_bytes(
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
        b"\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02"
        b"\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDAT"
        b"\x08\xd7c\xf8\xff\xff?\x00\x05\xfe\x02\xfeA"
        b"\xe2'\xb5\x00\x00\x00\x00IEND\xaeB`\x82"
    )

    _insert_schematic_image_from_agent_content(
        {"schematic_image_path": str(image)},
        notebook,
        tmp_path,
    )

    nb = json.loads(notebook.read_text())
    assert nb["cells"][1]["id"] == "schematic_image"
    source = "".join(nb["cells"][1]["source"])
    assert "Graphical abstract" in source
    assert "data:image/png;base64," in source

    _insert_statistical_figure_from_agent_content(
        {"statistical_figure_path": str(image)},
        notebook,
        tmp_path,
    )

    nb = json.loads(notebook.read_text())
    stat_cells = [cell for cell in nb["cells"] if cell.get("id") == "statistical_figure"]
    assert len(stat_cells) == 1
    assert "Statistical figure" in "".join(stat_cells[0]["source"])


def test_lightweight_executor_supports_notebook_display(tmp_path):
    from uchrom.auto_discovery.notebooks import execute_notebook_python

    notebook = tmp_path / "display.ipynb"
    notebook.write_text(json.dumps({
        "cells": [{
            "cell_type": "code",
            "id": "display_cell",
            "metadata": {},
            "execution_count": None,
            "outputs": [],
            "source": ["value = {'ok': True}\n", "display(value)\n", "verification = {'status': 'pass'}\n"],
        }],
        "metadata": {},
        "nbformat": 4,
        "nbformat_minor": 5,
    }))

    result = execute_notebook_python(notebook)
    nb = json.loads(notebook.read_text())

    assert result["ok"]
    assert result["verification"]["status"] == "pass"
    assert "display" in result["namespace_keys"]
    assert "{'ok': True}" in "".join(nb["cells"][0]["outputs"][0]["text"])


def test_lightweight_executor_uses_noninteractive_matplotlib_backend(tmp_path):
    pytest.importorskip("matplotlib")
    from uchrom.auto_discovery.notebooks import execute_notebook_python

    notebook = tmp_path / "figure.ipynb"
    notebook.write_text(json.dumps({
        "cells": [{
            "cell_type": "code",
            "id": "plot_cell",
            "metadata": {},
            "execution_count": None,
            "outputs": [],
            "source": [
                "import matplotlib\n",
                "import matplotlib.pyplot as plt\n",
                "fig, ax = plt.subplots()\n",
                "ax.plot([0, 1], [0, 1])\n",
                "verification = {'status': 'pass', 'backend': matplotlib.get_backend()}\n",
            ],
        }],
        "metadata": {},
        "nbformat": 4,
        "nbformat_minor": 5,
    }))

    result = execute_notebook_python(notebook)
    nb = json.loads(notebook.read_text())
    outputs = nb["cells"][0]["outputs"]

    assert result["ok"]
    assert result["verification"]["backend"].lower() == "agg"
    assert any("image/png" in output.get("data", {}) for output in outputs)


def test_evidence_classification_separates_verified_from_supported():
    from uchrom.auto_discovery.evidence import classify_hypothesis_evidence

    idea = _make_idea()
    idea.expected_direction = "Positive interaction: higher marker should increase the statistic."

    conclusion = classify_hypothesis_evidence(idea, {
        "status": "pass",
        "p_value": 1.0,
        "effect_size": -0.076,
        "test_method": "unit-test permutation",
    })

    assert conclusion.notebook_status == "Notebook verified"
    assert conclusion.hypothesis_status == "Not supported"
    assert conclusion.direction_status == "Opposite direction"


def test_structured_conclusion_replaces_vague_final_interpretation(tmp_path):
    from uchrom.auto_discovery import create_exploration_notebook
    from uchrom.auto_discovery.notebooks import upsert_structured_conclusion

    idea = _make_idea()
    idea.expected_direction = "Positive interaction: higher marker should increase the statistic."
    notebook = create_exploration_notebook(idea, tmp_path / "idea.ipynb")
    nb = json.loads(notebook.read_text())
    nb["cells"].append({
        "cell_type": "markdown",
        "id": "agent_final",
        "metadata": {},
        "source": ["## Final interpretation\n", "\n", "Looks interesting but needs more work.\n"],
    })
    notebook.write_text(json.dumps(nb, indent=2))

    upsert_structured_conclusion(notebook, idea, {
        "status": "pass",
        "checks": {"statistical_hypothesis_test": "pass"},
        "parameter_value": -0.076,
        "p_value": 1.0,
        "test_method": "unit-test permutation",
        "effect_size": -0.076,
        "notes": ["unit-test caveat"],
    })

    nb = json.loads(notebook.read_text())
    final_cells = [
        cell for cell in nb["cells"]
        if "".join(cell.get("source", [])).startswith("## Final interpretation")
    ]
    assert len(final_cells) == 1
    assert final_cells[0]["id"] == "structured_conclusion"
    source = "".join(final_cells[0]["source"])
    assert "Notebook verified" in source
    assert "Not supported" in source
    assert "What verification means" in source


def test_run_auto_discovery_executes_notebook_pipeline(monkeypatch, tmp_path):
    from uchrom.auto_discovery import DiscoveryRunConfig, run_auto_discovery

    cdata = _make_cd()
    h5cd_path = tmp_path / "data.h5cd"
    cdata.write(h5cd_path)
    idea = _make_idea()
    idea2 = _make_idea(title="Bergmann H3K27me3 compaction", cell_type="Bergmann")
    analysis_code = """
import json
from pathlib import Path
import pandas as pd

result_path = RUN_OUTPUT_DIR / f"{IDEA.idea_id}_result.csv"
result_table = pd.DataFrame([{
    "cell_type": "Granule",
    "value": 1.25,
    "observed_statistic": 1.25,
    "effect_size": 0.25,
    "p_value": 0.04,
    "test_method": "unit-test permutation",
}])
result_table.to_csv(result_path, index=False)
analysis_summary = {
    "idea_id": IDEA.idea_id,
    "n_selected_cells": 1,
    "n_rows": int(len(result_table)),
    "parameter_value": 1.25,
    "observed_statistic": 1.25,
    "effect_size": 0.25,
    "p_value": 0.04,
    "test_method": "unit-test permutation",
    "null_hypothesis": "Marker status is unrelated to the statistic.",
    "alternative_hypothesis": "Marker status changes the statistic in the expected direction.",
    "hypothesis_test_status": "pass",
    "result_path": str(result_path),
    "notes": [],
}
print(json.dumps(analysis_summary, indent=2))
"""

    monkeypatch.setattr(
        "uchrom.auto_discovery.llm.generate_openai_ideas",
        lambda schema, **kwargs: [idea, idea2],
    )
    monkeypatch.setattr(
        "uchrom.auto_discovery.llm.generate_openai_analysis_code",
        lambda idea, schema, **kwargs: analysis_code,
    )

    result = run_auto_discovery(DiscoveryRunConfig(
        h5cd_path=h5cd_path,
        output_dir=tmp_path / "run",
        max_ideas=2,
        idea_source="openai",
        code_source="openai",
        execute=True,
        store_schema=True,
    ))

    assert result.n_generated == 2
    assert result.n_accepted == 2
    assert result.n_executed == 2
    assert result.n_verified >= 1
    assert (tmp_path / "run" / "ideas.jsonl").exists()
    assert (tmp_path / "run" / "reviews.jsonl").exists()
    assert (tmp_path / "run" / "results.jsonl").exists()
    assert (tmp_path / "run" / "report.md").exists()
    assert len(list((tmp_path / "run" / "notebooks").glob("*.ipynb"))) == 2


def test_auto_discovery_defaults_to_pantheon_backend(tmp_path):
    from uchrom.auto_discovery import DiscoveryRunConfig

    config = DiscoveryRunConfig(h5cd_path=tmp_path / "data.h5cd", output_dir=tmp_path / "run")

    assert config.idea_source == "pantheon"
    assert config.code_source == "pantheon"
    assert config.idea_agent_count == 3
    assert config.notebook_agent_concurrency == 3
    assert config.generate_schematic_image is False
    assert config.schematic_image_model is None
    assert config.max_complexity == 5
    assert config.llm_timeout == 420


def test_openai_backend_defaults_to_current_reasoning_model(monkeypatch, tmp_path):
    from uchrom.auto_discovery import DiscoveryIdea
    from uchrom.auto_discovery.llm import DEFAULT_OPENAI_MODEL, generate_openai_analysis_code

    cdata = _make_cd()
    schema = cdata.build_discovery_schema(store=False)
    idea = DiscoveryIdea.from_dict({
        "idea_title": "Granule H3K27me3 compaction",
        "biological_hypothesis": "H3K27me3-high bins are compacted in Granule cells.",
        "computable_parameter": "Median high-marker pairwise distance.",
        "analysis_plan": "Subset Granule cells and compare distances by marker rank.",
        "modalities": ["chromatin_tracing", "if_tracks", "cell_metadata"],
        "cell_types": ["Granule"],
        "required_fields": ["coords", "spots.cell_id", "tracks.H3K27me3", "cells.cell_type"],
        "validation_checks": ["required_fields_exist", "cell_id_alignment"],
        "expected_direction": "H3K27me3-high bins have lower distances.",
        "complexity": 3,
    })
    captured = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def read(self):
            return json.dumps({"output_text": json.dumps({"analysis_code": "result_table = None"})}).encode()

    def fake_urlopen(req, timeout):
        captured["payload"] = json.loads(req.data.decode("utf-8"))
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    monkeypatch.delenv("OPENAI_REASONING_EFFORT", raising=False)
    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    generate_openai_analysis_code(
        idea,
        schema,
        api_key="test-key",
        env_path=tmp_path / "missing.env",
        timeout=17,
    )

    assert captured["payload"]["model"] == DEFAULT_OPENAI_MODEL
    assert captured["payload"]["reasoning"] == {"effort": "medium"}
    assert captured["timeout"] == 17
