"""uchrom.strc.tad.single_cell_boundaries: insulation boundaries of imputed single-cell maps and their
frequency across cells, on synthetic cells with domains."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

cooler = pytest.importorskip("cooler")

from uchrom import ChromData  # noqa: E402
from uchrom.strc.tad import single_cell as SC  # noqa: E402

RES = 10_000
N = 240
EDGES = [60, 120, 180]                                    # domain boundaries (bins)


@pytest.fixture(scope="module")
def cd(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("scb")
    from uchrom.io.pairs_maps import genome_bins

    rng = np.random.default_rng(0)
    bounds = np.r_[0, EDGES, N]
    maps = {}
    for k in range(20):
        a, b = [], []
        for lo, hi in zip(bounds[:-1], bounds[1:]):            # contacts inside the domains
            x = rng.integers(lo, hi, 400)
            y = x + (rng.pareto(1.2, 400) * 2).astype(int) + 2
            ok = y < hi
            a.append(x[ok])
            b.append(y[ok])
        x = rng.integers(0, N, 40)                                # a few anywhere
        y = np.minimum(x + rng.integers(2, 60, 40), N - 1)
        a.append(x)
        b.append(y)
        a, b = np.concatenate(a), np.concatenate(b)
        px = pd.DataFrame({"bin1_id": np.minimum(a, b), "bin2_id": np.maximum(a, b), "count": 1})
        maps[f"c{k}"] = px[px["bin1_id"] < px["bin2_id"]].groupby(["bin1_id", "bin2_id"], as_index=False)["count"].sum()
    cooler.create_scool(str(tmp / "cells.scool"), genome_bins({"chr1": N * RES}, RES), maps, ordered=True)
    no = pd.DataFrame({c: pd.Series(dtype=t) for c, t in [("chrom", str), ("start", np.int64), ("end", np.int64),
                                                          ("trace_id", str), ("cell_id", str)]})
    cd = ChromData(np.zeros((0, 3)), no, cells=pd.DataFrame(index=pd.Index(list(maps), name="cell_id")))
    cd.link_scool(str(tmp / "cells.scool"), key="per_cell", bin_size=RES)
    return cd


def test_domain_edges_are_frequent_boundaries(cd):
    params = SC.SingleCellBoundaryParams(window=None, insulation_window=80_000)
    out = SC.single_cell_boundaries(cd.copy(), params=params, per_cell=True, backend="numpy", copy=True)
    t = out.results["tads.single_cell"]
    assert len(t) == N and (t["n_cells"].max() == 20)
    freq = t["frequency"].to_numpy()
    for e in EDGES:                                          # the boundary sits at the edge or one bin off
        assert np.nanmax(freq[e - 1:e + 2]) >= 0.5
    inside = np.r_[20:40, 85:100, 140:160]
    assert np.nanmean(freq[inside]) < 0.15
    cons = t.loc[t["consensus"], "start"].to_numpy() // RES
    assert all(np.abs(cons - e).min() <= 1 for e in EDGES)
    dom = out.intervals["tads.single_cell.domains"]
    assert len(dom) >= len(EDGES) + 1
    cells = out.results["tads.single_cell.cells"]
    assert set(cells["cell_id"]) <= set(cd.cells.index) and (cells["strength"] > 0).all()
    rec = out.results.record("tads.single_cell")
    assert rec.function == "uchrom.strc.tad.single_cell_boundaries" and rec.inputs["insulation_window_bins"] == 8


def test_consensus_from_the_frequency_peaks(cd):
    params = SC.SingleCellBoundaryParams(window=None, insulation_window=80_000, consensus="frequency")
    t = SC.single_cell_boundaries(cd, params=params, backend="numpy", key_added=None)
    cons = t.loc[t["consensus"], "start"].to_numpy() // RES
    assert all(np.abs(cons - e).min() <= 1 for e in EDGES)
    assert np.isfinite(t.loc[t["consensus"], "consensus_strength"]).all()
    with pytest.raises(ValueError, match="consensus"):
        SC.SingleCellBoundaryParams(consensus="mode")


def test_windowed_imputation_gives_the_same_boundaries(cd):
    a = SC.single_cell_boundaries(cd, params=SC.SingleCellBoundaryParams(window=None, insulation_window=80_000),
                                  backend="numpy", key_added=None)
    b = SC.single_cell_boundaries(cd, params=SC.SingleCellBoundaryParams(window=1_200_000, insulation_window=80_000),
                                  backend="numpy", key_added=None)
    fa, fb = a["frequency"].to_numpy(), b["frequency"].to_numpy()
    assert np.corrcoef(np.nan_to_num(fa), np.nan_to_num(fb))[0, 1] > 0.9
