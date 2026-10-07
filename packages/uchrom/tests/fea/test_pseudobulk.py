"""uchrom.fea.pseudobulk: per-cell maps summed per group of cells, from a .scool and from embedded maps;
uchrom.io.pairs_maps: pairs files binned into a .scool."""

import gzip
import warnings

import numpy as np
import pandas as pd
import pytest

cooler = pytest.importorskip("cooler")

from chromdata import ChromData  # noqa: E402

from uchrom.fea import pseudobulk  # noqa: E402
from uchrom.io.pairs_maps import bin_pairs, genome_bins, pairs_to_scool  # noqa: E402

RES = 1000
SIZES = {"chrA": 40_500, "chrB": 23_000, "chrC": 9_000}


def _cell_pixels(rng, nb, chrom, n=400):
    """A sparse single-cell map: mostly cis contacts near the diagonal, some trans."""
    i = rng.integers(0, nb, n)
    j = np.clip(i + rng.geometric(0.2, n) - 1, 0, nb - 1)
    t = rng.random(n) < 0.15
    j[t] = rng.integers(0, nb, int(t.sum()))
    same = chrom[i] == chrom[j]
    j[~same & ~t] = i[~same & ~t]
    a, b = np.minimum(i, j), np.maximum(i, j)
    px = (pd.DataFrame({"bin1_id": a, "bin2_id": b, "count": rng.integers(1, 3, n)})
          .groupby(["bin1_id", "bin2_id"], as_index=False)["count"].sum())
    return px


def _dataset(tmp_path, n_cells=24, seed=0):
    rng = np.random.default_rng(seed)
    bins = genome_bins(SIZES, RES)
    chrom = bins["chrom"].to_numpy()
    names = [f"c{k:02d}" for k in range(n_cells)]
    maps = {c: _cell_pixels(rng, len(bins), chrom) for c in names}
    scool = tmp_path / "cells.scool"
    cooler.create_scool(str(scool), bins, maps, ordered=True, assembly="toy1")
    types = np.array(["T1", "T2", "T3"])[np.arange(n_cells) % 3]
    types[-1] = "T4"                                            # a group of one cell
    cells = pd.DataFrame({"cell_type": pd.Categorical(types, categories=["T2", "T1", "T3", "T4"])},
                         index=pd.Index(names, name="cell_id"))
    no_spots = pd.DataFrame({"chrom": pd.Series(dtype=str), "start": pd.Series(dtype=np.int64),
                             "end": pd.Series(dtype=np.int64), "trace_id": pd.Series(dtype=str),
                             "cell_id": pd.Series(dtype=str)})
    cd = ChromData(np.zeros((0, 3)), no_spots, cells=cells, uns={"genome_assembly": "toy1"})
    cd.link_scool(scool.name, key="per_cell", cell_name="cell_id", genome_assembly="toy1", bin_size=RES)
    store = tmp_path / "toy.chromdata.zarr"
    cd.write(store)
    return store, bins, maps, cells


def _expected(bins, maps, cells, res=RES, trans=True):
    """The pseudo-bulk of every group, summed directly (pandas), at ``res``."""
    chrom = bins["chrom"].to_numpy()
    coarse = genome_bins(SIZES, res)
    first = coarse.reset_index().groupby("chrom", sort=False)["index"].min()
    to_coarse = first[chrom].to_numpy() + bins["start"].to_numpy() // res
    out = {}
    for g, sub in cells.groupby("cell_type", observed=True):
        px = pd.concat([maps[c] for c in sub.index], ignore_index=True)
        if not trans:
            px = px[chrom[px["bin1_id"]] == chrom[px["bin2_id"]]]
        px = px.assign(bin1_id=to_coarse[px["bin1_id"]], bin2_id=to_coarse[px["bin2_id"]])
        out[str(g)] = px.groupby(["bin1_id", "bin2_id"], as_index=False)["count"].sum()
    return out


def _pixels(path):
    return cooler.Cooler(str(path)).pixels()[:][["bin1_id", "bin2_id", "count"]].reset_index(drop=True)


def _same(a, b):
    a = a.sort_values(["bin1_id", "bin2_id"]).reset_index(drop=True)
    b = b.sort_values(["bin1_id", "bin2_id"]).reset_index(drop=True)
    return np.array_equal(a.to_numpy(np.int64), b.to_numpy(np.int64))


@pytest.mark.parametrize("res", [RES, 5 * RES])
def test_pseudobulk_from_a_scool_sums_each_group(tmp_path, res):
    store, bins, maps, cells = _dataset(tmp_path)
    cd = ChromData.read(store)
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        summary = pseudobulk(cd, "cell_type", min_cells=2, resolution=res)
    assert any("T4 (1)" in str(x.message) for x in w)                 # one-cell group skipped
    assert list(summary["group"]) == ["T2", "T1", "T3"]               # category order
    want = _expected(bins, maps, cells, res)
    for row in summary.itertuples():
        assert _same(_pixels(row.path), want[row.group])
        assert row.n_contacts == int(want[row.group]["count"].sum())
        assert row.n_cells == int((cells["cell_type"] == row.group).sum())
        clr = cooler.Cooler(row.path)
        assert clr.binsize == res and "weight" in clr.bins().columns and row.balanced is not None
        rec = cd.uns["linked_cool"][row.key]
        assert rec["group"] == row.group and rec["n_cells"] == row.n_cells and rec["bin_size"] == res
        # next to the store, linked by a relative path
        assert not rec["path"].startswith("/") and cd.linked_cool_path(row.key) == row.path
    assert str(tmp_path / "toy_pseudobulk") in summary["path"].iloc[0]
    assert cd.results.record("pseudobulk").function == "uchrom.fea.pseudobulk"


def test_pseudobulk_from_embedded_maps_matches_the_scool(tmp_path):
    from chromdata.embedded import embed_links

    store, bins, maps, cells = _dataset(tmp_path)
    embed_links(str(store), verbose=False)
    (tmp_path / "cells.scool").rename(tmp_path / "moved.scool")       # only the embedded copy is left
    cd = ChromData.read(store, backed=True)
    out = tmp_path / "out"
    summary = pseudobulk(cd, "cell_type", out_dir=out, max_pixels=150)  # several blocks per partition
    want = _expected(bins, maps, cells)
    assert set(summary["group"]) == {"T1", "T2", "T3", "T4"}
    for row in summary.itertuples():
        assert _same(_pixels(row.path), want[row.group])
        assert row.path.startswith(str(out))
    # cis only, and the sum over all cells (groupby=None) equals the store's all-cells sum
    total = pseudobulk(cd, None, trans=False, out_dir=out, key_prefix="pb")
    assert list(total["key"]) == ["pb.all"]
    from chromdata.embedded import EmbeddedContacts, list_embedded

    e = EmbeddedContacts(str(store), list_embedded(str(store))["per_cell"])
    px = _pixels(total["path"].iloc[0])
    for c in SIZES:
        s = e.sum_pixels(f"cis/{c}")
        f0 = e.first_bin(c)
        ref = pd.DataFrame({"bin1_id": s[:, 0] + f0, "bin2_id": s[:, 1] + f0, "count": s[:, 2]})
        sel = (px["bin1_id"] >= f0) & (px["bin1_id"] < f0 + len(bins[bins["chrom"] == c]))
        assert _same(px[sel], ref)


def test_pseudobulk_reuses_maps_and_takes_a_mapping(tmp_path):
    store, bins, maps, cells = _dataset(tmp_path)
    cd = ChromData.read(store)
    lab = {c: ("even" if k % 2 == 0 else "odd") for k, c in enumerate(cells.index)}
    first = pseudobulk(cd, lab, cells=list(cells.index[:10]), groups=["odd"], out_dir=tmp_path / "o")
    assert list(first["group"]) == ["odd"] and first["n_cells"].iloc[0] == 5 and not first["reused"].iloc[0]
    again = pseudobulk(cd, lab, cells=list(cells.index[:10]), groups=["odd"], out_dir=tmp_path / "o")
    assert again["reused"].iloc[0] and again["n_contacts"].iloc[0] == first["n_contacts"].iloc[0]
    other = pseudobulk(cd, lab, cells=list(cells.index[:12]), groups=["odd"], out_dir=tmp_path / "o")
    assert not other["reused"].iloc[0] and other["n_cells"].iloc[0] == 6     # other cells: recomputed
    cd2 = pseudobulk(cd, "cell_type", groups=["T1"], out_dir=tmp_path / "o", copy=True)
    assert "pseudobulk.T1" in cd2.uns["linked_cool"] and "pseudobulk.T1" not in cd.uns["linked_cool"]
    with pytest.raises(ValueError, match="not a multiple"):
        pseudobulk(cd, "cell_type", resolution=1500)
    with pytest.raises(KeyError, match="not a column"):
        pseudobulk(cd, "nope")


def test_pseudobulk_of_an_in_memory_object_goes_to_a_scratch_dir(tmp_path):
    store, bins, maps, cells = _dataset(tmp_path)
    cd = ChromData.read(store)
    cd2 = ChromData(np.zeros((0, 3)), cd.spots, cells=cd.cells, uns=dict(cd.uns))
    with pytest.raises(FileNotFoundError, match="not embedded"):
        pseudobulk(cd2, "cell_type")                                  # relative link, no store: unresolvable
    summary = pseudobulk(cd2, "cell_type", contacts=str(tmp_path / "cells.scool"), groups=["T1"])
    assert str(tmp_path) not in summary["path"].iloc[0]
    assert cd2.uns["linked_cool"]["pseudobulk.T1"]["path"].startswith("/")


def _write_pairs(path, rows, header=True):
    opener = gzip.open if str(path).endswith(".gz") else open
    with opener(path, "wt") as fh:
        if header:
            fh.write("## pairs format v1.0\n#columns: readID chr1 pos1 chr2 pos2 strand1 strand2 phase0 phase1\n")
        for k, (c1, p1, c2, p2) in enumerate(rows):
            fh.write(f"r{k}\t{c1}\t{p1}\t{c2}\t{p2}\t+\t-\t0\t.\n")


def test_bin_pairs_counts_each_contact_once_and_matches_chromosome_names(tmp_path):
    rows = [("A", 1, "A", 1000), ("A", 1000, "A", 1), ("chrA", 1001, "A", 2500),   # 1-based: 1000 -> bin 0
            ("A", 5, "B", 7), ("B", 3, "A", 2001), ("M", 1, "A", 5), ("A", 40_501, "A", 1)]
    _write_pairs(tmp_path / "c.pairs.gz", rows)
    sizes = {"chrA": 40_500, "chrB": 23_000}
    px, st = bin_pairs(tmp_path / "c.pairs.gz", sizes, 1000)
    nA = 41
    assert st["n_lines"] == 7 and st["n_dropped"] == 2 and st["n_contacts"] == 5
    assert st["n_cis"] == 3 and st["n_trans"] == 2
    got = {(int(a), int(b)): int(c) for a, b, c in px.to_numpy()}
    assert got == {(0, 0): 2, (1, 2): 1, (0, nA + 0): 1, (2, nA + 0): 1}
    # Dip-C .con: legs "chrom,pos,hap"
    with gzip.open(tmp_path / "c.con.txt.gz", "wt") as fh:
        fh.write("A,1,0\tA,1000,1\nA,5,.\tB,7,0\n")
    px2, st2 = bin_pairs(tmp_path / "c.con.txt.gz", sizes, 1000)
    assert st2["n_contacts"] == 2 and {(int(a), int(b)) for a, b, _ in px2.to_numpy()} == {(0, 0), (0, nA)}


def test_pairs_to_scool_writes_every_cell(tmp_path):
    rng = np.random.default_rng(3)
    sizes = {"chr1": 30_000, "chr2": 12_000}
    cells = {}
    for k in range(3):
        rows = [(f"chr{rng.integers(1, 3)}", int(rng.integers(1, 12_000)), f"chr{rng.integers(1, 3)}",
                 int(rng.integers(1, 12_000))) for _ in range(200)]
        _write_pairs(tmp_path / f"cell{k}.pairs", rows)
        cells[f"cell{k}"] = tmp_path / f"cell{k}.pairs"
    stats = pairs_to_scool(cells, tmp_path / "x.scool", chromsizes=sizes, resolution=2000, assembly="toy")
    assert list(stats.index) == ["cell0", "cell1", "cell2"] and (stats["n_contacts"] == 200).all()
    names = cooler.fileops.list_scool_cells(str(tmp_path / "x.scool"))
    assert sorted(n.rsplit("/", 1)[-1] for n in names) == ["cell0", "cell1", "cell2"]
    clr = cooler.Cooler(f"{tmp_path / 'x.scool'}::/cells/cell1")
    assert clr.binsize == 2000 and int(clr.pixels()[:]["count"].sum()) == 200


@pytest.mark.parametrize("embedded", [False, True])
def test_pseudobulk_sparse_sums_and_concurrent_reads_are_exact(tmp_path, monkeypatch, embedded):
    import uchrom.fea.pseudobulk_maps as pb

    store, bins, maps, cells = _dataset(tmp_path, n_cells=40, seed=4)
    if embedded:
        from chromdata.embedded import embed_links

        embed_links(str(store), verbose=False)
        (tmp_path / "cells.scool").unlink()
    monkeypatch.setattr(pb, "DENSE_MAX", 0)              # every accumulator sparse ...
    monkeypatch.setattr(pb, "FLUSH_MIN", 50)             # ... folding small buffers many times
    cd = ChromData.read(store, backed=embedded)
    summary = pb.pseudobulk(cd, "cell_type", out_dir=tmp_path / "o", max_pixels=200, workers=3,
                            resolution=2 * RES)
    want = _expected(bins, maps, cells, 2 * RES)
    for row in summary.itertuples():
        assert _same(_pixels(row.path), want[row.group])


def test_default_folders(tmp_path, monkeypatch):
    from uchrom.fea.pseudobulk_maps import _default_out_dir

    class Remote:
        def _links_from(self):
            return "https://example.org/atlas/dschic_aging_cortex.chromdata.zarr"

    class Local:
        def _links_from(self):
            return str(tmp_path / "x" / "kim2020.chromdata.zarr")

    monkeypatch.setenv("UCHROM_DATA", str(tmp_path / "data"))
    assert _default_out_dir(Remote()) == (tmp_path / "data" / "pseudobulk" / "dschic_aging_cortex", True)
    assert _default_out_dir(Local()) == ((tmp_path / "x").resolve() / "kim2020_pseudobulk", True)


@pytest.mark.parametrize("trans", [True, False])
def test_ice_matches_cooler_balance(tmp_path, trans):
    store, bins, maps, cells = _dataset(tmp_path, n_cells=60, seed=7)
    cd = ChromData.read(store)
    summary = pseudobulk(cd, "cell_type", groups=["T1", "T2"], trans=trans, out_dir=tmp_path / "o")
    for path in summary["path"]:
        clr = cooler.Cooler(path)
        ours = clr.bins()[:]["weight"].to_numpy()
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            ref, stats = cooler.balance_cooler(clr, cis_only=not trans)
        assert np.isfinite(ours).sum() > 20
        assert np.array_equal(np.isfinite(ours), np.isfinite(ref))
        ok = np.isfinite(ref)
        assert np.allclose(ours[ok], ref[ok], rtol=1e-9, atol=0)
        with clr.open("r") as h5:
            attrs = dict(h5["bins/weight"].attrs)
        assert set(attrs) == set(stats) and np.allclose(attrs["scale"], stats["scale"], equal_nan=True)
