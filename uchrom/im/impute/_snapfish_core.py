"""
SnapFISH-IMPUTE core integration for ChromData.

This module adapts the SnapFISH-IMPUTE algorithm to work with uchrom's ChromData.
"""

import numpy as np
import pandas as pd

from ._snapfish.impute import (
    interpolate_coors_scipy,
    to_dist_df,
    normalize_pdist_by1d,
    impute_pdist_one_iter,
    inverse_trf,
    recover_3d_coor_single_chr,
    count_na_in_pdist,
)


def impute_snapfish(cd, max_iter=50, verbose=True):
    """
    Impute missing coordinates using SnapFISH-IMPUTE algorithm.

    This is a single-process implementation. For large datasets (>1000 cells),
    consider exporting to SnapFISH format and using external MPI tools.

    Parameters
    ----------
    cd : ChromData
        Input ChromData with missing coordinates (NaN values).
    max_iter : int, default 50
        Maximum number of imputation iterations.
    verbose : bool, default True
        Print progress information.

    Returns
    -------
    ChromData
        ChromData with SnapFISH-imputed coordinates.

    Notes
    -----
    Algorithm steps:
    1. Linear interpolation for initialization
    2. Compute pairwise distance matrices
    3. Normalize by 1D genomic distance (Box-Cox transformation)
    4. Iteratively impute missing distances via similarity weighting
    5. Recover 3D coordinates via L-BFGS-B optimization

    References
    ----------
    Yu, H. et al. SnapFISH-IMPUTE (2023)
    https://github.com/hyuyu104/SnapFISH-IMPUTE
    """
    from uchrom.core import ChromData

    if verbose:
        n_missing = np.isnan(cd.coords).sum()
        n_total = cd.coords.size
        print(f"Input: {n_missing}/{n_total} ({n_missing/n_total*100:.1f}%) coordinates missing")

    # Step 1: Convert ChromData to SnapFISH format
    ann_df, coor_df = _chromdata_to_snapfish(cd)

    # Step 2: Linear interpolation for initialization
    if verbose:
        print("Step 1/4: Linear interpolation initialization...")
    linear_df = interpolate_coors_scipy(ann_df, coor_df, kind='linear')

    # Step 3: Compute and normalize pairwise distances
    if verbose:
        print("Step 2/4: Computing pairwise distance matrices...")
    dist_df = to_dist_df(coor_df, ann_df)
    norm_df = normalize_pdist_by1d(dist_df)

    # Step 4: Iterative imputation (single-process version)
    if verbose:
        print("Step 3/4: Iterative similarity-weighted imputation...")

    pdist_arr = norm_df.to_darr().T
    prev_na = None
    curr_na = count_na_in_pdist(pdist_arr)

    for i in range(max_iter):
        if curr_na == 0:
            if verbose:
                print(f"  Converged: all values imputed")
            break

        if curr_na == prev_na:
            if verbose:
                print(f"  Converged: no further improvement")
            break

        P = impute_pdist_one_iter(pdist_arr)
        pdist_arr = np.where(np.isnan(pdist_arr), P, pdist_arr)
        prev_na = curr_na
        curr_na = count_na_in_pdist(pdist_arr)

        if verbose:
            print(f"  Iteration {i+1}: {curr_na} NaN values remaining")

    # Update normalized distances
    norm_df[norm_df.vcol()] = pdist_arr.T

    # Step 5: Inverse transform to 3D coordinates
    if verbose:
        print("Step 4/4: Recovering 3D coordinates...")

    target_df = inverse_trf(norm_df)

    # Recover coordinates for each haploid
    imputed_coords_list = []

    for region in ann_df['region'].unique():
        reg_ann = ann_df[ann_df['region'] == region]
        reg_coor = coor_df[coor_df['region'] == region]
        reg_linear = linear_df[linear_df['region'] == region]
        reg_target = target_df[target_df['region'] == region]

        for haploid in reg_coor['haploid'].unique():
            hap_coor = reg_coor[reg_coor['haploid'] == haploid]
            hap_linear = reg_linear[reg_linear['haploid'] == haploid]

            raw = hap_coor[['x', 'y', 'z']].values
            lnr = hap_linear[['x', 'y', 'z']].values

            # Get target distances for this haploid
            hap_target = reg_target[haploid].values
            hap_trf = reg_target[['lmbda', 'mu', 'var']].values

            # Recover coordinates via optimization
            recovered = recover_3d_coor_single_chr(raw, lnr, hap_target, hap_trf)
            imputed_coords_list.append(recovered)

    # Reassemble coordinates
    imputed_coor_df = coor_df.copy()
    imputed_coor_df[['x', 'y', 'z']] = np.vstack(imputed_coords_list)

    # Step 6: Convert back to ChromData
    result = _snapfish_to_chromdata(ann_df, imputed_coor_df, cd)

    if verbose:
        n_still_missing = np.isnan(result.coords).sum()
        n_imputed = n_missing - n_still_missing
        print(f"Done! Imputed {n_imputed} coordinates ({n_imputed/n_missing*100:.1f}% of missing)")
        if n_still_missing > 0:
            print(f"Warning: {n_still_missing} coordinates remain missing (no reference data)")

    return result


def _chromdata_to_snapfish(cd):
    """
    Convert ChromData to SnapFISH format.

    Returns
    -------
    ann_df : pd.DataFrame
        Annotation file (region, pos, start, end)
    coor_df : pd.DataFrame
        Coordinate file (region, haploid, pos, x, y, z)
    """
    spots = cd.spots.copy()
    coords = cd.coords.copy()

    # Build annotation file (unique loci)
    ann_df = spots[['chrom', 'start', 'end']].drop_duplicates()
    ann_df = ann_df.sort_values(['chrom', 'start']).reset_index(drop=True)
    ann_df['pos'] = ann_df.groupby('chrom').cumcount() + 1  # 1-based
    ann_df = ann_df.rename(columns={'chrom': 'region'})
    ann_df = ann_df[['region', 'pos', 'start', 'end']]

    # Build coordinate file
    if 'cell_id' in spots.columns:
        haploid = spots['cell_id'].astype(str) + '.' + spots['trace_id'].astype(str)
    else:
        haploid = spots['trace_id'].astype(str)

    # Map to pos
    spot_key = spots['chrom'].astype(str) + '_' + spots['start'].astype(str)
    ann_key = ann_df['region'].astype(str) + '_' + ann_df['start'].astype(str)
    pos_map = pd.Series(ann_df['pos'].values, index=ann_key.values)

    coor_df = pd.DataFrame({
        'region': spots['chrom'],
        'haploid': haploid,
        'pos': spot_key.map(pos_map),
        'x': coords[:, 0],
        'y': coords[:, 1],
        'z': coords[:, 2],
    })

    return ann_df, coor_df


def _snapfish_to_chromdata(ann_df, coor_df, original_cd):
    """
    Convert SnapFISH format back to ChromData.

    Parameters
    ----------
    ann_df : pd.DataFrame
        Annotation file
    coor_df : pd.DataFrame
        Imputed coordinate file
    original_cd : ChromData
        Original ChromData (for metadata)

    Returns
    -------
    ChromData
        ChromData with imputed coordinates
    """
    from uchrom.core import ChromData

    # Reconstruct coordinates array (same order as original)
    coords_imputed = coor_df[['x', 'y', 'z']].values

    # Create new ChromData with same metadata
    result = ChromData(
        coords=coords_imputed,
        spots=original_cd.spots,
        cells=original_cd.cells if hasattr(original_cd, 'cells') else None,
        traces=original_cd.traces if hasattr(original_cd, 'traces') else None,
        tracks=original_cd.tracks if hasattr(original_cd, 'tracks') else None,
        layers=original_cd.layers if hasattr(original_cd, 'layers') else None,
        cellm=original_cd.cellm if hasattr(original_cd, 'cellm') else None,
        results=original_cd.results if hasattr(original_cd, 'results') else None,
        uns=original_cd.uns if hasattr(original_cd, 'uns') else None,
    )

    return result
