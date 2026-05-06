"""Synthetic end-to-end benchmark for GEM-FISH.

Generates a ground-truth polymer chain organised into ``n_tads`` tight
TADs, synthesises matching Hi-C contact counts (``f_ij = 1 / (1 + d_ij)``)
plus noisy per-pair FISH distances, runs the three stages directly, and
measures how well the final assembled chain recovers the truth via:

- per-stage loss values
- distance-matrix correlation (truth vs reconstructed)
- Procrustes RMSD after rigid + scale alignment

Usage::

    python benchmarks/gem_fish_synthetic.py
"""

from __future__ import annotations

import argparse
import numpy as np
from scipy.spatial.distance import cdist

from uchrom.recon.fish._tad_level import (
    Stage1Params, reconstruct_tad_level,
)
from uchrom.recon.fish._intra_tad import (
    Stage2Params, reconstruct_intra_tad,
)
from uchrom.recon.fish._assembly import assemble
from uchrom.recon.fish._hic import contact_to_distance


def _procrustes_rmsd(A: np.ndarray, B: np.ndarray) -> float:
    """Rigid-body + scale alignment RMSD (allow reflections)."""
    A = A - A.mean(0)
    B = B - B.mean(0)
    if np.std(B) > 1e-9:
        B = B * (np.std(A) / np.std(B))
    U, _, Vt = np.linalg.svd(A.T @ B)
    R = U @ Vt
    if np.linalg.det(R) < 0:
        Vt[-1] *= -1
        R = U @ Vt
    return float(np.sqrt(((A - B @ R.T) ** 2).sum(1).mean()))


def make_truth(seed: int = 0, n_tads: int = 5, bins_per_tad: int = 20):
    rng = np.random.default_rng(seed)
    # Each TAD is a tight random walk; TADs are offset from each other.
    tad_coords = []
    tad_centre_sep = 5.0
    centre = np.zeros(3)
    for t in range(n_tads):
        # random walk with small step → compact TAD
        walk = np.cumsum(rng.normal(0, 0.3, (bins_per_tad, 3)), axis=0)
        walk = walk - walk.mean(axis=0) + centre
        tad_coords.append(walk)
        # move centre forward along +x with some random tilt
        step = tad_centre_sep * (np.array([1.0, 0.0, 0.0])
                                 + 0.3 * rng.normal(0, 1, 3))
        centre = centre + step
    coords = np.vstack(tad_coords)
    # TAD bin windows
    tad_bins = [(t * bins_per_tad, (t + 1) * bins_per_tad)
                for t in range(n_tads)]
    tad_centres = np.array([coords[s:e].mean(axis=0) for (s, e) in tad_bins])
    return coords, tad_bins, tad_centres


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n-tads", type=int, default=5)
    ap.add_argument("--bins-per-tad", type=int, default=20)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--device", default="cpu")
    args = ap.parse_args()

    truth, tad_bins, truth_tad_centres = make_truth(
        seed=args.seed, n_tads=args.n_tads, bins_per_tad=args.bins_per_tad,
    )
    N = truth.shape[0]
    print(f"Ground truth: {N} bins across {args.n_tads} TADs")

    # Synthesise Hi-C: f_ij = 1 / (1 + d_ij)
    D_true = cdist(truth, truth)
    contacts = 1.0 / (1.0 + D_true)
    np.fill_diagonal(contacts, 0.0)

    # Aggregate to TAD-level contacts
    n_tads = args.n_tads
    inter_contacts = np.zeros((n_tads, n_tads))
    for i, (si, ei) in enumerate(tad_bins):
        for j, (sj, ej) in enumerate(tad_bins):
            inter_contacts[i, j] = contacts[si:ei, sj:ej].sum()

    # Synthesise FISH TAD-centre distances (noise = 0.1)
    rng = np.random.default_rng(args.seed + 1)
    F = cdist(truth_tad_centres, truth_tad_centres)
    F = F + rng.normal(0, 0.1, F.shape)
    np.fill_diagonal(F, 0.0)

    # Per-TAD Rg² targets
    rg_targets = []
    for (s, e) in tad_bins:
        sub = truth[s:e]
        centroid = sub.mean(0)
        rg2 = ((sub - centroid) ** 2).sum(1).mean()
        rg_targets.append(rg2 * (1 + 0.05 * rng.standard_normal()))

    # --- Stage 1
    print("\n=== Stage 1 ===")
    s1_params = Stage1Params(
        lambda_E=0.05, lambda_F=0.5, n_iter=500, n_ensemble=20,
        device=args.device, verbose=False,
    )
    tad_centres_recon, s1_info = reconstruct_tad_level(
        inter_contacts, F, params=s1_params,
    )
    D_c = cdist(tad_centres_recon, tad_centres_recon)
    D_ct = cdist(truth_tad_centres, truth_tad_centres)
    iu = np.triu_indices(n_tads, 1)
    corr_s1 = np.corrcoef(D_c[iu], D_ct[iu])[0, 1]
    rmsd_s1 = _procrustes_rmsd(truth_tad_centres, tad_centres_recon)
    print(f"Stage 1 centre-distance correlation: {corr_s1:.3f}")
    print(f"Stage 1 Procrustes RMSD: {rmsd_s1:.3f}")

    # --- Stage 2
    print("\n=== Stage 2 ===")
    s2_params = Stage2Params(
        lambda_E=0.05, lambda_R=0.01, n_iter=300, n_ensemble=6,
        device=args.device, verbose=False,
    )
    intra_coords, s2_info = reconstruct_intra_tad(
        contacts, tad_bins,
        target_rg_sq_per_tad=rg_targets,
        params=s2_params,
    )
    # Per-TAD intra correlation
    per_tad_corr = []
    for i, (s, e) in enumerate(tad_bins):
        D_i = cdist(intra_coords[i], intra_coords[i])
        D_t = cdist(truth[s:e], truth[s:e])
        n = e - s
        if n < 2:
            continue
        ci = np.corrcoef(D_i[np.triu_indices(n, 1)],
                         D_t[np.triu_indices(n, 1)])[0, 1]
        per_tad_corr.append(ci)
    print(f"Stage 2 mean intra-TAD distance correlation: "
          f"{np.mean(per_tad_corr):.3f}")

    # --- Stage 3 assembly
    print("\n=== Stage 3 ===")
    # Compute expected inter-TAD gaps from aggregated contacts
    tad_mid = np.array([
        0.5 * ((s + e) - 1) * args.bins_per_tad for (s, e) in tad_bins
    ])
    # Use unit genomic distance per bin for fallback
    genomic = np.abs(tad_mid[:, None] - tad_mid[None, :]).astype(np.float64)
    gap = contact_to_distance(
        inter_contacts, genomic_distances=genomic,
        alpha=0.25, fallback_c=1.0, fallback_beta=0.5,
    )
    final = assemble(tad_centres_recon, intra_coords, inter_tad_distances=gap)

    D_final = cdist(final, final)
    corr_final = np.corrcoef(D_final[np.triu_indices(N, 1)],
                              D_true[np.triu_indices(N, 1)])[0, 1]
    rmsd_final = _procrustes_rmsd(truth, final)
    print(f"Final full-chain distance correlation: {corr_final:.3f}")
    print(f"Final Procrustes RMSD: {rmsd_final:.3f}")

    print("\n=== Summary ===")
    print(f"{'Stage 1 centre corr':30s} {corr_s1:.3f}")
    print(f"{'Stage 1 centre RMSD':30s} {rmsd_s1:.3f}")
    print(f"{'Stage 2 mean intra corr':30s} {np.mean(per_tad_corr):.3f}")
    print(f"{'Final full-chain corr':30s} {corr_final:.3f}")
    print(f"{'Final full-chain RMSD':30s} {rmsd_final:.3f}")


if __name__ == "__main__":
    main()
