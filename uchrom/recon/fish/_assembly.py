"""Stage 3 of GEM-FISH — assemble per-TAD intra models under the
TAD-level scaffold.

For each TAD i with intra-TAD coordinates ``y^{(i)}`` and a target
TAD-centre position ``s_i`` from Stage 1:

1. **Translate** each TAD so its centroid (mean of its bin coords)
   coincides with ``s_i``.
2. **Rotate / reflect** each TAD (except the first) to minimise the
   distance between its start point and the previous TAD's end point,
   penalised against the expected inter-TAD gap ``d_{i-1,i}``
   (computed from Hi-C contact counts via Eqn. 10).

Step 2 is solved independently per TAD: with the rigid-body transform
constrained to keep the centroid fixed at ``s_i``, the optimal
rotation/reflection that minimises ``||y^{(i)}_{start} − (y^{(i-1)}_{end}
+ d̂_{i-1,i})||²`` is a closed-form Kabsch problem on a **single vector
pair**, but since we also have the freedom to reflect and the objective
is a single squared distance, the simplest robust thing is to rotate
the TAD around its centroid so that the vector ``centroid → start``
points toward the desired target.  That's a two-atom Kabsch, done via
SVD of the outer product.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Tuple

import numpy as np


@dataclass
class AssemblyParams:
    """Parameters for the Stage-3 assembly step."""

    allow_reflection: bool = True
    """If True, accept reflections (negative-determinant rotations)
    when they reduce the boundary-gap objective."""

    endpoint_k: int = 1
    """Number of bins from each TAD end used as 'anchor' points when
    computing the Kabsch alignment.  ``1`` uses just the first / last
    bin; ``3`` uses the first/last 3 bins (robust to noise)."""


def _kabsch(
    P: np.ndarray, Q: np.ndarray, allow_reflection: bool = True,
) -> np.ndarray:
    """Optimal rotation R with ``min ||P R − Q||²``.

    Both ``P`` and ``Q`` are ``(k, 3)`` matrices of corresponding
    points, **already centred** (their centroids are at the origin).
    ``R`` is right-applied: new_coords = old_coords @ R.
    """
    H = P.T @ Q
    U, _, Vt = np.linalg.svd(H)
    d = np.sign(np.linalg.det(U @ Vt))
    D = np.eye(3)
    if not allow_reflection and d < 0:
        D[-1, -1] = d
    return U @ D @ Vt


def assemble(
    tad_centres: np.ndarray,
    intra_tad_coords: List[np.ndarray],
    inter_tad_distances: Optional[np.ndarray] = None,
    params: Optional[AssemblyParams] = None,
) -> np.ndarray:
    """Stitch intra-TAD conformations together into a single chain.

    Parameters
    ----------
    tad_centres : ndarray (n_tads, 3)
        Stage-1 TAD-centre coordinates.
    intra_tad_coords : list of ndarray (n_bins_i, 3)
        Stage-2 intra-TAD coordinate clouds (one per TAD).
    inter_tad_distances : ndarray (n_tads, n_tads), optional
        Pairwise expected distances used for Stage-3 alignment.  Only
        the immediate-neighbour entries ``d[i, i+1]`` are consulted in
        this simple implementation.  If omitted, we fall back to using
        the Stage-1 centre distances directly.
    params : AssemblyParams

    Returns
    -------
    coords : ndarray (sum n_bins_i, 3)
        Concatenated, rigid-body-aligned per-bin coordinates.  Order is
        TAD-0 bins first, then TAD-1, …
    """
    params = params or AssemblyParams()
    n_tads = tad_centres.shape[0]
    assert len(intra_tad_coords) == n_tads, (
        "intra_tad_coords length must match tad_centres length"
    )

    # Stage 3a: centre each intra-TAD cloud on its TAD centre
    placed = []
    for i, clump in enumerate(intra_tad_coords):
        cl = np.asarray(clump, dtype=np.float64)
        cl = cl - cl.mean(axis=0, keepdims=True) + tad_centres[i]
        placed.append(cl)

    # Stage 3b: rotate each TAD (i ≥ 1) so its start anchor is closest
    # to the previous TAD's end anchor + expected-gap heading
    k = max(1, int(params.endpoint_k))
    for i in range(1, n_tads):
        prev = placed[i - 1]
        curr = placed[i]
        if prev.shape[0] < k or curr.shape[0] < k:
            continue

        # Anchor points
        prev_end = prev[-k:].mean(axis=0)
        curr_start_now = curr[:k].mean(axis=0)

        # Expected heading vector from prev_end toward the curr centre
        heading = tad_centres[i] - prev_end
        hn = np.linalg.norm(heading)
        if hn < 1e-9:
            continue
        heading_unit = heading / hn

        # Decide the target location for the "start anchor" of the
        # current TAD: sit on the line from prev_end toward curr centre,
        # at a distance given by inter_tad_distances[i-1, i] if set.
        if inter_tad_distances is not None:
            target_gap = float(inter_tad_distances[i - 1, i])
        else:
            target_gap = hn  # fallback: use centre-to-centre distance
        target_start = prev_end + heading_unit * target_gap

        # Current anchor vector (centred on the TAD centre)
        v_curr = curr_start_now - tad_centres[i]
        v_target = target_start - tad_centres[i]

        # Kabsch on a single anchor pair (k=1 semantics preserved even
        # with k>1 because we collapse anchors to their mean).
        P = v_curr[np.newaxis, :]
        Q = v_target[np.newaxis, :]
        R = _kabsch(P, Q, allow_reflection=params.allow_reflection)

        # Apply rotation around the TAD centre
        placed[i] = (curr - tad_centres[i]) @ R + tad_centres[i]

    return np.vstack(placed)


def gap_distance_from_contacts(
    tad_contacts: np.ndarray,
    tad_genomic_distances: np.ndarray,
    alpha: float = 0.25,
    fallback_c: float = 1.0,
    fallback_beta: float = 0.5,
) -> np.ndarray:
    """Wrapper around :func:`uchrom.recon.fish._hic.contact_to_distance`
    producing the neighbour-gap matrix used by :func:`assemble`.
    """
    from ._hic import contact_to_distance

    return contact_to_distance(
        tad_contacts,
        genomic_distances=tad_genomic_distances,
        alpha=alpha,
        fallback_c=fallback_c,
        fallback_beta=fallback_beta,
    )


__all__ = ["AssemblyParams", "assemble", "gap_distance_from_contacts"]
