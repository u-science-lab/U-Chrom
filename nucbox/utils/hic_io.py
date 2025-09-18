"""
Hi-C data I/O utilities for miniMDS integration.
Supports reading Hi-C BED files and converting to NucBox format.
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Tuple, Optional
import os


def read_hic_bed(file_path: str, resolution: int = 100000) -> pd.DataFrame:
    """
    Read Hi-C BED file and convert to NucBox format.
    
    Args:
        file_path: Path to Hi-C BED file
        resolution: Bin resolution in base pairs
        
    Returns:
        DataFrame with columns: chr1, pos1, chr2, pos2, count
    """
    try:
        # Read BED file
        df = pd.read_csv(file_path, sep='\t', header=None, 
                        names=['chr1', 'start1', 'end1', 'chr2', 'start2', 'end2', 'count'])
        
        # Filter out zero counts
        df = df[df['count'] > 0]
        
        # Calculate mid positions
        df['pos1'] = (df['start1'] + df['end1']) // 2
        df['pos2'] = (df['start2'] + df['end2']) // 2
        
        # Select relevant columns
        result = df[['chr1', 'pos1', 'chr2', 'pos2', 'count']].copy()
        
        # Convert chromosome names to string
        result['chr1'] = result['chr1'].astype(str)
        result['chr2'] = result['chr2'].astype(str)
        
        return result
        
    except Exception as e:
        raise ValueError(f"Failed to read Hi-C BED file {file_path}: {e}")


def hic_to_particles(hic_df: pd.DataFrame, resolution: int = 100000) -> pd.DataFrame:
    """
    Convert Hi-C data to particle format for NucBox visualization.
    
    Args:
        hic_df: Hi-C DataFrame with chr1, pos1, chr2, pos2, count
        resolution: Bin resolution in base pairs
        
    Returns:
        DataFrame with columns: chrom, start, end, x, y, z
    """
    # Get unique genomic positions
    positions = set()
    
    for _, row in hic_df.iterrows():
        positions.add((row['chr1'], row['pos1']))
        positions.add((row['chr2'], row['pos2']))
    
    # Create particles DataFrame
    particles = []
    for chrom, pos in positions:
        start = pos - resolution // 2
        end = pos + resolution // 2
        particles.append({
            'chrom': chrom,
            'start': start,
            'end': end,
            'x': 0.0,  # Will be filled by MDS
            'y': 0.0,
            'z': 0.0
        })
    
    return pd.DataFrame(particles)


def create_distance_matrix(hic_df: pd.DataFrame, resolution: int = 100000) -> Tuple[np.ndarray, List[Tuple[str, int]]]:
    """
    Create distance matrix from Hi-C contact frequencies.
    
    Args:
        hic_df: Hi-C DataFrame with chr1, pos1, chr2, pos2, count columns
        resolution: Bin resolution
        
    Returns:
        Distance matrix and position list
    """
    # Get unique positions
    positions = []
    pos_to_idx = {}
    
    for _, row in hic_df.iterrows():
        for chrom, pos in [(row['chr1'], row['pos1']), (row['chr2'], row['pos2'])]:
            key = (chrom, pos)
            if key not in pos_to_idx:
                pos_to_idx[key] = len(positions)
                positions.append(key)
    
    n = len(positions)
    contact_matrix = np.zeros((n, n))
    
    # Fill contact matrix
    for _, row in hic_df.iterrows():
        idx1 = pos_to_idx[(row['chr1'], row['pos1'])]
        idx2 = pos_to_idx[(row['chr2'], row['pos2'])]
        contact_matrix[idx1, idx2] = row['count']
        contact_matrix[idx2, idx1] = row['count']  # Symmetric
    
    # Convert to distance matrix using power law relationship
    # Distance ∝ (1/contact_frequency)^(1/3)
    distance_matrix = np.zeros_like(contact_matrix)
    
    for i in range(n):
        for j in range(n):
            if i == j:
                distance_matrix[i, j] = 0.0
            elif contact_matrix[i, j] > 0:
                # Power law: d = (1/c)^(1/3) * scale_factor
                distance_matrix[i, j] = (1.0 / contact_matrix[i, j]) ** (1.0/3.0)
            else:
                # No contact - set to large distance
                distance_matrix[i, j] = 10.0
    
    return distance_matrix, positions


def apply_mds_coordinates(particles_df: pd.DataFrame, coordinates: np.ndarray, 
                         positions: List[Tuple[str, int]]) -> pd.DataFrame:
    """
    Apply MDS coordinates to particles DataFrame.
    
    Args:
        particles_df: Particles DataFrame
        coordinates: 3D coordinates from MDS (n_points, 3)
        positions: List of (chrom, pos) tuples corresponding to coordinates
        
    Returns:
        Updated particles DataFrame with x, y, z coordinates
    """
    result_df = particles_df.copy()
    
    # Create position to coordinate mapping
    pos_to_coord = {}
    for i, (chrom, pos) in enumerate(positions):
        pos_to_coord[(chrom, pos)] = coordinates[i]
    
    # Apply coordinates
    for idx, row in result_df.iterrows():
        chrom = row['chrom']
        pos = (row['start'] + row['end']) // 2
        key = (chrom, pos)
        
        if key in pos_to_coord:
            x, y, z = pos_to_coord[key]
            result_df.at[idx, 'x'] = x
            result_df.at[idx, 'y'] = y
            result_df.at[idx, 'z'] = z
    
    return result_df


def validate_hic_data(hic_df: pd.DataFrame) -> bool:
    """
    Validate Hi-C data format and quality.
    
    Args:
        hic_df: Hi-C DataFrame
        
    Returns:
        True if valid, False otherwise
    """
    required_cols = ['chr1', 'pos1', 'chr2', 'pos2', 'count']
    
    # Check required columns
    if not all(col in hic_df.columns for col in required_cols):
        return False
    
    # Check for non-negative counts
    if (hic_df['count'] < 0).any():
        return False
    
    # Check for reasonable position values
    if (hic_df['pos1'] < 0).any() or (hic_df['pos2'] < 0).any():
        return False
    
    # Check for sufficient data (minimum 10 contacts for testing)
    if len(hic_df) < 10:
        return False
    
    return True


def get_chromosome_colormap(particles_df: pd.DataFrame) -> Dict[str, str]:
    """
    Generate chromosome colormap for visualization.
    
    Args:
        particles_df: Particles DataFrame with chrom column
        
    Returns:
        Dictionary mapping chromosome names to colors
    """
    import matplotlib.pyplot as plt
    import matplotlib.colors as mcolors
    
    chromosomes = sorted(particles_df['chrom'].unique())
    n_chroms = len(chromosomes)
    
    # Generate distinct colors
    if n_chroms <= 10:
        colors = plt.cm.tab10(np.linspace(0, 1, n_chroms))
    else:
        colors = plt.cm.tab20(np.linspace(0, 1, n_chroms))
    
    colormap = {}
    for i, chrom in enumerate(chromosomes):
        rgb = colors[i][:3]  # Remove alpha
        hex_color = mcolors.rgb2hex(rgb)
        colormap[chrom] = hex_color
    
    return colormap
