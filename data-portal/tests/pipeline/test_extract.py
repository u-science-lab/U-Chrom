from uchrom.core.cdata import ChromData
from pipeline.extract import extract_stats


def test_extract_rich(rich_h5cd):
    cd = ChromData.read(rich_h5cd)
    stats = extract_stats(cd)
    assert stats["n_cells"] == 20
    assert stats["n_traces"] == 20
    assert stats["n_spots"] == 1000
    # tracks is None in this fixture -> 0 markers
    assert stats["n_markers"] == 0
    # cells has cell_type column -> non-empty mapping summing to n_cells
    assert isinstance(stats["cell_types"], dict)
    assert sum(stats["cell_types"].values()) == 20
    assert stats["assembly"] == "hg38"
    assert stats["xyz_unit"] == "nm"
    assert stats["genome_coverage"] == "chr21"


def test_extract_minimal(minimal_h5cd):
    cd = ChromData.read(minimal_h5cd)
    stats = extract_stats(cd)
    assert stats["n_cells"] == 0
    assert stats["n_traces"] == 5
    assert stats["n_markers"] == 0
    assert stats["cell_types"] == {}
    # missing uns -> safe defaults (not crash)
    assert stats["assembly"] in ("", None) or isinstance(stats["assembly"], str)
    assert stats["xyz_unit"] in ("", None) or isinstance(stats["xyz_unit"], str)


def test_extract_cell_types_counts_nan_as_unassigned():
    import pandas as pd
    import numpy as np

    class _Stub:
        # mimic the ChromData attributes extract_stats reads
        tracks = None
        uns = {}
        chroms = ["chr1"]
        n_cells = 4
        n_traces = 4
        n_spots = 4
        cells = pd.DataFrame({"cell_type": ["A", "A", np.nan, "B"]})

    from pipeline.extract import extract_stats
    stats = extract_stats(_Stub())
    # NaN must be retained as an explicit bucket, not dropped
    assert stats["cell_types"].get("unassigned") == 1
    assert stats["cell_types"].get("A") == 2
    assert stats["cell_types"].get("B") == 1
    # distribution sums to the number of typed cells
    assert sum(stats["cell_types"].values()) == 4
