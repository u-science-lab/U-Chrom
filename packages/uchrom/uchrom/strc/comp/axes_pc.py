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
4. Align the eigenvector signs with the highest-weight axis, weight each
   axis by the ArcFISH ``axis_weight`` and stack:
   ``features[i, :] = [w_x V_x[i], w_y V_y[i], w_z V_z[i]]``.  The
   ``pc2`` output column is the row sum, oriented so that ``A`` > 0.
5. Run ``KMeans(n_clusters=2)`` on the features to get A/B labels.
6. Filter tiny compartments below ``min_bins``: merge into the neighbour.
7. Assign labels ``'A'`` / ``'B'`` by the mean pairwise distance within
   each cluster — the cluster with the smaller mean intra-distance is
   treated as the more compacted one.  Without a tissue-specific gene
   annotation this is a convention, not ground truth.  (Caller can
   override via the ``a_cluster`` argument.)

Output
------
A DataFrame with columns ``chrom, start, end, bin_index, cluster,
compartment, pc2`` (one row per bin, all requested chromosomes merged),
stored with provenance at ``cd.results[key_added]`` (default
``"compartments.axes_pc"``).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd

from uchrom.convention import (
    UNSET,
    merge_tables,
    parse_legacy_call,
    resolve_chroms,
    select_spots,
    selection_inputs,
    store_and_return,
)
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
    *args,
    chrom=None,
    trace_ids=None,
    cells=None,
    params: Optional[CompartmentCallerParams] = None,
    device: str = "auto",
    key_added: Optional[str] = UNSET,
    copy: bool = False,
    verbose: bool = False,
    store=UNSET,
    result_key=UNSET,
):
    """Call A/B compartments (ArcFISH axes-PC; chromatin tracing).

    Parameters
    ----------
    cd : ChromData
    chrom : str, sequence of str, or None
        ``None`` (default) calls every chromosome and merges the tables.
    trace_ids, cells : sequence, optional
        Restrict the population to these traces / cells.
    params : CompartmentCallerParams, optional
    device : ``'auto' | 'cpu' | 'cuda' | 'mps'``
    key_added : str or None
        ``cd.results`` key (default ``"compartments.axes_pc"``); ``None``
        does not store.
    copy : bool
        ``True`` → return a new ChromData holding the result.

    Returns
    -------
    DataFrame (``copy=False``) or ChromData (``copy=True``)
        One row per bin: ``chrom, start, end, bin_index, cluster,
        compartment, pc2`` (``bin_index`` counts within the chromosome).

    Notes
    -----
    Deprecated 1.x forms (positional ``chrom``, ``store=``,
    ``result_key=``) still work with a ``DeprecationWarning`` and default
    to the 1.x key ``"compartments"``.
    """
    chrom, key_added, _ = parse_legacy_call(
        "call_compartments_axes_pc", args, chrom=chrom, key_added=key_added,
        store=store, result_key=result_key, default_key="compartments.axes_pc",
        legacy_key="compartments", copy=copy,
    )
    params = params or CompartmentCallerParams()
    work = select_spots(cd, trace_ids=trace_ids, cells=cells)
    chroms = resolve_chroms(work, chrom)
    frames = [_call_compartments_chrom(work, c, params, device, verbose) for c in chroms]
    table = merge_tables(frames, _empty_compartments())
    track = table[["chrom", "start", "end"]].assign(value=table["pc2"].to_numpy(dtype=float))
    return store_and_return(
        cd, table, key_added=key_added, copy=copy, kind="table",
        function="uchrom.strc.comp.call_compartments_axes_pc", params=params,
        inputs=selection_inputs(work, chroms, trace_ids, cells),
        intervals=[(key_added, compartment_segments(table), "segment")] if key_added else (),
        bin_tracks={f"{key_added}.pc2": track} if key_added else None,
    )


def compartment_segments(table: pd.DataFrame) -> pd.DataFrame:
    """Per-bin compartment calls → runs of equal label per chromosome.

    Columns ``chrom, start, end, label, n_bins, pc2`` (mean ``pc2`` of the
    run's bins).  Stored as the ``segment`` interval table
    ``cd.intervals[key_added]``.
    """
    rows = []
    for chrom, sub in table.groupby("chrom", sort=False, observed=True):
        sub = sub.sort_values("start", kind="mergesort")
        lab = sub["compartment"].astype(str).to_numpy()
        run = np.concatenate([[0], np.cumsum(lab[1:] != lab[:-1])])
        for _, g in sub.groupby(run, sort=True):
            rows.append({
                "chrom": str(chrom),
                "start": int(g["start"].iloc[0]),
                "end": int(g["end"].iloc[-1]),
                "label": str(g["compartment"].iloc[0]),
                "n_bins": int(len(g)),
                "pc2": float(g["pc2"].mean()),
            })
    cols = ["chrom", "start", "end", "label", "n_bins", "pc2"]
    if not rows:
        return pd.DataFrame({"chrom": pd.Series(dtype=str), "start": pd.Series(dtype="int64"),
                             "end": pd.Series(dtype="int64"), "label": pd.Series(dtype=str),
                             "n_bins": pd.Series(dtype="int64"), "pc2": pd.Series(dtype=float)})
    return pd.DataFrame(rows, columns=cols)


def _call_compartments_chrom(cd, chrom: str, params: CompartmentCallerParams,
                             device: str, verbose: bool) -> pd.DataFrame:
    """Per-chromosome kernel of :func:`call_compartments_axes_pc`."""
    from sklearn.cluster import KMeans

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

    # Eigenvector signs are arbitrary: align every axis with the highest-weight
    # axis so the summed track below does not cancel (KMeans is unaffected —
    # flipping a feature's sign keeps all Euclidean distances).
    ref = per_axis_pc2[int(np.argmax(w))]
    for ax in range(3):
        if float(per_axis_pc2[ax] @ ref) < 0:
            per_axis_pc2[ax] = -per_axis_pc2[ax]

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
    # orient the track: positive = the "A" cluster
    is_a = labels == a_cluster
    if is_a.any() and (~is_a).any() and track[is_a].mean() < track[~is_a].mean():
        track = -track

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
    return pd.DataFrame(rows)


def _empty_compartments() -> pd.DataFrame:
    return pd.DataFrame({
        "chrom": pd.Series(dtype=str),
        "start": pd.Series(dtype="int64"),
        "end": pd.Series(dtype="int64"),
        "bin_index": pd.Series(dtype="int64"),
        "cluster": pd.Series(dtype="int64"),
        "compartment": pd.Series(dtype=str),
        "pc2": pd.Series(dtype="float64"),
    })


__all__ = [
    "call_compartments_axes_pc",
    "compartment_segments",
    "CompartmentCallerParams",
]
