"""
TAD utility functions.
Support for external BED file import and substructure creation.
"""

import numpy as np
import pandas as pd
from typing import List, Tuple, Optional


def load_tad_from_bed(bed_path: str) -> List[Tuple[str, int, int]]:
    """
    Load TAD regions from external BED file.
    
    This allows users to use TAD calls from other software
    (e.g., TADbit, Arrowhead, TopDom) instead of built-in detection.
    
    Args:
        bed_path: Path to BED file with TAD regions
        
    Returns:
        List of (chrom, start, end) tuples
    """
    regions = []
    
    with open(bed_path, 'r') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            
            parts = line.split('\t')
            if len(parts) >= 3:
                chrom = parts[0]
                start = int(parts[1])
                end = int(parts[2])
                regions.append((chrom, start, end))
    
    return regions


def tad_regions_to_bin_indices(
    regions: List[Tuple[str, int, int]],
    bins_df: pd.DataFrame,
    chrom: Optional[str] = None
) -> List[Tuple[int, int]]:
    """
    Convert TAD genomic regions to bin indices.
    
    Args:
        regions: List of (chrom, start, end) genomic regions
        bins_df: DataFrame with bin information (chrom, start, end)
        chrom: Filter to specific chromosome (optional)
        
    Returns:
        List of (start_bin_idx, end_bin_idx) tuples
    """
    bin_indices = []
    
    for rgn_chrom, rgn_start, rgn_end in regions:
        if chrom is not None and rgn_chrom != chrom:
            continue
        
        # Find bins overlapping this region
        mask = (
            (bins_df['chrom'] == rgn_chrom) &
            (bins_df['start'] >= rgn_start) &
            (bins_df['end'] <= rgn_end)
        )
        
        matching_bins = bins_df[mask]
        
        if len(matching_bins) > 0:
            start_idx = matching_bins.index[0]
            end_idx = matching_bins.index[-1]
            bin_indices.append((start_idx, end_idx))
    
    return bin_indices


def substructures_from_tads(
    tad_indices: List[Tuple[int, int]],
    structure_coords: np.ndarray
) -> List[np.ndarray]:
    """
    Extract substructures from full structure based on TAD boundaries.
    
    Args:
        tad_indices: List of (start_idx, end_idx) bin indices
        structure_coords: N x 3 coordinate array
        
    Returns:
        List of coordinate arrays, one per TAD
    """
    substructures = []
    
    for start_idx, end_idx in tad_indices:
        subcoords = structure_coords[start_idx:end_idx+1].copy()
        substructures.append(subcoords)
    
    return substructures


def merge_substructures(
    substructures: List[np.ndarray],
    tad_indices: List[Tuple[int, int]],
    total_bins: int
) -> np.ndarray:
    """
    Merge TAD substructures back into full structure.
    
    Args:
        substructures: List of coordinate arrays per TAD
        tad_indices: List of (start_idx, end_idx) bin indices
        total_bins: Total number of bins in full structure
        
    Returns:
        N x 3 merged coordinate array
    """
    full_coords = np.zeros((total_bins, 3))
    
    for (start_idx, end_idx), subcoords in zip(tad_indices, substructures):
        full_coords[start_idx:end_idx+1] = subcoords
    
    return full_coords


def save_tads_to_bed(
    tad_indices: List[Tuple[int, int]],
    bins_df: pd.DataFrame,
    output_path: str
):
    """
    Save detected TAD regions to BED file.
    
    Args:
        tad_indices: List of (start_idx, end_idx) bin indices
        bins_df: DataFrame with bin information
        output_path: Output BED file path
    """
    with open(output_path, 'w') as f:
        for start_idx, end_idx in tad_indices:
            chrom = bins_df.iloc[start_idx]['chrom']
            start = bins_df.iloc[start_idx]['start']
            end = bins_df.iloc[end_idx]['end']
            f.write(f"{chrom}\t{start}\t{end}\n")
    
    print(f"TADs saved to {output_path}")
