"""The web browser on a .chromdata.zarr read over HTTP (fsspec): the same maps and tracks as from the local store."""

import functools
import http.server
import threading

import numpy as np
import pytest

pytest.importorskip("aiohttp")
pytest.importorskip("cooler")

from chromdata import embedded  # noqa: E402
from chromdata.testing import LINKED_RES as RES, RangeRequestHandler as _RangeHandler, linked_store as _store  # noqa: E402
from uchrom_browser.data import GENOME, DatasetStore, decode_matrix  # noqa: E402


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


def test_browser_over_http_equals_local(served):
    emb, url = served
    local = DatasetStore().load(emb)
    remote = DatasetStore().load(url)
    assert [m["key"] for m in remote.contact_maps()] == [m["key"] for m in local.contact_maps()]
    assert remote.name == local.name
    for kw in (dict(key="bulk", chrom="chr1"), dict(key="bulk", chrom=GENOME),
               dict(key="cells", chrom="chr2", cell="c1"), dict(key="cells", chrom=GENOME, cell="c2")):
        np.testing.assert_array_equal(decode_matrix(remote.contacts(**kw))["matrix"],
                                      decode_matrix(local.contacts(**kw))["matrix"])
    assert "ssAB@100bp" in remote._cell_bin_tracks()
