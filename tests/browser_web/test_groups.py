"""Cell groups: categorical groups, registered cell lists, group-scoped views (API.md)."""

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from uchrom import ChromData
from uchrom.browser.web.data import DatasetStore, decode_matrix

_FOV0 = Path(__file__).resolve().parents[2] / "example-data" / "takei2025_fov0"
# built by example-data/build_takei2025_fov0.py
TAKEI = _FOV0 / "takei2025_fov0.chromdata.zarr"


def _three_cells():
    """Cells c1, c2 (type A) and c3 (type B); one 3-bin trace each on chr1.

    Trace of cell k is the c1 trace scaled by k, so group statistics are
    predictable.
    """
    base = np.array([[0, 0, 0], [1, 0, 0], [3, 0, 0]], float)
    coords = np.vstack([base * k for k in (1, 2, 3)])
    spots = pd.DataFrame({
        "chrom": "chr1", "start": [0, 100, 200] * 3, "end": [100, 200, 300] * 3,
        "trace_id": np.repeat(["t1", "t2", "t3"], 3), "cell_id": np.repeat(["c1", "c2", "c3"], 3),
    })
    tracks = pd.DataFrame({"mark": [1.0, 1.0, 1.0, 3.0, 3.0, 3.0, 10.0, 10.0, 10.0]})
    cells = pd.DataFrame({"cell_type": ["A", "A", "B"]}, index=pd.Index(["c1", "c2", "c3"], name="cell_id"))
    cd = ChromData(coords, spots, tracks=tracks, cells=cells, uns={"xyz_unit": "um"})
    return DatasetStore().add(cd, name="three")


def test_field_group_cells_and_errors():
    ds = _three_cells()
    assert ds.group_cells("field:cell_type=A") == ["c1", "c2"]
    assert ds.group_cells("all") == ["c1", "c2", "c3"]
    assert ds.group_info("all")["name"] == "all cells"
    info = ds.group_info("field:cell_type=B")
    assert info == {"group": "field:cell_type=B", "name": "B", "n_cells": 1, "cells": ["c3"]}
    with pytest.raises(KeyError):
        ds.group_cells("field:nope=A")
    with pytest.raises(LookupError):
        ds.group_cells("field:cell_type=Z")  # no cells: 422, not 404
    with pytest.raises(KeyError):
        ds.group_cells("g0123456789ab")  # never registered


def test_register_group_is_stable_and_drops_unknown_cells():
    ds = _three_cells()
    r = ds.register_group(["c3", "c1", "zz"], name="lasso 1")
    assert r["n_cells"] == 2 and r["n_unknown"] == 1 and r["id"].startswith("g")
    # same cells in another order → same id; the name is updated
    assert ds.register_group(["c1", "c3"], name="renamed")["id"] == r["id"]
    assert ds.group_cells(r["id"]) == ["c1", "c3"]
    assert ds.groups() == [{"id": r["id"], "name": "renamed", "n_cells": 2}]
    with pytest.raises(LookupError):
        ds.register_group(["zz"])


def test_group_scoped_tracks_distance_and_stats():
    ds = _three_cells()
    a = "field:cell_type=A"
    t = ds.tracks(["mark"], "chr1", group=a)
    assert t["values"]["mark"] == [2.0, 2.0, 2.0] and t["n_spots"] == [2, 2, 2] and t["group"] == a
    d = decode_matrix(ds.distance("chr1", group=a))
    np.testing.assert_allclose(d["matrix"][0, 2], np.median([3, 6]))
    assert d["header"]["n_traces"] == 2 and d["header"]["n_cells"] == 2 and d["header"]["group"] == a
    rg = ds.stats_rg("chr1", group="field:cell_type=B")
    assert rg["cell_ids"] == ["c3"] and rg["n_cells"] == 1
    sc = ds.stats_scaling("chr1", group=a, n_bins=2)
    assert sum(sc["n_pairs"]) == 6 and sc["n_cells"] == 2
    lasso = ds.register_group(["c3"])["id"]
    np.testing.assert_allclose(ds.tracks(["mark"], "chr1", group=lasso)["values"]["mark"], [10.0] * 3)
    with pytest.raises(ValueError):
        ds.tracks(["mark"], "chr1", cell_id="c1", group=a)  # one scope at a time


def _scool(tmp_path):
    cooler = pytest.importorskip("cooler")
    bins = pd.DataFrame({"chrom": "chr1", "start": np.arange(4) * 100, "end": np.arange(4) * 100 + 100})
    i, j = np.triu_indices(4)
    pix = pd.DataFrame({"bin1_id": i, "bin2_id": j, "count": np.ones(len(i), int)})
    maps = {"c1": pix, "c2": pix.assign(count=2), "c3": pix.assign(count=5)}
    cooler.create_scool(str(tmp_path / "cells.scool"), bins, maps, ordered=True)
    cooler.create_cooler(str(tmp_path / "bulk.cool"), bins, pix, ordered=True)


def test_scool_pseudobulk(tmp_path):
    _scool(tmp_path)
    spots = pd.DataFrame({c: pd.Series(dtype=t) for c, t in
                          [("chrom", str), ("start", np.int64), ("end", np.int64), ("trace_id", str), ("cell_id", str)]})
    cells = pd.DataFrame({"cell_type": ["A", "A", "B"]}, index=pd.Index(["c1", "c2", "c3"], name="cell_id"))
    cd = ChromData(np.zeros((0, 3)), spots, cells=cells)
    cd.link_scool("cells.scool", key="cells")
    cd.link_cool("bulk.cool", key="bulk")
    cd.write(tmp_path / "d.chromdata.zarr")
    ds = DatasetStore().load(tmp_path / "d.chromdata.zarr")

    m = decode_matrix(ds.contacts("cells", "chr1", group="field:cell_type=A"))
    assert np.all(m["matrix"] == 3)  # 1 + 2, symmetric
    h = m["header"]
    assert h["n_cells"] == 2 and h["group"] == "field:cell_type=A" and h["n_contacts"] == 3 * 10
    part = decode_matrix(ds.contacts("cells", "chr1", start=100, end=300, group="field:cell_type=B"))
    assert part["header"]["bin_starts"] == [100, 200] and np.all(part["matrix"] == 5)
    gid = ds.register_group(["c1", "c3"])["id"]
    assert np.all(decode_matrix(ds.contacts("cells", "chr1", group=gid))["matrix"] == 6)
    # reserved "all": every cell's map
    everyone = decode_matrix(ds.contacts("cells", "chr1", group="all"))
    assert np.all(everyone["matrix"] == 8) and everyone["header"]["n_cells"] == 3
    # cached: the same bytes come back
    assert ds.contacts("cells", "chr1", group=gid) is ds.contacts("cells", "chr1", group=gid)
    with pytest.raises(ValueError):
        ds.contacts("bulk", "chr1", group=gid)  # not per-cell
    with pytest.raises(ValueError):
        ds.contacts("cells", "chr1", cell="c1", group=gid)


def test_group_routes(tmp_path):
    pytest.importorskip("fastapi")
    pytest.importorskip("httpx")
    from fastapi.testclient import TestClient

    from uchrom.browser.web import create_app

    store = DatasetStore()
    ds = _three_cells()
    store._datasets[ds.id] = ds
    c = TestClient(create_app(store))
    base = f"/api/datasets/{ds.id}"
    r = c.post(f"{base}/groups", json={"cells": ["c2", "c3"], "name": "sel"})
    assert r.status_code == 200 and r.json()["n_cells"] == 2
    gid = r.json()["id"]
    assert c.get(f"{base}/groups").json() == [{"id": gid, "name": "sel", "n_cells": 2}]
    assert c.get(f"{base}/group_cells", params={"group": gid}).json()["cells"] == ["c2", "c3"]
    assert c.get(f"{base}/group_cells", params={"group": "field:cell_type=A"}).json()["cells"] == ["c1", "c2"]
    tr = c.get(f"{base}/tracks", params={"names": "mark", "chrom": "chr1", "group": gid}).json()
    assert tr["values"]["mark"] == [6.5, 6.5, 6.5]
    assert c.get(f"{base}/stats/rg", params={"group": "field:cell_type=A"}).json()["n_cells"] == 2
    assert c.get(f"{base}/distance", params={"chrom": "chr1", "group": gid}).status_code == 200
    # unknown group → 404, empty group / no known cells → 422
    assert c.get(f"{base}/stats/rg", params={"group": "gffffffffffff"}).status_code == 404
    assert c.get(f"{base}/stats/rg", params={"group": "field:cell_type=Z"}).status_code == 422
    assert c.post(f"{base}/groups", json={"cells": ["nope"]}).status_code == 422


@pytest.mark.skipif(not TAKEI.exists(), reason="takei2025_fov0 example missing (example-data/build_takei2025_fov0.py)")
def test_takei_cell_types_differ():
    """Real data: per-cell-type aggregation on Takei 2025 cerebellum FOV 0.
    Every cell type must yield statistics over exactly its own cells."""
    ds = DatasetStore().load(TAKEI)
    field = next(f for f in ds.cell_fields() if f["name"] == "cell_type")
    for cat in field["categories"]:
        g = f"field:cell_type={cat['value']}"
        rg = ds.stats_rg("chr1", group=g)
        assert rg["n_cells"] == cat["count"]
        assert set(rg["cell_ids"]) <= set(ds.group_cells(g))
