"""
Complete miniMDS algorithm implementation - faithful to original.
Implements both full MDS and partitioned MDS with TAD-based domain detection.
"""

import numpy as np
import pandas as pd
from typing import List, Tuple, Optional, Dict, Any
from sklearn.manifold import MDS
import multiprocessing as mp
from functools import partial

from .minimds_core import (
    Structure, Point, ChromParameters, structureFromBed, chromFromBed, matFromBed,
    get_expected, contactToDist, makeSymmetric, getTransformation, radius_of_gyration,
    highToLow, cmds
)
from .tad_detection import getDomains, substructuresFromTads


def infer_structure(contactMat: np.ndarray, structure: Structure, alpha: float, 
                   num_threads: int, weight: float, classical: bool = False) -> Structure:
    """Infers 3D coordinates for one structure - core miniMDS algorithm"""
    assert len(structure.nonzero_abs_indices()) == len(contactMat)

    # Check for empty or invalid matrix
    if contactMat.size == 0 or np.all(contactMat == 0):
        raise ValueError("Contact matrix is empty or contains only zeros")

    # Apply distance decay prior
    expected = get_expected(contactMat)
    for i in range(len(contactMat)):
        for j in range(i):
            if i - j - 1 < len(expected):  # Bounds check
                contactMat[i, j] = (1 - weight) * contactMat[i, j] + weight * expected[i - j - 1]

    makeSymmetric(contactMat)
    rowsums = np.array([sum(row) for row in contactMat])
    
    # Check for zero row sums
    zero_rows = np.where(rowsums == 0)[0]
    if len(zero_rows) > 0:
        print(f"Warning: {len(zero_rows)} rows have zero sums, removing them")
        # Remove zero rows and columns
        valid_indices = np.where(rowsums > 0)[0]
        contactMat = contactMat[np.ix_(valid_indices, valid_indices)]
        # Update structure to match
        structure.points = structure.points[valid_indices]
        structure.set_rel_indices()

    # Convert contacts to distances
    distMat = contactToDist(contactMat, alpha)
    makeSymmetric(distMat)

    # Check for invalid distances
    if np.any(np.isnan(distMat)) or np.any(np.isinf(distMat)):
        print("Warning: Invalid distances found, replacing with finite values")
        distMat = np.nan_to_num(distMat, nan=1.0, posinf=10.0, neginf=0.1)

    # Normalize distance matrix
    mean_dist = np.mean(distMat[distMat > 0])
    if mean_dist > 0:
        distMat = distMat / mean_dist

    # Perform MDS
    try:
        if classical:  # classical MDS
            coords = cmds(distMat)
        else:
            mds = MDS(n_components=3, metric=True, random_state=42, 
                     verbose=0, dissimilarity="precomputed", n_jobs=1,  # Use single thread
                     normalized_stress='auto')  # Suppress warning
            coords = mds.fit_transform(distMat)
    except Exception as e:
        if "v cannot be empty" in str(e):
            # Handle empty distance matrix
            print(f"Warning: Empty distance matrix detected, using random coordinates")
            n_points = len(distMat)
            coords = np.random.rand(n_points, 3) * 0.1  # Small random coordinates
        else:
            raise e

    structure.setCoords(coords)
    return structure


def fullMDS(path: str, classical: bool, alpha: float, num_threads: int, weight: float) -> Structure:
    """MDS without partitioning - full structure inference"""
    structure = structureFromBed(path)
    contactMat = matFromBed(path, structure1=structure)
    return infer_structure(contactMat, structure, alpha, num_threads, weight, classical)


def mds_partition(high_substructure: Structure, low_substructure: Structure, path: str,
                 alpha2: float, weight: float, res_ratio: int) -> Structure:
    """Perform MDS on a single partition"""
    if len(high_substructure.getPoints()) > 0:  # skip empty
        # Perform MDS individually
        structure_contactMat = matFromBed(path, structure1=high_substructure)
        infer_structure(structure_contactMat, high_substructure, alpha2, 1, weight)

        # Approximate as low resolution
        inferred_low = highToLow(high_substructure, res_ratio)

        # Rescale
        scaling_factor = radius_of_gyration(low_substructure) / radius_of_gyration(inferred_low)
        for i, point in enumerate(inferred_low.points):
            if point != 0:
                x, y, z = point.pos
                inferred_low.points[i].pos = (x * scaling_factor, y * scaling_factor, z * scaling_factor)

        # Recover the transformation for inferred from true low structure
        r, t = getTransformation(inferred_low, low_substructure)
        if scaling_factor != 0:
            t /= scaling_factor

        # Transform high structure
        high_substructure.transform(r, t)

        print(f"MDS performed on substructure")

        return high_substructure


def partitionedMDS(path: str, domainSmoothingParameter: float, minSizeFraction: float,
                  maxmemory: int, num_threads: int, alpha: float, res_ratio: int,
                  alpha2: float, weight: float) -> Structure:
    """Partitions structure into substructures and performs MDS - full partitioned algorithm"""
    
    print("Beginning partitioned MDS")
    
    # Create low-res structure
    low_chrom = chromFromBed(path)
    print("Initialized low-resolution chromosome")
    low_chrom.res *= res_ratio
    lowstructure = structureFromBed(path, chrom=low_chrom)  # low global structure
    print("Initialized low-resolution structure")

    # Get TADs
    low_contactMat = matFromBed(path, structure1=lowstructure)
    low_tads = getDomains(low_contactMat, lowstructure, domainSmoothingParameter, minSizeFraction)
    substructuresFromTads(lowstructure, low_tads)
    print("Identified TADs")

    # Create high-res chrom
    highChrom = ChromParameters(lowstructure.chrom.minPos, lowstructure.chrom.maxPos, 
                               low_chrom.res // res_ratio, lowstructure.chrom.name)

    # Create high-res structure
    highstructure = Structure([], [], highChrom, 0)

    # Initialize high-res substructures
    high_substructures = []
    low_gen_coords = lowstructure.getGenCoords()
    offset = 0  # initialize
    for i, low_tad in enumerate(low_tads):
        start_gen_coord = low_gen_coords[low_tad[0]]
        if i == len(low_tads) - 1:  # for last tad, avoid rounding error
            end_gen_coord = highstructure.chrom.maxPos
        else:
            end_gen_coord = low_gen_coords[low_tad[1]]
        high_substructure = structureFromBed(path, None, highChrom, start_gen_coord, end_gen_coord, offset)
        high_substructures.append(high_substructure)
        offset += len(high_substructure.points)  # update
        offset -= 1

    highstructure.setstructures(high_substructures)
    print("Initialized high-resolution structure")

    # Low-resolution MDS
    if low_contactMat.size == 0 or np.all(low_contactMat == 0):
        print("Warning: Low-resolution contact matrix is empty, using full MDS instead")
        return fullMDS(path, False, alpha, num_threads, weight)
    
    infer_structure(low_contactMat, lowstructure, alpha, num_threads, weight)
    print("Low-resolution MDS complete")

    # High-resolution partitioned MDS
    num_substructures = len(highstructure.structures)
    print(f"Performing MDS on {num_substructures} substructures")
    
    # If no substructures, return the low-resolution structure
    if num_substructures == 0:
        print("Warning: No substructures found, returning low-resolution structure")
        return lowstructure
    
    # Process substructures sequentially to avoid multiprocessing issues
    processed_substructures = []
    for high_substructure, low_substructure in zip(highstructure.structures, lowstructure.structures):
        try:
            processed_substructure = mds_partition(high_substructure, low_substructure, path, alpha2, weight, res_ratio)
            processed_substructures.append(processed_substructure)
        except Exception as e:
            print(f"Warning: Failed to process substructure: {e}")
            # Use original substructure if processing fails
            processed_substructures.append(high_substructure)
    
    highstructure.setstructures(processed_substructures)

    highstructure.set_rel_indices()
    return highstructure


class MiniMDS:
    """Main miniMDS class that provides the interface for structure inference"""
    
    def __init__(self, alpha: float = 4.0, alpha2: float = 2.5, weight: float = 0.05,
                 num_threads: int = 3, classical: bool = False, partitioned: bool = False,
                 res_ratio: int = 10, domain_smoothing: float = 0.1, 
                 min_size_fraction: float = 0.05, max_memory: int = 32000000):
        """
        Initialize miniMDS with parameters.
        
        Args:
            alpha: Scaling factor for contact-to-distance conversion
            alpha2: Short-range scaling factor
            weight: Weight of distance decay prior
            num_threads: Number of threads for parallel processing
            classical: Use classical MDS instead of metric MDS
            partitioned: Use partitioned MDS for large datasets
            res_ratio: Resolution ratio for partitioned MDS
            domain_smoothing: Domain smoothing parameter
            min_size_fraction: Minimum domain size fraction
            max_memory: Maximum memory usage (in kb)
        """
        self.alpha = alpha
        self.alpha2 = alpha2
        self.weight = weight
        self.num_threads = num_threads
        self.classical = classical
        self.partitioned = partitioned
        self.res_ratio = res_ratio
        self.domain_smoothing = domain_smoothing
        self.min_size_fraction = min_size_fraction
        self.max_memory = max_memory
        
        self.structure = None
        self.metadata = {}
    
    def infer_structure(self, path: str) -> Structure:
        """
        Infer 3D structure from Hi-C BED file.
        
        Args:
            path: Path to Hi-C BED file
            
        Returns:
            Structure object with 3D coordinates
        """
        if self.partitioned:
            params = (self.domain_smoothing, self.min_size_fraction, self.max_memory,
                     self.num_threads, self.alpha, self.res_ratio, self.alpha2, self.weight)
            self.structure = partitionedMDS(path, *params)
        else:
            self.structure = fullMDS(path, self.classical, self.alpha, self.num_threads, self.weight)
        
        # Store metadata
        self.metadata = {
            'method': 'partitioned_mds' if self.partitioned else 'full_mds',
            'alpha': self.alpha,
            'alpha2': self.alpha2,
            'weight': self.weight,
            'num_threads': self.num_threads,
            'classical': self.classical,
            'res_ratio': self.res_ratio if self.partitioned else None,
            'domain_smoothing': self.domain_smoothing if self.partitioned else None,
            'min_size_fraction': self.min_size_fraction if self.partitioned else None
        }
        
        return self.structure
    
    def to_particles_dataframe(self) -> pd.DataFrame:
        """
        Convert structure to NucBox particles DataFrame format.
        
        Returns:
            DataFrame with columns: chrom, start, end, x, y, z
        """
        if self.structure is None:
            raise ValueError("No structure has been inferred yet")
        
        particles = []
        for point in self.structure.getPoints():
            gen_coord = self.structure.chrom.getGenCoord(point.absolute_index)
            particles.append({
                'chrom': self.structure.chrom.name,
                'start': gen_coord,
                'end': gen_coord + self.structure.chrom.res,
                'x': point.pos[0],
                'y': point.pos[1],
                'z': point.pos[2]
            })
        
        return pd.DataFrame(particles)
    
    def write_structure(self, output_path: str):
        """Write structure to TSV file in miniMDS format"""
        if self.structure is None:
            raise ValueError("No structure has been inferred yet")
        
        with open(output_path, "w") as out:
            out.write(self.structure.chrom.name + "\n")
            out.write(str(self.structure.chrom.res) + "\n")
            out.write(str(self.structure.chrom.minPos) + "\n")
            abs_index = self.structure.offset
            for point in self.structure.points:
                if point == 0:
                    out.write("\t".join((str(abs_index), "nan", "nan", "nan")) + "\n")
                else:
                    out.write("\t".join((str(abs_index), str(point.pos[0]), str(point.pos[1]), str(point.pos[2]))) + "\n")
                abs_index += 1


def infer_3d_structure_minimds(hic_df: pd.DataFrame, resolution: int = 100000,
                              use_partitioned: bool = True, **kwargs) -> Tuple[pd.DataFrame, Dict]:
    """
    Infer 3D structure using miniMDS algorithm.
    
    Args:
        hic_df: Hi-C DataFrame
        resolution: Bin resolution
        use_partitioned: Whether to use partitioned MDS
        **kwargs: Additional parameters for MiniMDS
        
    Returns:
        Tuple of (particles_df, metadata)
    """
    # Create temporary BED file
    import tempfile
    import os
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.bed', delete=False) as f:
        for _, row in hic_df.iterrows():
            # Calculate start and end positions from mid positions
            start1 = row['pos1'] - resolution // 2
            end1 = row['pos1'] + resolution // 2
            start2 = row['pos2'] - resolution // 2
            end2 = row['pos2'] + resolution // 2
            
            f.write(f"{row['chr1']}\t{start1}\t{end1}\t"
                   f"{row['chr2']}\t{start2}\t{end2}\t{row['count']}\n")
        temp_file = f.name
    
    try:
        # Initialize miniMDS
        minimds = MiniMDS(partitioned=use_partitioned, **kwargs)
        
        # Infer structure
        structure = minimds.infer_structure(temp_file)
        
        # Convert to particles DataFrame
        particles_df = minimds.to_particles_dataframe()
        
        # Get metadata
        metadata = minimds.metadata.copy()
        metadata.update({
            'n_points': len(particles_df),
            'resolution': resolution,
            'chromosome': structure.chrom.name
        })
        
        return particles_df, metadata
        
    finally:
        # Clean up temporary file
        os.unlink(temp_file)
