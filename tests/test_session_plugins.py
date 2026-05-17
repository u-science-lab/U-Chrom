"""Tests for session persistence and plugin system."""

import pytest
import tempfile
import os
import json
from webapp.backend.session import Session, Viewport


def test_session_to_dict():
    """Test session serialization to dictionary."""
    session = Session(session_id="test123")
    session.viewport = Viewport(chrom="chr1", start=1000000, end=2000000)
    session.cell_selection = ["cell_001", "cell_002"]
    session.conversation_history = [
        {"role": "user", "content": "Hello"},
        {"role": "agent", "content": "Hi there"}
    ]
    session.analysis_results = {"tads": [{"start": 1000000, "end": 1500000}]}
    session.annotations = [{"type": "highlight", "label": "Region 1"}]
    session.highlight_regions = [{"chrom": "chr1", "start": 1000000, "end": 1500000}]
    session.colormap_config = {"scheme": "viridis", "property": "compartment"}

    data = session.to_dict()

    assert data["version"] == "2.0"
    assert data["session_id"] == "test123"
    assert data["viewport"]["chrom"] == "chr1"
    assert data["viewport"]["start"] == 1000000
    assert len(data["cell_selection"]) == 2
    assert len(data["conversation_history"]) == 2
    assert "tads" in data["analysis_results"]
    assert len(data["annotations"]) == 1
    assert data["colormap_config"]["scheme"] == "viridis"


def test_session_from_dict():
    """Test session deserialization from dictionary."""
    data = {
        "version": "2.0",
        "session_id": "test123",
        "viewport": {"chrom": "chr1", "start": 1000000, "end": 2000000},
        "cell_selection": ["cell_001"],
        "conversation_history": [{"role": "user", "content": "Test"}],
        "analysis_results": {"compartments": []},
        "annotations": [{"label": "Test"}],
        "highlight_regions": [],
        "colormap_config": {"scheme": "RdBu_r"},
        "panels": [],
    }

    session = Session.from_dict(data, "new_session")

    assert session.session_id == "new_session"
    assert session.viewport.chrom == "chr1"
    assert session.viewport.start == 1000000
    assert len(session.cell_selection) == 1
    assert len(session.conversation_history) == 1
    assert "compartments" in session.analysis_results
    assert session.colormap_config["scheme"] == "RdBu_r"


def test_session_save_load():
    """Test session save and load to file."""
    session = Session(session_id="test123")
    session.viewport = Viewport(chrom="chr2", start=5000000, end=6000000)
    session.analysis_results = {"loops": [{"start": 5100000, "end": 5200000}]}

    with tempfile.NamedTemporaryFile(suffix=".uchromfig", delete=False, mode='w') as f:
        path = f.name

    try:
        # Save
        session.save(path)
        assert os.path.exists(path)

        # Load
        loaded = Session.load(path, "loaded_session")
        assert loaded.session_id == "loaded_session"
        assert loaded.viewport.chrom == "chr2"
        assert loaded.viewport.start == 5000000
        assert "loops" in loaded.analysis_results
    finally:
        os.unlink(path)


def test_plugin_registration():
    """Test plugin registration."""
    from uchrom.plugins import UChromPlugin, PluginManager

    class TestPlugin(UChromPlugin):
        def __init__(self):
            super().__init__()
            self.name = "TestPlugin"
            self.version = "1.0.0"

        def analyze(self, chromdata, **kwargs):
            return {"result": "test"}

    manager = PluginManager()
    plugin = TestPlugin()
    manager.register_plugin(plugin)

    assert "TestPlugin" in manager.plugins
    assert manager.get_plugin("TestPlugin") is plugin


def test_plugin_list():
    """Test listing plugins."""
    from uchrom.plugins import UChromPlugin, PluginManager

    class Plugin1(UChromPlugin):
        def __init__(self):
            super().__init__()
            self.name = "Plugin1"
            self.version = "1.0.0"
            self.description = "Test plugin 1"

        def analyze(self, chromdata, **kwargs):
            return {}

    class Plugin2(UChromPlugin):
        def __init__(self):
            super().__init__()
            self.name = "Plugin2"
            self.version = "2.0.0"
            self.description = "Test plugin 2"

        def analyze(self, chromdata, **kwargs):
            return {}

    manager = PluginManager()
    manager.register_plugin(Plugin1())
    manager.register_plugin(Plugin2())

    plugins = manager.list_plugins()
    assert len(plugins) == 2
    assert plugins[0]["name"] == "Plugin1"
    assert plugins[1]["version"] == "2.0.0"


def test_plugin_run():
    """Test running a plugin."""
    from uchrom.plugins import UChromPlugin, PluginManager
    from uchrom.core import ChromData
    import numpy as np
    import pandas as pd

    class SumPlugin(UChromPlugin):
        def __init__(self):
            super().__init__()
            self.name = "SumPlugin"

        def analyze(self, chromdata, **kwargs):
            return {"sum": float(np.sum(chromdata.coords))}

    # Create test data
    coords = np.array([[1, 2, 3], [4, 5, 6]])
    spots = pd.DataFrame({
        "chrom": ["chr1", "chr1"],
        "start": [0, 1000],
        "end": [1000, 2000],
        "trace_id": [0, 0],
    })
    cd = ChromData(coords=coords, spots=spots)

    # Run plugin
    manager = PluginManager()
    plugin = SumPlugin()
    manager.register_plugin(plugin)

    result = manager.run_plugin("SumPlugin", cd)
    assert result["sum"] == 21.0  # 1+2+3+4+5+6


def test_example_plugin_distance_stats():
    """Test DistanceStats example plugin."""
    from uchrom.plugins.examples.distance_stats import DistanceStatsPlugin
    from uchrom.core import ChromData
    import numpy as np
    import pandas as pd

    # Create test data
    coords = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1]])
    spots = pd.DataFrame({
        "chrom": ["chr1"] * 4,
        "start": [0, 1000, 2000, 3000],
        "end": [1000, 2000, 3000, 4000],
        "trace_id": [0] * 4,
    })
    cd = ChromData(coords=coords, spots=spots)

    plugin = DistanceStatsPlugin()
    result = plugin.analyze(cd)

    assert "mean" in result
    assert "median" in result
    assert "std" in result
    assert "histogram" in result
    assert result["n_points"] == 4
    assert result["min"] == 1.0  # Distance between adjacent points


def test_example_plugin_compactness():
    """Test Compactness example plugin."""
    from uchrom.plugins.examples.compactness import CompactnessPlugin
    from uchrom.core import ChromData
    import numpy as np
    import pandas as pd

    # Create test data (cube)
    coords = np.array([
        [0, 0, 0], [1, 0, 0], [0, 1, 0], [1, 1, 0],
        [0, 0, 1], [1, 0, 1], [0, 1, 1], [1, 1, 1]
    ])
    spots = pd.DataFrame({
        "chrom": ["chr1"] * 8,
        "start": list(range(0, 8000, 1000)),
        "end": list(range(1000, 9000, 1000)),
        "trace_id": [0] * 8,
    })
    cd = ChromData(coords=coords, spots=spots)

    plugin = CompactnessPlugin()
    result = plugin.analyze(cd)

    assert "radius_of_gyration" in result
    assert "center_of_mass" in result
    assert "principal_moments" in result
    assert "asphericity" in result
    assert len(result["principal_moments"]) == 3


def test_example_plugin_data_export():
    """Test DataExport example plugin."""
    from uchrom.plugins.examples.data_export import DataExportPlugin
    from uchrom.core import ChromData
    import numpy as np
    import pandas as pd

    coords = np.array([[1, 2, 3], [4, 5, 6]])
    spots = pd.DataFrame({
        "chrom": ["chr1", "chr1"],
        "start": [0, 1000],
        "end": [1000, 2000],
        "trace_id": [0, 0],
    })
    cd = ChromData(coords=coords, spots=spots)

    plugin = DataExportPlugin()

    # Test CSV export
    result = plugin.analyze(cd, format="csv")
    assert result["format"] == "csv"
    assert "chrom" in result["data"]
    assert result["n_rows"] == 2

    # Test PDB export
    result = plugin.analyze(cd, format="pdb")
    assert result["format"] == "pdb"
    assert "ATOM" in result["data"]
    assert result["n_atoms"] == 2

    # Test JSON export
    result = plugin.analyze(cd, format="json")
    assert result["format"] == "json"
    data = json.loads(result["data"])
    assert len(data["coords"]) == 2
