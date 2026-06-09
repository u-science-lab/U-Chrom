"""Extract portal display statistics from a ChromData object.

Pure function over an already-loaded ChromData. Degrades gracefully when
optional layers (cells, tracks, uns) are absent — minimal fixtures have
none of them, full datasets (Takei 2025) have all.
"""
from __future__ import annotations

from typing import Any


def extract_stats(cd: Any) -> dict:
    # Marker count = number of epigenomic track columns (tracks may be None).
    n_markers = 0 if cd.tracks is None else int(cd.tracks.shape[1])

    # Cell-type distribution, if a cell_type column exists.
    cell_types: dict[str, int] = {}
    cells = cd.cells
    if cells is not None and "cell_type" in getattr(cells, "columns", []):
        counts = cells["cell_type"].value_counts(dropna=False)
        cell_types = {}
        for k, v in counts.items():
            # NaN is the only value not equal to itself; retain it as an
            # explicit "unassigned" bucket so the distribution sums to the
            # number of cells (the real Takei dataset has untyped cells).
            key = "unassigned" if (k is None or (isinstance(k, float) and k != k)) else str(k)
            # merge in case a real "unassigned" label coexists with NaN
            cell_types[key] = cell_types.get(key, 0) + int(v)

    # Genome coverage: list of chromosomes joined, or "genome-wide" if many.
    chroms = list(cd.chroms)
    if len(chroms) == 0:
        genome_coverage = ""
    elif len(chroms) >= 20:
        genome_coverage = "genome-wide"
    else:
        genome_coverage = ",".join(chroms)

    uns = cd.uns or {}
    return {
        "n_cells": int(cd.n_cells),
        "n_traces": int(cd.n_traces),
        "n_spots": int(cd.n_spots),
        "n_markers": n_markers,
        "cell_types": cell_types,
        "genome_coverage": genome_coverage,
        "assembly": str(uns.get("genome_assembly", "")),
        "xyz_unit": str(uns.get("xyz_unit", "")),
    }
