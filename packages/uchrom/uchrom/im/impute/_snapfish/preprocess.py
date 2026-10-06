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
"""

import re
from itertools import combinations

import pandas as pd
import numpy as np


def format_fish_data(
    ann: pd.DataFrame,
    data: pd.DataFrame,
    reg_col: str, pos_col: str, s1d_col: str, e1d_col: str,
    grp_cols: str,
    extra_col: list
):
    """format multiplexed DNA FISH data.

    Args:
        ann (pd.DataFrame): 1D genomic location annotation file.
        data (pd.DataFrame): 3D coordinates.
        reg_col (str): column name, imaging region of interest.
        pos_col (str): column name, locus ID, unique within each region.
        s1d_col (str): column name, the starting 1D genomic location.
        e1d_col (str): column name, the ending 1D genomic location.
        grp_cols (list): column names that determine a unique haploid.
        extra_col (list): extra columns to include in the output.

    Returns:
        (pd.DataFrame, pd.DataFrame): processed annotation and data.
    """
    type_dict = {reg_col: str, pos_col: str, s1d_col: int, e1d_col: int}
    ann = ann.astype(type_dict)

    # ensure data has region column
    if reg_col not in data.columns:
        pos_to_reg_map = pd.Series(ann[reg_col].values, index=ann[pos_col])
        data[reg_col] = data[pos_col].map(pos_to_reg_map)
    data = data.astype(
        {k: v for k, v in type_dict.items() if k in data.columns}
    )

    ann_by_1d = (
        ann.groupby(reg_col, sort=False)
        .apply(lambda df: df.sort_values(e1d_col))
        .reset_index(drop=True)
    )
    # pos starts from 1 in each imaging region
    pos_srs = (
        ann_by_1d.groupby(reg_col, sort=False)
        .apply(lambda df: np.arange(1, len(df) + 1))
        .values
    )
    # new pos numbering
    pos = np.concatenate(pos_srs)
    pos_key = ann_by_1d[reg_col] + "." + ann_by_1d[pos_col]
    # map: original str pos to int pos
    pos_map = pd.Series(pos, index=pos_key.values)

    # rename the columns of the annotation file
    ann_by_1d["pos"] = pos_key.map(pos_map)
    kept_ann = ann_by_1d.rename(
        {reg_col: "region", s1d_col: "start", e1d_col: "end"}, axis=1
    )
    final_ann = kept_ann[["region", "pos", "start", "end"]]

    # convert data's pos to int
    data_pos_key = data[reg_col] + "." + data[pos_col]
    data["pos"] = data_pos_key.map(pos_map)

    data["region"] = data[reg_col]

    # keep only one 3D coordinate for each id
    unique_cols = grp_cols + ["region", "pos"]
    kept_rows = (
        data.groupby(unique_cols, sort=False).head(1).reset_index(drop=True)
    )

    # sort the dataframe
    vals = pd.unique(ann[reg_col])
    chr_map = pd.Series(np.arange(len(vals)), index=vals)
    # encode regions to ensure they are in the same order
    kept_rows["int_" + reg_col] = kept_rows["region"].map(chr_map)
    for c in grp_cols:
        vals = pd.unique(kept_rows[c])
        int_map = pd.Series(np.arange(len(vals)), index=vals)
        kept_rows["int_" + c] = kept_rows[c].map(int_map)
    sort_cols = ["int_" + reg_col] + ["int_" + c for c in grp_cols] + ["pos"]
    kept_rows = kept_rows.sort_values(sort_cols, ignore_index=True)

    # generate unique haploid chromatin ID
    c = grp_cols[0]
    chr_id = c + "." + kept_rows[c].astype("str")
    for c in grp_cols[1:]:
        chr_id += f".{c}." + kept_rows[c].astype("str")
    kept_rows["haploid"] = chr_id

    kept_cols = ["region", "haploid", "pos", "x", "y", "z"] + extra_col
    final_data = kept_rows[kept_cols]
    return final_ann, final_data


def read_4dn_csv(data_path: str, trace_cols: list):
    """read data downloaded from 4DN data portal.

    Args:
        data_path (str): the local file path of the data.
        trace_cols (list): the name of each part after splitting trace_id
            by "_".

    Returns:
        (pd.DataFrame, pd.DataFrame): processed annotation and data.
    """
    info_lines = []
    with open(data_path, "r") as f:
        line = f.readline()
        while line.startswith("#") or line.startswith('"'):
            info_lines.append(line)
            line = f.readline()
    # Fixed: use raw string for regex
    col_str = re.sub(r"^.*\((.*)\).*$", r"\g<1>", info_lines[-1]).strip().lower()
    data = pd.read_csv(
        data_path, skiprows=len(info_lines), names=col_str.split(",")
    )

    pre_ann = data[["chrom", "chrom_start", "chrom_end"]].drop_duplicates(
        ["chrom", "chrom_start"], ignore_index=True
    )

    ann = (
        pre_ann.groupby("chrom", sort=False, as_index=False)
        .apply(lambda df: df.sort_values("chrom_start").reset_index(drop=True))
        .reset_index(level=1)
        .rename({"level_1": "pos"}, axis=1)
        .reset_index(drop=True)
    )

    ann["pos"] = ann["pos"] + 1

    spl_trace = data["trace_id"].str.split("_").values
    data[trace_cols] = np.stack(spl_trace)

    pos_key = (
        data["chrom"].astype("str") + "." + data["chrom_start"].astype("str")
    )
    pos_map = pd.Series(
        data=ann["pos"].values,
        index=ann["chrom"].astype("str")
        + "."
        + ann["chrom_start"].astype("str"),
    )
    data["pos"] = pos_key.map(pos_map)

    return ann, data


def fill_missing_by_nan(data: pd.DataFrame, ann: pd.DataFrame):
    """insert missing rows to data with 3D coordinates replaced by np.nan.

    Args:
        data (pd.DataFrame): processed data from format_fish_data.
        ann (pd.DataFrame): processed annotation file from format_fish_data.

    Returns:
        pd.DataFrame: processed data with missing 3D coordinates.
    """
    inserted_nan = []
    default_cols = ["region", "haploid", "pos", "x", "y", "z"]
    rep_cols = data.columns.drop(default_cols[2:])
    for reg_id, df in data.groupby("region", sort=False):
        sub_ann = ann[ann["region"] == reg_id]
        num_loci = len(sub_ann)
        num_chrs = len(pd.unique(df["haploid"]))

        rep_vals = df.groupby("haploid", sort=False).head(1)[rep_cols]
        full_other_cols = np.repeat(rep_vals.values, num_loci, axis=0)
        full_pos = np.tile(sub_ann["pos"], num_chrs)

        full_df = pd.DataFrame(full_other_cols, columns=rep_cols)
        full_df["pos"] = full_pos
        full_df = full_df.merge(
            df[default_cols], how="left", on=default_cols[:3], sort=False
        )
        inserted_nan.append(full_df)

    exp_data = pd.concat(inserted_nan, sort=False, ignore_index=True)
    exp_data = exp_data[data.columns]
    return exp_data


def read_data(path):
    """read 3D coordinates/pairwise distances files. Convert imaging region
    and cell ID columns to strings.

    Args:
        path (str): file path.

    Returns:
        pd.DataFrame: data read from the file path.
    """
    dtype_dict = {"region": "str", "haploid": "str", "pos": "int"}
    data = pd.read_csv(path, sep="\t")

    shared_type = {k: v for k, v in dtype_dict.items() if k in data.columns}
    data = data.astype(shared_type)

    return data


def save_coor(save_coor_df, raw_coor_path, save_path):
    """save imputed 3D coordinates. Automatically round the 3D coordinates
    to the precision of the input file.

    Args:
        save_coor_df (pd.DataFrame): the dataframe to save.
        raw_coor_path (pd.DataFrame): the raw 3D coordinates path.
        save_path (str): path to save the file.
    """
    raw_as_str = pd.read_csv(raw_coor_path, dtype="str", sep="\t")
    for coor_name in ["x", "y", "z"]:
        str_col = raw_as_str[coor_name].astype("str")
        precs = str_col.str.replace(r"^[^\.]+\.?", "").str.len()
        prec = np.max(precs)

        save_coor_df[coor_name] = save_coor_df[coor_name].round(prec)

    save_coor_df.to_csv(save_path, sep="\t", index=False)


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


def to_double_dist_mat(val1, val2):
    """upper right is val1, lower left is val2.

    Args:
        val1 (array): the first pairwise distance matrix.
        val2 (array): the second pairwise distance matrix.

    Returns:
        array: K*K matrix.
    """
    mat = to_dist_mat(val1)
    mat[np.tril_indices_from(mat)] = to_dist_mat(val2)[
        np.tril_indices_from(mat)
    ]
    return mat
