"""uchrom.io.pairs_stats: contact-distance histograms (scHiCluster's bins) and trans counts per cell, checked on
the real pairs of one mESC cell (fixtures/cell1.pairs.gz) against numpy.histogram and direct counts."""

import numpy as np
import pandas as pd
import pytest

from uchrom import ChromData
from uchrom.io.pairs_stats import ORIENTATIONS, ContactStats, distance_edges, pairs_contact_stats

from .. import FIXTURES

MM10 = {"chr1": 195471971, "chr2": 182113224, "chr3": 160039680, "chr4": 156508116, "chr5": 151834684,
        "chr6": 149736546, "chr7": 145441459, "chr8": 129401213, "chr9": 124595110, "chr10": 130694993,
        "chr11": 122082543, "chr12": 120129022, "chr13": 120421639, "chr14": 124902244, "chr15": 104043685,
        "chr16": 98207768, "chr17": 94987271, "chr18": 90702639, "chr19": 61431566, "chrX": 171031299}


@pytest.fixture(scope="module")
def pairs():
    return pd.read_csv(FIXTURES / "cell1.pairs.gz", sep="\t", header=None,
                       names=["read", "chrom1", "pos1", "chrom2", "pos2", "strand1", "strand2"])


def test_edges_are_schicluster():
    # scHiCluster contact_distance: nbins = floor(log2(max / 2500) / 0.125); bins = 2500 * exp2(0.125 * arange)
    nbins = np.floor(np.log2(max(MM10.values()) / 2500) / 0.125)
    ref = 2500 * np.exp2(0.125 * np.arange(nbins + 1))
    e = distance_edges(MM10)
    assert np.array_equal(e, ref) and len(e) == 131
    # Guo et al. 2026: short = bins 51-76 (~200 kb - 2 Mb), long = bins 103-114 (~20 - 50 Mb)
    assert 2.0e5 < e[51] < 2.1e5 and 1.9e6 < e[77] < 2.0e6 and 1.8e7 < e[103] < 1.9e7 and 5.3e7 < e[115] < 5.4e7


def test_histogram_matches_numpy(pairs):
    names = list(MM10)
    code = {c: i for i, c in enumerate(names)}
    c1 = pairs["chrom1"].map(code).fillna(-1).astype(int).to_numpy()
    c2 = pairs["chrom2"].map(code).fillna(-1).astype(int).to_numpy()
    edges = distance_edges(MM10)
    st = ContactStats(["cell1"], names, edges)
    half = len(pairs) // 2                                  # two chunks: accumulation across calls
    for sl in (slice(0, half), slice(half, None)):
        p = pairs.iloc[sl]
        st.add(np.zeros(len(p), int), c1[sl], p["pos1"], c2[sl], p["pos2"], p["strand1"], p["strand2"])
    cis = (pairs["chrom1"] == pairs["chrom2"]) & pairs["chrom1"].isin(names)
    d = (pairs["pos2"] - pairs["pos1"]).abs()[cis].to_numpy()
    ref = np.histogram(d, edges)[0]
    assert np.array_equal(st.distance[0].sum(0)[1:-1], ref)              # scHiCluster's decay vector
    assert st.distance[0].sum(0)[0] == (d < edges[0]).sum()
    assert st.distance[0].sum(0)[-1] == (d > edges[-1]).sum()
    assert st.n_cis[0] == cis.sum()
    for i, c in enumerate(names):                                       # per chromosome
        dc = (pairs["pos2"] - pairs["pos1"]).abs()[cis & (pairs["chrom1"] == c)].to_numpy()
        assert np.array_equal(st.distance[0, i, 1:-1], np.histogram(dc, edges)[0])
    trans = pairs["chrom1"].isin(names) & pairs["chrom2"].isin(names) & ~cis
    assert st.n_trans[0] == trans.sum() and st.trans[0].sum() == 2 * trans.sum()
    for i, c in enumerate(names):
        assert st.trans[0, i] == ((pairs["chrom1"] == c) | (pairs["chrom2"] == c))[trans].sum()
    # orientation in genome order: summed over orientations = the histogram
    assert np.array_equal(st.orientation[0].sum(0), st.distance[0].sum(0))
    p = pairs[cis]
    up_minus = np.where(p["pos1"] <= p["pos2"], p["strand1"], p["strand2"]) == "-"
    down_minus = np.where(p["pos1"] <= p["pos2"], p["strand2"], p["strand1"]) == "-"
    o = 2 * up_minus + down_minus
    assert ORIENTATIONS[1] == "+-"
    assert np.array_equal(st.orientation[0].sum(1), np.bincount(o, minlength=4))


def test_cells_other_chroms_and_last_edge():
    edges = np.array([10.0, 20.0, 40.0])
    st = ContactStats(["a", "b"], ["chr1", "chr2"], edges, orientation=False)
    # distances 5 (under), 10, 19 (bin 1), 20, 40 (last bin, closed), 41 (over); one trans; one other chrom;
    # one with no cell
    st.add([0, 0, 0, 1, 1, 1, 1, 0, -1], [0, 0, 0, 0, 0, 0, 0, -1, 0], [100] * 9,
           [0, 0, 0, 0, 0, 0, 1, 0, 0], [105, 110, 119, 120, 140, 141, 100, 100, 100])
    assert st.distance[0, 0].tolist() == [1, 2, 0, 0]
    assert st.distance[1, 0].tolist() == [0, 0, 2, 1]
    assert st.trans.tolist() == [[0, 0], [1, 1]] and st.n_trans.tolist() == [0, 1]
    assert st.n_other == 1


def test_save_load_merge_write(tmp_path, pairs):
    names = list(MM10)
    st = pairs_contact_stats({"cell1": FIXTURES / "cell1.pairs.gz"}, chromsizes=MM10)
    assert st.orientation is None and st.n_cis[0] > 0
    st.save(tmp_path / "s.npz", filter="all")
    back = ContactStats.load(tmp_path / "s.npz")
    assert np.array_equal(back.distance, st.distance) and back.chroms == names and back.meta == {"filter": "all"}
    back.merge(st)
    assert np.array_equal(back.distance, 2 * st.distance)
    with pytest.raises(ValueError):
        back.merge(ContactStats(["x"], names, st.edges, orientation=False))
    cd = ChromData(coords=np.zeros((0, 3)), spots=pd.DataFrame({"chrom": pd.Series([], dtype=str),
                                                                "start": [], "end": [], "trace_id": []}),
                   cells=pd.DataFrame({"cell_id": ["other", "cell1"]}))
    st.write(cd, key="contacts")
    assert cd.cellm["contacts.distance"].shape == (2, len(names), len(st.edges) + 1)
    assert cd.cells["contacts.n_cis"].tolist() == [0, int(st.n_cis[0])]
    rec = cd.uns["contact_stats"]["contacts"]
    assert rec["chroms"] == names and rec["n_cells_counted"] == 1 and len(rec["edges"]) == len(st.edges)
