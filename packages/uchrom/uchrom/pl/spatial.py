"""Cells in tissue space coloured by a per-cell value: one panel per region (section / field of view), squares on
a barcode grid, dots otherwise; numeric values on a colour scale (robust limits by default), categories with a
legend; the y axis points down when the position record says so (``y_axis="down"``, image rows)."""

from __future__ import annotations

from typing import Optional, Sequence, Union

import numpy as np
import pandas as pd

__all__ = ["plot_spatial"]


def plot_spatial(cd, color: Union[str, pd.Series], *, key: str = "default", regions: Optional[Sequence[str]] = None,
                 cells=None, physical: bool = False, ax=None, size: Optional[float] = None,
                 marker: Optional[str] = None, cmap: str = "viridis", vmin=None, vmax=None,
                 robust: bool = True, center: Optional[float] = None, title: Optional[str] = None,
                 colorbar: bool = True, panel_width: float = 3.2):
    """Plot cells at their positions coloured by ``color``.

    Parameters
    ----------
    cd
        A ``ChromData`` with cell positions.
    color
        A ``cd.cells`` column, or a Series indexed by cell id.
    key, cells, physical
        The position set, a subset of cells, physical units (:func:`uchrom.spatial.cell_positions_table`).
    regions
        The regions to draw (default all); one panel each.
    ax
        One Axes per region (a single Axes for one region); default: a new figure.
    size, marker
        Marker area and shape (default: squares filling a unit grid when positions are integers, dots else).
    vmin, vmax, robust, center
        Colour limits: given, else the 2nd / 98th percentiles (``robust``) or the range; ``center`` makes the
        scale symmetric around it (e.g. 0 for a centred score, with ``cmap="RdBu_r"``).

    Returns
    -------
    list of Axes
    """
    import matplotlib.pyplot as plt

    from ..spatial.graph import cell_positions_table

    pos = cell_positions_table(cd, key, cells=cells, physical=physical)
    if isinstance(color, str):
        if color not in cd.cells.columns:
            raise KeyError(f"{color!r} is not a cells column")
        vals = pd.Series(cd.cells[color].to_numpy(), index=[str(c) for c in cd._cell_ids_axis()], name=color)
    else:
        vals = color.copy()
        vals.index = vals.index.astype(str)
    vals = vals.reindex(pos.index)
    reg = pos["region"].astype(str) if "region" in pos.columns else pd.Series("", index=pos.index)
    names = [r for r in pd.unique(reg) if regions is None or r in set(map(str, regions))]
    if ax is None:
        fig, axes = plt.subplots(1, len(names), figsize=(panel_width * len(names) + (0.6 if colorbar else 0),
                                                         panel_width), squeeze=False)
        axes = list(axes[0])
    else:
        axes = list(np.atleast_1d(ax))
        fig = axes[0].figure
    numeric = pd.api.types.is_numeric_dtype(vals) and not pd.api.types.is_bool_dtype(vals)
    if numeric:
        v = vals.to_numpy(float)
        fin = v[np.isfinite(v)]
        lo = vmin if vmin is not None else (np.percentile(fin, 2) if robust and len(fin) else np.nanmin(v))
        hi = vmax if vmax is not None else (np.percentile(fin, 98) if robust and len(fin) else np.nanmax(v))
        if center is not None:
            half = max(abs(hi - center), abs(lo - center))
            lo, hi = center - half, center + half
    else:
        cats = pd.Categorical(vals.astype("object").where(vals.notna(), None))
        palette = plt.get_cmap("tab20" if len(cats.categories) > 10 else "tab10")
        colours = {c: palette(i % palette.N) for i, c in enumerate(cats.categories)}
    xy = pos[["x", "y"]].to_numpy(float)
    y_down = cd.cell_positions(key).attrs.get("cell_spatial", {}).get("y_axis") == "down"
    grid = np.allclose(xy, np.round(xy))
    mk = marker or ("s" if grid else "o")
    sc = None
    for a, r in zip(axes, names):
        m = (reg == r).to_numpy()
        x, y = xy[m, 0], xy[m, 1]
        span = max(np.ptp(x) if len(x) else 1, np.ptp(y) if len(y) else 1, 1)
        s = size if size is not None else ((72 * panel_width * 0.85 / span) ** 2 if grid else 6)
        if numeric:
            vv = v[m]
            nan = ~np.isfinite(vv)
            if nan.any():
                a.scatter(x[nan], y[nan], s=s, marker=mk, c="0.85", linewidths=0)
            sc = a.scatter(x[~nan], y[~nan], c=vv[~nan], s=s, marker=mk, cmap=cmap, vmin=lo, vmax=hi,
                           linewidths=0, rasterized=len(x) > 2000)
        else:
            cv = np.asarray(cats)[m]
            for c in cats.categories:
                k = cv == c
                a.scatter(x[k], y[k], s=s, marker=mk, color=colours[c], linewidths=0, label=str(c),
                          rasterized=len(x) > 2000)
        a.set_aspect("equal")
        if y_down:
            a.invert_yaxis()                               # image convention: rows grow downwards
        a.set_xticks([])
        a.set_yticks([])
        for side in a.spines.values():
            side.set_visible(False)
        a.set_title(r if title is None else (f"{title} — {r}" if r else title), fontsize=9)
    if numeric and colorbar and sc is not None:
        cb = fig.colorbar(sc, ax=axes, shrink=0.7, pad=0.02)
        cb.set_label(vals.name or "", fontsize=8)
        cb.ax.tick_params(labelsize=7)
    elif not numeric:
        axes[-1].legend(loc="center left", bbox_to_anchor=(1.0, 0.5), fontsize=7, frameon=False, markerscale=2)
    return axes
