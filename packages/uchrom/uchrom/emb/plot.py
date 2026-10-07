"""A cell embedding as a scatter plot (matplotlib)."""

from __future__ import annotations

from typing import Dict, Optional, Sequence, Union

import numpy as np
import pandas as pd

__all__ = ["plot_embedding"]


def plot_embedding(
    cd,
    use: str,
    color: Union[None, str, Sequence] = None,
    *,
    ax=None,
    dims: Sequence[int] = (0, 1),
    palette: Optional[Dict[str, object]] = None,
    cmap: str = "viridis",
    annotate: bool = True,
    legend: bool = False,
    colorbar: bool = True,
    colorbar_label: Optional[str] = None,
    s: float = 4,
    title: Optional[str] = None,
):
    """Scatter plot of the embedding ``cd.cellm[use]``, the cells coloured by a label or a value.

    Parameters
    ----------
    cd : ChromData
        With ``cd.cellm[use]`` (rows = ``cd.cells``).
    use : str
        The embedding (``"rna_umap"``, ``"hic_umap"``, ``"higashi"``, …).
    color : str or array-like, optional
        A ``cd.cells`` column or one value per cell.  Text / categorical values are drawn as groups
        (``palette``, default ``tab20`` + ``Dark2``), numbers on the colour map ``cmap`` with a colour bar.
        Cells without a value are drawn in light grey.
    ax : matplotlib Axes, optional
        Where to draw (default: a new figure).
    dims : (int, int)
        The two dimensions shown (0-based).
    annotate : bool
        Write each group's name at the median position of its cells.
    legend : bool
        Add a legend of the groups.
    colorbar, colorbar_label
        For numeric colours: draw a colour bar, with this label (default: the column name).
    s : float
        Marker size.
    title : str, optional
        Default: the embedding's label (``cd.uns["embeddings"][use]["label"]``) and the colour's name.

    Returns
    -------
    The matplotlib Axes.  Cells whose embedding row is missing (NaN) are not drawn; the axes are labelled
    with the embedding's ``axis_prefix`` (``UMAP1``, ``PC2``, …).
    """
    import matplotlib.pyplot as plt

    if use not in cd.cellm:
        raise KeyError(f"cd.cellm has no {use!r}; available: {sorted(cd.cellm)}")
    xy = np.asarray(cd.cellm[use], dtype=np.float64)[:, list(dims)]
    meta = (cd.uns.get("embeddings") or {}).get(use) or {}
    if ax is None:
        _, ax = plt.subplots(figsize=(3.6, 3.4))
    name = color if isinstance(color, str) else None
    values = None
    if color is not None:
        values = cd.cells[color] if isinstance(color, str) else pd.Series(np.asarray(color), index=cd.cells.index)
        if len(values) != len(xy):
            raise ValueError(f"color has {len(values)} values for {len(xy)} cells")
    shown = np.isfinite(xy).all(axis=1)

    if values is None:
        ax.scatter(xy[shown, 0], xy[shown, 1], s=s, lw=0, color="0.4")
    elif (pd.api.types.is_numeric_dtype(values) and not pd.api.types.is_bool_dtype(values)
          and not isinstance(values.dtype, pd.CategoricalDtype)):
        v = values.to_numpy(dtype=np.float64)
        miss = shown & ~np.isfinite(v)
        ax.scatter(xy[miss, 0], xy[miss, 1], s=s, lw=0, color="0.85")
        ok = shown & np.isfinite(v)
        sc = ax.scatter(xy[ok, 0], xy[ok, 1], s=s, lw=0, c=v[ok], cmap=cmap)
        if colorbar:
            ax.figure.colorbar(sc, ax=ax, label=colorbar_label if colorbar_label is not None else (name or ""))
    else:
        missing = values.isna().to_numpy()
        labels = values.astype(str).to_numpy()
        ax.scatter(xy[shown & missing, 0], xy[shown & missing, 1], s=s, lw=0, color="0.85")
        cats = sorted(set(labels[shown & ~missing]))
        colors = palette or dict(zip(cats, _cycle(plt.cm.tab20.colors + plt.cm.Dark2.colors, len(cats))))
        for c in cats:
            m = shown & ~missing & (labels == c)
            ax.scatter(xy[m, 0], xy[m, 1], s=s, lw=0, color=colors[c], label=c)
            if annotate:
                ax.text(*np.median(xy[m], axis=0), c, fontsize=6.5, ha="center", va="center", weight="bold")
        if legend:
            ax.legend(fontsize=7, markerscale=3, frameon=False, loc="best")
    prefix = str(meta.get("axis_prefix") or "")
    ax.set_xlabel(f"{prefix}{dims[0] + 1}" if prefix else "", fontsize=8)
    ax.set_ylabel(f"{prefix}{dims[1] + 1}" if prefix else "", fontsize=8)
    ax.set_xticks([])
    ax.set_yticks([])
    if title is None:
        title = str(meta.get("label") or use) + (f": {name}" if name else "")
    ax.set_title(title, fontsize=9)
    return ax


def _cycle(colors, n: int):
    return [colors[i % len(colors)] for i in range(n)]
