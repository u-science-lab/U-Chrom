# Coordinate transformations and SVD-based alignment

import numpy as np


def center_coords(coords):
    """Center coordinates to zero mean."""
    centroid = coords.mean(axis=0)
    centered = coords - centroid
    return centered, centroid


def compute_radius_of_gyration(coords):
    """Rg = sqrt(mean(||x - centroid||^2))."""
    centered, _ = center_coords(coords)
    distances_sq = np.sum(centered ** 2, axis=1)
    return np.sqrt(np.mean(distances_sq))


def procrustes_alignment(source, target, scale=True):
    """Align source to target using SVD-based Procrustes analysis."""
    source_centered, source_centroid = center_coords(source)
    target_centered, target_centroid = center_coords(target)

    if scale:
        source_rg = compute_radius_of_gyration(source)
        target_rg = compute_radius_of_gyration(target)
        scaling_factor = target_rg / source_rg if source_rg > 0 else 1.0
    else:
        scaling_factor = 1.0

    source_scaled = source_centered * scaling_factor

    H = source_scaled.T @ target_centered
    U, S, Vt = np.linalg.svd(H)

    R = Vt.T @ U.T
    if np.linalg.det(R) < 0:
        Vt[-1, :] *= -1
        R = Vt.T @ U.T

    t = target_centroid - scaling_factor * (R @ source_centroid)
    return R, t, scaling_factor


def apply_transform(coords, rotation=None, translation=None, scale=1.0):
    """Apply rotation, translation and scaling."""
    result = coords.copy()
    if scale != 1.0:
        result *= scale
    if rotation is not None:
        result = result @ rotation.T
    if translation is not None:
        result += translation
    return result


def align_substructure_to_scaffold(high_res_coords, low_res_coords,
                                   scaffold_coords, res_ratio=10):
    """Align high-res substructure to global scaffold via Procrustes."""
    R, t, scale = procrustes_alignment(low_res_coords, scaffold_coords)
    aligned = apply_transform(high_res_coords, R, t, scale)
    return aligned


def downsample_coords(coords, res_ratio, method='mean'):
    """Downsample coordinates by resolution ratio."""
    n = len(coords)
    n_low = n // res_ratio

    if method == 'mean':
        low_coords = np.zeros((n_low, 3))
        for i in range(n_low):
            start = i * res_ratio
            end = min((i + 1) * res_ratio, n)
            low_coords[i] = coords[start:end].mean(axis=0)
    else:
        low_coords = coords[::res_ratio]

    return low_coords
