"""Shared helpers for the Figure 2 benchmarks (``benchmarks/fig2/*.py``).

* paths: repo root, example-data (``$UCHROM_EXAMPLE_DATA`` overrides), results
  (``paper/fig2/results``) and a scratch work dir (``$UCHROM_FIG2_WORK``);
* ``machine_info()`` — CPU / RAM / disk / OS / library versions for the JSON;
* ``run_child()`` — run one measurement in a fresh interpreter and collect its
  JSON (timings + peak RSS), so every trial starts with a cold Python heap;
* ``FORMATS`` — the storage formats compared in panel b.  Each is a small
  class with ``write(cd, path)`` / ``read(path)``.  The ``h5cd`` entry is
  labelled from ``uchrom.core.cdata.FORMAT_VERSION`` (the "h5cd 1.x" series
  was measured on a 1.x checkout); ``h5cd2`` ("h5cd 2.0", the HDF5 writer of
  format 2.0) and ``zarr`` ("chromdata.zarr 2.0", the Zarr + Parquet
  container) need a 2.0 checkout.  Series are merged by label into the JSON;
* ``size_bytes()`` — file or directory (a ``.chromdata.zarr`` store) size;
* Takei 2025 whole-cell subsets for the scaling series (``stage_subset``).
"""

from __future__ import annotations

import json
import os
import pickle
import platform
import resource
import shutil
import statistics
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))  # this checkout's uchrom, not an installed copy

from uchrom.datasets import example_data_dir, example_path  # noqa: E402

DATA = example_data_dir()  # $UCHROM_EXAMPLE_DATA, else this checkout's example-data/
RESULTS = ROOT / "paper" / "fig2" / "results"
WORK = Path(os.environ.get("UCHROM_FIG2_WORK", example_path("generated", "fig2_work")))

TAKEI_DIR = example_path("takei2025_cerebellum")
TAKEI_COMBINED = TAKEI_DIR / "takei2025_cerebellum_rep1.h5cd"


# ----------------------------------------------------------------------------- measurement

def peak_rss_mb() -> float:
    """Peak resident set size of this process (MB)."""
    r = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return r / 2**20 if sys.platform == "darwin" else r / 1024


def current_rss_mb() -> float:
    try:
        import psutil
        return psutil.Process().memory_info().rss / 2**20
    except ImportError:  # pragma: no cover
        return float("nan")


def run_child(script: Path, args: List[str], timeout: Optional[float] = None) -> Dict[str, Any]:
    """Run ``python script args…`` in a fresh interpreter; the child prints one
    ``__RESULT__{json}`` line.  Raises with the child's stderr on failure."""
    proc = subprocess.run([sys.executable, str(script), *args], capture_output=True, text=True, timeout=timeout)
    if proc.returncode != 0 or "__RESULT__" not in proc.stdout:
        raise RuntimeError(f"child {script.name} {args} failed (rc={proc.returncode}):\n{proc.stderr[-4000:]}")
    return json.loads(proc.stdout.rsplit("__RESULT__", 1)[1].strip().splitlines()[0])


def emit(result: Dict[str, Any]) -> None:
    print("__RESULT__" + json.dumps(result), flush=True)


def summarize(values: List[float]) -> Dict[str, float]:
    v = [float(x) for x in values if x is not None and np.isfinite(x)]
    if not v:
        return {"median": None, "min": None, "max": None, "n": 0}
    return {"median": statistics.median(v), "min": min(v), "max": max(v), "n": len(v)}


def iqr(values: List[float]) -> Dict[str, float]:
    a = np.asarray(values, dtype=float)
    q1, med, q3 = np.percentile(a, [25, 50, 75])
    return {"median": float(med), "q1": float(q1), "q3": float(q3), "min": float(a.min()),
            "max": float(a.max()), "n": int(a.size)}


def machine_info() -> Dict[str, Any]:
    def sh(cmd):
        try:
            return subprocess.run(cmd, capture_output=True, text=True, timeout=10).stdout.strip()
        except Exception:
            return None

    info: Dict[str, Any] = {"os": f"{platform.system()} {platform.release()}", "platform": platform.platform(),
                            "python": platform.python_version(), "machine": platform.machine()}
    if sys.platform == "darwin":
        info["cpu"] = sh(["sysctl", "-n", "machdep.cpu.brand_string"])
        info["n_cpu"] = int(sh(["sysctl", "-n", "hw.ncpu"]) or 0)
        info["ram_gb"] = round(int(sh(["sysctl", "-n", "hw.memsize"]) or 0) / 2**30, 1)
        info["os"] = f"macOS {sh(['sw_vers', '-productVersion'])} ({platform.release()})"
        disk = sh(["diskutil", "info", "/"]) or ""
        keep = ("Device / Media Name", "Solid State", "Protocol", "File System Personality")
        info["disk"] = "; ".join(l.split(":", 1)[0].strip() + "=" + l.split(":", 1)[1].strip()
                                 for l in disk.splitlines() if l.split(":", 1)[0].strip() in keep)
    else:
        info["cpu"] = platform.processor()
        info["n_cpu"] = os.cpu_count()
        try:
            import psutil
            info["ram_gb"] = round(psutil.virtual_memory().total / 2**30, 1)
        except ImportError:
            pass
    usage = shutil.disk_usage(WORK if WORK.exists() else ROOT)
    info["work_dir_free_gb"] = round(usage.free / 1e9, 1)
    vers = {}
    from importlib.metadata import PackageNotFoundError, version
    for mod in ("numpy", "pandas", "h5py", "pyarrow", "zarr", "anndata", "cooler", "psutil", "scipy"):
        try:
            vers[mod] = version(mod)
        except PackageNotFoundError:
            vers[mod] = None
    from uchrom.core.cdata import FORMAT_VERSION
    vers["uchrom_h5cd_format"] = FORMAT_VERSION
    try:
        vers["uchrom_git"] = sh(["git", "-C", str(ROOT), "rev-parse", "--short", "HEAD"])
    except Exception:
        pass
    info["versions"] = vers
    return info


def write_json(name: str, payload: Dict[str, Any], merge_key: Optional[str] = None) -> Path:
    """Write ``paper/fig2/results/<name>.json``.  With ``merge_key``, series in
    ``payload[merge_key]`` are merged into an existing file's (other series,
    e.g. a 2.x run, are kept)."""
    RESULTS.mkdir(parents=True, exist_ok=True)
    path = RESULTS / f"{name}.json"
    if merge_key and path.exists():
        old = json.loads(path.read_text())
        merged = dict(old.get(merge_key, {}))
        merged.update(payload.get(merge_key, {}))
        payload = {**old, **payload, merge_key: merged}
    path.write_text(json.dumps(payload, indent=1, default=_jsonable))
    return path


def _jsonable(o):
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        return float(o)
    if isinstance(o, np.ndarray):
        return o.tolist()
    if isinstance(o, Path):
        return str(o)
    raise TypeError(type(o))


def size_bytes(path: Path) -> int:
    """Size of a file, or of every file under a directory store."""
    path = Path(path)
    if path.is_dir():
        return sum(f.stat().st_size for f in path.rglob("*") if f.is_file())
    return path.stat().st_size


def remove(path: Path) -> None:
    path = Path(path)
    if path.is_dir():
        shutil.rmtree(path)
    elif path.exists():
        path.unlink()


def timed(fn: Callable, *a, **kw):
    t0 = time.perf_counter()
    out = fn(*a, **kw)
    return out, time.perf_counter() - t0


# ----------------------------------------------------------------------------- formats

FOFCT_CORE = ["Spot_ID", "Trace_ID", "X", "Y", "Z", "Chrom", "Chrom_Start", "Chrom_End", "Cell_ID"]


def write_fofct(cd, path: Path, *, assembly: Optional[str] = None, unit: Optional[str] = None) -> None:
    """Minimal FOF-CT v0.1 core-table writer (uchrom has a reader,
    ``ChromData.from_fofct``, but no writer yet).  Extra spot columns and all
    ``tracks`` columns follow the core columns, as FOF-CT allows."""
    spots = cd.spots
    df = pd.DataFrame({
        "Spot_ID": spots["spot_id"].to_numpy() if "spot_id" in spots else np.arange(cd.n_spots),
        "Trace_ID": spots["trace_id"].astype(str).to_numpy(),
        "X": cd.coords[:, 0], "Y": cd.coords[:, 1], "Z": cd.coords[:, 2],
        "Chrom": spots["chrom"].astype(str).to_numpy(),
        "Chrom_Start": spots["start"].to_numpy(), "Chrom_End": spots["end"].to_numpy(),
    })
    if "cell_id" in spots:
        df["Cell_ID"] = spots["cell_id"].astype(str).to_numpy()
    for c in spots.columns:
        if c not in ("spot_id", "trace_id", "chrom", "start", "end", "cell_id"):
            df[c] = spots[c].to_numpy()
    if cd.tracks is not None:
        for c in cd.tracks.columns:
            df[c] = cd.tracks[c].to_numpy()
    header = ["##FOF-CT_version=v0.1", "##Table_namespace=4dn_FOF-CT_core",
              f"##genome_assembly={assembly or cd.uns.get('genome_assembly', 'unknown')}",
              f"##XYZ_unit={unit or cd.uns.get('xyz_unit', 'micron')}",
              "##columns=(" + ",".join(df.columns) + ")"]
    with open(path, "w") as fh:
        fh.write("\n".join(header) + "\n")
        df.to_csv(fh, header=False, index=False)


def flat_table(cd) -> pd.DataFrame:
    """The flat spot table: spots + x/y/z + tracks (one row per spot)."""
    df = cd.to_dataframe()
    if cd.tracks is not None:
        df = pd.concat([df, cd.tracks.reset_index(drop=True)], axis=1)
    return df


def to_spot_anndata(cd):
    """AnnData with **spots as obs**: spot columns + tracks in ``obs``, coords
    in ``obsm['spatial']``, an empty (n_spots × 0) X."""
    import anndata as ad

    obs = cd.spots.copy()
    if cd.tracks is not None:
        obs = pd.concat([obs, cd.tracks.reset_index(drop=True)], axis=1)
    obs.index = pd.RangeIndex(len(obs)).astype(str)
    return ad.AnnData(X=np.zeros((len(obs), 0), dtype=np.float32), obs=obs,
                      obsm={"spatial": np.asarray(cd.coords)})


class Format:
    label: str
    ext: str

    def write(self, cd, path: Path) -> None:  # pragma: no cover - interface
        raise NotImplementedError

    def read(self, path: Path):  # pragma: no cover - interface
        raise NotImplementedError


class FofctCSV(Format):
    label, ext = "FOF-CT / CSV", ".csv"

    def write(self, cd, path):
        write_fofct(cd, path)

    def read(self, path):
        from uchrom import ChromData
        return ChromData.from_fofct(path)


class Parquet(Format):
    label, ext = "Parquet", ".parquet"

    def write(self, cd, path):
        flat_table(cd).to_parquet(path, engine="pyarrow", index=False)  # pyarrow default: snappy

    def read(self, path):
        return pd.read_parquet(path, engine="pyarrow")


class AnnDataSpots(Format):
    label, ext = "AnnData (spots as obs)", ".h5ad"

    def write(self, cd, path):
        to_spot_anndata(cd).write_h5ad(path)

    def read(self, path):
        import anndata as ad
        return ad.read_h5ad(path)


class H5cd(Format):
    """``cd.write`` / ``ChromData.read`` of whatever format this checkout writes."""
    ext = ".h5cd"

    @property
    def label(self):
        from uchrom.core.cdata import FORMAT_VERSION
        return f"h5cd {FORMAT_VERSION.split('.')[0]}.x"

    def write(self, cd, path):
        cd.write(path)

    def read(self, path):
        from uchrom import ChromData
        return ChromData.read(path)


class H5cd2(Format):
    """HDF5 ``.h5cd`` written by format 2.0 (#65; deprecated for writing)."""
    label, ext = "h5cd 2.0", ".h5cd"

    def write(self, cd, path):
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            cd.write(path, format="h5cd")

    def read(self, path):
        from uchrom import ChromData
        return ChromData.read(path)


class ChromDataZarr(Format):
    """The format 2.0 container: Zarr v3 + Parquet (``cd.write`` defaults)."""
    label, ext = "chromdata.zarr 2.0", ".chromdata.zarr"
    options: Dict[str, Any] = {}

    def write(self, cd, path):
        cd.write(path, **self.options)

    def read(self, path):
        from uchrom import ChromData
        return ChromData.read(path)


class ChromDataZarrF32(ChromDataZarr):
    label = "chromdata.zarr 2.0 (float32 coords)"
    options = {"coord_dtype": "float32"}


FORMATS: Dict[str, Format] = {k: f for k, f in (("fofct", FofctCSV()), ("parquet", Parquet()),
                                                 ("anndata", AnnDataSpots()), ("h5cd", H5cd()),
                                                 ("h5cd2", H5cd2()), ("zarr", ChromDataZarr()),
                                                 ("zarr_f32", ChromDataZarrF32()))}


# ----------------------------------------------------------------------------- real-data subsets

def load_takei_all():
    from uchrom import ChromData
    if not TAKEI_COMBINED.exists():
        raise SystemExit(f"{TAKEI_COMBINED} missing — run example-data/takei2025_cerebellum/build.py")
    return ChromData.read(TAKEI_COMBINED)


def subset_by_cells(cd, n_target: int, seed: int = 0):
    """Whole cells (random order, fixed seed) until ≥ n_target spots; above the
    real size, whole copies of real cells with new cell / trace ids.
    Returns (ChromData, info)."""
    from uchrom import ChromData

    cell = cd.spots["cell_id"]
    codes = cell.cat.codes.to_numpy()
    counts = np.bincount(codes, minlength=len(cell.cat.categories))
    order = np.random.default_rng(seed).permutation(len(counts))
    order = order[counts[order] > 0]
    total = int(counts.sum())
    if n_target <= total:
        csum = np.cumsum(counts[order])
        k = int(np.searchsorted(csum, n_target) + 1)
        chosen = order[:k]
        sub = cd[np.isin(codes, chosen)]
        return sub, {"n_target": n_target, "n_spots": int(sub.n_spots), "n_cells": int(k),
                     "replicated": False, "n_copies": 1}
    # replicate the whole dataset, then top up with whole cells
    reps, parts = n_target // total, []
    rest = n_target - reps * total
    for r in range(reps + (1 if rest else 0)):
        part = cd if r < reps else subset_by_cells(cd, rest, seed=seed + r)[0]
        if r:
            part = _relabel(part, f"r{r}")
        parts.append(part)
    out = concat_chromdata(parts)
    return out, {"n_target": n_target, "n_spots": int(out.n_spots), "n_cells": int(out.n_cells),
                 "replicated": True, "n_copies": len(parts)}


def _relabel(cd, tag: str):
    """Copy with ``<id>_<tag>`` cell / trace ids (spots, cells, traces)."""
    from uchrom import ChromData

    spots = cd.spots.copy()
    for col in ("cell_id", "trace_id"):
        spots[col] = spots[col].cat.rename_categories(lambda s: f"{s}_{tag}")
    cells = cd.cells.copy()
    cells.index = pd.Index([f"{s}_{tag}" for s in cells.index], name=cells.index.name)
    traces = cd.traces.copy()
    traces.index = pd.Index([f"{s}_{tag}" for s in traces.index], name=traces.index.name)
    return ChromData(cd.coords, spots, cells=cells, cellm=dict(cd.cellm), tracks=cd.tracks,
                     traces=traces, uns=dict(cd.uns), validate=False)


def concat_chromdata(parts):
    from pandas.api.types import union_categoricals
    from uchrom import ChromData

    spots = {}
    for col in parts[0].spots.columns:
        cols = [p.spots[col] for p in parts]
        if all(isinstance(c.dtype, pd.CategoricalDtype) for c in cols):
            spots[col] = union_categoricals(cols, ignore_order=True)
        else:
            spots[col] = np.concatenate([c.to_numpy() for c in cols])
    tracks = (pd.concat([p.tracks for p in parts], ignore_index=True)
              if parts[0].tracks is not None else None)
    cellm = {k: np.concatenate([p.cellm[k] for p in parts]) for k in parts[0].cellm}
    return ChromData(np.concatenate([p.coords for p in parts]), pd.DataFrame(spots),
                     cells=pd.concat([p.cells for p in parts]), cellm=cellm, tracks=tracks,
                     traces=pd.concat([p.traces for p in parts]), uns=dict(parts[0].uns), validate=False)


def stage_subset(n_target: int, *, schema: str = "full", seed: int = 0, _cache: dict = {}) -> Path:
    """Pickle of a whole-cell Takei 2025 subset (cached in WORK/stage).
    ``schema='core'`` drops ``tracks`` (coords + spots + cells only)."""
    stage = WORK / "stage"
    stage.mkdir(parents=True, exist_ok=True)
    path = stage / f"takei_{schema}_{n_target:.0e}.pkl".replace("+", "")
    info_path = path.with_suffix(".json")
    if path.exists() and info_path.exists():
        return path
    if "all" not in _cache:
        _cache["all"] = load_takei_all()
    cd, info = subset_by_cells(_cache["all"], n_target, seed=seed)
    if schema == "core":
        cd.tracks = None
    info["schema"] = schema
    with open(path, "wb") as fh:
        pickle.dump(cd, fh, protocol=5)
    info_path.write_text(json.dumps(info))
    return path


def stage_info(path: Path) -> Dict[str, Any]:
    return json.loads(Path(path).with_suffix(".json").read_text())


def load_stage(path: Path):
    with open(path, "rb") as fh:
        cd = pickle.load(fh)
    if "_bins" not in cd.__dict__ and "spots" in cd.__dict__:
        cd = _upgrade_1x_object(cd)
    return cd


def _upgrade_1x_object(old):
    """A ChromData pickled by a 1.x checkout (spot loci, spot-aligned
    ``tracks``) → the 2.0 object ``ChromData.read`` makes of the same data
    (bins from the loci, tracks split), so the staged subsets are reused."""
    from uchrom import ChromData

    d = old.__dict__
    cd = ChromData(d["coords"], d["spots"], cells=d.get("cells"), cellm=d.get("cellm") or None,
                   traces=d.get("traces"), layers=d.get("layers") or None,
                   results=dict(d.get("results") or {}), uns=d.get("uns") or None,
                   points=d.get("points") or None)
    tracks = d.get("tracks")
    if tracks is not None and len(tracks.columns):
        cd._set_spot_aligned_tracks(tracks)
    return cd
