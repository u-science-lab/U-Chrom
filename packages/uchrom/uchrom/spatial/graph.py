"""Neighbour graphs of cells (or spatial Hi-C spots) from their positions in the tissue.

Positions are read with :meth:`ChromData.cell_positions` (``key``: the position set, e.g. ``"default"``).
Cells in different regions — sections of a spatial Hi-C study, fields of view of a tracing experiment (the
record's ``region_col``) — are never neighbours: each region is its own coordinate frame.  The graph is
cheap to build (a k-d tree per region), so it is computed when needed and not stored on the object.

Methods: ``"knn"`` (each cell to its ``n_neighbors`` nearest, made symmetric), ``"radius"`` (every pair closer
than ``radius``; on a barcode grid in spot units ``radius=1`` gives the 4 and ``radius=1.5`` the 8 adjacent
spots), ``"delaunay"`` (the edges of the Delaunay triangulation, 2-D positions).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Optional

import numpy as np
import pandas as pd
import scipy.sparse as sps

__all__ = ["SpatialGraph", "spatial_neighbors", "cell_positions_table"]


@dataclass
class SpatialGraph:
    """A neighbour graph over cells.

    Attributes
    ----------
    cell_ids : ndarray of str
        The cells, in the order of the rows and columns of ``adjacency``.
    adjacency : scipy.sparse.csr_matrix (n, n)
        1 for neighbours (symmetric, zero diagonal).
    positions : DataFrame
        ``x, y[, z]`` of the cells (index ``cell_id``) and ``region`` when the position set has regions.
    params : dict
        How the graph was built.
    """

    cell_ids: np.ndarray
    adjacency: sps.csr_matrix
    positions: pd.DataFrame
    params: dict = field(default_factory=dict)

    @property
    def n(self) -> int:
        return len(self.cell_ids)

    @property
    def regions(self) -> Optional[np.ndarray]:
        return self.positions["region"].astype(str).to_numpy() if "region" in self.positions else None

    def weights(self, transform: str = "r") -> sps.csr_matrix:
        """The spatial weights: ``"b"`` binary (the adjacency), ``"r"`` row-standardised (each row sums to 1;
        cells without neighbours keep an empty row)."""
        w = self.adjacency.astype(float).tocsr()
        if transform == "b":
            return w
        if transform != "r":
            raise ValueError(f"transform must be 'r' or 'b', not {transform!r}")
        deg = np.asarray(w.sum(axis=1)).ravel()
        inv = np.divide(1.0, deg, out=np.zeros_like(deg), where=deg > 0)
        return sps.diags(inv) @ w

    def subset(self, mask) -> "SpatialGraph":
        """The graph restricted to the cells of a boolean mask (edges to removed cells are dropped)."""
        mask = np.asarray(mask, bool)
        idx = np.flatnonzero(mask)
        return SpatialGraph(self.cell_ids[idx], self.adjacency[idx][:, idx].tocsr(),
                            self.positions.iloc[idx], dict(self.params))

    def neighbour_counts(self) -> np.ndarray:
        return np.diff(self.adjacency.indptr)


def cell_positions_table(cd, key: str = "default", *, cells: Optional[Iterable] = None,
                         physical: bool = False) -> pd.DataFrame:
    """The positions of ``cells`` (all cells by default) with finite coordinates: ``x, y[, z][, region]``."""
    pos = cd.cell_positions(key, physical=physical)
    if cells is not None:
        want = pd.Index([str(c) for c in cells])
        pos = pos.loc[pos.index.astype(str).isin(want)]
    dims = [c for c in ("x", "y", "z") if c in pos.columns and pos[c].notna().any()]
    pos = pos.loc[np.isfinite(pos[dims].to_numpy(float)).all(axis=1)]
    out = pos[dims + (["region"] if "region" in pos.columns else [])].copy()
    out.index = out.index.astype(str)
    return out


def _edges_knn(xy: np.ndarray, k: int):
    from scipy.spatial import cKDTree

    k = min(k, len(xy) - 1)
    if k < 1:
        return np.zeros(0, int), np.zeros(0, int)
    _, j = cKDTree(xy).query(xy, k=k + 1)
    i = np.repeat(np.arange(len(xy)), k)
    j = j[:, 1:].ravel()
    keep = j < len(xy)
    return i[keep], j[keep]


def _edges_radius(xy: np.ndarray, r: float):
    from scipy.spatial import cKDTree

    pairs = cKDTree(xy).query_pairs(r, output_type="ndarray")
    return pairs[:, 0], pairs[:, 1]


def _edges_delaunay(xy: np.ndarray):
    from scipy.spatial import Delaunay

    if xy.shape[1] != 2:
        raise ValueError("method='delaunay' needs 2-D positions")
    if len(xy) < 3:
        return np.zeros(0, int), np.zeros(0, int)
    tri = Delaunay(xy).simplices
    e = np.concatenate([tri[:, [0, 1]], tri[:, [1, 2]], tri[:, [0, 2]]])
    return e[:, 0], e[:, 1]


def spatial_neighbors(cd, *, key: str = "default", method: str = "knn", n_neighbors: int = 6,
                      radius: Optional[float] = None, cells: Optional[Iterable] = None,
                      physical: bool = False) -> SpatialGraph:
    """The neighbour graph of the cells of ``cd`` in tissue space.

    Parameters
    ----------
    cd
        A ``ChromData`` with cell positions (:meth:`~chromdata.ChromData.set_cell_positions`).
    key
        The position set.
    method
        ``"knn"``, ``"radius"`` or ``"delaunay"`` (module docstring).  On a regular barcode grid prefer
        ``"radius"``: the k nearest of a grid are tied.
    n_neighbors, radius
        Of ``"knn"`` and ``"radius"`` (in the units of the positions).
    cells
        Only these cells (default: every cell with a position).
    physical
        Positions in physical units for positions stored in voxels.

    Returns
    -------
    SpatialGraph
        Symmetric, no self-loops, no edges between regions.
    """
    pos = cell_positions_table(cd, key, cells=cells, physical=physical)
    dims = [c for c in ("x", "y", "z") if c in pos.columns]
    xy = pos[dims].to_numpy(float)
    groups = (pos["region"].astype(str).to_numpy() if "region" in pos.columns else np.zeros(len(pos), int))
    rows, cols = [], []
    for g in pd.unique(groups):
        idx = np.flatnonzero(groups == g)
        sub = xy[idx]
        if method == "knn":
            i, j = _edges_knn(sub, int(n_neighbors))
        elif method == "radius":
            if radius is None:
                raise ValueError("method='radius' needs radius=")
            i, j = _edges_radius(sub, float(radius))
        elif method == "delaunay":
            i, j = _edges_delaunay(sub)
        else:
            raise ValueError(f"method must be 'knn', 'radius' or 'delaunay', not {method!r}")
        rows.append(idx[i])
        cols.append(idx[j])
    r = np.concatenate(rows) if rows else np.zeros(0, int)
    c = np.concatenate(cols) if cols else np.zeros(0, int)
    n = len(pos)
    a = sps.coo_matrix((np.ones(len(r)), (r, c)), shape=(n, n)).tocsr()
    a = ((a + a.T) > 0).astype(np.float64).tocsr()
    a.setdiag(0)
    a.eliminate_zeros()
    params = {"key": key, "method": method, "n_neighbors": int(n_neighbors) if method == "knn" else None,
              "radius": radius if method == "radius" else None, "physical": bool(physical),
              "regions": None if "region" not in pos.columns else [str(g) for g in pd.unique(groups)]}
    return SpatialGraph(pos.index.to_numpy(dtype=object), a, pos, params)
