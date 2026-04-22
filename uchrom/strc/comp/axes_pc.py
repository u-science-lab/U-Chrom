"""ArcFISH-style A/B compartment caller using per-axis PC2.

Independent implementation of Yu et al. 2025 (*ArcFISH*,
bioRxiv 2025.11.26.690837v1) ``ABCaller.by_axes_pc``.

Algorithm (per chromosome)
--------------------------
1. Compute the per-axis LOWESS-normalised variance ``norm_var[c, i, j]``
   via the shared :mod:`uchrom.fea.arc` preprocessing.
2. Turn each axis' variance matrix into a pseudo-contact kernel
   ``K_c = exp(-norm_var_c)`` and symmetrise.
3. Spectral decomposition per axis: the **second-largest eigenvector**
   carries the compartment-level structure (the first is the overall
   distance trend).  Call it ``V_c``.
4. Weight each axis by the ArcFISH ``axis_weight`` and stack:
   ``features[i, :] = [w_x V_x[i], w_y V_y[i], w_z V_z[i]]``.
5. Run ``KMeans(n_clusters=2)`` on the features to get A/B labels.
6. Filter tiny compartments below ``min_bins``: merge into the neighbour.
7. Assign labels ``'A'`` / ``'B'`` by the mean pairwise distance within
   each cluster — the cluster with the smaller mean intra-distance is
   treated as the more compacted one.  Without a tissue-specific gene
   annotation this is a convention, not ground truth.  (Caller can
   override via the ``a_cluster`` argument.)

Output
------
A DataFrame with columns ``chrom, start, end, compartment, pc2,
 cluster, bin_index``.  Also written to ``cd.results['compartments']``
when ``store=True``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd

from uchrom.fea.arc import axis_variance_cube, filter_normalize, axis_weight


@dataclass
class CompartmentCallerParams:
    n_clusters: int = 2             # 2 for A/B; can be extended
    min_bins: int = 2               # minimum compartment size
    k_sigma: float = 4.0
    frac: float = 0.1
    random_state: int = 0
    a_cluster: Optional[int] = None   # if set, that cluster label is "A"


def _pseudo_contact_matrix(norm_var: np.ndarray) -> np.ndarray:
    """``K = exp(-norm_var)`` with NaN → 0 and forced symmetry."""
    v = np.where(np.isfinite(norm_var), norm_var, np.inf)
    K = np.exp(-v)
    K = 0.5 * (K + K.T)
    np.fill_diagonal(K, 0.0)
    return K


def _second_eigenvector(K: np.ndarray) -> np.ndarray:
    """Return the eigenvector associated with the 2nd-largest eigenvalue."""
    w, vecs = np.linalg.eigh(K)
    # eigh returns ascending eigenvalues → 2nd largest is index -2
    return vecs[:, -2]


def _filter_small_compartments(labels: np.ndarray, min_bins: int) -> np.ndarray:
    """Merge runs shorter than ``min_bins`` into the neighbour run."""
    labels = labels.astype(int).copy()
    B = len(labels)
    # Simple single-pass: find short runs, merge into whichever side is larger.
    changed = True
    while changed:
        changed = False
        # find contiguous runs
        runs = []
        i = 0
        while i < B:
            j = i
            while j + 1 < B and labels[j + 1] == labels[i]:
                j += 1
            runs.append((i, j, labels[i]))
            i = j + 1
        for k, (s, e, lab) in enumerate(runs):
            if (e - s + 1) < min_bins:
                left = runs[k - 1] if k > 0 else None
                right = runs[k + 1] if k + 1 < len(runs) else None
                if left is None and right is None:
                    continue
                pick = None
                if left is not None and right is not None:
                    pick = left if (left[1] - left[0]) >= (right[1] - right[0]) else right
                else:
                    pick = left or right
                labels[s: e + 1] = pick[2]
                changed = True
                break
    return labels


def call_compartments_axes_pc(
    cd,
    chrom: str,
    params: Optional[CompartmentCallerParams] = None,
    device: str = "auto",
    store: bool = True,
    result_key: str = "compartments",
    verbose: bool = False,
) -> pd.DataFrame:
    """Call A/B compartments on a single chromosome.

    Returns a DataFrame indexed by bin.  Stores it in
    ``cd.results[result_key]`` when ``store=True``.
    """
    from sklearn.cluster import KMeans

    params = params or CompartmentCallerParams()

    if verbose:
        print(f"[comp/{chrom}] variance cube + normalise...")
    cube = axis_variance_cube(cd, chrom=chrom, device=device)
    cube = filter_normalize(cube, k_sigma=params.k_sigma, frac=params.frac)
    norm_var = cube["norm_var"]
    bin_ids = cube["bin_ids"]
    B = len(bin_ids)

    w = axis_weight(cd, chrom=chrom, device=device)
    if verbose:
        print(f"[comp/{chrom}] axis weights: {w.round(3)}")

    # Per-axis PC2
    per_axis_pc2 = np.zeros((3, B), dtype=np.float64)
    for ax in range(3):
        K = _pseudo_contact_matrix(norm_var[ax])
        try:
            per_axis_pc2[ax] = _second_eigenvector(K)
        except np.linalg.LinAlgError:
            per_axis_pc2[ax] = 0.0

    # Weighted stack → (B, 3) feature matrix
    features = (per_axis_pc2.T * w[None, :])

    if verbose:
        print(f"[comp/{chrom}] KMeans on {B} bins × {features.shape[1]} features")

    km = KMeans(
        n_clusters=params.n_clusters,
        random_state=params.random_state,
        n_init=10,
    )
    raw_labels = km.fit_predict(features)

    labels = _filter_small_compartments(raw_labels, params.min_bins)

    # Compute a single "compartment track" (weighted average of per-axis PC2)
    # — useful for downstream plotting as a 1D signal.
    track = features.sum(axis=1)

    # Assign A/B — smaller mean intra-variance ≈ more compact ≈ "A" by convention
    n_clusters = len(np.unique(labels))
    if params.a_cluster is not None:
        a_cluster = int(params.a_cluster)
    else:
        intra_var = np.full(n_clusters, np.inf)
        unique_labels = np.unique(labels)
        for uli, lab in enumerate(unique_labels):
            idx = np.where(labels == lab)[0]
            if len(idx) < 2:
                continue
            sub = norm_var[:, idx][:, :, idx]
            intra_var[uli] = float(np.nanmean(sub))
        a_cluster = int(unique_labels[np.nanargmin(intra_var)])

    compartment = np.where(labels == a_cluster, "A", "B")

    rows = []
    for i in range(B):
        s, e = bin_ids[i]
        rows.append({
            "chrom": chrom,
            "start": int(s),
            "end": int(e),
            "bin_index": i,
            "cluster": int(labels[i]),
            "compartment": str(compartment[i]),
            "pc2": float(track[i]),
        })
    df = pd.DataFrame(rows)
    if store:
        _store(cd, result_key, df)
    return df


def _store(cd, key: str, df: pd.DataFrame):
    if getattr(cd, "results", None) is None:
        cd.results = {}
    cd.results[key] = df


__all__ = [
    "call_compartments_axes_pc",
    "CompartmentCallerParams",
]
