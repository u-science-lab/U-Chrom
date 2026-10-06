"""
SnapFISH-IMPUTE core integration for ChromData.

This module adapts the SnapFISH-IMPUTE algorithm to work with uchrom's ChromData.
"""

import numpy as np

from ._snapfish.impute import (
    interpolate_coors_scipy,
    to_dist_df,
    normalize_pdist_by1d,
    impute_pdist_one_iter,
    inverse_trf,
    recover_3d_coor_single_chr,
    count_na_in_pdist,
)


def _recover_all(tasks, n_jobs=1, verbose=False):
    """Recover 3D coordinates for every haploid.

    The per-haploid L-BFGS-B recovery is the dominant cost and is
    embarrassingly parallel. Its objective/Jacobian are Python callbacks
    (GIL-bound), so process-based parallelism (joblib's loky backend) is the
    only thing that helps; thread backends do not. Inner BLAS threads are pinned
    to 1 so workers don't oversubscribe cores.

    n_jobs=1 runs serially and is bit-for-bit identical to the original.
    """
    if n_jobs == 1 or len(tasks) < 2:
        return [recover_3d_coor_single_chr(*t) for t in tasks]

    from joblib import Parallel, delayed, parallel_config

    with parallel_config(backend="loky", inner_max_num_threads=1):
        return Parallel(n_jobs=n_jobs)(
            delayed(recover_3d_coor_single_chr)(*t) for t in tasks
        )


def impute_snapfish(cd, max_iter=50, ann=None, n_jobs=1, verbose=True):
    """
    Impute missing coordinates using SnapFISH-IMPUTE algorithm.

    This is a single-machine implementation with optional multiprocessing.
    For very large datasets, the original MPI tools remain an option.

    Parameters
    ----------
    cd : ChromData
        Input ChromData with missing coordinates (NaN values and/or absent rows).
    max_iter : int, default 50
        Maximum number of imputation iterations.
    ann : pd.DataFrame, optional
        Authoritative locus panel (columns chrom|region, start, end). When given,
        loci absent from every haploid are still restored. When omitted, the
        panel is the union of observed loci per chrom.
    n_jobs : int, default 1
        Number of worker processes for the per-haploid 3D recovery step
        (L-BFGS-B), which dominates runtime. 1 runs serially and is bit-for-bit
        identical to the original single-process algorithm; >1 distributes
        haploids across processes (joblib ``loky`` backend, inner BLAS threads
        pinned to avoid oversubscription). The algorithm is unchanged -- only
        independent per-haploid work is parallelized, so results are identical.
        Process-based parallelism is required here because the L-BFGS objective
        and Jacobian are Python callbacks (GIL-bound); thread backends do not
        help. On a ~300-haploid dataset this gives roughly 2.5x at n_jobs=4 and
        4x at n_jobs=8 end-to-end (the recovery step alone scales ~3.4x; the
        serial normalization/iteration phase caps the overall speedup).
    verbose : bool, default True
        Print progress information.

    Returns
    -------
    ChromData
        ChromData on the dense grid with SnapFISH-imputed coordinates.

    Notes
    -----
    Algorithm steps:
    1. Densify onto the per-chrom locus panel (insert NaN rows for absent loci)
    2. Linear interpolation for initialization
    3. Compute pairwise distance matrices
    4. Normalize by 1D genomic distance (Box-Cox transformation)
    5. Iteratively impute missing distances via similarity weighting
    6. Recover 3D coordinates via L-BFGS-B optimization

    References
    ----------
    Yu, H. et al. SnapFISH-IMPUTE (2023)
    https://github.com/hyuyu104/SnapFISH-IMPUTE
    """
    if verbose:
        n_missing = np.isnan(cd.coords).sum()
        n_total = cd.coords.size
        print(f"Input: {n_missing}/{n_total} ({n_missing/n_total*100:.1f}%) coordinates missing")

    # Step 1: Densify to the SnapFISH format on the full (haploid x locus) grid
    ann_df, coor_df = _chromdata_to_snapfish(cd, ann=ann)
    if verbose:
        n_grid_missing = np.isnan(coor_df[['x', 'y', 'z']].to_numpy()).any(axis=1).sum()
        print(f"Dense grid: {len(coor_df)} rows, {n_grid_missing} loci missing coords")

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

    # NaN-aware arithmetic below intentionally produces nan/inf in masked-out
    # entries; silence the resulting numpy warnings for the whole numeric body.
    with np.errstate(divide="ignore", invalid="ignore", over="ignore"):
        for i in range(max_iter):
            if curr_na == 0:
                if verbose:
                    print("  Converged: all values imputed")
                break

            if curr_na == prev_na:
                if verbose:
                    print("  Converged: no further improvement")
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

        # Collect one recovery task per haploid (KEYED by mask so results are
        # written back by identity, never by implicit row order).
        coor_df = coor_df.copy()
        coor_df[['x', 'y', 'z']] = np.array(
            coor_df[['x', 'y', 'z']].to_numpy(dtype=float)
        )
        recovered_xyz = coor_df[['x', 'y', 'z']].to_numpy(dtype=float)

        masks, tasks = [], []
        for region in ann_df['region'].unique():
            reg_mask = (coor_df['region'] == region).to_numpy()
            reg_coor = coor_df[reg_mask]
            reg_linear = linear_df[linear_df['region'] == region]
            reg_target = target_df[target_df['region'] == region]
            hap_trf = reg_target[['lmbda', 'mu', 'var']].values

            for haploid in reg_coor['haploid'].unique():
                hap_mask = reg_mask & (coor_df['haploid'] == haploid).to_numpy()
                raw = coor_df.loc[hap_mask, ['x', 'y', 'z']].to_numpy(dtype=float)
                lnr = reg_linear[reg_linear['haploid'] == haploid][['x', 'y', 'z']].values
                hap_target = reg_target[haploid].values
                masks.append(hap_mask)
                tasks.append((raw, lnr, hap_target, hap_trf))

    # 3D recovery (L-BFGS-B per haploid) dominates runtime. Its objective and
    # Jacobian are Python callbacks (GIL-bound), so only PROCESS-based parallelism
    # helps; threads do not. Inner BLAS threads are pinned to avoid oversubscription.
    recovered = _recover_all(tasks, n_jobs=n_jobs, verbose=verbose)
    for hap_mask, rec in zip(masks, recovered):
        recovered_xyz[hap_mask] = rec

    coor_df[['x', 'y', 'z']] = recovered_xyz

    # Step 6: Convert back to ChromData
    result = _snapfish_to_chromdata(coor_df, cd)

    if verbose:
        n_still_missing = np.isnan(result.coords).sum()
        print(f"Done! Result has {n_still_missing} coordinates still missing")
        if n_still_missing > 0:
            print(f"Note: {n_still_missing} coordinates remain missing (no reference data)")

    return result


def _chromdata_to_snapfish(cd, ann=None):
    """
    Convert ChromData to SnapFISH format on a dense (haploid x locus) grid.

    Returns
    -------
    ann_df : pd.DataFrame
        Annotation file (region, pos, start, end)
    coor_df : pd.DataFrame
        Dense coordinate grid with at least (region, haploid, pos, x, y, z),
        plus identity columns (chrom, start, end, trace_id, [cell_id]) for
        rebuilding the result. Sorted by (region, haploid, pos); absent loci
        have NaN coordinates.
    """
    from ._grid import build_dense_grid

    grid, panel, _has_cell = build_dense_grid(cd, ann=ann)

    ann_df = panel.rename(columns={'chrom': 'region'})
    ann_df['region'] = ann_df['region'].astype(str)
    ann_df = ann_df[['region', 'pos', 'start', 'end']]

    return ann_df, grid


def _snapfish_to_chromdata(coor_df, original_cd):
    """
    Convert a densified SnapFISH coordinate grid back to ChromData.

    Parameters
    ----------
    coor_df : pd.DataFrame
        Dense grid with chrom/start/end/trace_id/[cell_id]/x/y/z columns.
    original_cd : ChromData
        Original ChromData (for cell/trace-level metadata and uns).

    Returns
    -------
    ChromData
        ChromData with imputed coordinates on the dense grid.
    """
    from ._grid import grid_to_chromdata

    has_cell = 'cell_id' in coor_df.columns
    return grid_to_chromdata(coor_df, has_cell, original_cd)
