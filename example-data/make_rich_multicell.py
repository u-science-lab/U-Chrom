"""Generate ``rich_multicell.h5cd`` — a small multi-cell, multi-chrom fixture.

8 cells (2 cell types), 2 chromosomes, 30 bins/trace, with cell-level
metadata and a genome assembly. Used by the webapp test suite to exercise
code paths that the single-cell ``synthetic_chr1_tiny.h5cd`` cannot reach:
per-cell embedding (UMAP), cell-coloured 3D structure, /api/cells,
/api/dataset_info, and CSV round-trips.

NOT a replacement for real data — it is a deterministic fast-iteration
supplement. Real-data validation of the webapp uses the 4DN FOF-CT dataset
``4DNFIHF3JCBY.csv`` (see example-data/README.md).

The fixture is gitignored (like the other generated ``.h5cd`` files); the
test suite auto-creates it on demand via ``tests/conftest.py`` calling
``build_rich_multicell()``. Run this module directly to (re)create it by hand.
"""
from pathlib import Path

import numpy as np
import pandas as pd

from uchrom.core import ChromData

DEFAULT_PATH = Path(__file__).resolve().parent / "rich_multicell.h5cd"


def build_rich_multicell(path: str | Path = DEFAULT_PATH) -> ChromData:
    """Build the fixture deterministically and write it to ``path``.

    Returns the in-memory :class:`ChromData` as well, so callers can use it
    without a round-trip.
    """
    rng = np.random.default_rng(42)
    n_cells = 8
    bins_per_chrom = 30
    chroms = ["chr1", "chr2"]
    cell_types = ["typeA", "typeB"]

    rows = []
    coords = []
    for ci in range(n_cells):
        for chrom in chroms:
            # each (cell, chrom) is one trace; coords are a random walk so the
            # per-cell distance matrices differ (gives UMAP something to see).
            pos = np.zeros(3)
            for b in range(bins_per_chrom):
                pos = pos + rng.normal(0, 1, 3)
                coords.append(pos.copy())
                rows.append({
                    "chrom": chrom,
                    "start": b * 100000,
                    "end": (b + 1) * 100000,
                    "trace_id": f"t{ci}_{chrom}",
                    "cell_id": f"c{ci}",
                })

    spots = pd.DataFrame(rows)
    coords = np.array(coords, dtype=np.float64)
    cells = pd.DataFrame({
        "cell_id": [f"c{i}" for i in range(n_cells)],
        "cell_type": [cell_types[i % 2] for i in range(n_cells)],
    }).set_index("cell_id")

    cd = ChromData(
        coords=coords,
        spots=spots,
        cells=cells,
        uns={"genome_assembly": "mm10", "xyz_unit": "um"},
    )
    cd.write(str(path))
    return cd


if __name__ == "__main__":
    cd = build_rich_multicell()
    print(f"wrote {DEFAULT_PATH}")
    print(
        "coords:", cd.coords.shape,
        "cells:", cd.cells.shape,
        "traces:", cd.spots["trace_id"].nunique(),
        "chroms:", list(cd.spots["chrom"].unique()),
    )
