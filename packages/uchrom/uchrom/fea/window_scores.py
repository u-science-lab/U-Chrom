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

Against the cell's own expected (``expected=``, :func:`window_expected`: each window's contacts predicted from the
cell's contact-distance histogram of that chromosome, :class:`uchrom.io.ContactStats`).  A structure's per-cell
log ratio depends on more than the structure: on the cell's contact decay (the windows lie at different distances
from the diagonal) and, at a few contacts per window, on how many contacts the cell has on that chromosome (the
log of a few counts plus a pseudo-count is biased, by an amount that changes with the counts).  Where the decay or
the coverage varies across a tissue (copy number, a haploid chromosome X), these scores can vary with it, alike for
the structures of a chromosome or the loops of a size.  The scores against the expected remove both: ``insulation_oe[k]`` = the share of boundary k's contacts
that cross it minus the share the cell's decay predicts (negative where it insulates), ``loops_oe[k]`` = the share
of loop k's contacts at its peak (of peak + donut) minus the predicted share; a share is unbiased at any number of
contacts (NaN at none).  Pooled: ``boundary_strength_oe`` (log2 observed / expected within the flanks minus the
same across the boundaries), ``loop_strength_oe`` (peak minus donut) and ``interior_oe`` (the same as
``boundary_strength_oe`` at the interiors: about 0 where the expected describes the cell).
"""

from __future__ import annotations

from typing import Mapping, Optional

import numpy as np
import pandas as pd

__all__ = ["window_expected", "window_scores"]


def _window_fractions(windows: pd.DataFrame, resolution: int, edges: np.ndarray, chromsizes: Mapping,
                      samples: int = 16, chunk: int = 2000) -> np.ndarray:
    """(n_windows, n_bins): the fraction of a chromosome's contacts at distance bin k that fall in each window,
    for contacts placed uniformly along the chromosome (the left end uniform on [0, L - d)) and distances uniform
    within the bin (midpoint rule, ``samples`` points)."""
    r = int(resolution)
    a1 = (windows["start1"].to_numpy(np.int64) // r * r).astype(float)
    b1 = (-(-windows["end1"].to_numpy(np.int64) // r) * r).astype(float)
    a2 = (windows["start2"].to_numpy(np.int64) // r * r).astype(float)
    b2 = (-(-windows["end2"].to_numpy(np.int64) // r) * r).astype(float)
    L = np.array([float(chromsizes.get(c, np.nan)) for c in windows["chrom"]])
    lo = np.r_[0.0, edges]                                   # bin k: [lo_k, hi_k); the last bin: up to L
    hi = np.r_[edges, np.inf]
    t = (np.arange(samples) + 0.5) / samples
    out = np.zeros((len(windows), len(lo)))
    for s in range(0, len(windows), chunk):
        sl = slice(s, s + chunk)
        Lw = L[sl, None, None]
        top = np.minimum(hi[None, :, None], Lw)
        width = np.clip(top - lo[None, :, None], 0, None)
        d = lo[None, :, None] + t[None, None, :] * width       # (windows, bins, samples)
        ov = np.minimum(np.minimum(b1[sl, None, None], b2[sl, None, None] - d), Lw - d) - \
            np.maximum(np.maximum(a1[sl, None, None], a2[sl, None, None] - d), 0.0)
        with np.errstate(invalid="ignore", divide="ignore"):
            frac = np.where(Lw - d > 0, np.clip(ov, 0, None) / (Lw - d), 0.0)
        out[sl] = np.where(width[..., 0] > 0, frac.mean(axis=2), 0.0)
    return np.nan_to_num(out)


def window_expected(counts, stats, *, chromsizes: Mapping, samples: int = 16) -> np.ndarray:
    """The contacts each cell is expected to have in each window, from its own contact-distance histogram of the
    window's chromosome.

    Parameters
    ----------
    counts
        :class:`~uchrom.io.WindowCounts` (its windows, resolution and cells).
    stats
        :class:`~uchrom.io.ContactStats` of the same contacts (``distance`` per chromosome; cells matched by id).
    chromsizes
        Chromosome lengths (bp).
    samples
        Distances per histogram bin in the integration.

    Returns
    -------
    ndarray (n_cells of ``counts``, n_windows), float: per window, sum over distance bins of the cell's contacts
    on that chromosome in the bin times the fraction of such contacts the window holds (contacts placed uniformly
    along the chromosome).  NaN for cells without statistics, 0 for windows on chromosomes the statistics lack.
    """
    w = counts.windows
    F = _window_fractions(w, counts.resolution, np.asarray(stats.edges, float), chromsizes, samples)
    row = {str(c): i for i, c in enumerate(stats.cells)}
    take = np.array([row.get(str(c), -1) for c in counts.cells], np.int64)
    out = np.zeros((len(counts.cells), len(w)))
    chrom_of = w["chrom"].astype(str).to_numpy()
    for ci, c in enumerate(stats.chroms):
        cols = np.flatnonzero(chrom_of == c)
        if len(cols):
            H = stats.distance[np.clip(take, 0, None), ci, :].astype(float)
            out[:, cols] = H @ F[cols].T
    out[take < 0] = np.nan
    return out


def _share_minus(num, den_other, e_num, e_other):
    """num / (num + other) - e_num / (e_num + e_other); NaN where there are no contacts."""
    n = num + den_other
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(n > 0, num / np.where(n > 0, n, 1), np.nan) - e_num / (e_num + e_other)


def _log_ratio(num, num_px, den, den_px, pseudo):
    return np.log2((num + pseudo) / num_px) - np.log2((den + pseudo) / den_px)


def window_scores(counts, *, expected: Optional[np.ndarray] = None, pseudo: float = 0.5,
                  per_structure: bool = True) -> dict:
    """Scores of each cell from :class:`~uchrom.io.WindowCounts` with windows of kinds ``boundary``,
    ``interior`` (optional) and ``loop``; ``expected`` (:func:`window_expected`, cells x windows) adds the
    scores against each cell's own expected.

    Returns
    -------
    dict
        ``"cells"``: DataFrame indexed by cell — ``boundary_strength`` (with interiors), ``boundary_ratio``
        (log2 within / cross at the boundaries, without the interior correction), ``interior_ratio``,
        ``loop_strength``, the summed counts ``n_boundary``, ``n_interior``, ``n_loop_peak``, ``n_loop_donut``;
        with ``per_structure``: ``"insulation"`` (cells x boundaries, log2 cross / within minus the cell's
        interior ratio) and ``"loops"`` (cells x loops, log2 peak / donut per pixel), plus ``"boundary_counts"``
        and ``"loop_counts"`` (dicts of raw count matrices by part).  With ``expected``: the columns
        ``boundary_strength_oe``, ``interior_oe``, ``loop_strength_oe`` and, with ``per_structure``,
        ``"insulation_oe"`` / ``"loops_oe"`` (cells x structures, observed minus expected shares).
    """
    if expected is not None:
        expected = np.asarray(expected, float)
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
        if expected is not None:
            e, _ = counts.by_part("boundary", values=expected)
            e_within = e["left"] + e["right"]
            cells["boundary_strength_oe"] = _log_ratio(within.sum(1), e_within.sum(1), c["cross"].sum(1),
                                                       e["cross"].sum(1), pseudo)
            if "interior" in kinds:
                ei, _ = counts.by_part("interior", values=expected)
                cells["interior_oe"] = _log_ratio(wi.sum(1), (ei["left"] + ei["right"]).sum(1), ci["cross"].sum(1),
                                                  ei["cross"].sum(1), pseudo)
            if per_structure:
                out["insulation_oe"] = pd.DataFrame(_share_minus(c["cross"], within, e["cross"], e_within), index=idx)
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
        if expected is not None:
            e, _ = counts.by_part("loop", values=expected)
            cells["loop_strength_oe"] = _log_ratio(c["peak"].sum(1), e["peak"].sum(1), c["donut"].sum(1),
                                                   e["donut"].sum(1), pseudo)
            if per_structure:
                out["loops_oe"] = pd.DataFrame(_share_minus(c["peak"], c["donut"], e["peak"], e["donut"]), index=idx)
    return out
