"""Loss primitives for GEM-FISH.

Independent re-implementation of the loss terms from Abbas et al. 2019
(*Nat. Commun.*, doi:10.1038/s41467-019-10005-6).  Each primitive takes
a coordinate tensor of shape ``(*batch, n_bins, 3)`` (PyTorch) and
returns a scalar loss per batch item.  A leading batch dimension is
supported for ensemble training — stacking K independent models on the
first axis lets them share autograd and optimiser state at zero extra
code cost.

Summary of terms
----------------
- ``C_1`` — KL divergence between row-normalised Hi-C interaction
  frequencies and row-normalised inverse reconstructed distances.  This
  is the paper's Hi-C structural consistency term (Eqn. 3).
- ``C_2`` — polymer conformation energy (bond + angle + excluded
  volume).  The paper cites prior GEM / uchrom.recon.sc.gem for the
  functional form; implemented here as a sum of three standard
  harmonic / hinge terms.
- ``C_3`` — sum of squared errors between reconstructed pairwise
  distances and FISH-measured distances on TAD centres (Eqn. 6).
- ``C_4`` — L1 penalty on the deviation of squared radius-of-gyration
  from a FISH-derived target (Eqn. 7).

All lengths are in the coordinate system of ``coords`` (typically nm),
with the Hi-C-derived distances scaled to the same units.
"""

from __future__ import annotations

from typing import Optional

import torch
from torch import Tensor


_EPS = 1e-12


def _pairwise_dist(coords: Tensor) -> Tensor:
    """Return ``(..., N, N)`` Euclidean distances for ``coords``
    shaped ``(..., N, 3)``.  Diagonal is exactly zero.
    """
    diff = coords.unsqueeze(-2) - coords.unsqueeze(-3)  # (..., N, N, 3)
    return torch.sqrt((diff * diff).sum(-1).clamp_min(0.0) + _EPS)


# ----------------------------------------------------------------------
# C_1 — Hi-C KL divergence
# ----------------------------------------------------------------------

def hic_kl_loss(
    coords: Tensor,
    contacts: Tensor,
    mask: Optional[Tensor] = None,
) -> Tensor:
    """Row-wise KL divergence between normalised Hi-C and normalised
    inverse reconstructed distances.

    ``P_ij = f_ij / Σ_{k≠i} f_ik`` and
    ``Q_ij = (1 + d_ij)^{-1} / Σ_{k≠i} (1 + d_ik)^{-1}``, where
    ``d_ij = ||s_i - s_j||`` is the reconstructed 3-D distance.

    Returns ``Σ_i Σ_{j≠i} P_ij log(P_ij / Q_ij)`` summed over ``i``.

    Parameters
    ----------
    coords : Tensor (..., N, 3)
    contacts : Tensor (N, N)
        Raw Hi-C interaction frequencies.  Symmetric; diagonal ignored.
    mask : Tensor (N, N), optional
        Boolean mask of ``(i, j)`` pairs to include (for e.g. dropping
        unmappable bins).  Default: all off-diagonal pairs.
    """
    N = coords.shape[-2]
    # Zero the diagonal of contacts and mask
    contacts = contacts.to(coords.dtype).to(coords.device)
    diag = torch.eye(N, dtype=torch.bool, device=contacts.device)
    f = contacts.masked_fill(diag, 0.0)
    if mask is not None:
        f = f * mask.to(f.dtype)

    # Row-normalise Hi-C: P_ij = f_ij / Σ_j f_ij
    row_sum = f.sum(-1, keepdim=True).clamp_min(_EPS)
    P = f / row_sum

    d = _pairwise_dist(coords)
    inv = 1.0 / (1.0 + d)
    # Zero diagonal of inv so its row-sum matches P's support
    inv = inv.masked_fill(diag, 0.0)
    if mask is not None:
        inv = inv * mask.to(inv.dtype)
    Q = inv / inv.sum(-1, keepdim=True).clamp_min(_EPS)

    # KL(P||Q) = Σ P log(P/Q), summed over j then i.
    # When P_ij = 0 the term is 0 by convention; we clamp P to avoid log(0).
    valid = P > 0
    logterm = torch.where(
        valid,
        torch.log(P.clamp_min(_EPS) / Q.clamp_min(_EPS)),
        torch.zeros_like(P),
    )
    return (P * logterm).sum(dim=(-1, -2))


# ----------------------------------------------------------------------
# C_2 — polymer energy (bond + angle + excluded volume)
# ----------------------------------------------------------------------

def polymer_energy(
    coords: Tensor,
    bond_length: float = 1.0,
    bond_weight: float = 1.0,
    angle_weight: float = 0.1,
    exclude_weight: float = 1.0,
    exclude_radius: float = 1.0,
) -> Tensor:
    """Bond-stretching + angle-bending + excluded-volume energy.

    - Bond: ``Σ_i (||s_{i+1} - s_i|| - b)²``
    - Angle: ``Σ_i θ²`` where ``θ`` is the angle between successive
      bond vectors.
    - Exclude: ``Σ_{i<j} max(0, r - ||s_i - s_j||)²`` (hinge).

    Matches the functional form used in the existing
    ``uchrom.recon.sc.gem`` Taichi kernels.
    """
    N = coords.shape[-2]
    if N < 2:
        return torch.zeros(coords.shape[:-2], device=coords.device,
                           dtype=coords.dtype)

    # Bond
    bond_vec = coords[..., 1:, :] - coords[..., :-1, :]
    bond_len = torch.sqrt((bond_vec * bond_vec).sum(-1).clamp_min(0.0) + _EPS)
    E_bond = bond_weight * ((bond_len - bond_length) ** 2).sum(-1)

    # Angle — cosine between consecutive bond vectors
    if N >= 3:
        v1 = bond_vec[..., :-1, :]
        v2 = bond_vec[..., 1:, :]
        v1n = v1 / (v1.norm(dim=-1, keepdim=True).clamp_min(_EPS))
        v2n = v2 / (v2.norm(dim=-1, keepdim=True).clamp_min(_EPS))
        cos = (v1n * v2n).sum(-1).clamp(-1.0 + 1e-7, 1.0 - 1e-7)
        angle = torch.acos(cos)
        E_angle = angle_weight * (angle ** 2).sum(-1)
    else:
        E_angle = torch.zeros_like(E_bond)

    # Excluded volume — hinge penalty for pairs closer than exclude_radius
    d = _pairwise_dist(coords)
    triu = torch.triu(torch.ones_like(d), diagonal=1)
    overlap = torch.clamp_min(exclude_radius - d, 0.0) * triu
    E_exclude = exclude_weight * ((overlap) ** 2).sum(dim=(-1, -2))

    return E_bond + E_angle + E_exclude


# ----------------------------------------------------------------------
# C_3 — FISH distance constraints
# ----------------------------------------------------------------------

def fish_distance_loss(
    coords: Tensor,
    fish_distances: Tensor,
    mask: Optional[Tensor] = None,
) -> Tensor:
    """``Σ_{i,j ∈ M} (||s_i - s_j|| - F_ij)²``.

    Parameters
    ----------
    coords : Tensor (..., N, 3)
    fish_distances : Tensor (N, N)
        FISH-measured average pairwise distances.  Symmetric; NaN or
        non-finite entries are ignored.
    mask : Tensor (N, N), optional
        Extra Boolean mask — set to ``False`` where no FISH measurement
        is available.  If omitted, finite entries of ``fish_distances``
        define the mask automatically.
    """
    F = fish_distances.to(coords.dtype).to(coords.device)
    if mask is None:
        mask = torch.isfinite(F) & (F > 0)
    mask = mask.to(coords.device) & ~torch.eye(
        F.shape[-1], dtype=torch.bool, device=coords.device,
    )
    d = _pairwise_dist(coords)
    diff = torch.where(mask, d - F, torch.zeros_like(d))
    # Count each (i, j) pair once: divide by 2 (symmetric matrix)
    return 0.5 * (diff * diff).sum(dim=(-1, -2))


# ----------------------------------------------------------------------
# C_4 — Radius of gyration L1 penalty
# ----------------------------------------------------------------------

def rg_squared(coords: Tensor) -> Tensor:
    """Squared radius of gyration ``(1/N) Σ ||s_i - s̄||²``."""
    centroid = coords.mean(dim=-2, keepdim=True)
    d2 = ((coords - centroid) ** 2).sum(-1)
    return d2.mean(dim=-1)


def rg_loss(
    coords: Tensor,
    target_rg_sq: Tensor,
) -> Tensor:
    """``|R_g² - R̂_g²|`` — L1 penalty on the squared-Rg deviation.

    Parameters
    ----------
    coords : Tensor (..., N, 3)
    target_rg_sq : Tensor (...) or scalar
        FISH-derived ``R̂_g²``.  Broadcast over the batch dimension.
    """
    r2 = rg_squared(coords)
    target = torch.as_tensor(
        target_rg_sq, dtype=coords.dtype, device=coords.device,
    )
    return (r2 - target).abs()


__all__ = [
    "hic_kl_loss",
    "polymer_energy",
    "fish_distance_loss",
    "rg_squared",
    "rg_loss",
]
