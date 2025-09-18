"""
MDS (Multidimensional Scaling) engine for 3D structure inference from Hi-C data.
Based on miniMDS algorithm with optimizations for NucBox integration.
"""

import numpy as np
import pandas as pd
from typing import Tuple, Optional, List, Dict
from sklearn.manifold import MDS
from sklearn.metrics import pairwise_distances
import warnings
warnings.filterwarnings('ignore')


class MDSStructureEngine:
    """
    MDS-based 3D structure inference engine.
    """
    
    def __init__(self, n_components: int = 3, max_iter: int = 300, 
                 eps: float = 1e-3, random_state: Optional[int] = None):
        """
        Initialize MDS engine.
        
        Args:
            n_components: Number of dimensions (3 for 3D)
            max_iter: Maximum iterations
            eps: Convergence threshold
            random_state: Random seed for reproducibility
        """
        self.n_components = n_components
        self.max_iter = max_iter
        self.eps = eps
        self.random_state = random_state
        
        # MDS parameters
        self.mds = MDS(
            n_components=n_components,
            max_iter=max_iter,
            eps=eps,
            random_state=random_state,
            dissimilarity='precomputed',
            n_jobs=1
        )
        
        # Results storage
        self.coordinates_ = None
        self.stress_ = None
        self.n_iter_ = None
        
    def fit(self, distance_matrix: np.ndarray) -> 'MDSStructureEngine':
        """
        Fit MDS to distance matrix.
        
        Args:
            distance_matrix: Precomputed distance matrix
            
        Returns:
            Self for method chaining
        """
        # Validate input
        if distance_matrix.shape[0] != distance_matrix.shape[1]:
            raise ValueError("Distance matrix must be square")
        
        if not np.allclose(distance_matrix, distance_matrix.T):
            raise ValueError("Distance matrix must be symmetric")
        
        # Remove any infinite or NaN values
        distance_matrix = np.nan_to_num(distance_matrix, nan=0.0, posinf=10.0, neginf=0.0)
        
        # Fit MDS
        self.coordinates_ = self.mds.fit_transform(distance_matrix)
        self.stress_ = self.mds.stress_
        self.n_iter_ = self.mds.n_iter_
        
        return self
    
    def transform(self, distance_matrix: np.ndarray) -> np.ndarray:
        """
        Transform new distance matrix using fitted MDS.
        
        Args:
            distance_matrix: New distance matrix
            
        Returns:
            Transformed coordinates
        """
        if self.coordinates_ is None:
            raise ValueError("MDS must be fitted before transform")
        
        return self.mds.transform(distance_matrix)
    
    def get_coordinates(self) -> np.ndarray:
        """Get fitted 3D coordinates."""
        if self.coordinates_ is None:
            raise ValueError("MDS has not been fitted yet")
        return self.coordinates_.copy()
    
    def get_stress(self) -> float:
        """Get MDS stress value."""
        if self.stress_ is None:
            raise ValueError("MDS has not been fitted yet")
        return self.stress_


class PartitionedMDS:
    """
    Partitioned MDS for handling large datasets efficiently.
    """
    
    def __init__(self, partition_size: int = 1000, overlap: int = 100,
                 mds_params: Optional[Dict] = None):
        """
        Initialize partitioned MDS.
        
        Args:
            partition_size: Size of each partition
            overlap: Overlap between partitions
            mds_params: Parameters for MDS engine
        """
        self.partition_size = partition_size
        self.overlap = overlap
        self.mds_params = mds_params or {}
        
        # Results
        self.global_coordinates_ = None
        self.partition_results_ = []
        
    def fit(self, distance_matrix: np.ndarray, positions: List[Tuple[str, int]]) -> np.ndarray:
        """
        Fit partitioned MDS to large distance matrix.
        
        Args:
            distance_matrix: Distance matrix
            positions: List of (chrom, pos) tuples
            
        Returns:
            Global 3D coordinates
        """
        n_points = distance_matrix.shape[0]
        
        if n_points <= self.partition_size:
            # Use regular MDS for small datasets
            mds = MDSStructureEngine(**self.mds_params)
            mds.fit(distance_matrix)
            self.global_coordinates_ = mds.get_coordinates()
            return self.global_coordinates_
        
        # Partition the data
        partitions = self._create_partitions(n_points)
        
        # Fit MDS for each partition
        partition_coords = []
        for i, (start, end) in enumerate(partitions):
            sub_matrix = distance_matrix[start:end, start:end]
            sub_positions = positions[start:end]
            
            mds = MDSStructureEngine(**self.mds_params)
            mds.fit(sub_matrix)
            coords = mds.get_coordinates()
            
            partition_coords.append({
                'start': start,
                'end': end,
                'coordinates': coords,
                'positions': sub_positions
            })
        
        # Merge partitions
        self.global_coordinates_ = self._merge_partitions(partition_coords, n_points)
        self.partition_results_ = partition_coords
        
        return self.global_coordinates_
    
    def _create_partitions(self, n_points: int) -> List[Tuple[int, int]]:
        """Create partition boundaries."""
        partitions = []
        start = 0
        
        while start < n_points:
            end = min(start + self.partition_size, n_points)
            partitions.append((start, end))
            start = end - self.overlap
            
            if start >= n_points:
                break
        
        return partitions
    
    def _merge_partitions(self, partition_coords: List[Dict], n_points: int) -> np.ndarray:
        """Merge partition coordinates into global coordinates."""
        global_coords = np.zeros((n_points, 3))
        
        for partition in partition_coords:
            start = partition['start']
            end = partition['end']
            coords = partition['coordinates']
            
            # Simple overlap handling - use average for overlapping regions
            for i in range(len(coords)):
                global_idx = start + i
                if global_idx < n_points:
                    if np.allclose(global_coords[global_idx], 0):
                        global_coords[global_idx] = coords[i]
                    else:
                        # Average overlapping coordinates
                        global_coords[global_idx] = (global_coords[global_idx] + coords[i]) / 2
        
        return global_coords


def infer_3d_structure(hic_df: pd.DataFrame, resolution: int = 100000,
                      use_partitioned: bool = True, partition_size: int = 1000,
                      mds_params: Optional[Dict] = None) -> Tuple[pd.DataFrame, Dict]:
    """
    Infer 3D structure from Hi-C data using MDS.
    
    Args:
        hic_df: Hi-C DataFrame
        resolution: Bin resolution
        use_partitioned: Whether to use partitioned MDS
        partition_size: Size of partitions
        mds_params: MDS parameters
        
    Returns:
        Tuple of (particles_df, metadata)
    """
    from .hic_io import create_distance_matrix, hic_to_particles, apply_mds_coordinates
    
    # Create distance matrix
    distance_matrix, positions = create_distance_matrix(hic_df, resolution)
    
    # Create particles DataFrame
    particles_df = hic_to_particles(hic_df, resolution)
    
    # Infer 3D coordinates
    if use_partitioned and len(positions) > partition_size:
        mds = PartitionedMDS(partition_size=partition_size, mds_params=mds_params)
        coordinates = mds.fit(distance_matrix, positions)
    else:
        mds = MDSStructureEngine(**(mds_params or {}))
        mds.fit(distance_matrix)
        coordinates = mds.get_coordinates()
    
    # Apply coordinates to particles
    result_df = apply_mds_coordinates(particles_df, coordinates, positions)
    
    # Create metadata
    metadata = {
        'n_points': len(positions),
        'resolution': resolution,
        'method': 'partitioned_mds' if use_partitioned else 'mds',
        'stress': getattr(mds, 'stress_', None),
        'n_iter': getattr(mds, 'n_iter_', None)
    }
    
    return result_df, metadata


def optimize_mds_parameters(hic_df: pd.DataFrame, resolution: int = 100000,
                          param_grid: Optional[Dict] = None) -> Dict:
    """
    Optimize MDS parameters for best structure quality.
    
    Args:
        hic_df: Hi-C DataFrame
        resolution: Bin resolution
        param_grid: Parameter grid for optimization
        
    Returns:
        Best parameters
    """
    if param_grid is None:
        param_grid = {
            'max_iter': [100, 300, 500],
            'eps': [1e-2, 1e-3, 1e-4],
            'partition_size': [500, 1000, 2000]
        }
    
    best_params = {}
    best_stress = float('inf')
    
    # Simple grid search
    for max_iter in param_grid['max_iter']:
        for eps in param_grid['eps']:
            for partition_size in param_grid['partition_size']:
                try:
                    mds_params = {
                        'max_iter': max_iter,
                        'eps': eps
                    }
                    
                    _, metadata = infer_3d_structure(
                        hic_df, resolution, 
                        partition_size=partition_size,
                        mds_params=mds_params
                    )
                    
                    stress = metadata.get('stress', float('inf'))
                    if stress < best_stress:
                        best_stress = stress
                        best_params = {
                            'max_iter': max_iter,
                            'eps': eps,
                            'partition_size': partition_size
                        }
                        
                except Exception as e:
                    print(f"Failed with params {max_iter}, {eps}, {partition_size}: {e}")
                    continue
    
    return best_params
