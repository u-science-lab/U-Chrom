"""Tracks, intervals, contact / distance matrices and stats (API.md, genome views)."""

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from chromdata import ChromData
from uchrom_browser.data import MAX_MATRIX_BINS, DatasetStore, decode_matrix
from tests import FIXTURES

SIM = FIXTURES / "sim_cell1" / "sim_cell1.cdz"


def _two_cell_dataset():
    """Two cells × one trace on chr1 with 3 bins; trace b is a×2 in space."""
    spots = pd.DataFrame({
        "chrom": ["chr1"] * 6, "start": [0, 100, 200] * 2, "end": [100, 200, 300] * 2,
        "trace_id": ["a"] * 3 + ["b"] * 3, "cell_id": ["c1"] * 3 + ["c2"] * 3,
    })
    coords = np.array([[0, 0, 0], [1, 0, 0], [3, 0, 0], [0, 0, 0], [2, 0, 0], [6, 0, 0]], float)
    tracks = pd.DataFrame({"H3K27ac": [1.0, 2.0, 3.0, 3.0, 4.0, 5.0], "label": list("abcdef")})
    tads = pd.DataFrame({"chrom": ["chr1", "chr1", "chr2"], "start": [0, 150, 0],
                         "end": [150, 300, 10], "score": [0.5, np.nan, 1.0]})
    cd = ChromData(coords, spots, spot_tracks=tracks, results={"tads": tads}, uns={"xyz_unit": "um"})
    cd.bin_tracks = pd.DataFrame({"ATAC": [0.5, 1.5, 2.5]})   # one value per locus
    return DatasetStore().add(cd, name="two")


def test_summary_lists_genome_views():
    s = _two_cell_dataset().summary()
    assert s["has_coords"] is True
    assert s["n_bins"] == 3
    # non-numeric columns are not tracks
    assert s["tracks"] == [{"name": "ATAC", "level": "bin", "grid": "spots"}, {"name": "H3K27ac", "level": "spot", "grid": "spots"}]
    assert s["intervals"] == [{"key": "tads", "n": 3, "kind": None}]
    assert s["contact_maps"] == []


def test_tracks_aggregate_per_bin_and_by_cell():
    ds = _two_cell_dataset()
    t = ds.tracks(["H3K27ac"], "chr1")
    assert t["bin_starts"] == [0, 100, 200] and t["bin_ends"] == [100, 200, 300]
    assert t["n_spots"] == [2, 2, 2] and t["values"]["H3K27ac"] == [2.0, 3.0, 4.0]
    assert ds.tracks(["H3K27ac"], "chr1", cell_id="c2")["values"]["H3K27ac"] == [3.0, 4.0, 5.0]
    assert ds.tracks(["H3K27ac"], "chr1", start=150)["bin_starts"] == [100, 200]
    assert ds.tracks(["H3K27ac"], "chr1", agg="max")["values"]["H3K27ac"] == [3.0, 4.0, 5.0]
    with pytest.raises(KeyError):
        ds.tracks(["nope"], "chr1")


def test_bin_level_track_is_broadcast_to_spots():
    ds = _two_cell_dataset()
    t = ds.tracks(["ATAC", "H3K27ac"], "chr1", cell_id="c1")
    assert t["values"]["ATAC"] == [0.5, 1.5, 2.5] and t["n_spots"] == [1, 1, 1]


def test_typed_intervals_are_listed_first():
    ds = _two_cell_dataset()
    ds.cd.intervals["tads.x"] = pd.DataFrame({"chrom": ["chr1"], "start": [0], "end": [300]})
    s = ds.summary()
    assert s["intervals"][0] == {"key": "tads.x", "n": 1, "kind": "domain"}
    assert ds.intervals("tads.x", "chr1")["rows"] == [["chr1", 0, 300]]


def test_intervals_filter_by_locus():
    ds = _two_cell_dataset()
    iv = ds.intervals("tads", "chr1", start=160, end=400)
    assert iv["columns"] == ["chrom", "start", "end", "score"]
    assert iv["rows"] == [["chr1", 150, 300, None]]


def test_distance_matrices_single_cell_and_population():
    ds = _two_cell_dataset()
    one = decode_matrix(ds.distance("chr1", trace_id="a"))
    np.testing.assert_allclose(one["matrix"], [[0, 1, 3], [1, 0, 2], [3, 2, 0]])
    assert one["header"]["unit"] == "um" and one["header"]["bin_starts"] == [0, 100, 200]
    pop = decode_matrix(ds.distance("chr1", stat="median"))
    np.testing.assert_allclose(pop["matrix"][0, 2], np.median([3, 6]))
    assert pop["header"]["n_traces"] == 2
    cf = decode_matrix(ds.distance("chr1", stat="contact", threshold=2.5))
    assert cf["header"]["value"] == "contact_frequency"
    np.testing.assert_allclose(cf["matrix"][0, 1], 1.0)   # 1 and 2 < 2.5
    np.testing.assert_allclose(cf["matrix"][0, 2], 0.0)   # 3 and 6
    with pytest.raises(LookupError):
        ds.distance("chr9")
    with pytest.raises(ValueError):
        ds.distance("chr1", stat="mode")


def test_distance_matrix_is_pooled_to_the_cap():
    n = int(MAX_MATRIX_BINS * 1.5)
    spots = pd.DataFrame({"chrom": "chr1", "start": np.arange(n) * 10, "end": np.arange(n) * 10 + 10,
                          "trace_id": "t"})
    coords = np.c_[np.arange(n, dtype=float), np.zeros(n), np.zeros(n)]
    ds = DatasetStore().add(ChromData(coords, spots), name="long")
    m = decode_matrix(ds.distance("chr1"))
    assert m["matrix"].shape == (750, 750) and "2 bins pooled" in m["header"]["note"]


def test_stats_rg_and_scaling():
    ds = _two_cell_dataset()
    rg = ds.stats_rg("chr1")
    assert rg["trace_ids"] == ["a", "b"] and rg["cell_ids"] == ["c1", "c2"]
    expect_a = np.sqrt(np.mean((np.array([0, 1, 3]) - 4 / 3) ** 2))
    np.testing.assert_allclose(rg["rg"], [expect_a, 2 * expect_a])
    sc = ds.stats_scaling("chr1", n_bins=2)
    assert sum(sc["n_pairs"]) == 6 and sc["unit"] == "um"
    assert sc["median"][0] < sc["median"][-1]  # farther along the genome → farther in space


def _cool(path: Path, n_bins: int = 6, res: int = 100):
    import cooler

    bins = pd.DataFrame({"chrom": "chr1", "start": np.arange(n_bins) * res, "end": np.arange(n_bins) * res + res})
    i, j = np.triu_indices(n_bins)
    pix = pd.DataFrame({"bin1_id": i, "bin2_id": j, "count": (1 + (i == j) * 9).astype(int)})
    cooler.create_cooler(str(path), bins, pix, ordered=True)
    return bins, pix


def test_contact_maps_cool_mcool_scool(tmp_path):
    cooler = pytest.importorskip("cooler")
    _cool(tmp_path / "bulk.cool")
    cooler.zoomify_cooler(str(tmp_path / "bulk.cool"), str(tmp_path / "bulk.mcool"), [100, 200], chunksize=1000)
    bins, pix = _cool(tmp_path / "x.cool")
    cooler.create_scool(str(tmp_path / "cells.scool"), bins, {"c1": pix, "c2": pix.assign(count=1)}, ordered=True)

    spots = pd.DataFrame({"chrom": ["chr1"], "start": [0], "end": [100], "trace_id": ["t"]})
    cd = ChromData(np.zeros((1, 3)), spots)
    cd.link_cool("bulk.mcool", key="bulk", label="Bulk")   # relative to the dataset
    cd.link_scool("cells.scool", key="cells")
    cd.write(tmp_path / "d.chromdata.zarr")
    ds = DatasetStore().load(tmp_path / "d.chromdata.zarr")
    assert ds.backed

    maps = {m["key"]: m for m in ds.summary()["contact_maps"]}
    assert maps["bulk"]["kind"] == "mcool" and maps["bulk"]["resolutions"] == [100, 200]
    assert maps["cells"]["kind"] == "scool" and maps["cells"]["n_cells"] == 2 and maps["cells"]["per_cell"]
    assert maps["bulk"]["chroms"] == [{"name": "chr1", "length": 600}]

    m = decode_matrix(ds.contacts("bulk", "chr1"))
    assert m["header"]["resolution"] == 100 and m["matrix"].shape == (6, 6)
    assert m["matrix"][0, 0] == 10 and m["matrix"][0, 1] == 1 and m["matrix"][1, 0] == 1  # symmetric
    coarse = decode_matrix(ds.contacts("bulk", "chr1", resolution=200))
    # cool stores the upper triangle: the (0,1) pixel is counted once when coarsening
    assert coarse["matrix"].shape == (3, 3) and coarse["matrix"][0, 0] == 10 + 10 + 1
    part = decode_matrix(ds.contacts("bulk", "chr1", start=200, end=400))
    assert part["header"]["bin_starts"] == [200, 300]

    c2 = decode_matrix(ds.contacts("cells", "chr1", cell="c2"))
    assert np.all(c2["matrix"] == 1)
    with pytest.raises(LookupError):
        ds.contacts("cells", "chr1")          # per-cell map needs a cell
    with pytest.raises(KeyError):
        ds.contacts("cells", "chr1", cell="zz")
    with pytest.raises(ValueError):
        ds.contacts("bulk", "chr1", resolution=150)


def test_dataset_without_coords_lists_cells_from_table():
    spots = pd.DataFrame({c: pd.Series(dtype=t) for c, t in
                          [("chrom", str), ("start", np.int64), ("end", np.int64), ("trace_id", str), ("cell_id", str)]})
    cells = pd.DataFrame({"cell_type": ["A", "B"]}, index=pd.Index(["b10", "b2"], name="cell_id"))
    ds = DatasetStore().add(ChromData(np.zeros((0, 3)), spots, cells=cells), name="nocoords")
    s = ds.summary()
    assert s["has_coords"] is False and s["n_cells"] == 2 and s["n_spots"] == 0
    assert [c["cell_id"] for c in ds.cells()["cells"]] == ["b2", "b10"]


@pytest.mark.skipif(not SIM.exists(), reason="sim_cell1 example missing")
def test_simulated_structure_agrees_with_its_contacts():
    """Real data: NucDynamics on cell1.pairs.  Bins that were in contact in
    the input must be much closer in the reconstructed 3-D structure."""
    pytest.importorskip("cooler")
    ds = DatasetStore().load(SIM)
    C = decode_matrix(ds.contacts("cell1_contacts", "chr2", resolution=1_000_000))
    D = decode_matrix(ds.distance("chr2"))
    cb = np.array(C["header"]["bin_starts"])
    blk = np.searchsorted(cb, np.array(D["header"]["bin_starts"]), side="right") - 1
    n = len(cb)
    dist = np.full((n, n), np.nan)
    for i in range(n):
        for j in range(i + 2, n):
            ri, rj = blk == i, blk == j
            if ri.any() and rj.any():
                dist[i, j] = np.nanmean(D["matrix"][np.ix_(ri, rj)])
    iu = np.triu_indices(n, 2)
    c, d = C["matrix"][iu], dist[iu]
    ok = np.isfinite(d)
    ratio = np.median(d[ok & (c > 0)]) / np.median(d[ok & (c == 0)])
    assert ratio < 0.7  # observed 0.51 on chr2


def test_whole_genome_view(tmp_path, monkeypatch):
    """chrom="*": chromosomes end to end (natural order), maps / tracks / intervals in genome
    coordinates."""
    cooler = pytest.importorskip("cooler")
    import uchrom_browser.data as data

    res = 100
    # the cooler lists chr2 before chr1: the genome view reorders to chr1, chr2
    bins = pd.DataFrame({"chrom": ["chr2"] * 3 + ["chr1"] * 4,
                         "start": [0, 100, 200, 0, 100, 200, 300], "end": [100, 200, 300, 100, 200, 300, 400]})
    i, j = np.triu_indices(len(bins))
    pix = pd.DataFrame({"bin1_id": i, "bin2_id": j, "count": 1 + i + 2 * j})
    cooler.create_cooler(str(tmp_path / "bulk.cool"), bins, pix, ordered=True)
    cooler.create_scool(str(tmp_path / "cells.scool"), bins,
                        {"c1": pix, "c2": pix.assign(count=2)}, ordered=True)

    ds = _two_cell_dataset()
    ds.cd.link_cool(str(tmp_path / "bulk.cool"), key="bulk")
    ds.cd.link_scool(str(tmp_path / "cells.scool"), key="cells")
    lay = ds.summary()["genome"]
    assert [(c["name"], c["offset"], c["length"]) for c in lay] == [("chr1", 0, 400), ("chr2", 400, 300)]

    # the dense map, rows / columns in genome order (chr1 bins, then chr2)
    dense = cooler.Cooler(str(tmp_path / "bulk.cool")).matrix(balance=False)[:]
    order = [3, 4, 5, 6, 0, 1, 2]
    want = dense[np.ix_(order, order)]
    m = decode_matrix(ds.contacts("bulk", "*"))
    assert m["header"]["chrom"] == "*" and m["header"]["resolution"] == res
    assert m["header"]["bin_starts"] == [0, 100, 200, 300, 400, 500, 600]
    np.testing.assert_array_equal(m["matrix"], want)

    # a group of a per-cell map: the sum of its cells' maps
    ref = ds.register_group(["c1", "c2"], "both")["id"]
    g = decode_matrix(ds.contacts("cells", "*", group=ref))
    c2 = np.where(dense > 0, 2, 0)
    np.testing.assert_array_equal(g["matrix"], want + c2[np.ix_(order, order)])
    assert g["header"]["n_cells"] == 2
    c1 = decode_matrix(ds.contacts("cells", "*", cell="c1"))
    np.testing.assert_array_equal(c1["matrix"], want)
    with pytest.raises(LookupError):
        ds.contacts("cells", "*")

    # pooled within each chromosome (never across a boundary); the total is kept
    monkeypatch.setattr(data, "MAX_MATRIX_BINS", 4)
    ds._cache.pop("genome_contacts", None)
    p = decode_matrix(ds.contacts("bulk", "*"))
    assert p["header"]["resolution"] == 2 * res and "2x2 bins pooled" in p["header"]["note"]
    assert p["header"]["bin_starts"] == [0, 200, 400, 600] and p["header"]["bin_ends"] == [200, 400, 600, 700]
    assert p["matrix"].sum() == pytest.approx(want.sum())

    # tracks and intervals in genome coordinates
    t = ds.tracks(["ATAC"], "*")
    assert t["chrom"] == "*" and t["bin_starts"] == [0, 100, 200] and t["values"]["ATAC"] == [0.5, 1.5, 2.5]
    iv = ds.intervals("tads", "*")
    cols = iv["columns"]
    rows = {(r[cols.index("chrom")], r[cols.index("start")], r[cols.index("end")]) for r in iv["rows"]}
    assert ("chr2", 400, 410) in rows and ("chr1", 150, 300) in rows
    with pytest.raises(ValueError, match="per chromosome"):
        ds.distance("*")


def _cluster_dataset():
    """Two cells' multi-way contacts on chr1 / chr2: cluster k1 of c1 spans chr1:100-900 with a fragment on
    chr2, k2 (c1) lies in chr1:400-450, k3 (c2) has one fragment at chr1:500."""
    frags = pd.DataFrame({
        "cluster": ["k1"] * 4 + ["k2"] * 2 + ["k3"],
        "cell": ["c1"] * 6 + ["c2"],
        "chrom": ["chr1", "chr1", "chr1", "chr2", "chr1", "chr1", "chr1"],
        "start": [100, 420, 900, 50, 400, 440, 500],
        "end": [150, 470, 950, 90, 410, 450, 520],
    })
    empty = pd.DataFrame({"chrom": pd.Series([], dtype=str), "start": pd.Series([], dtype=np.int64),
                          "end": pd.Series([], dtype=np.int64), "trace_id": pd.Series([], dtype=str)})
    cd = ChromData(np.zeros((0, 3)), empty, cells=pd.DataFrame(index=pd.Index(["c1", "c2"], name="cell_id")))
    cd.set_clusters("sprite", frags, cluster="cluster", cell="cell", attrs={"assay": "SPRITE"})
    return DatasetStore().add(cd, name="clusters")


def test_cluster_track_window():
    d = _cluster_dataset()
    s = d.summary()
    assert s["clusters"] == [{"key": "sprite", "n_clusters": 3, "n_fragments": 7, "per_cell": True,
                              "assay": "SPRITE", "filtered_from": None}]
    w = d.clusters("sprite", "chr1", 300, 600, min_size=1)
    assert w["n_clusters"] == 3
    # by span start: k1 (100-900, 4 fragments, 3 on chr1), k2 (400-450), k3 (500)
    assert [(c["span"], c["size"], c["chrom_size"], c["cell"]) for c in w["clusters"]] == [
        ([100, 950], 4, 3, "c1"), ([400, 450], 2, 2, "c1"), ([500, 520], 1, 1, "c2")]
    assert w["clusters"][0]["fragments"] == [[420, 470]]
    assert w["clusters"][1]["fragments"] == [[400, 410], [440, 450]]
    assert [c["cell"] for c in d.clusters("sprite", "chr1", 300, 600, cell_id="c2", min_size=1)["clusters"]] == ["c2"]
    assert d.clusters("sprite", "chr1", 300, 600)["n_clusters"] == 2                 # default: 2 fragments or more
    assert d.clusters("sprite", "chr1", 300, 600, max_size=3)["n_clusters"] == 1
    # beyond the limit: the clusters with the most fragments in the window
    lim = d.clusters("sprite", "chr1", 0, 1000, min_size=1, limit=1)
    assert lim["n_clusters"] == 3 and [c["id"] for c in lim["clusters"]] == [w["clusters"][0]["id"]]
    assert d.clusters("sprite", "chr1", 2000, 3000)["clusters"] == []
    with pytest.raises(ValueError):
        d.clusters("sprite", "*", 0, 10)
    with pytest.raises(KeyError):
        d.clusters("nope", "chr1", 0, 10)
