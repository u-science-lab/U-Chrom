"""How well cells group: clusters against known labels, neighbourhoods, and what drives an embedding."""

from __future__ import annotations

from typing import Dict, Optional, Sequence, Union

import numpy as np
import pandas as pd


def cluster_agreement(labels, truth) -> Dict[str, float]:
    """Adjusted Rand index and normalised mutual information of two labellings of the same cells."""
    from sklearn.metrics import adjusted_rand_score, normalized_mutual_info_score

    labels, truth = np.asarray(labels), np.asarray(truth)
    if labels.shape != truth.shape:
        raise ValueError(f"{labels.shape} labels against {truth.shape} truth")
    return {"ARI": float(adjusted_rand_score(truth, labels)), "NMI": float(normalized_mutual_info_score(truth, labels))}


def knn_purity(x, truth, *, k: int = 10) -> float:
    """Mean fraction of each cell's ``k`` nearest neighbours (Euclidean, the cell itself left out) that
    share its label."""
    from sklearn.neighbors import NearestNeighbors

    x, truth = np.asarray(x, dtype=np.float64), np.asarray(truth)
    k = int(min(k, len(x) - 1))
    nn = NearestNeighbors(n_neighbors=k + 1).fit(x)
    idx = nn.kneighbors(x, return_distance=False)[:, 1:]
    return float((truth[idx] == truth[:, None]).mean())


def _cell_mask(cd, cells) -> np.ndarray:
    n = cd.n_cells
    if cells is None:
        return np.ones(n, bool)
    if isinstance(cells, str):                         # a boolean column, or a column == "pass"
        col = cd.cells[cells]
        return (col == "pass").to_numpy() if col.dtype != bool else col.to_numpy()
    cells = np.asarray(cells)
    if cells.dtype == bool:
        if len(cells) != n:
            raise ValueError(f"a boolean mask of {len(cells)} for {n} cells")
        return cells
    return pd.Index([str(c) for c in cd.cells.index]).isin([str(c) for c in cells])


def score_embedding(
    cd,
    use: str,
    truth: str,
    *,
    cells: Union[None, str, Sequence] = None,
    n_clusters: Optional[int] = None,
    k: int = 10,
    depth: Optional[str] = None,
    random_state: int = 0,
) -> Dict[str, float]:
    """Score an embedding ``cd.cellm[use]`` against known labels ``cd.cells[truth]``.

    - ``ARI`` / ``NMI``: k-means with as many clusters as labels (``n_clusters``) against the labels;
    - ``kNN purity``: :func:`knn_purity` with ``k`` neighbours;
    - ``|r| dim 1 ~ log depth`` (with ``depth``, a cells column such as the number of contacts): how much
      the first dimension follows sequencing depth rather than biology.

    ``cells`` restricts the scoring: cell ids, a boolean mask, or a cells column (``"higashi_qc"``: the
    cells marked ``"pass"``).  Cells with a missing embedding row are left out.
    """
    from sklearn.cluster import KMeans

    x = np.asarray(cd.cellm[use], dtype=np.float64)
    mask = _cell_mask(cd, cells) & np.isfinite(x).all(axis=1)
    y = cd.cells[truth].astype(str).to_numpy()[mask]
    x = x[mask]
    n = n_clusters or len(np.unique(y))
    pred = KMeans(n, n_init=10, random_state=random_state).fit_predict(x)
    out = {"n_cells": int(mask.sum()), **cluster_agreement(pred, y), "kNN purity": knn_purity(x, y, k=k)}
    if depth is not None:
        d = np.log(cd.cells[depth].to_numpy(dtype=np.float64)[mask])
        out["|r| dim 1 ~ log depth"] = float(abs(np.corrcoef(x[:, 0], d)[0, 1]))
    return out
