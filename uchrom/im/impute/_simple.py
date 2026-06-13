"""
Simple interpolation methods for coordinate imputation.

These methods use scipy's interp1d for linear or cubic spline interpolation
along the 1D genomic coordinate.
"""

import numpy as np
from scipy.interpolate import interp1d


def impute_linear(cd, extrapolate=True, ann=None):
    """
    Impute missing coordinates using linear interpolation.

    The input is first densified onto the per-chrom locus panel, so loci that
    are missing as *absent rows* (not just NaN rows) are also imputed.

    Parameters
    ----------
    cd : ChromData
        Input ChromData with missing coordinates (NaN values and/or absent rows).
    extrapolate : bool, default True
        Whether to extrapolate values outside the range of known coordinates.
    ann : pd.DataFrame, optional
        Authoritative locus panel (columns chrom|region, start, end). When given,
        loci absent from every haploid are still restored.

    Returns
    -------
    ChromData
        ChromData on the dense grid with linearly interpolated coordinates.

    Examples
    --------
    >>> cd_imputed = impute_linear(cd)
    """
    return _impute_interpolation(cd, kind='linear', extrapolate=extrapolate, ann=ann)


def impute_cubic(cd, extrapolate=True, ann=None):
    """
    Impute missing coordinates using cubic spline interpolation.

    The input is first densified onto the per-chrom locus panel, so loci that
    are missing as *absent rows* (not just NaN rows) are also imputed.

    Parameters
    ----------
    cd : ChromData
        Input ChromData with missing coordinates (NaN values and/or absent rows).
    extrapolate : bool, default True
        Whether to extrapolate values outside the range of known coordinates.
    ann : pd.DataFrame, optional
        Authoritative locus panel (columns chrom|region, start, end).

    Returns
    -------
    ChromData
        ChromData on the dense grid with cubic-spline interpolated coordinates.

    Examples
    --------
    >>> cd_imputed = impute_cubic(cd)
    """
    return _impute_interpolation(cd, kind='cubic', extrapolate=extrapolate, ann=ann)


def _impute_interpolation(cd, kind, extrapolate, ann=None):
    """
    Internal function for scipy-based interpolation.

    Densifies onto the per-chrom locus panel, then interpolates along the
    genomic coordinate (start position) for each haploid independently.
    """
    from ._grid import build_dense_grid, grid_to_chromdata

    grid, _panel, has_cell = build_dense_grid(cd, ann=ann)
    # np.array (not asarray) guarantees a writable copy; h5cd-backed coords
    # can be read-only views.
    coords_imputed = np.array(grid[['x', 'y', 'z']].to_numpy(dtype=float))
    fill_value = 'extrapolate' if extrapolate else np.nan

    # grid is sorted by (region, haploid, pos); interpolate per haploid.
    for _hap, group_df in grid.groupby('haploid', sort=False):
        indices = group_df.index.to_numpy()
        positions = group_df['start'].to_numpy()
        group_coords = coords_imputed[indices]

        mask = ~np.isnan(group_coords[:, 0])
        if mask.sum() < 2:
            # Not enough anchors to interpolate; leave as NaN.
            continue

        for dim in range(3):
            f = interp1d(
                positions[mask],
                group_coords[mask, dim],
                kind=kind,
                fill_value=fill_value,
                bounds_error=False,
            )
            coords_imputed[indices, dim] = f(positions)

    grid[['x', 'y', 'z']] = coords_imputed
    return grid_to_chromdata(grid, has_cell, cd)
