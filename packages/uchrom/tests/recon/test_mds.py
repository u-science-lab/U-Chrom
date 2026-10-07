"""Bulk MDS: recover a known structure from its distance / contact matrix."""
import numpy as np
import torch
from scipy.spatial.distance import pdist, squareform
from scipy.stats import spearmanr


def _helix(n=60):
    t = np.linspace(0, 4 * np.pi, n)
    return np.c_[np.cos(t), np.sin(t), 0.3 * t]


def test_smacof_recovers_exact_distances():
    from uchrom.recon.bulk.mds.torch_mds import compute_stress, smacof

    X = _helix()
    D = squareform(pdist(X))
    Y = smacof(torch.as_tensor(D), device="cpu", n_iter=300)
    assert Y.shape == X.shape
    assert np.allclose(Y.mean(0), 0, atol=1e-6)
    r = np.corrcoef(pdist(Y), pdist(X))[0, 1]
    assert r > 0.999
    stress = float(compute_stress(torch.as_tensor(Y), torch.as_tensor(D)))
    assert np.isfinite(stress)


def test_run_mds_from_contacts_preserves_distance_ranks():
    from uchrom.recon.bulk.mds import run_mds

    X = _helix()
    D = squareform(pdist(X))
    C = np.zeros_like(D)
    off = ~np.eye(len(D), dtype=bool)
    C[off] = D[off] ** -3.0          # contact ∝ d^-α, α = 3
    C[:, 5] = C[5, :] = 0.0          # an empty bin → must be dropped
    Y, keep = run_mds(torch.as_tensor(C), alpha=3.0, device="cpu", weight=0.0,
                      n_iter=300)
    assert keep.sum() == len(D) - 1 and not keep[5]
    assert Y.shape == (len(D) - 1, 3)
    rho = spearmanr(pdist(Y), pdist(X[keep])).correlation
    assert rho > 0.95
