"""Tests for uchrom.pl.figure module."""

import pytest
import numpy as np
import pandas as pd
from uchrom.pl import create_figure, PanelSpec, JOURNAL_STYLES


def test_journal_styles_exist():
    """Test that all journal styles are defined."""
    assert "nature" in JOURNAL_STYLES
    assert "cell" in JOURNAL_STYLES
    assert "science" in JOURNAL_STYLES
    assert "pnas" in JOURNAL_STYLES
    assert "default" in JOURNAL_STYLES


def test_nature_style_dimensions():
    """Test Nature style has correct dimensions."""
    style = JOURNAL_STYLES["nature"]
    assert style.name == "Nature"
    assert style.font_family == "Helvetica"
    assert style.dpi == 300
    # Nature single column: 89mm ≈ 3.5 inches
    assert 3.4 < style.single_column_width < 3.6


def test_panel_spec_creation():
    """Test PanelSpec dataclass creation."""
    panel = PanelSpec(
        type="structure_3d",
        data={"projection": "xy"},
        label="A",
        title="3D Structure",
    )
    assert panel.type == "structure_3d"
    assert panel.label == "A"
    assert panel.title == "3D Structure"
    assert panel.show_scale is True


def test_create_figure_basic():
    """Test basic figure creation."""
    from uchrom.core import ChromData
    import pandas as pd

    # Create minimal ChromData
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
        PanelSpec(type="structure_3d", data={}, label="A"),
    ]
    fig = create_figure(
        chromdata=cd,
        layout="1x1",
        panels=panels,
        style="default",
    )

    assert fig is not None
    assert fig.fig is not None
    assert fig.metadata["style"] == "default"
    assert fig.metadata["layout"] == "1x1"


def test_create_figure_multi_panel():
    """Test multi-panel figure creation."""
    from uchrom.core import ChromData

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
    ]
    fig = create_figure(
        chromdata=cd,
        layout="1x2",
        panels=panels,
        style="nature",
    )

    assert len(fig.metadata["panels"]) == 2
    assert fig.metadata["panels"][0]["label"] == "A"
    assert fig.metadata["panels"][1]["label"] == "B"


def test_create_figure_with_title():
    """Test figure with overall title."""
    from uchrom.core import ChromData

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
        title="Figure 1: Test Figure",
    )

    assert fig is not None


def test_figure_save_params():
    """Test saving figure parameters to JSON."""
    from uchrom.core import ChromData
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

    panels = [PanelSpec(type="structure_3d", data={}, label="A")]
    fig = create_figure(
        chromdata=cd,
        layout="1x1",
        panels=panels,
        style="nature",
    )

    # Save params
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        params_path = f.name

    try:
        fig.save_params(params_path)

        # Load and verify
        with open(params_path, 'r') as f:
            params = json.load(f)

        assert params["style"] == "nature"
        assert params["layout"] == "1x1"
        assert len(params["panels"]) == 1
    finally:
        os.unlink(params_path)


def test_figure_to_base64():
    """Test converting figure to base64."""
    from uchrom.core import ChromData

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

    base64_str = fig.to_base64(format="png", dpi=72)
    assert isinstance(base64_str, str)
    assert len(base64_str) > 0

    # Verify it's valid base64
    import base64
    decoded = base64.b64decode(base64_str)
    assert len(decoded) > 0


def test_figure_save_pdf():
    """Test saving figure as PDF."""
    from uchrom.core import ChromData
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

    # Save as PDF
    with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as f:
        pdf_path = f.name

    try:
        fig.save(pdf_path, dpi=150)
        assert os.path.exists(pdf_path)
        assert os.path.getsize(pdf_path) > 0
    finally:
        os.unlink(pdf_path)


def test_custom_dpi():
    """Test custom DPI setting."""
    from uchrom.core import ChromData

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
        dpi=600,
    )

    assert fig.metadata["dpi"] == 600


def test_custom_figsize():
    """Test custom figure size."""
    from uchrom.core import ChromData

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
        figsize=(5.0, 4.0),
    )

    assert fig.metadata["figsize"] == (5.0, 4.0)
