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


def test_discovery_schema_exposes_enriched_feature_groups():
    cdata = _make_cd()
    cdata.tracks["seq.gc_fraction"] = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6]
    cdata.tracks["gtf.nearest_tss_distance"] = [0, 10, 20, 30, 40, 50]
    cdata.tracks["strc.distance_to_tad_boundary"] = [5, 4, 3, 2, 1, 0]
    cdata.tracks["peak.h3k27me3_overlap"] = [0, 1, 0, 1, 0, 1]
    cdata.tracks["H2A.X"] = [1, 1, 0, 0, 1, 0]
    cdata.results["bin_features"] = pd.DataFrame({
        "chrom": ["chr1", "chr1"],
        "start": [0, 25_000],
        "end": [25_000, 50_000],
        "gc_fraction": [0.42, 0.51],
        "nearest_tss_distance": [0, 10_000],
    })
    cdata.results["tads"] = pd.DataFrame({
        "chrom": ["chr1"],
        "start": [0],
        "end": [50_000],
        "score": [3.2],
    })
    cdata.uns["feature_registry"] = [
        {"feature_group": "sequence", "features": ["seq.gc_fraction"]},
        {"feature_group": "annotation", "features": ["gtf.nearest_tss_distance"]},
        {"feature_group": "peaks", "features": ["peak.h3k27me3_overlap"]},
    ]

    schema = cdata.build_discovery_schema(store=True)
    context = cdata.describe_for_agent(max_items=10)

    assert schema["modalities"]["sequence_features"]["present"]
    assert schema["modalities"]["genome_annotations"]["present"]
    assert schema["modalities"]["structure_annotations"]["present"]
    assert schema["modalities"]["peak_features"]["present"]
    assert schema["summary"]["n_feature_registry_entries"] == 3
    assert schema["catalogs"]["track_groups"]["seq"]["values"] == ["seq.gc_fraction"]
    assert schema["catalogs"]["track_groups"]["peak"]["values"] == ["peak.h3k27me3_overlap"]
    assert "H2A" not in schema["catalogs"]["track_groups"]
    assert "H2A.X" in schema["catalogs"]["track_groups"]["marker"]["values"]
    assert "seq.gc_fraction" not in schema["catalogs"]["track_groups"]["marker"]["values"]
    assert "bin_features" in schema["fields"]["results"]["tables"]
    assert schema["fields"]["results"]["tables"]["tads"]["columns"] == [
        "chrom",
        "start",
        "end",
        "score",
    ]
    assert "track_groups:" in context
    assert "result_tables:" in context
    assert "feature_registry:" in context


def test_discovery_schema_includes_linked_anndata():
    ad = pytest.importorskip("anndata")
    from uchrom.auto_discovery import DiscoveryIdea, review_idea_against_schema

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

    idea = DiscoveryIdea(
        idea_title="Pcp2 expression linked chromatin phenotype",
        biological_hypothesis="Pcp2 expression should align with a linked chromatin phenotype.",
        computable_parameter="Association between linked Pcp2 expression and H3K27me3 signal.",
        analysis_plan="Align cells by linked_adata.obs_names and compare expression to chromatin tracks.",
        modalities=["rna_expression", "chromatin_tracing", "if_tracks", "cell_metadata"],
        cell_types=["Bergmann", "Granule"],
        required_fields=[
            "linked_adata.X",
            "linked_adata.var.Pcp2",
            "linked_adata.obs_names",
            "cells.cell_type",
            "tracks.H3K27me3",
        ],
        validation_checks=["required_fields_exist", "cell_id_alignment", "statistical_hypothesis_test"],
    )

    review = review_idea_against_schema(idea, schema)

    assert review.accepted
    assert "linked_adata.obs_names" not in review.missing_fields


def test_discovery_schema_includes_references_and_user_annotations(tmp_path):
    from uchrom import ChromData

    cdata = _make_cd()
    ref = cdata.add_reference(
        role="primary_dataset_paper",
        title="Takei 2025 cerebellum multi-omics",
        doi="10.0000/example",
        url="https://example.org/takei",
        year=2025,
        notes="Primary paper associated with this linked dataset.",
    )
    ann = cdata.add_user_annotation(
        scope="analysis_constraint",
        target="linked_adata",
        text="RNA and chromatin tracing are linked at cell_id level; do not assume RNA spot geometry.",
        tags=["constraint", "multiomics_alignment"],
    )

    assert ref["reference_id"].startswith("ref_")
    assert ann["annotation_id"].startswith("ann_")

    schema = cdata.build_discovery_schema(store=True)
    context = cdata.describe_for_agent(max_items=10)

    assert schema["summary"]["n_references"] == 1
    assert schema["summary"]["n_user_annotations"] == 1
    assert schema["references"][0]["role"] == "primary_dataset_paper"
    assert schema["references"][0]["doi"] == "10.0000/example"
    assert schema["user_annotations"][0]["scope"] == "analysis_constraint"
    assert schema["knowledge_seed_context"]["reference_roles"]["primary_dataset_paper"] == 1
    assert schema["knowledge_seed_context"]["annotation_scopes"]["analysis_constraint"] == 1
    assert "dataset_references:" in context
    assert "user_annotations:" in context
    assert "Takei 2025 cerebellum multi-omics" in context
    assert "RNA and chromatin tracing are linked" in context

    path = tmp_path / "schema_context.h5cd"
    cdata.write(path)
    out = ChromData.read(path)

    assert out.dataset_references[0]["reference_id"] == ref["reference_id"]
    assert out.user_annotations[0]["annotation_id"] == ann["annotation_id"]
    assert out.discovery_schema["references"][0]["doi"] == "10.0000/example"
    assert out.validate_discovery_schema() == []


def test_refresh_literature_claims_for_iteration_uses_cached_and_schema_knowledge(tmp_path):
    from uchrom.auto_discovery import (
        build_idea_graph_from_run,
        refresh_literature_claims_for_iteration,
    )

    cdata = _make_cd()
    ref = cdata.add_reference(
        role="primary_dataset_paper",
        title="Takei 2025 cerebellum multi-omics",
        doi="10.0000/example",
        year=2025,
        notes="Primary dataset paper links chromatin tracing with IF markers.",
    )
    ann = cdata.add_user_annotation(
        scope="analysis_constraint",
        target="linked_adata",
        text="Treat RNA and chromatin tracing as cell-level matched modalities.",
    )
    schema = cdata.build_discovery_schema(store=False)
    seed_claims = tmp_path / "seed_claims.jsonl"
    seed_claims.write_text(
        json.dumps({
            "claim_text": "Pcp2 is a Purkinje marker in cerebellum.",
            "source": {
                "reference_id": "seed_ref",
                "title": "Seed source",
                "url": "https://example.org/seed",
            },
            "entities": {
                "genes": ["Pcp2"],
                "cell_types": ["Purkinje"],
                "modalities": ["rna_expression"],
            },
        }) + "\n"
    )

    run_dir = tmp_path / "run"
    result = refresh_literature_claims_for_iteration(
        run_dir=run_dir,
        schema=schema,
        seed_claim_paths=[seed_claims],
    )
    graph = build_idea_graph_from_run(run_dir)

    assert result.n_claims == 3
    assert Path(result.claims_path).exists()
    assert Path(result.retrieval_log_path).exists()
    assert ref["reference_id"] in Path(result.claims_path).read_text()
    assert ann["annotation_id"] in Path(result.claims_path).read_text()
    assert graph.summary()["node_kinds"]["LiteratureClaim"] == 3
    assert any(edge["relation"] == "mentions_gene" for edge in graph.edges)


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


def test_schematic_coverage_reports_missing_verified_notebooks(tmp_path):
    from uchrom.auto_discovery import create_exploration_notebook, schematic_coverage_for_run
    from uchrom.auto_discovery.pantheon import _insert_schematic_image_from_agent_content

    run_dir = tmp_path / "run"
    notebooks_dir = run_dir / "notebooks"
    notebooks_dir.mkdir(parents=True)
    image = tmp_path / "schematic.png"
    image.write_bytes(
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
        b"\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02"
        b"\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDAT"
        b"\x08\xd7c\xf8\xff\xff?\x00\x05\xfe\x02\xfeA"
        b"\xe2'\xb5\x00\x00\x00\x00IEND\xaeB`\x82"
    )

    idea_with_image = _make_idea(title="Granule H3K27me3 compaction")
    idea_missing = _make_idea(title="Bergmann H3K27me3 compaction", cell_type="Bergmann")
    notebook_with_image = create_exploration_notebook(
        idea_with_image,
        notebooks_dir / f"{idea_with_image.idea_id}.ipynb",
    )
    notebook_missing = create_exploration_notebook(
        idea_missing,
        notebooks_dir / f"{idea_missing.idea_id}.ipynb",
    )
    _insert_schematic_image_from_agent_content(
        {"schematic_image_path": str(image)},
        notebook_with_image,
        run_dir,
    )

    (run_dir / "ideas.jsonl").write_text(
        "\n".join(json.dumps(idea.to_dict()) for idea in [idea_with_image, idea_missing]) + "\n"
    )
    (run_dir / "results.jsonl").write_text(
        "\n".join(json.dumps({
            "idea_id": idea.idea_id,
            "notebook": str(path),
            "verification": {"status": "pass"},
        }) for idea, path in [
            (idea_with_image, notebook_with_image),
            (idea_missing, notebook_missing),
        ]) + "\n"
    )

    coverage = schematic_coverage_for_run(run_dir)

    assert coverage["n_targets"] == 2
    assert coverage["n_present"] == 1
    assert coverage["n_missing"] == 1
    assert coverage["coverage"] == 0.5
    assert coverage["missing_notebooks"] == [str(notebook_missing)]


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
    from uchrom import ChromData
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
    assert result.graph_path is not None
    assert result.graph_summary_path is not None
    assert result.graph_html_path is not None
    assert Path(result.graph_path).exists()
    assert Path(result.graph_summary_path).exists()
    assert Path(result.graph_html_path).exists()
    assert len(list((tmp_path / "run" / "notebooks").glob("*.ipynb"))) == 2
    out = ChromData.read(h5cd_path)
    assert out.uns["auto_discovery_graph"]["latest_graph_path"] == result.graph_path
    assert out.uns["auto_discovery_runs"][-1]["graph_path"] == result.graph_path


def test_build_idea_graph_from_run_artifacts(tmp_path):
    from uchrom.auto_discovery import (
        build_idea_graph_from_run,
        idea_signature,
        load_idea_graph,
        write_idea_graph_artifacts,
    )

    run_dir = tmp_path / "run"
    run_dir.mkdir()
    idea = _make_idea()
    idea.metadata["direction_id"] = "coverage_gap-test"
    idea.expected_direction = "Positive interaction: higher marker should increase the statistic."
    idea.metadata["source_claim_ids"] = ["claim_pcp2_marker"]
    idea.metadata["parent_idea_ids"] = ["parent_idea"]

    def write_jsonl(path, rows):
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w") as fh:
            for row in rows:
                fh.write(json.dumps(row) + "\n")

    write_jsonl(run_dir / "ideas.jsonl", [idea.to_dict()])
    write_jsonl(run_dir / "reviews.jsonl", [{
        "idea_id": idea.idea_id,
        "accepted": True,
        "errors": [],
        "warnings": [],
        "missing_fields": [],
    }])
    write_jsonl(run_dir / "results.jsonl", [{
        "idea_id": idea.idea_id,
        "notebook": str(run_dir / "notebooks" / f"{idea.idea_id}.ipynb"),
        "execution_ok": True,
        "elapsed_sec": 1.2,
        "errors": [],
        "verification": {
            "status": "pass",
            "p_value": 0.01,
            "effect_size": 0.25,
            "observed_statistic": 0.25,
            "parameter_value": 0.25,
            "test_method": "unit-test permutation",
            "result_path": str(run_dir / f"{idea.idea_id}_result.csv"),
        },
    }])

    signature = idea_signature(idea)
    graph = build_idea_graph_from_run(run_dir)
    artifacts = write_idea_graph_artifacts(graph, run_dir)
    loaded = load_idea_graph(artifacts["graph_json"])
    summary = loaded.summary()
    edge_relations = {edge["relation"] for edge in loaded.edges}

    assert signature["markers"] == ["H3K27me3"]
    assert signature["parameter_family"] == "spatial_distance"
    assert f"idea:{idea.idea_id}" in loaded.nodes
    assert f"evidence:{idea.idea_id}" in loaded.nodes
    assert loaded.nodes[f"evidence:{idea.idea_id}"]["hypothesis_status"] == "Supported"
    assert "supports" in edge_relations
    assert "motivated_by" in edge_relations
    assert "derived_from" in edge_relations
    assert "direction_proposed" in edge_relations
    assert summary["coverage"]["markers"]["H3K27me3"] == 1
    assert Path(artifacts["graph_summary"]).exists()


def test_build_idea_graph_marks_schema_rejected_ideas(tmp_path):
    from uchrom.auto_discovery import build_idea_graph_from_run

    run_dir = tmp_path / "run"
    run_dir.mkdir()
    idea = _make_idea()

    def write_jsonl(path, rows):
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w") as fh:
            for row in rows:
                fh.write(json.dumps(row) + "\n")

    write_jsonl(run_dir / "ideas.jsonl", [idea.to_dict()])
    write_jsonl(run_dir / "reviews.jsonl", [{
        "idea_id": idea.idea_id,
        "accepted": False,
        "errors": ["required field does not exist: linked_adata.obs_names"],
        "warnings": [],
        "missing_fields": ["linked_adata.obs_names"],
    }])

    graph = build_idea_graph_from_run(run_dir)
    idea_node = graph.nodes[f"idea:{idea.idea_id}"]

    assert idea_node["review_status"] == "Rejected"
    assert idea_node["review_accepted"] is False
    assert idea_node["execution_state"] == "Rejected by schema"
    assert idea_node["hypothesis_status"] == "Rejected"
    assert f"evidence:{idea.idea_id}" not in graph.nodes


def test_plan_discovery_directions_from_idea_graph(tmp_path):
    from uchrom.auto_discovery import (
        build_idea_graph_from_run,
        directions_to_agent_context,
        plan_discovery_directions,
        write_direction_artifacts,
    )

    cdata = _make_cd()
    schema = cdata.build_discovery_schema(store=False)
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    idea = _make_idea()
    idea.expected_direction = "Positive interaction: higher marker should increase the statistic."

    def write_jsonl(path, rows):
        with path.open("w") as fh:
            for row in rows:
                fh.write(json.dumps(row) + "\n")

    write_jsonl(run_dir / "ideas.jsonl", [idea.to_dict()])
    write_jsonl(run_dir / "reviews.jsonl", [{
        "idea_id": idea.idea_id,
        "accepted": True,
        "errors": [],
        "warnings": [],
        "missing_fields": [],
    }])
    write_jsonl(run_dir / "results.jsonl", [{
        "idea_id": idea.idea_id,
        "notebook": str(run_dir / "notebooks" / f"{idea.idea_id}.ipynb"),
        "execution_ok": True,
        "elapsed_sec": 1.2,
        "errors": [],
        "verification": {
            "status": "pass",
            "p_value": 0.01,
            "effect_size": 0.25,
            "test_method": "unit-test permutation",
        },
    }])

    graph = build_idea_graph_from_run(run_dir)
    directions = plan_discovery_directions(graph, schema, max_directions=6)
    artifacts = write_direction_artifacts(directions, run_dir)
    context = directions_to_agent_context(directions)
    direction_types = {d.direction_type for d in directions}

    assert directions
    assert directions[0].direction_id
    assert "evidence_extension" in direction_types
    assert "cell_spatial_context" in direction_types
    assert "global_structure" in direction_types
    assert "coverage_gap" in direction_types
    spatial_direction = next(d for d in directions if d.direction_type == "cell_spatial_context")
    assert "cellm.umap" in spatial_direction.target_facets["cell_spatial_fields"]
    assert "pan-cell" in context
    assert idea.idea_id in context
    assert "Graph-derived discovery directions" in context
    assert Path(artifacts["directions_json"]).exists()
    assert Path(artifacts["directions_markdown"]).exists()


def test_literature_claims_and_graph_html_viewer(tmp_path):
    from uchrom.auto_discovery import (
        build_idea_graph_from_run,
        ingest_literature_claims,
        load_idea_graph,
        write_idea_graph_artifacts,
        write_idea_graph_html,
    )

    run_dir = tmp_path / "run"
    run_dir.mkdir()
    idea = _make_idea()
    idea.metadata["direction_id"] = "coverage_gap-test"
    idea.metadata["direction_type"] = "coverage_gap"

    def write_jsonl(path, rows):
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w") as fh:
            for row in rows:
                fh.write(json.dumps(row) + "\n")

    write_jsonl(run_dir / "ideas.jsonl", [idea.to_dict()])
    write_jsonl(run_dir / "reviews.jsonl", [{
        "idea_id": idea.idea_id,
        "accepted": True,
        "errors": [],
        "warnings": [],
        "missing_fields": [],
    }])
    write_jsonl(run_dir / "results.jsonl", [{
        "idea_id": idea.idea_id,
        "notebook": str(run_dir / "notebooks" / f"{idea.idea_id}.ipynb"),
        "execution_ok": True,
        "elapsed_sec": 1.2,
        "errors": [],
        "verification": {
            "status": "pass",
            "p_value": 0.01,
            "effect_size": 0.25,
            "test_method": "unit-test permutation",
        },
    }])
    claims_path = run_dir / "browser" / "claims.jsonl"
    write_jsonl(claims_path, [{
        "claim_id": "claim_hp1alpha_heterochromatin",
        "claim": "HP1alpha marks heterochromatin domains relevant to chromatin compaction.",
        "source_title": "Browser agent source",
        "url": "https://example.org/paper",
        "genes": [],
        "markers": ["HP1alpha"],
        "cell_types": ["Granule"],
        "supports_idea_ids": [idea.idea_id],
        "extraction_method": "browser_agent",
    }])

    graph = build_idea_graph_from_run(run_dir)
    assert graph.nodes["literature_claim:claim_hp1alpha_heterochromatin"]["kind"] == "LiteratureClaim"
    assert graph.nodes["direction:coverage_gap-test"]["kind"] == "Direction"
    assert any(edge["relation"] == "direction_proposed" for edge in graph.edges)
    assert any(edge["relation"] == "literature_supports" for edge in graph.edges)

    extra_claims = tmp_path / "extra_claims.jsonl"
    write_jsonl(extra_claims, [{
        "claim_text": "Pcp2 is a Purkinje marker.",
        "source": {"reference_id": "ref_pcp2", "title": "Pcp2 source"},
        "entities": {"genes": ["Pcp2"], "cell_types": ["Purkinje"]},
        "related_idea_ids": [idea.idea_id],
    }])
    assert ingest_literature_claims(graph, extra_claims) == 1

    artifacts = write_idea_graph_artifacts(graph, run_dir)
    html_path = write_idea_graph_html(
        load_idea_graph(artifacts["graph_json"]),
        run_dir / "graph" / "idea_graph.html",
        notebook_base_url="_auto_discovery_notebooks",
    )
    html = html_path.read_text()

    assert "U-Chrom Idea Graph" in html
    assert "Tree view" not in html
    assert "Discovery tree" not in html
    assert "cdata" in html
    assert "uchrom-idea-graph-app" in html
    assert "Visible ideas" in html
    assert "Global" in html
    assert "Overview" in html
    assert "Focus" in html
    assert "Follow-up direction" in html
    assert "Idea graph" in html
    assert "legend-pills" in html
    assert "canvas-tools" in html
    assert "node-card-bg" in html
    assert "global-node-visual" in html
    assert "global-node-label" in html
    assert "globalLabelScale" in html
    assert "conclusion" in html
    assert "viewport-layer" in html
    assert "lineage-path" in html
    assert "evidence-strip" in html
    assert "evidence-segment" in html
    assert "selection-dock" in html
    assert "minimap" in html
    assert "node-badge" in html
    assert "node-badge-text" in html
    assert "dimmed" in html
    assert "lane-guides" in html
    assert "lane-band" in html
    assert "Notebook evidence" in html
    assert "edge-label" in html
    assert "edge-label-bg" in html
    assert "edgeLabelVisible" in html
    assert "node-port" in html
    assert "lineage-edge" in html
    assert "Technical details" in html
    assert "Notebook" in html
    assert "primary-link" in html
    assert "_auto_discovery_notebooks" in html
    assert "LiteratureClaim" in html
    assert "claim_hp1alpha_heterochromatin" in html


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


def test_iterative_auto_discovery_defaults_to_inline_schematics(monkeypatch, tmp_path):
    from uchrom.auto_discovery import IterativeDiscoveryConfig
    from uchrom.auto_discovery.runner import DiscoveryRunResult
    import uchrom.auto_discovery.iterative as iterative

    captured = {}

    def fake_run_auto_discovery(config):
        captured["generate_schematic_image"] = config.generate_schematic_image
        captured["schematic_image_model"] = config.schematic_image_model
        captured["schematic_image_model_args"] = config.schematic_image_model_args
        return DiscoveryRunResult(
            output_dir=str(config.output_dir),
            n_generated=1,
            n_accepted=1,
            n_executed=1,
            n_verified=1,
            report_path="report.md",
            ideas_path="ideas.jsonl",
            reviews_path="reviews.jsonl",
            results_path="results.jsonl",
        )

    monkeypatch.setattr(iterative, "run_auto_discovery", fake_run_auto_discovery)
    monkeypatch.setattr(iterative, "build_idea_graph_from_runs", lambda *_, **__: object())
    monkeypatch.setattr(
        iterative,
        "write_idea_graph_artifacts",
        lambda *_: {"graph_json": "graph.json", "graph_summary": "graph.md"},
    )
    monkeypatch.setattr(iterative, "_schema_for_h5cd", lambda *_, **__: {})
    monkeypatch.setattr(iterative, "plan_discovery_directions", lambda *_, **__: [])
    monkeypatch.setattr(
        iterative,
        "write_direction_artifacts",
        lambda *_: {
            "directions_json": "directions.json",
            "directions_markdown": "directions.md",
        },
    )
    monkeypatch.setattr(iterative, "write_idea_graph_html", lambda *_, **__: tmp_path / "graph.html")

    config = IterativeDiscoveryConfig(
        h5cd_path=tmp_path / "data.h5cd",
        output_dir=tmp_path / "iterative",
        iterations=1,
        schematic_image_model="openai",
        schematic_image_model_args={"size": "1536x1024"},
    )
    iterative.run_iterative_auto_discovery(config)

    assert config.generate_schematic_image is True
    assert captured == {
        "generate_schematic_image": True,
        "schematic_image_model": "openai",
        "schematic_image_model_args": {"size": "1536x1024"},
    }


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
