"""
PyTorch-based MDS implementation with GPU acceleration.
Supports CUDA, MPS (Apple Silicon), and CPU backends.
"""

import torch
import numpy as np
from typing import Optional, Literal, Tuple


def get_device(device: str = 'auto') -> torch.device:
    """
    Get the appropriate torch device.
    
    Args:
        device: 'cuda', 'mps', 'cpu', or 'auto'
        
    Returns:
        torch.device object
    """
    if device == 'auto':
        if torch.cuda.is_available():
            return torch.device('cuda')
        elif torch.backends.mps.is_available():
            return torch.device('mps')
        else:
            return torch.device('cpu')
    return torch.device(device)


def get_dtype(device: torch.device) -> torch.dtype:
    """
    Get appropriate dtype for device.
    MPS only supports float32, CUDA/CPU support float64.
    
    Args:
        device: torch device
        
    Returns:
        torch.float32 for MPS, torch.float64 for others
    """
    if device.type == 'mps':
        return torch.float32
    return torch.float64


def compute_stress(
    coords: torch.Tensor,
    dist_mat: torch.Tensor,
    weights: Optional[torch.Tensor] = None
) -> torch.Tensor:
    """
    Compute MDS stress function.
    
    stress = Σ w_ij * (||x_i - x_j|| - d_ij)²
    
    Uses vectorized computation without boolean masking for MPS compatibility.
    """
    # Compute pairwise distances from coordinates
    pred_dist = torch.cdist(coords, coords)
    
    # Compute squared differences for all pairs
    diff_sq = (pred_dist - dist_mat) ** 2
    
    # Only sum upper triangle (avoid double counting)
    # Use triu_indices for stable indexing
    if weights is not None:
        diff_sq = weights * diff_sq
    
    # Sum only upper triangle elements (excluding diagonal)
    stress = torch.triu(diff_sq, diagonal=1).sum()
    
    return stress


def cmds_init(dist_mat: torch.Tensor) -> torch.Tensor:
    """
    Classical MDS initialization using eigendecomposition.
    Provides a good starting point for iterative MDS.
    """
    n = dist_mat.shape[0]
    dtype = dist_mat.dtype
    device = dist_mat.device
    
    # Double centering
    D_sq = dist_mat ** 2
    row_mean = D_sq.mean(dim=1, keepdim=True)
    col_mean = D_sq.mean(dim=0, keepdim=True)
    grand_mean = D_sq.mean()
    
    B = -0.5 * (D_sq - row_mean - col_mean + grand_mean)
    
    # Eigendecomposition
    try:
        eigenvalues, eigenvectors = torch.linalg.eigh(B)
        
        # Take top 3 eigenvalues/vectors (they are sorted ascending)
        idx = torch.argsort(eigenvalues, descending=True)[:3]
        top_eigenvalues = eigenvalues[idx]
        top_eigenvectors = eigenvectors[:, idx]
        
        # Handle negative eigenvalues
        top_eigenvalues = torch.clamp(top_eigenvalues, min=1e-10)
        
        coords = top_eigenvectors * torch.sqrt(top_eigenvalues)
        
    except RuntimeError:
        # Fallback to random init if eigendecomposition fails
        coords = torch.randn(n, 3, dtype=dtype, device=device)
    
    return coords


def torch_mds(
    dist_mat: torch.Tensor,
    device: str = 'auto',
    n_iter: int = 1000,
    lr: float = 0.01,
    tol: float = 1e-6,
    init: Literal['cmds', 'random'] = 'cmds',
    verbose: bool = False
) -> np.ndarray:
    """
    PyTorch MDS implementation with GPU acceleration.
    Uses gradient descent to minimize stress function.
    
    Args:
        dist_mat: N x N distance matrix (numpy or torch)
        device: 'cuda', 'mps', 'cpu', or 'auto'
        n_iter: Maximum number of iterations
        lr: Learning rate for Adam optimizer
        tol: Convergence tolerance
        init: Initialization method ('cmds' or 'random')
        verbose: Print progress
        
    Returns:
        N x 3 numpy array of 3D coordinates
    """
    # Setup device and dtype
    dev = get_device(device)
    dtype = get_dtype(dev)
    
    # Convert to tensor if needed
    if isinstance(dist_mat, np.ndarray):
        dist_mat = torch.from_numpy(dist_mat)
    
    # Move to device with appropriate dtype
    dist_mat = dist_mat.to(dtype=dtype, device=dev)
    n = dist_mat.shape[0]
    
    # Initialize coordinates
    if init == 'cmds':
        coords = cmds_init(dist_mat)
    else:
        coords = torch.randn(n, 3, dtype=dtype, device=dev)
    
    coords = coords.requires_grad_(True)
    
    # Optimizer
    optimizer = torch.optim.Adam([coords], lr=lr)
    
    # Training loop
    prev_loss = float('inf')
    for i in range(n_iter):
        optimizer.zero_grad()
        
        loss = compute_stress(coords, dist_mat)
        loss.backward()
        optimizer.step()
        
        current_loss = loss.item()
        
        if verbose and i % 100 == 0:
            print(f"Iteration {i}: stress = {current_loss:.6f}")
        
        # Convergence check
        if abs(prev_loss - current_loss) < tol:
            if verbose:
                print(f"Converged at iteration {i}")
            break
        
        prev_loss = current_loss
    
    # Center coordinates
    result = coords.detach()
    result = result - result.mean(dim=0, keepdim=True)
    
    return result.cpu().numpy()


def run_mds(
    contact_mat: torch.Tensor,
    alpha: float = 4.0,
    device: str = 'auto',
    weight: float = 0.05,
    **kwargs
) -> np.ndarray:
    """
    Full MDS pipeline: contact matrix → 3D coordinates.
    All operations are performed on the specified device (GPU).
    """
    from .core import (
        contact_to_distance, 
        fill_missing_distances,
        normalize_distances,
        apply_distance_decay_prior
    )
    
    # Get device and dtype (MPS requires float32)
    dev = get_device(device)
    dtype = get_dtype(dev)
    
    # Move contact matrix to device with appropriate dtype
    contact_mat = contact_mat.to(dtype=dtype, device=dev)
    
    print(f"Processing on device: {dev} (dtype: {dtype})")
    
    # Apply distance decay prior (on GPU)
    if weight > 0:
        contact_mat = apply_distance_decay_prior(contact_mat, weight)
    
    # Convert contacts to distances (on GPU)
    dist_mat = contact_to_distance(contact_mat, alpha)
    
    # Fill missing values (on GPU)
    dist_mat = fill_missing_distances(dist_mat, contact_mat)
    
    # Normalize (on GPU)
    dist_mat = normalize_distances(dist_mat)
    
    # Run MDS (already on GPU with correct dtype)
    coords = torch_mds(dist_mat, device=device, **kwargs)
    
    return coords
