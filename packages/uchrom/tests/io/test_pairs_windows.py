"""uchrom.io.pairs_windows: contacts per cell in windows of the map (boundary flanks / crossing squares, loop peaks /
donuts), checked against a direct count on the real pairs of one mESC cell."""

import numpy as np
import pandas as pd
import pytest

from uchrom.io.pairs_windows import WindowCounts, boundary_windows, loop_windows

from .. import FIXTURES
from .test_pairs_stats import MM10


@pytest.fixture(scope="module")
def pairs():
    p = pd.read_csv(FIXTURES / "cell1.pairs.gz", sep="\t", header=None,
                    names=["read", "chrom1", "pos1", "chrom2", "pos2", "strand1", "strand2"])
    return p[p["chrom1"].isin(list(MM10)) & p["chrom2"].isin(list(MM10))]


def _direct(pairs, w, res):
    """Contacts of each window by brute force: bins (pos - 1) // res, upper triangle."""
    cis = pairs[pairs["chrom1"] == pairs["chrom2"]]
    b1 = (cis["pos1"].to_numpy() - 1) // res
    b2 = (cis["pos2"].to_numpy() - 1) // res
    lo, hi = np.minimum(b1, b2), np.maximum(b1, b2)
    ch = cis["chrom1"].to_numpy()
    out = []
    for r in w.itertuples():
        m = ((ch == r.chrom) & (lo >= r.start1 // res) & (lo < -(-r.end1 // res))
             & (hi >= r.start2 // res) & (hi < -(-r.end2 // res)))
        out.append(int(m.sum()))
    return np.array(out)


def test_windows_match_direct_count(pairs):
    names = list(MM10)
    code = {c: i for i, c in enumerate(names)}
    res = 100_000
    rng = np.random.default_rng(0)
    cis = pairs[pairs["chrom1"] == pairs["chrom2"]].sample(40, random_state=1)
    bnd = pd.DataFrame({"chrom": cis["chrom1"].to_numpy(), "pos": cis["pos1"].to_numpy() // res * res})
    loops = pd.DataFrame({"chrom1": cis["chrom1"].to_numpy(), "start1": np.minimum(cis["pos1"], cis["pos2"]).to_numpy(),
                          "start2": np.maximum(cis["pos1"], cis["pos2"]).to_numpy()})
    w = pd.concat([boundary_windows(bnd, window=1_000_000, resolution=res),
                   loop_windows(loops, resolution=res).assign(feature=lambda d: d["feature"] + 1000)],
                  ignore_index=True)
    wc = WindowCounts(["cell1", "other"], w, res, names)
    c1 = pairs["chrom1"].map(code).to_numpy()
    c2 = pairs["chrom2"].map(code).to_numpy()
    half = len(pairs) // 2
    for sl in (slice(0, half), slice(half, None)):
        wc.add(np.zeros(len(pairs))[sl].astype(int), c1[sl], pairs["pos1"].to_numpy()[sl], c2[sl],
               pairs["pos2"].to_numpy()[sl])
    ref = _direct(pairs, w, res)
    assert np.array_equal(wc.counts[0], ref) and wc.counts[1].sum() == 0
    assert ref.sum() > 1000
    # each loop's peak is (2 * 1 + 1)^2 pixels and the four donut strips do not overlap the peak or each other
    lw = loop_windows(loops.iloc[:1], resolution=res)
    pix = set()
    for r in lw.itertuples():
        for i in range(r.start1 // res, r.end1 // res):
            for j in range(r.start2 // res, r.end2 // res):
                assert (i, j) not in pix
                pix.add((i, j))
    assert len(pix) == 11 * 11 - 3 * 3 + 9
    parts = wc.by_part()
    assert set(parts) == {"left", "right", "cross", "peak", "donut"}
    assert parts["cross"].shape == (2, 1040)
    assert parts["cross"][0, :40].sum() == ref[w["part"].eq("cross").to_numpy()].sum()


def test_save_load(tmp_path, pairs):
    w = boundary_windows(pd.DataFrame({"chrom": ["chr1"], "pos": [5_000_000]}), window=500_000, resolution=50_000)
    wc = WindowCounts(["a"], w, 50_000, list(MM10))
    wc.save(tmp_path / "w.npz", sample="x")
    back = WindowCounts.load(tmp_path / "w.npz")
    assert back.windows.equals(wc.windows) and back.meta == {"sample": "x"} and back.resolution == 50_000
