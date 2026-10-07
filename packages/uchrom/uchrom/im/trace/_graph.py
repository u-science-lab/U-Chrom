"""DAG construction and shortest-path fiber extraction for the jie
spatial genome aligner.

Nodes are detected FISH spots plus a virtual source (``SRC``) and sink
(``SNK``).  Edges connect spot *i* at locus *t* to spot *j* at locus
*t + c* for ``1 ≤ c ≤ max_skip``, with weight::

    w_ij = R²_ij / (2·S²_ij) + (c - 1) · gap_penalty

(the Mahalanobis cost under a Gaussian-chain bond, without the
``-1.5·log(2π·S²)`` normalisation constant — see
:func:`uchrom.im.trace._polymer.mahalanobis_cost` for rationale).
``S²_ij`` is the Gaussian-chain axis variance from
:func:`expected_distance_sq`.

The virtual source connects to every spot at locus ``< max_skip``
(with a leading gap penalty), and every spot at locus
``>= n_loci - max_skip`` connects to the sink.  A shortest *S → T*
path therefore picks at most one spot per locus, can skip loci to
handle dropout, and is forced to span the full locus range.

``iterative_karyotype`` repeats Dijkstra, masking used spots each time,
until either the path drops below ``min_spots_per_fiber`` useful loci
or ``max_fibers_per_chrom`` is reached.  Sister-chromatid pairs are
detected post-hoc via the mean nearest-neighbour distance between
fiber coordinate sets.
"""

from __future__ import annotations

from typing import List, Sequence, Tuple

import numpy as np
import scipy.sparse as sp
from scipy.sparse.csgraph import dijkstra

from ._polymer import (
    mahalanobis_cost,
    PERSISTENCE_LENGTH_BP_DEFAULT,
)


# scipy's sparse graph algorithms treat explicit zeros as "no edge", so
# every edge we insert gets a floor of _EDGE_EPS (~1e-12) added to its
# weight.  The offset is dominated by the actual logp / gap terms and
# has no practical effect on shortest-path results.
_EDGE_EPS = 1e-12


# ----------------------------------------------------------------------
# DAG construction
# ----------------------------------------------------------------------

def build_dag(
    spots_xyz: np.ndarray,
    spot_locus: np.ndarray,
    bin_bp: np.ndarray,
    sigma_per_spot: np.ndarray,
    l_p_bp: float,
    tau_nm_per_bp: float,
    max_skip: int,
    gap_penalty: float,
) -> Tuple[sp.csr_matrix, int, int]:
    """Build the weighted DAG for a single (cell, chromosome).

    Parameters
    ----------
    spots_xyz : ndarray (n_spots, 3)
        Spot coordinates in nm.
    spot_locus : ndarray (n_spots,)
        Integer locus index for each spot (0-based, into ``bin_bp``).
    bin_bp : ndarray (n_loci,)
        Genomic midpoint per locus, in bp.
    sigma_per_spot : ndarray (n_spots,) or (n_spots, 3)
        Per-spot axis-wise localisation σ (nm).  Scalar broadcasts.
    l_p_bp, tau_nm_per_bp : float
        Persistence length (bp) and genomic-to-spatial scale (nm/bp).
    max_skip : int
        Max allowed skipped loci per edge (C in the paper).
    gap_penalty : float
        Additive penalty per skipped locus, in natural-log units
        (``(c - 1) · gap_penalty`` added to each edge).  A skip of 0
        adds nothing; skip of 2 adds 2·gap_penalty.

    Returns
    -------
    W : csr_matrix (n_nodes, n_nodes)
        Non-negative edge weights (negative log probabilities plus gap
        penalty).  ``n_nodes = n_spots + 2`` with indices 0..n_spots-1
        for spots, ``n_spots`` = SRC, ``n_spots + 1`` = SNK.
    src : int
        Source node index.
    snk : int
        Sink node index.
    """
    spots_xyz = np.asarray(spots_xyz, dtype=np.float64)
    spot_locus = np.asarray(spot_locus, dtype=np.int64)
    bin_bp = np.asarray(bin_bp, dtype=np.float64)
    n_spots = spots_xyz.shape[0]
    n_loci = bin_bp.size

    # Normalise sigma to per-spot axis variance (scalar sum σ_i²)
    sig = np.asarray(sigma_per_spot, dtype=np.float64)
    if sig.ndim == 0:
        sig_sq = np.full(n_spots, sig ** 2, dtype=np.float64)
    elif sig.ndim == 1 and sig.shape == (n_spots,):
        sig_sq = sig ** 2
    elif sig.ndim == 2 and sig.shape == (n_spots, 3):
        # axis variance = mean of per-axis σ²; aligner treats S² isotropically
        sig_sq = np.mean(sig ** 2, axis=1)
    else:
        raise ValueError(
            f"sigma_per_spot shape {sig.shape} not understood"
        )

    src = n_spots
    snk = n_spots + 1
    n_nodes = n_spots + 2

    rows: List[int] = []
    cols: List[int] = []
    vals: List[float] = []

    # Group spots by locus for fast neighbour lookup
    locus_to_spots: List[np.ndarray] = [
        np.where(spot_locus == t)[0] for t in range(n_loci)
    ]

    # ----------------------------------------------------------------
    # Spot-to-spot edges
    # ----------------------------------------------------------------
    for t in range(n_loci):
        src_spots = locus_to_spots[t]
        if src_spots.size == 0:
            continue
        for c in range(1, max_skip + 1):
            u = t + c
            if u >= n_loci:
                break
            dst_spots = locus_to_spots[u]
            if dst_spots.size == 0:
                continue
            L_bp = float(bin_bp[u] - bin_bp[t])
            if L_bp <= 0:
                continue
            # Axis variance for every (i, j) pair at this (t, u) step.
            # sig_i² + sig_j² + chain term.  chain term is scalar here.
            chain_term = (2.0 / 3.0) * l_p_bp * tau_nm_per_bp * L_bp
            gap_add = (c - 1) * gap_penalty
            pi = spots_xyz[src_spots]
            pj = spots_xyz[dst_spots]
            diff = pi[:, None, :] - pj[None, :, :]
            R = np.sqrt(np.sum(diff ** 2, axis=-1))
            sig_sum = sig_sq[src_spots][:, None] + sig_sq[dst_spots][None, :]
            S2 = chain_term + sig_sum
            # Use the bias-free Mahalanobis cost R²/2S² rather than the
            # full -log p; see :func:`mahalanobis_cost` for rationale.
            w = mahalanobis_cost(R, S2) + gap_add
            # Guard against non-finite weights (shouldn't happen for S2>0)
            w = np.where(np.isfinite(w), w, 1e18)
            # Flatten into COO triples
            for a_idx, si in enumerate(src_spots):
                for b_idx, sj in enumerate(dst_spots):
                    rows.append(int(si))
                    cols.append(int(sj))
                    vals.append(float(w[a_idx, b_idx]) + _EDGE_EPS)

    # ----------------------------------------------------------------
    # Source edges: SRC -> spot at locus t, with leading gap penalty
    # (treat SRC as being at virtual locus -1, so skip c = t + 1)
    # Only connect to loci within max_skip (otherwise no path).
    # ----------------------------------------------------------------
    for t in range(min(max_skip, n_loci)):
        for si in locus_to_spots[t]:
            rows.append(src)
            cols.append(int(si))
            # leading gap = t (number of loci skipped before this)
            vals.append(float(t * gap_penalty) + _EDGE_EPS)

    # ----------------------------------------------------------------
    # Sink edges: spot at locus t -> SNK, with trailing gap penalty
    # (treat SNK as being at virtual locus n_loci, so skip c = n_loci - t)
    # ----------------------------------------------------------------
    for t in range(max(0, n_loci - max_skip), n_loci):
        trailing = n_loci - 1 - t
        for si in locus_to_spots[t]:
            rows.append(int(si))
            cols.append(snk)
            vals.append(float(trailing * gap_penalty) + _EDGE_EPS)

    if not rows:
        # Degenerate: no edges.  Return an empty graph.
        W = sp.csr_matrix((n_nodes, n_nodes), dtype=np.float64)
    else:
        W = sp.coo_matrix(
            (vals, (rows, cols)), shape=(n_nodes, n_nodes),
        ).tocsr()

    return W, src, snk


# ----------------------------------------------------------------------
# Shortest-path decoding
# ----------------------------------------------------------------------

def shortest_fiber_path(
    W: sp.csr_matrix, src: int, snk: int,
) -> Tuple[List[int], float]:
    """Dijkstra from *src* to *snk*; return the spot nodes along the
    path and the total path weight.

    Returns an empty list and ``inf`` if no path exists.
    """
    dist, predecessors = dijkstra(
        csgraph=W, directed=True, indices=src,
        return_predecessors=True,
    )
    if not np.isfinite(dist[snk]):
        return [], float("inf")
    # Rebuild path by following predecessors from snk backwards.
    path = []
    node = snk
    while node != src and node >= 0:
        if node != snk:
            path.append(int(node))
        prev = int(predecessors[node])
        if prev < 0:
            break
        node = prev
    path.reverse()
    return path, float(dist[snk])


# ----------------------------------------------------------------------
# Iterative fiber extraction
# ----------------------------------------------------------------------

def iterative_karyotype(
    spots_xyz: np.ndarray,
    spot_locus: np.ndarray,
    bin_bp: np.ndarray,
    sigma_per_spot: np.ndarray,
    l_p_bp: float = PERSISTENCE_LENGTH_BP_DEFAULT,
    tau_nm_per_bp: float = 0.01,
    max_skip: int = 3,
    gap_penalty: float = 2.0,
    max_fibers: int = 8,
    min_spots_per_fiber: int = 5,
    mean_edge_weight_cutoff: float = np.inf,
) -> List[dict]:
    """Iteratively extract fibers: Dijkstra → mask used spots → repeat.

    Each call rebuilds the DAG on the remaining spots.  Rebuilding is
    O(E) but E is small after masking, so this is pragmatic.

    Parameters
    ----------
    spots_xyz, spot_locus, bin_bp, sigma_per_spot : see :func:`build_dag`
    l_p_bp, tau_nm_per_bp, max_skip, gap_penalty : see :func:`build_dag`
    max_fibers : int
        Safety cap on the number of extracted fibers per chromosome.
    min_spots_per_fiber : int
        Reject candidate fibers with fewer than this many *actual* spots.
    mean_edge_weight_cutoff : float
        Reject candidate fibers whose mean per-edge weight exceeds this
        value (coarse null model).  Default inf disables the check.

    Returns
    -------
    List of dicts, one per accepted fiber:
        ``{'spots': [idx], 'path_weight': float, 'mean_edge': float}``.
    """
    spots_xyz = np.asarray(spots_xyz, dtype=np.float64)
    n_spots = spots_xyz.shape[0]
    if n_spots == 0:
        return []

    used = np.zeros(n_spots, dtype=bool)
    fibers: List[dict] = []

    for _ in range(max_fibers):
        remaining = np.where(~used)[0]
        if remaining.size < min_spots_per_fiber:
            break
        W, src, snk = build_dag(
            spots_xyz[remaining],
            spot_locus[remaining],
            bin_bp,
            sigma_per_spot[remaining] if sigma_per_spot.ndim >= 1
                else sigma_per_spot,
            l_p_bp=l_p_bp,
            tau_nm_per_bp=tau_nm_per_bp,
            max_skip=max_skip,
            gap_penalty=gap_penalty,
        )
        local_path, total = shortest_fiber_path(W, src, snk)
        if not local_path:
            break
        # Map back from local indices (0..remaining.size-1) to the
        # global spot indices.
        global_path = [int(remaining[i]) for i in local_path]
        n_edges = len(global_path) + 1  # +2 virtual edges - 1
        mean_edge = total / max(n_edges, 1)
        if (
            len(global_path) < min_spots_per_fiber
            or mean_edge > mean_edge_weight_cutoff
        ):
            # This path is poor-quality; stop extracting rather than
            # masking it (we may otherwise mask good spots with a bad
            # partial path).
            break
        used[global_path] = True
        fibers.append({
            "spots": global_path,
            "path_weight": float(total),
            "mean_edge": float(mean_edge),
        })

    return fibers


# ----------------------------------------------------------------------
# Sister-chromatid detection
# ----------------------------------------------------------------------

def detect_sister_pairs(
    fibers: Sequence[dict],
    spots_xyz: np.ndarray,
    spot_locus: np.ndarray,
    pair_radius_nm: float = 300.0,
) -> List[int]:
    """Post-hoc sister-chromatid grouping.

    For each pair of fibers, compute the mean of the **per-locus
    distance** between the spots that they picked from the same locus
    (both fibers must agree on the locus, otherwise that locus is
    skipped).  If the mean is below ``pair_radius_nm``, the two fibers
    are grouped as sisters.

    Returns a list of group IDs, one per fiber, with fibers sharing a
    group ID being sisters.  Solo fibers each get their own group.
    """
    n = len(fibers)
    if n == 0:
        return []

    # Pairwise mean co-locus distance
    co_dist = np.full((n, n), np.inf, dtype=np.float64)
    for i in range(n):
        loci_i = {int(spot_locus[s]): s for s in fibers[i]["spots"]}
        for j in range(i + 1, n):
            loci_j = {int(spot_locus[s]): s for s in fibers[j]["spots"]}
            shared = sorted(set(loci_i) & set(loci_j))
            if not shared:
                continue
            d = []
            for L in shared:
                a = spots_xyz[loci_i[L]]
                b = spots_xyz[loci_j[L]]
                d.append(float(np.linalg.norm(a - b)))
            co_dist[i, j] = co_dist[j, i] = float(np.mean(d))

    # Union-find grouping
    parent = list(range(n))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(x, y):
        rx, ry = find(x), find(y)
        if rx != ry:
            parent[rx] = ry

    for i in range(n):
        for j in range(i + 1, n):
            if co_dist[i, j] < pair_radius_nm:
                union(i, j)

    # Renumber so groups are 0, 1, 2, ...
    roots = {}
    out = []
    for i in range(n):
        r = find(i)
        if r not in roots:
            roots[r] = len(roots)
        out.append(roots[r])
    return out


__all__ = [
    "build_dag",
    "shortest_fiber_path",
    "iterative_karyotype",
    "detect_sister_pairs",
]
