"""
Partitioned MDS for high-resolution data.
Divide-and-conquer approach using TAD boundaries.
"""

import numpy as np
import torch
from typing import List, Tuple, Optional
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor


def partitioned_mds(
    contact_mat: torch.Tensor,
    tad_regions: Optional[List[Tuple[int, int]]] = None,
    device: str = 'auto',
    res_ratio: int = 10,
    alpha: float = 4.0,
    alpha2: float = 2.5,
    weight: float = 0.05,
    n_iter: int = 1000,
    verbose: bool = False,
    n_workers: int = 1
) -> np.ndarray:
    """
    Partitioned MDS for high-resolution Hi-C data.

    Algorithm:
    1. Create low-resolution contact matrix
    2. Run global MDS on low-res → scaffold
    3. Detect TADs (or use provided)
    4. Run high-res MDS on each TAD (parallel)
    5. Align each substructure to scaffold

    Args:
        contact_mat: N x N contact matrix
        tad_regions: Optional list of (start, end) TAD indices
        device: Compute device
        res_ratio: Low-res / high-res ratio
        alpha: Contact-distance exponent (global)
        alpha2: Contact-distance exponent (local/short-range)
        weight: Distance decay prior weight
        n_iter: MDS iterations
        verbose: Print progress
        n_workers: Number of parallel workers for TAD MDS

    Returns:
        N x 3 coordinate array
    """
    from .core import contact_to_distance, fill_missing_distances, normalize_distances
    from .torch_mds import torch_mds, run_mds
    from .transforms import align_substructure_to_scaffold, downsample_coords
    from uchrom.strc.tad import get_domains

    n = contact_mat.shape[0]

    if verbose:
        print(f"Starting partitioned MDS on {n} bins")

    # Step 1: Create low-resolution matrix
    n_low = n // res_ratio
    low_mat = torch.zeros((n_low, n_low), dtype=torch.float64)

    for i in range(n_low):
        for j in range(n_low):
            i_start, i_end = i * res_ratio, (i + 1) * res_ratio
            j_start, j_end = j * res_ratio, (j + 1) * res_ratio
            low_mat[i, j] = contact_mat[i_start:i_end, j_start:j_end].sum()

    if verbose:
        print(f"Created low-resolution matrix: {n_low} x {n_low}")

    # Step 2: Global MDS on low-res
    low_coords = run_mds(
        low_mat,
        alpha=alpha,
        device=device,
        weight=weight,
        n_iter=n_iter,
        verbose=verbose
    )

    if verbose:
        print("Low-resolution MDS complete")

    # Step 3: Detect TADs
    if tad_regions is None:
        tad_regions = get_domains(
            low_mat,
            smoothing_param=0.1,
            min_size_frac=0.05,
            device=device
        )
        # Convert low-res indices to high-res
        tad_regions = [
            (start * res_ratio, min((end + 1) * res_ratio - 1, n - 1))
            for start, end in tad_regions
        ]

    if verbose:
        print(f"Identified {len(tad_regions)} TAD regions")

    # Step 4: Run MDS on each TAD
    high_coords = np.zeros((n, 3))

    def process_tad(tad_info):
        idx, (start, end) = tad_info
        if end <= start:
            return idx, None

        # Extract submatrix
        sub_mat = contact_mat[start:end+1, start:end+1]

        # Run MDS
        sub_coords = run_mds(
            sub_mat,
            alpha=alpha2,
            device=device,
            weight=weight,
            n_iter=n_iter,
            verbose=False
        )

        return idx, (start, end, sub_coords)

    # Process TADs (parallel or sequential)
    if n_workers > 1 and len(tad_regions) > 1:
        with ThreadPoolExecutor(max_workers=n_workers) as executor:
            results = list(executor.map(process_tad, enumerate(tad_regions)))
    else:
        results = [process_tad((i, tad)) for i, tad in enumerate(tad_regions)]

    # Step 5: Align and merge substructures
    for idx, result in results:
        if result is None:
            continue

        start, end, sub_coords = result

        # Get corresponding low-res scaffold section
        low_start = start // res_ratio
        low_end = min(end // res_ratio, n_low - 1)
        scaffold_section = low_coords[low_start:low_end+1]

        if len(scaffold_section) > 0 and len(sub_coords) > 0:
            # Downsample high-res to compare with scaffold
            inferred_low = downsample_coords(sub_coords, res_ratio)

            if len(inferred_low) > 0 and len(inferred_low) == len(scaffold_section):
                # Align
                aligned = align_substructure_to_scaffold(
                    sub_coords, inferred_low, scaffold_section, res_ratio
                )
                high_coords[start:end+1] = aligned
            else:
                # Fallback: direct insertion without alignment
                high_coords[start:end+1] = sub_coords
        else:
            high_coords[start:end+1] = sub_coords

        if verbose:
            print(f"Processed TAD {idx+1}/{len(tad_regions)}: bins {start}-{end}")

    return high_coords
