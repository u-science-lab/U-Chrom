"""skills/compare-groups/scripts/compare_groups.py on synthetic data with known answers."""

import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd

from uchrom import ChromData
from tests import REPO

SCRIPT = REPO / "skills/compare-groups/scripts/compare_groups.py"
spec = importlib.util.spec_from_file_location("compare_groups", SCRIPT)
cg = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cg)


def _cd(n_a=6, n_b=6, traces=4, scale_a=2.0, rng=np.random.default_rng(0)):
    rows, xyz, cells = [], [], []
    for g, n, sc in (("A", n_a, scale_a), ("B", n_b, 1.0)):
        for c in range(n):
            cid = f"{g}{c}"
            cells.append((cid, g, 100.0 + c))
            for t in range(traces):
                for k in range(10):
                    rows.append(("chr1", k * 10, k * 10 + 10, f"{cid}_t{t}", cid))
                    xyz.append(rng.normal(0, sc, 3))
    spots = pd.DataFrame(rows, columns=["chrom", "start", "end", "trace_id", "cell_id"])
    cdf = pd.DataFrame(cells, columns=["cell_id", "cell_type", "nuc_volume_um3"]).set_index("cell_id")
    return ChromData(np.array(xyz), spots, cells=cdf)


def test_cell_is_the_unit_and_direction_is_right():
    res = cg.compare(_cd(), "field:cell_type=A", "field:cell_type=B", stat="rg", confounder=None)
    assert res["a"]["n_cells"] == 6 and res["b"]["n_cells"] == 6
    assert res["a"]["n_traces"] == 24
    assert res["a"]["median"] > 1.5 * res["b"]["median"]
    assert res["effect"]["rank_biserial"] == 1.0          # every A cell above every B cell
    assert res["test"]["p"] < 0.01


def test_small_groups_and_overlap_are_flagged():
    cd = _cd(n_a=3)
    res = cg.compare(cd, "field:cell_type=A", "A0,B0,B1,B2,B3,B4", stat="rg", confounder=None)
    joined = " ".join(res["checks"])
    assert "fewer than 5 cells" in joined and "overlap" in joined


def test_cells_column_stat():
    res = cg.compare(_cd(), "field:cell_type=A", "field:cell_type=B", stat="nuc_volume_um3", confounder=None)
    assert res["unit"] == "cell" and res["a"]["median"] == 102.5
