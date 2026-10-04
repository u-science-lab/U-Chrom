"""Embedded contact maps / AnnData against the linked files, on the Spatial Hi-C-RNA mouse brain.

Prepare (once)::

    python -m uchrom.core.embedded example-data/spatial_hicrna/hicrna_mouse_brain.chromdata.zarr      # ~3 min
    python benchmarks/embedded_contacts.py                                                              # ~1 min

(the linked reference is a temporary copy of the store without ``embedded/``)

Reports (``benchmarks/results/embedded_contacts.json``):

1. size of every embedded object against the linked file;
2. exactness: the web-browser matrices from the embedded store equal those from the linked store;
4. the same over real HTTP range requests (a local server), requests and bytes on the wire;
3. what an object store would see: the number of GET requests / bytes per operation, counted on the
   store layer (every ``get`` zarr issues, with its byte range; metadata separate from data).  The
   store is local, so times are the CPU / decode cost only.
"""

from __future__ import annotations

import json
import time
import warnings
from pathlib import Path

import numpy as np

from uchrom.browser.web.data import GENOME, DatasetStore, decode_matrix
from uchrom.core.embedded import EmbeddedContacts, list_embedded

warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parents[1]
D = ROOT / "example-data" / "spatial_hicrna"
EMB = D / "hicrna_mouse_brain.chromdata.zarr"
LINKED = D / "_linked_reference.chromdata.zarr"      # the same store without embedded/ (links only)
OUT = ROOT / "benchmarks" / "results" / "embedded_contacts.json"


def du(p: Path) -> float:
    return sum(f.stat().st_size for f in p.rglob("*") if f.is_file()) / 1e6


def sizes(res: dict) -> None:
    print("[1] sizes (MB)")
    pairs = {"bulk.mouse_brain_r1": D / "contacts/mouse_brain_r1.bulk.mcool",
             "bulk.mouse_brain_r2": D / "contacts/mouse_brain_r2.bulk.mcool",
             "per_spot.mouse_brain_r1": D / "hicrna_mouse_brain.mouse_brain_r1.spots_1Mb.scool",
             "per_spot.mouse_brain_r2": D / "hicrna_mouse_brain.mouse_brain_r2.spots_1Mb.scool"}
    out = {}
    for key, src in pairs.items():
        e = du(EMB / "embedded/contacts" / key)
        out[key] = {"linked_mb": round(src.stat().st_size / 1e6, 1), "embedded_mb": round(e, 1),
                    "ratio": round(e / (src.stat().st_size / 1e6), 3)}
    for key, name in (("ssAB", "hicrna_mouse_brain_ssab.h5ad"), ("default", "hicrna_mouse_brain_rna.h5ad")):
        e = du(EMB / "embedded/anndata" / key)
        out[f"anndata.{key}"] = {"linked_mb": round((D / name).stat().st_size / 1e6, 1), "embedded_mb": round(e, 1),
                                 "ratio": round(e / ((D / name).stat().st_size / 1e6), 3)}
    for k, v in out.items():
        print(f"  {k:26s} linked {v['linked_mb']:8.1f}  embedded {v['embedded_mb']:8.1f}  ({v['ratio']:.2f}x)")
    res["sizes"] = out


def exactness(res: dict) -> None:
    print("[2] browser output, embedded vs linked")
    s = DatasetStore()
    lnk, emb = s.load(LINKED), s.load(EMB)
    cells = emb._embedded_maps()["per_spot.mouse_brain_r1"].cells
    group_cells = cells[:500]
    for ds in (lnk, emb):
        ds.group_cells = lambda g, _c=group_cells: _c
    queries = {
        "bulk chr2 (auto resolution)": dict(key="bulk.mouse_brain_r1", chrom="chr2"),
        "bulk chr2 30-40 Mb, 25 kb": dict(key="bulk.mouse_brain_r1", chrom="chr2", start=30_000_000, end=40_000_000, resolution=25000),
        "bulk chr5 (r2)": dict(key="bulk.mouse_brain_r2", chrom="chr5"),
        "bulk whole genome": dict(key="bulk.mouse_brain_r1", chrom=GENOME),
        "one spot chr1": dict(key="per_spot.mouse_brain_r1", chrom="chr1", cell=cells[100]),
        "one spot whole genome": dict(key="per_spot.mouse_brain_r1", chrom=GENOME, cell=cells[100]),
        "500 spots chr7": dict(key="per_spot.mouse_brain_r1", chrom="chr7", group="g"),
        "500 spots whole genome": dict(key="per_spot.mouse_brain_r1", chrom=GENOME, group="g"),
    }
    out = {}
    for label, kw in queries.items():
        t = time.time(); a = decode_matrix(lnk.contacts(**kw)); ta = time.time() - t
        t = time.time(); b = decode_matrix(emb.contacts(**kw)); tb = time.time() - t
        same = bool(np.array_equal(a["matrix"], b["matrix"], equal_nan=True))
        out[label] = {"equal": same, "linked_ms": round(ta * 1000), "embedded_ms": round(tb * 1000)}
        print(f"  {label:30s} equal={same}  linked {ta * 1000:6.0f} ms  embedded {tb * 1000:6.0f} ms")
    # ssAB track: the same numbers from the embedded AnnData
    import anndata as ad

    ref = ad.read_h5ad(D / "hicrna_mouse_brain_ssab.h5ad")
    m = emb._bin_matrix("ssAB")
    v = m["var"]
    cols = v[v["chrom"] == "chr1"]["col"].to_numpy()
    same = bool(np.array_equal(np.asarray(m["adata"].X[:, int(cols.min()):int(cols.max()) + 1]),
                               np.asarray(ref.X[:, int(cols.min()):int(cols.max()) + 1])))
    out["ssAB chr1, every spot"] = {"equal": same}
    print(f"  ssAB chr1 (all spots) equal={same}")
    res["exactness"] = out
    assert all(x["equal"] for x in out.values()), "embedded output differs from the linked files"


def requests(res: dict) -> None:
    import zarr
    from zarr.storage import LocalStore

    class Counting(LocalStore):
        log: list = []

        async def get(self, key, prototype, byte_range=None):
            r = await super().get(key, prototype, byte_range)
            Counting.log.append((key, 0 if r is None else len(r)))
            return r

    def report(label, fn, out):
        Counting.log.clear()
        t = time.time(); fn(); dt = time.time() - t
        meta = [x for x in Counting.log if x[0].endswith("zarr.json")]
        data = [x for x in Counting.log if not x[0].endswith("zarr.json")]
        r = {"metadata_requests": len(meta), "data_requests": len(data), "data_mb": round(sum(b for _, b in data) / 1e6, 2),
             "ms": round(dt * 1000)}
        out[label] = r
        print(f"  {label:44s} meta {r['metadata_requests']:3d}  data {r['data_requests']:4d} req  {r['data_mb']:7.2f} MB  {r['ms']:5d} ms")

    print("[3] requests an object store would see (cold reader, nothing cached between rows)")
    out: dict = {}
    names = list_embedded(str(EMB))

    def fresh(key):
        st = Counting(str(EMB), read_only=True)
        return EmbeddedContacts(st, names[key])
    sp, bk = "per_spot.mouse_brain_r1", "bulk.mouse_brain_r1"
    report("open a per-spot map (metadata only)", lambda: fresh(sp), out)
    report("one spot, chr1 (cis)", lambda: fresh(sp).cell_pixels("cis/chr1", [3000]), out)

    def one_spot_genome():
        e = fresh(sp)
        list(e.iter_pixels(cell_idx=[3000]))
    report("one spot, whole genome (cis + trans)", one_spot_genome, out)
    report("500 spots, chr1 (pseudo-bulk)", lambda: fresh(sp).cell_pixels("cis/chr1", range(1000, 1500)), out)

    def group_genome():
        e = fresh(sp)
        list(e.iter_pixels(cell_idx=list(range(1000, 1500))))
    report("500 spots, whole genome", group_genome, out)
    report("open a bulk map (metadata only)", lambda: fresh(bk), out)
    report("bulk chr2:30-40 Mb at 25 kb", lambda: fresh(bk).region_pixels("chr2", 1200, 1600, 25000), out)

    def bulk_genome():
        e = fresh(bk)
        list(e.iter_pixels(500000))
    report("bulk whole genome at 500 kb", bulk_genome, out)
    res["requests"] = out


def http_requests(res: dict) -> None:
    """The same operations over real HTTP (a local server with Range support): requests and bytes on the wire."""
    import functools
    import http.server
    import threading

    log: list = []

    class H(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _send(self, body: bytes, code=200, extra=None):
            self.send_response(code)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Accept-Ranges", "bytes")
            for k, v in (extra or {}).items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(body)

        def do_HEAD(self):
            p = Path(self.translate_path(self.path))
            if not p.is_file():
                return self.send_error(404)
            self.send_response(200)
            self.send_header("Content-Length", str(p.stat().st_size))
            self.send_header("Accept-Ranges", "bytes")
            self.end_headers()

        def do_GET(self):
            p = Path(self.translate_path(self.path))
            if not p.is_file():
                return self.send_error(404)
            size = p.stat().st_size
            rng = self.headers.get("Range")
            lo, hi = 0, size
            if rng:
                a, _, b = rng.removeprefix("bytes=").partition("-")
                lo = int(a) if a else max(0, size - int(b))
                hi = min(size, int(b) + 1) if (a and b) else size
            with open(p, "rb") as f:
                f.seek(lo)
                body = f.read(hi - lo)
            log.append((self.path, bool(rng), len(body)))
            self._send(body, 206 if rng else 200,
                       {"Content-Range": f"bytes {lo}-{hi - 1}/{size}"} if rng else None)

    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(H, directory=str(D)))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{srv.server_address[1]}/{EMB.name}"
    print("[4] over HTTP (a real server with Range support; every request counted)")
    out: dict = {}

    def report(label, fn):
        log.clear()
        t = time.time(); fn(); dt = time.time() - t
        nbytes = sum(b for _, _, b in log)
        out[label] = {"requests": len(log), "range_requests": sum(1 for _, r, _ in log if r),
                      "mb": round(nbytes / 1e6, 2), "ms": round(dt * 1000)}
        r = out[label]
        print(f"  {label:44s} {r['requests']:4d} req ({r['range_requests']} ranged)  {r['mb']:7.2f} MB  {r['ms']:5d} ms")

    t = time.time()
    s = DatasetStore()
    report("open the store in the browser (backed)", lambda: s.load(url))
    ds = s._datasets[max(s._datasets)]
    cells = ds._embedded_maps()["per_spot.mouse_brain_r1"].cells
    ds.group_cells = lambda g, _c=cells[1000:1500]: _c
    report("contact map list (embedded)", lambda: ds.contact_maps())
    report("bulk chr2 (auto resolution)", lambda: ds.contacts("bulk.mouse_brain_r1", "chr2"))
    report("bulk chr2:30-40 Mb at 25 kb", lambda: ds.contacts("bulk.mouse_brain_r1", "chr2", start=30_000_000, end=40_000_000, resolution=25000))
    report("bulk whole genome", lambda: ds.contacts("bulk.mouse_brain_r1", GENOME))
    report("one spot, chr1", lambda: ds.contacts("per_spot.mouse_brain_r1", "chr1", cell=cells[3000]))
    report("one spot, whole genome", lambda: ds.contacts("per_spot.mouse_brain_r1", GENOME, cell=cells[3000]))
    report("500 spots, chr7", lambda: ds.contacts("per_spot.mouse_brain_r1", "chr7", group="g"))
    report("500 spots, whole genome", lambda: ds.contacts("per_spot.mouse_brain_r1", GENOME, group="g"))
    srv.shutdown()
    res["http"] = out


if __name__ == "__main__":
    import shutil

    res: dict = {}
    shutil.rmtree(LINKED, ignore_errors=True)
    shutil.copytree(EMB, LINKED, ignore=shutil.ignore_patterns("embedded"))
    try:
        sizes(res)
        exactness(res)
        requests(res)
        http_requests(res)
    finally:
        shutil.rmtree(LINKED, ignore_errors=True)
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(res, indent=1))
    print("wrote", OUT.relative_to(ROOT))
