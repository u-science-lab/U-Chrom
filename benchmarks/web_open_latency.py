"""Web browser: time to open a dataset and to get the first cell's geometry.

Runs the web backend's data layer (``uchrom.browser.web.data``, what
``POST /api/datasets`` and ``POST /api/datasets/{id}/geometry`` call) in a
fresh process per file:

* ``open``      — ``DatasetStore.load`` + ``summary()`` (the load response);
* ``lists``     — the cell and trace lists the page requests next;
* ``geometry``  — one cell's geometry (the first cell in natural order,
  then 5 more random cells: median);
* peak RSS of the process.

A ``.chromdata.zarr`` / ``.cdz`` store is opened backed (the browser no
longer opens ``.h5cd``).  The OS page cache is not flushed.

    python benchmarks/web_open_latency.py PATH [PATH ...]
"""

from __future__ import annotations

import json
import resource
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def child(path: str) -> None:
    import warnings
    warnings.simplefilter("ignore")
    import numpy as np

    import h5py, pyarrow.parquet, zarr  # noqa: F401,E401  (imports out of the timing)
    from uchrom.browser.web.data import DatasetStore, GeometryFilter, decode_geometry
    import chromdata.backed  # noqa: F401

    out = {"path": path}
    t0 = time.perf_counter()
    store = DatasetStore()
    ds = store.load(path)
    s = ds.summary()
    out["open_s"] = time.perf_counter() - t0
    out["n_spots"] = s["n_spots"]
    out["backed"] = bool(getattr(ds, "backed", False))
    t0 = time.perf_counter()
    cells = ds.cells(limit=500)
    ds.traces(limit=500)
    out["lists_s"] = time.perf_counter() - t0
    ids = [c["cell_id"] for c in cells["cells"]]
    t0 = time.perf_counter()
    g = decode_geometry(ds.geometry(GeometryFilter(cell_ids=[ids[0]])))
    out["first_cell_geometry_s"] = time.perf_counter() - t0
    out["first_cell_points"] = g["header"]["n_points"]
    rng = np.random.default_rng(0)
    ts = []
    for c in rng.choice(len(cells["cells"]), 5, replace=False):
        t0 = time.perf_counter()
        ds.geometry(GeometryFilter(cell_ids=[ids[c]]))
        ts.append(time.perf_counter() - t0)
    out["cell_geometry_median_s"] = float(np.median(ts))
    r = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    out["peak_rss_gb"] = r / 2**30 if sys.platform == "darwin" else r / 2**20
    print("__RESULT__" + json.dumps(out), flush=True)


def main() -> None:
    if len(sys.argv) > 2 and sys.argv[1] == "--child":
        return child(sys.argv[2])
    rows = []
    for path in sys.argv[1:]:
        proc = subprocess.run([sys.executable, __file__, "--child", path], capture_output=True, text=True)
        if "__RESULT__" not in proc.stdout:
            raise RuntimeError(proc.stderr[-3000:])
        r = json.loads(proc.stdout.rsplit("__RESULT__", 1)[1].strip())
        rows.append(r)
        print(f"{Path(path).name}: {r['n_spots']:,} spots, backed={r['backed']}: open {r['open_s']:.2f} s, "
              f"lists {r['lists_s']:.2f} s, first cell geometry {r['first_cell_geometry_s'] * 1e3:.0f} ms "
              f"({r['first_cell_points']:,} points), median cell {r['cell_geometry_median_s'] * 1e3:.0f} ms, "
              f"peak RSS {r['peak_rss_gb']:.2f} GB", flush=True)
    print(json.dumps(rows, indent=1))


if __name__ == "__main__":
    main()
