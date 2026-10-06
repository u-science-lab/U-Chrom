"""Convert the real example stores to ``.chromdata.zarr`` format 2.2 and check them.

For each source store (format 2.1): ``python -m uchrom.io.upgrade``'s
``upgrade_h5cd(src, dst)`` writes ``<name>.v22.chromdata.zarr`` next to it;
then both stores are read in their original order and compared **bitwise**
(coordinates and every float column by bit pattern; everything else with
``pandas.testing``), and the backed 2.2 store is checked against in-memory
subsets (get_cell / get_trace / get_chrom, with and without
``columns="coords"``) for a sample of ids.

    python benchmarks/cd22_convert_validate.py [--data takei,liu]

Writes ``u-chrom-paper/manuscripts/full/figures/fig2/results/cd22_convert_validation.json``.
"""

from __future__ import annotations

from uchrom.datasets import data_dir
import argparse
import json
import os
import resource
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
for _pkg in ("uchrom", "chromdata", "uchrom-browser"):   # this checkout's packages, not installed copies
    sys.path.insert(0, str(ROOT / "packages" / _pkg))
DATA = data_dir()
STORES = {
    "takei": DATA / "takei2025_cerebellum" / "takei2025_cerebellum_rep1.v21.chromdata.zarr",
    "liu": DATA / "liu2025_mop" / "liu2025_mop.v21.chromdata.zarr",
}


def _bits(a):
    return np.ascontiguousarray(a, dtype=np.float64).view(np.int64)


def _same_frame(a: pd.DataFrame, b: pd.DataFrame, what: str):
    pd.testing.assert_frame_equal(a, b, check_exact=True, obj=what)
    for c in a.columns:
        if a[c].dtype == np.float64:
            if not np.array_equal(_bits(a[c]), _bits(b[c])):
                raise AssertionError(f"{what}.{c}: float bits differ")


def compare(src, dst) -> dict:
    from uchrom import ChromData

    a = ChromData.read(src, original_order=True)
    b = ChromData.read(dst, original_order=True)
    if not np.array_equal(_bits(a.coords), _bits(b.coords)):
        raise AssertionError("coords differ")
    _same_frame(a.spots, b.spots, "spots")
    _same_frame(a.spot_tracks, b.spot_tracks, "spot_tracks")
    _same_frame(a.bins, b.bins, "bins")
    _same_frame(a.bin_tracks, b.bin_tracks, "bin_tracks")
    _same_frame(a.cells, b.cells, "cells")
    _same_frame(a.traces, b.traces, "traces")
    assert list(a.cellm) == list(b.cellm) and all(np.array_equal(a.cellm[k], b.cellm[k]) for k in a.cellm)
    assert list(a.layers) == list(b.layers)
    for k in a.layers:
        assert np.array_equal(_bits(a.layers[k]), _bits(b.layers[k])), k
    assert json.dumps(a.uns, sort_keys=True, default=str) == json.dumps(b.uns, sort_keys=True, default=str)
    return {"n_spots": int(a.n_spots), "spot_columns": list(a.spots.columns),
            "n_spot_tracks": int(len(a.spot_tracks.columns))}


def backed_check(dst, n_ids=5) -> dict:
    from uchrom import ChromData

    mem = ChromData.read(dst)
    bk = ChromData.read(dst, backed=True)
    rng = np.random.default_rng(0)
    out = {}
    for level, ids in (("cell", list(mem.spots["cell_id"].cat.categories)),
                       ("trace", list(mem.spots["trace_id"].cat.categories)),
                       ("chrom", list(mem.bins["chrom"].cat.categories))):
        picks = [ids[i] for i in rng.choice(len(ids), min(n_ids, len(ids)), replace=False)]
        for key in picks:
            for sel in (None, "coords"):
                x = getattr(mem, f"get_{level}")(key, columns=sel)
                y = getattr(bk, f"get_{level}")(key, columns=sel)
                assert np.array_equal(_bits(x.coords), _bits(y.coords)), (level, key)
                _same_frame(x.spots, y.spots, f"{level} {key} spots")
                _same_frame(x.spot_tracks, y.spot_tracks, f"{level} {key} spot_tracks")
        out[level] = picks
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", default="takei,liu")
    args = ap.parse_args()
    from uchrom.io.upgrade import upgrade_h5cd

    sys.path.insert(0, str(ROOT / "benchmarks"))
    from _paper import results_dir
    res_path = results_dir("fig2") / "cd22_convert_validation.json"
    res = json.loads(res_path.read_text()) if res_path.exists() else {}
    for key in args.data.split(","):
        src = STORES[key]
        dst = src.parent / src.name.replace(".v21.chromdata.zarr", ".v22.chromdata.zarr")
        t0 = time.perf_counter()
        info = upgrade_h5cd(src, dst, overwrite=True)
        dt = time.perf_counter() - t0
        size = lambda p: sum(f.stat().st_size for f in Path(p).rglob("*") if f.is_file())  # noqa: E731
        rec = {"src": str(src.relative_to(DATA)), "dst": str(dst.relative_to(DATA)), "seconds": dt,
               "from_version": info["from_version"], "to_version": info["to_version"],
               "src_bytes": size(src), "dst_bytes": size(dst)}
        rec.update(compare(src, dst))
        rec["backed_vs_memory_ids"] = backed_check(dst)
        rec["identical"] = True
        rec["peak_rss_mb"] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 2**20
        res[key] = rec
        print(key, json.dumps({k: v for k, v in rec.items() if k != "backed_vs_memory_ids"}), flush=True)
        res_path.parent.mkdir(parents=True, exist_ok=True)
        res_path.write_text(json.dumps(res, indent=1))
    print(res_path)


if __name__ == "__main__":
    main()
