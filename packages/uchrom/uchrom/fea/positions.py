"""Where the spots sit in their nucleus: the centre of a cell's (or a trace's) spots and each spot's radial
position relative to it.

    centres = spot_centroids(cd, by="cell", stat="median")     # x, y, z per cell
    radial_position(cd)                                        # -> cd.spot_tracks["radial_position"]
"""

from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd

from .registry import append_feature_registry_entry

_BY = {"cell": "cell_id", "trace": "trace_id"}
_STATS = ("mean", "median")


def _group_keys(cd, by: str) -> tuple[str, np.ndarray]:
    if by not in _BY:
        raise ValueError(f"by must be one of {sorted(_BY)}, got {by!r}")
    col = _BY[by]
    if col not in cd.spots.columns:
        raise KeyError(f"by={by!r} needs a {col!r} column in cd.spots")
    return col, cd.spots[col].astype(str).to_numpy()


def _check_stat(stat: str, name: str) -> str:
    if stat not in _STATS:
        raise ValueError(f"{name} must be one of {_STATS}, got {stat!r}")
    return stat


def spot_centroids(cd, *, by: str = "cell", stat: str = "mean") -> pd.DataFrame:
    """The centre of the spots of every cell (or trace): the per-axis mean or median of their coordinates.

    An estimate of the nucleus centre from the DNA spots alone — e.g. to check that a segmentation centroid
    shares the frame of ``coords``, or to register it as an inferred cell position
    (``cd.set_cell_positions(spot_centroids(cd), status="inferred", ...)``).

    Parameters
    ----------
    cd : ChromData
    by : ``"cell"`` (default; needs ``cell_id``) or ``"trace"``
    stat : ``"mean"`` (default) or ``"median"``
        Per axis; NaN coordinates are skipped.

    Returns
    -------
    DataFrame
        ``x, y, z`` indexed by ``cell_id`` (or ``trace_id``) as strings, sorted.
    """
    col, keys = _group_keys(cd, by)
    _check_stat(stat, "stat")
    xyz = pd.DataFrame(np.asarray(cd.coords, dtype=np.float64), columns=["x", "y", "z"])
    out = getattr(xyz.groupby(keys), stat)()
    out.index.name = col
    return out


def radial_position(cd, *, by: str = "cell", centre: str = "median", scale: Optional[float] = 0.95,
                    key_added: Optional[str] = "radial_position", copy: bool = False):
    """Radial position of every spot: its distance from the centre of its cell's spots, scaled per cell.

    The centre is the per-axis ``centre`` (median by default) of the cell's spots (:func:`spot_centroids`);
    the distance is divided by the ``scale`` quantile of the distances of that cell's spots (the 95th
    percentile by default — a robust nuclear radius), so ~0 is the nucleus centre and ~1 its edge, comparable
    between cells of different size.  ``scale=None`` keeps the distance in the unit of the coordinates.

    Parameters
    ----------
    cd : ChromData
        In memory (a backed object needs ``key_added=None``: its spot tracks are read-only).
    by : ``"cell"`` (default; needs ``cell_id``) or ``"trace"``
        The group whose spots give the centre (and the scale): the nucleus, or one chromatin fibre.
    centre : ``"median"`` (default) or ``"mean"``
    scale : float in (0, 1] or None
        Quantile of the group's distances to divide by; ``None``: no scaling.
    key_added : str or None
        The ``cd.spot_tracks`` column to write (default ``"radial_position"``), recorded in
        ``cd.uns["feature_registry"]``; ``None``: only return the values.
    copy : bool
        ``True``: write to a copy of ``cd`` and return it.

    Returns
    -------
    Series (``copy=False``) or ChromData (``copy=True``)
        One value per spot (index = the rows of ``cd.spots``); NaN for spots with a NaN coordinate.
    """
    col, keys = _group_keys(cd, by)
    _check_stat(centre, "centre")
    if scale is not None and not 0.0 < float(scale) <= 1.0:
        raise ValueError(f"scale must be a quantile in (0, 1] or None, got {scale!r}")
    if copy and key_added is None:
        raise ValueError("radial_position(copy=True) needs a key_added")
    if key_added is not None and getattr(cd, "backed", False) and not copy:
        raise ValueError("spot tracks of a backed ChromData are read-only: pass key_added=None (or read it "
                         "into memory)")
    xyz = np.asarray(cd.coords, dtype=np.float64)
    c = pd.DataFrame(xyz, columns=list("xyz")).groupby(keys).transform(centre).to_numpy()
    r = np.linalg.norm(xyz - c, axis=1)
    if scale is not None:
        q = float(scale)
        r = r / pd.Series(r).groupby(keys).transform(lambda s: s.quantile(q)).to_numpy()
    values = pd.Series(r, index=cd.spots.index, name=key_added or "radial_position")
    if key_added is None:
        return values
    target = cd.to_memory().copy() if copy else cd
    target.spot_tracks[key_added] = r
    append_feature_registry_entry(target, {
        "feature_group": "radial_position",
        "features": [key_added],
        "axis": "spot",
        "parameters": {"by": by, "group_column": col, "centre": centre,
                       "scale_quantile": None if scale is None else float(scale)},
        "created_by": "uchrom.fea.radial_position",
    })
    return target if copy else values


__all__ = ["radial_position", "spot_centroids"]
