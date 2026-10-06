"""
Core imputation algorithms for FISH data.

Adapted from SnapFISH-IMPUTE v0.0.2
Original: https://github.com/hyuyu104/SnapFISH-IMPUTE
Author: Hongyu Yu (hongyuyu@unc.edu)
License: MIT

Modifications:
- Removed MPI parallel functions (scatter_row_idxs, simil_mat_parallel, to_target_parallel)
- Kept single-process versions (to_simil_mat, impute_pdist_one_iter)
- This provides the complete non-MPI functionality
- Kept only what uchrom.im.impute uses (resizing and file I/O removed: no scikit-image)
"""

from itertools import combinations
import pandas as pd
import numpy as np

from scipy import stats, interpolate
from scipy.spatial.distance import pdist
from scipy.optimize import minimize

from sklearn.metrics.pairwise import nan_euclidean_distances

from .preprocess import to_dist_mat


class DistDataFrame(pd.DataFrame):
    """extends pd.DataFrame to store pairwise distances."""

    def __init__(self, *args, **kwargs):
        """initialize a DistDataFrame. Convert all column names to str."""
        super().__init__(*args, **kwargs)
        # convert all cell_ids to string
        self.columns = self.columns.astype("str")

    @property
    def _constructor(self):
        """ensures all following operations return DistDataFrame.

        Returns:
            type: DistDataFrame.
        """
        return DistDataFrame

    def kcol(self):
        """returns the names of the information columns.

        Returns:
            np.array: key column names.
        """
        COL = ["region", "bin1", "x1", "bin2", "y1", "y-x", "lmbda", "mu", "var"]
        return np.array([t for t in self.columns if t in COL])

    def vcol(self):
        """returns the names of the chromosomes.

        Returns:
            np.array: value column names.
        """
        COL = ["region", "bin1", "x1", "bin2", "y1", "y-x", "lmbda", "mu", "var"]
        return np.array([t for t in self.columns if t not in COL])

    def to_darr(self, vcol=None):
        """return the value columns as numpy array.

        Args:
            vcol (list, optional): cell_ids. Defaults to None.

        Returns:
            np.ndarray: the pairwise distances.
        """
        if vcol is None:
            return self[self.vcol()].values
        else:
            return self[vcol].values


def to_dist_df(coor_data, ann_df):
    """convert 3D coordinates to pairwise distances.

    Args:
        coor_data (pd.DataFrame): coordinate df with columns chr, cell_id,
        pos, x, y, and z, have NaNs.
        ann_df (pd.DataFrame): annotation file.

    Returns:
        pd.DataFrame: (chr*M)*(5+N).
    """
    coor_dists = coor_data.groupby(["region", "haploid"], sort=False).apply(
        lambda x: pdist(x[["x", "y", "z"]])
    )

    dist_df_ls = []
    for c, sub_ann_df in ann_df.groupby("region", sort=False):
        single_chr_dists = np.stack(coor_dists[c].values).T
        sub_dist_df = pd.DataFrame(
            single_chr_dists, columns=coor_dists[c].index
        )

        comb_cols = sub_ann_df[["pos", "start"]].values
        ann_comb = list(combinations(comb_cols, 2))
        bin_cols = np.stack(ann_comb).reshape((-1, 4))
        sub_bin_df = pd.DataFrame(
            bin_cols, columns=["bin1", "x1", "bin2", "y1"]
        )
        sub_bin_df.insert(0, "region", c)
        sub_bin_df["y-x"] = sub_bin_df["y1"] - sub_bin_df["x1"]

        dist_df_ls.append(
            pd.concat([sub_bin_df, sub_dist_df], axis=1, sort=False)
        )

    dist_df = pd.concat(dist_df_ls, axis=0, sort=False)
    cell_ids = pd.unique(coor_data["haploid"]).tolist()

    sorted_cols = dist_df.columns[: sub_bin_df.shape[1]].tolist() + cell_ids
    dist_df = DistDataFrame(dist_df.loc[:, sorted_cols])

    start1d = ann_df["start"]
    # take the median of all 1D distance between consecutive loci
    median = np.nanmedian(start1d - start1d.shift())
    # the bin size to do normalization
    median = round(median, 2 - len(str(int(median))))
    dist_df["y-x"] = (dist_df["y-x"] // median * median).astype("int")

    return dist_df


def interpolate_coors_scipy(ann_df, coor_df, kind):
    """impute missing 3D coordinates by scipy's interp1d. The independent
    variable is the starting 1D genomic location of each locus.

    Args:
        ann_df (pd.DataFrame): 1D genomic location annotation file.
        coor_df (pd.DataFrame): 3D coodinates data with missing values as NaN.
            Contains chr, cell_id, pos, x, y, and z as columns.
        kind (str): interpolation method, argument passed to scipy's interp1d.

    Returns:
        pd.DataFrame: same shape as coor_df with all missing values filled
            by scipy's interp1d.
    """
    interp_vals = []
    for (im_id, _), df in coor_df.groupby(["region", "haploid"], sort=False):
        x = ann_df[ann_df["region"] == im_id]["start"].values
        y = df[["x", "y", "z"]].values
        nan_filter = ~np.isnan(y[:, 0])
        interp_fxn = interpolate.interp1d(
            x[nan_filter],
            y[nan_filter, :],
            axis=0,
            kind=kind,
            fill_value="extrapolate",
        )
        interp_vals.append(interp_fxn(x))

    interp_vals = np.concatenate(interp_vals)
    interp_coor_df = coor_df.copy()
    interp_coor_df[["x", "y", "z"]] = interp_vals

    return interp_coor_df


def boxcox_by1d(by1d_arr):
    """transform to normal by box-cox transformation and then to N(0,1).

    Args:
        by1d_arr (np.ndarray): rows of normalized pairwise distances.

    Returns:
        np.ndarray, np.ndarray: transformed data, transformed parameters.
    """
    # Make a copy to avoid read-only issues
    by1d_arr = by1d_arr.copy()

    y = by1d_arr[~np.isnan(by1d_arr)]
    lmbda = round(stats.boxcox_normmax(y, method="mle"), 4)
    y_trf = stats.boxcox(y, lmbda=lmbda)

    mu, var = np.mean(y_trf), np.var(y_trf)
    by1d_arr[~np.isnan(by1d_arr)] = (y_trf - mu) / (var**0.5)
    trf_vals = np.tile([lmbda, mu, var], by1d_arr.shape[0]).reshape(-1, 3)

    return by1d_arr, trf_vals


def normalize_pdist_by1d(dist_df):
    """normalize all pairwise distances by
    For each chr:
    1) box-cox transformation for each set of bin pairs with the same
    1D genomic distances
    2) transform all distributions to N(0,1)

    Args:
        dist_df (pd.DataFrame): dist_df of a all chromosomes.

    Returns:
        pd.DataFrame: dist_df-like object with normalized distances.
    """
    dist_df_ls = []
    for c, sub_dist_df in dist_df.groupby("region", sort=False):
        kcol_ls, norm_pdists, trf_val_ls = [], [], []
        for d, df in sub_dist_df.groupby("y-x", sort=False):
            by1d_arr, trf_vals = boxcox_by1d(df.to_darr())
            kcol_ls.append(df[df.kcol()].reset_index(drop=True))
            norm_pdists.append(by1d_arr)
            trf_val_ls.append(trf_vals)

        kcols = pd.concat(kcol_ls, sort=False, ignore_index=True)
        norm_pdists = pd.DataFrame(
            np.concatenate(norm_pdists), columns=sub_dist_df.vcol()
        )
        trf_vals = pd.DataFrame(
            np.concatenate(trf_val_ls), columns=["lmbda", "mu", "var"]
        )
        n_df = DistDataFrame(
            pd.concat([kcols, trf_vals, norm_pdists], sort=False, axis=1)
        )
        n_df = n_df.sort_values(["bin1", "bin2"])
        dist_df_ls.append(n_df)

    return pd.concat(dist_df_ls, ignore_index=True, sort=False)


def inverse_trf(chr_norm_df):
    """inverse transformation, N(0,1) -> N(m, s) -> inv_boxcox.

    Args:
        chr_norm_df (pd.DataFrame): normalized pairwise distances,
            column names: chr, bin1, x1, bin2, y1, lmbda, mu, var
            row names: combination of bin pairs

    Returns:
        pd.DataFrame: same format as chr_norm_df.
    """
    target_mat = chr_norm_df.to_darr()
    l, m, v = np.expand_dims(chr_norm_df[["lmbda", "mu", "var"]].values.T, 2)

    lne0 = np.exp(np.log((target_mat * np.sqrt(v) + m) * l + 1) / l)
    le0 = np.exp(target_mat * np.sqrt(v) + m)
    l_filter = np.repeat(l, target_mat.shape[1], axis=1) == 0

    target_mat_trf = np.where(l_filter, le0, lne0)
    target_df = chr_norm_df.copy()
    target_df[target_df.vcol()] = target_mat_trf
    return target_df


def filter_by_prop(count_ratio, simil_mat, ratio):
    """filter pairwise dissimilarities by NaN proportions.

    Args:
        count_ratio (np.ndarray): N*N NaN ratios
        simil_mat (np.ndarray): N*N pairwise dissimilarities.
        ratio (float): between 0 and 1. Defaults to 0.8.

    Returns:
        np.ndarray: N*N filtered dissimilarities.
    """
    min_r = min(np.nanquantile(count_ratio, 0.99), ratio)
    simil_mat[count_ratio < min_r] = np.nan
    np.fill_diagonal(simil_mat, np.nan)
    return simil_mat


def to_simil_mat(pdist_arr, ratio=0.8):
    """calculate the pairwise similarities from pairwise distances
    with NaN entries. For any two chromosomes, the similarity between
    them is only defined if the number of shared available entries is
    larger than ratio% of the number of available entries in at least
    one chromosome.

    This is the single-process version. For large-scale data, consider
    using external MPI tools.

    Args:
        pdist_arr (np.ndarray): N*M normalized pairwise distances.
        ratio (float): between 0 and 1. Defaults to 0.8.

    Returns:
        np.ndarray: N*N pairiwse similarities.
    """
    count_iter = combinations(np.sum(~np.isnan(pdist_arr), axis=1), 2)
    min_count = np.min(np.array(list(count_iter)), axis=1)
    share_count = pdist(~np.isnan(pdist_arr), lambda u, v: np.sum(u & v))
    count_ratio = to_dist_mat(share_count / min_count)

    simil_mat = nan_euclidean_distances(pdist_arr)
    simil_mat = simil_mat / (pdist_arr.shape[1] ** 0.5)

    return filter_by_prop(count_ratio, simil_mat, ratio)


# MPI functions removed: scatter_row_idxs, simil_mat_parallel, to_target_parallel
# Use single-process versions below for non-MPI environments


def to_target_single_chr(pdist_arr, wr):
    """calculate the target distance matrix for a given chromosome
    based on a nn nearest entries.

    Args:
        pdist_arr (np.ndarray): N*M matrix of normalized pairwise distances.
        wr (np.array): 1*N, weight computed from similarities.

    Returns:
        np.array: 1*M, the predicted pairwise distances for the chromosome.
    """
    expanded_weight = np.repeat(wr.reshape((1, -1)), pdist_arr.shape[1], axis=0)
    expanded_weight[np.isnan(pdist_arr.T)] = 0

    thresh = -np.sort(-expanded_weight, axis=1)[:, 1]
    expanded_weight[expanded_weight <= thresh[:, None]] = 0
    weight = expanded_weight / expanded_weight.sum(axis=1)[:, None]

    pdists_wo_nan = np.where(np.isnan(pdist_arr), 0, pdist_arr)
    target = (weight * pdists_wo_nan.T).sum(-1)

    # entries where all cells with positive weights are NaN
    target[target == 0] = np.nan
    return target


def impute_pdist_one_iter(pdist_arr):
    """construct the predicted pairwise distance matrice.

    This is the single-process version of the imputation iteration.

    Args:
        pdist_arr (np.ndarray): N*M matrix, where
            N: number of chromosomes
            M: number of combination of bins

    Returns:
        np.ndarray, int: N*M predicted values and kernel size.
    """
    simil_mat = to_simil_mat(pdist_arr, ratio=0.8)
    W = np.where(np.isnan(simil_mat), 0, 1 / simil_mat)
    target_pdists = np.array([to_target_single_chr(pdist_arr, w) for w in W])
    return target_pdists


def count_na_in_pdist(pdist_arr):
    """count the total number of NaN entries in pairwise distance
    matrix. Does not count chromosomes with all NaN values.

    Args:
        pdist_arr (np.ndarray): N*M pairwise distances.

    Returns:
        int: number of NaN entries.
    """
    avail_idx = np.sum(~np.isnan(pdist_arr), axis=1) != 0
    return np.sum(np.isnan(pdist_arr[avail_idx]))


def loss_pdist(x, raw_coors, mats):
    """computes the loss by summing the squared difference of pairwise distances.

    Args:
        x (np.array): flattend updated 3D coordinates.
        raw_coors (np.ndarray): K*3, raw 3D coordinates with NaN.
        mats (np.ndarray): 4*K*K, [target, lambda, mu, std].

    Returns:
        float: computed loss.
    """
    upt_coors = raw_coors.copy()
    upt_coors[np.isnan(upt_coors)] = x
    upt_pdist = to_dist_mat(pdist(upt_coors), np.nan)

    # transformed the distances by box-cox and normalization
    trf_upt_pdist = (np.power(upt_pdist, mats[1]) - 1) / mats[1]
    trf_upt_pdist = (trf_upt_pdist - mats[2]) / mats[3]

    # return the sum of squares
    return np.nansum(np.square(trf_upt_pdist - mats[0]))


def jac_pdist(x, raw_coors, mats):
    """computes the Jacobian of the loss function.

    Args:
        x (np.array): flattend updated 3D coordinates.
        raw_coors (np.ndarray): K*3, raw 3D coordinates with NaN.
        mats (np.ndarray): 4*K*K, [target, lambda, mu, std].

    Returns:
        np.array: computed Jacobian, same shape as x.
    """
    upt_coors = raw_coors.copy()
    upt_coors[np.isnan(upt_coors)] = x
    upt_pdist = to_dist_mat(pdist(upt_coors), np.nan)

    # transformed the distances by box-cox and normalization
    trf_upt_pdist = (np.power(upt_pdist, mats[1]) - 1) / mats[1]
    trf_upt_pdist = (trf_upt_pdist - mats[2]) / mats[3]

    # the second part of the Jacobian
    prod_part = np.power(upt_pdist, mats[1] - 2) * (trf_upt_pdist - mats[0])
    prod_part = prod_part * 2 / mats[3]

    num_bins = upt_coors.shape[0]
    # expand the 3D coordinates to 3*K*K to compute pairwise differences
    upt_expand = np.repeat(upt_coors.T, num_bins).reshape((3, num_bins, -1))
    coor_diff = upt_expand.transpose((0, 2, 1)) - upt_coors.T[:, :, None]

    jac = np.nansum(coor_diff * prod_part[None, :, :], axis=1).T
    return jac[np.isnan(raw_coors)]


def recover_3d_coor_single_chr(raw, lnr, fla_mat, trf):
    """recover the 3D coordinates based on a target pairwise
    distance matrix, use the transformed loss.

    Args:
        raw (array): K*3, with NaN values.
        lnr (array): K*3, linear imputed values.
        fla_mat (array): C^n_2, target pairwise distances.
        trf (array): (C^n_2)*3, lmbda, mu, var columns.

    Returns:
        array: same shape as raw, recovered 3D coordinates.
    """
    upt = raw.copy()
    mats = np.stack([to_dist_mat(m, np.nan) for m in [fla_mat, *trf.T]])
    mats[1] = np.where(mats[1] == 0, 1e-4, mats[1])
    mats[3] = np.sqrt(mats[3])
    x = lnr[np.isnan(raw)]
    if x.size > 0:
        upt[np.isnan(upt)] = minimize(
            loss_pdist,
            x,
            args=(raw, mats),
            method="L-BFGS-B",
            jac=jac_pdist,
            options={"disp": False},
        ).x
        # set bins with no available target dists to NaN
        target_nan = np.sum(np.isnan(mats[0]), axis=1)
        upt[target_nan == mats[0].shape[0], :] = np.nan
    return upt
