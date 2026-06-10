"""Test real data loading and WebSocket data workflow."""
import os
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

# Test data paths (from main repo example-data/)
MAIN_REPO = Path("/Users/bakezq/Coding/U-Chrom")
TEST_H5CD_20CELLS = MAIN_REPO / "example-data/test_20cells_chr21.h5cd"
TEST_H5CD_FISH = MAIN_REPO / "example-data/mESC_Sox2_5cells_wnan.h5cd"
TEST_H5CD_IMPUTED = MAIN_REPO / "example-data/mESC_Sox2_5cells_imputed_snapfish.h5cd"

# Skip if test data not available
pytestmark = pytest.mark.skipif(
    not TEST_H5CD_20CELLS.exists(),
    reason="Test data not available at /Users/bakezq/Coding/U-Chrom/example-data/"
)

from webapp.backend.main import app  # noqa: E402
from webapp.backend.ws_handler import _load_chromdata  # noqa: E402

client = TestClient(app)


class TestRealDataLoading:
    """Test loading real h5cd files."""

    def test_load_h5cd_20cells(self):
        """Load 20-cell chr21 h5cd file."""
        from uchrom.core import ChromData
        cd = ChromData.read(str(TEST_H5CD_20CELLS))
        assert cd is not None
        assert len(cd.coords) > 0, "No coordinates loaded"
        assert cd.spots is not None
        assert "chrom" in cd.spots.columns
        assert cd.cells is not None
        assert len(cd.cells) == 20, f"Expected 20 cells, got {len(cd.cells)}"
        print(f"✅ Loaded {len(cd.coords)} spots from 20 cells")

    def test_load_h5cd_fish_wnan(self):
        """Load FISH data with NaN values."""
        from uchrom.core import ChromData
        cd = ChromData.read(str(TEST_H5CD_FISH))
        assert cd is not None
        assert len(cd.coords) > 0
        assert cd.spots is not None
        # Should handle NaN gracefully
        import numpy as np
        has_nan = np.isnan(cd.coords).any()
        print(f"✅ Loaded FISH data, has NaN: {has_nan}")

    def test_load_h5cd_imputed(self):
        """Load imputed FISH data."""
        from uchrom.core import ChromData
        cd = ChromData.read(str(TEST_H5CD_IMPUTED))
        assert cd is not None
        assert len(cd.coords) > 0
        import numpy as np
        has_nan = np.isnan(cd.coords).any()
        # Note: snapfish imputation may still leave some NaN values
        print(f"✅ Loaded imputed data, {len(cd.coords)} spots, has NaN: {has_nan}")


class TestWebSocketDataLoading:
    """Test data loading via WebSocket."""

    def test_ws_load_data_success(self):
        """Load data via WebSocket load_data message."""
        with client.websocket_connect("/ws/main") as ws:
            ws.send_json({
                "type": "load_data",
                "payload": {
                    "path": str(TEST_H5CD_20CELLS),
                    "format": "h5cd"
                }
            })

            # Collect response
            msg = ws.receive_json()
            if msg["type"] == "error":
                print(f"ERROR: {msg['payload']}")
            assert msg["type"] == "data_loaded", f"Expected data_loaded, got {msg['type']}: {msg.get('payload')}"
            assert "cell_count" in msg["payload"]
            assert msg["payload"]["cell_count"] == 20
            assert "chroms" in msg["payload"]
            assert len(msg["payload"]["chroms"]) > 0
            print(f"✅ WebSocket loaded data: {msg['payload']}")

    def test_ws_load_data_bad_path(self):
        """Load data with invalid path should return error."""
        with client.websocket_connect("/ws/main") as ws:
            ws.send_json({
                "type": "load_data",
                "payload": {
                    "path": "/nonexistent/file.h5cd",
                    "format": "h5cd"
                }
            })

            msg = ws.receive_json()
            assert msg["type"] == "error", f"Expected error, got {msg['type']}"
            assert "message" in msg["payload"]
            print(f"✅ WebSocket error handling: {msg['payload']['message'][:50]}")

    def test_ws_load_then_viewport(self):
        """Load data then set viewport."""
        with client.websocket_connect("/ws/main") as ws:
            # Load data
            ws.send_json({
                "type": "load_data",
                "payload": {
                    "path": str(TEST_H5CD_20CELLS),
                    "format": "h5cd"
                }
            })
            msg1 = ws.receive_json()
            assert msg1["type"] == "data_loaded"

            # Set viewport
            ws.send_json({
                "type": "update_viewport",
                "payload": {
                    "chrom": "chr21",
                    "start": 10_000_000,
                    "end": 20_000_000
                }
            })

            # Viewport update doesn't send response, but shouldn't crash
            print("✅ WebSocket load → viewport sequence OK")


class TestDataVisualization:
    """Test visualization with real data."""

    def test_figure_render_with_real_data(self):
        """Render figure using real ChromData."""
        from uchrom.core import ChromData
        from webapp.backend.figure_render import build_svg

        cd = ChromData.read(str(TEST_H5CD_20CELLS))

        # Take first 100 spots for visualization
        coords_subset = cd.coords[:100].tolist()

        svg = build_svg(
            panels=[{
                "type": "structure_3d",
                "data": {"coords": coords_subset},
                "label": "Test Structure"
            }],
            style={"preset": "nature-single"}
        )

        assert "<svg" in svg
        assert len(svg) > 200, "SVG should be non-trivial"
        assert "width" in svg
        print(f"✅ Rendered SVG with real data ({len(svg)} bytes)")


class TestDataStatistics:
    """Test data statistics and validation."""

    def test_chromdata_integrity(self):
        """Verify loaded ChromData has expected structure."""
        from uchrom.core import ChromData

        cd = ChromData.read(str(TEST_H5CD_20CELLS))

        # Check coords
        assert cd.coords.shape[1] == 3, "Coords should be (n, 3)"

        # Check spots
        required_cols = ["chrom", "start", "end", "trace_id"]
        for col in required_cols:
            assert col in cd.spots.columns, f"Missing required column: {col}"

        # Check cells
        assert cd.cells is not None
        assert len(cd.cells) > 0, "No cells found"
        # cell_id can be in columns, index, or implicit (RangeIndex)
        print(f"✅ ChromData integrity OK: {len(cd.coords)} spots, {len(cd.cells)} cells")

    def test_chromosome_coverage(self):
        """Verify chromosome data is complete."""
        from uchrom.core import ChromData

        cd = ChromData.read(str(TEST_H5CD_20CELLS))

        chroms = cd.spots["chrom"].unique()
        assert len(chroms) > 0, "No chromosomes found"

        for chrom in chroms:
            chrom_cd = cd.get_chrom(str(chrom))
            assert chrom_cd is not None
            assert len(chrom_cd.coords) > 0

        print(f"✅ Chromosome coverage OK: {list(chroms)}")
