"""The web browser on contact maps / AnnData / images embedded in a .chromdata.zarr (chromdata.embedded): the
same answers as from the linked files, without the files, without cooler, from a .cdz."""

import numpy as np
import pytest

cooler = pytest.importorskip("cooler")
anndata = pytest.importorskip("anndata")

from chromdata import ChromData, embedded  # noqa: E402
from chromdata.testing import LINKED_BINS as N, LINKED_RES as RES, linked_store as _store  # noqa: E402
from uchrom_browser.data import GENOME, DatasetStore, decode_matrix  # noqa: E402


@pytest.fixture
def stores(tmp_path):
    linked, emb = _store(tmp_path)
    done = embedded.embed_links(emb, verbose=False, trans_min_resolution=RES)
    assert set(done) == {"bulk", "cells", "ssAB", "secA", "default"}
    return tmp_path, linked, emb


@pytest.mark.parametrize("kw", [
    dict(key="bulk", chrom="chr1"),
    dict(key="bulk", chrom="chr2", start=100, end=400),
    dict(key="bulk", chrom="chr1", resolution=2 * RES),
    dict(key="bulk", chrom="chr1", balance=True),
    dict(key="bulk", chrom=GENOME),
    dict(key="bulk", chrom=GENOME, resolution=2 * RES),
    dict(key="cells", chrom="chr1", cell="c1"),
    dict(key="cells", chrom=GENOME, cell="c2"),
    dict(key="cells", chrom="chr2", group="field:cell_type=A"),
    dict(key="cells", chrom=GENOME, group="field:cell_type=B"),
])
def test_browser_embedded_equals_linked(stores, kw):
    _, linked, emb = stores
    a = DatasetStore().load(linked)
    b = DatasetStore().load(emb)
    assert [m.get("embedded", False) for m in b.contact_maps()] == [True, True]
    assert not any(m.get("embedded") for m in a.contact_maps())
    x, y = decode_matrix(a.contacts(**kw)), decode_matrix(b.contacts(**kw))
    np.testing.assert_array_equal(x["matrix"], y["matrix"])
    hx, hy = x["header"], y["header"]
    assert {k: v for k, v in hx.items()} == {k: v for k, v in hy.items()}


def test_embedded_wins_without_the_external_files(stores):
    tmp_path, _, emb = stores
    for f in ("bulk.mcool", "bulk.cool", "cells.scool", "ssab.h5ad"):
        (tmp_path / f).unlink()
    ds = DatasetStore().load(emb)
    assert {m["key"] for m in ds.contact_maps()} == {"bulk", "cells"}
    assert decode_matrix(ds.contacts("cells", "chr1", cell="c0"))["matrix"].shape == (N, N)
    assert "ssAB@100bp" in ds._cell_bin_tracks()


def test_image_embedded(stores):
    tmp_path, _, emb = stores
    (tmp_path / "sec.png").unlink()
    ds = DatasetStore().load(emb)
    assert "secA" in ds._images()
    raw, media = ds.image_bytes("secA")
    assert media == "image/png" and raw.startswith(b"\x89PNG") and len(raw) == 8 + 256 * 40


def test_http_routes_without_the_files(stores):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from uchrom_browser.server import create_app

    tmp_path, _, emb = stores
    for f in ("bulk.mcool", "bulk.cool", "cells.scool", "ssab.h5ad", "sec.png"):
        (tmp_path / f).unlink()
    store = DatasetStore()
    ds = store.load(emb)
    client = TestClient(create_app(store))
    r = client.get(f"/api/datasets/{ds.id}/images/secA")
    assert r.status_code == 200 and r.headers["content-type"] == "image/png" and r.content.startswith(b"\x89PNG")
    assert client.get(f"/api/datasets/{ds.id}/images/nope").status_code == 404
    r = client.get(f"/api/datasets/{ds.id}/contacts/cells", params={"chrom": "chr1", "cell": "c0"})
    assert r.status_code == 200 and decode_matrix(r.content)["matrix"].shape == (N, N)


def test_embedded_maps_need_no_cooler(stores, monkeypatch):
    """A sandboxed server cannot import cooler (multiprocessing semaphores): embedded maps must not need it."""
    import sys

    tmp_path, _, emb = stores
    monkeypatch.setitem(sys.modules, "cooler", None)            # `import cooler` now raises ImportError
    monkeypatch.setitem(sys.modules, "h5py", None)
    ds = DatasetStore().load(emb)
    assert {m["key"] for m in ds.contact_maps()} == {"bulk", "cells"}
    for kw in (dict(key="bulk", chrom="chr1"), dict(key="bulk", chrom=GENOME), dict(key="cells", chrom="chr2", cell="c1"),
               dict(key="cells", chrom=GENOME, cell="c2"), dict(key="cells", chrom="chr1", group="field:cell_type=A")):
        assert decode_matrix(ds.contacts(**kw))["matrix"].size > 0
    assert ds.image_bytes("secA") is not None


def test_all_cells_sums(stores):
    """The precomputed 'all spots' sums answer the all-cells group exactly like summing every cell."""
    tmp_path, linked, emb = stores
    e = embedded.EmbeddedContacts(str(emb), embedded.list_embedded(str(emb))["cells"])
    assert e.has_sum() and e.meta["has_sum"]
    ref = DatasetStore().load(linked)
    new = DatasetStore().load(emb)
    for kw in (dict(key="cells", chrom="chr1", group="all"), dict(key="cells", chrom="chr2", start=100, end=500, group="all"),
               dict(key="cells", chrom=GENOME, group="all")):
        a, b = decode_matrix(ref.contacts(**kw)), decode_matrix(new.contacts(**kw))
        np.testing.assert_array_equal(a["matrix"], b["matrix"])
        assert a["header"]["n_cells"] == b["header"]["n_cells"] == 3 and a["header"]["n_contacts"] == b["header"]["n_contacts"]
    # a store embedded before the sums existed: upgrade adds them, with the same numbers
    import zarr, shutil

    name = embedded.list_embedded(str(emb))["cells"]
    for part in [p for p in (emb / "embedded" / "contacts" / name).rglob(embedded.SUM) if p.is_dir()]:
        shutil.rmtree(part)
    g = zarr.open_group(str(emb), path=f"embedded/contacts/{name}", mode="r+", zarr_format=3, use_consolidated=False)
    meta = dict(g.attrs["uchrom_contacts"]); meta.pop("has_sum"); g.attrs["uchrom_contacts"] = meta
    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        zarr.consolidate_metadata(str(emb), path=f"embedded/contacts/{name}")
    embedded.consolidate_sections(emb)
    assert not embedded.EmbeddedContacts(str(emb), name).has_sum()
    done = embedded.upgrade_store(emb)
    assert done["sum"] == ["cells"]
    again = DatasetStore().load(emb)
    for kw in (dict(key="cells", chrom="chr1", group="all"), dict(key="cells", chrom=GENOME, group="all")):
        np.testing.assert_array_equal(decode_matrix(ref.contacts(**kw))["matrix"], decode_matrix(again.contacts(**kw))["matrix"])


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
    a, b = DatasetStore().load(emb), DatasetStore().load(cdz)
    assert {m["key"] for m in b.contact_maps()} == {"bulk", "cells"}
    for kw in ({"key": "bulk", "chrom": "chr1"}, {"key": "cells", "chrom": "chr2", "cell": "c1"}):
        x, y = decode_matrix(a.contacts(**kw)), decode_matrix(b.contacts(**kw))
        np.testing.assert_array_equal(x["matrix"], y["matrix"])
    assert "ssAB@100bp" in b._cell_bin_tracks()
    assert set(embedded.list_embedded_images(str(cdz))) == {"secA"}
