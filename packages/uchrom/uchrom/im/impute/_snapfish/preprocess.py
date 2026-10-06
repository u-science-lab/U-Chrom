"""
Data preprocessing utilities for FISH imputation.

Adapted from SnapFISH-IMPUTE v0.0.2
Original: https://github.com/hyuyu104/SnapFISH-IMPUTE
Author: Hongyu Yu (hongyuyu@unc.edu)
License: MIT

Modifications:
- Removed matplotlib/seaborn visualization dependencies
- Fixed regex escape sequence warnings
- Removed heatmap_wrapper() and row_heatmap() functions
- Kept only what uchrom.im.impute uses (file readers / writers and resizing removed)
"""

from itertools import combinations

import pandas as pd
import numpy as np


def to_dist_mat(d, fill_val=0.0):
    """convert a 1-D distance vector to matrix.

    Args:
        d (np.array): 1-D pairwise distances.
        fill_val (float): values to fill the diagonal. Defaults to 0.0.

    Returns:
        arr: K*K dimension matrix.
    """
    num_ids = int((1 + (1 + 8 * len(d)) ** 0.5) / 2)
    id_iter = combinations(np.arange(1, num_ids + 1), 2)
    mat_df = pd.DataFrame(list(id_iter), columns=["id1", "id2"])
    mat_df["d"] = d
    dist_vals = pd.pivot_table(mat_df, "d", "id1", "id2", dropna=False).values
    dist_mat = np.diag([fill_val] * num_ids)

    uids = np.triu_indices(num_ids, 1)
    fids = np.triu_indices_from(dist_vals)

    dist_mat[uids] = dist_vals[fids]
    dist_mat.T[uids] = dist_vals[fids]
    return dist_mat

