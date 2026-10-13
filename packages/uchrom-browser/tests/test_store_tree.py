"""The Store tab: the on-disk structure of a .chromdata.zarr / .cdz store."""

import numpy as np
import pandas as pd
import pytest

from chromdata import ChromData
from uchrom_browser.data import DatasetStore


def _cd():
    spots = pd.DataFrame({"chrom": ["chr1"] * 4, "start": [0, 100, 0, 100], "end": [100, 200, 100, 200],
                          "trace_id": ["a", "a", "b", "b"], "cell_id": ["c1", "c1", "c2", "c2"]})
    cd = ChromData(np.arange(12, dtype=float).reshape(4, 3), spots)
    cd.cellm["umap"] = np.zeros((2, 2))
    return cd


def _find(node, path):
    if node["path"] == path:
        return node
    for c in node.get("children", []):
        hit = _find(c, path)
        if hit:
            return hit
    return None


@pytest.mark.parametrize("suffix", [".chromdata.zarr", ".cdz"])
def test_store_tree_lists_groups_arrays_tables(tmp_path, suffix):
    p = tmp_path / f"d{suffix}"
    _cd().write(p)
    t = DatasetStore().load(p).store_tree()
    assert t["kind"] == "group" and t["container"] == ("cdz" if suffix == ".cdz" else "zarr")
    assert '"format_version"' in t["attrs"]["uchrom"]               # attributes: previews
    assert t["bytes"] >= sum(c["bytes"] for c in t["children"]) > 0     # + the root zarr.json
    umap = _find(t, "cellm/umap")
    assert umap["kind"] == "array" and umap["shape"] == [2, 2] and "children" not in umap  # chunks folded
    bins = _find(t, "tables/bins.parquet")
    assert bins["kind"] == "table" and bins["rows"] == 2 and "start" in bins["columns"]


def test_store_tree_needs_a_store():
    d = DatasetStore().add(_cd(), name="mem")
    with pytest.raises(LookupError):
        d.store_tree()


def _flat(node, out=None):
    out = {} if out is None else out
    out[node["path"]] = node
    for c in node.get("children", []):
        _flat(c, out)
    return out


def test_store_tree_over_http_equals_local(tmp_path):
    """HTTP lists no files: the tree is rebuilt from the store's metadata — same nodes, same tables."""
    pytest.importorskip("aiohttp")
    from chromdata.testing import serve_directory

    p = tmp_path / "d.chromdata.zarr"
    _cd().write(p)
    local = _flat(DatasetStore().load(p).store_tree())
    with serve_directory(tmp_path) as base:
        tree = DatasetStore().load(f"{base}/d.chromdata.zarr").store_tree()
    remote = _flat(tree)
    assert tree["container"] == "remote" and tree["note"] and tree["meta"] == local[""].get("meta")
    assert list(remote) == list(local)                               # same nodes, same order
    for path, r in remote.items():
        loc = local[path]
        for f in ("kind", "attrs", "shape", "dtype", "chunk_shape", "rows", "columns", "row_groups"):
            assert r.get(f) == loc.get(f), (path, f)
        if r["kind"] == "table":
            assert r["bytes"] == loc["bytes"]
    umap = remote["cellm/umap"]
    assert umap["bytes"] is None and umap["nbytes"] == 2 * 2 * 8 and "n_chunks" not in umap
    assert remote["cellm"]["bytes"] is None and remote[""]["bytes"] is None   # they hold an array
    assert remote["tables"]["bytes"] == local["tables"]["bytes"]             # tables + metadata: exact


def test_store_tree_of_a_listing_object_store(tmp_path):
    """An object store that lists its keys (s3://, gs://; here memory://) is walked like a directory."""
    fsspec = pytest.importorskip("fsspec")
    from uchrom_browser.store_tree import remote_store_tree

    p = tmp_path / "d.chromdata.zarr"
    _cd().write(p)
    fs = fsspec.filesystem("memory")
    fs.put(str(p), "/bucket/d.chromdata.zarr", recursive=True)
    try:
        tree = remote_store_tree("memory://bucket/d.chromdata.zarr")
    finally:
        fs.rm("/bucket", recursive=True)
    local = _flat(DatasetStore().load(p).store_tree())
    remote = _flat(tree)
    assert tree["container"] == "remote" and "note" not in tree
    assert list(remote) == list(local)
    assert all(r["bytes"] == local[k]["bytes"] and r.get("n_chunks") == local[k].get("n_chunks") for k, r in remote.items())


def test_store_tree_of_a_url_without_a_store():
    from uchrom_browser.store_tree import remote_store_tree

    with pytest.raises(LookupError):
        remote_store_tree("memory://nothing/here.chromdata.zarr")
