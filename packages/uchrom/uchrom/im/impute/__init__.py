"""
FISH data imputation module for uchrom.

This module provides coordinate imputation methods for multiplexed DNA FISH data,
including linear interpolation and the SnapFISH-IMPUTE algorithm, and a hold-out
test of their accuracy on real traces (:func:`evaluate_imputation`).
"""

from ._simple import impute_linear, impute_cubic
from ._snapfish_core import impute_snapfish
from ._holdout import ImputationHoldout, evaluate_imputation

__all__ = [
    'impute_coordinates',
    'impute_linear',
    'impute_cubic',
    'impute_snapfish',
    'evaluate_imputation',
    'ImputationHoldout',
]


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
        - 'snapfish': SnapFISH-IMPUTE algorithm (scipy / scikit-learn, both core dependencies)
    **kwargs
        Additional arguments passed to the specific imputation method.

    Returns
    -------
    ChromData
        ChromData with imputed coordinates, on the dense (trace x locus) grid of
        each chromosome; the spot column ``imputed`` marks the loci that had no
        coordinate in the input (still NaN where a method could not fill them).

    Raises
    ------
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
        return impute_snapfish(cd, **kwargs)
    else:
        raise ValueError(
            f"Unknown imputation method: {method}\n"
            "Available methods: 'linear', 'cubic', 'snapfish'"
        )
