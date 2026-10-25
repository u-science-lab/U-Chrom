"""Multi-way contacts (``ChromData.clusters``, format 2.4): the CSR table, the locus index and region queries,
storage (zarr, cdz, backed, HTTP), adding to an existing store and the streaming writer."""

import json

import numpy as np
import pandas as pd
import pytest

from chromdata import ChromData, ClusterTable
from chromdata.clusters import CHUNK, add_clusters
from chromdata.testing import example_chromdata, serve_directory

CHROMS = ["chr1", "chr2", "chrX"]
CELLS = ["c0", "c1", "c2", "c3"]
CONTEXT = ["cluster", "start", "end", "size", "chrom_size", "span_start", "span_end"]


def fragments(n_clusters=3000, seed=0, cells=CELLS):
    """Random clusters: 1-11 fragments around a home locus, mostly on one chromosome, 1 % long fragments."""
    rng = np.random.default_rng(seed)
    sizes = rng.integers(1, 12, n_clusters)
    cl = np.repeat(np.arange(n_clusters), sizes)
    n = len(cl)
    home = rng.integers(0, len(CHROMS), n_clusters)[cl]
    chrom = np.where(rng.random(n) < 0.8, home, rng.integers(0, len(CHROMS), n))
    centre = rng.integers(0, 5_000_000, n_clusters)[cl]
    start = np.clip(centre + rng.normal(0, 3e5, n).astype(np.int64), 0, None)
    length = np.where(rng.random(n) < 0.01, rng.integers(10_000, 60_000, n), rng.integers(20, 3000, n))
    labels = np.array([f"bc{i:06d}" for i in rng.permutation(n_clusters)])
    out = pd.DataFrame({"barcode": labels[cl], "chrom": np.asarray(CHROMS)[chrom], "start": start,
                        "end": start + length, "mapq": rng.integers(0, 60, n).astype(np.uint8)})
    if cells is not None:
        out["cell"] = np.asarray(cells)[rng.integers(0, len(cells), n_clusters)][cl]
    return out


def brute_region(frame, chrom, start, end):
    """Fragments of ``frame`` (a ``to_frame()``) overlapping the window, with their clusters' context."""
    ctx = (frame.groupby(["cluster", "chrom"], observed=True)
           .agg(chrom_size=("start", "size"), span_start=("start", "min"), span_end=("end", "max")).reset_index())
    size = frame.groupby("cluster").size().rename("size").reset_index()
    hit = frame[(frame["chrom"].astype(str) == chrom) & (frame["start"] < end) & (frame["end"] > start)]
    hit = hit.merge(ctx, on=["cluster", "chrom"]).merge(size, on="cluster")
    return hit.sort_values(["start", "end", "cluster"]).reset_index(drop=True)


def assert_same_table(a: ClusterTable, b: ClusterTable):
    assert a.chroms == b.chroms and a.kind == b.kind
    np.testing.assert_array_equal(a.member_offsets, b.member_offsets)
    np.testing.assert_array_equal(a.members_array.astype(np.int64), b.members_array.astype(np.int64))
    if a.cells is not None:
        assert list(a.cells) == list(b.cells)
        np.testing.assert_array_equal(a.cell_offsets, b.cell_offsets)
    assert sorted(a.member_columns) == sorted(b.member_columns)
    for k in a.member_columns:
        np.testing.assert_array_equal(np.asarray(a.member_columns[k][:]), np.asarray(b.member_columns[k][:]))


@pytest.fixture(scope="module")
def table():
    return ClusterTable.from_frame(fragments(), cluster="barcode", cell="cell", member_columns=["mapq"],
                                   attrs={"assay": "test"})


# ----------------------------------------------------------------------------- the table

def test_from_frame_is_sorted_csr(table):
    t = table
    off, mem = t.member_offsets, t.members_array.astype(np.int64)
    assert off[0] == 0 and off[-1] == mem.shape[1] == t.n_members and (np.diff(off) > 0).all()
    co = t.cell_offsets
    assert list(t.cells) == CELLS and co[0] == 0 and co[-1] == t.n_clusters
    first = off[:-1]
    key = np.stack([t.cell_codes(np.arange(t.n_clusters)), mem[0, first], mem[1, first], mem[2, first]])
    assert (np.diff(key[0]) >= 0).all()
    same_cell = np.diff(key[0]) == 0
    order = np.lexsort(key[::-1])
    np.testing.assert_array_equal(order, np.arange(t.n_clusters))       # clusters by (cell, first fragment)
    for k in range(0, t.n_clusters, 97):                                 # fragments by (chrom, start, end)
        block = mem[:, off[k]:off[k + 1]]
        np.testing.assert_array_equal(np.lexsort(block[::-1]), np.arange(block.shape[1]))
    assert same_cell.any()


def test_from_frame_keeps_every_fragment(table):
    src = fragments()
    got = table.to_frame()
    got["barcode"] = table.cluster_columns["name"].to_numpy()[got["cluster"]]
    cols = ["barcode", "chrom", "start", "end", "mapq"]
    a = src[cols + ["cell"]].assign(chrom=src["chrom"].astype(str)).sort_values(cols).reset_index(drop=True)
    b = (got.assign(chrom=got["chrom"].astype(str), cell=got["cell_id"].astype(str))[cols + ["cell"]]
         .sort_values(cols).reset_index(drop=True))
    pd.testing.assert_frame_equal(a, b, check_dtype=False)


def test_input_order_does_not_matter(table):
    shuffled = fragments().sample(frac=1, random_state=3)
    other = ClusterTable.from_frame(shuffled, cluster="barcode", cell="cell", member_columns=["mapq"])
    assert_same_table(table, other)
    assert table.cluster_columns["name"].tolist() == other.cluster_columns["name"].tolist()


def test_to_frame_round_trip(table):
    again = ClusterTable.from_frame(table.to_frame(), cell="cell_id", member_columns=["mapq"], keep_names=False)
    assert_same_table(table, again)


def test_members_and_cells(table):
    ids = np.array([5, 0, 2000, 17])
    m = table.members(ids)
    assert m["cluster"].drop_duplicates().tolist() == ids.tolist()
    full = table.to_frame()
    for k in ids:
        pd.testing.assert_frame_equal(m[m["cluster"] == k].reset_index(drop=True),
                                      full[full["cluster"] == k].reset_index(drop=True))
    c2 = table.get_cell("c2")
    r = table.cell_clusters("c2")
    assert c2["cluster"].min() == r.start and c2["cluster"].max() == r.stop - 1
    assert (c2["cell_id"] == "c2").all()
    sub = table.select_cells(["c3", "c1"])
    assert list(sub.cells) == ["c1", "c3"]
    assert sub.n_clusters == len(table.cell_clusters("c1")) + len(table.cell_clusters("c3"))
    pd.testing.assert_frame_equal(sub.get_cell("c3").drop(columns="cluster"),
                                  table.get_cell("c3").drop(columns="cluster"), check_categorical=False)
    with pytest.raises(KeyError):
        table.get_cell("nope")


# ----------------------------------------------------------------------------- region queries

def _windows(seed=0, n=60):
    rng = np.random.default_rng(seed)
    out = [("chr1", 0, 10), ("chr2", 2_000_000, 2_000_001), ("chrX", 0, 10 ** 9), ("chrY", 0, 10 ** 6),
           ("chr1", 500, 500)]
    for _ in range(n):
        s = int(rng.integers(0, 5_500_000))
        out.append((CHROMS[rng.integers(0, 3)], s, s + int(rng.choice([1, 300, 5_000, 40_000, 400_000, 2_000_000]))))
    return out


def _check_regions(t: ClusterTable, frame: pd.DataFrame, windows):
    for chrom, s, e in windows:
        got = t.region(chrom, s, e)
        want = brute_region(frame, chrom, s, e) if e > s else frame.iloc[:0]
        assert len(got) == len(want), (chrom, s, e)
        if len(want):
            np.testing.assert_array_equal(got[CONTEXT].to_numpy(), want[CONTEXT].to_numpy().astype(np.int64))
            if t.cells is not None:
                assert got["cell_id"].astype(str).tolist() == want["cell_id"].astype(str).tolist()


def test_region_matches_brute_force(table):
    frame = table.to_frame()
    windows = _windows()
    # a window that starts where a fragment ends must not return it (end-exclusive)
    f0 = frame[frame["chrom"] == "chr2"].iloc[0]
    windows += [("chr2", int(f0["end"]), int(f0["end"]) + 1), ("chr2", int(f0["start"]) - 5, int(f0["start"]) + 1)]
    _check_regions(table, frame, windows)


@pytest.fixture(scope="module")
def big_store(tmp_path_factory):
    """A store whose chromosomes hold several locus chunks each."""
    t = ClusterTable.from_frame(fragments(n_clusters=25_000, seed=7), cluster="barcode", cell="cell",
                                member_columns=["mapq"])
    cd = example_chromdata()
    cd.clusters["sprite"] = t
    path = tmp_path_factory.mktemp("big") / "big.chromdata.zarr"
    cd.write(path)
    return t, path


def test_backed_region_matches(big_store):
    t, path = big_store
    frame = t.to_frame()
    assert (frame["chrom"] == "chr1").sum() > 2 * CHUNK
    b = ChromData.read(path, backed=True).clusters["sprite"]
    assert b.backed and b.n_clusters == t.n_clusters
    _check_regions(b, frame, _windows(seed=1))
    for chrom, s, e in _windows(seed=2, n=20):
        pd.testing.assert_frame_equal(b.region(chrom, s, e, min_size=3, max_size=8, cells=["c1", "c2"]),
                                      t.region(chrom, s, e, min_size=3, max_size=8, cells=["c1", "c2"]))


def test_region_filters(table):
    r = table.region("chr1", 0, 6_000_000, min_size=4, max_size=6, cells=["c0", "c3"])
    assert len(r) and r["size"].between(4, 6).all() and set(r["cell_id"].astype(str)) <= {"c0", "c3"}
    full = table.region("chr1", 0, 6_000_000)
    keep = full["size"].between(4, 6) & full["cell_id"].astype(str).isin(["c0", "c3"])
    pd.testing.assert_frame_equal(r, full[keep].reset_index(drop=True))
    trans = full[full["size"] > full["chrom_size"]]
    assert len(trans)                                   # clusters with fragments on other chromosomes


# ----------------------------------------------------------------------------- storage

@pytest.mark.parametrize("suffix", [".chromdata.zarr", ".cdz"])
def test_store_round_trip(tmp_path, table, suffix):
    cd = example_chromdata()
    cd.clusters["sprite"] = table
    cd.set_clusters("bulk", fragments(400, seed=5, cells=None), cluster="barcode")
    path = tmp_path / f"x{suffix}"
    cd.write(path)
    mem = ChromData.read(path)
    assert set(mem.clusters) == {"sprite", "bulk"} and not mem.clusters["sprite"].backed
    assert_same_table(table, mem.clusters["sprite"])
    assert mem.clusters["sprite"].attrs == {"assay": "test"}
    assert mem.clusters["sprite"].cluster_columns["name"].tolist() == table.cluster_columns["name"].tolist()
    assert mem.clusters["bulk"].kind == "bulk" and "cell_id" not in mem.clusters["bulk"].region("chr1", 0, 10 ** 7)
    b = ChromData.read(path, backed=True)
    bt = b.clusters["sprite"]
    assert bt.backed and repr(bt).endswith("backed)")
    assert b._c.meta["format_version"] == "2.4"
    ids = np.array([3, 2999, 1500, 4, 1501])
    pd.testing.assert_frame_equal(bt.members(ids), table.members(ids))
    pd.testing.assert_frame_equal(bt.get_cell("c1"), table.get_cell("c1"))
    assert_same_table(table, bt.select_cells(CELLS))
    assert bt.cluster_columns["name"].tolist() == table.cluster_columns["name"].tolist()
    # spots round-trip as before; the clusters ride along with subsets and copies
    sub = b.get_cell("c1")
    assert sub.clusters["sprite"] is bt
    assert mem[:5].clusters["sprite"] is mem.clusters["sprite"]
    cp = mem.copy()
    assert cp.clusters["sprite"] is not mem.clusters["sprite"]
    assert_same_table(cp.clusters["sprite"], mem.clusters["sprite"])
    assert "clusters: {'sprite': 3000, 'bulk': 400}" in repr(mem)


def test_rewrite_and_older_layouts(tmp_path, table):
    cd = example_chromdata()
    cd.clusters["sprite"] = table
    path = tmp_path / "a.chromdata.zarr"
    cd.write(path)
    b = ChromData.read(path, backed=True)
    b.write(tmp_path / "b.chromdata.zarr")             # a backed object writes its tables (read on the way)
    assert_same_table(table, ChromData.read(tmp_path / "b.chromdata.zarr").clusters["sprite"])
    from chromdata.zarrcd import write_zarr

    with pytest.raises(ValueError, match="2.4"):
        write_zarr(cd, tmp_path / "old.chromdata.zarr", _layout="2.1")


def test_over_http(big_store):
    pytest.importorskip("aiohttp")
    from chromdata.testing import RangeRequestHandler

    t, path = big_store
    with serve_directory(path.parent) as base:
        b = ChromData.read(f"{base}/{path.name}", backed=True)
        bt = b.clusters["sprite"]
        RangeRequestHandler.log.clear()
        got = bt.region("chr2", 1_000_000, 1_040_000)
        pd.testing.assert_frame_equal(got, t.region("chr2", 1_000_000, 1_040_000))
        touched = {p for p, _, _ in RangeRequestHandler.log}
        assert touched and all("/by_locus/" in p for p in touched)    # the window reads the locus index only
        pd.testing.assert_frame_equal(bt.get_cell("c0"), t.get_cell("c0"))


@pytest.mark.parametrize("chunk", [1000, 4096])
def test_locus_layout_is_read_as_written(tmp_path, chunk):
    """Another locus chunk size or codec: readers follow the attrs and the array metadata."""
    import zarr

    t = ClusterTable.from_frame(fragments(n_clusters=8000, seed=11), cluster="barcode", cell="cell")
    path = tmp_path / "s.chromdata.zarr"
    example_chromdata().write(path)
    codec = zarr.codecs.BloscCodec(cname="zstd", clevel=5, shuffle="bitshuffle")
    add_clusters(path, "x", t, locus_chunk=chunk, locus_compressor=codec)
    b = ChromData.read(path, backed=True).clusters["x"]
    assert b._meta["locus_chunk"] == chunk
    _check_regions(b, t.to_frame(), _windows(seed=4, n=25))


def test_search_does_not_cast_the_index():
    from chromdata.clusters import _search

    s = np.array([5, 5, 9, 4_000_000_000], dtype=np.uint32)
    assert [_search(s, v, side) for v, side in [(-3, "right"), (5, "right"), (5, "left"), (9, "left"),
                                                 (2 ** 40, "left"), (4_000_000_000, "right")]] == [0, 2, 0, 2, 4, 4]


def test_add_clusters_to_a_store(tmp_path, table):
    cd = example_chromdata()
    path = tmp_path / "s.chromdata.zarr"
    cd.write(path)
    meta = json.loads((path / "zarr.json").read_text())
    attrs = meta["attributes"]
    attrs["uchrom"]["format_version"] = attrs["uchrom_format_version"] = "2.3"     # an older store
    (path / "zarr.json").write_text(json.dumps(meta))
    add_clusters(path, "sprite", table)
    b = ChromData.read(path, backed=True)
    assert b._c.meta["format_version"] == "2.4"
    assert_same_table(table, b.clusters["sprite"])
    with pytest.raises(FileExistsError):
        add_clusters(path, "sprite", table)
    small = table.select_cells(["c0"])
    add_clusters(path, "sprite", small, overwrite=True)
    add_clusters(path, "other one", table)
    back = ChromData.read(path)
    assert back.clusters["sprite"].n_clusters == small.n_clusters
    assert_same_table(table, back.clusters["other one"])
    np.testing.assert_array_equal(back.coords.shape, ChromData.read(path, backed=True).coords.shape)
    cd.write(tmp_path / "s.cdz")
    with pytest.raises(ValueError, match="directory"):
        add_clusters(tmp_path / "s.cdz", "x", table)


def test_streaming_writer_keeps_clusters(tmp_path, table):
    cd = example_chromdata()
    cd.clusters["sprite"] = table
    src = tmp_path / "src.chromdata.zarr"
    cd.write(src)
    b = ChromData.read(src, backed=True)
    w = ChromData.writer(tmp_path / "out.chromdata.zarr")
    for chunk in b.iter_cells(1):
        w.append(chunk)
    w.finish()
    assert_same_table(table, ChromData.read(tmp_path / "out.chromdata.zarr").clusters["sprite"])


# ----------------------------------------------------------------------------- input checks

def test_bad_input():
    good = pd.DataFrame({"cluster": [0, 0, 1], "chrom": ["chr1"] * 3, "start": [0, 10, 5], "end": [5, 20, 9],
                         "cell": ["a", "a", "b"]})
    with pytest.raises(ValueError, match="one cell"):
        ClusterTable.from_frame(good.assign(cell=["a", "b", "b"]), cell="cell")
    with pytest.raises(ValueError, match="end > start"):
        ClusterTable.from_frame(good.assign(end=[5, 10, 9]))
    with pytest.raises(ValueError, match="chromosomes"):
        ClusterTable.from_frame(good, chroms=["chr2"])
    with pytest.raises(ValueError, match="cells"):
        ClusterTable.from_frame(good, cell="cell", cells=["a"])
    with pytest.raises(TypeError, match="numeric"):
        ClusterTable.from_frame(good.assign(tag="x"), member_columns=["tag"])
    with pytest.raises(TypeError, match="ClusterTable"):
        ChromData(np.zeros((0, 3)), example_chromdata().spots.iloc[:0], clusters={"x": good})


def test_empty_and_singletons(tmp_path):
    empty = ClusterTable.from_frame(pd.DataFrame({"cluster": [], "chrom": [], "start": [], "end": []}))
    assert empty.n_clusters == 0 and empty.region("chr1", 0, 100).empty
    one = ClusterTable.from_frame(pd.DataFrame({"cluster": ["r1"], "chrom": ["chr1"], "start": [3], "end": [9]}))
    cd = example_chromdata()
    cd.clusters.update({"empty": empty, "one": one})
    cd.write(tmp_path / "e.chromdata.zarr")
    back = ChromData.read(tmp_path / "e.chromdata.zarr", backed=True)
    assert back.clusters["empty"].n_clusters == 0
    r = back.clusters["one"].region("chr1", 0, 4)
    assert r[["start", "end", "size", "chrom_size"]].values.tolist() == [[3, 9, 1, 1]]


def test_set_clusters_uses_the_object_axes():
    cd = example_chromdata()
    df = fragments(200, seed=2, cells=["c3", "c0", "zz"])
    t = cd.set_clusters("sprite", df, cluster="barcode", cell="cell")
    assert t.chroms[:3] == [str(c) for c in cd.bins["chrom"].cat.categories]
    assert list(t.cells) == [str(c) for c in cd.cells.index] + ["zz"]
    with pytest.raises(ValueError):
        cd.set_clusters("a/b", t)
