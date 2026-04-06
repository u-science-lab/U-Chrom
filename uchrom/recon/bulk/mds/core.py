"""
Core functions for MDS-based 3D structure reconstruction.
Optimized for GPU with vectorized operations.
"""

import numpy as np
import torch
from typing import Optional, Tuple


def contacts_to_matrix(
    bin1: np.ndarray,
    bin2: np.ndarray,
    counts: np.ndarray,
    n: int,
    dtype: torch.dtype = torch.float64
) -> torch.Tensor:
    """
    Build symmetric contact matrix from sparse contact data.
    Vectorized implementation.
    """
    mat = torch.zeros((n, n), dtype=dtype)
    
    # Vectorized assignment
    bin1 = np.asarray(bin1)
    bin2 = np.asarray(bin2)
    counts = np.asarray(counts)
    
    # Filter valid indices
    valid = (bin1 >= 0) & (bin1 < n) & (bin2 >= 0) & (bin2 < n)
    bin1_v = bin1[valid]
    bin2_v = bin2[valid]
    counts_v = counts[valid]
    
    # Use index_put_ for efficient assignment
    indices = torch.tensor([bin1_v, bin2_v], dtype=torch.long)
    values = torch.tensor(counts_v, dtype=dtype)
    mat.index_put_(tuple(indices), values, accumulate=True)
    
    # Make symmetric
    indices_sym = torch.tensor([bin2_v, bin1_v], dtype=torch.long)
    mat.index_put_(tuple(indices_sym), values, accumulate=True)
    
    # Diagonal was added twice, fix it
    diag_mask = bin1_v == bin2_v
    if diag_mask.any():
        diag_idx = bin1_v[diag_mask]
        diag_vals = counts_v[diag_mask]
        for idx, val in zip(diag_idx, diag_vals):
            mat[idx, idx] = val
    
    return mat


def contact_to_distance(
    contact_mat: torch.Tensor,
    alpha: float = 4.0,
    eps: float = 1e-10
) -> torch.Tensor:
    """
    Convert contact frequencies to distances using power law.
    Fully vectorized, GPU-friendly.
    
    distance = contact_frequency^(-1/alpha)
    """
    # Avoid zero contacts - fully vectorized
    mat = torch.clamp(contact_mat, min=eps)
    
    # Apply power law: d = c^(-1/alpha)
    dist = torch.pow(mat, -1.0 / alpha)
    
    # Set diagonal to 0 (distance to self)
    dist.fill_diagonal_(0)
    
    return dist


def fill_missing_distances_vectorized(
    dist_mat: torch.Tensor,
    contact_mat: Optional[torch.Tensor] = None
) -> torch.Tensor:
    """
    Estimate missing distance values using genomic distance prior.
    Vectorized GPU implementation.
    """
    device = dist_mat.device
    dtype = dist_mat.dtype
    dist = dist_mat.clone()
    n = dist.shape[0]
    
    # Find invalid entries (inf or very large)
    finite_mask = torch.isfinite(dist)
    if not finite_mask.any():
        return dist
    
    max_valid = dist[finite_mask].max()
    invalid_mask = ~finite_mask | (dist > max_valid * 10)
    
    if not invalid_mask.any():
        return dist
    
    # Create genomic distance matrix (vectorized)
    idx = torch.arange(n, device=device, dtype=dtype)
    genomic_dist = torch.abs(idx.unsqueeze(0) - idx.unsqueeze(1))
    
    # Calculate average distance per genomic unit for valid entries
    valid_mask = ~invalid_mask & (genomic_dist > 0)
    if valid_mask.any():
        # Distance per unit genomic distance
        dist_per_unit = dist[valid_mask] / genomic_dist[valid_mask]
        avg_per_unit = dist_per_unit.mean()
    else:
        avg_per_unit = max_valid / n
    
    # Estimate missing distances based on genomic distance
    estimated = avg_per_unit * genomic_dist
    
    # Fill invalid entries
    dist = torch.where(invalid_mask, estimated, dist)
    
    # Ensure diagonal is 0
    dist.fill_diagonal_(0)
    
    return dist


def normalize_distances(dist_mat: torch.Tensor) -> torch.Tensor:
    """
    Normalize distance matrix to have unit mean.
    Fully vectorized.
    """
    n = dist_mat.shape[0]
    # Exclude diagonal from mean calculation
    mask = ~torch.eye(n, dtype=torch.bool, device=dist_mat.device)
    mean_dist = dist_mat[mask].mean()
    
    if mean_dist > 0:
        return dist_mat / mean_dist
    return dist_mat


def apply_distance_decay_prior_vectorized(
    contact_mat: torch.Tensor,
    weight: float = 0.05
) -> torch.Tensor:
    """
    Apply distance decay prior to smooth contact frequencies.
    Fully vectorized GPU implementation.
    """
    device = contact_mat.device
    dtype = contact_mat.dtype
    n = contact_mat.shape[0]
    
    # Create genomic distance matrix
    idx = torch.arange(n, device=device, dtype=dtype)
    genomic_dist = torch.abs(idx.unsqueeze(0) - idx.unsqueeze(1)).long()
    
    # Calculate expected contacts at each genomic distance
    # Use scatter_add for efficient binning
    max_dist = n
    expected_sum = torch.zeros(max_dist, device=device, dtype=dtype)
    counts = torch.zeros(max_dist, device=device, dtype=dtype)
    
    # Flatten and use upper triangle only
    triu_mask = torch.triu(torch.ones(n, n, device=device, dtype=torch.bool), diagonal=1)
    flat_dists = genomic_dist[triu_mask]
    flat_contacts = contact_mat[triu_mask]
    
    expected_sum.scatter_add_(0, flat_dists, flat_contacts)
    counts.scatter_add_(0, flat_dists, torch.ones_like(flat_contacts))
    
    # Average expected at each distance
    expected = expected_sum / torch.clamp(counts, min=1)
    
    # Apply prior using the genomic distance matrix as index
    expected_mat = expected[genomic_dist]
    
    # Blend original with expected
    result = (1 - weight) * contact_mat + weight * expected_mat
    
    return result


# Aliases for backward compatibility
def fill_missing_distances(
    dist_mat: torch.Tensor,
    contact_mat: Optional[torch.Tensor] = None
) -> torch.Tensor:
    """Alias for vectorized version."""
    return fill_missing_distances_vectorized(dist_mat, contact_mat)


def apply_distance_decay_prior(
    contact_mat: torch.Tensor,
    weight: float = 0.05
) -> torch.Tensor:
    """Alias for vectorized version."""
    return apply_distance_decay_prior_vectorized(contact_mat, weight)
