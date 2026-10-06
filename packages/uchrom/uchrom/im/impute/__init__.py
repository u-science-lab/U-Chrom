"""
FISH data imputation module for uchrom.

This module provides coordinate imputation methods for multiplexed DNA FISH data,
including linear interpolation and the SnapFISH-IMPUTE algorithm.
"""

from ._simple import impute_linear, impute_cubic

# Map import name -> pip package name for SnapFISH-IMPUTE's extra dependencies.
_SNAPFISH_DEPS = {
    "scipy": "scipy",
    "sklearn": "scikit-learn",
    "skimage": "scikit-image",
}


def _missing_snapfish_deps(_import=None):
    """Return the pip names of SnapFISH dependencies that fail to import.

    Parameters
    ----------
    _import : callable, optional
        Import function (defaults to importlib.import_module); injectable for
        testing. Should raise ImportError when the module is unavailable.
    """
    import importlib

    do_import = _import if _import is not None else importlib.import_module
    missing = []
    for mod, pip_name in _SNAPFISH_DEPS.items():
        try:
            do_import(mod)
        except ImportError:
            missing.append(pip_name)
    return missing


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
    '_missing_snapfish_deps',
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
            missing = _missing_snapfish_deps()
            pkgs = " ".join(missing) if missing else "scipy scikit-learn scikit-image"
            raise ImportError(
                "SnapFISH-IMPUTE is unavailable because these packages are "
                f"missing: {', '.join(missing) if missing else 'unknown'}.\n"
                f"Install with: pip install {pkgs}\n\n"
                "For small datasets, you can use method='linear' or 'cubic'"
            )
        return impute_snapfish(cd, **kwargs)
    else:
        raise ValueError(
            f"Unknown imputation method: {method}\n"
            f"Available methods: 'linear', 'cubic'" +
            (", 'snapfish'" if SNAPFISH_AVAILABLE else "")
        )
