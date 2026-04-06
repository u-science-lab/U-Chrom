# Core functions for MDS-based 3D structure reconstruction

import numpy as np
import torch


def contacts_to_matrix(bin1, bin2, counts, n, dtype=torch.float64):
    """Build symmetric contact matrix from sparse contact data."""
    mat = torch.zeros((n, n), dtype=dtype)

    bin1 = np.asarray(bin1)
    bin2 = np.asarray(bin2)
    counts = np.asarray(counts)

    valid = (bin1 >= 0) & (bin1 < n) & (bin2 >= 0) & (bin2 < n)
    bin1_v = bin1[valid]
    bin2_v = bin2[valid]
    counts_v = counts[valid]

    indices = torch.tensor([bin1_v, bin2_v], dtype=torch.long)
    values = torch.tensor(counts_v, dtype=dtype)
    mat.index_put_(tuple(indices), values, accumulate=True)

    indices_sym = torch.tensor([bin2_v, bin1_v], dtype=torch.long)
    mat.index_put_(tuple(indices_sym), values, accumulate=True)

    # diagonal was added twice, fix it
    diag_mask = bin1_v == bin2_v
    if diag_mask.any():
        diag_idx = bin1_v[diag_mask]
        diag_vals = counts_v[diag_mask]
        for idx, val in zip(diag_idx, diag_vals):
            mat[idx, idx] = val

    return mat


def contact_to_distance(contact_mat, alpha=4.0, eps=1e-10):
    """Convert contact frequencies to distances: d = c^(-1/alpha)."""
    mat = torch.clamp(contact_mat, min=eps)
    dist = torch.pow(mat, -1.0 / alpha)
    dist.fill_diagonal_(0)
    return dist


def fill_missing_distances_vectorized(dist_mat, contact_mat=None):
    """Estimate missing distance values using genomic distance prior."""
    device = dist_mat.device
    dtype = dist_mat.dtype
    dist = dist_mat.clone()
    n = dist.shape[0]

    finite_mask = torch.isfinite(dist)
    if not finite_mask.any():
        return dist

    max_valid = dist[finite_mask].max()
    invalid_mask = ~finite_mask | (dist > max_valid * 10)

    if not invalid_mask.any():
        return dist

    idx = torch.arange(n, device=device, dtype=dtype)
    genomic_dist = torch.abs(idx.unsqueeze(0) - idx.unsqueeze(1))

    valid_mask = ~invalid_mask & (genomic_dist > 0)
    if valid_mask.any():
        dist_per_unit = dist[valid_mask] / genomic_dist[valid_mask]
        avg_per_unit = dist_per_unit.mean()
    else:
        avg_per_unit = max_valid / n

    estimated = avg_per_unit * genomic_dist
    dist = torch.where(invalid_mask, estimated, dist)
    dist.fill_diagonal_(0)

    return dist


def normalize_distances(dist_mat):
    """Normalize distance matrix to have unit mean."""
    n = dist_mat.shape[0]
    mask = ~torch.eye(n, dtype=torch.bool, device=dist_mat.device)
    mean_dist = dist_mat[mask].mean()
    if mean_dist > 0:
        return dist_mat / mean_dist
    return dist_mat


def apply_distance_decay_prior_vectorized(contact_mat, weight=0.05):
    """Apply distance decay prior to smooth contact frequencies."""
    device = contact_mat.device
    dtype = contact_mat.dtype
    n = contact_mat.shape[0]

    idx = torch.arange(n, device=device, dtype=dtype)
    genomic_dist = torch.abs(idx.unsqueeze(0) - idx.unsqueeze(1)).long()

    max_dist = n
    expected_sum = torch.zeros(max_dist, device=device, dtype=dtype)
    counts = torch.zeros(max_dist, device=device, dtype=dtype)

    triu_mask = torch.triu(torch.ones(n, n, device=device, dtype=torch.bool), diagonal=1)
    flat_dists = genomic_dist[triu_mask]
    flat_contacts = contact_mat[triu_mask]

    expected_sum.scatter_add_(0, flat_dists, flat_contacts)
    counts.scatter_add_(0, flat_dists, torch.ones_like(flat_contacts))

    expected = expected_sum / torch.clamp(counts, min=1)
    expected_mat = expected[genomic_dist]

    result = (1 - weight) * contact_mat + weight * expected_mat
    return result


# aliases
def fill_missing_distances(dist_mat, contact_mat=None):
    return fill_missing_distances_vectorized(dist_mat, contact_mat)


def apply_distance_decay_prior(contact_mat, weight=0.05):
    return apply_distance_decay_prior_vectorized(contact_mat, weight)
