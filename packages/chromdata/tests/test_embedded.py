"""Contact maps / AnnData / images embedded in a .chromdata.zarr (chromdata.embedded).

The web browser on embedded copies: uchrom-browser's tests/test_embedded_maps.py."""

import shutil
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

cooler = pytest.importorskip("cooler")
anndata = pytest.importorskip("anndata")

from chromdata import ChromData  # noqa: E402
from chromdata import embedded  # noqa: E402
from chromdata.testing import LINKED_BINS as N, LINKED_RES as RES, linked_store as _store  # noqa: E402

@pytest.fixture
def stores(tmp_path):
    linked, emb = _store(tmp_path)
    done = embedded.embed_links(emb, verbose=False, trans_min_resolution=RES)
    assert set(done) == {"bulk", "cells", "ssAB", "secA", "default"}
    return tmp_path, linked, emb


def test_pixels_are_exact(stores):
    tmp_path, _, emb = stores
    e = embedded.EmbeddedContacts(str(emb), embedded.list_embedded(str(emb))["cells"])
    assert e.kind == "per_cell" and e.cells == ["c0", "c1", "c2"] and e.resolutions == [RES]
    for k, name in enumerate(e.cells):
        px = cooler.Cooler(f"{tmp_path / 'cells.scool'}::/cells/{name}").pixels()[:]
        got = list(e.iter_pixels(cell_idx=[k]))
        ref = sorted(zip(px.bin1_id, px.bin2_id, px["count"]))
        out = sorted(zip(*(np.concatenate([g[j] for g in got]) for j in range(3))))
        assert ref == out
    b = embedded.EmbeddedContacts(str(emb), embedded.list_embedded(str(emb))["bulk"])
    assert b.resolutions == [RES, 2 * RES] and b.has_trans(RES) and b.has_trans(2 * RES)
    px = cooler.Cooler(f"{tmp_path / 'bulk.mcool'}::/resolutions/{RES}").pixels()[:]
    got = list(b.iter_pixels(RES))
    assert sorted(zip(px.bin1_id, px.bin2_id, px["count"])) == sorted(
        zip(*(np.concatenate([g[j] for g in got]) for j in range(3))))


def test_trans_only_from_the_minimum_resolution(tmp_path):
    linked, emb = _store(tmp_path)
    embedded.embed_cool(emb, "bulk", tmp_path / "bulk.mcool", trans_min_resolution=2 * RES)
    b = embedded.EmbeddedContacts(str(emb), "bulk")
    assert not b.has_trans(RES) and b.has_trans(2 * RES)
    px = cooler.Cooler(f"{tmp_path / 'bulk.mcool'}::/resolutions/{RES}").pixels()[:]
    px = px[px.bin1_id // N == px.bin2_id // N]
    got = list(b.iter_pixels(RES))
    assert sorted(zip(px.bin1_id, px.bin2_id, px["count"])) == sorted(
        zip(*(np.concatenate([g[j] for g in got]) for j in range(3))))


def test_overwrite_and_partial_dirs(stores):
    _, _, emb = stores
    with pytest.raises(FileExistsError):
        embedded.embed_scool(emb, "cells", emb.parent / "cells.scool")
    embedded.embed_scool(emb, "cells", emb.parent / "cells.scool", overwrite=True)
    assert not [p for p in (emb / "embedded" / "contacts").iterdir() if ".partial" in p.name]


def test_anndata_roundtrip(stores):
    tmp_path, _, emb = stores
    found = embedded.list_embedded_anndata(str(emb), "linked_bin_matrices")
    got = embedded.read_embedded_anndata(str(emb), found["ssAB"])
    ref = anndata.read_h5ad(tmp_path / "ssab.h5ad")
    np.testing.assert_array_equal(got.X, ref.X)
    assert list(got.obs_names) == list(ref.obs_names) and list(got.var["bin_id"]) == list(ref.var["bin_id"])


def test_store_still_reads_and_older_layout_unaffected(stores):
    _, linked, emb = stores
    cd = ChromData.read(str(emb), backed=True)
    assert cd.uns["linked_scool"]["path"] if "path" in cd.uns["linked_scool"] else cd.uns["linked_scool"]["cells"]["path"]
    assert embedded.list_embedded(str(linked)) == {}


def test_linked_scool_path_is_the_file_while_it_exists(stores):
    tmp_path, linked, _ = stores
    cd = ChromData.read(str(linked))
    assert Path(cd.linked_scool_path("cells")).resolve() == (tmp_path / "cells.scool").resolve()
    with pytest.raises(FileNotFoundError):
        (tmp_path / "cells.scool").unlink()
        cd.linked_scool_path("cells")                    # gone, and this store embeds nothing


def test_python_api_without_the_files(stores):
    tmp_path, _, emb = stores
    ref = {r: cooler.Cooler(f"{tmp_path / 'bulk.mcool'}::/resolutions/{r}").pixels()[:] for r in (RES, 2 * RES)}
    ref_cell = cooler.Cooler(f"{tmp_path / 'cells.scool'}::/cells/c1").pixels()[:]
    for f in ("bulk.mcool", "bulk.cool", "cells.scool", "ssab.h5ad", "sec.png"):
        (tmp_path / f).unlink()
    cd = ChromData.read(str(emb), backed=True)
    assert set(cd.embedded_links()["contacts"]) == {"bulk", "cells"}
    assert cd.validate_links() == [m for m in cd.validate_links() if "does not exist" not in m]
    # a bulk map: an mcool exported from the embedded copy, same pixels
    path = cd.linked_cool_path("bulk")
    for r, px in ref.items():
        got = cooler.Cooler(f"{path}::/resolutions/{r}").pixels()[:]
        assert sorted(zip(got.bin1_id, got.bin2_id, got["count"])) == sorted(zip(px.bin1_id, px.bin2_id, px["count"]))
    # one cell of a per-cell map, and the cell list
    assert cd.load_linked_scool(key="cells")["cells"] == ["/cells/c0", "/cells/c1", "/cells/c2"]
    got = cd.load_linked_scool(key="cells", cell="c1").pixels()[:]
    assert sorted(zip(got.bin1_id, got.bin2_id, got["count"])) == sorted(zip(ref_cell.bin1_id, ref_cell.bin2_id, ref_cell["count"]))
    # the per-cell map as a file: some cells exported from the embedded copy, same pixels
    path = cd.linked_scool_path("cells", cells=["c1"])
    assert cooler.fileops.list_scool_cells(path) == ["/cells/c1"]
    got = cooler.Cooler(f"{path}::/cells/c1").pixels()[:]
    assert sorted(zip(got.bin1_id, got.bin2_id, got["count"])) == sorted(zip(ref_cell.bin1_id, ref_cell.bin2_id, ref_cell["count"]))
    assert cd.linked_scool_path("cells", cells=["c1"]) == path            # exported once
    # a subset or a copy reads its parent's links and embedded copies
    assert cd[:2].linked_scool_path("cells", cells=["c1"]) == path
    assert cd.to_memory()[:2].linked_scool_path("cells", cells=["c1"]) == path
    assert cd.to_memory().copy().linked_cool_path("bulk") == cd.linked_cool_path("bulk")
    # linked_adata falls back to the embedded AnnData
    assert cd.linked_adata is not None and cd.linked_adata.shape == (3, 2 * N)


def test_export_roundtrip(stores):
    tmp_path, _, emb = stores
    out = embedded.export_scool(str(emb), "cells", tmp_path / "again.scool")
    for c in ("c0", "c1", "c2"):
        a = cooler.Cooler(f"{out}::/cells/{c}").pixels()[:]
        b = cooler.Cooler(f"{tmp_path / 'cells.scool'}::/cells/{c}").pixels()[:]
        assert sorted(zip(a.bin1_id, a.bin2_id, a["count"])) == sorted(zip(b.bin1_id, b.bin2_id, b["count"]))
    # a subset of the cells, in the order given; cis contacts only
    sub = embedded.export_scool(str(emb), "cells", tmp_path / "sub.scool", cells=["c2", "c0"], trans=False)
    for c in ("c2", "c0"):
        a = cooler.Cooler(f"{sub}::/cells/{c}")
        b = cooler.Cooler(f"{tmp_path / 'cells.scool'}::/cells/{c}")
        chrom = b.bins()[:]["chrom"].to_numpy()
        px = b.pixels()[:]
        cis = px[chrom[px.bin1_id] == chrom[px.bin2_id]]
        assert len(cis) < len(px)                       # the fixture has trans contacts
        assert sorted(zip(a.pixels()[:].bin1_id, a.pixels()[:].bin2_id, a.pixels()[:]["count"])) == \
            sorted(zip(cis.bin1_id, cis.bin2_id, cis["count"]))
    assert sorted(cooler.fileops.list_scool_cells(str(sub))) == ["/cells/c0", "/cells/c2"]
    with pytest.raises(KeyError):
        embedded.export_scool(str(emb), "cells", tmp_path / "x.scool", cells=["nope"])
    one = embedded.export_cool(str(emb), "bulk", tmp_path / "r.cool", resolution=2 * RES)
    assert cooler.Cooler(str(one)).binsize == 2 * RES
    with pytest.raises(ValueError):
        embedded.export_cool(str(emb), "cells", tmp_path / "x.cool")


def test_rewriting_the_same_store_keeps_the_embedded_copies(stores):
    tmp_path, _, emb = stores
    cd = ChromData.read(str(emb))                       # in memory, read from emb
    cd.cells["note"] = "x"
    cd.write(emb)                                       # same store: embedded/ survives
    assert set(embedded.list_embedded(str(emb))) == {"bulk", "cells"}
    assert ChromData.read(str(emb), backed=True).cells["note"].iloc[0] == "x"
    assert len(embedded.EmbeddedContacts(str(emb), embedded.list_embedded(str(emb))["cells"]).cell_pixels("cis/chr1", [0])) > 0
    other = ChromData.read(str(tmp_path / "linked.chromdata.zarr"))
    other.write(emb)                                    # another object over the store: nothing inherited
    assert embedded.list_embedded(str(emb)) == {}


def test_pixel_blocks_equal_the_whole_read_and_stay_small(stores):
    _, _, emb = stores
    e = embedded.EmbeddedContacts(str(emb), embedded.list_embedded(str(emb))["cells"])
    whole = e.cell_pixels("cis/chr1", [0, 1, 2])
    blocks = list(e.cell_pixel_blocks("cis/chr1", [0, 1, 2], max_pixels=5))
    assert len(blocks) > 1 and all(len(b) <= max(5, 40) for b in blocks)     # a cell bigger than the budget is a block of its own
    np.testing.assert_array_equal(np.concatenate(blocks), whole)
    full = [np.column_stack(b) for b in e.iter_pixels(cell_idx=[0, 1, 2])]
    small = [np.column_stack(b) for b in e.iter_pixels(cell_idx=[0, 1, 2], max_pixels=7)]
    assert sorted(map(tuple, np.concatenate(full))) == sorted(map(tuple, np.concatenate(small)))


def test_upgrade_makes_an_old_store_cheap_to_open(stores):
    """A store embedded before chromsizes / uchrom_var / the consolidated root existed: --upgrade adds them."""
    import zarr

    _, _, emb = stores
    for name in embedded.list_embedded(str(emb)).values():              # strip what newer embeds write
        g = zarr.open_group(str(emb), path=f"embedded/contacts/{name}", mode="r+", zarr_format=3, use_consolidated=False)
        meta = dict(g.attrs["uchrom_contacts"]); meta.pop("chromsizes"); g.attrs["uchrom_contacts"] = meta
    g = zarr.open_group(str(emb), path="embedded/anndata/ssAB", mode="r+", zarr_format=3, use_consolidated=False)
    del g.attrs["uchrom_var"]
    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        for sub in [f"embedded/contacts/{n}" for n in embedded.list_embedded(str(emb)).values()] + ["embedded/anndata/ssAB"]:
            zarr.consolidate_metadata(str(emb), path=sub)       # each group as an earlier embed left it
    embedded.consolidate_sections(emb)
    assert not embedded.open_all(str(emb))["bulk"].meta.get("chromsizes")
    done = embedded.upgrade_store(emb)
    assert set(done["chromsizes"]) == {"bulk", "cells"} and done["var"] == ["ssAB"] and done["root_consolidated"]
    maps = embedded.open_all(str(emb))
    assert maps["bulk"].meta["chromsizes"] == {"chr1": N * RES, "chr2": N * RES}
    var = embedded.bin_matrix_var(embedded.open_anndata_groups(str(emb), "linked_bin_matrices")["ssAB"][0])
    assert list(var["bin_id"]) == list(range(2 * N)) and set(var["resolution"]) == {RES}
    assert set(embedded.open_all(str(emb))) == {"bulk", "cells"}       # still reads, and now from the consolidated root
    assert upgrade_twice(emb) == {"chromsizes": [], "sum": [], "var": [], "root_consolidated": True}


def upgrade_twice(emb):
    return embedded.upgrade_store(emb)


def test_embedded_maps_need_no_cooler(stores, monkeypatch):
    """A sandboxed server cannot import cooler (multiprocessing semaphores): reading embedded maps must not need it."""
    import sys

    _, _, emb = stores
    monkeypatch.setitem(sys.modules, "cooler", None)            # `import cooler` now raises ImportError
    monkeypatch.setitem(sys.modules, "h5py", None)
    assert set(embedded.open_all(str(emb))) == {"bulk", "cells"}
    e = embedded.EmbeddedContacts(str(emb), embedded.list_embedded(str(emb))["cells"])
    assert len(e.cell_pixels("cis/chr1", [0, 1, 2])) > 0
    assert set(embedded.list_embedded_images(str(emb))) == {"secA"}


def test_all_cells_sums_and_their_upgrade(stores):
    """Per-cell maps carry 'all spots' sums; a store embedded before they existed gets them from upgrade_store."""
    import shutil
    import warnings

    import zarr

    _, _, emb = stores
    name = embedded.list_embedded(str(emb))["cells"]
    e = embedded.EmbeddedContacts(str(emb), name)
    assert e.has_sum() and e.meta["has_sum"]
    for part in [p for p in (emb / "embedded" / "contacts" / name).rglob(embedded.SUM) if p.is_dir()]:
        shutil.rmtree(part)
    g = zarr.open_group(str(emb), path=f"embedded/contacts/{name}", mode="r+", zarr_format=3, use_consolidated=False)
    meta = dict(g.attrs["uchrom_contacts"]); meta.pop("has_sum"); g.attrs["uchrom_contacts"] = meta
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        zarr.consolidate_metadata(str(emb), path=f"embedded/contacts/{name}")
    embedded.consolidate_sections(emb)
    assert not embedded.EmbeddedContacts(str(emb), name).has_sum()
    assert embedded.upgrade_store(emb)["sum"] == ["cells"]
    assert embedded.EmbeddedContacts(str(emb), name).has_sum()


def test_a_cdz_of_the_store_carries_the_embedded_copies(stores):
    """The atlas download: the embedded store zipped as one .cdz reads like the directory, without the files."""
    from chromdata.zarrcd import _zip_tree

    tmp_path, _, emb = stores
    cdz = tmp_path / "emb.cdz"
    _zip_tree(emb, cdz)
    for f in ("bulk.mcool", "bulk.cool", "cells.scool", "ssab.h5ad"):
        (tmp_path / f).unlink()
    cd = ChromData.read(cdz, backed=True)
    assert set(cd.embedded_links()["contacts"]) == {"bulk", "cells"}
    assert set(embedded.list_embedded_images(str(cdz))) == {"secA"}

