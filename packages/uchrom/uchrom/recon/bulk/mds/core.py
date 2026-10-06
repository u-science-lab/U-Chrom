# Core functions for MDS-based 3D structure reconstruction

import torch


def contact_to_distance(contact_mat, alpha=4.0):
    """Convert contact frequencies to distances: d = c^(-1/alpha).
    Zero contacts are treated as missing data (distance = 0)."""
    dist = torch.zeros_like(contact_mat)
    nonzero = contact_mat > 0
    dist[nonzero] = torch.pow(contact_mat[nonzero], -1.0 / alpha)
    dist.fill_diagonal_(0)
    return dist


def fill_missing_distances(dist_mat, contact_mat=None):
    """Fill zero (missing) distances using genomic distance prior.
    After contact_to_distance, zeros represent missing data, not zero distance."""
    device = dist_mat.device
    dtype = dist_mat.dtype
    dist = dist_mat.clone()
    n = dist.shape[0]

    # identify missing entries: off-diagonal zeros
    diag_mask = torch.eye(n, dtype=torch.bool, device=device)
    missing = (dist == 0) & ~diag_mask

    if not missing.any():
        return dist

    # compute average distance per genomic separation from observed entries
    idx = torch.arange(n, device=device, dtype=dtype)
    genomic_dist = torch.abs(idx.unsqueeze(0) - idx.unsqueeze(1))

    observed = (dist > 0) & ~diag_mask
    if observed.any():
        dist_per_unit = dist[observed] / genomic_dist[observed]
        avg_per_unit = dist_per_unit.mean()
    else:
        avg_per_unit = torch.tensor(1.0, device=device, dtype=dtype)

    # fill missing with linear genomic distance estimate
    estimated = avg_per_unit * genomic_dist
    dist = torch.where(missing, estimated, dist)
    dist.fill_diagonal_(0)

    return dist


def normalize_distances(dist_mat):
    """Normalize distance matrix to have unit mean.
    Includes zeros in mean calculation to match miniMDS behavior
    (miniMDS divides by np.mean(distMat) which includes zeros)."""
    mean_dist = dist_mat.mean()
    if mean_dist > 0:
        return dist_mat / mean_dist
    return dist_mat


def apply_distance_decay_prior(contact_mat, weight=0.05):
    """Apply distance decay prior to smooth contact frequencies.
    Expected values computed from nonzero contacts only (matching miniMDS)."""
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

    # only count nonzero contacts for expected value calculation
    nonzero = flat_contacts > 0
    flat_dists_nz = flat_dists[nonzero]
    flat_contacts_nz = flat_contacts[nonzero]

    expected_sum.scatter_add_(0, flat_dists_nz, flat_contacts_nz)
    counts.scatter_add_(0, flat_dists_nz, torch.ones_like(flat_contacts_nz))

    expected = expected_sum / torch.clamp(counts, min=1)
    expected_mat = expected[genomic_dist]

    result = (1 - weight) * contact_mat + weight * expected_mat
    return result
