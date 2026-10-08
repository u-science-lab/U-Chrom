"""Spatial analysis of cells in tissue: neighbour graphs from cell positions, spatial autocorrelation (Moran's
I, Geary's C) and tests of spatial variation (SPARK-X) of per-cell features — 3-D genome features of spatial Hi-C
spots or traced cells — with covariates such as cell-type composition.

    g = uc.spatial.spatial_neighbors(cd, method="radius", radius=1.5)      # 8 adjacent spots of a grid
    uc.spatial.spatial_autocorr(cd, ["contacts.short_long_ratio"], graph=g)
    uc.spatial.spatially_variable(cd, values=features, covariates=composition)   # per section
"""

from .autocorr import bh_adjust, cell_values, spatial_autocorr
from .graph import SpatialGraph, cell_positions_table, spatial_neighbors
from .sparkx import KERNELS, acat, by_adjust, coordinate_kernels, sparkx
from .variable import covariate_matrix, spatially_variable

__all__ = [
    "KERNELS",
    "SpatialGraph",
    "acat",
    "bh_adjust",
    "by_adjust",
    "cell_positions_table",
    "cell_values",
    "coordinate_kernels",
    "covariate_matrix",
    "sparkx",
    "spatial_autocorr",
    "spatial_neighbors",
    "spatially_variable",
]
