"""E2E tests for intelligent figure generation."""

import pytest
import numpy as np
import pandas as pd


def test_figure_generation_basic():
    """Test basic figure generation via create_figure."""
    from uchrom.core import ChromData
    from uchrom.pl import create_figure, PanelSpec

    # Create test data
    coords = np.random.rand(100, 3)
    spots = pd.DataFrame({
        "chrom": ["chr1"] * 100,
        "start": list(range(0, 100000, 1000)),
        "end": list(range(1000, 101000, 1000)),
        "trace_id": [0] * 100,
    })
    cd = ChromData(coords=coords, spots=spots)

    # Create figure
    panels = [
        PanelSpec(type="structure_3d", data={}, label="A", title="3D Structure"),
    ]
    fig = create_figure(
        chromdata=cd,
        layout="1x1",
        panels=panels,
        style="nature",
        dpi=300,
    )

    assert fig is not None
    assert fig.metadata["style"] == "nature"
    assert fig.metadata["dpi"] == 300


def test_figure_generation_multi_panel():
    """Test multi-panel figure generation."""
    from uchrom.core import ChromData
    from uchrom.pl import create_figure, PanelSpec

    coords = np.random.rand(100, 3)
    spots = pd.DataFrame({
        "chrom": ["chr1"] * 100,
        "start": list(range(0, 100000, 1000)),
        "end": list(range(1000, 101000, 1000)),
        "trace_id": [0] * 100,
    })
    cd = ChromData(coords=coords, spots=spots)

    panels = [
        PanelSpec(type="structure_3d", data={}, label="A", title="Panel A"),
        PanelSpec(type="contact_map", data={}, label="B", title="Panel B"),
        PanelSpec(type="track", data={}, label="C", title="Panel C"),
    ]
    fig = create_figure(
        chromdata=cd,
        layout="3x1",
        panels=panels,
        style="cell",
    )

    assert len(fig.metadata["panels"]) == 3
    assert fig.metadata["style"] == "cell"


def test_figure_export_formats():
    """Test exporting figure in different formats."""
    from uchrom.core import ChromData
    from uchrom.pl import create_figure, PanelSpec
    import tempfile
    import os

    coords = np.random.rand(50, 3)
    spots = pd.DataFrame({
        "chrom": ["chr1"] * 50,
        "start": list(range(0, 50000, 1000)),
        "end": list(range(1000, 51000, 1000)),
        "trace_id": [0] * 50,
    })
    cd = ChromData(coords=coords, spots=spots)

    panels = [PanelSpec(type="structure_3d", data={}, label="A")]
    fig = create_figure(
        chromdata=cd,
        layout="1x1",
        panels=panels,
        style="default",
    )

    # Test PDF export
    with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as f:
        pdf_path = f.name
    try:
        fig.save(pdf_path)
        assert os.path.exists(pdf_path)
        assert os.path.getsize(pdf_path) > 0
    finally:
        os.unlink(pdf_path)

    # Test PNG export
    with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as f:
        png_path = f.name
    try:
        fig.save(png_path, dpi=150)
        assert os.path.exists(png_path)
        assert os.path.getsize(png_path) > 0
    finally:
        os.unlink(png_path)


def test_figure_base64_conversion():
    """Test converting figure to base64 for WebSocket."""
    from uchrom.core import ChromData
    from uchrom.pl import create_figure, PanelSpec
    import base64

    coords = np.random.rand(50, 3)
    spots = pd.DataFrame({
        "chrom": ["chr1"] * 50,
        "start": list(range(0, 50000, 1000)),
        "end": list(range(1000, 51000, 1000)),
        "trace_id": [0] * 50,
    })
    cd = ChromData(coords=coords, spots=spots)

    panels = [PanelSpec(type="structure_3d", data={}, label="A")]
    fig = create_figure(
        chromdata=cd,
        layout="1x1",
        panels=panels,
        style="default",
    )

    # Convert to base64
    base64_str = fig.to_base64(format="png", dpi=72)
    assert isinstance(base64_str, str)
    assert len(base64_str) > 0

    # Verify it's valid base64
    decoded = base64.b64decode(base64_str)
    assert len(decoded) > 0
    # PNG signature
    assert decoded[:8] == b'\x89PNG\r\n\x1a\n'


def test_figure_params_roundtrip():
    """Test saving and loading figure parameters."""
    from uchrom.core import ChromData
    from uchrom.pl import create_figure, PanelSpec
    import tempfile
    import json
    import os

    coords = np.random.rand(50, 3)
    spots = pd.DataFrame({
        "chrom": ["chr1"] * 50,
        "start": list(range(0, 50000, 1000)),
        "end": list(range(1000, 51000, 1000)),
        "trace_id": [0] * 50,
    })
    cd = ChromData(coords=coords, spots=spots)

    panels = [
        PanelSpec(type="structure_3d", data={}, label="A", title="Test"),
    ]
    fig = create_figure(
        chromdata=cd,
        layout="1x1",
        panels=panels,
        style="science",
        dpi=600,
    )

    # Save params
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        params_path = f.name

    try:
        fig.save_params(params_path)

        # Load and verify
        with open(params_path, 'r') as f:
            params = json.load(f)

        assert params["style"] == "science"
        assert params["dpi"] == 600
        assert params["layout"] == "1x1"
        assert len(params["panels"]) == 1
        assert params["panels"][0]["label"] == "A"
        assert params["panels"][0]["title"] == "Test"
    finally:
        os.unlink(params_path)


def test_emit_artifact_figure_integration():
    """Test emit_artifact with figure type in worker."""
    from webapp.backend.ws_handler import _run_code_in_worker
    import tempfile
    import numpy as np
    import pandas as pd
    from uchrom.core import ChromData

    # Create test ChromData file
    coords = np.random.rand(50, 3)
    spots = pd.DataFrame({
        "chrom": ["chr1"] * 50,
        "start": list(range(0, 50000, 1000)),
        "end": list(range(1000, 51000, 1000)),
        "trace_id": [0] * 50,
    })
    cd = ChromData(coords=coords, spots=spots)

    with tempfile.NamedTemporaryFile(suffix='.h5cd', delete=False) as f:
        cd_path = f.name
    cd.write(cd_path)

    code = '''
from uchrom.pl import create_figure, PanelSpec
import tempfile

panels = [PanelSpec(type="structure_3d", data={}, label="A")]
fig = create_figure(
    chromdata=cd,
    layout="1x1",
    panels=panels,
    style="nature",
)

pdf_path = tempfile.mktemp(suffix=".pdf")
fig.save(pdf_path)
preview_base64 = fig.to_base64(dpi=150)

emit_artifact("figure", {
    "path": pdf_path,
    "preview": preview_base64,
    "format": "pdf",
    "params": fig.metadata
})
'''

    try:
        artifacts = _run_code_in_worker(code, cd_path)

        # Should have one figure artifact
        assert len(artifacts) == 1
        assert artifacts[0]["artifact_type"] == "figure"
        assert "preview" in artifacts[0]["payload"]
        assert "path" in artifacts[0]["payload"]
        assert "format" in artifacts[0]["payload"]
        assert artifacts[0]["payload"]["format"] == "pdf"
    finally:
        import os
        os.unlink(cd_path)


def test_journal_style_inference():
    """Test that different journal styles produce different outputs."""
    from uchrom.core import ChromData
    from uchrom.pl import create_figure, PanelSpec, JOURNAL_STYLES

    coords = np.random.rand(50, 3)
    spots = pd.DataFrame({
        "chrom": ["chr1"] * 50,
        "start": list(range(0, 50000, 1000)),
        "end": list(range(1000, 51000, 1000)),
        "trace_id": [0] * 50,
    })
    cd = ChromData(coords=coords, spots=spots)

    panels = [PanelSpec(type="structure_3d", data={}, label="A")]

    # Test each journal style
    for style_name in ["nature", "cell", "science", "pnas"]:
        fig = create_figure(
            chromdata=cd,
            layout="1x1",
            panels=panels,
            style=style_name,
        )

        assert fig.metadata["style"] == style_name
        style = JOURNAL_STYLES[style_name]
        assert fig.metadata["dpi"] == style.dpi
