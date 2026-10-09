"""uchrom.fea.window_scores: per-cell boundary insulation (against domain interiors) and loop strength from window
counts, checked against the formulas on the real pairs of one mESC cell."""

import numpy as np
import pandas as pd
import pytest

from uchrom.fea.window_scores import window_scores
from uchrom.io.pairs_windows import WindowCounts, boundary_windows, loop_windows

from .. import FIXTURES
from ..io.test_pairs_stats import MM10


def test_scores_follow_the_formulas():
    p = pd.read_csv(FIXTURES / "cell1.pairs.gz", sep="\t", header=None,
                    names=["read", "chrom1", "pos1", "chrom2", "pos2", "strand1", "strand2"])
    names = list(MM10)
    p = p[p["chrom1"].isin(names) & p["chrom2"].isin(names)]
    code = {c: i for i, c in enumerate(names)}
    res = 100_000
    b = pd.DataFrame({"chrom": ["chr1"] * 5, "pos": [20_000_000, 40_000_000, 60_000_000, 80_000_000, 100_000_000]})
    mid = pd.DataFrame({"chrom": ["chr1"] * 4, "pos": [30_000_000, 50_000_000, 70_000_000, 90_000_000]})
    lp = pd.DataFrame({"chrom1": ["chr2", "chr3"], "start1": [30_000_000, 50_000_000], "start2": [31_000_000, 52_000_000]})
    w = pd.concat([boundary_windows(b, window=1_000_000, resolution=res).assign(kind="boundary"),
                   boundary_windows(mid, window=1_000_000, resolution=res).assign(kind="interior"),
                   loop_windows(lp, resolution=res).assign(kind="loop")], ignore_index=True)
    wc = WindowCounts(["cell1", "none"], w, res, names)
    wc.add(np.zeros(len(p), int), p["chrom1"].map(code), p["pos1"], p["chrom2"].map(code), p["pos2"])
    s = window_scores(wc, pseudo=0.5)
    c, px = wc.by_part("boundary")
    ci, pxi = wc.by_part("interior")
    within, cross = (c["left"] + c["right"])[0], c["cross"][0]
    wpx, cpx = px["left"] + px["right"], px["cross"]
    ratio_b = np.log2((within.sum() + 0.5) / wpx.sum()) - np.log2((cross.sum() + 0.5) / cpx.sum())
    wi, xi = (ci["left"] + ci["right"])[0], ci["cross"][0]
    ratio_i = np.log2((wi.sum() + 0.5) / (pxi["left"] + pxi["right"]).sum()) - \
        np.log2((xi.sum() + 0.5) / pxi["cross"].sum())
    cells = s["cells"]
    assert cells.loc["cell1", "boundary_ratio"] == pytest.approx(ratio_b)
    assert cells.loc["cell1", "boundary_strength"] == pytest.approx(ratio_b - ratio_i)
    k = 2
    ins = np.log2((cross[k] + 0.5) / cpx[k]) - np.log2((within[k] + 0.5) / wpx[k]) + ratio_i
    assert s["insulation"].loc["cell1", k] == pytest.approx(ins)
    cl, pxl = wc.by_part("loop")
    lstr = np.log2((cl["peak"][0].sum() + 0.5) / pxl["peak"].sum()) - np.log2((cl["donut"][0].sum() + 0.5) /
                                                                               pxl["donut"].sum())
    assert cells.loc["cell1", "loop_strength"] == pytest.approx(lstr)
    assert s["loops"].shape == (2, 2) and s["insulation"].shape == (2, 5)
    assert cells.loc["none", "n_boundary"] == 0 and np.isfinite(cells.loc["none", "boundary_strength"])
    # a cell's contacts decay: its flanks hold more contacts per pixel than the squares crossing them
    assert cells.loc["cell1", "interior_ratio"] > 0
