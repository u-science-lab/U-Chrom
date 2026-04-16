from pathlib import Path
from uuid import NAMESPACE_DNS, uuid5

import numpy as np
import pandas as pd
from astropy.table import Table
from scipy.spatial import cKDTree

from uchrom.im._base import LocalizationResult, MatrixResult, TraceResult


def _as_dataframe(localizations):
    if isinstance(localizations, LocalizationResult):
        return localizations.table.copy()
    if isinstance(localizations, TraceResult):
        return localizations.table.copy()
    if isinstance(localizations, pd.DataFrame):
        return localizations.copy()
    raise ValueError("Expected a pandas DataFrame or U-Chrom localization/trace result.")


def _trace_id(group_key, cluster_id):
    return str(uuid5(NAMESPACE_DNS, f"trace:{group_key}:{cluster_id}"))


def filter_localizations(localizations, flux_min_3D=None, flux_max_3D=None, **kwargs):
    table = _as_dataframe(localizations)
    if flux_min_3D is not None and "flux" in table:
        table = table[table["flux"] >= float(flux_min_3D)]
    if flux_max_3D is not None and "flux" in table:
        table = table[table["flux"] <= float(flux_max_3D)]
    return table.reset_index(drop=True)


def _global_shift_for_row(global_registration, round_name):
    if global_registration is None or round_name not in global_registration.rounds:
        return np.array([0.0, 0.0, 0.0], dtype=np.float64)
    shift_yx = np.asarray(global_registration.rounds[round_name].shift, dtype=np.float64)
    return np.array([0.0, shift_yx[0], shift_yx[1]], dtype=np.float64)


def _round_name_for_row(row):
    round_name = row.get("round", None)
    if round_name is not None and not (isinstance(round_name, float) and np.isnan(round_name)):
        return str(round_name)
    barcode = row.get("Barcode #", -1)
    if pd.isna(barcode):
        return ""
    try:
        return f"RT{int(barcode)}"
    except (TypeError, ValueError):
        return ""


def _normalize_tolerance_drift(tolerance_drift):
    if tolerance_drift is None:
        return None
    if np.isscalar(tolerance_drift):
        value = float(tolerance_drift)
        return np.array([value, value, value], dtype=np.float64)
    values = np.asarray(tolerance_drift, dtype=np.float64)
    if values.shape != (3,):
        return np.array([3.0, 1.0, 1.0], dtype=np.float64)
    return values


def _local_shift_for_round(local_registration, round_name):
    if local_registration is None or round_name not in local_registration.rounds:
        return None
    return np.asarray(local_registration.rounds[round_name].shift_zyx, dtype=np.float64)


def _local_alignment_table(local_registration):
    if local_registration is None or getattr(local_registration, "table", None) is None:
        return None
    table = pd.DataFrame(local_registration.table).copy()
    if table.empty:
        return None
    required = {"ROI #", "label", "block_i", "block_j", "blockXY", "shift_z", "shift_x", "shift_y"}
    if not required.issubset(table.columns):
        return None
    table["ROI #"] = pd.to_numeric(table["ROI #"], errors="coerce")
    table["block_i"] = pd.to_numeric(table["block_i"], errors="coerce")
    table["block_j"] = pd.to_numeric(table["block_j"], errors="coerce")
    table["blockXY"] = pd.to_numeric(table["blockXY"], errors="coerce")
    for column in ("shift_z", "shift_x", "shift_y"):
        table[column] = pd.to_numeric(table[column], errors="coerce")
    table["label"] = table["label"].astype(str)
    return table.dropna(subset=["ROI #", "block_i", "block_j", "blockXY"])


def _local_alignment_lookup(local_registration):
    table = _local_alignment_table(local_registration)
    if table is None:
        return {}, None

    lookup = {}
    block_size = None
    for _, row in table.iterrows():
        key = (
            int(row["ROI #"]),
            str(row["label"]),
            int(row["block_i"]),
            int(row["block_j"]),
        )
        lookup[key] = np.array(
            [row["shift_z"], row["shift_x"], row["shift_y"]],
            dtype=np.float64,
        )
        if block_size is None:
            block_size = int(row["blockXY"])
    return lookup, block_size


def _roi_for_row(row):
    roi = row.get("ROI #", -1)
    if pd.isna(roi):
        return -1
    try:
        return int(roi)
    except (TypeError, ValueError):
        return -1


def _block_key_for_row(row, round_name, block_size_xy):
    block_i = int(np.floor(float(row["ycentroid"]) / block_size_xy))
    block_j = int(np.floor(float(row["xcentroid"]) / block_size_xy))
    return (_roi_for_row(row), str(round_name), block_i, block_j)


def _pyhim_block_shift_for_row(row, round_name, local_lookup, block_size_xy):
    if block_size_xy is None:
        return None
    return local_lookup.get(_block_key_for_row(row, round_name, block_size_xy))


def _passes_tolerance(shift_zyx, tolerance_drift):
    if shift_zyx is None:
        return False
    if tolerance_drift is None:
        return True
    return bool(np.all(np.abs(shift_zyx) < tolerance_drift))


def register_localizations(
    localizations,
    global_registration=None,
    local_registration=None,
    tolerance_drift=(3, 1, 1),
    remove_uncorrected_localizations=True,
    **kwargs,
):
    table = _as_dataframe(localizations)
    if table.empty:
        return table
    for column in ("xcentroid", "ycentroid", "zcentroid"):
        if column not in table:
            raise ValueError(f"Localization table is missing required column '{column}'.")

    corrected = table.copy()
    local_lookup, block_size_xy = _local_alignment_lookup(local_registration)
    tolerance_drift = _normalize_tolerance_drift(tolerance_drift)
    rows_to_remove = []

    for idx, row in corrected.iterrows():
        round_name = _round_name_for_row(row)
        if local_registration is not None and round_name == getattr(local_registration, "reference", None):
            shift_zyx = np.array([0.0, 0.0, 0.0], dtype=np.float64)
        elif local_lookup:
            shift_zyx = _pyhim_block_shift_for_row(row, round_name, local_lookup, block_size_xy)
            if not _passes_tolerance(shift_zyx, tolerance_drift):
                if remove_uncorrected_localizations:
                    rows_to_remove.append(idx)
                continue
        else:
            local_shift = _local_shift_for_round(local_registration, round_name)
            shift_zyx = (
                local_shift
                if local_shift is not None
                else _global_shift_for_row(global_registration, round_name)
            )
        corrected.at[idx, "zcentroid"] = float(row["zcentroid"] + shift_zyx[0])
        corrected.at[idx, "ycentroid"] = float(row["ycentroid"] + shift_zyx[1])
        corrected.at[idx, "xcentroid"] = float(row["xcentroid"] + shift_zyx[2])
    if rows_to_remove:
        corrected = corrected.drop(index=rows_to_remove)
    return corrected.reset_index(drop=True)


def _cluster_points(points, threshold):
    if len(points) == 0:
        return np.array([], dtype=int)
    if len(points) == 1 or threshold is None or threshold <= 0:
        return np.arange(len(points), dtype=int)
    tree = cKDTree(points)
    pairs = tree.query_pairs(float(threshold))
    parent = np.arange(len(points))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(i, j):
        ri, rj = find(i), find(j)
        if ri != rj:
            parent[rj] = ri

    for i, j in pairs:
        union(i, j)
    roots = [find(i) for i in range(len(points))]
    remap = {root: idx for idx, root in enumerate(sorted(set(roots)))}
    return np.array([remap[root] for root in roots], dtype=int)


def build_traces(
    localizations,
    masks=None,
    method="KDtree",
    distance_threshold_um=1.0,
    pixel_size_xy=1.0,
    pixel_size_z=1.0,
    roi=None,
    **kwargs,
):
    table = _as_dataframe(localizations)
    if table.empty:
        return TraceResult(table=table, method=method)

    traces = table.copy()
    traces["x"] = traces["xcentroid"].astype(float) * float(pixel_size_xy)
    traces["y"] = traces["ycentroid"].astype(float) * float(pixel_size_xy)
    traces["z"] = traces["zcentroid"].astype(float) * float(pixel_size_z)
    if "Spot_ID" not in traces:
        traces["Spot_ID"] = [
            str(uuid5(NAMESPACE_DNS, f"spot:{idx}:{row.Buid}"))
            if "Buid" in traces
            else str(uuid5(NAMESPACE_DNS, f"spot:{idx}"))
            for idx, row in traces.iterrows()
        ]
    if "ROI #" not in traces:
        traces["ROI #"] = -1 if roi is None else int(roi)
    if "Mask_id" not in traces:
        traces["Mask_id"] = traces.get("CellID #", 0)

    trace_ids = pd.Series(index=traces.index, dtype=object)
    group_column = "Mask_id" if "Mask_id" in traces else "CellID #"
    for group_key, group in traces.groupby(group_column, sort=False):
        points = group[["x", "y", "z"]].to_numpy(dtype=float)
        clusters = _cluster_points(points, distance_threshold_um)
        for row_idx, cluster_id in zip(group.index, clusters):
            trace_ids.at[row_idx] = _trace_id(group_key, int(cluster_id))
    traces["Trace_ID"] = trace_ids

    for column, default in (
        ("Chrom", "xxxxx"),
        ("Chrom_Start", 0),
        ("Chrom_End", 999999999),
        ("label", "xxxxxxxxxxxxxxxxxxxx"),
    ):
        if column not in traces:
            traces[column] = default

    ordered = [
        "Spot_ID",
        "Trace_ID",
        "x",
        "y",
        "z",
        "Chrom",
        "Chrom_Start",
        "Chrom_End",
        "ROI #",
        "Mask_id",
        "Barcode #",
        "label",
    ]
    remaining = [column for column in traces.columns if column not in ordered]
    return TraceResult(table=traces[ordered + remaining], method=method)


def build_matrix(traces, pixel_size_xy=1.0, pixel_size_z=1.0, **kwargs):
    table = _as_dataframe(traces)
    if table.empty or "Barcode #" not in table:
        return MatrixResult(
            {
                "PWDscMatrix": np.empty((0, 0), dtype=np.float64),
                "Nmatrix": np.empty((0, 0), dtype=np.float64),
                "uniqueBarcodes": np.empty((0,), dtype=np.int32),
            }
        )

    barcodes = np.array(sorted(table["Barcode #"].dropna().astype(int).unique()))
    index = {barcode: idx for idx, barcode in enumerate(barcodes)}
    n = len(barcodes)
    distances = [[[] for _ in range(n)] for _ in range(n)]

    for _, group in table.groupby("Trace_ID", sort=False):
        by_barcode = group.groupby("Barcode #", sort=False).first()
        for b1, row1 in by_barcode.iterrows():
            for b2, row2 in by_barcode.iterrows():
                i, j = index[int(b1)], index[int(b2)]
                p1 = np.array([row1["x"], row1["y"], row1["z"]], dtype=float)
                p2 = np.array([row2["x"], row2["y"], row2["z"]], dtype=float)
                distances[i][j].append(float(np.linalg.norm(p1 - p2)))

    pwd = np.full((n, n), np.nan, dtype=np.float64)
    nmatrix = np.zeros((n, n), dtype=np.float64)
    for i in range(n):
        for j in range(n):
            values = distances[i][j]
            nmatrix[i, j] = len(values)
            if values:
                pwd[i, j] = float(np.nanmedian(values))

    return MatrixResult(
        {
            "PWDscMatrix": pwd,
            "Nmatrix": nmatrix,
            "uniqueBarcodes": barcodes,
        }
    )


def save_traces(result, out_dir, name="Trace_3D_barcode_KDtree"):
    out_dir = Path(out_dir)
    data_dir = out_dir / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    path = data_dir / f"{name}.ecsv"
    table = result.table if isinstance(result, TraceResult) else result
    Table.from_pandas(table).write(path, format="ascii.ecsv", overwrite=True)
    if isinstance(result, TraceResult):
        result.saved_path = str(path)
        return result
    return str(path)


def save_matrix(result, out_dir, prefix="Trace_3D_barcode_KDtree"):
    out_dir = Path(out_dir)
    data_dir = out_dir / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    matrices = result.matrices if isinstance(result, MatrixResult) else result
    saved = {}
    for name, array in matrices.items():
        path = data_dir / f"{prefix}_{name}.npy"
        np.save(path, array)
        saved[name] = str(path)
    if isinstance(result, MatrixResult):
        result.saved_paths = saved
        return result
    return saved


__all__ = [
    "filter_localizations",
    "register_localizations",
    "build_traces",
    "build_matrix",
    "save_traces",
    "save_matrix",
]
