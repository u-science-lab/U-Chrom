"""Contact maps / AnnData embedded in a .chromdata.zarr (uchrom.core.embedded)."""

import shutil

import numpy as np
import pandas as pd
import pytest

cooler = pytest.importorskip("cooler")
anndata = pytest.importorskip("anndata")

from uchrom import ChromData  # noqa: E402
from uchrom.browser.web.data import GENOME, DatasetStore, decode_matrix  # noqa: E402
from uchrom.core import embedded  # noqa: E402

RES = 100
N = 6   # bins per chromosome


def _bins():
    rows = [(c, i * RES, i * RES + RES) for c in ("chr1", "chr2") for i in range(N)]
    return pd.DataFrame(rows, columns=["chrom", "start", "end"])


def _pixels(seed: int, scale: int = 1):
    rng = np.random.default_rng(seed)
    i, j = np.triu_indices(2 * N)
    keep = rng.random(len(i)) < 0.6
    return pd.DataFrame({"bin1_id": i[keep], "bin2_id": j[keep],
                         "count": rng.integers(1, 40, keep.sum()) * scale})


def _store(tmp_path):
    bins = _bins()
    cooler.create_cooler(str(tmp_path / "bulk.cool"), bins, _pixels(0), ordered=True)
    cooler.zoomify_cooler(str(tmp_path / "bulk.cool"), str(tmp_path / "bulk.mcool"), [RES, 2 * RES], chunksize=1000)
    cooler.balance_cooler(cooler.Cooler(f"{tmp_path / 'bulk.mcool'}::/resolutions/{RES}"), store=True, ignore_diags=0, min_nnz=1)
    maps = {f"c{k}": _pixels(10 + k, k + 1) for k in range(3)}
    cooler.create_scool(str(tmp_path / "cells.scool"), bins, maps, ordered=True)
    ad = anndata.AnnData(np.arange(3 * 2 * N, dtype=np.float32).reshape(3, 2 * N),
                         obs=pd.DataFrame(index=["c0", "c1", "c2"]),
                         var=pd.DataFrame({"bin_id": np.arange(2 * N), "resolution": RES}, index=[f"b{i}" for i in range(2 * N)]))
    ad.write_h5ad(tmp_path / "ssab.h5ad")
    spots = pd.DataFrame({"chrom": bins["chrom"], "start": bins["start"], "end": bins["end"],
                          "trace_id": bins["chrom"]})
    cells = pd.DataFrame({"cell_type": ["A", "A", "B"]}, index=pd.Index(["c0", "c1", "c2"], name="cell_id"))
    cd = ChromData(np.zeros((len(spots), 3)), spots, cells=cells)
    cd.link_cool("bulk.mcool", key="bulk")
    cd.link_scool("cells.scool", key="cells")
    cd.uns["linked_bin_matrices"] = {"ssAB": {"path": "ssab.h5ad", "label": "ssAB"}}
    (tmp_path / "sec.png").write_bytes(b"\x89PNG\r\n\x1a\n" + bytes(range(256)) * 40)
    cd.uns["linked_images"] = {"secA": {"path": "sec.png", "kind": "png"}}
    cd.uns["linked_anndata"] = {"path": "ssab.h5ad", "format": "h5ad"}
    cd.write(tmp_path / "linked.chromdata.zarr")
    shutil.copytree(tmp_path / "linked.chromdata.zarr", tmp_path / "emb.chromdata.zarr")
    return tmp_path / "linked.chromdata.zarr", tmp_path / "emb.chromdata.zarr"


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


def test_image_embedded(stores):
    tmp_path, _, emb = stores
    (tmp_path / "sec.png").unlink()
    ds = DatasetStore().load(emb)
    assert "secA" in ds._images()
    raw, media = ds.image_bytes("secA")
    assert media == "image/png" and raw.startswith(b"\x89PNG") and len(raw) == 8 + 256 * 40


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
    # linked_adata falls back to the embedded AnnData
    assert cd.linked_adata is not None and cd.linked_adata.shape == (3, 2 * N)


def test_export_roundtrip(stores):
    tmp_path, _, emb = stores
    out = embedded.export_scool(str(emb), "cells", tmp_path / "again.scool")
    for c in ("c0", "c1", "c2"):
        a = cooler.Cooler(f"{out}::/cells/{c}").pixels()[:]
        b = cooler.Cooler(f"{tmp_path / 'cells.scool'}::/cells/{c}").pixels()[:]
        assert sorted(zip(a.bin1_id, a.bin2_id, a["count"])) == sorted(zip(b.bin1_id, b.bin2_id, b["count"]))
    one = embedded.export_cool(str(emb), "bulk", tmp_path / "r.cool", resolution=2 * RES)
    assert cooler.Cooler(str(one)).binsize == 2 * RES
    with pytest.raises(ValueError):
        embedded.export_cool(str(emb), "cells", tmp_path / "x.cool")


def test_http_routes_without_the_files(stores):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from uchrom.browser.web.server import create_app

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
