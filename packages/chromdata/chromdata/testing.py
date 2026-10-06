"""Test helpers of chromdata and the packages built on it (uchrom, uchrom-browser).

Not a stable API.  An example object that exercises every attribute, comparisons that know
how a store orders its rows, a streamed copy of an object, a store with linked and embedded
contact maps, and a local HTTP server that answers range requests (what an object store sees).
"""

from __future__ import annotations

import contextlib
import functools
import http.server
import json
import shutil
import threading
from pathlib import Path
from typing import Iterator

import numpy as np
import pandas as pd

from .cdata import ChromData

__all__ = ["example_chromdata", "sorted_frame", "sorted_tracks", "assert_same_small", "assert_uns_equal",
           "chunk_rows", "stream_write", "assert_same_store", "LINKED_RES", "LINKED_BINS", "linked_store", "example_atlas",
           "RangeRequestHandler", "serve_directory"]


# ------------------------------------------------------------------ an object with every attribute

def example_chromdata(n_cells: int = 4, seed: int = 0) -> ChromData:
    """Unsorted multi-cell data exercising every attribute (``spot_id`` is a stable key)."""
    rng = np.random.default_rng(seed)
    rows = []
    for c in rng.permutation(n_cells):
        for t in range(3):
            chrom = ["chr2", "chr1", "chrX"][t]
            for b in rng.permutation(6):
                rows.append((chrom, b * 1000, b * 1000 + 1000, f"c{c}_t{t}", f"c{c}"))
    spots = pd.DataFrame(rows, columns=["chrom", "start", "end", "trace_id", "cell_id"])
    n = len(spots)
    spots["spot_id"] = rng.permutation(n)
    spots["label"] = rng.choice(["a", "b", None], n)
    spots["quality"] = rng.random(n)
    spots["coord_status"] = pd.Categorical(rng.choice(["measured", "imputed"], n))
    coords = rng.normal(size=(n, 3))
    coords[[2, 7]] = np.nan
    cells = pd.DataFrame({"cell_type": pd.Categorical(["A", "B"] * (n_cells // 2)),
                          "volume": rng.random(n_cells)},
                         index=pd.Index([f"c{i}" for i in range(n_cells)], name="cell_id"))
    traces = pd.DataFrame({"allele": rng.integers(0, 2, 3 * n_cells)},
                          index=pd.Index([f"c{c}_t{t}" for c in range(n_cells) for t in range(3)],
                                         name="trace_id"))
    cd = ChromData(
        coords, spots, cells=cells, traces=traces,
        cellm={"umap": rng.normal(size=(n_cells, 2)), "X_emb": rng.random((n_cells, 5)).astype(np.float32)},
        spot_tracks=pd.DataFrame({"IF": rng.normal(size=n), "z": rng.integers(0, 9, n),
                                  "grp": pd.Categorical(rng.choice(["x", "y"], n))}),
        layers={"raw": coords + 1, "Raw": coords * 2},     # case-insensitive clash on disk
        uns={"genome_assembly": "mm10",
             "linked_scool": {"cells": {"path": "c.scool", "format": "scool", "bin_size": 1000000}},
             "xyz_unit": "um", "fovs": [0, 1], "tup": (1, "a"),
             "big": np.arange(500.0), "small": np.arange(3), "names": np.array(["p", "q"]),
             "nested": {"a": 1, "b": {"c": [1.5, None]}, "arr": np.ones((10, 10))},
             "nan": float("nan"),
             "linked_cool": {"bulk": {"path": "bulk.mcool", "format": "mcool", "label": "Bulk"}},
             "linked_anndata": {"path": "rna.h5ad", "obs_key": "cell_id"}},
        points={"rna": pd.DataFrame({"x": [1.0, 2.0], "y": [2.0, 3.0], "z": [3.0, 4.0],
                                     "cell_id": ["c1", "c2"], "gene": ["Actb", "Gapdh"]})},
    )
    cd.bin_tracks = pd.DataFrame({"atac": np.arange(cd.n_bins, dtype=float),
                                  "label": [f"b{i}" for i in range(cd.n_bins)]})
    cd.binm["loading"] = rng.normal(size=(cd.n_bins, 2))
    cd.intervals["tads"] = pd.DataFrame({"chrom": ["chr1"], "start": [0], "end": [3000], "score": [0.5]})
    cd.results.set("tads", cd.intervals["tads"], kind="intervals", function="uchrom.x.f",
                   params={"window": 3, "nan": float("nan")}, inputs={"chrom": ["chr1"]})
    cd.results["table"] = pd.DataFrame({"a": [1, 2], "b": ["x", "y"]}, index=pd.Index([5, 6], name="k"))
    cd.results["series"] = pd.Series([1.0, 2.0], name="s")
    cd.results["arr"] = np.arange(6).reshape(2, 3)
    cd.results["bools"] = np.array([True, False])
    cd.results["strings"] = np.array(["u", "v"])
    cd.results["scalar"] = 3.5
    cd.results["tup"] = (1, 2)
    cd.results["ensemble"] = {"chr1": {"mask": np.ones((2, 2), dtype=bool), "n_traces": 3},
                              "Chr1": {"n": 1}, "__odd": 2}     # names escaped on disk
    cd.results["empty"] = pd.DataFrame({"x": pd.Series([], dtype=float)})
    return cd


# ------------------------------------------------------------------ comparisons

def sorted_frame(cd: ChromData) -> pd.DataFrame:
    """``to_dataframe()`` sorted by ``spot_id`` (a store returns its rows in another order)."""
    return cd.to_dataframe().sort_values("spot_id").reset_index(drop=True)


def sorted_tracks(cd: ChromData) -> pd.DataFrame:
    df = cd.tracks_spot_view()
    df["spot_id"] = cd.spots["spot_id"].to_numpy()
    return df.sort_values("spot_id").reset_index(drop=True)


def assert_same_small(a: ChromData, b: ChromData) -> None:
    """The tables that are not spot-aligned (and the results with their provenance) are equal."""
    pd.testing.assert_frame_equal(a.bins, b.bins)
    pd.testing.assert_frame_equal(a.bin_tracks, b.bin_tracks)
    pd.testing.assert_frame_equal(a.cells, b.cells)
    pd.testing.assert_frame_equal(a.traces, b.traces)
    assert list(a.cellm) == list(b.cellm)
    for k in a.cellm:
        np.testing.assert_array_equal(a.cellm[k], b.cellm[k])
        assert a.cellm[k].dtype == b.cellm[k].dtype
    for k in a.binm:
        np.testing.assert_array_equal(a.binm[k], b.binm[k])
    assert list(a.intervals) == list(b.intervals)
    for k in a.intervals:
        pd.testing.assert_frame_equal(pd.DataFrame(a.intervals[k]), pd.DataFrame(b.intervals[k]))
        assert (a.intervals[k].kind, a.intervals[k].source_result) == \
            (b.intervals[k].kind, b.intervals[k].source_result)
    assert list(a.results) == list(b.results)
    assert a.results == b.results
    for k in a.results:
        ra, rb = a.results.record(k), b.results.record(k)
        assert json.dumps(ra.provenance, sort_keys=True) == json.dumps(rb.provenance, sort_keys=True)
    assert list(a.points) == list(b.points)
    for k in a.points:
        pd.testing.assert_frame_equal(a.points[k], b.points[k])


def assert_uns_equal(a: dict, b: dict) -> None:
    """``uns`` dictionaries are equal, array dtypes and NaN included."""
    assert list(a) == list(b)
    for k in a:
        x, y = a[k], b[k]
        if isinstance(x, np.ndarray):
            assert isinstance(y, np.ndarray) and x.dtype == y.dtype
            np.testing.assert_array_equal(x, y)
        elif isinstance(x, dict):
            assert_uns_equal(x, y)
        elif isinstance(x, float) and np.isnan(x):
            assert np.isnan(y)
        else:
            assert x == y and type(x) is type(y), (k, x, y)


# ------------------------------------------------------------------ streaming

def chunk_rows(cd: ChromData, n_chunks: int, seed: int = 1) -> Iterator[dict]:
    """``cd`` split into row chunks (input order kept) as the raw arrays ``ChromData.writer`` takes."""
    rng = np.random.default_rng(seed)
    cuts = np.sort(rng.choice(np.arange(1, cd.n_spots), n_chunks - 1, replace=False))
    bounds = np.r_[0, cuts, cd.n_spots]
    spots = cd.spots.drop(columns=["bin_id"])
    for a, b in zip(bounds[:-1], bounds[1:]):
        yield dict(coords=cd.coords[a:b], spots=spots.iloc[a:b].reset_index(drop=True),
                   spot_tracks=cd.spot_tracks.iloc[a:b].reset_index(drop=True),
                   layers={k: v[a:b] for k, v in cd.layers.items()})


def stream_write(cd: ChromData, path, n_chunks: int = 5, budget: str = "1KB", **kw):
    """Write ``cd`` with the streaming writer, in ``n_chunks`` chunks under a memory budget."""
    w = ChromData.writer(path, memory_budget=budget, **kw)
    for ch in chunk_rows(cd, n_chunks):
        w.append(**ch)
    w.finish(cells=cd.cells, cellm=cd.cellm, traces=cd.traces, bin_tracks=cd.bin_tracks,
             binm=cd.binm, intervals=cd.intervals, points=cd.points, results=cd.results, uns=cd.uns)
    return path


def assert_same_store(a_path, b_path):
    """Two stores hold the same rows in the same order, with the same index and row groups."""
    import zarr

    a, b = ChromData.read(a_path), ChromData.read(b_path)
    pd.testing.assert_frame_equal(a.to_dataframe(include_bin_id=True), b.to_dataframe(include_bin_id=True))
    pd.testing.assert_frame_equal(a.spots, b.spots)
    pd.testing.assert_frame_equal(a.spot_tracks, b.spot_tracks)
    for k in a.layers:
        np.testing.assert_array_equal(a.layers[k], b.layers[k])
    assert_same_small(a, b)
    assert_uns_equal(a.uns, b.uns)
    ra, rb = zarr.open_group(str(a_path), mode="r"), zarr.open_group(str(b_path), mode="r")
    for name in ("trace_offsets", "trace_codes", "trace_cells", "chrom_trace", "cell_offsets",
                 "cell_codes", "cell_partition", "row_groups", "partition_offsets",
                 "partition_groups", "partition_chrom", "source_row"):
        if name in ra["index"] or name in rb["index"]:
            np.testing.assert_array_equal(ra[f"index/{name}"][:], rb[f"index/{name}"][:], err_msg=name)
    ma, mb = ra.attrs["uchrom"], rb.attrs["uchrom"]
    for key in ("format_version", "spot_order", "n_spots", "n_bins", "n_traces", "n_cells",
                "n_row_groups", "n_partitions", "has_source_row", "has_cell_id"):
        assert ma[key] == mb[key], key
    ta, tb = ra["tables"].attrs["tables"], rb["tables"].attrs["tables"]
    for key in ("partitions", "coords", "primary"):
        assert ta.get(key) == tb.get(key), key
    for key in ("spots", "spot_tracks"):
        if key in ta:
            assert {k: v for k, v in ta[key].items() if k != "spot_view_order"} == \
                {k: v for k, v in tb[key].items() if k != "spot_view_order"}
    return a, b


# ------------------------------------------------------------------ linked and embedded contact maps

#: resolution (bp) and bins per chromosome of :func:`linked_store`
LINKED_RES = 100
LINKED_BINS = 6


def _linked_bins() -> pd.DataFrame:
    rows = [(c, i * LINKED_RES, i * LINKED_RES + LINKED_RES) for c in ("chr1", "chr2") for i in range(LINKED_BINS)]
    return pd.DataFrame(rows, columns=["chrom", "start", "end"])


def _linked_pixels(seed: int, scale: int = 1) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    i, j = np.triu_indices(2 * LINKED_BINS)
    keep = rng.random(len(i)) < 0.6
    return pd.DataFrame({"bin1_id": i[keep], "bin2_id": j[keep],
                         "count": rng.integers(1, 40, keep.sum()) * scale})


def linked_store(directory) -> tuple[Path, Path]:
    """Two copies of a small store with linked files next to them (needs cooler and anndata).

    In ``directory``: ``bulk.cool`` / ``bulk.mcool`` (resolutions ``LINKED_RES`` and twice it,
    balanced), ``cells.scool`` (cells c0-c2), ``ssab.h5ad`` (a cell x bin matrix), ``sec.png``;
    the store links them (keys bulk, cells, ssAB, secA, the AnnData).  Returns the paths of
    ``linked.chromdata.zarr`` and of its copy ``emb.chromdata.zarr`` (to embed into).
    """
    import anndata
    import cooler

    directory = Path(directory)
    bins = _linked_bins()
    cooler.create_cooler(str(directory / "bulk.cool"), bins, _linked_pixels(0), ordered=True)
    cooler.zoomify_cooler(str(directory / "bulk.cool"), str(directory / "bulk.mcool"),
                          [LINKED_RES, 2 * LINKED_RES], chunksize=1000)
    cooler.balance_cooler(cooler.Cooler(f"{directory / 'bulk.mcool'}::/resolutions/{LINKED_RES}"),
                          store=True, ignore_diags=0, min_nnz=1)
    maps = {f"c{k}": _linked_pixels(10 + k, k + 1) for k in range(3)}
    cooler.create_scool(str(directory / "cells.scool"), bins, maps, ordered=True)
    n = 2 * LINKED_BINS
    ad = anndata.AnnData(np.arange(3 * n, dtype=np.float32).reshape(3, n),
                         obs=pd.DataFrame(index=["c0", "c1", "c2"]),
                         var=pd.DataFrame({"bin_id": np.arange(n), "resolution": LINKED_RES},
                                          index=[f"b{i}" for i in range(n)]))
    ad.write_h5ad(directory / "ssab.h5ad")
    spots = pd.DataFrame({"chrom": bins["chrom"], "start": bins["start"], "end": bins["end"],
                          "trace_id": bins["chrom"]})
    cells = pd.DataFrame({"cell_type": ["A", "A", "B"]}, index=pd.Index(["c0", "c1", "c2"], name="cell_id"))
    cd = ChromData(np.zeros((len(spots), 3)), spots, cells=cells)
    cd.link_cool("bulk.mcool", key="bulk")
    cd.link_scool("cells.scool", key="cells")
    cd.uns["linked_bin_matrices"] = {"ssAB": {"path": "ssab.h5ad", "label": "ssAB"}}
    (directory / "sec.png").write_bytes(b"\x89PNG\r\n\x1a\n" + bytes(range(256)) * 40)
    cd.uns["linked_images"] = {"secA": {"path": "sec.png", "kind": "png"}}
    cd.uns["linked_anndata"] = {"path": "ssab.h5ad", "format": "h5ad"}
    cd.write(directory / "linked.chromdata.zarr")
    shutil.copytree(directory / "linked.chromdata.zarr", directory / "emb.chromdata.zarr")
    return directory / "linked.chromdata.zarr", directory / "emb.chromdata.zarr"


def example_atlas(directory) -> Path:
    """A folder atlas in ``directory``/atlas: one embedded store (``toy.chromdata.zarr``, from
    :func:`linked_store`) and its ``catalog.json`` (``datasets.json`` next to the folder)."""
    from . import catalog, embedded

    directory = Path(directory)
    _, emb = linked_store(directory)
    embedded.embed_links(emb, verbose=False, trans_min_resolution=LINKED_RES)
    root = directory / "atlas"
    root.mkdir()
    emb.rename(root / "toy.chromdata.zarr")
    cfg = {"title": "Toy atlas", "datasets": [
        {"id": "toy", "store": "toy.chromdata.zarr", "path": "toy.chromdata.zarr", "title": "A toy dataset",
         "paper": "nobody 2026", "license": "CC0"}]}
    (directory / "datasets.json").write_text(json.dumps(cfg))
    catalog.build_catalog(directory / "datasets.json", root, root / "catalog.json")
    return root


# ------------------------------------------------------------------ HTTP with range requests

class RangeRequestHandler(http.server.SimpleHTTPRequestHandler):
    """Static files with ``Range`` support; the requests are logged in ``log`` (path, range, bytes)."""

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
        RangeRequestHandler.log.append((self.path, rng, len(body)))
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


@contextlib.contextmanager
def serve_directory(directory) -> Iterator[str]:
    """Serve ``directory`` over HTTP on a free local port (range requests); yields the base URL."""
    handler = functools.partial(RangeRequestHandler, directory=str(directory))
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    RangeRequestHandler.log.clear()
    try:
        yield f"http://127.0.0.1:{srv.server_address[1]}"
    finally:
        srv.shutdown()
