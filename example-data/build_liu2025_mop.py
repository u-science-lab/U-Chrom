"""Liu et al. 2025 mouse MOp DNA-MERFISH (4DN FOF-CT) → ``.h5cd``.

Input (fetch explicitly first; nothing is downloaded silently)::

    python example-data/download_data.py --liu2025_mop

stages ``liu2025_mop/4DNFID46OABK.csv`` (FOF-CT core, 1.68 GB) and
``liu2025_mop/4DNFICX8IVEK.csv`` (FOF-CT cell table, 17 MB).  This script
reads both with :meth:`ChromData.from_fofct` (``cell_table=``), writes
``liu2025_mop/liu2025_mop.h5cd`` and ``liu2025_mop/build_summary.json``
(n_spots / n_traces / n_cells, NaN-coordinate spots, file sizes, wall time,
peak RSS of the FOF-CT read).

Usage::

    python example-data/build_liu2025_mop.py [--data-dir DIR]
"""

from __future__ import annotations

import argparse
import json
import os
import resource
import sys
import time
import warnings
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))  # this checkout's uchrom, not an installed copy
CORE, CELLS = "4DNFID46OABK.csv", "4DNFICX8IVEK.csv"


def peak_rss_mb() -> float:
    r = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return r / 2**20 if sys.platform == "darwin" else r / 1024


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    root = Path(os.environ.get("UCHROM_EXAMPLE_DATA", HERE))
    ap.add_argument("--data-dir", type=Path, default=root / "liu2025_mop")
    args = ap.parse_args()
    d = args.data_dir
    for name in (CORE, CELLS):
        if not (d / name).exists():
            raise SystemExit(f"{d / name} missing — run: python example-data/download_data.py --liu2025_mop")

    from uchrom import ChromData

    t0 = time.perf_counter()
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        cd = ChromData.from_fofct(d / CORE, cell_table=d / CELLS, cell_value_prefix=None)
    read_s = time.perf_counter() - t0
    rss = peak_rss_mb()
    out = d / "liu2025_mop.h5cd"
    t0 = time.perf_counter()
    cd.write(out)
    write_s = time.perf_counter() - t0
    nan = ~np.isfinite(cd.coords).all(axis=1)
    per_trace = cd.spots.groupby("trace_id", observed=True).size()
    summary = {
        "core_csv": CORE, "core_csv_bytes": (d / CORE).stat().st_size,
        "cell_csv": CELLS, "cell_csv_bytes": (d / CELLS).stat().st_size,
        "h5cd": out.name, "h5cd_bytes": out.stat().st_size,
        "n_spots": int(cd.n_spots), "n_spots_nan_xyz": int(nan.sum()),
        "n_traces": int(cd.n_traces), "n_cells": int(cd.n_cells), "n_cells_in_cell_table": int(len(cd.cells)),
        "n_chroms": len(cd.chroms), "spots_per_trace_median": float(per_trace.median()),
        "spot_columns": list(cd.spots.columns), "cell_columns": list(cd.cells.columns)[:20],
        "xyz_unit": cd.uns.get("xyz_unit"), "genome_assembly": cd.uns.get("genome_assembly"),
        "from_fofct_s": round(read_s, 1), "from_fofct_peak_rss_mb": round(rss, 1),
        "h5cd_write_s": round(write_s, 1),
        "warnings": sorted({str(w.message)[:200] for w in caught}),
    }
    (d / "build_summary.json").write_text(json.dumps(summary, indent=1))
    print(cd)
    print(json.dumps({k: v for k, v in summary.items() if k not in ("spot_columns", "cell_columns")}, indent=1))


if __name__ == "__main__":
    main()
