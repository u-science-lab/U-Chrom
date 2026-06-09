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
