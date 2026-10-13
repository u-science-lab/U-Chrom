"""Figure 2c — access by level: ``get_trace`` / ``get_cell`` / ``get_chrom`` latency vs n_spots.

Data: the same whole-cell Takei 2025 subsets as panel b (``_common.stage_subset``),
written once per backend (the HDF5 ``.h5cd`` baselines through
``uchrom.io._h5cd_legacy``).  For each size a fresh interpreter
opens the file through a *backend* (``BACKENDS``), records the open/read time
and RSS, then times ``n_queries`` random ids per level (fixed seed; chromosome
names are drawn with replacement since there are only ~20).  Reported: median
and IQR per level, plus the read time separately.

Backends:

* ``h5cd-1x-memory`` — read the whole file, then in-memory ``cd.get_*`` (a
  boolean-mask scan over all spots); measured on a 1.x checkout.
* ``h5cd-2-memory`` — the same on the HDF5 file written by format 2.0.
* ``zarr-backed`` — ``ChromData.read(path, backed=True)`` on a
  ``.chromdata.zarr`` store: only the small tables and ``index/`` are read on
  open; ``get_*`` reads the row ranges it needs (Parquet row groups) and
  returns an in-memory ChromData.  The page cache is not flushed (no root):
  "from disk" means a fresh process, warm OS cache.
* ``zarr-memory`` — full ``ChromData.read`` of the store, then the in-memory
  scan.
* ``parquet-memory`` — the common baseline without a ChromData: load the
  whole flat spot table (``pd.read_parquet``, the panel-b Parquet file) and
  subset it with a pandas boolean mask (``df[df.trace_id == id]``).
* ``anndata-memory`` — the same with spots as obs in an ``.h5ad``
  (``ad.read_h5ad``, then ``adata[mask].copy()``).
* ``anndata-lazy`` — AnnData's partial read (``anndata.experimental.read_lazy``, the read Supplementary Table 1
  rates native): the same spots as obs written as AnnData Zarr; open = ``read_lazy`` (obs a lazy xarray Dataset,
  obsm / X dask arrays); a query = the boolean mask of the lazy id column (that column read), the subset,
  ``.to_memory()`` (only the chunks holding the selected rows).  ``anndata-lazy-h5ad`` does the same on the
  ``.h5ad`` of ``anndata-memory`` -- with AnnData 0.12.11 ``read_lazy`` fails on that file (its X, n_spots x 0,
  is an unchunked HDF5 dataset: dask rejects the empty chunk tuple), so the lazy series is the Zarr one.  Each
  query's time is also split into the mask and the ``to_memory`` (``diag``).
* ``fofct-memory`` — the FOF-CT core table loaded with
  ``ChromData.from_fofct``, then the in-memory ``get_*``.
* ``spatialdata-lazy`` — SpatialData: ``read_zarr`` (lazy dask points), then
  a dask filter on the id column + ``.compute()`` per query.

Each backend writes its own file (``ext`` / ``write``).  Besides the latency,
every child records its RSS after open, after the trace and cell queries
(before the chromosome scans) and its peak.

    python benchmarks/fig2/c_access.py [--sizes 1e4,1e5,1e6,1e7] [--queries 20] [--backends h5cd-1x-memory]
        [--out-json PATH]

Writes ``u-chrom-paper/manuscripts/full/figures/fig2/results/c_access.json`` (series merged by label), or, with
``--out-json``, a separate file with ``benchmarks/_record.py`` provenance (a run on another machine, e.g. a
cluster node, must not merge into the laptop's series).
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _common as C  # noqa: E402

SCRIPT = Path(__file__).resolve()


class H5cd1xMemory:
    """Load the whole file (format 1.x), query in memory by mask scan."""

    label = "h5cd 1.x (in memory, scan)"
    ext = ".h5cd"

    @staticmethod
    def write(cd, path):
        C.FORMATS["h5cd"].write(cd, path)

    def open(self, path):
        self.cd = C.FORMATS["h5cd"].read(path)

    def ids(self):
        s = self.cd.spots
        return {"trace": list(s["trace_id"].cat.categories), "cell": list(s["cell_id"].cat.categories),
                "chrom": list(s["chrom"].cat.categories)}

    def get(self, level, key):
        return {"trace": self.cd.get_trace, "cell": self.cd.get_cell, "chrom": self.cd.get_chrom}[level](key)


class H5cd2Memory(H5cd1xMemory):
    """HDF5 written by format 2.0 (#65), loaded whole, queried by mask scan."""

    label = "h5cd 2.0 (in memory, scan)"

    @staticmethod
    def write(cd, path):
        C.FORMATS["h5cd2"].write(cd, path)


def _zarr_version() -> str:
    try:
        from chromdata.zarrcd import ZARR_FORMAT_VERSION
    except ImportError:  # pragma: no cover - older checkout
        return "2.0"
    return ZARR_FORMAT_VERSION


class ZarrMemory(H5cd1xMemory):
    label = f"chromdata.zarr {_zarr_version()} (in memory, scan)"
    ext = ".chromdata.zarr"
    row_group_rows = None

    @classmethod
    def write(cls, cd, path):
        cd.write(path, **({"row_group_rows": cls.row_group_rows} if cls.row_group_rows else {}))


class ZarrBacked(ZarrMemory):
    """Backed store: open reads the small tables + index; get_* reads row ranges.

    Also timed with ``columns="coords"`` (coordinates + key columns only; the
    62 Takei spot tracks are not read): levels ``trace_coords`` /
    ``cell_coords`` / ``chrom_coords``."""

    label = f"chromdata.zarr {_zarr_version()} (backed, from disk)"
    coords_levels = True

    def open(self, path):
        from uchrom import ChromData
        self.cd = ChromData.read(path, backed=True)

    def ids(self):
        cd = self.cd
        return {"trace": list(cd._categories("trace_id")), "cell": list(cd._categories("cell_id")),
                "chrom": list(cd.bins["chrom"].cat.categories)}

    def get(self, level, key):
        if level.endswith("_coords"):
            fn = {"trace": self.cd.get_trace, "cell": self.cd.get_cell,
                  "chrom": self.cd.get_chrom}[level.split("_")[0]]
            return fn(key, columns="coords")
        return super().get(level, key)


class ParquetMemory:
    """Baseline: load the whole flat table, subset with a pandas boolean mask."""

    label = "Parquet (load + subset)"
    ext = ".parquet"
    key = "parquet"

    @classmethod
    def write(cls, cd, path):
        C.FORMATS[cls.key].write(cd, path)

    def open(self, path):
        import pandas as pd
        self.df = pd.read_parquet(path, engine="pyarrow")

    def table(self):
        return self.df

    def ids(self):
        t = self.table()
        return {lv: list(t[col].unique()) for lv, col in (("trace", "trace_id"), ("cell", "cell_id"),
                                                             ("chrom", "chrom"))}

    def get(self, level, key):
        col = {"trace": "trace_id", "cell": "cell_id", "chrom": "chrom"}[level]
        return self.df[self.df[col] == key]


class AnnDataMemory(ParquetMemory):
    """Baseline: load the whole .h5ad (spots as obs), subset with a boolean mask."""

    label = "AnnData (load + subset)"
    ext = ".h5ad"
    key = "anndata"

    def open(self, path):
        import anndata as ad
        self.adata = ad.read_h5ad(path)

    def table(self):
        return self.adata.obs

    def get(self, level, key):
        col = {"trace": "trace_id", "cell": "cell_id", "chrom": "chrom"}[level]
        return self.adata[(self.adata.obs[col] == key).to_numpy()].copy()


class AnnDataLazy(ParquetMemory):
    """AnnData's partial read: ``anndata.experimental.read_lazy`` on an AnnData Zarr store (spots as obs), the
    mask from the lazy id column, the subset, ``.to_memory()``."""

    label = "AnnData (read_lazy + subset)"
    ext = ".anndata.zarr"
    key = "anndata"

    def __init__(self):
        self.diag = {"mask_s": [], "to_memory_s": []}

    @staticmethod
    def write(cd, path):
        C.to_spot_anndata(cd).write_zarr(path)

    def open(self, path):
        from anndata.experimental import read_lazy
        self.adata = read_lazy(str(path))

    def ids(self):                                            # not timed
        obs = self.adata.obs
        return {lv: list(pd.unique(np.asarray(obs[col].to_numpy()).astype(str)))
                for lv, col in (("trace", "trace_id"), ("cell", "cell_id"), ("chrom", "chrom"))}

    def get(self, level, key):
        col = {"trace": "trace_id", "cell": "cell_id", "chrom": "chrom"}[level]
        t0 = time.perf_counter()
        mask = (self.adata.obs[col] == key).to_numpy()
        t1 = time.perf_counter()
        sub = self.adata[mask].to_memory()
        self.diag["mask_s"].append(t1 - t0)
        self.diag["to_memory_s"].append(time.perf_counter() - t1)
        return sub


class AnnDataLazyH5ad(AnnDataLazy):
    """The same lazy read on the ``.h5ad`` file of ``anndata-memory`` (``read_lazy`` on an h5py file)."""

    label = "AnnData (read_lazy on .h5ad + subset)"
    ext = ".h5ad"

    @staticmethod
    def write(cd, path):
        C.FORMATS["anndata"].write(cd, path)

    def open(self, path):
        import h5py
        from anndata.experimental import read_lazy
        self.file = h5py.File(path, "r")
        self.adata = read_lazy(self.file)


class FofctMemory(H5cd1xMemory):
    """Baseline: load the FOF-CT core table (``ChromData.from_fofct``; file
    written by the official ``uchrom.io.write_fofct``), then the in-memory
    ``get_*`` (boolean-mask scan)."""

    label = "FOF-CT (load + subset)"
    ext = ".csv"

    @staticmethod
    def write(cd, path):
        C.FORMATS["fofct"].write(cd, path)

    def open(self, path):
        from uchrom import ChromData
        self.cd = ChromData.from_fofct(path)


class SpatialDataLazy:
    """Baseline: SpatialData (scverse).  Spots as a 3-D points element
    (``_common.to_spatialdata``); open = ``spatialdata.read_zarr`` (points are
    a lazy dask DataFrame); a query = the idiomatic dask filter on the id
    column + ``.compute()`` (``pts[pts.trace_id == id].compute()``).  Its
    spatial queries (bounding box, polygon) do not address genomic ids."""

    label = "SpatialData (lazy open + filter)"
    ext = ".sdata.zarr"

    @staticmethod
    def write(cd, path):
        C.FORMATS["spatialdata"].write(cd, path)

    def open(self, path):
        import spatialdata as sd
        self.sdata = sd.read_zarr(path)
        self.pts = self.sdata.points["spots"]

    def ids(self):
        keys = self.pts[["trace_id", "cell_id", "chrom"]].compute()   # not timed
        return {lv: list(keys[col].astype(str).unique()) for lv, col in
                (("trace", "trace_id"), ("cell", "cell_id"), ("chrom", "chrom"))}

    def get(self, level, key):
        col = {"trace": "trace_id", "cell": "cell_id", "chrom": "chrom"}[level]
        return self.pts[self.pts[col] == key].compute()


BACKENDS = {"h5cd-1x-memory": H5cd1xMemory, "h5cd-2-memory": H5cd2Memory,
            "zarr-backed": ZarrBacked, "zarr-memory": ZarrMemory,
            "parquet-memory": ParquetMemory, "anndata-memory": AnnDataMemory, "anndata-lazy": AnnDataLazy,
            "anndata-lazy-h5ad": AnnDataLazyH5ad, "fofct-memory": FofctMemory, "spatialdata-lazy": SpatialDataLazy}


def child(backend_key, path, n_queries):
    be = BACKENDS[backend_key]()
    import h5py  # noqa: F401  (import cost out of the timing)
    from uchrom import ChromData  # noqa: F401
    if backend_key == "spatialdata-lazy":
        import spatialdata  # noqa: F401
    if backend_key.startswith("anndata-lazy"):
        import anndata.experimental, dask.array, xarray  # noqa: F401,E401
    try:
        import pyarrow.parquet, zarr, anndata  # noqa: F401,E401
        import chromdata.backed  # noqa: F401
    except ImportError:  # 1.x checkout
        pass
    base = C.current_rss_mb()
    t0 = time.perf_counter()
    be.open(Path(path))
    open_s = time.perf_counter() - t0
    rss_open = C.current_rss_mb()
    ids = be.ids()
    rng = np.random.default_rng(0)
    out = {"open_s": open_s, "rss_after_open_mb": rss_open, "baseline_rss_mb": base}
    levels = ["trace", "cell", "chrom"]
    if getattr(be, "coords_levels", False):
        levels += ["trace_coords", "cell_coords", "chrom_coords"]
    for level in levels:
        if level == "chrom":
            out["rss_after_trace_cell_mb"] = C.current_rss_mb()
            out["peak_rss_trace_cell_mb"] = C.peak_rss_mb()
        pool = ids[level.split("_")[0]]
        picks = rng.choice(len(pool), int(n_queries),
                           replace=len(pool) < int(n_queries) or level.startswith("chrom"))
        be.get(level, pool[picks[0]])  # warm-up (first-call imports / caches), not timed
        times, sizes = [], []
        for i in picks:
            t0 = time.perf_counter()
            sub = be.get(level, pool[i])
            times.append(time.perf_counter() - t0)
            sizes.append(int(sub.n_spots) if hasattr(sub, "n_spots") else len(sub))
        out[level] = {"latency_s": C.iqr(times), "times_s": times, "result_spots_median": float(np.median(sizes)),
                      "n_ids": len(pool)}
        if getattr(be, "diag", None):                       # per-query parts (timed queries only)
            out[level]["diag"] = {k: C.iqr(v[-len(picks):]) for k, v in be.diag.items() if v}
            for v in be.diag.values():
                v.clear()
    out["peak_rss_mb"] = C.peak_rss_mb()
    C.emit(out)


def _pool_repeats(runs):
    """Several fresh-process runs of one (backend, size) → one record: query
    times pooled over the runs (median / IQR), open time and memory as the
    median of the runs; the per-run summaries are kept under ``repeats``."""
    import statistics

    out = dict(runs[0])
    for key in ("open_s", "rss_after_open_mb", "baseline_rss_mb", "rss_after_trace_cell_mb",
                "peak_rss_trace_cell_mb", "peak_rss_mb"):
        vals = [r[key] for r in runs if r.get(key) is not None]
        if vals:
            out[key] = statistics.median(vals)
    for level in [k for k, v in runs[0].items() if isinstance(v, dict) and "times_s" in v]:
        times = [t for r in runs for t in r[level]["times_s"]]
        out[level] = {**runs[0][level], "latency_s": C.iqr(times), "times_s": times}
    out["repeats"] = [{"open_s": r["open_s"], **{lv: r[lv]["latency_s"]["median"] for lv in r
                                                 if isinstance(r[lv], dict) and "latency_s" in r[lv]}}
                      for r in runs]
    return out


def child_write(backend_key, stage, out):
    cd = C.load_stage(Path(stage))
    BACKENDS[backend_key].write(cd, out)
    C.emit({"bytes": C.size_bytes(Path(out))})


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sizes", default="1e4,1e5,1e6,1e7")
    ap.add_argument("--queries", type=int, default=20)
    ap.add_argument("--repeats", type=int, default=3,
                    help="fresh processes per (backend, size); query times are pooled")
    ap.add_argument("--backends", default="h5cd-1x-memory")
    ap.add_argument("--prebuilt", action="append", default=[], metavar="N=PATH",
                    help="zarr backends: use this store for size N instead of staging + writing "
                         "one (e.g. a 1e8-spot store from replicate_store.py); repeatable")
    ap.add_argument("--out-json", type=Path, default=None,
                    help="write the series to this file (with benchmarks/_record.py provenance) instead of merging "
                         "them into the paper's c_access.json")
    ap.add_argument("--child", nargs="+", help=argparse.SUPPRESS)
    args = ap.parse_args()
    if args.child:
        if args.child[0] == "write":
            return child_write(*args.child[1:])
        return child(*args.child)

    from uchrom.io._h5cd_legacy import FORMAT_VERSION

    sizes = [int(float(s)) for s in args.sizes.split(",")]
    prebuilt = {int(float(k)): Path(v) for k, v in (p.split("=", 1) for p in args.prebuilt)}
    work = C.WORK / "c_access"
    work.mkdir(parents=True, exist_ok=True)
    series = {}
    for key in args.backends.split(","):
        be = BACKENDS[key]
        points = []
        for n in sizes:
            if n in prebuilt and key.startswith("zarr"):
                h5 = prebuilt[n]
                meta = json.loads((h5 / "zarr.json").read_text())["attributes"]["uchrom"]
                info = {"n_spots": meta["n_spots"], "n_cells": meta["n_cells"],
                        "replicated": bool(meta.get("replicated")),
                        "prebuilt": str(h5), "replicated_from": meta.get("replicated")}
            else:
                stage = C.stage_subset(n)
                info = C.stage_info(stage)
                tag = ("h5cd2" if key == "h5cd-2-memory"
                       else f"zarr{_zarr_version().replace('.', '')}" if key.startswith("zarr")
                       else key.split("-")[0] if key in ("parquet-memory", "anndata-memory", "anndata-lazy",
                                                         "anndata-lazy-h5ad", "fofct-memory", "spatialdata-lazy")
                       else f"v{FORMAT_VERSION}")
                h5 = work / f"n{n}_{tag}{be.ext}"
                if not h5.exists():
                    C.run_child(SCRIPT, ["--child", "write", key, str(stage), str(h5)])
            r = _pool_repeats([C.run_child(SCRIPT, ["--child", key, str(h5), str(args.queries)])
                               for _ in range(args.repeats)])
            points.append({"n_target": n, "n_spots": info["n_spots"], "n_cells": info["n_cells"],
                           "replicated": info["replicated"], "file_mb": C.size_bytes(h5) / 2**20,
                           **({"prebuilt": info["prebuilt"], "replicated_from": info["replicated_from"]}
                              if "prebuilt" in info else {}), **r})
            print(f"{be.label:28s} n={info['n_spots']:>11,}  open {r['open_s']:7.2f} s  "
                  + "  ".join(f"{lv} {r[lv]['latency_s']['median'] * 1e3:8.2f} ms" for lv in ("trace", "cell", "chrom")),
                  flush=True)
        series[be.label] = {"backend": key, "points": points, "repeats": args.repeats,
                            "format_version": _zarr_version() if key.startswith("zarr") else FORMAT_VERSION,
                            "page_cache": "warm (fresh process; OS cache not flushed)"}
        doc = {"panel": "c", "machine": C.machine_info(), "queries_per_level": args.queries,
               "dataset": "Takei 2025 cerebellum rep 1 whole-cell subsets (see b_storage.json)", "series": series}
        if args.out_json is None:
            C.write_json("c_access", doc, merge_key="series")
        else:
            from _record import save
            save(args.out_json, doc, script="benchmarks/fig2/c_access.py", datasets=["takei2025_cerebellum"],
                 params={"sizes": sizes, "queries": args.queries, "repeats": args.repeats,
                         "backends": args.backends.split(","), "work": str(work)})
    print(args.out_json or C.RESULTS / "c_access.json")


if __name__ == "__main__":
    main()
