"""
Simple interpolation methods for coordinate imputation.

These methods use scipy's interp1d for linear or cubic spline interpolation
along the 1D genomic coordinate.
"""

import numpy as np
from scipy.interpolate import interp1d


def impute_linear(cd, extrapolate=True):
    """
    Impute missing coordinates using linear interpolation.

    Parameters
    ----------
    cd : ChromData
        Input ChromData with missing coordinates (NaN values).
    extrapolate : bool, default True
        Whether to extrapolate values outside the range of known coordinates.

    Returns
    -------
    ChromData
        ChromData with linearly interpolated coordinates.

    Examples
    --------
    >>> cd_imputed = impute_linear(cd)
    """
    return _impute_interpolation(cd, kind='linear', extrapolate=extrapolate)


def impute_cubic(cd, extrapolate=True):
    """
    Impute missing coordinates using cubic spline interpolation.

    Parameters
    ----------
    cd : ChromData
        Input ChromData with missing coordinates (NaN values).
    extrapolate : bool, default True
        Whether to extrapolate values outside the range of known coordinates.

    Returns
    -------
    ChromData
        ChromData with cubic-spline interpolated coordinates.

    Examples
    --------
    >>> cd_imputed = impute_cubic(cd)
    """
    return _impute_interpolation(cd, kind='cubic', extrapolate=extrapolate)


def _impute_interpolation(cd, kind, extrapolate):
    """
    Internal function for scipy-based interpolation.

    Interpolates along the genomic coordinate (start position) for each
    trace independently.
    """
    from uchrom.core import ChromData

    coords_imputed = cd.coords.copy()
    spots = cd.spots.copy()

    # Group by trace_id (and cell_id if present)
    if 'cell_id' in spots.columns:
        group_cols = ['cell_id', 'trace_id', 'chrom']
    else:
        group_cols = ['trace_id', 'chrom']

    for group_keys, group_df in spots.groupby(group_cols, sort=False):
        indices = group_df.index.values

        # Get genomic positions and coordinates
        positions = group_df['start'].values
        group_coords = coords_imputed[indices]

        # Find non-NaN entries
        mask = ~np.isnan(group_coords[:, 0])

        if mask.sum() < 2:
            # Need at least 2 points for interpolation
            continue

        # Interpolate each dimension
        fill_value = 'extrapolate' if extrapolate else np.nan

        try:
            for dim in range(3):
                f = interp1d(
                    positions[mask],
                    group_coords[mask, dim],
                    kind=kind,
                    fill_value=fill_value,
                    bounds_error=False
                )
                coords_imputed[indices, dim] = f(positions)
        except ValueError:
            # Interpolation failed (e.g., all NaN), skip this group
            continue

    # Create new ChromData with imputed coordinates
    result = ChromData(
        coords=coords_imputed,
        spots=cd.spots,
        cells=cd.cells if hasattr(cd, 'cells') else None,
        traces=cd.traces if hasattr(cd, 'traces') else None,
        tracks=cd.tracks if hasattr(cd, 'tracks') else None,
        layers=cd.layers if hasattr(cd, 'layers') else None,
        cellm=cd.cellm if hasattr(cd, 'cellm') else None,
        results=cd.results if hasattr(cd, 'results') else None,
        uns=cd.uns if hasattr(cd, 'uns') else None,
    )

    return result
