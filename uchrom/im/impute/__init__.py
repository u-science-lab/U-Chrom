"""
FISH data imputation module for uchrom.

This module provides coordinate imputation methods for multiplexed DNA FISH data,
including linear interpolation and the SnapFISH-IMPUTE algorithm.
"""

from ._simple import impute_linear, impute_cubic

# Try to import SnapFISH core functions
try:
    from ._snapfish_core import impute_snapfish
    SNAPFISH_AVAILABLE = True
except ImportError:
    SNAPFISH_AVAILABLE = False

__all__ = [
    'impute_coordinates',
    'impute_linear',
    'impute_cubic',
]

if SNAPFISH_AVAILABLE:
    __all__.append('impute_snapfish')


def impute_coordinates(cd, method='linear', **kwargs):
    """
    Impute missing 3D coordinates in ChromData.

    Parameters
    ----------
    cd : ChromData
        Input ChromData with missing coordinates (NaN values).
    method : {'linear', 'cubic', 'snapfish'}, default 'linear'
        Imputation method:
        - 'linear': Linear interpolation (no extra dependencies)
        - 'cubic': Cubic spline interpolation (no extra dependencies)
        - 'snapfish': SnapFISH-IMPUTE algorithm (requires scipy, sklearn, skimage)
    **kwargs
        Additional arguments passed to the specific imputation method.

    Returns
    -------
    ChromData
        ChromData with imputed coordinates.

    Raises
    ------
    ImportError
        If method='snapfish' but required dependencies are not installed.
    ValueError
        If method is not recognized.

    Examples
    --------
    >>> cd = uc.ChromData.from_fofct('data.csv')
    >>> cd_imputed = uc.im.impute.impute_coordinates(cd, method='linear')

    >>> # For SnapFISH-IMPUTE algorithm
    >>> cd_imputed = uc.im.impute.impute_coordinates(
    ...     cd, method='snapfish', max_iter=50, verbose=True
    ... )

    Notes
    -----
    The SnapFISH-IMPUTE algorithm (Yu et al.) uses a similarity-weighted approach
    to impute missing coordinates based on cells with similar conformations.
    For large datasets (>1000 cells), consider using external MPI tools for
    better performance.
    """
    if method == 'linear':
        return impute_linear(cd, **kwargs)
    elif method == 'cubic':
        return impute_cubic(cd, **kwargs)
    elif method == 'snapfish':
        if not SNAPFISH_AVAILABLE:
            raise ImportError(
                "SnapFISH-IMPUTE requires additional dependencies.\n"
                "Install with: pip install scipy scikit-learn scikit-image\n\n"
                "For small datasets (<1000 cells), you can use method='linear' or 'cubic'"
            )
        return impute_snapfish(cd, **kwargs)
    else:
        raise ValueError(
            f"Unknown imputation method: {method}\n"
            f"Available methods: 'linear', 'cubic'" +
            (", 'snapfish'" if SNAPFISH_AVAILABLE else "")
        )
