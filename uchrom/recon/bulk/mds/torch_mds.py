# PyTorch MDS with GPU acceleration (CUDA / MPS / CPU)

import torch
import numpy as np


def get_device(device='auto'):
    """Get appropriate torch device."""
    if device == 'auto':
        if torch.cuda.is_available():
            return torch.device('cuda')
        elif torch.backends.mps.is_available():
            return torch.device('mps')
        else:
            return torch.device('cpu')
    return torch.device(device)


def get_dtype(device):
    """MPS only supports float32."""
    if device.type == 'mps':
        return torch.float32
    return torch.float64


def compute_stress(coords, dist_mat, weights=None):
    """Compute MDS stress: sum w_ij * (||x_i - x_j|| - d_ij)^2."""
    pred_dist = torch.cdist(coords, coords)
    diff_sq = (pred_dist - dist_mat) ** 2
    if weights is not None:
        diff_sq = weights * diff_sq
    stress = torch.triu(diff_sq, diagonal=1).sum()
    return stress


def cmds_init(dist_mat):
    """Classical MDS initialization via eigendecomposition."""
    n = dist_mat.shape[0]
    dtype = dist_mat.dtype
    device = dist_mat.device

    D_sq = dist_mat ** 2
    row_mean = D_sq.mean(dim=1, keepdim=True)
    col_mean = D_sq.mean(dim=0, keepdim=True)
    grand_mean = D_sq.mean()
    B = -0.5 * (D_sq - row_mean - col_mean + grand_mean)

    try:
        eigenvalues, eigenvectors = torch.linalg.eigh(B)
        idx = torch.argsort(eigenvalues, descending=True)[:3]
        top_eigenvalues = torch.clamp(eigenvalues[idx], min=1e-10)
        top_eigenvectors = eigenvectors[:, idx]
        coords = top_eigenvectors * torch.sqrt(top_eigenvalues)
    except RuntimeError:
        coords = torch.randn(n, 3, dtype=dtype, device=device)

    return coords


def torch_mds(dist_mat, device='auto', n_iter=1000, lr=0.01,
              tol=1e-6, init='cmds', verbose=False):
    """Run iterative MDS using Adam optimizer."""
    dev = get_device(device)
    dtype = get_dtype(dev)

    if isinstance(dist_mat, np.ndarray):
        dist_mat = torch.from_numpy(dist_mat)
    dist_mat = dist_mat.to(dtype=dtype, device=dev)
    n = dist_mat.shape[0]

    if init == 'cmds':
        coords = cmds_init(dist_mat)
    else:
        coords = torch.randn(n, 3, dtype=dtype, device=dev)
    coords = coords.requires_grad_(True)

    optimizer = torch.optim.Adam([coords], lr=lr)

    prev_loss = float('inf')
    for i in range(n_iter):
        optimizer.zero_grad()
        loss = compute_stress(coords, dist_mat)
        loss.backward()
        optimizer.step()

        current_loss = loss.item()
        if verbose and i % 100 == 0:
            print(f"Iteration {i}: stress = {current_loss:.6f}")
        if abs(prev_loss - current_loss) < tol:
            if verbose:
                print(f"Converged at iteration {i}")
            break
        prev_loss = current_loss

    result = coords.detach()
    result = result - result.mean(dim=0, keepdim=True)
    return result.cpu().numpy()


def run_mds(contact_mat, alpha=4.0, device='auto', weight=0.05, **kwargs):
    """Full MDS pipeline: contact matrix -> 3D coordinates."""
    from .core import (
        contact_to_distance,
        fill_missing_distances,
        normalize_distances,
        apply_distance_decay_prior
    )

    dev = get_device(device)
    dtype = get_dtype(dev)
    contact_mat = contact_mat.to(dtype=dtype, device=dev)

    print(f"Processing on device: {dev} (dtype: {dtype})")

    if weight > 0:
        contact_mat = apply_distance_decay_prior(contact_mat, weight)

    dist_mat = contact_to_distance(contact_mat, alpha)
    dist_mat = fill_missing_distances(dist_mat, contact_mat)
    dist_mat = normalize_distances(dist_mat)

    coords = torch_mds(dist_mat, device=device, **kwargs)
    return coords
