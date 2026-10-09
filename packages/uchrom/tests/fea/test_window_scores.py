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


def _uniform_contacts(n, L, rng, dmin=1_000, dmax=3_000_000):
    """Contacts with no structure: distance log-uniform, left end uniform along the chromosome."""
    d = np.exp(rng.uniform(np.log(dmin), np.log(dmax), n)).astype(np.int64)
    x = (rng.random(n) * (L - d)).astype(np.int64)
    return x + 1, x + d + 1


def test_window_fractions_tile_the_chromosome():
    from uchrom.fea.window_scores import _window_fractions
    from uchrom.io import distance_edges

    L, m = 10_000_000, 4_000_000
    edges = distance_edges(max_distance=L)
    w = pd.DataFrame({"chrom": ["c"] * 4, "start1": [0, 0, m, 0], "end1": [L, m, L, m],
                      "start2": [0, 0, m, m], "end2": [L, m, L, L]})
    F = _window_fractions(w, 25_000, edges, {"c": L})
    inside = np.r_[0.0, edges] < L
    assert np.allclose(F[0, inside], 1.0)                          # the whole triangle holds every contact
    assert np.allclose(F[1:].sum(0)[inside], 1.0)                  # left + right + cross tile it


def test_expected_matches_counts_without_structure():
    from uchrom.fea.window_scores import window_expected
    from uchrom.io import ContactStats, distance_edges

    rng = np.random.default_rng(1)
    L, res = 10_000_000, 25_000
    p1, p2 = _uniform_contacts(400_000, L, rng)
    b = pd.DataFrame({"chrom": ["c"] * 3, "pos": [2_000_000, 5_000_000, 8_000_000]})
    lp = pd.DataFrame({"chrom1": ["c"] * 3, "start1": [1_000_000, 4_000_000, 6_000_000],
                       "start2": [1_150_000, 4_500_000, 8_000_000]})
    w = pd.concat([boundary_windows(b, window=250_000, resolution=res).assign(kind="boundary"),
                   loop_windows(lp, resolution=res).assign(kind="loop")], ignore_index=True)
    wc = WindowCounts(["a", "b"], w, res, ["c"])
    cell = (rng.random(len(p1)) < 0.25).astype(int)                # two cells, 1:3 contacts
    zero = np.zeros(len(p1), int)
    wc.add(cell, zero, p1, zero, p2)
    st = ContactStats(["b", "a", "c"], ["c"], distance_edges(max_distance=L), orientation=False)
    st.add(np.where(cell == 0, 1, 0), zero, p1, zero, p2)          # rows in another order: matched by id
    E = window_expected(wc, st, chromsizes={"c": L})
    O = wc.counts.astype(float)
    assert E.shape == O.shape and np.all(np.isfinite(E))
    assert np.all(np.abs(O - E) <= 5 * np.sqrt(E) + 2)
    assert O.sum() == pytest.approx(E.sum(), rel=0.01)
    s = window_scores(wc, expected=E)
    assert {"boundary_strength_oe", "loop_strength_oe"} <= set(s["cells"].columns)
    # no structure: observed = expected within the counting noise
    c, _ = wc.by_part("boundary")
    within, cross = (c["left"] + c["right"]), c["cross"]
    sd = np.log2(np.e) * np.sqrt(1 / cross.sum(1) + 1 / within.sum(1))
    assert np.all(np.abs(s["cells"]["boundary_strength_oe"].to_numpy()) < 4 * sd)
    e, _ = wc.by_part("boundary", values=E)
    q = e["cross"] / (e["cross"] + e["left"] + e["right"])
    assert np.all(np.abs(s["insulation_oe"].to_numpy()) < 4 * np.sqrt(q * (1 - q) / (cross + within)))
    with pytest.raises(ValueError):
        wc.by_part("loop", values=E[:, :3])


def test_oe_shares_ignore_coverage():
    """A shallow copy of a cell (2 % of its contacts, a few per window) has, on average, the same shares."""
    from uchrom.fea.window_scores import window_expected
    from uchrom.io import ContactStats, distance_edges

    rng = np.random.default_rng(2)
    L, res = 10_000_000, 25_000
    p1, p2 = _uniform_contacts(300_000, L, rng)
    b = pd.DataFrame({"chrom": ["c"] * 95, "pos": np.arange(1, 96) * 100_000})
    w = boundary_windows(b, window=100_000, resolution=res).assign(kind="boundary")
    keep = rng.random(len(p1)) < 0.02                              # a shallow cell: a few contacts per window
    rows = np.r_[np.zeros(len(p1), int), np.where(keep, 1, -1)]
    zero = np.zeros(2 * len(p1), int)
    P1, P2 = np.r_[p1, p1], np.r_[p2, p2]
    wc = WindowCounts(["deep", "shallow"], w, res, ["c"])
    wc.add(rows, zero, P1, zero, P2)
    st = ContactStats(["deep", "shallow"], ["c"], distance_edges(max_distance=L), orientation=False)
    st.add(rows, zero, P1, zero, P2)
    s = window_scores(wc, expected=window_expected(wc, st, chromsizes={"c": L}))
    oe = s["insulation_oe"]
    shallow = oe.loc["shallow"].dropna()
    assert len(shallow) > 80
    assert abs(shallow.mean() - oe.loc["deep"].mean()) < 4 * shallow.std() / np.sqrt(len(shallow))
