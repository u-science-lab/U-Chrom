from pathlib import Path
import uuid
import warnings
from uuid import NAMESPACE_DNS, uuid5

import numpy as np
import pandas as pd
from astropy.table import Table
from scipy.spatial import KDTree
from sklearn.metrics import pairwise_distances
from skimage.measure import label as relabel_connected
from skimage.segmentation import expand_labels

from uchrom.im._base import LocalizationResult, MaskResult, MatrixResult, TraceResult


def _as_dataframe(localizations):
    if isinstance(localizations, LocalizationResult):
        return localizations.table.copy()
    if isinstance(localizations, TraceResult):
        return localizations.table.copy()
    if isinstance(localizations, pd.DataFrame):
        return localizations.copy()
    raise ValueError("Expected a pandas DataFrame or U-Chrom localization/trace result.")


def _set_result_meta(result, meta):
    current = getattr(result, "meta", None)
    if current is None:
        current = {}
        result.meta = current
    current.update(meta)
    return result


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


def filter_localizations(localizations, flux_min_3D=None, flux_max_3D=None, **kwargs):
    table = _as_dataframe(localizations)
    if flux_min_3D is not None and "flux" in table:
        table = table[table["flux"] >= float(flux_min_3D)]
    if flux_max_3D is not None and "flux" in table:
        table = table[table["flux"] <= float(flux_max_3D)]
    return table.reset_index(drop=True)


def register_localizations(
    localizations,
    global_registration=None,
    local_registration=None,
    tolerance_drift=(3, 1, 1),
    remove_uncorrected_localizations=True,
    apply_global_registration=False,
    **kwargs,
):
    """
    Apply pyHiM-style local block corrections to globally registered spot coordinates.

    Global registration is assumed to have been applied upstream during 3D localization.
    The optional `apply_global_registration=True` fallback is kept only for explicit
    compatibility calls.
    """
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
        elif (
            local_registration is not None
            and round_name in getattr(local_registration, "rounds", {})
            and round_name != getattr(local_registration, "reference", None)
        ):
            shift_zyx = np.asarray(
                local_registration.rounds[round_name].shift_zyx,
                dtype=np.float64,
            )
        elif apply_global_registration and global_registration is not None:
            shift_yx = np.asarray(
                global_registration.rounds[round_name].shift,
                dtype=np.float64,
            )
            shift_zyx = np.array([0.0, shift_yx[0], shift_yx[1]], dtype=np.float64)
        else:
            shift_zyx = np.array([0.0, 0.0, 0.0], dtype=np.float64)

        corrected.at[idx, "zcentroid"] = float(row["zcentroid"] + shift_zyx[0])
        corrected.at[idx, "ycentroid"] = float(row["ycentroid"] + shift_zyx[1])
        corrected.at[idx, "xcentroid"] = float(row["xcentroid"] + shift_zyx[2])

    if rows_to_remove:
        corrected = corrected.drop(index=rows_to_remove)
    return corrected.reset_index(drop=True)


def _mask_labels(masks, mask_expansion=0):
    if masks is None:
        return None
    labels = masks.labels if isinstance(masks, MaskResult) else np.asarray(masks)
    labels = np.asarray(labels, dtype=np.int32)
    if mask_expansion and int(mask_expansion) > 0:
        labels = expand_labels(labels, distance=int(mask_expansion))
        labels = relabel_connected(labels > 0, connectivity=1).astype(np.int32)
    return labels


def _mask_id_from_labels(labels, row, z_offset=0):
    if labels is None:
        return 0

    x_corrected = float(row["ycentroid"])
    y_corrected = float(row["xcentroid"])
    z_corrected = float(row["zcentroid"]) if "zcentroid" in row else 0.0

    x_int = np.nan if np.isnan(x_corrected) else int(x_corrected)
    y_int = np.nan if np.isnan(y_corrected) else int(y_corrected)
    z_int = np.nan if np.isnan(z_corrected) else int(z_corrected) + int(z_offset)

    if np.isnan(x_int) or np.isnan(y_int) or np.isnan(z_int):
        return 0

    if labels.ndim == 2:
        if 0 < x_int < labels.shape[0] and 0 < y_int < labels.shape[1]:
            return int(labels[x_int, y_int])
        return 0

    if (
        0 < z_int < labels.shape[0]
        and 0 < x_int < labels.shape[1]
        and 0 < y_int < labels.shape[2]
    ):
        return int(labels[z_int, x_int, y_int])
    return 0


def _assign_masks_pyhim(table, masks, mask_expansion=0, z_offset=0):
    labels = _mask_labels(masks, mask_expansion=mask_expansion)
    if labels is None:
        return table

    assigned = table.copy()
    cell_ids = []
    for _, row in assigned.iterrows():
        cell_ids.append(_mask_id_from_labels(labels, row, z_offset=z_offset))
    assigned["CellID #"] = np.asarray(cell_ids, dtype=np.int32)
    assigned["Mask_id"] = assigned["CellID #"]
    return assigned


def _group_localizations_by_coordinate_pyhim(table, distance_threshold_um, pixel_size_xy, pixel_size_z):
    grouped = table.copy()
    grouped["CellID #"] = 0

    for roi_value, roi_group in grouped.groupby("ROI #", sort=False):
        idx = list(roi_group.index)
        if not idx:
            continue

        coordinates = np.column_stack(
            [
                pixel_size_xy * roi_group["xcentroid"].to_numpy(dtype=float),
                pixel_size_xy * roi_group["ycentroid"].to_numpy(dtype=float),
                pixel_size_z * roi_group["zcentroid"].to_numpy(dtype=float),
            ]
        )

        tree = KDTree(coordinates)
        points = [
            tree.query_ball_point(element, float(distance_threshold_um), p=2.0)
            for element in coordinates
        ]
        group_list = [list(group) for group in {tuple(group) for group in points}]

        for trace_id, trace in enumerate(group_list):
            for local_index in trace:
                grouped.at[idx[local_index], "CellID #"] = int(trace_id)

    grouped["Mask_id"] = grouped["CellID #"]
    return grouped


def _spot_uid(row, fallback_idx):
    if "Buid" in row and pd.notna(row["Buid"]):
        return str(row["Buid"])
    return str(uuid5(NAMESPACE_DNS, f"spot:{fallback_idx}"))


def _trace_table_from_groups(table, pixel_size_xy, pixel_size_z):
    traces = table.copy()
    traces["x"] = traces["xcentroid"].astype(float) * float(pixel_size_xy)
    traces["y"] = traces["ycentroid"].astype(float) * float(pixel_size_xy)
    traces["z"] = traces["zcentroid"].astype(float) * float(pixel_size_z)

    if "ROI #" not in traces:
        traces["ROI #"] = 0
    if "Mask_id" not in traces:
        traces["Mask_id"] = traces.get("CellID #", 0)

    output_rows = []
    grouped = traces.groupby("CellID #", sort=False)
    for group_key, group in grouped:
        # pyHiM's builds_sc_distance_table keeps only CellID > 1.
        if int(group_key) <= 1:
            continue

        trace_id = str(uuid.uuid4())
        for fallback_idx, (_, row) in enumerate(group.iterrows()):
            output_rows.append(
                {
                    "Spot_ID": _spot_uid(row, fallback_idx),
                    "Trace_ID": trace_id,
                    "x": float(row["x"]),
                    "y": float(row["y"]),
                    "z": float(row["z"]),
                    "Chrom": "xxxxx",
                    "Chrom_Start": 0,
                    "Chrom_End": 999999999,
                    "ROI #": int(row["ROI #"]),
                    "Mask_id": int(row.get("Mask_id", row.get("CellID #", 0))),
                    "Barcode #": int(row["Barcode #"]),
                    "label": "x" * 20,
                    **{
                        key: row[key]
                        for key in traces.columns
                        if key not in {
                            "x",
                            "y",
                            "z",
                            "Trace_ID",
                            "Spot_ID",
                            "Chrom",
                            "Chrom_Start",
                            "Chrom_End",
                            "Mask_id",
                            "label",
                        }
                    },
                }
            )

    columns = [
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
    trace_table = pd.DataFrame(output_rows)
    if trace_table.empty:
        return trace_table.reindex(columns=columns)
    remaining = [column for column in trace_table.columns if column not in columns]
    return trace_table[columns + remaining]


def build_traces(
    localizations,
    masks=None,
    method="KDtree",
    distance_threshold_um=1.0,
    pixel_size_xy=1.0,
    pixel_size_z=1.0,
    roi=None,
    mask_expansion=0,
    z_offset=0,
    **kwargs,
):
    """
    Build pyHiM-style trace tables from registered localization coordinates.

    Supported methods:
    - `KDtree`: spatial grouping with pyHiM's KDTree query_ball_point workflow
    - `masking`: assign spots to masks and build one trace per mask
    """
    table = _as_dataframe(localizations)
    if table.empty:
        return TraceResult(table=table, method=method)

    traces = table.copy()
    if "ROI #" not in traces:
        traces["ROI #"] = -1 if roi is None else int(roi)

    method_normalized = str(method).lower()
    if method_normalized in {"masking", "mask", "masking_expanded"}:
        traces = _assign_masks_pyhim(
            traces,
            masks=masks,
            mask_expansion=mask_expansion,
            z_offset=z_offset,
        )
    elif method_normalized in {"kdtree", "kdtree_clustering", "clustering"}:
        traces = _group_localizations_by_coordinate_pyhim(
            traces,
            distance_threshold_um=distance_threshold_um,
            pixel_size_xy=float(pixel_size_xy),
            pixel_size_z=float(pixel_size_z),
        )
    else:
        raise ValueError(f"Unsupported trace-building method: {method}")

    trace_table = _trace_table_from_groups(
        traces,
        pixel_size_xy=float(pixel_size_xy),
        pixel_size_z=float(pixel_size_z),
    )
    result = TraceResult(
        table=trace_table.reset_index(drop=True),
        method=method,
    )
    return _set_result_meta(
        result,
        {
            "distance_threshold_um": float(distance_threshold_um),
            "mask_expansion": int(mask_expansion),
        },
    )


def _empty_matrix_result():
    empty_2d = np.empty((0, 0), dtype=np.float64)
    empty_3d = np.empty((0, 0, 0), dtype=np.float64)
    empty_1d = np.empty((0,), dtype=np.int32)
    return MatrixResult(
        {
            "PWDscMatrix": empty_3d,
            "PWDmedianMatrix": empty_2d,
            "Nmatrix": empty_2d,
            "uniqueBarcodes": empty_1d,
        }
    )


def build_matrix(
    traces,
    pixel_size_xy=1.0,
    pixel_size_z=1.0,
    mode="min",
    distance_threshold=np.inf,
    **kwargs,
):
    table = _as_dataframe(traces)
    if table.empty or "Barcode #" not in table or "Trace_ID" not in table:
        return _empty_matrix_result()

    barcodes = np.array(sorted(table["Barcode #"].dropna().astype(int).unique()))
    n_barcodes = len(barcodes)
    n_traces = int(table["Trace_ID"].nunique())
    if n_barcodes == 0 or n_traces == 0:
        return _empty_matrix_result()

    barcode_index = {barcode: idx for idx, barcode in enumerate(barcodes)}
    sc_matrix = np.full((n_barcodes, n_barcodes, n_traces), np.nan, dtype=np.float64)

    for trace_idx, (_, group) in enumerate(table.groupby("Trace_ID", sort=False)):
        barcodes_in_trace = group["Barcode #"].to_numpy(dtype=int)
        xyz = group[["x", "y", "z"]].to_numpy(dtype=float)
        pwd_matrix = pairwise_distances(xyz)

        for i, barcode_1 in enumerate(barcodes_in_trace):
            index_1 = barcode_index[int(barcode_1)]
            for j, barcode_2 in enumerate(barcodes_in_trace):
                if barcode_1 == barcode_2:
                    continue
                new_distance = float(pwd_matrix[i, j])
                if new_distance >= float(distance_threshold):
                    continue
                index_2 = barcode_index[int(barcode_2)]

                current = sc_matrix[index_1, index_2, trace_idx]
                if mode == "last" or np.isnan(current):
                    sc_matrix[index_1, index_2, trace_idx] = new_distance
                elif mode == "mean":
                    sc_matrix[index_1, index_2, trace_idx] = float(
                        np.nanmean([current, new_distance])
                    )
                elif mode == "min":
                    sc_matrix[index_1, index_2, trace_idx] = float(
                        np.nanmin([current, new_distance])
                    )
                else:
                    raise ValueError(f"Unsupported matrix mode: {mode}")

    n_matrix = np.sum(~np.isnan(sc_matrix), axis=2).astype(np.float64)
    if sc_matrix.size:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", category=RuntimeWarning)
            pwd_median = np.nanmedian(sc_matrix, axis=2)
    else:
        pwd_median = np.empty((0, 0))

    result = MatrixResult(
        {
            "PWDscMatrix": sc_matrix,
            "PWDmedianMatrix": np.asarray(pwd_median, dtype=np.float64),
            "Nmatrix": n_matrix,
            "uniqueBarcodes": barcodes.astype(np.int32),
        }
    )
    return _set_result_meta(
        result,
        {
            "mode": str(mode),
            "distance_threshold": float(distance_threshold),
        },
    )


def save_traces(result, out_dir, name="Trace_3D_barcode_KDtree"):
    out_dir = Path(out_dir)
    data_dir = out_dir / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    path = data_dir / f"{name}.ecsv"
    table = result.table if isinstance(result, TraceResult) else result
    Table.from_pandas(pd.DataFrame(table)).write(path, format="ascii.ecsv", overwrite=True)
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
        if name == "uniqueBarcodes":
            path = data_dir / f"{prefix}_{name}.ecsv"
            np.savetxt(path, np.asarray(array, dtype=np.int32), delimiter=" ", fmt="%d")
        else:
            path = data_dir / f"{prefix}_{name}.npy"
            np.save(path, np.asarray(array))
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
