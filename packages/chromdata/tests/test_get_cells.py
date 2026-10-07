import numpy as np
import pandas as pd
import pytest

from chromdata import ChromData


def _cd():
    spots = pd.DataFrame({
        "chrom": ["chr1"] * 6, "start": [0, 10, 0, 10, 0, 10], "end": [10, 20, 10, 20, 10, 20],
        "trace_id": ["a", "a", "b", "b", "c", "c"], "cell_id": ["c1", "c1", "c2", "c2", "c3", "c3"],
    })
    cells = pd.DataFrame({"cell_type": ["x", "y", "x"]}, index=pd.Index(["c1", "c2", "c3"], name="cell_id"))
    return ChromData(np.arange(18, dtype=float).reshape(6, 3), spots, cells=cells)


def test_get_cells_subsets_spots_and_cells():
    sub = _cd().get_cells(["c1", "c3", "nope"])
    assert sorted(sub.spots["cell_id"].astype(str).unique()) == ["c1", "c3"]
    assert sub.n_spots == 4
    assert list(sub.cells.index) == ["c1", "c3"]


def test_get_cells_empty_and_missing_column():
    assert _cd().get_cells([]).n_spots == 0
    cd = _cd()
    cd.spots = cd.spots.drop(columns="cell_id")
    with pytest.raises(KeyError):
        cd.get_cells(["c1"])


def test_cells_without_spots_are_kept_when_asked_for(tmp_path):
    """Sequencing data: cells with contact maps or RNA but no coordinates."""
    from chromdata import ChromData

    no_spots = pd.DataFrame({c: pd.Series(dtype=t) for c, t in
                             [("chrom", str), ("start", np.int64), ("end", np.int64), ("trace_id", str), ("cell_id", str)]})
    cells = pd.DataFrame({"cell_type": list("abc")}, index=pd.Index(["c0", "c1", "c2"], name="cell_id"))
    cd = ChromData(np.zeros((0, 3)), no_spots, cells=cells, cellm={"e": np.arange(6.0).reshape(3, 2)})
    sub = cd.get_cells(["c2", "c0", "nope"])
    assert list(sub.cells.index) == ["c0", "c2"] and sub.cellm["e"].tolist() == [[0, 1], [4, 5]]
    assert cd.get_cell("c1").cells["cell_type"].tolist() == ["b"]
    cd.write(tmp_path / "x.chromdata.zarr")
    backed = ChromData.read(tmp_path / "x.chromdata.zarr", backed=True)
    assert list(backed.get_cells(["c1", "c2"]).cells.index) == ["c1", "c2"]
    assert backed.get_cell("c0").n_cells == 1
