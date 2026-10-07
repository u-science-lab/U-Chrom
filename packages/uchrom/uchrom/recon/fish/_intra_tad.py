"""Stage 2 of GEM-FISH — intra-TAD fine 3-D model.

For each TAD ``t``, minimises Abbas et al. 2019 Eqn. (9)::

    C_t = C_1 + lambda_E * C_2 + lambda_R * C_4

- ``C_1``: row-wise KL on the intra-TAD Hi-C sub-matrix.
- ``C_2``: polymer energy (bond + angle + excluded volume).
- ``C_4``: L1 penalty on the deviation of the reconstructed squared
  radius of gyration from a FISH-derived target.

Each TAD is solved independently so the work is trivially parallel over
TADs.  We run an ensemble per TAD just like Stage 1 and keep the best
single fibre per TAD.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Tuple

import numpy as np
import torch

from ._losses import hic_kl_loss, polymer_energy, rg_loss
from ._tad_level import _resolve_device


@dataclass
class Stage2Params:
    """Optimisation parameters for Stage-2 (intra-TAD) reconstruction."""

    lambda_E: float = 0.05
    lambda_R: float = 0.01
    bond_length: float = 1.0
    bond_weight: float = 1.0
    angle_weight: float = 0.1
    exclude_weight: float = 1.0
    exclude_radius: float = 0.9

    n_iter: int = 500
    lr: float = 0.05
    optimiser: str = "adam"
    n_ensemble: int = 10
    init_scale: float = 2.0
    device: str = "auto"
    verbose: bool = False

    # Clamp the per-TAD matrix size to avoid pathological TADs
    max_bins_per_tad: int = 2000


# ----------------------------------------------------------------------

def _reconstruct_one_tad(
    sub_contacts: np.ndarray,
    target_rg_sq: Optional[float],
    params: Stage2Params,
) -> Tuple[np.ndarray, dict]:
    """Gradient descent on a single TAD's intra-Hi-C + Rg target."""
    device, dtype = _resolve_device(params.device)
    N = sub_contacts.shape[0]
    K = params.n_ensemble

    C = torch.as_tensor(sub_contacts, dtype=dtype, device=device)
    R_target = None
    if target_rg_sq is not None and np.isfinite(target_rg_sq):
        R_target = torch.tensor(float(target_rg_sq), dtype=dtype, device=device)

    torch.manual_seed(0)
    coords = params.init_scale * torch.randn(
        K, N, 3, dtype=dtype, device=device,
    )
    coords.requires_grad_(True)

    opt = torch.optim.Adam([coords], lr=params.lr)

    def _total(x):
        l1 = hic_kl_loss(x, C)
        l2 = polymer_energy(
            x,
            bond_length=params.bond_length,
            bond_weight=params.bond_weight,
            angle_weight=params.angle_weight,
            exclude_weight=params.exclude_weight,
            exclude_radius=params.exclude_radius,
        )
        l4 = (
            rg_loss(x, R_target)
            if R_target is not None
            else torch.zeros_like(l1)
        )
        return l1 + params.lambda_E * l2 + params.lambda_R * l4, l1, l2, l4

    history = np.zeros((params.n_iter, K), dtype=np.float64)
    for it in range(params.n_iter):
        opt.zero_grad()
        total, l1, l2, l4 = _total(coords)
        total.sum().backward()
        opt.step()
        history[it] = total.detach().cpu().numpy()

    with torch.no_grad():
        total, l1, l2, l4 = _total(coords)
        best = int(total.argmin().item())
        info = {
            "final_loss": total.cpu().numpy(),
            "best_ensemble_idx": best,
            "C_1": float(l1[best].item()),
            "C_2": float(l2[best].item()),
            "C_4": float(l4[best].item()),
        }
    return coords[best].detach().cpu().numpy(), info


def reconstruct_intra_tad(
    contacts: np.ndarray,
    tad_bin_indices: List[Tuple[int, int]],
    target_rg_sq_per_tad: Optional[List[float]] = None,
    params: Optional[Stage2Params] = None,
) -> Tuple[List[np.ndarray], List[dict]]:
    """Run Stage-2 on every TAD.

    Parameters
    ----------
    contacts : ndarray (n_bins, n_bins)
        Full bin-resolution Hi-C matrix (the same one used to build the
        TAD partition).
    tad_bin_indices : list of (start_idx, end_idx)
        Bin-index windows (end exclusive), as produced by
        :func:`uchrom.recon.fish._hic.aggregate_over_tads`.
    target_rg_sq_per_tad : list of float, optional
        FISH-derived :math:`\\hat{R}_g^2` per TAD (same length as
        ``tad_bin_indices``).  Use ``None`` or ``NaN`` for TADs without
        a measurement.
    params : Stage2Params

    Returns
    -------
    coords_per_tad : list of ndarray (n_bins_in_tad, 3)
    infos : list of dict per TAD (final loss, C_1, C_2, C_4)
    """
    params = params or Stage2Params()
    coords_out: List[np.ndarray] = []
    infos: List[dict] = []
    for ti, (s, e) in enumerate(tad_bin_indices):
        sub = contacts[s:e, s:e]
        N = sub.shape[0]
        if N < 2:
            # 1-bin TAD: just a point at origin
            coords_out.append(np.zeros((max(N, 1), 3), dtype=np.float64))
            infos.append({"final_loss": np.zeros(1), "note": "degenerate"})
            continue
        if N > params.max_bins_per_tad:
            if params.verbose:
                print(
                    f"[stage2] TAD {ti}: {N} bins exceeds "
                    f"max_bins_per_tad={params.max_bins_per_tad}; skipping"
                )
            coords_out.append(np.zeros((N, 3), dtype=np.float64))
            infos.append({"final_loss": np.zeros(1), "note": "oversize"})
            continue
        rg_target = None
        if target_rg_sq_per_tad is not None:
            rg_target = target_rg_sq_per_tad[ti]
        coords, info = _reconstruct_one_tad(sub, rg_target, params)
        coords_out.append(coords)
        infos.append(info)
        if params.verbose:
            print(
                f"[stage2] TAD {ti:4d}: {N:4d} bins  "
                f"loss={info['final_loss'].min():.4f}  "
                f"C1={info['C_1']:.4f}  C4={info['C_4']:.4f}"
            )
    return coords_out, infos


__all__ = ["Stage2Params", "reconstruct_intra_tad"]
