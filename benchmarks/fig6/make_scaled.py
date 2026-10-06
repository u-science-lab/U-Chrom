"""Scaled copies of Takei 2025 FOV 0 for the Fig 6c browser benchmarks.

Real cells are replicated k times and tiled side by side in x/y (one FOV width apart), with cell and trace
ids suffixed ``_r<k>``.  Only geometry is kept (spots, coords, cells.cell_type): the 62 IF track columns
would not fit in memory at 10^7 spots and are not used by the geometry benchmarks.  The replicated files
are **labelled as replicated** wherever they are reported.

    python benchmarks/fig6/make_scaled.py --src example-data/takei2025_fov0/takei2025_fov0.chromdata.zarr \
        --out benchmarks/fig6/_data --factors 1 3 10 30
"""
from __future__ import annotations

import argparse
import time
from pathlib import Path

import numpy as np
import pandas as pd

from chromdata import ChromData


def replicate(cd: ChromData, k: int) -> ChromData:
    xyz = np.asarray(cd.coords, float)
    span = np.nanmax(xyz[:, :2], 0) - np.nanmin(xyz[:, :2], 0)
    side = int(np.ceil(np.sqrt(k)))
    spots0 = cd.spots[["chrom", "start", "end", "trace_id", "cell_id"]].copy()
    for c in ("chrom", "trace_id", "cell_id"):
        spots0[c] = spots0[c].astype(str)
    cells0 = cd.cells[["cell_type"]].copy()
    cells0.index = cells0.index.astype(str)
    coords, spots, cells = [], [], []
    for r in range(k):
        off = np.array([(r % side) * span[0] * 1.05, (r // side) * span[1] * 1.05, 0.0])
        coords.append(xyz + off)
        s = spots0.copy()
        s["trace_id"] = s["trace_id"] + f"_r{r}"
        s["cell_id"] = s["cell_id"] + f"_r{r}"
        spots.append(s)
        c = cells0.copy()
        c.index = c.index + f"_r{r}"
        cells.append(c)
    uns = {kk: v for kk, v in cd.uns.items() if kk in ("xyz_unit", "genome_assembly")}
    uns["replicated_from"] = {"source": "takei2025_fov0", "factor": k}
    return ChromData(np.vstack(coords), pd.concat(spots, ignore_index=True), cells=pd.concat(cells), uns=uns)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True)
    ap.add_argument("--out", default="benchmarks/fig6/_data")
    ap.add_argument("--factors", type=int, nargs="+", default=[1, 3, 10, 30])
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    cd = ChromData.read(a.src)
    for k in a.factors:
        t = time.time()
        rep = replicate(cd, k)
        path = out / f"takei2025_fov0_x{k}.chromdata.zarr"
        rep.write(str(path))
        print(f"x{k}: {rep.n_spots:,} spots, {rep.n_cells} cells -> {path} "
              f"({store_mb(path):.0f} MB, {time.time() - t:.1f} s)")


def store_mb(path: Path) -> float:
    """Size on disk of a file or a directory store (.chromdata.zarr), in MB."""
    path = Path(path)
    if path.is_dir():
        return sum(f.stat().st_size for f in path.rglob("*") if f.is_file()) / 1e6
    return path.stat().st_size / 1e6


if __name__ == "__main__":
    main()
