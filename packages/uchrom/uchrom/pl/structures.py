"""Called structures on matrices and along the genome: domains as squares and loops as circles on a
distance / contact map, compartment tracks."""

from __future__ import annotations

from typing import Optional, Sequence

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt


def _row_starts(bins):
    """``bins`` (the matrix rows) -> (sorted starts, chromosome or None)."""
    if isinstance(bins, pd.DataFrame):
        chrom = None
        if "chrom" in bins.columns:
            names = pd.unique(bins["chrom"].astype(str))
            chrom = str(names[0]) if len(names) == 1 else None
        return bins["start"].to_numpy(np.int64), chrom
    arr = np.asarray(bins)
    if arr.ndim == 2:                               # (start, end) pairs
        arr = arr[:, 0]
    return arr.astype(np.int64), None


def draw_domains(ax, domains, bins=None, *, level: Optional[int] = None, min_size: int = 2, **kwargs):
    """Outline domains as squares on the diagonal of a matrix drawn with ``imshow`` (one row per locus).

    Parameters
    ----------
    ax : matplotlib Axes
    domains : DataFrame or sequence of (first_row, end_row)
        A domain table with ``start`` / ``end`` in bp (TADs, DI domains, FISHnet domains of one trace),
        placed on the rows by ``bins``; or row-index pairs (end exclusive), e.g. the ``domains`` of
        :func:`uchrom.strc.tad.call_domains_fishnet_trace`.
    bins : DataFrame or array, optional
        The loci of the matrix rows (e.g. ``distance_map(...).bins``, or their starts).  Required for a
        table.  A row range of a larger map works: domains are clipped to it.  With a ``chrom`` column of
        one chromosome, only the domains on it are drawn.
    level : int, optional
        For hierarchical tables (a ``level`` column): the level to draw (default all rows).
    min_size : int
        Leave out domains (after clipping) shorter than this many rows.
    **kwargs
        Passed to :class:`matplotlib.patches.Rectangle` (``edgecolor``, ``lw``, ...; default white).

    Returns
    -------
    list of Rectangle
    """
    from matplotlib.patches import Rectangle

    kw = {"edgecolor": "white", "lw": 1.2, **kwargs}
    kw["fill"] = False
    if isinstance(domains, pd.DataFrame):
        if bins is None:
            raise TypeError("draw_domains(): a domain table needs bins= (the loci of the matrix rows)")
        starts, chrom = _row_starts(bins)
        table = domains
        if level is not None:
            table = table[table["level"] == level]
        if chrom is not None and "chrom" in table.columns:
            table = table[table["chrom"].astype(str) == chrom]
        pairs = zip(np.searchsorted(starts, table["start"].to_numpy(np.int64)),
                    np.searchsorted(starts, table["end"].to_numpy(np.int64)))      # end exclusive
    else:
        pairs = [(int(a), int(b)) for a, b in domains]
    patches = []
    for a, b in pairs:
        a, b = int(a), int(b)
        if b - a < min_size:
            continue
        patches.append(ax.add_patch(Rectangle((a - 0.5, a - 0.5), b - a, b - a, **kw)))
    return patches


def draw_loops(ax, loops: pd.DataFrame, bins, *, symmetric: bool = True, **kwargs):
    """Circle loops on a matrix drawn with ``imshow`` (one row per locus).

    Parameters
    ----------
    ax : matplotlib Axes
    loops : DataFrame
        BEDPE-like loop table (``start1``, ``start2``; ``chrom1`` filters to the matrix chromosome).
    bins : DataFrame or array
        The loci of the matrix rows (e.g. ``distance_map(...).bins``, or their starts); an anchor is placed
        on the row whose locus starts at it.
    symmetric : bool
        Circle both ``(i, j)`` and ``(j, i)`` (default) or only ``(row of start1, column of start2)``.
    **kwargs
        Passed to ``ax.plot`` (default open cyan circles).

    Returns
    -------
    list of Line2D
    """
    starts, chrom = _row_starts(bins)
    row = {int(s): k for k, s in enumerate(starts)}
    table = loops
    cc = "chrom1" if "chrom1" in table.columns else ("chrom" if "chrom" in table.columns else None)
    if chrom is not None and cc is not None:
        table = table[table[cc].astype(str) == chrom]
    kw = {"marker": "o", "linestyle": "none", "mfc": "none", "mec": "cyan", "mew": 1.5, "ms": 10, **kwargs}
    lines = []
    for s1, s2 in zip(table["start1"].to_numpy(np.int64), table["start2"].to_numpy(np.int64)):
        if int(s1) not in row or int(s2) not in row:
            continue
        i, j = row[int(s1)], row[int(s2)]
        xs, ys = ([j, i], [i, j]) if symmetric else ([j], [i])
        lines += ax.plot(xs, ys, **kw)
    return lines


def plot_compartments(cd, keys: Sequence[str], *, chrom: Optional[str] = None,
                      names: Optional[Sequence[str]] = None, fig=None):
    """Compartment tracks along a chromosome: per call the score (A positive, red; B blue) and the A/B
    labels as a bar, all on the loci of ``cd``.

    Parameters
    ----------
    cd : ChromData
        Holds the calls (``cd.results[key]``: per-bin tables with ``chrom, start, end``, ``compartment`` and
        ``pc2`` / ``pc1`` / ``score``, as :func:`uchrom.strc.comp.call_compartments_axes_pc` and
        :func:`uchrom.strc.comp.call_compartments_hic` store them).  Each locus of ``cd.bins`` shows the
        call of the bin that holds its midpoint, so calls on different bins (imaging loci, Hi-C bins) line
        up.
    keys : sequence of str
        The calls to show, top to bottom.
    chrom : str, optional
        Default: the first chromosome of the first call.
    names : sequence of str, optional
        Track labels (default the keys).
    fig : Figure, optional

    Returns
    -------
    Figure
    """
    from uchrom.strc.comp.hic_pc1 import _per_locus

    keys = list(keys)
    names = list(names) if names is not None else keys
    if chrom is None:
        chrom = str(pd.DataFrame(cd.results[keys[0]])["chrom"].iloc[0])
    on = (cd.bins["chrom"].astype(str) == chrom).to_numpy()
    order = np.argsort(cd.bins["start"].to_numpy()[on], kind="mergesort")
    loci = cd.bins[on].iloc[order]
    mid = (loci["start"].to_numpy() + loci["end"].to_numpy()) / 2e6
    if fig is None:
        fig = plt.figure(figsize=(7, 1.2 + 1.5 * len(keys)))
    ratios = [r for _ in keys for r in (3, 0.6)]
    axes = np.atleast_1d(fig.subplots(2 * len(keys), 1, sharex=True, gridspec_kw={"height_ratios": ratios}))
    for k, (key, name) in enumerate(zip(keys, names)):
        labels, scores, _ = _per_locus(cd, key)
        labels, score = labels[on][order], scores[on][order]
        ax, bar = axes[2 * k], axes[2 * k + 1]
        ax.fill_between(mid, score, where=score > 0, color="tab:red", lw=0)
        ax.fill_between(mid, score, where=score < 0, color="tab:blue", lw=0)
        ax.axhline(0, color="grey", lw=0.5)
        ax.set_ylabel(name, fontsize=8)
        ax.set_yticks([])
        is_a = np.where(labels == None, np.nan, (labels == "A").astype(float))     # noqa: E711
        bar.imshow(is_a[None, :].astype(float), aspect="auto", cmap="coolwarm", vmin=0, vmax=1,
                   extent=[mid[0], mid[-1], 0, 1], interpolation="nearest")
        bar.set_yticks([])
        bar.set_ylabel("A/B", fontsize=8)
    axes[-1].set_xlabel(f"{chrom} position (Mb)")
    return fig


__all__ = ["draw_domains", "draw_loops", "plot_compartments"]
