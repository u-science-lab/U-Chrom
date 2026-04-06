"""
Coordinate transformation utilities.
SVD-based alignment for merging substructures.
"""

import torch
import numpy as np
from typing import Tuple, Optional


def center_coords(coords: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    """
    Center coordinates to zero mean.
    
    Args:
        coords: N x 3 coordinate array
        
    Returns:
        Tuple of (centered_coords, centroid)
    """
    centroid = coords.mean(axis=0)
    centered = coords - centroid
    return centered, centroid


def compute_radius_of_gyration(coords: np.ndarray) -> float:
    """
    Calculate radius of gyration of structure.
    
    Rg = sqrt(mean(sum((coords - centroid)^2)))
    
    Args:
        coords: N x 3 coordinate array
        
    Returns:
        Radius of gyration
    """
    centered, _ = center_coords(coords)
    distances_sq = np.sum(centered ** 2, axis=1)
    rg = np.sqrt(np.mean(distances_sq))
    return rg


def procrustes_alignment(
    source: np.ndarray,
    target: np.ndarray,
    scale: bool = True
) -> Tuple[np.ndarray, np.ndarray, float]:
    """
    Align source coordinates to target using Procrustes analysis.
    
    Uses SVD to find optimal rotation.
    
    Args:
        source: N x 3 source coordinates
        target: N x 3 target coordinates
        scale: Whether to apply scaling
        
    Returns:
        Tuple of (rotation_matrix, translation_vector, scaling_factor)
    """
    # Center both
    source_centered, source_centroid = center_coords(source)
    target_centered, target_centroid = center_coords(target)
    
    # Compute scaling factor
    if scale:
        source_rg = compute_radius_of_gyration(source)
        target_rg = compute_radius_of_gyration(target)
        scaling_factor = target_rg / source_rg if source_rg > 0 else 1.0
    else:
        scaling_factor = 1.0
    
    # Apply scaling to source
    source_scaled = source_centered * scaling_factor
    
    # SVD for rotation
    H = source_scaled.T @ target_centered
    U, S, Vt = np.linalg.svd(H)
    
    # Handle reflection
    R = Vt.T @ U.T
    if np.linalg.det(R) < 0:
        Vt[-1, :] *= -1
        R = Vt.T @ U.T
    
    # Translation
    t = target_centroid - scaling_factor * (R @ source_centroid)
    
    return R, t, scaling_factor


def apply_transform(
    coords: np.ndarray,
    rotation: Optional[np.ndarray] = None,
    translation: Optional[np.ndarray] = None,
    scale: float = 1.0
) -> np.ndarray:
    """
    Apply transformation to coordinates.
    
    Args:
        coords: N x 3 coordinates
        rotation: 3 x 3 rotation matrix (optional)
        translation: 1 x 3 translation vector (optional)
        scale: Scaling factor
        
    Returns:
        Transformed coordinates
    """
    result = coords.copy()
    
    # Scale
    if scale != 1.0:
        result *= scale
    
    # Rotate
    if rotation is not None:
        result = result @ rotation.T
    
    # Translate
    if translation is not None:
        result += translation
    
    return result


def align_substructure_to_scaffold(
    high_res_coords: np.ndarray,
    low_res_coords: np.ndarray,
    scaffold_coords: np.ndarray,
    res_ratio: int = 10
) -> np.ndarray:
    """
    Align high-resolution substructure to global scaffold.
    
    Used in partitioned MDS to position each TAD substructure
    within the global low-resolution structure.
    
    Args:
        high_res_coords: High-resolution substructure coordinates
        low_res_coords: Same substructure at low resolution (inferred)
        scaffold_coords: Global scaffold at low resolution
        res_ratio: Resolution ratio (high_res / low_res)
        
    Returns:
        Aligned high-resolution coordinates
    """
    # Get transformation from inferred low-res to scaffold
    R, t, scale = procrustes_alignment(low_res_coords, scaffold_coords)
    
    # Apply transformation to high-res structure
    aligned = apply_transform(high_res_coords, R, t, scale)
    
    return aligned


def downsample_coords(
    coords: np.ndarray,
    res_ratio: int,
    method: str = 'mean'
) -> np.ndarray:
    """
    Downsample coordinates by resolution ratio.
    
    Args:
        coords: N x 3 high-resolution coordinates
        res_ratio: Downsampling ratio
        method: 'mean' or 'subsample'
        
    Returns:
        Downsampled coordinates
    """
    n = len(coords)
    n_low = n // res_ratio
    
    if method == 'mean':
        low_coords = np.zeros((n_low, 3))
        for i in range(n_low):
            start = i * res_ratio
            end = min((i + 1) * res_ratio, n)
            low_coords[i] = coords[start:end].mean(axis=0)
    else:
        # Subsample
        low_coords = coords[::res_ratio]
    
    return low_coords
