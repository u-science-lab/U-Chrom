"""Domain boundaries of single cells from their imputed contact maps, and how often each bin is one.

Single-cell maps are too sparse for an insulation score; imputed by a random walk with restart they are not
(scHiCluster: Zhou et al. 2019, *PNAS* 116:14011; Higashi calls single-cell domain boundaries the same way on
its imputed maps: Zhang et al. 2022, *Nat Biotechnol* 40:254).  Per cell and chromosome:

1. the RWR band of the cell (:func:`uchrom.fea.impute_rwr.rwr_band`, the kernel SnapHiC uses; up to the
   diamond's reach, ``2 (w - 1)`` bins);
2. the diamond insulation score of that band and the prominence of its minima — the code of the bulk caller
   (:mod:`uchrom.strc.tad.insulation`: :func:`~uchrom.strc.tad.insulation.diamond_sums`, ``log2`` of the mean
   over the chromosome's median, :func:`~uchrom.strc.tad.insulation.boundary_strength`);
3. the cell's boundaries: minima stronger than Li's threshold of the cell's strengths (as the bulk caller).

Across cells: per bin the share of cells with a boundary there (``frequency``) and the mean of the cells'
insulation scores.  Consensus boundaries (``consensus="insulation"``, the default): the minima of that mean
profile whose strength passes Li's threshold — the bulk caller's rule applied to the cells' mean insulation;
``consensus="frequency"``: the peaks of the frequency profile (``scipy.signal.find_peaks``) whose prominence
passes it.  The stretches between consensus boundaries are the consensus domains.  On the 742 mES cells of
SnapHiC against the insulation boundaries of bulk mESC Hi-C (Bonev et al. 2017; same 100 kb diamond, 10 kb,
``benchmarks/sc_structures/impute_domains.py``) the mean-insulation rule gives 7,270 boundaries (bulk: 7,574),
60 % within 2 bins of a bulk boundary and 58 % of the bulk ones recovered (chance 16 %), where the frequency
peaks give 20,414 at 30 % / 74 %: single-cell boundaries scatter around the population ones, their frequency
stays low (0.058 at bulk boundaries, 0.040 elsewhere), and their mean insulation is the cleaner population
signal (Spearman 0.60 with the bulk insulation).
"""

from __future__ import annotations

import time
import warnings
from dataclasses import dataclass
from typing import Optional, Sequence, Union

import numpy as np
import pandas as pd

from uchrom.convention import store_and_return


@dataclass(frozen=True)
class SingleCellBoundaryParams:
    """Knobs of :func:`single_cell_boundaries`.

    Attributes
    ----------
    rp : float
        Restart probability of the imputation (SnapHiC's 0.05).
    window : int, "auto" or None
        Sliding window of the imputation, bp (``"auto"``: SnapHiC2's rule; ``None``: whole chromosomes).
    insulation_window : int, optional
        Side of the insulation diamond, bp; default that of :class:`~uchrom.strc.tad.InsulationParams` (100 kb,
        at least 3 bins).
    ignore_diags : int
        Diagonals left out of the diamond (2).
    threshold : "li", "otsu" or float
        Boundary-strength cut per cell, and of the consensus.
    normalize : bool
        Insulation of the per-diagonal z-scores (SnapHiC's normalisation) instead of the RWR values.
    consensus : {"insulation", "frequency"}
        Consensus boundaries from the minima of the cells' mean insulation, or from the peaks of the boundary
        frequency.
    """

    rp: float = 0.05
    window: Union[int, str, None] = "auto"
    insulation_window: Optional[int] = None
    ignore_diags: int = 2
    threshold: Union[str, float] = "li"
    normalize: bool = False
    consensus: str = "insulation"

    def __post_init__(self):
        if self.consensus not in ("insulation", "frequency"):
            raise ValueError(f"consensus={self.consensus!r}: 'insulation' or 'frequency'")


def _cell_scores(band: np.ndarray, w: int, ignore_diags: int):
    """Log2 insulation score and boundary strength of one imputed band (every bin valid)."""
    from .insulation import _log2_score, boundary_strength, diamond_sums, n_valid_pixels

    n, W = band.shape
    i = np.repeat(np.arange(n), W)
    d = np.tile(np.arange(W), n)
    v = band.ravel()
    ok = np.isfinite(v)
    sums, nnz = diamond_sums(i[ok], (i + d)[ok], v[ok], n, w, ignore_diags)
    nv = n_valid_pixels(np.ones(n, bool), w, ignore_diags)
    score = _log2_score(sums, nnz, nv, "mean")
    return score, boundary_strength(score)


def single_cell_boundaries(
    cd,
    *,
    contacts: str = "per_cell",
    cells: Optional[Sequence] = None,
    chrom: Union[None, str, Sequence[str]] = None,
    params: Optional[SingleCellBoundaryParams] = None,
    per_cell: bool = False,
    key_added: Optional[str] = "tads.single_cell",
    copy: bool = False,
    backend: Optional[str] = None,
    n_threads: int = 0,
    timing: Optional[dict] = None,
):
    """Domain boundaries of every cell from its imputed map (insulation), and their frequency across cells.

    Parameters
    ----------
    cd : ChromData
        With per-cell maps linked (``cd.link_scool``) or embedded in its atlas store.
    contacts : str
        Key of the per-cell maps (or a ``.scool`` named by cell id).
    cells : sequence, optional
        Cells (default: every cell of ``cd.cells``).
    chrom : str or sequence, optional
        Chromosomes (default: the autosomes of the maps).
    params : SingleCellBoundaryParams, optional
    per_cell : bool
        Also store every cell's boundaries (``cd.results[key_added + ".cells"]``: ``cell_id, chrom, start,
        end, strength``).
    key_added : str or None
        The per-bin table goes to ``cd.results[key_added]``, the consensus domains to
        ``cd.intervals[key_added + ".domains"]`` (``None``: nothing stored).
    copy : bool
        Return a new ``ChromData`` holding the results.
    backend, n_threads
        Of the imputation (:func:`uchrom.fea.impute_rwr.rwr_band`).
    timing : dict, optional
        Seconds per step.

    Returns
    -------
    DataFrame (``copy=False``) or ChromData (``copy=True``)
        One row per bin: ``chrom, start, end``, ``n_cells`` (cells scored), ``frequency`` (share of them with a
        boundary at the bin), ``insulation`` (mean log2 insulation score), ``strength`` (mean strength where a
        cell has a boundary), ``consensus_strength`` (prominence of the mean insulation's minimum, or of the
        frequency's peak) and ``consensus`` (above the threshold).
    """
    from uchrom.fea.impute_rwr import (ImputeParams, _autosomes, _cells_and_source, _resolve_window, _ScoolCells,
                                        _window_bins, read_cell_pixels, rwr_band, zscore_band)

    from .insulation import DEFAULT_WINDOW_BP, MIN_WINDOW_BINS, _threshold, boundary_strength

    if copy and key_added is None:
        raise ValueError("single_cell_boundaries(): copy=True needs a key_added")
    params = params or SingleCellBoundaryParams()
    timing = {} if timing is None else timing
    t0 = time.perf_counter()
    ids, scool = _cells_and_source(cd, contacts, cells)
    src = _ScoolCells(scool)
    names, binsize = list(src.chroms), int(src.binsize)
    src.close()
    chroms = _autosomes(names) if chrom is None else ([chrom] if isinstance(chrom, str) else [str(c) for c in chrom])
    wbp = params.insulation_window if params.insulation_window is not None else DEFAULT_WINDOW_BP
    w = max(MIN_WINDOW_BINS, int(round(wbp / binsize)))
    max_diag = 2 * (w - 1)
    ip = ImputeParams(rp=params.rp, window=params.window, max_dist=max_diag * binsize)
    window_bp = _resolve_window(ip, scool, ids, binsize, _autosomes(names) or chroms)
    win, step = _window_bins(ip, binsize, window_bp)
    if win and win - step < max_diag:
        raise ValueError("the imputation window is too small for the insulation diamond")
    timing["setup_s"] = time.perf_counter() - t0
    # per cell: strengths of every chromosome (the cell's threshold pools them)
    per_chrom = {}
    strengths = {c: [] for c in ids}
    t_imp = t_ins = 0.0
    for c in chroms:
        n, pix = read_cell_pixels(scool, ids, c)
        scores = np.full((len(ids), n), np.nan)
        strg = np.full((len(ids), n), np.nan)
        for k, (i, j) in enumerate(pix):
            t1 = time.perf_counter()
            band = rwr_band(i, j, n, rp=params.rp, window=win, step=step, max_diag=max_diag, backend=backend,
                            n_threads=n_threads)
            if params.normalize:
                band = zscore_band(band, edge=0, backend=backend, n_threads=n_threads)
                band[:, 0] = np.nan
            t2 = time.perf_counter()
            scores[k], strg[k] = _cell_scores(band, w, params.ignore_diags)
            strengths[ids[k]].append(strg[k][np.isfinite(strg[k])])
            t_ins += time.perf_counter() - t2
            t_imp += t2 - t1
        per_chrom[c] = (n, scores, strg)
    timing["impute_s"], timing["insulation_s"] = t_imp, t_ins
    thr = {cell: _threshold(np.concatenate(v) if v else np.zeros(0), params.threshold) for cell, v in strengths.items()}
    cut = np.array([thr[cell] for cell in ids])
    rows, cell_rows = [], []
    for c, (n, scores, strg) in per_chrom.items():
        with np.errstate(invalid="ignore"):
            is_b = strg >= cut[:, None]
        scored = np.isfinite(scores).sum(axis=0)
        freq = np.where(scored > 0, is_b.sum(axis=0) / np.maximum(scored, 1), np.nan)
        with np.errstate(invalid="ignore"), warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)         # bins no cell scores / no cell's boundary
            ins = np.nanmean(np.where(np.isfinite(scores), scores, np.nan), axis=0) if len(ids) else np.full(n, np.nan)
            st = np.nanmean(np.where(is_b, strg, np.nan), axis=0)
        starts = np.arange(n, dtype=np.int64) * binsize
        rows.append(pd.DataFrame({"chrom": c, "start": starts, "end": starts + binsize, "n_cells": scored,
                                  "frequency": freq, "insulation": ins, "strength": st}))
        if per_cell:
            kk, bb = np.nonzero(is_b)
            cell_rows.append(pd.DataFrame({"cell_id": np.asarray(ids)[kk], "chrom": c, "start": bb * binsize,
                                           "end": bb * binsize + binsize, "strength": strg[kk, bb]}))
    table = pd.concat(rows, ignore_index=True) if rows else pd.DataFrame(
        columns=["chrom", "start", "end", "n_cells", "frequency", "insulation", "strength"])
    # consensus boundaries: minima of the mean insulation (or peaks of the frequency) above the threshold
    from scipy.signal import find_peaks

    prom = np.full(len(table), np.nan)
    for c, idx in table.groupby("chrom", sort=False).indices.items():
        if params.consensus == "insulation":
            prom[idx] = boundary_strength(table["insulation"].to_numpy()[idx])
        else:
            f = np.nan_to_num(table["frequency"].to_numpy()[idx], nan=0.0)
            pk, props = find_peaks(f, prominence=0)          # plateaus / equal peaks: common in a frequency
            prom[idx[pk]] = props["prominences"]
    finite = prom[np.isfinite(prom)]
    pcut = _threshold(finite, params.threshold) if len(finite) else np.inf
    table["consensus_strength"] = prom
    with np.errstate(invalid="ignore"):
        table["consensus"] = prom >= pcut
    domains = []
    for c, g in table.groupby("chrom", sort=False):
        edges = g.loc[g["consensus"], "start"].to_numpy()
        lo, hi = int(g["start"].min()), int(g["end"].max())
        cuts = np.r_[lo, edges, hi]
        for a, b in zip(cuts[:-1], cuts[1:]):
            if b > a:
                domains.append((c, int(a), int(b)))
    dom = pd.DataFrame(domains, columns=["chrom", "start", "end"])
    inputs = {"contacts": str(contacts), "n_cells": len(ids), "resolution": binsize, "chrom": chroms,
              "window_bp": window_bp, "insulation_window_bins": w, "consensus_threshold": float(pcut)}
    extra = []
    if key_added is not None and per_cell:
        extra.append((f"{key_added}.cells", pd.concat(cell_rows, ignore_index=True) if cell_rows else
                      pd.DataFrame(columns=["cell_id", "chrom", "start", "end", "strength"]), "table"))
    intervals = [] if key_added is None else [(f"{key_added}.domains", dom, "domain")]
    return store_and_return(cd, table, key_added=key_added, copy=copy, kind="table",
                            function="uchrom.strc.tad.single_cell_boundaries", params=params, inputs=inputs,
                            extra=extra, intervals=intervals)


__all__ = ["SingleCellBoundaryParams", "single_cell_boundaries"]
