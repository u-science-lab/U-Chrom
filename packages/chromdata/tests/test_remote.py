"""Reading a .chromdata.zarr over HTTP (fsspec): backed ChromData and embedded contact maps.

The web browser over HTTP: uchrom-browser's tests/test_remote_store.py."""

import functools
import http.server
import threading

import numpy as np
import pytest

pytest.importorskip("aiohttp")
pytest.importorskip("cooler")

from chromdata import ChromData, embedded  # noqa: E402
from chromdata.testing import LINKED_RES as RES, RangeRequestHandler as _RangeHandler, linked_store as _store  # noqa: E402


@pytest.fixture
def served(tmp_path):
    _, emb = _store(tmp_path)
    embedded.embed_links(emb, verbose=False, trans_min_resolution=RES)
    handler = functools.partial(_RangeHandler, directory=str(tmp_path))
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    _RangeHandler.log.clear()
    yield emb, f"http://127.0.0.1:{srv.server_address[1]}/{emb.name}"
    srv.shutdown()


def test_backed_read_over_http(served):
    emb, url = served
    local = ChromData.read(str(emb), backed=True)
    remote = ChromData.read(url, backed=True)
    assert remote.n_spots == local.n_spots and list(remote.cells.index) == list(local.cells.index)
    a, b = local.get_chrom("chr2"), remote.get_chrom("chr2")
    np.testing.assert_array_equal(np.asarray(a.coords), np.asarray(b.coords))
    with pytest.raises(ValueError, match="backed"):
        ChromData.read(url)


def test_embedded_maps_over_http(served):
    emb, url = served
    assert set(embedded.list_embedded(url)) == {"bulk", "cells"}
    e = embedded.EmbeddedContacts(url, "cells")
    assert e.cells == ["c0", "c1", "c2"]
    loc = embedded.EmbeddedContacts(str(emb), "cells")
    _RangeHandler.log.clear()
    for k in range(3):
        np.testing.assert_array_equal(e.cell_pixels("cis/chr1", [k]), loc.cell_pixels("cis/chr1", [k]))
    assert 0 < len(_RangeHandler.log) <= 3 * 4          # a few requests per cell (offsets + one shard each)
