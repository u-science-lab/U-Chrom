"""Reading a .chromdata.zarr over HTTP (fsspec): backed ChromData, embedded contact maps, the web browser."""

import functools
import http.server
import threading
from pathlib import Path

import numpy as np
import pytest

pytest.importorskip("aiohttp")
pytest.importorskip("cooler")

from tests.core.test_embedded import RES, _store  # noqa: E402
from uchrom import ChromData  # noqa: E402
from uchrom.browser.web.data import GENOME, DatasetStore, decode_matrix  # noqa: E402
from chromdata import embedded  # noqa: E402


class _RangeHandler(http.server.SimpleHTTPRequestHandler):
    """Static files with ``Range`` support, the requests logged (what an object store would see)."""

    log: list = []

    def log_message(self, *a):
        pass

    def do_GET(self):
        path = Path(self.translate_path(self.path))
        if not path.is_file():
            self.send_error(404)
            return
        data = path.read_bytes()
        rng = self.headers.get("Range")
        code, body = 200, data
        if rng:
            a, _, b = rng.removeprefix("bytes=").partition("-")
            lo = int(a) if a else max(0, len(data) - int(b))
            hi = int(b) + 1 if (a and b) else len(data)
            code, body = 206, data[lo:hi]
        _RangeHandler.log.append((self.path, rng, len(body)))
        self.send_response(code)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Accept-Ranges", "bytes")
        if code == 206:
            self.send_header("Content-Range", f"bytes {lo}-{lo + len(body) - 1}/{len(data)}")
        self.end_headers()
        self.wfile.write(body)

    def do_HEAD(self):
        path = Path(self.translate_path(self.path))
        if not path.is_file():
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Length", str(path.stat().st_size))
        self.send_header("Accept-Ranges", "bytes")
        self.end_headers()


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
