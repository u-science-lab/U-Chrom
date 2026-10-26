"""uchrom.fea.cluster_maps: the SpaceA authors' cluster filter, binned fragment pairs of multi-way contacts,
per-cell .scool and pooled .mcool."""

import itertools
import math
from collections import Counter, defaultdict

import numpy as np
import pandas as pd
import pytest

from chromdata import ChromData

from uchrom.fea.cluster_maps import cluster_pixels, clusters_to_mcool, clusters_to_scool, filter_clusters

SIZES = {"chrA": 50_000, "chrB": 30_000, "chrC": 20_000}
RES = 5_000


def _store(seed=0, n_clusters=300, n_cells=6):
    """Clusters of 1-30 fragments, mostly on one chromosome, some repeated starts, a few on chrM (left out)."""
    rng = np.random.default_rng(seed)
    rows = []
    for c in range(n_clusters):
        n = int(rng.integers(1, 31))
        home = rng.choice(list(SIZES))
        for _ in range(n):
            ch = home if rng.random() < 0.7 else rng.choice(list(SIZES) + ["chrM"])
            s = int(rng.integers(0, (SIZES.get(ch, 16_000)) - 200))
            rows.append((f"c{c}", f"cell{c % n_cells}", ch, s, s + int(rng.integers(50, 150))))
        if n > 3 and rng.random() < 0.3:                     # a repeated start (another end)
            rows.append(rows[-1][:4] + (rows[-1][4] + 7,))
    df = pd.DataFrame(rows, columns=["cluster", "cell", "chrom", "start", "end"])
    cells = pd.DataFrame(index=pd.Index([f"cell{i}" for i in range(n_cells)], name="cell_id"))
    empty = pd.DataFrame({"chrom": pd.Series([], dtype=str), "start": pd.Series([], dtype=np.int64),
                          "end": pd.Series([], dtype=np.int64), "trace_id": pd.Series([], dtype=str)})
    cd = ChromData(np.zeros((0, 3)), empty, cells=cells, uns={"genome_assembly": "test"})
    cd.set_clusters("raw", df, cluster="cluster", cell="cell")
    return cd


def _authors_filter(reads, min_size=2, max_size=1000, min_chr=0.15, min_cis=0.2):
    """filter_sprite.py's spot_qc for one cluster (reads: 'chrom:start'), the reads it keeps."""
    reads = set(reads)
    n = len(reads)
    if not min_size <= n <= max_size:
        return set()
    by = defaultdict(list)
    for r in reads:
        by[r.split(":")[0]].append(r)
    kept = {c: v for c, v in by.items() if len(v) / n > min_chr}
    k = sum(len(v) for v in kept.values())
    tot = math.comb(k, 2) if k >= 2 else 0
    cis = sum(math.comb(len(v), 2) for v in kept.values())
    return {r for v in kept.values() for r in v} if tot and cis / tot >= min_cis else set()


def test_filter_matches_the_authors_code():
    cd = _store()
    t = cd.clusters["raw"]
    new = filter_clusters(cd, "raw")
    assert cd.clusters["raw_filtered"] is new
    want = Counter()
    for _, g in t.to_frame().groupby("cluster"):
        for r in _authors_filter(f"{c}:{s}" for c, s in zip(g["chrom"], g["start"])):
            want[(g["cell_id"].iloc[0], r)] += 1
    got = Counter((str(c), f"{ch}:{s}") for c, ch, s in
                  zip(new.to_frame()["cell_id"], new.to_frame()["chrom"], new.to_frame()["start"]))
    assert got == want and sum(want.values()) > 100
    assert new.attrs["filtered_from"] == "raw"


def _brute(t, ids):
    """Fragment pairs per bin pair (bins of SIZES, by start), by enumeration."""
    first = dict(zip(SIZES, np.concatenate([[0], np.cumsum([-(-s // RES) for s in SIZES.values()])])))
    cnt = Counter()
    for _, g in t.members(ids).groupby("cluster"):
        b = [int(first[c]) + s // RES for c, s in zip(g["chrom"], g["start"]) if c in SIZES]
        for x, y in itertools.combinations(b, 2):
            cnt[(min(x, y), max(x, y))] += 1
    return pd.Series(cnt, dtype=np.int64).sort_index()


def test_pixels_are_the_fragment_pairs():
    cd = _store(1)
    t = cd.clusters["raw"]
    bins, px = cluster_pixels(cd, "raw", chromsizes=SIZES, resolution=RES, max_size=20)
    assert len(bins) == sum(-(-s // RES) for s in SIZES.values())
    ids = np.flatnonzero((t.sizes() >= 2) & (t.sizes() <= 20))
    want = _brute(t, ids)
    got = px.set_index(["bin1_id", "bin2_id"])["count"].sort_index()
    assert (px["bin1_id"] <= px["bin2_id"]).all()
    assert got.index.equals(want.index) and (got.to_numpy() == want.to_numpy()).all()
    # one cell's clusters
    _, one = cluster_pixels(cd, "raw", chromsizes=SIZES, resolution=RES, cells=["cell2"], max_size=20)
    r = t.cell_clusters("cell2")
    assert one["count"].sum() == _brute(t, np.intersect1d(ids, np.arange(r.start, r.stop))).sum() > 0


def test_scool_and_mcool(tmp_path):
    cooler = pytest.importorskip("cooler")
    cd = _store(2)
    filter_clusters(cd, "raw")
    st = clusters_to_scool(cd, "raw_filtered", tmp_path / "m.scool", chromsizes=SIZES, resolution=RES,
                           max_size=None, link_key="per_cell")
    assert cd.uns["linked_scool"]["per_cell"]["bin_size"] == RES
    for cell in ["cell0", "cell3"]:
        clr = cooler.Cooler(f"{tmp_path / 'm.scool'}::/cells/{cell}")
        _, px = cluster_pixels(cd, "raw_filtered", chromsizes=SIZES, resolution=RES, cells=[cell], max_size=None)
        assert int(clr.pixels()[:]["count"].sum()) == int(px["count"].sum()) == st.loc[cell, "n_pairs"]
    out = clusters_to_mcool(cd, "raw_filtered", tmp_path / "p.mcool", chromsizes=SIZES,
                            resolutions=[RES, 2 * RES], max_size=None, link_key="pooled")
    assert cd.uns["linked_cool"]["pooled"]["format"] == "mcool"
    total = st["n_pairs"].sum()
    for r in (RES, 2 * RES):
        clr = cooler.Cooler(f"{out}::/resolutions/{r}")
        assert int(clr.pixels()[:]["count"].sum()) == total
        assert "weight" in clr.bins().columns
