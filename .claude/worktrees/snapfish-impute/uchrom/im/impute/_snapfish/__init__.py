"""
SnapFISH-IMPUTE: Imputation for multiplexed DNA FISH data.

Adapted from: https://github.com/hyuyu104/SnapFISH-IMPUTE (v0.0.2)
Original author: Hongyu Yu (hongyuyu@unc.edu)
License: MIT (see LICENSE file in this directory)

This module contains the core algorithms from SnapFISH-IMPUTE, adapted for
use with uchrom's ChromData structure. The following modifications have been made:
- Removed MPI parallel functions (parallel.py completely removed)
- Removed visualization dependencies (matplotlib, seaborn)
- Fixed code quality issues (regex warnings, type hints)
- Adapted for ChromData integration
"""

from .impute import (
    interpolate_coors_scipy,
    to_dist_df,
    normalize_pdist_by1d,
    to_simil_mat,
    impute_pdist_one_iter,
    inverse_trf,
    recover_3d_coor_single_chr,
    count_na_in_pdist,
    DistDataFrame,
)

from .preprocess import (
    read_data,
    to_dist_mat,
)

__all__ = [
    'interpolate_coors_scipy',
    'to_dist_df',
    'normalize_pdist_by1d',
    'to_simil_mat',
    'impute_pdist_one_iter',
    'inverse_trf',
    'recover_3d_coor_single_chr',
    'count_na_in_pdist',
    'DistDataFrame',
    'read_data',
    'to_dist_mat',
]
