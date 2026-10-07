"""Per-trace coordinates on the loci of one chromosome (shared by the structure scores).  The distance
matrix of one trace on those loci is public: :func:`uchrom.fea.trace_distance_matrix`."""

from __future__ import annotations

from typing import Tuple

import numpy as np
import pandas as pd


def chrom_loci(cd, chrom: str) -> pd.DataFrame:
    """The loci of ``chrom`` in ``cd.bins``, sorted by start: ``bin_id, chrom, start, end`` (row = locus
    index within the chromosome)."""
    bins = cd.bins
    loci = bins[bins["chrom"].astype(str) == str(chrom)].sort_values("start", kind="mergesort")
    if loci.empty:
        raise KeyError(f"no loci on {chrom!r} in cd.bins (for a ChromData holding a Hi-C map, give contacts=<its key>"
                       f" where the function takes it)")
    out = loci[["chrom", "start", "end"]].astype({"chrom": str}).reset_index(names="bin_id")
    return out.astype({"start": np.int64, "end": np.int64})


def coord_cube(cd, chrom: str) -> Tuple[np.ndarray, pd.DataFrame, np.ndarray]:
    """``(cube, loci, trace_ids)``: the coordinates of every trace on ``chrom`` as a
    ``(n_traces, n_loci, 3)`` array, NaN where a trace has no spot on a locus (a locus seen twice in a trace
    keeps its last spot); ``loci`` from :func:`chrom_loci`; traces in order of first appearance."""
    sub = cd.get_chrom(chrom)
    loci = chrom_loci(cd, chrom)
    row = pd.Series(np.arange(len(loci)), index=loci["bin_id"].to_numpy())
    rows = row.reindex(sub.spots["bin_id"].to_numpy()).to_numpy()
    codes, traces = pd.factorize(sub.spots["trace_id"].astype(str).to_numpy())
    cube = np.full((len(traces), len(loci), 3), np.nan)
    ok = np.isfinite(rows)
    cube[codes[ok], rows[ok].astype(np.int64)] = np.asarray(sub.coords, dtype=np.float64)[ok]
    return cube, loci, np.asarray(traces)
