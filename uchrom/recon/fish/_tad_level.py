"""Stage 1 of GEM-FISH — TAD-level coarse 3-D model.

Minimises the objective of Abbas et al. 2019 Eqn. (2)::

    C_g = C_1 + lambda_E * C_2 + lambda_F * C_3

- ``C_1``: row-wise KL between Hi-C and reconstructed inverse distances
  (:func:`._losses.hic_kl_loss`).
- ``C_2``: polymer energy (bond + angle + excluded volume)
  (:func:`._losses.polymer_energy`).
- ``C_3``: squared error against FISH-measured TAD-centre distances
  (:func:`._losses.fish_distance_loss`).

Gradient descent is run on an *ensemble* of ``n_ensemble`` independent
initialisations; the best single model (lowest final loss) is returned
by default but the full ensemble is also available via ``return_all``.

Loss weights in the paper (λ_E = 5e12, λ_F = 1e-8) assume raw (not
row-normalised) Hi-C counts as input; our PyTorch ``C_1`` is scale-free
after row-normalisation, so we expose smaller defaults that balance the
three terms for unit-normalised data — users should tune them for their
data.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

import numpy as np
import torch
from torch import Tensor

from ._losses import (
    hic_kl_loss,
    polymer_energy,
    fish_distance_loss,
)


@dataclass
class Stage1Params:
    """Optimisation parameters for Stage-1 (TAD-level) reconstruction."""

    lambda_E: float = 0.05     # polymer weight (relative to KL)
    lambda_F: float = 0.01     # FISH distance weight
    bond_length: float = 1.0
    bond_weight: float = 1.0
    angle_weight: float = 0.1
    exclude_weight: float = 1.0
    exclude_radius: float = 0.9

    n_iter: int = 1000
    lr: float = 0.05
    optimiser: str = "adam"    # 'adam' | 'lbfgs'
    n_ensemble: int = 20
    init_scale: float = 3.0    # std of Gaussian initialisation
    device: str = "auto"       # 'auto' | 'cuda' | 'mps' | 'cpu'
    verbose: bool = False


# ----------------------------------------------------------------------

def _resolve_device(spec: str) -> Tuple[torch.device, torch.dtype]:
    """Return ``(device, dtype)`` — MPS is float32-only, others float64."""
    if spec == "cuda":
        return torch.device("cuda"), torch.float64
    if spec == "mps":
        return torch.device("mps"), torch.float32
    if spec == "cpu":
        return torch.device("cpu"), torch.float64
    # auto
    if torch.cuda.is_available():
        return torch.device("cuda"), torch.float64
    if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
        return torch.device("mps"), torch.float32
    return torch.device("cpu"), torch.float64


def reconstruct_tad_level(
    contacts: np.ndarray,
    fish_distances: Optional[np.ndarray],
    params: Optional[Stage1Params] = None,
    initial_coords: Optional[np.ndarray] = None,
    return_all: bool = False,
) -> Tuple[np.ndarray, dict]:
    """Stage-1 TAD-level optimisation.

    Parameters
    ----------
    contacts : ndarray (N, N)
        Inter-TAD Hi-C contact matrix (sums over TAD windows).  Raw or
        normalised — row-normalisation happens inside ``C_1``.
    fish_distances : ndarray (N, N), optional
        FISH-measured pairwise distances between TAD centres.  ``NaN``
        or non-positive entries are ignored.  If ``None``, the FISH
        term is dropped.
    params : Stage1Params
    initial_coords : ndarray (N, 3) or (n_ensemble, N, 3), optional
        Override the Gaussian initialisation.
    return_all : bool
        If True, return the full ensemble ``(n_ensemble, N, 3)``;
        otherwise return the best single model ``(N, 3)``.

    Returns
    -------
    coords : ndarray
    info : dict with keys ``final_loss`` (per-ensemble),
        ``best_ensemble_idx``, ``loss_history`` (shape
        ``(n_iter, n_ensemble)``), and the split C_1 / C_2 / C_3 at
        the end.
    """
    params = params or Stage1Params()
    device, dtype = _resolve_device(params.device)
    N = contacts.shape[0]
    K = params.n_ensemble

    # --- Tensors ---
    C = torch.as_tensor(contacts, dtype=dtype, device=device)
    F = None
    if fish_distances is not None:
        F = torch.as_tensor(fish_distances, dtype=dtype, device=device)

    if initial_coords is not None:
        init = torch.as_tensor(initial_coords, dtype=dtype, device=device)
        if init.dim() == 2:
            init = init.unsqueeze(0).expand(K, -1, -1).clone()
        elif init.dim() == 3:
            K = init.shape[0]
        coords = init.clone()
    else:
        # MPS RNG doesn't support manual_seed on generators yet; seed torch global
        torch.manual_seed(0)
        coords = params.init_scale * torch.randn(
            K, N, 3, dtype=dtype, device=device,
        )
    coords.requires_grad_(True)

    # --- Optimiser ---
    if params.optimiser == "lbfgs":
        opt = torch.optim.LBFGS(
            [coords], lr=params.lr, max_iter=20, line_search_fn="strong_wolfe",
        )
    else:
        opt = torch.optim.Adam([coords], lr=params.lr)

    history = np.zeros((params.n_iter, K), dtype=np.float64)

    def _total_loss(x: Tensor) -> Tuple[Tensor, Tensor, Tensor, Tensor]:
        l1 = hic_kl_loss(x, C)
        l2 = polymer_energy(
            x,
            bond_length=params.bond_length,
            bond_weight=params.bond_weight,
            angle_weight=params.angle_weight,
            exclude_weight=params.exclude_weight,
            exclude_radius=params.exclude_radius,
        )
        l3 = (
            fish_distance_loss(x, F)
            if F is not None
            else torch.zeros_like(l1)
        )
        total = l1 + params.lambda_E * l2 + params.lambda_F * l3
        return total, l1, l2, l3

    for it in range(params.n_iter):
        if params.optimiser == "lbfgs":
            def closure():
                opt.zero_grad()
                total, _, _, _ = _total_loss(coords)
                total_sum = total.sum()
                total_sum.backward()
                return total_sum
            opt.step(closure)
            with torch.no_grad():
                total, _, _, _ = _total_loss(coords)
        else:
            opt.zero_grad()
            total, _, _, _ = _total_loss(coords)
            total.sum().backward()
            opt.step()
        history[it] = total.detach().cpu().numpy()
        if params.verbose and (it % max(1, params.n_iter // 10) == 0
                               or it == params.n_iter - 1):
            with torch.no_grad():
                _, l1, l2, l3 = _total_loss(coords)
                best = int(total.argmin().item())
                print(
                    f"[stage1] iter {it:5d}/{params.n_iter}  "
                    f"total={total[best]:.4f}  "
                    f"C1={l1[best]:.4f}  "
                    f"C2={l2[best]:.4f}  "
                    f"C3={l3[best]:.4f}  (ens best={best})"
                )

    with torch.no_grad():
        total, l1, l2, l3 = _total_loss(coords)
        final = total.cpu().numpy()
        best_idx = int(np.argmin(final))
        info = {
            "final_loss": final,
            "best_ensemble_idx": best_idx,
            "loss_history": history,
            "C_1": l1.cpu().numpy(),
            "C_2": l2.cpu().numpy(),
            "C_3": l3.cpu().numpy(),
        }

    out = coords.detach().cpu().numpy()
    if return_all:
        return out, info
    return out[best_idx], info


__all__ = ["Stage1Params", "reconstruct_tad_level"]
