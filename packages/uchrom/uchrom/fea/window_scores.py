"""Per-cell strength of known boundaries and loops from contacts counted in their windows
(:class:`uchrom.io.WindowCounts`): structures called once on a pooled map, scored in every cell or spatial Hi-C
spot that is too shallow to call them itself.

Boundaries.  Per cell and boundary, the insulation is log2 of the contacts per pixel crossing the boundary over the
contacts per pixel within its flanks.  It depends on the cell's contact-decay shape (the cross square lies further
from the diagonal than the flanks), so it is compared with the same ratio at domain interiors (windows of
``kind="interior"``, no boundary): ``boundary_strength`` = log2(within / cross at the boundaries) - log2(within /
cross at the interiors) over all boundaries — a cell's overall insulation — and ``insulation[k]`` = boundary k's
log2(cross / within) minus the interiors' — negative where the boundary insulates in that cell.

Loops.  Per cell and loop, log2 of the contacts per pixel at the loop (the peak) over those around it (the donut);
``loop_strength`` pools all loops (an aggregate peak analysis per cell).

Pseudo-counts (``pseudo``, per window) keep the logs finite; per-structure scores of a cell with few contacts
are noisy, the pooled ones much less so.
"""

from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd

__all__ = ["window_scores"]


def _log_ratio(num, num_px, den, den_px, pseudo):
    return np.log2((num + pseudo) / num_px) - np.log2((den + pseudo) / den_px)


def window_scores(counts, *, pseudo: float = 0.5, per_structure: bool = True) -> dict:
    """Scores of each cell from :class:`~uchrom.io.WindowCounts` with windows of kinds ``boundary``,
    ``interior`` (optional) and ``loop``.

    Returns
    -------
    dict
        ``"cells"``: DataFrame indexed by cell — ``boundary_strength`` (with interiors), ``boundary_ratio``
        (log2 within / cross at the boundaries, without the interior correction), ``interior_ratio``,
        ``loop_strength``, the summed counts ``n_boundary``, ``n_interior``, ``n_loop_peak``, ``n_loop_donut``;
        with ``per_structure``: ``"insulation"`` (cells x boundaries, log2 cross / within minus the cell's
        interior ratio) and ``"loops"`` (cells x loops, log2 peak / donut per pixel), plus ``"boundary_counts"``
        and ``"loop_counts"`` (dicts of raw count matrices by part).
    """
    kinds = set(counts.windows["kind"]) if "kind" in counts.windows else set()
    idx = pd.Index(np.asarray(counts.cells, dtype=str), name="cell_id")
    cells = pd.DataFrame(index=idx)
    out = {"cells": cells}
    if "boundary" in kinds:
        c, px = counts.by_part("boundary")
        within = c["left"] + c["right"]
        within_px = px["left"] + px["right"]
        cells["n_boundary"] = (within + c["cross"]).sum(axis=1)
        cells["boundary_ratio"] = -_log_ratio(c["cross"].sum(1), px["cross"].sum(), within.sum(1), within_px.sum(),
                                              pseudo)
        base = 0.0
        if "interior" in kinds:
            ci, pxi = counts.by_part("interior")
            wi = ci["left"] + ci["right"]
            cells["n_interior"] = (wi + ci["cross"]).sum(axis=1)
            cells["interior_ratio"] = -_log_ratio(ci["cross"].sum(1), pxi["cross"].sum(), wi.sum(1),
                                                  (pxi["left"] + pxi["right"]).sum(), pseudo)
            cells["boundary_strength"] = cells["boundary_ratio"] - cells["interior_ratio"]
            base = cells["interior_ratio"].to_numpy()[:, None]
        if per_structure:
            ins = _log_ratio(c["cross"], np.maximum(px["cross"], 1), within, np.maximum(within_px, 1), pseudo)
            out["insulation"] = pd.DataFrame(ins + base, index=idx)
            out["boundary_counts"] = c
    if "loop" in kinds:
        c, px = counts.by_part("loop")
        cells["n_loop_peak"] = c["peak"].sum(axis=1)
        cells["n_loop_donut"] = c["donut"].sum(axis=1)
        cells["loop_strength"] = _log_ratio(c["peak"].sum(1), px["peak"].sum(), c["donut"].sum(1),
                                            px["donut"].sum(), pseudo)
        if per_structure:
            out["loops"] = pd.DataFrame(_log_ratio(c["peak"], np.maximum(px["peak"], 1), c["donut"],
                                                   np.maximum(px["donut"], 1), pseudo), index=idx)
            out["loop_counts"] = c
    return out
