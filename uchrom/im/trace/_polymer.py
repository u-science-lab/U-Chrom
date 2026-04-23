"""Gaussian-chain polymer primitives for the spatial genome aligner.

Two-end distance distribution of an ideal Gaussian chain of contour
length ``L`` with Kuhn segment ``b = 2 * l_p`` (persistence length) is
isotropic Gaussian with variance ``Nb² / 3`` per axis — i.e.
``<R²> = 2 * l_p * L`` for the 3-D distance, and ``<R²> / 3`` per axis.

Adding independent Gaussian localisation noise with axis variance
``σ²`` at each end yields

    S²(i, j) = σ_i² + σ_j² + (2/3) · l_p · τ · L_ij

which is the expected **axis-wise** variance of the observed distance
between two FISH spots connected by a contour length ``L_ij`` bp under
a scale factor ``τ`` (nm/bp).  ``S²`` scales the Gaussian-chain bond
probability used by the aligner.

All lengths here are in **nm** and all genomic distances in **bp**.
"""

from __future__ import annotations

from typing import Union, Tuple

import numpy as np

# Physical constants ----------------------------------------------------
PERSISTENCE_LENGTH_BP_DEFAULT: float = 150.0
"""Persistence length of bare B-form dsDNA, in bp.

One persistence length ≈ 50 nm at the canonical 0.34 nm/bp rise, which
gives ~150 bp.  For chromatin the *effective* persistence length is
much larger, but is folded into the fitted scale factor ``τ`` so we
keep the bp value constant.
"""


# ----------------------------------------------------------------------
# Distance statistics
# ----------------------------------------------------------------------

def expected_distance_sq(
    L_bp: Union[np.ndarray, float],
    l_p_bp: float = PERSISTENCE_LENGTH_BP_DEFAULT,
    tau_nm_per_bp: float = 0.01,
    sigma_nm: Union[np.ndarray, float] = 0.0,
) -> np.ndarray:
    """Gaussian-chain axis variance of the end-to-end distance.

    ``S²(L) = 2·σ² + (2/3)·l_p·τ·L``

    Parameters
    ----------
    L_bp : ndarray or float
        Genomic distance(s) in bp between the two loci.
    l_p_bp : float
        Persistence length in bp.
    tau_nm_per_bp : float
        Genomic-to-spatial scale factor (nm / bp).
    sigma_nm : ndarray or float
        Axis-wise localisation uncertainty of each endpoint, in nm.
        A scalar is broadcast to both endpoints; an array of shape (2,)
        or matching ``L_bp`` is also accepted.

    Returns
    -------
    S2 : ndarray or float
        Axis-wise variance of the observed distance, in nm².
    """
    L = np.asarray(L_bp, dtype=np.float64)
    sig = np.asarray(sigma_nm, dtype=np.float64)
    chain_term = (2.0 / 3.0) * l_p_bp * tau_nm_per_bp * L
    if sig.ndim == 0:
        noise_term = 2.0 * sig ** 2
    elif sig.shape == (2,):
        noise_term = sig[0] ** 2 + sig[1] ** 2
    else:
        # assume caller already summed σ_i² + σ_j²
        noise_term = sig
    return chain_term + noise_term


def expected_distance(
    L_bp: Union[np.ndarray, float],
    l_p_bp: float = PERSISTENCE_LENGTH_BP_DEFAULT,
    tau_nm_per_bp: float = 0.01,
) -> np.ndarray:
    """Gaussian-chain mean 3-D end-to-end distance ``<R> ≈ √(2·l_p·τ·L)``.

    Strictly ``<R> = √(8/(3π)) · √(<R²>)`` for a 3-D Gaussian variable,
    but the scaling-law form ``√(<R²>)`` is what the literature calls
    the "Gaussian chain" expected distance and what jie uses.
    """
    L = np.asarray(L_bp, dtype=np.float64)
    return np.sqrt(2.0 * l_p_bp * tau_nm_per_bp * np.maximum(L, 0.0))


def bond_log_probability(
    R_nm: Union[np.ndarray, float],
    S2_nm2: Union[np.ndarray, float],
) -> np.ndarray:
    """Log probability density of an observed distance ``R`` under an
    isotropic 3-D Gaussian with axis variance ``S²``.

    ``log p = -1.5 · log(2π·S²) - R² / (2·S²)``
    """
    R = np.asarray(R_nm, dtype=np.float64)
    S2 = np.asarray(S2_nm2, dtype=np.float64)
    S2_safe = np.where(S2 > 0, S2, np.nan)
    return -1.5 * np.log(2.0 * np.pi * S2_safe) - R * R / (2.0 * S2_safe)


def mahalanobis_cost(
    R_nm: Union[np.ndarray, float],
    S2_nm2: Union[np.ndarray, float],
) -> np.ndarray:
    """Mahalanobis-style squared cost ``R² / (2·S²)``.

    This is the **data-dependent** part of the negative log Gaussian
    density (the exponent, without the ``-1.5·log(2π·S²)`` normalisation
    constant).  For shortest-path aligners this has a useful property
    that :func:`bond_log_probability` does not: the cost of a single
    edge is independent of how many loci lie between its endpoints, so
    paths with different numbers of skipped loci can be compared
    fairly.

    Together with a per-skip ``gap_penalty`` it gives well-calibrated
    edge weights::

        w_ij = R²_ij / (2·S²_ij) + (c - 1) · gap_penalty
    """
    R = np.asarray(R_nm, dtype=np.float64)
    S2 = np.asarray(S2_nm2, dtype=np.float64)
    S2_safe = np.where(S2 > 0, S2, np.nan)
    return R * R / (2.0 * S2_safe)


# ----------------------------------------------------------------------
# Scale factor fitting
# ----------------------------------------------------------------------

def fit_scale_factor(
    observed_dist_nm: np.ndarray,
    genomic_dist_bp: np.ndarray,
    l_p_bp: float = PERSISTENCE_LENGTH_BP_DEFAULT,
    fix_exponent: bool = True,
) -> Tuple[float, float]:
    """Fit Gaussian-chain scale factor ``τ`` to observed trace distances.

    Performs a log-log regression of ``R`` on ``L``::

        log R = 0.5 · log(2·l_p·τ) + α · log L

    with ``α = 0.5`` fixed for an ideal Gaussian chain (``fix_exponent=
    True``) or fitted jointly.  Returns ``(τ, α)``.

    Parameters
    ----------
    observed_dist_nm : ndarray
        Observed 3-D distances (nm).  NaN and non-positive values are
        dropped.
    genomic_dist_bp : ndarray
        Genomic separations (bp) with the same shape as
        ``observed_dist_nm``.
    l_p_bp : float
        Persistence length (bp).
    fix_exponent : bool
        If True, force ``α = 0.5`` (ideal Gaussian chain).  If False,
        fit it jointly — useful for chromatin where ``α`` often ≈ 0.33
        (crumpled globule).

    Returns
    -------
    tau_nm_per_bp : float
    scaling_exponent : float
        ``0.5`` when ``fix_exponent=True``; otherwise the fitted value.
    """
    R = np.asarray(observed_dist_nm, dtype=np.float64).ravel()
    L = np.asarray(genomic_dist_bp, dtype=np.float64).ravel()
    mask = np.isfinite(R) & np.isfinite(L) & (R > 0) & (L > 0)
    if mask.sum() < 3:
        raise ValueError(
            "Need at least 3 finite, positive (R, L) samples to fit τ"
        )
    R = R[mask]
    L = L[mask]
    logR = np.log(R)
    logL = np.log(L)

    if fix_exponent:
        alpha = 0.5
        intercept = float(np.mean(logR - alpha * logL))
    else:
        A = np.vstack([np.ones_like(logL), logL]).T
        intercept, alpha = np.linalg.lstsq(A, logR, rcond=None)[0]
        intercept = float(intercept)
        alpha = float(alpha)

    # intercept = 0.5 · log(2 · l_p · τ)  when α = 0.5
    # 通用:  intercept = log(prefactor),  prefactor = √(2 l_p τ) under α=0.5
    #                   generalised via matching <R> ≈ prefactor · L^α
    if fix_exponent:
        tau = float(np.exp(2.0 * intercept) / (2.0 * l_p_bp))
    else:
        # With free α we just report an effective τ under the same α.
        prefactor = float(np.exp(intercept))
        tau = float(prefactor ** 2 / (2.0 * l_p_bp))
    return tau, float(alpha)


def fit_scale_factor_from_matrix(
    dist_matrix_nm: np.ndarray,
    bin_genomic_bp: np.ndarray,
    l_p_bp: float = PERSISTENCE_LENGTH_BP_DEFAULT,
    aggregator: str = "median",
    fix_exponent: bool = True,
) -> Tuple[float, float]:
    """Fit ``τ`` from a (n_bins, n_bins) distance matrix.

    For each unique off-diagonal genomic separation ``L``, aggregates
    the observed distances (median or mean) across all bin pairs with
    that separation, then runs :func:`fit_scale_factor` on the result.

    Parameters
    ----------
    dist_matrix_nm : ndarray (n_bins, n_bins)
        Pairwise distances in nm.  NaNs are ignored.
    bin_genomic_bp : ndarray (n_bins,)
        Genomic midpoint of each bin, in bp.
    l_p_bp : float
    aggregator : 'median' | 'mean'
    fix_exponent : bool

    Returns
    -------
    tau_nm_per_bp : float
    scaling_exponent : float
    """
    M = np.asarray(dist_matrix_nm, dtype=np.float64)
    bp = np.asarray(bin_genomic_bp, dtype=np.float64).ravel()
    n = M.shape[0]
    if M.shape != (n, n) or bp.size != n:
        raise ValueError("dist_matrix must be square and match bin_genomic_bp")

    iu, ju = np.triu_indices(n, k=1)
    Rvals = M[iu, ju]
    Lvals = np.abs(bp[iu] - bp[ju])
    mask = np.isfinite(Rvals) & np.isfinite(Lvals) & (Rvals > 0) & (Lvals > 0)
    Rvals = Rvals[mask]
    Lvals = Lvals[mask]
    if Rvals.size == 0:
        raise ValueError("No finite pairs in distance matrix")

    # Aggregate by unique L (stratified median / mean)
    unique_L, inverse = np.unique(Lvals, return_inverse=True)
    agg = np.full(unique_L.size, np.nan)
    fn = np.median if aggregator == "median" else np.mean
    for k in range(unique_L.size):
        sel = Rvals[inverse == k]
        if sel.size:
            agg[k] = float(fn(sel))
    keep = np.isfinite(agg)
    return fit_scale_factor(
        agg[keep], unique_L[keep],
        l_p_bp=l_p_bp, fix_exponent=fix_exponent,
    )


__all__ = [
    "PERSISTENCE_LENGTH_BP_DEFAULT",
    "expected_distance",
    "expected_distance_sq",
    "bond_log_probability",
    "mahalanobis_cost",
    "fit_scale_factor",
    "fit_scale_factor_from_matrix",
]
