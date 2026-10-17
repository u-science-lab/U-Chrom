"""ArcFISH's A/B compartment caller for chromatin tracing: k-means on the weighted second eigenvectors of the
per-axis kernels (``ABCaller(method="axes")``).

Reference: Yu H. *et al.* ArcFISH: accurate and robust 3D genome feature discovery from chromatin tracing data.
bioRxiv 2025.11.26.690837 (github.com/hyuyu104/ArcFISH).  U-Chrom's own implementation of the published algorithm;
uchrom-reproducibility ``benchmarks/toolkit_parity/arcfish_parity/`` checks it against the authors' package (commit a21d889): the same eigenvectors and
compartments.

Algorithm (per chromosome or arm)
---------------------------------
1. Normalised variances ``norm_var`` (:func:`uchrom.fea.arc.filter_normalize`; a missing entry is set to 1, the
   value expected after normalisation) and the axis weights ``w`` (:func:`uchrom.fea.arc.axis_weight` of the loci
   called).
2. Per axis the eigenvector of the second-largest eigenvalue of ``exp(-norm_var)`` (``V_x, V_y, V_z``).
3. k-means (``KMeans(n_clusters=2, random_state=0, n_init=1)`` of scikit-learn, as the authors' default) of the
   loci on ``(w_x V_x, w_y V_y, w_z V_z)``.
4. Compartments shorter than ``min_compartment_bp`` (the distance from a run's first to its last locus start) are
   flipped, the shortest first, until none is left.
5. Which cluster is A: ``a_cluster`` if given; else with ``a_track`` the cluster whose loci have the higher mean of
   that ``cd.bin_tracks`` column (gene density, an active mark); else the authors' rule without a reference genome:
   per axis the median of ``norm_var`` over each cluster's block of pairs, and **A is the less compact cluster** in
   the majority of axes (B compartments are the more compacted).  (The authors' docstring says the opposite; their
   code, and this, follow the rule above.)

Output
------
One row per locus (``chrom, start, end, bin_index, cluster, compartment, pc2, eig_x, eig_y, eig_z``), stored with
provenance at ``cd.results[key_added]`` (default ``"compartments.axes_pc"``) with the runs as the ``segment``
intervals and ``pc2`` as a bin track.
"""

from __future__ import annotations

import warnings
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
from uchrom.fea.arc import _axis_weight_cube, _coord_cube_for_chrom, axis_variance_cube, filter_normalize


@dataclass
class CompartmentCallerParams:
    """Knobs of :func:`call_compartments_axes_pc` (module docstring).

    ``min_compartment_bp`` (ArcFISH ``min_cpmt_size``; default 0 as in the authors' tutorial); ``n_init`` /
    ``random_state`` of the k-means; ``a_cluster`` / ``a_track`` name the A compartment (else the authors' rule);
    ``k_sigma`` / ``frac`` of :func:`uchrom.fea.arc.filter_normalize`.  ``min_bins`` (deprecated) is the former
    minimum run in loci; given, it flips runs of fewer loci the same way.

    Before U-Chrom 0.3 (2026-10) missing variances were dropped from the kernel, the k-means ran 10 times, short
    runs were merged by bin count and **A was the more compact cluster** — the opposite of the authors' rule
    (``docs/source/reference/changelog.md``).
    """

    n_clusters: int = 2
    min_compartment_bp: float = 0.0
    min_bins: Optional[int] = None
    k_sigma: float = 4.0
    frac: float = 0.1
    random_state: int = 0
    n_init: int = 1
    a_cluster: Optional[int] = None
    a_track: Optional[str] = None


def _flip_small_runs(labels: np.ndarray, starts: np.ndarray, minimum: float, *, in_loci: bool = False) -> np.ndarray:
    """Flip the shortest run shorter than ``minimum`` until none is left (module docstring, step 4); the length of a
    run is ``start(last) - start(first)`` in bp, or its number of loci with ``in_loci``."""
    labels = np.asarray(labels).astype(int).copy()
    while True:
        cut = np.flatnonzero(np.r_[True, labels[1:] != labels[:-1]])
        last = np.r_[cut[1:], len(labels)] - 1
        lengths = (last - cut + 1) if in_loci else (starts[last] - starts[cut])
        if not np.any(lengths < minimum):
            return labels
        k = int(np.argmin(lengths))
        labels[cut[k]:last[k] + 1] = 1 - labels[cut[k]:last[k] + 1]


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
    centromeres=None,
    store=UNSET,
    result_key=UNSET,
):
    """Call A/B compartments with ArcFISH's axes-PC method (chromatin tracing; module docstring).

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
    centromeres : mapping or DataFrame, optional
        Centromere position per chromosome (``{chrom: bp}``, or a table with ``chrom`` and ``mid`` / ``pos``
        / ``start, end``; as :func:`uchrom.strc.comp.call_compartments_eig`): each arm is called on its own, as
        the authors' caller does with a reference genome — the normalised variances of the whole chromosome,
        the p arm the loci with ``end <= centromere``; with fewer than 2 loci on an arm the whole chromosome is
        called.  For whole
        chromosomes of reconstructed single-cell structures, whose two arms often lie apart, the second
        eigenvector of a metacentric chromosome otherwise separates the arms rather than the compartments
        (Tan et al. 2018 Dip-C GM12878 at 250 kb: per-chromosome r with the E1 of the same cells' contacts
        -0.36-0.21 on chr2, 3, 4, 5, 8, 10 whole, 0.31-0.78 per arm; uchrom-reproducibility/benchmarks/toolkit_parity/sc_structures).

    Returns
    -------
    DataFrame (``copy=False``) or ChromData (``copy=True``)
        One row per locus: ``chrom, start, end, bin_index, cluster, compartment, pc2, eig_x, eig_y, eig_z``
        (``bin_index`` counts within the chromosome; ``eig_*`` the per-axis eigenvectors, ``pc2`` their weighted
        sum oriented so that A > 0); with ``centromeres`` also ``region`` (``<chrom>_p`` / ``<chrom>_q``, or
        the chromosome).

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
    if centromeres is None:
        frames = [_call_compartments_chrom(work, c, params, device, verbose) for c in chroms]
    else:
        frames = [_call_compartments_chrom(work, c, params, device, verbose, centromeres=centromeres)
                  for c in chroms]
    table = merge_tables(frames, _empty_compartments())
    track = table[["chrom", "start", "end"]].assign(value=table["pc2"].to_numpy(dtype=float))
    inputs = selection_inputs(work, chroms, trace_ids, cells)
    if centromeres is not None:
        from .eig import _centromere_of

        inputs["centromeres"] = {c: _centromere_of(centromeres, c) for c in chroms
                                 if _centromere_of(centromeres, c) is not None}
    return store_and_return(
        cd, table, key_added=key_added, copy=copy, kind="table",
        function="uchrom.strc.comp.call_compartments_axes_pc", params=params,
        inputs=inputs,
        intervals=[(key_added, compartment_segments(table), "segment")] if key_added else (),
        bin_tracks={f"{key_added}.pc2": track} if key_added else None,
    )


def compartment_segments(table: pd.DataFrame, score: str = "pc2") -> pd.DataFrame:
    """Per-bin compartment calls → runs of equal label per chromosome.

    Columns ``chrom, start, end, label, n_bins`` and ``score`` (default
    ``pc2``: its mean over the run's bins).  Stored as the ``segment``
    interval table ``cd.intervals[key_added]``.
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
                score: float(g[score].mean()),
            })
    cols = ["chrom", "start", "end", "label", "n_bins", score]
    if not rows:
        return pd.DataFrame({"chrom": pd.Series(dtype=str), "start": pd.Series(dtype="int64"),
                             "end": pd.Series(dtype="int64"), "label": pd.Series(dtype=str),
                             "n_bins": pd.Series(dtype="int64"), score: pd.Series(dtype=float)})
    return pd.DataFrame(rows, columns=cols)


def _call_compartments_chrom(cd, chrom: str, params: CompartmentCallerParams, device: str, verbose: bool,
                             centromeres=None) -> pd.DataFrame:
    """Per-chromosome kernel of :func:`call_compartments_axes_pc` (both arms when a centromere is given)."""
    if verbose:
        print(f"[comp/{chrom}] variance cube + normalise...")
    cube = filter_normalize(axis_variance_cube(cd, chrom=chrom, device=device), k_sigma=params.k_sigma,
                            frac=params.frac)
    coords, bin_ids, _ = _coord_cube_for_chrom(cd, chrom)
    norm_var = np.where(np.isnan(cube["norm_var"]), 1.0, cube["norm_var"])
    starts = np.array([s for s, _ in bin_ids], dtype=np.int64)
    ends = np.array([e for _, e in bin_ids], dtype=np.int64)
    regions = [(chrom, np.arange(len(bin_ids)))]
    if centromeres is not None:
        from .eig import _centromere_of

        cen = _centromere_of(centromeres, chrom)
        if cen is not None:
            p, q = np.flatnonzero(ends <= cen), np.flatnonzero(ends > cen)
            if len(p) < 2 or len(q) < 2:
                warnings.warn(f"{chrom}: the centromere does not split the loci into two arms of at least 2 "
                              f"loci; calling the whole chromosome", stacklevel=3)
            else:
                regions = [(f"{chrom}_p", p), (f"{chrom}_q", q)]
    frames = []
    for name, idx in regions:
        t = _call_region(cd, chrom, params, norm_var[:, idx][:, :, idx], _axis_weight_cube(coords[:, idx]),
                         starts[idx], ends[idx], [bin_ids[i] for i in idx], verbose)
        t["bin_index"] = idx
        if centromeres is not None:
            t["region"] = name
        frames.append(t)
    return pd.concat(frames, ignore_index=True)


def _call_region(cd, chrom: str, params: CompartmentCallerParams, norm_var: np.ndarray, w: np.ndarray,
                 starts: np.ndarray, ends: np.ndarray, bin_ids, verbose: bool) -> pd.DataFrame:
    """Steps 2-5 of the module docstring on one chromosome or arm."""
    from scipy import stats
    from sklearn.cluster import KMeans

    if params.min_compartment_bp > np.ptp(starts):
        raise ValueError("Minimum compartment size larger than the region.")
    if verbose:
        print(f"[comp/{chrom}] axis weights: {np.round(w, 3)}")
    V = np.linalg.eigh(np.exp(-norm_var))[1][:, :, -2]                # (3, B)
    wtV = V * w[:, None]
    labels = KMeans(n_clusters=params.n_clusters, random_state=params.random_state,
                    n_init=params.n_init).fit_predict(wtV.T)
    if params.min_bins is not None:
        warnings.warn("CompartmentCallerParams.min_bins is deprecated; use min_compartment_bp (bp)",
                      DeprecationWarning, stacklevel=4)
        labels = _flip_small_runs(labels, starts, params.min_bins, in_loci=True)
    labels = _flip_small_runs(labels, starts, params.min_compartment_bp)

    if params.a_cluster is not None:
        a_cluster = int(params.a_cluster)
    elif params.a_track is not None:
        values = _bin_track_values(cd, chrom, bin_ids, params.a_track)
        uniq = np.unique(labels)
        means = [float(np.nanmean(values[labels == lab])) if np.isfinite(values[labels == lab]).any()
                 else -np.inf for lab in uniq]
        a_cluster = int(uniq[int(np.argmax(means))])
    else:
        med = []
        for lab in (0, 1):
            m = labels == lab
            block = norm_var[:, m][:, :, m].reshape(3, -1)
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", RuntimeWarning)
                med.append(np.nanmedian(block, axis=1))
        flip = int(stats.mode((med[0] < med[1]).astype("int64")).mode) == 1   # cluster 0 more compact → B
        a_cluster = 1 if flip else 0
    compartment = np.where(labels == a_cluster, "A", "B")

    # one signed track: the weighted eigenvectors aligned on the highest-weight axis, summed, A > 0
    ref = V[int(np.argmax(w))]
    aligned = np.stack([v if float(v @ ref) >= 0 else -v for v in V]) * w[:, None]
    track = aligned.sum(axis=0)
    is_a = labels == a_cluster
    if is_a.any() and (~is_a).any() and track[is_a].mean() < track[~is_a].mean():
        track = -track
    return pd.DataFrame({
        "chrom": chrom, "start": starts, "end": ends, "bin_index": np.arange(len(starts)),
        "cluster": labels.astype(int), "compartment": compartment.astype(str), "pc2": track,
        "eig_x": V[0], "eig_y": V[1], "eig_z": V[2],
    })


def _bin_track_values(cd, chrom: str, bin_ids, track: str) -> np.ndarray:
    """``cd.bin_tracks[track]`` at the loci ``bin_ids`` (``(start, end)``) of ``chrom`` (NaN if absent)."""
    if track not in cd.bin_tracks.columns:
        raise KeyError(f"a_track={track!r} is not a column of cd.bin_tracks ({list(cd.bin_tracks.columns)})")
    bins = cd.bins
    on = bins["chrom"].astype(str) == str(chrom)
    values = pd.Series(cd.bin_tracks.loc[bins.index[on], track].to_numpy(dtype=float),
                       index=pd.MultiIndex.from_arrays([bins.loc[on, "start"].astype(np.int64),
                                                        bins.loc[on, "end"].astype(np.int64)]))
    values = values[~values.index.duplicated()]
    want = pd.MultiIndex.from_tuples([(int(s), int(e)) for s, e in bin_ids])
    return values.reindex(want).to_numpy(dtype=float)


def _empty_compartments() -> pd.DataFrame:
    return pd.DataFrame({
        "chrom": pd.Series(dtype=str),
        "start": pd.Series(dtype="int64"),
        "end": pd.Series(dtype="int64"),
        "bin_index": pd.Series(dtype="int64"),
        "cluster": pd.Series(dtype="int64"),
        "compartment": pd.Series(dtype=str),
        "pc2": pd.Series(dtype="float64"),
        "eig_x": pd.Series(dtype="float64"), "eig_y": pd.Series(dtype="float64"),
        "eig_z": pd.Series(dtype="float64"),
    })


__all__ = [
    "call_compartments_axes_pc",
    "compartment_segments",
    "CompartmentCallerParams",
]
