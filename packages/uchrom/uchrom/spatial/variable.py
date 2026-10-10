"""Which per-cell features vary in space: SPARK-X (default) or Moran's I on the cells of a ``ChromData``, per
region (section / field of view), optionally adjusted for covariates such as cell-type composition or depth.

A 3-D genome feature that follows the cell types will vary in space wherever the cell types do.  Testing with
the composition (or the cell type) as covariates asks the second question — does the feature vary beyond what
the cells' identities explain?  Both answers are worth reporting; the second is the one that needs space.
"""

from __future__ import annotations

from typing import Iterable, Optional, Sequence, Union

import numpy as np
import pandas as pd

from ..convention import UNSET, store_and_return
from .autocorr import cell_values, spatial_autocorr
from .graph import SpatialGraph, cell_positions_table, spatial_neighbors
from .sparkx import sparkx

__all__ = ["covariate_matrix", "spatially_variable"]


def covariate_matrix(cd, covariates, cell_ids: Sequence[str]) -> Optional[pd.DataFrame]:
    """The covariates of ``cell_ids`` as a numeric DataFrame: ``covariates`` is a DataFrame (index = cell ids),
    or names of ``cd.cells`` columns (and ``cd.cellm`` keys: their columns); categorical columns become
    indicators (the first level dropped)."""
    if covariates is None:
        return None
    ids = pd.Index([str(c) for c in cell_ids])
    if isinstance(covariates, pd.DataFrame):
        df = covariates.copy()
        df.index = df.index.astype(str)
        df = df.reindex(ids)
    else:
        names = [covariates] if isinstance(covariates, str) else list(covariates)
        axis = pd.Index([str(c) for c in cd._cell_ids_axis()])
        parts = []
        for name in names:
            if name in cd.cells.columns:
                col = cd.cells[name]
                parts.append(pd.Series(col.to_numpy(), index=axis, name=name, dtype=col.dtype).to_frame())
            elif name in cd.cellm:
                arr = np.asarray(cd.cellm[name], float).reshape(len(axis), -1)
                parts.append(pd.DataFrame(arr, index=axis, columns=[f"{name}[{j}]" for j in range(arr.shape[1])]))
            else:
                raise KeyError(f"covariate {name!r} is neither a cells column nor a cellm key")
        df = pd.concat(parts, axis=1).reindex(ids)
    cat = [c for c in df.columns if not pd.api.types.is_numeric_dtype(df[c])]
    if cat:
        df = pd.get_dummies(df, columns=cat, drop_first=True, dummy_na=False, dtype=float)
    return df.astype(float)


def spatially_variable(cd, features: Union[None, str, Sequence[str]] = None, *, values=None,
                       key: str = "default", method: str = "sparkx", covariates=None,
                       cells: Optional[Iterable] = None, regions: Optional[Sequence[str]] = None,
                       graph: Optional[SpatialGraph] = None, graph_kwargs: Optional[dict] = None,
                       kernels="mixture", n_perms: int = 0, physical: bool = False,
                       key_added=UNSET, copy: bool = False):
    """Test every feature for spatial variation, region by region.

    Parameters
    ----------
    cd
        A ``ChromData`` with cell positions.
    features, values
        The per-cell values (:func:`~uchrom.spatial.cell_values`: ``cd.cells`` columns, a ``cd.cellm`` key,
        or a DataFrame indexed by cell id).
    key
        The position set (its ``region_col`` splits the cells into regions).
    method
        ``"sparkx"`` (:func:`~uchrom.spatial.sparkx`) or ``"moran"`` (:func:`~uchrom.spatial.spatial_autocorr`
        on ``graph`` / ``spatial_neighbors(**graph_kwargs)``; with covariates, Moran's I of the residuals of a
        least-squares fit on them, permutation p-values recommended).
    covariates
        Adjust for these (:func:`covariate_matrix`).
    cells, regions
        Only these cells / regions.
    kernels, n_perms
        Of SPARK-X / Moran's I.

    Returns
    -------
    DataFrame
        ``region, feature`` then the test's columns (``pval``, ``padj`` per region); stored as
        ``cd.results[key_added]`` (default ``"spatially_variable.<method>"``; None: not stored) per the
        calling convention.
    """

    if method not in ("sparkx", "moran"):
        raise ValueError(f"method must be 'sparkx' or 'moran', not {method!r}")
    pos = cell_positions_table(cd, key, cells=cells, physical=physical)
    vals = cell_values(cd, features, values=values).reindex(pos.index)
    cov = covariate_matrix(cd, covariates, pos.index)
    reg = pos["region"].astype(str) if "region" in pos.columns else pd.Series("all", index=pos.index)
    dims = [c for c in ("x", "y", "z") if c in pos.columns]
    tables = []
    for r in pd.unique(reg):
        if regions is not None and r not in set(map(str, regions)):
            continue
        m = (reg == r).to_numpy()
        ids = pos.index[m]
        if method == "sparkx":
            t = sparkx(vals.loc[ids], pos.loc[ids, dims].to_numpy(float),
                       covariates=None if cov is None else cov.loc[ids].to_numpy(float), kernels=kernels)
        else:
            g = graph.subset(np.isin(graph.cell_ids.astype(str), ids)) if graph is not None else \
                spatial_neighbors(cd, key=key, cells=ids, physical=physical, **(graph_kwargs or {}))
            v = vals.loc[ids]
            if cov is not None:
                v = _residuals(v, cov.loc[ids])
            t = spatial_autocorr(values=v, graph=g, n_perms=n_perms)
        t = t.reset_index()
        t.insert(0, "region", r)
        tables.append(t)
    table = pd.concat(tables, ignore_index=True) if tables else pd.DataFrame(columns=["region", "feature"])
    params = {"key": key, "method": method, "kernels": kernels if method == "sparkx" else None,
              "n_perms": n_perms, "physical": physical, "graph": graph.params if graph is not None else graph_kwargs,
              "covariates": None if cov is None else list(cov.columns)}
    inputs = {"n_cells": int(len(pos)), "features": [str(c) for c in vals.columns][:50],
              "n_features": int(vals.shape[1])}
    if key_added is UNSET:
        key_added = f"spatially_variable.{method}"
    return store_and_return(cd, table, key_added=key_added,
                            copy=copy, kind="table", function="uchrom.spatial.spatially_variable",
                            params=params, inputs=inputs)


def _residuals(values: pd.DataFrame, cov: pd.DataFrame) -> pd.DataFrame:
    """Least-squares residuals of each column on the covariates (+ intercept), cell by cell where both exist."""
    X = np.hstack([np.ones((len(cov), 1)), cov.to_numpy(float)])
    out = values.copy()
    okx = np.isfinite(X).all(axis=1)
    for c in values.columns:
        y = values[c].to_numpy(float)
        m = okx & np.isfinite(y)
        res = np.full(len(y), np.nan)
        if m.sum() > X.shape[1]:
            beta, *_ = np.linalg.lstsq(X[m], y[m], rcond=None)
            res[m] = y[m] - X[m] @ beta
        out[c] = res
    return out
