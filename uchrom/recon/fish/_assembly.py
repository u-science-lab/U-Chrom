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

    match_scales: bool = True
    """If True, uniformly rescale the Stage-1 TAD-centre layout so the
    mean inter-TAD gap matches the intra-TAD Rg scale (roughly tangent
    packing of TADs).  Without this, Stage 1 and Stage 2 end up on
    incompatible scales: Stage-1 centres drift apart under minimal
    polymer constraint while each Stage-2 intra-TAD cloud optimises
    to unit bond length, giving tight blobs with huge bridges between
    them.  The intra-TAD geometry (which Stage 2 optimised against
    real Hi-C) is preserved; only the global layout is rescaled."""

    centre_gap_factor: float = 2.0
    """When ``match_scales=True``, the TAD centres are rescaled so
    that ``mean_inter_TAD_gap = centre_gap_factor * mean_intra_TAD_Rg``.
    ``2.0`` corresponds to roughly-tangent TAD packing; ``1.5`` gives
    slight overlap between neighbours; ``3.0`` gives visible spacing."""

    iterative: bool = True
    """If True, after the single-shot Kabsch rotation run the upstream
    GEM-FISH iterative gradient descent (Abbas 2019 Eqn. 13): for each
    adjacent-TAD pair, rotate TAD i+1 around its centre so the gap
    between ``y_end[i]`` and ``y_start[i+1]`` converges toward
    ``d_prior[i, i+1]``.  Repeats with reflection retry for TADs whose
    boundary gap has > ``reflect_threshold`` relative error."""

    inner_max_iter: int = 5000
    """Max gradient-descent iterations per inner assembly pass."""

    outer_max_iter: int = 5
    """Max outer passes (each can reflect bad TADs and re-run inner)."""

    alpha: float = 0.1
    """Gradient-descent learning rate for the iterative assembly."""

    reflect_threshold: float = 0.2
    """TADs whose adjacent-boundary relative error exceeds this
    threshold are reflected through their centre before the next outer
    pass (matches the upstream reflection-retry strategy)."""

    convergence_abs: float = 0.1
    """Convergence: stop inner loop when ``Σ|d_prior - df| < convergence_abs``."""


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

    # Harmonise Stage-1 (TAD-centre) and Stage-2 (intra-TAD) scales.
    # The intra-TAD geometry carries the information that Stage 2
    # optimised against real Hi-C, so we leave the clouds intact and
    # rescale the TAD-centre layout instead.  Target: mean inter-TAD
    # gap ≈ ``centre_gap_factor * mean intra-TAD Rg`` (tangent-packed
    # TAD spheres for factor=2).
    if params.match_scales and n_tads >= 2:
        intra_rgs = []
        for clump in intra_tad_coords:
            cl = np.asarray(clump)
            if cl.shape[0] >= 2:
                centroid = cl.mean(axis=0)
                rg = float(np.sqrt(((cl - centroid) ** 2).sum(axis=1).mean()))
                intra_rgs.append(rg)
        if intra_rgs:
            mean_rg = float(np.mean(intra_rgs))
            gaps = np.linalg.norm(
                tad_centres[1:] - tad_centres[:-1], axis=1,
            )
            mean_gap = float(np.mean(gaps))
            if mean_gap > 1e-9:
                target_gap = params.centre_gap_factor * mean_rg
                tad_centres = tad_centres * (target_gap / mean_gap)
                if inter_tad_distances is not None:
                    inter_tad_distances = (
                        inter_tad_distances * (target_gap / mean_gap)
                    )

    # Stage 3a: centre each intra-TAD cloud on its (optionally rescaled)
    # TAD centre — the intra geometry is preserved.
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

    # Stage 3c: optional iterative gradient-descent + reflection retry.
    if params.iterative and n_tads >= 2 and inter_tad_distances is not None:
        placed = _iterative_rotate_assemble(
            placed, tad_centres, inter_tad_distances,
            params.inner_max_iter,
            params.outer_max_iter,
            params.alpha,
            params.reflect_threshold,
            params.convergence_abs,
        )

    return np.vstack(placed)


def _rotation_matrix(theta: float, axis: np.ndarray) -> np.ndarray:
    """Rodrigues' rotation about unit vector ``axis`` by angle ``theta``."""
    ax = axis / max(np.linalg.norm(axis), 1e-12)
    c, s = np.cos(theta), np.sin(theta)
    x, y, z = ax
    C = 1.0 - c
    return np.array([
        [c + x * x * C,     x * y * C - z * s, x * z * C + y * s],
        [y * x * C + z * s, c + y * y * C,     y * z * C - x * s],
        [z * x * C - y * s, z * y * C + x * s, c + z * z * C],
    ])


def _rotate_around_centre(
    segment: np.ndarray, centre: np.ndarray, R: np.ndarray,
) -> np.ndarray:
    return (segment - centre) @ R.T + centre


def _iterative_rotate_assemble(
    placed: list,
    tad_centres: np.ndarray,
    inter_tad_distances: np.ndarray,
    inner_max_iter: int,
    outer_max_iter: int,
    alpha: float,
    reflect_threshold: float,
    convergence_abs: float,
) -> list:
    """Upstream GEM-FISH iterative assembly (Abbas 2019 Eqn. 13 + reflection).

    For each adjacent TAD pair ``(i, i+1)``:

    - Measure boundary distance ``df[i] = ||y_end[i] - y_start[i+1]||``
    - Compute gradient ``der[i] = 2(df[i] − d_prior[i])/df[i] × (y_start[i+1] − y_end[i])``
    - Move ``y_start[i+1]`` toward ``y_start[i+1] − alpha × der[i]``
    - Rotate TAD ``i+1`` around its centre so its first-point lands at
      the new target position.

    Outer loop: any TAD whose boundary-gap relative error is above
    ``reflect_threshold`` gets reflected (x,y mirror through its centre)
    and the inner loop restarts.
    """
    n_tads = len(placed)
    # d_prior for adjacent pairs only
    d_prior = np.array([
        float(inter_tad_distances[i, i + 1]) for i in range(n_tads - 1)
    ])
    # If any are 0 or non-finite, leave as no-op (matches upstream when
    # both Hi-C and genomic fallback yield 0)
    d_prior = np.where(np.isfinite(d_prior) & (d_prior > 0), d_prior, np.nan)

    placed = [np.asarray(p, dtype=np.float64).copy() for p in placed]
    lr = alpha

    for outer in range(outer_max_iter):
        # --- Inner gradient descent ---
        prev_err_sum = float("inf")
        stagnant = 0
        for inner in range(inner_max_iter):
            df = np.zeros(n_tads - 1)
            der = np.zeros((n_tads - 1, 3))
            ok_pairs = np.zeros(n_tads - 1, dtype=bool)
            for i in range(n_tads - 1):
                if placed[i].shape[0] < 1 or placed[i + 1].shape[0] < 1:
                    continue
                y_end = placed[i][-1]
                y_start = placed[i + 1][0]
                diff = y_start - y_end
                d = np.linalg.norm(diff)
                df[i] = d
                if not np.isfinite(d_prior[i]) or d < 1e-9:
                    continue
                factor = 2.0 * (d - d_prior[i]) / d
                der[i] = factor * diff
                ok_pairs[i] = True

            err = np.where(
                np.isfinite(d_prior), np.abs(d_prior - df), 0.0,
            )
            err_sum = float(err.sum())
            if err_sum < convergence_abs:
                break
            if abs(err_sum - prev_err_sum) < 0.01:
                stagnant += 1
            else:
                stagnant = 0
            if stagnant > 50:
                break
            prev_err_sum = err_sum

            # Every 1000 iters, escalate learning rate (as upstream does)
            if (inner + 1) % 1000 == 0:
                lr = lr * 2.0

            # Apply rotations
            for i in range(n_tads - 1):
                if not ok_pairs[i]:
                    continue
                y_start = placed[i + 1][0]
                y_new = y_start - lr * der[i]
                v1 = y_start - tad_centres[i + 1]
                v2 = y_new - tad_centres[i + 1]
                n1 = np.linalg.norm(v1)
                n2 = np.linalg.norm(v2)
                if n1 < 1e-9 or n2 < 1e-9:
                    continue
                cos_a = float(np.clip(
                    np.dot(v1, v2) / (n1 * n2), -1.0, 1.0,
                ))
                angle = float(np.arccos(cos_a))
                if angle < 1e-3:
                    continue
                axis = np.cross(v1, v2)
                if np.linalg.norm(axis) < 1e-9:
                    continue
                R = _rotation_matrix(angle, axis)
                placed[i + 1] = _rotate_around_centre(
                    placed[i + 1], tad_centres[i + 1], R,
                )

        # --- Outer loop: reflection retry for high-error TADs ---
        final_df = np.zeros(n_tads - 1)
        for i in range(n_tads - 1):
            final_df[i] = np.linalg.norm(
                placed[i + 1][0] - placed[i][-1]
            )
        with np.errstate(divide="ignore", invalid="ignore"):
            relative = np.where(
                np.isfinite(d_prior) & (d_prior > 0),
                np.abs(d_prior - final_df) / d_prior,
                0.0,
            )
        reflected_any = False
        for i in range(n_tads - 1):
            if relative[i] > reflect_threshold:
                # Reflect TAD i+1 through its centre in x and y
                centre = tad_centres[i + 1]
                reflected = placed[i + 1].copy()
                reflected[:, 0] = 2 * centre[0] - reflected[:, 0]
                reflected[:, 1] = 2 * centre[1] - reflected[:, 1]
                placed[i + 1] = reflected
                reflected_any = True
        if not reflected_any:
            break

    return placed


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
