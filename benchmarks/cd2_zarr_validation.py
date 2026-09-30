"""Real-data validation of the ``.chromdata.zarr`` container (format 2.0).

For every example dataset (all catalogued in ``example-data/README.md``):

1. **convert** — ``uchrom.io.upgrade_h5cd`` from the 1.x ``.h5cd`` (or
   ``ChromData.from_fofct`` for the Takei 2021 FOF-CT) to
   ``.chromdata.zarr`` in a fresh process: wall time and peak RSS.  The same
   source is also written as HDF5 2.0 (``.h5cd``, the #65 format, with the
   legacy writer ``uchrom.io._h5cd_legacy.write_h5cd`` — ``.h5cd`` is no longer
   a ChromData format) and as a zarr store with float32 coords, for the size
   comparison.  The 1.x ``mESC_Sox2_5cells_wnan.h5cd`` source is in git
   history (the repo now has the converted store).
2. **verify** — a fresh process reads the source and the zarr store with
   ``original_order=True`` (the spots are stored sorted by cell / trace /
   bin; ``index/source_row`` restores the written order) and checks value
   identity: ``to_dataframe()`` / spots with loci (dtypes and categories
   included), coords (NaN-aware), bins, bin- and spot-level tracks, cells,
   traces, cellm, binm, layers, points, results (values + provenance) and
   uns.  It also checks that the sorted (default) read holds the same spots,
   and that a backed open returns the same ``get_cell`` / ``get_trace`` as
   the in-memory object.

The sources are never modified (outputs go to ``--work``).  Run the big
datasets one at a time (the 1.x reader of the 10.9 M-spot Takei file peaks
at ~22 GB).

    python benchmarks/cd2_zarr_validation.py --data /path/to/example-data --work /tmp/cd2z \\
        [--only takei2025_cerebellum,liu2025_mop,...]
"""

from __future__ import annotations

import argparse
import json
import resource
import subprocess
import sys
import time
import warnings
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))

DATASETS = {
    # name: (source relative to --data, kind)
    "mESC_Sox2_5cells_wnan": ("mESC_Sox2_5cells_wnan.h5cd", "h5cd"),
    "sim_cell1": ("sim_cell1/sim_cell1.h5cd", "h5cd"),
    "takei2021_fofct": ("4DNFIHF3JCBY.csv", "fofct"),
    "schicar_mop": ("schicar_mop/schicar_mop.h5cd", "h5cd"),
    "takei2025_fov0": ("takei2025_fov0/takei2025_fov0.h5cd", "h5cd"),
    "liu2025_mop": ("liu2025_mop/liu2025_mop.h5cd", "h5cd"),
    "takei2025_cerebellum": ("takei2025_cerebellum/takei2025_cerebellum_rep1.h5cd", "h5cd"),
}


def peak_rss_gb() -> float:
    r = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return r / 2**30 if sys.platform == "darwin" else r / 2**20


def size_bytes(p: Path) -> int:
    p = Path(p)
    if p.is_dir():
        return sum(f.stat().st_size for f in p.rglob("*") if f.is_file())
    return p.stat().st_size


def emit(obj) -> None:
    print("__RESULT__" + json.dumps(obj), flush=True)


def load_source(src: Path, kind: str):
    from uchrom import ChromData

    if kind == "fofct":
        data = src.parent
        return ChromData.from_fofct(src, cell_table=data / "4DNFIFINA2U9.csv",
                                    rna_table=data / "4DNFIJ52NVDV.csv")
    if kind == "h5cd":
        from uchrom.io._h5cd_legacy import read_h5cd
        return read_h5cd(src)
    return ChromData.read(src)


# ----------------------------------------------------------------------------- children

def child_convert(src, kind, dst, opts):
    warnings.simplefilter("ignore")
    opts = json.loads(opts)
    t0 = time.perf_counter()
    if kind == "h5cd" and not opts:
        from uchrom.io import upgrade_h5cd
        upgrade_h5cd(src, dst, overwrite=True)
        t_read = None
    else:
        cd = load_source(Path(src), kind)
        t_read = time.perf_counter() - t0
        if opts.pop("format", None) == "h5cd":
            from uchrom.io._h5cd_legacy import write_h5cd
            write_h5cd(cd, dst, **opts)
        else:
            cd.write(dst, **opts)
    emit({"seconds": time.perf_counter() - t0, "read_s": t_read, "peak_rss_gb": peak_rss_gb(),
          "bytes": size_bytes(Path(dst))})


def _same_frame(a, b, what):
    import pandas as pd
    pd.testing.assert_frame_equal(a, b, check_exact=True, obj=what)


def _same_value(a, b, what):
    import numpy as np
    import pandas as pd
    if isinstance(a, pd.DataFrame):
        _same_frame(pd.DataFrame(a), pd.DataFrame(b), what)
    elif isinstance(a, pd.Series):
        pd.testing.assert_series_equal(a, b, obj=what)
    elif isinstance(a, np.ndarray):
        assert isinstance(b, np.ndarray) and a.shape == b.shape, what
        assert np.array_equal(a, b, equal_nan=a.dtype.kind == "f"), what
    elif isinstance(a, dict):
        assert list(map(str, a)) == list(map(str, b)), (what, list(a), list(b))
        for k in a:
            _same_value(a[k], b[str(k)] if str(k) in b else b[k], f"{what}[{k!r}]")
    elif isinstance(a, float) and a != a:
        assert b != b, what
    else:
        assert a == b, (what, a, b)


def child_verify(src, kind, dst):
    warnings.simplefilter("ignore")
    import numpy as np
    import pandas as pd
    from uchrom import ChromData

    t0 = time.perf_counter()
    a = load_source(Path(src), kind)
    t_src = time.perf_counter() - t0
    t0 = time.perf_counter()
    b = ChromData.read(dst, original_order=True)
    t_dst = time.perf_counter() - t0
    checks = []

    def ok(name):
        checks.append(name)

    assert a.n_spots == b.n_spots
    assert np.array_equal(a.coords, b.coords, equal_nan=True)
    ok("coords")
    _same_frame(a.spots_with_loci(), b.spots_with_loci(), "spots (with loci)")
    ok("spots+loci")
    _same_frame(a.bins, b.bins, "bins")
    ok("bins")
    _same_frame(a.bin_tracks, b.bin_tracks, "bin_tracks")
    _same_frame(a.spot_tracks, b.spot_tracks, "spot_tracks")
    assert a._spot_view_order == b._spot_view_order
    ok(f"tracks ({len(a.bin_tracks.columns)} bin / {len(a.spot_tracks.columns)} spot)")
    for name in ("cells", "traces"):
        _same_frame(getattr(a, name), getattr(b, name), name)
    ok("cells+traces")
    for name in ("cellm", "binm", "layers"):
        _same_value(dict(getattr(a, name)), dict(getattr(b, name)), name)
    ok("cellm+binm+layers")
    _same_value(dict(a.points), dict(b.points), "points")
    ok(f"points ({sum(len(v) for v in a.points.values())} rows)")
    assert list(a.results) == list(b.results)
    for k in a.results:
        _same_value(a.results[k], b.results[k], f"results[{k!r}]")
        assert a.results.record(k).provenance == b.results.record(k).provenance
    for k in a.intervals:
        _same_frame(pd.DataFrame(a.intervals[k]), pd.DataFrame(b.intervals[k]), f"intervals[{k!r}]")
    ok(f"results ({len(a.results)}) + intervals ({len(a.intervals)})")
    _same_value(dict(a.uns), dict(b.uns), "uns")
    ok("uns")
    del b
    # the default (sorted) read: the same spots, keyed by row of the source
    c = ChromData.read(dst)
    src_row = __import__("zarr").open_group(str(dst), mode="r")["index/source_row"][:] \
        if Path(dst).is_dir() and (Path(dst) / "index" / "source_row").exists() else np.arange(c.n_spots)
    assert np.array_equal(c.coords, a.coords[src_row], equal_nan=True)
    _same_frame(c.to_dataframe().drop(columns=["x", "y", "z"]),
                a.to_dataframe().drop(columns=["x", "y", "z"]).iloc[src_row].reset_index(drop=True),
                "sorted to_dataframe")
    ok("sorted read = source rows via index/source_row")
    # backed access
    t0 = time.perf_counter()
    bk = ChromData.read(dst, backed=True)
    t_open = time.perf_counter() - t0
    rng = np.random.default_rng(0)
    if a.n_spots:
        if "cell_id" in c.spots.columns:
            for cell in rng.choice(np.asarray(c.spots["cell_id"].cat.categories), 3):
                _same_frame(c.get_cell(cell).to_dataframe(), bk.get_cell(cell).to_dataframe(), "get_cell")
        for tr in rng.choice(np.asarray(c.spots["trace_id"].cat.categories), 3):
            _same_frame(c.get_trace(tr).to_dataframe(), bk.get_trace(tr).to_dataframe(), "get_trace")
        ok("backed get_cell/get_trace = in memory")
    emit({"identical": True, "checks": checks, "read_src_s": t_src, "read_zarr_s": t_dst,
          "backed_open_s": t_open, "peak_rss_gb": peak_rss_gb()})


# ----------------------------------------------------------------------------- driver

def run_child(args, timeout=3600):
    proc = subprocess.run([sys.executable, __file__, "--child", *args], capture_output=True,
                          text=True, timeout=timeout)
    if proc.returncode != 0 or "__RESULT__" not in proc.stdout:
        raise RuntimeError(f"child {args} failed:\n{proc.stderr[-3000:]}")
    return json.loads(proc.stdout.rsplit("__RESULT__", 1)[1].strip().splitlines()[0])


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", type=Path, default=ROOT / "example-data")
    ap.add_argument("--work", type=Path, required=False)
    ap.add_argument("--only")
    ap.add_argument("--out", type=Path, help="write the results as JSON")
    ap.add_argument("--child", nargs="+", help=argparse.SUPPRESS)
    args = ap.parse_args()
    if args.child:
        kind, *rest = args.child
        return {"convert": child_convert, "verify": child_verify}[kind](*rest)

    work = args.work
    work.mkdir(parents=True, exist_ok=True)
    names = args.only.split(",") if args.only else list(DATASETS)
    results = json.loads(args.out.read_text()) if args.out and args.out.exists() else {}
    for name in names:
        rel, kind = DATASETS[name]
        src = args.data / rel
        if not src.exists():
            print(f"{name}: {src} missing, skipped")
            continue
        row = {"source": str(rel), "source_kind": kind,
               "source_bytes": size_bytes(src) if kind == "h5cd" else None}
        if kind == "h5cd":
            from uchrom.io import file_format_version
            row["source_version"] = file_format_version(src)
        zarr = work / f"{name}.chromdata.zarr"
        row["zarr"] = run_child(["convert", str(src), kind, str(zarr), "{}"])
        if kind == "fofct":
            row["source_bytes"] = sum(size_bytes(args.data / f) for f in
                                      ("4DNFIHF3JCBY.csv", "4DNFIFINA2U9.csv", "4DNFIJ52NVDV.csv"))
        h5 = work / f"{name}.v2.h5cd"
        row["h5cd_2_0"] = run_child(["convert", str(src), kind, str(h5), json.dumps({"format": "h5cd"})])
        h5.unlink()
        f32 = work / f"{name}.f32.chromdata.zarr"
        row["zarr_float32"] = run_child(["convert", str(src), kind, str(f32),
                                         json.dumps({"coord_dtype": "float32"})])
        __import__("shutil").rmtree(f32)
        row["verify"] = run_child(["verify", str(src), kind, str(zarr)])
        results[name] = row
        mb = lambda b: None if b is None else round(b / 2**20, 2)  # noqa: E731
        print(f"{name}: src {mb(row['source_bytes'])} MB | h5cd 2.0 {mb(row['h5cd_2_0']['bytes'])} MB | "
              f"zarr {mb(row['zarr']['bytes'])} MB (f32 {mb(row['zarr_float32']['bytes'])}) | "
              f"convert {row['zarr']['seconds']:.1f} s, peak {row['zarr']['peak_rss_gb']:.1f} GB | "
              f"identical={row['verify']['identical']}", flush=True)
        if args.out:
            args.out.write_text(json.dumps(results, indent=1))


if __name__ == "__main__":
    main()
