import numpy as np
import pandas as pd
import pytest

from uchrom import ChromData


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
