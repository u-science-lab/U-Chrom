"""FISHnet — per-allele chromatin-domain caller via modularity maximisation.

Independent reimplementation of Patel et al. 2025
(*FISHnet: detecting chromatin domains in single-cell sequential
Oligopaints imaging data*, Nature Methods 22:1255–1264,
doi:10.1038/s41592-025-02688-1).  Not derived from the upstream
repository (``github.com/RohanpatelUpenn/FISHnet``), which ships without
an open-source licence.

Overview
--------
FISHnet is a **per-trace** domain caller — for each allele's pairwise
distance matrix it sweeps a range of distance thresholds, binarises at
each threshold, smooths, and runs Louvain modularity maximisation on the
resulting weighted graph.  Thresholds at which the community count is
stable across ``plateau_size`` or more adjacent steps are grouped, and
the consensus partition within each plateau is taken as the final
domain call for that allele.

This complements the other callers in :mod:`uchrom.strc.tad`:

- :func:`get_domains` — classical Dixon directionality index on a
  population contact matrix.
- :func:`call_tads_by_pval` — axis-wise F-test on per-bin variance.
- :func:`call_domains_fishnet_trace` — FISHnet on a single allele.
- :func:`call_domains_fishnet` — FISHnet applied across all alleles of a
  chromosome, with an ensemble "domain-mask" aggregation.

References
----------
Patel, R., Pham, K., Chandrashekar, H., Phillips-Cremins, J. E. (2025).
FISHnet: detecting chromatin domains in single-cell sequential
Oligopaints imaging data.  *Nature Methods* 22, 1255–1264.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Tuple

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


@dataclass
class FISHnetParams:
    """Runtime parameters for :func:`call_domains_fishnet_trace`.

    Defaults follow Patel et al. 2025.
    """

    thresholds: Optional[np.ndarray] = None   # in data's distance units
    threshold_step: Optional[float] = None    # if None, use linspace
    threshold_min: Optional[float] = None
    threshold_max: Optional[float] = None
    plateau_size: int = 4
    window_size: int = 2                      # (2*w)×(2*w) boxcar
    size_exclusion: int = 3                   # drop runs < N bins
    merge_tol: int = 3                        # merge boundaries within N bins
    n_louvain_runs: int = 20
    resolution: float = 1.0
    min_coverage: float = 0.6                 # require ≥N% non-NaN bins
    max_thresholds: int = 200                 # safety cap
    impute: bool = True                       # linear interpolate missing bins


# ----------------------------------------------------------------------
# Low-level helpers
# ----------------------------------------------------------------------

def _linear_impute(dist: np.ndarray) -> np.ndarray:
    """1-D linear interpolation of missing rows/columns of a distance
    matrix.  Works on the symmetric diagonal strip: for each bin ``i``
    with no finite distance to any other bin, fill its row/column with a
    linear blend of the nearest finite bins on each side.
    """
    d = dist.copy()
    n = d.shape[0]
    present = np.any(np.isfinite(d), axis=1)
    if present.all() or not present.any():
        return d
    present_idx = np.where(present)[0]
    missing_idx = np.where(~present)[0]
    for m in missing_idx:
        left = present_idx[present_idx < m]
        right = present_idx[present_idx > m]
        if left.size and right.size:
            a = left[-1]
            b = right[0]
            w = (m - a) / (b - a)
            d[m] = (1 - w) * d[a] + w * d[b]
            d[:, m] = d[m]
        elif left.size:
            a = left[-1]
            d[m] = d[a]
            d[:, m] = d[a]
        elif right.size:
            b = right[0]
            d[m] = d[b]
            d[:, m] = d[b]
    np.fill_diagonal(d, 0.0)
    return d


def _boxcar_nanmean(mat: np.ndarray, window: int) -> np.ndarray:
    """(2*w)×(2*w) NaN-aware boxcar mean.  Edge cells use the clipped
    window so the output is the same shape as the input.
    """
    if window <= 0:
        return mat.astype(np.float64, copy=True)
    n = mat.shape[0]
    out = np.zeros_like(mat, dtype=np.float64)
    for i in range(n):
        lf, uf = max(0, i - window), min(n, i + window)
        for j in range(n):
            ls, us = max(0, j - window), min(n, j + window)
            block = mat[lf:uf, ls:us]
            with np.errstate(invalid="ignore"):
                out[i, j] = np.nan if block.size == 0 else np.nanmean(block)
    return np.nan_to_num(out, nan=0.0)


def _louvain_labels(
    A: np.ndarray,
    resolution: float,
    seed: Optional[int],
) -> np.ndarray:
    """Run one Louvain pass and return an integer label per node.

    Edges with non-positive weight are dropped so the resulting graph is
    a weighted undirected network suitable for
    :func:`networkx.algorithms.community.louvain_communities`.
    """
    import networkx as nx
    from networkx.algorithms.community import louvain_communities

    n = A.shape[0]
    G = nx.Graph()
    G.add_nodes_from(range(n))
    iu, ju = np.triu_indices(n, k=1)
    w = A[iu, ju]
    mask = w > 0
    edges = list(zip(iu[mask].tolist(), ju[mask].tolist(), w[mask].tolist()))
    G.add_weighted_edges_from(edges)

    if G.number_of_edges() == 0:
        return np.arange(n, dtype=np.int64)

    communities = louvain_communities(
        G, weight="weight", resolution=resolution, seed=seed
    )
    labels = np.full(n, -1, dtype=np.int64)
    for k, comm in enumerate(communities):
        for node in comm:
            labels[node] = k
    # Un-assigned isolates → unique singleton labels
    next_k = int(labels.max()) + 1 if labels.max() >= 0 else 0
    for i in np.where(labels < 0)[0]:
        labels[i] = next_k
        next_k += 1
    return labels


def _count_switches(labels: np.ndarray) -> int:
    """Number of runs in the 1-D label sequence (= 1 + label-flip count)."""
    if len(labels) == 0:
        return 0
    return 1 + int(np.sum(labels[1:] != labels[:-1]))


def _consensus_partition(partitions: np.ndarray) -> np.ndarray:
    """Pick the partition with maximal mean adjusted-RAND similarity to
    all others.  ``partitions`` has shape (n_runs, n_bins).
    """
    from sklearn.metrics import adjusted_rand_score

    n_runs = partitions.shape[0]
    if n_runs == 1:
        return partitions[0]
    sim = np.zeros((n_runs, n_runs), dtype=np.float64)
    for i in range(n_runs):
        for j in range(i, n_runs):
            s = adjusted_rand_score(partitions[i], partitions[j])
            sim[i, j] = sim[j, i] = s
    idx = int(np.argmax(sim.mean(axis=0)))
    return partitions[idx]


def _find_plateaus(
    thresholds: np.ndarray, counts: np.ndarray, min_length: int,
) -> List[np.ndarray]:
    """Return a list of threshold-arrays, one per plateau of
    ``>= min_length`` consecutive equal community counts.
    """
    if min_length <= 0 or len(counts) == 0:
        return [thresholds] if len(thresholds) else []
    plateaus: List[np.ndarray] = []
    i = 0
    n = len(counts)
    while i < n:
        j = i
        while j + 1 < n and counts[j + 1] == counts[i]:
            j += 1
        run_len = j - i + 1
        if run_len >= min_length and not np.isnan(counts[i]):
            plateaus.append(thresholds[i:j + 1])
        i = j + 1
    return plateaus


def _size_exclude(labels: np.ndarray, min_size: int) -> np.ndarray:
    """Merge runs shorter than ``min_size`` into the larger neighbour."""
    out = labels.astype(np.int64).copy()
    n = out.size
    if min_size <= 1:
        return out
    changed = True
    while changed:
        changed = False
        i = 0
        while i < n:
            j = i
            while j + 1 < n and out[j + 1] == out[i]:
                j += 1
            run_len = j - i + 1
            if run_len < min_size:
                left = out[i - 1] if i > 0 else None
                right = out[j + 1] if j + 1 < n else None
                if left is None and right is None:
                    break
                if left is None:
                    pick = right
                elif right is None:
                    pick = left
                else:
                    # Merge toward the larger neighbouring run
                    l_len = 0
                    k = i - 1
                    while k >= 0 and out[k] == left:
                        l_len += 1
                        k -= 1
                    r_len = 0
                    k = j + 1
                    while k < n and out[k] == right:
                        r_len += 1
                        k += 1
                    pick = left if l_len >= r_len else right
                out[i:j + 1] = pick
                changed = True
                break
            i = j + 1
    return out


def _boundaries_from_labels(labels: np.ndarray) -> List[int]:
    """Indices where the label changes (exclusive end of the left run)."""
    if len(labels) == 0:
        return []
    return [int(i) for i in np.where(labels[1:] != labels[:-1])[0] + 1]


def _merge_close_boundaries(
    all_boundaries: List[List[int]], tol: int, n_bins: int,
) -> List[List[int]]:
    """Group boundary positions across plateaus that fall within ``tol``
    bins, replacing each group by its integer mean so every plateau
    shares canonical boundary coordinates.
    """
    flat = sorted({b for lst in all_boundaries for b in lst if 0 < b < n_bins})
    if not flat:
        return [list(lst) for lst in all_boundaries]
    groups: List[List[int]] = [[flat[0]]]
    for v in flat[1:]:
        if v - groups[-1][-1] <= tol:
            groups[-1].append(v)
        else:
            groups.append([v])
    # Map each raw boundary to its group's canonical value
    lookup = {}
    for g in groups:
        canon = int(round(float(np.mean(g))))
        for v in g:
            lookup[v] = canon

    merged = []
    for lst in all_boundaries:
        remapped = sorted({lookup.get(v, v) for v in lst if 0 < v < n_bins})
        merged.append(remapped)
    return merged


def _domains_from_boundaries(
    boundaries: List[int], n_bins: int,
) -> List[Tuple[int, int]]:
    """``boundaries`` are bin indices where a new domain starts.  Returns
    ``[(start, end_exclusive), ...]`` covering ``[0, n_bins)``.
    """
    pts = [0] + sorted(set(boundaries)) + [n_bins]
    out = []
    for a, b in zip(pts[:-1], pts[1:]):
        if b - a >= 1:
            out.append((a, b))
    return out


# ----------------------------------------------------------------------
# Per-trace FISHnet
# ----------------------------------------------------------------------

def call_domains_fishnet_trace(
    dist: np.ndarray,
    params: Optional[FISHnetParams] = None,
    seed_base: int = 0,
) -> dict:
    """Run FISHnet on a single-allele pairwise distance matrix.

    Parameters
    ----------
    dist : ndarray (n_bins, n_bins)
        Symmetric pairwise distance matrix, NaN for missing spots, in nm.
    params : FISHnetParams, optional
        Hyperparameters.  Use defaults if ``None``.
    seed_base : int
        Base seed for the 20 Louvain runs (reproducibility).

    Returns
    -------
    dict with keys
        ``domains`` : list of (start, end_exclusive) bin indices per plateau
        ``boundaries`` : sorted list of canonical boundary bin indices
        ``domain_mask`` : (n_bins, n_bins) int — count of plateaus in which
            bins i and j fall in the same domain (0 if never).
        ``n_plateaus`` : number of plateaus detected
        ``coverage`` : fraction of bins with ≥1 non-NaN distance
    """
    params = params or FISHnetParams()
    dist = np.asarray(dist, dtype=np.float64)
    n_bins = dist.shape[0]
    empty = {
        "domains": [],
        "boundaries": [],
        "domain_mask": np.zeros((n_bins, n_bins), dtype=np.int64),
        "n_plateaus": 0,
        "coverage": 0.0,
    }

    # Coverage check (a bin counts as present if any pairwise distance to
    # another bin is finite — i.e. the bin's 3D coordinate was detected)
    any_non_nan = np.any(np.isfinite(dist), axis=1)
    coverage = float(any_non_nan.mean())
    if coverage < params.min_coverage:
        empty["coverage"] = coverage
        return empty

    if params.impute and coverage < 1.0:
        dist = _linear_impute(dist)

    # Threshold sweep
    if params.thresholds is not None:
        thresholds = np.asarray(params.thresholds, dtype=np.float64)
    else:
        vmin = params.threshold_min
        vmax = params.threshold_max
        if vmin is None:
            pos = dist[np.isfinite(dist) & (dist > 0)]
            vmin = float(np.min(pos)) if pos.size else 0.0
        if vmax is None:
            vmax = float(np.nanmax(dist))
        if not np.isfinite(vmin) or not np.isfinite(vmax) or vmax <= vmin:
            return {**empty, "coverage": coverage}
        if params.threshold_step is not None:
            thresholds = np.arange(vmin, vmax + 1e-9, params.threshold_step)
        else:
            thresholds = np.linspace(vmin, vmax, params.max_thresholds)
        if len(thresholds) > params.max_thresholds:
            thresholds = np.linspace(vmin, vmax, params.max_thresholds)

    # Per-threshold: run Louvain 20× and cache both the partitions and the
    # stable-community-count statistic — phase 2 re-uses the same partitions.
    n_runs = params.n_louvain_runs
    partitions = np.full(
        (len(thresholds), n_runs, n_bins), -1, dtype=np.int64,
    )
    counts = np.full(len(thresholds), np.nan, dtype=np.float64)
    for ti, thr in enumerate(thresholds):
        B = (dist < thr).astype(np.float64)
        B[~np.isfinite(dist)] = 0.0
        A = _boxcar_nanmean(B, params.window_size)

        run_counts = []
        for r in range(n_runs):
            labels = _louvain_labels(
                A, params.resolution, seed=seed_base + ti * 1000 + r,
            )
            partitions[ti, r] = labels
            k = int(len(np.unique(labels)))
            # Reject spurious 2-community partitions with many interleaved
            # flips — per the FISHnet paper, genuine domain partitions
            # should produce contiguous runs in the 1-D bin order.
            if k == 2 and _count_switches(labels) > 2:
                continue
            run_counts.append(k)
        if run_counts:
            counts[ti] = round(float(np.mean(run_counts)))

    plateaus = _find_plateaus(thresholds, counts, params.plateau_size)
    if not plateaus:
        return {**empty, "coverage": coverage}

    # Per-plateau consensus partition — reuse cached partitions per threshold.
    t_to_idx = {float(t): i for i, t in enumerate(thresholds)}
    all_boundaries: List[List[int]] = []
    all_labels: List[np.ndarray] = []
    for plat_thresholds in plateaus:
        parts = np.zeros((len(plat_thresholds), n_bins), dtype=np.int64)
        for ki, thr in enumerate(plat_thresholds):
            ti = t_to_idx[float(thr)]
            parts[ki] = _consensus_partition(partitions[ti])
        consensus = _consensus_partition(parts)
        consensus = _size_exclude(consensus, params.size_exclusion)
        all_labels.append(consensus)
        all_boundaries.append(_boundaries_from_labels(consensus))

    all_boundaries = _merge_close_boundaries(
        all_boundaries, params.merge_tol, n_bins,
    )

    # Ensemble domain mask: for each plateau, bins i,j → 1 if same domain
    mask = np.zeros((n_bins, n_bins), dtype=np.int64)
    for labels in all_labels:
        same = labels[:, None] == labels[None, :]
        mask += same.astype(np.int64)

    boundaries_union = sorted({b for bl in all_boundaries for b in bl})
    domains = _domains_from_boundaries(boundaries_union, n_bins)

    return {
        "domains": domains,
        "boundaries": boundaries_union,
        "domain_mask": mask,
        "n_plateaus": len(plateaus),
        "coverage": coverage,
    }


# ----------------------------------------------------------------------
# ChromData-level wrapper
# ----------------------------------------------------------------------

def call_domains_fishnet(
    cd,
    *args,
    chrom=None,
    trace_ids=None,
    cells=None,
    params: Optional[FISHnetParams] = None,
    key_added: Optional[str] = UNSET,
    ensemble_key: Optional[str] = UNSET,
    copy: bool = False,
    verbose: bool = False,
    max_traces: Optional[int] = None,
    store=UNSET,
    result_key=UNSET,
):
    """Run FISHnet on every trace of the selected chromosome(s).

    Parameters
    ----------
    cd : ChromData
    chrom : str, sequence of str, or None
        ``None`` (default) runs every chromosome and merges the tables.
    trace_ids, cells : sequence, optional
        Restrict to these traces / cells.
    params : FISHnetParams, optional
    key_added : str or None
        ``cd.results`` key of the per-trace domain table (default
        ``"tads.fishnet"``); ``None`` does not store.
    ensemble_key : str, optional
        ``cd.results`` key of the ensemble domain mask (default
        ``f"{key_added}.ensemble"``).  Stored as a mapping
        ``{chrom: {"mask": (n_bins, n_bins) int64, "bin_ids": (n_bins, 2)
        int64 [start, end], "n_traces": int}}``.
    copy : bool
        ``True`` → return a new ChromData holding the results.
    max_traces : int, optional
        Cap on the number of traces processed **per chromosome** (useful
        for previews — FISHnet is O(n_bins² · n_thresholds) per trace).

    Returns
    -------
    DataFrame (``copy=False``) or ChromData (``copy=True``)
        One row per (trace, domain): ``chrom, trace_id, domain_idx, start,
        end, start_bin, end_bin``.

    Notes
    -----
    Deprecated 1.x forms (positional ``chrom``, ``store=``,
    ``result_key=``) still work with a ``DeprecationWarning``; they keep
    the 1.x keys ``"fishnet_domains"`` / ``"fishnet_ensemble"`` and the
    1.x single-chromosome ensemble layout ``{"chrom", "mask", "bin_ids",
    "n_traces"}``.
    """
    chrom, key_added, legacy = parse_legacy_call(
        "call_domains_fishnet", args, chrom=chrom, key_added=key_added,
        store=store, result_key=result_key, default_key="tads.fishnet",
        legacy_key="fishnet_domains", copy=copy,
    )
    if ensemble_key is UNSET:
        if key_added is None:
            ensemble_key = None
        elif legacy:
            ensemble_key = "fishnet_ensemble"
        else:
            ensemble_key = f"{key_added}.ensemble"
    params = params or FISHnetParams()
    work = select_spots(cd, trace_ids=trace_ids, cells=cells)
    chroms = resolve_chroms(work, chrom)

    frames, ensembles = [], {}
    for c in chroms:
        table, ens = _call_domains_fishnet_chrom(work, c, params, verbose, max_traces)
        frames.append(table)
        ensembles[c] = ens
    table = merge_tables(frames, _empty_fishnet())

    extra = []
    if ensemble_key is not None:
        if legacy and len(chroms) == 1:
            ens = ensembles[chroms[0]]
            ensemble = {"chrom": chroms[0], "mask": ens["mask"],
                        "bin_ids": [tuple(b) for b in ens["bin_ids"].tolist()],
                        "n_traces": ens["n_traces"]}
        else:
            ensemble = ensembles
        extra.append((ensemble_key, ensemble, "mapping"))
    inputs = selection_inputs(work, chroms, trace_ids, cells)
    if max_traces is not None:
        inputs["max_traces"] = int(max_traces)
    return store_and_return(
        cd, table, key_added=key_added, copy=copy, kind="intervals", interval_kind="domain",
        function="uchrom.strc.tad.call_domains_fishnet", params=params,
        inputs=inputs, extra=extra,
    )


def _call_domains_fishnet_chrom(cd, chrom: str, params: FISHnetParams,
                                verbose: bool, max_traces: Optional[int]):
    """Per-chromosome kernel: ``(domain table, ensemble dict)``."""
    from uchrom.fea.distance import _bin_coord_cube, _pairwise_distance_per_trace

    df = cd.to_dataframe()
    cube, bin_ids, trace_ids = _bin_coord_cube(df, chrom=chrom)
    dists = _pairwise_distance_per_trace(cube)  # (n_traces, n_bins, n_bins)
    n_traces, n_bins, _ = dists.shape

    if max_traces is not None:
        n_traces = min(n_traces, max_traces)

    if verbose:
        print(f"[fishnet/{chrom}] running on {n_traces} traces × "
              f"{n_bins} bins; plateau_size={params.plateau_size}, "
              f"window={params.window_size}")

    rows = []
    ensemble_mask = np.zeros((n_bins, n_bins), dtype=np.int64)
    skipped = 0
    for ti in range(n_traces):
        res = call_domains_fishnet_trace(
            dists[ti], params=params, seed_base=ti,
        )
        ensemble_mask += res["domain_mask"]
        if not res["domains"]:
            skipped += 1
            continue
        for di, (a, b) in enumerate(res["domains"]):
            s_bp = int(bin_ids[a][0])
            e_bp = int(bin_ids[b - 1][1])
            rows.append({
                "chrom": chrom,
                "trace_id": trace_ids[ti],
                "domain_idx": di,
                "start": s_bp,
                "end": e_bp,
                "start_bin": int(a),
                "end_bin": int(b),
            })
        if verbose and (ti + 1) % 25 == 0:
            print(f"[fishnet/{chrom}] {ti + 1}/{n_traces} traces")

    out = pd.DataFrame(rows, columns=list(_FISHNET_COLUMNS))
    if verbose:
        print(f"[fishnet/{chrom}] called domains in "
              f"{n_traces - skipped}/{n_traces} traces; "
              f"{len(out)} domains total")
    ensemble = {
        "mask": ensemble_mask,
        "bin_ids": np.asarray(bin_ids, dtype=np.int64).reshape(-1, 2),
        "n_traces": int(n_traces),
    }
    return out, ensemble


_FISHNET_COLUMNS = ("chrom", "trace_id", "domain_idx", "start", "end", "start_bin", "end_bin")


def _empty_fishnet() -> pd.DataFrame:
    return pd.DataFrame(columns=list(_FISHNET_COLUMNS))


__all__ = [
    "FISHnetParams",
    "call_domains_fishnet_trace",
    "call_domains_fishnet",
]
