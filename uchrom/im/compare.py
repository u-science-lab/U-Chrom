from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.ndimage import shift as shift_image
from scipy.optimize import linear_sum_assignment
from skimage import color, exposure


def first_existing(*paths):
    for path in paths:
        path = Path(path)
        if path.exists():
            return path
    return None


def read_ecsv(path):
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(path)
    try:
        from astropy.table import Table
    except ImportError as exc:
        raise ImportError("Reading pyHiM ECSV/dat tables requires astropy.") from exc
    return Table.read(path, format="ascii.ecsv").to_pandas()


def finite_array_metrics(reference, candidate):
    reference = np.asarray(reference)
    candidate = np.asarray(candidate)
    metrics = {
        "shape_reference": reference.shape,
        "shape_candidate": candidate.shape,
        "dtype_reference": str(reference.dtype),
        "dtype_candidate": str(candidate.dtype),
    }
    if reference.shape != candidate.shape:
        metrics["shape_match"] = False
        return metrics

    ref = reference.astype(float, copy=False)
    cand = candidate.astype(float, copy=False)
    finite = np.isfinite(ref) & np.isfinite(cand)
    metrics["shape_match"] = True
    metrics["finite_fraction"] = float(finite.mean())
    metrics["exact_equal"] = bool(np.array_equal(reference, candidate))
    if not finite.any():
        return metrics

    diff = cand[finite] - ref[finite]
    ref_f = ref[finite]
    cand_f = cand[finite]
    rmse = float(np.sqrt(np.mean(diff**2)))
    ref_range = np.nanmax(ref_f) - np.nanmin(ref_f)
    metrics.update(
        {
            "max_abs_diff": float(np.max(np.abs(diff))),
            "mean_abs_diff": float(np.mean(np.abs(diff))),
            "rmse": rmse,
            "nrmse_by_ref_range": float(rmse / ref_range) if ref_range else np.nan,
            "pearson": (
                float(np.corrcoef(ref_f, cand_f)[0, 1])
                if ref_f.size > 1 and np.std(ref_f) > 0 and np.std(cand_f) > 0
                else np.nan
            ),
        }
    )
    return metrics


def display_plane(array, z=None, projection="max"):
    array = np.asarray(array)
    if array.ndim == 2:
        return array
    if array.ndim != 3:
        raise ValueError(f"Expected 2D or 3D array, got {array.shape}")
    if z is not None:
        return array[int(z)]
    if projection == "sum":
        return np.sum(array, axis=0)
    return np.max(array, axis=0)


def show_array_comparison(reference, candidate, title="", z=None, projection="max", cmap="gray"):
    if np.asarray(reference).shape != np.asarray(candidate).shape:
        print(
            "Cannot plot difference for shape mismatch: "
            f"{np.asarray(reference).shape} vs {np.asarray(candidate).shape}"
        )
        return None
    ref = display_plane(reference, z=z, projection=projection)
    cand = display_plane(candidate, z=z, projection=projection)
    diff = cand.astype(float) - ref.astype(float)
    abs_diff = np.abs(diff)
    finite_signal = np.concatenate(
        [
            ref[np.isfinite(ref)].astype(float).ravel(),
            cand[np.isfinite(cand)].astype(float).ravel(),
        ]
    )
    if finite_signal.size:
        vmin, vmax_signal = np.nanpercentile(finite_signal, [1, 99.8])
        if vmax_signal <= vmin:
            vmin, vmax_signal = float(np.nanmin(finite_signal)), float(np.nanmax(finite_signal))
    else:
        vmin, vmax_signal = None, None
    diff_vmax = np.nanpercentile(abs_diff, 99.5) if np.isfinite(abs_diff).any() else 1
    max_abs_diff = np.nanmax(abs_diff) if np.isfinite(abs_diff).any() else np.nan
    if diff_vmax == 0:
        diff_vmax = 1
    fig, axes = plt.subplots(1, 3, figsize=(15, 4))
    axes[0].imshow(ref, cmap=cmap, vmin=vmin, vmax=vmax_signal)
    axes[0].set_title("pyHiM")
    axes[1].imshow(cand, cmap=cmap, vmin=vmin, vmax=vmax_signal)
    axes[1].set_title("U-Chrom")
    diff_image = axes[2].imshow(abs_diff, cmap="magma", vmin=0, vmax=diff_vmax)
    axes[2].set_title(f"|U-Chrom - pyHiM|\nmax={max_abs_diff:.3g}")
    for ax in axes:
        ax.axis("off")
    fig.colorbar(diff_image, ax=axes[2], fraction=0.046, pad=0.04)
    fig.suptitle(title)
    plt.tight_layout()
    return fig


def mask_summary(name, mask):
    mask = np.asarray(mask)
    labels = np.unique(mask)
    labels_fg = labels[labels != 0]
    return {
        "name": name,
        "shape": mask.shape,
        "dtype": str(mask.dtype),
        "objects": int(len(labels_fg)),
        "max_label": int(np.max(mask)) if mask.size else 0,
        "foreground_px": int(np.count_nonzero(mask)),
        "foreground_fraction": float(np.count_nonzero(mask) / mask.size)
        if mask.size
        else np.nan,
    }


def foreground_scores(reference_mask, candidate_mask):
    reference_mask = np.asarray(reference_mask)
    candidate_mask = np.asarray(candidate_mask)
    if reference_mask.shape != candidate_mask.shape:
        return {
            "shape_match": False,
            "shape_reference": reference_mask.shape,
            "shape_candidate": candidate_mask.shape,
        }
    ref = reference_mask > 0
    cand = candidate_mask > 0
    inter = np.logical_and(ref, cand).sum()
    union = np.logical_or(ref, cand).sum()
    return {
        "shape_match": True,
        "foreground_iou": float(inter / union) if union else 1.0,
        "dice": float(2 * inter / (ref.sum() + cand.sum()))
        if (ref.sum() + cand.sum())
        else 1.0,
        "recall_vs_pyhim": float(inter / ref.sum()) if ref.sum() else 1.0,
        "precision_vs_uchrom": float(inter / cand.sum()) if cand.sum() else 1.0,
        "pyhim_foreground_px": int(ref.sum()),
        "uchrom_foreground_px": int(cand.sum()),
    }


def label_iou_matches(reference_mask, candidate_mask):
    reference_mask = np.asarray(reference_mask, dtype=np.int64)
    candidate_mask = np.asarray(candidate_mask, dtype=np.int64)
    if reference_mask.shape != candidate_mask.shape:
        raise ValueError(
            f"shape mismatch: pyHiM {reference_mask.shape}, U-Chrom {candidate_mask.shape}"
        )

    ref_ids = np.unique(reference_mask)
    ref_ids = ref_ids[ref_ids != 0]
    cand_ids = np.unique(candidate_mask)
    cand_ids = cand_ids[cand_ids != 0]
    if len(ref_ids) == 0 or len(cand_ids) == 0:
        return pd.DataFrame()

    n_cand = int(candidate_mask.max()) + 1
    encoded = reference_mask.ravel() * n_cand + candidate_mask.ravel()
    overlap = np.bincount(
        encoded,
        minlength=(int(reference_mask.max()) + 1) * n_cand,
    ).reshape(int(reference_mask.max()) + 1, n_cand)
    ref_area = np.bincount(reference_mask.ravel(), minlength=int(reference_mask.max()) + 1)
    cand_area = np.bincount(candidate_mask.ravel(), minlength=n_cand)

    iou = np.zeros((len(ref_ids), len(cand_ids)), dtype=float)
    for i, ref_id in enumerate(ref_ids):
        inter = overlap[ref_id, cand_ids]
        union = ref_area[ref_id] + cand_area[cand_ids] - inter
        iou[i] = np.where(union > 0, inter / union, 0)

    row_ind, col_ind = linear_sum_assignment(-iou)
    rows = []
    for r, c in zip(row_ind, col_ind):
        ref_id = int(ref_ids[r])
        cand_id = int(cand_ids[c])
        inter = int(overlap[ref_id, cand_id])
        union = int(ref_area[ref_id] + cand_area[cand_id] - inter)
        rows.append(
            {
                "pyhim_label": ref_id,
                "uchrom_label": cand_id,
                "iou": float(iou[r, c]),
                "intersection_px": inter,
                "union_px": union,
                "pyhim_area": int(ref_area[ref_id]),
                "uchrom_area": int(cand_area[cand_id]),
                "area_ratio_uchrom_over_pyhim": (
                    float(cand_area[cand_id] / ref_area[ref_id])
                    if ref_area[ref_id]
                    else np.nan
                ),
            }
        )
    return pd.DataFrame(rows).sort_values("iou")


def show_mask_overlay(reference_image, pyhim_mask, uchrom_mask, title="", z=None):
    if np.asarray(pyhim_mask).shape != np.asarray(uchrom_mask).shape:
        print(
            "Cannot overlay masks with shape mismatch: "
            f"{np.asarray(pyhim_mask).shape} vs {np.asarray(uchrom_mask).shape}"
        )
        return None
    base = display_plane(reference_image, z=z).astype(float)
    lo, hi = np.nanpercentile(base, [1, 99]) if np.isfinite(base).any() else (0, 1)
    base = np.clip((base - lo) / (hi - lo + 1e-12), 0, 1)
    py = display_plane(pyhim_mask > 0, z=z).astype(bool)
    uc = display_plane(uchrom_mask > 0, z=z).astype(bool)
    rgb = np.dstack([base, base, base])
    rgb[py & ~uc] = [1, 0, 0]
    rgb[uc & ~py] = [0, 1, 0]
    rgb[py & uc] = [1, 1, 0]
    fig, ax = plt.subplots(figsize=(7, 7))
    ax.imshow(rgb)
    ax.set_title(title + " | red=pyHiM only, green=U-Chrom only, yellow=overlap")
    ax.axis("off")
    return fig


def _display_ready_image(image):
    image = np.asarray(image, dtype=float)
    finite = image[np.isfinite(image)]
    if finite.size == 0:
        return np.zeros_like(image, dtype=float)
    lo, hi = np.nanpercentile(finite, [1, 99.5])
    if hi <= lo:
        lo, hi = float(np.nanmin(finite)), float(np.nanmax(finite))
    return np.clip((image - lo) / (hi - lo + 1e-12), 0, 1)


def show_mask_segmentation_qc(raw_image, labels, title="", crop=None):
    """
    pyHiM-style mask QC: mean raw projection next to max-projected labels.
    """
    raw = np.asarray(raw_image)
    label_array = np.asarray(labels)
    raw_projection = np.mean(raw, axis=0) if raw.ndim == 3 else raw
    label_projection = np.max(label_array, axis=0) if label_array.ndim == 3 else label_array
    raw_projection = _display_ready_image(raw_projection)
    if crop is not None:
        raw_projection = _crop_abs(raw_projection, crop)
        label_projection = _crop_abs(label_projection, crop)

    label_rgb = color.label2rgb(
        label_projection.astype(int),
        bg_label=0,
        bg_color=(0, 0, 0),
        alpha=1.0,
    )
    fig, axes = plt.subplots(1, 2, figsize=(12, 6))
    axes[0].imshow(raw_projection, cmap="gray", origin="lower")
    axes[0].set_title("raw image")
    axes[1].imshow(label_rgb, origin="lower")
    axes[1].set_title("projected labeled image")
    for axis in axes:
        axis.set_xticks([])
        axis.set_yticks([])
    fig.suptitle(title)
    fig.tight_layout()
    return fig


def normalize_localization_table(table):
    table = pd.DataFrame(table).copy()
    columns = [
        "ROI #",
        "Barcode #",
        "id",
        "zcentroid",
        "xcentroid",
        "ycentroid",
        "flux",
        "peak",
        "npix",
    ]
    for column in columns:
        if column in table.columns:
            table[column] = pd.to_numeric(table[column], errors="coerce")
    return table


def localization_count_summary(pyhim_locs, uchrom_locs):
    py = normalize_localization_table(pyhim_locs)
    uc = normalize_localization_table(uchrom_locs)
    totals = pd.DataFrame(
        [
            {"source": "pyHiM", "n_localizations": len(py)},
            {"source": "U-Chrom", "n_localizations": len(uc)},
        ]
    )
    if "Barcode #" not in py or "Barcode #" not in uc:
        return totals, pd.DataFrame()
    counts = pd.concat(
        [
            py.groupby("Barcode #").size().rename("pyHiM"),
            uc.groupby("Barcode #").size().rename("U-Chrom"),
        ],
        axis=1,
    ).fillna(0).astype(int)
    return totals, counts


def match_localizations_by_position(pyhim_locs, uchrom_locs, max_distance_px=None):
    py = normalize_localization_table(pyhim_locs).reset_index().rename(
        columns={"index": "pyhim_index"}
    )
    uc = normalize_localization_table(uchrom_locs).reset_index().rename(
        columns={"index": "uchrom_index"}
    )
    required = ["ROI #", "Barcode #", "zcentroid", "xcentroid", "ycentroid"]
    for column in required:
        if column not in py.columns or column not in uc.columns:
            raise ValueError(f"Missing localization column: {column}")

    matches = []
    for key, py_group in py.groupby(["ROI #", "Barcode #"], dropna=False):
        uc_group = uc[(uc["ROI #"] == key[0]) & (uc["Barcode #"] == key[1])]
        if py_group.empty or uc_group.empty:
            continue
        py_points = py_group[["zcentroid", "xcentroid", "ycentroid"]].to_numpy(
            dtype=float
        )
        uc_points = uc_group[["zcentroid", "xcentroid", "ycentroid"]].to_numpy(
            dtype=float
        )
        distances = np.linalg.norm(py_points[:, None, :] - uc_points[None, :, :], axis=2)
        row_ind, col_ind = linear_sum_assignment(distances)
        for r, c in zip(row_ind, col_ind):
            distance = float(distances[r, c])
            if max_distance_px is not None and distance > max_distance_px:
                continue
            py_row = py_group.iloc[r]
            uc_row = uc_group.iloc[c]
            matches.append(
                {
                    "ROI #": key[0],
                    "Barcode #": key[1],
                    "pyhim_index": int(py_row["pyhim_index"]),
                    "uchrom_index": int(uc_row["uchrom_index"]),
                    "distance_px": distance,
                    "dz": float(uc_row["zcentroid"] - py_row["zcentroid"]),
                    "dx": float(uc_row["xcentroid"] - py_row["xcentroid"]),
                    "dy": float(uc_row["ycentroid"] - py_row["ycentroid"]),
                }
            )
    matches = pd.DataFrame(matches)
    summary = {
        "pyhim_total": len(py),
        "uchrom_total": len(uc),
        "matched": int(len(matches)),
        "pyhim_match_rate": float(len(matches) / len(py)) if len(py) else np.nan,
        "uchrom_match_rate": float(len(matches) / len(uc)) if len(uc) else np.nan,
        "median_distance_px": (
            float(matches["distance_px"].median()) if len(matches) else np.nan
        ),
        "p95_distance_px": (
            float(matches["distance_px"].quantile(0.95)) if len(matches) else np.nan
        ),
    }
    return matches, summary


def plot_localization_xy(pyhim_locs, uchrom_locs, barcode=None, title=""):
    py = normalize_localization_table(pyhim_locs)
    uc = normalize_localization_table(uchrom_locs)
    if barcode is not None:
        py = py[py["Barcode #"] == barcode]
        uc = uc[uc["Barcode #"] == barcode]
    fig, ax = plt.subplots(figsize=(7, 7))
    ax.scatter(
        py["xcentroid"],
        py["ycentroid"],
        s=18,
        facecolors="none",
        edgecolors="tab:red",
        label="pyHiM",
    )
    ax.scatter(
        uc["xcentroid"],
        uc["ycentroid"],
        s=12,
        alpha=0.6,
        color="tab:green",
        label="U-Chrom",
    )
    ax.set_aspect("equal")
    ax.invert_yaxis()
    ax.set_xlabel("xcentroid [px]")
    ax.set_ylabel("ycentroid [px]")
    ax.set_title(title)
    ax.legend()
    return fig


def show_barcode_localization_qc(
    image,
    localizations,
    barcode=None,
    title="",
    projection="sum",
    crop=None,
    color_by="Barcode #",
    spot_size=18,
):
    """
    Show barcode localizations over a 2D projection of the corresponding 3D image.
    """
    table = normalize_localization_table(localizations)
    if barcode is not None and "Barcode #" in table:
        table = table[table["Barcode #"] == barcode]

    base = display_plane(image, projection=projection)
    base = _display_ready_image(base)
    y_offset = 0
    x_offset = 0
    if crop is not None:
        y0, y1, x0, x1 = crop
        base = _crop_abs(base, crop)
        y_offset = y0
        x_offset = x0
        table = table[
            (table["ycentroid"] >= y0)
            & (table["ycentroid"] < y1)
            & (table["xcentroid"] >= x0)
            & (table["xcentroid"] < x1)
        ]

    fig, ax = plt.subplots(figsize=(9, 9))
    ax.imshow(base, cmap="gray", origin="lower")
    if not table.empty:
        if color_by in table:
            values = pd.to_numeric(table[color_by], errors="coerce")
            unique_values = sorted(values.dropna().unique())
            cmap = plt.get_cmap("hsv", max(len(unique_values), 1))
            color_map = {value: cmap(i) for i, value in enumerate(unique_values)}
            colors = [color_map.get(value, (1, 1, 0, 1)) for value in values]
        else:
            colors = "yellow"
        ax.scatter(
            table["xcentroid"] - x_offset,
            table["ycentroid"] - y_offset,
            s=spot_size,
            facecolors="none",
            edgecolors=colors,
            linewidths=1.0,
            alpha=0.9,
        )
    ax.set_title(title)
    ax.set_xticks([])
    ax.set_yticks([])
    return fig


def show_localization_match_diagnostics(matches, title=""):
    matches = pd.DataFrame(matches)
    if matches.empty:
        print("No matched localizations to plot.")
        return None
    fig, axes = plt.subplots(2, 2, figsize=(10, 8))
    axes = axes.ravel()
    axes[0].hist(matches["distance_px"].dropna(), bins=30, color="0.3")
    axes[0].set_xlabel("nearest-neighbor distance [px]")
    axes[0].set_ylabel("matched spots")
    for axis, column in zip(axes[1:], ["dz", "dx", "dy"]):
        axis.hist(matches[column].dropna(), bins=30, color="tab:blue", alpha=0.75)
        axis.axvline(0, color="black", linewidth=1)
        axis.set_xlabel(f"{column} = U-Chrom - pyHiM [px]")
        axis.set_ylabel("matched spots")
    fig.suptitle(title)
    fig.tight_layout()
    return fig


def trace_summary(table, source):
    table = pd.DataFrame(table).copy()
    row = {"source": source, "rows": len(table)}
    if "Trace_ID" in table.columns:
        row["unique_traces"] = int(table["Trace_ID"].nunique())
        row["median_spots_per_trace"] = float(table.groupby("Trace_ID").size().median())
    if "Barcode #" in table.columns:
        row["unique_barcodes"] = int(table["Barcode #"].nunique())
    return row


def matrix_metrics(reference_matrix, candidate_matrix):
    reference_matrix = np.asarray(reference_matrix)
    candidate_matrix = np.asarray(candidate_matrix)
    metrics = finite_array_metrics(reference_matrix, candidate_matrix)
    if reference_matrix.shape == candidate_matrix.shape:
        finite = np.isfinite(reference_matrix) & np.isfinite(candidate_matrix)
        metrics["finite_overlap_fraction"] = float(finite.mean())
    return metrics


def show_matrix_comparison(reference_matrix, candidate_matrix, title=""):
    if np.asarray(reference_matrix).shape != np.asarray(candidate_matrix).shape:
        print(
            "Cannot plot matrix comparison for shape mismatch: "
            f"{np.asarray(reference_matrix).shape} vs {np.asarray(candidate_matrix).shape}"
        )
        return None
    return show_array_comparison(reference_matrix, candidate_matrix, title=title, cmap="viridis")


def _crop_abs(image, zoom):
    if zoom is None:
        return image
    y0, y1, x0, x1 = zoom
    if image.ndim == 2:
        return image[y0:y1, x0:x1]
    return image[y0:y1, x0:x1, :]


def _display_ready_registration(image):
    from uchrom.im.reg.register_2d import _image_adjust, _normalize_image

    image = _normalize_image(image)
    image, _, _, _, _ = _image_adjust(
        image,
        lower_threshold=0.5,
        higher_threshold=0.9999,
    )
    return image


def _registration_qc_panels(reference_image, moving_uncorrected, moving_corrected, zoom=None, overlay_gain=5.0):
    ref_disp = _display_ready_registration(reference_image)
    mov_uncorrected_disp = _display_ready_registration(moving_uncorrected)
    mov_corrected_disp = _display_ready_registration(moving_corrected)

    uncorrected = _crop_abs(ref_disp - mov_uncorrected_disp, zoom)
    corrected = _crop_abs(ref_disp - mov_corrected_disp, zoom)
    overlay = _crop_abs(
        np.dstack([ref_disp, mov_corrected_disp, np.zeros_like(ref_disp)]),
        zoom,
    )
    if overlay_gain is not None:
        overlay = np.clip(overlay.astype(np.float32) * overlay_gain, 0, 1)
    return uncorrected, corrected, overlay


def show_registration_qc_comparison(
    uchrom_registration,
    moving_round,
    pyhim_project_data,
    pyhim_register_global_data,
    reference_round=None,
    zoom=(300, 700, 300, 700),
    overlay_gain=5.0,
    background_sigma=3.0,
):
    """
    Compare U-Chrom and pyHiM 2D global registration QC for one moving round.

    Rows are U-Chrom and pyHiM. Columns are uncorrected difference, corrected
    difference, and reference/moving overlay. The pyHiM row is reconstructed
    from pyHiM projected fiducials and registered fiducial output.
    """
    from uchrom.im.reg.register_2d import _preprocess_fiducial

    reference_round = uchrom_registration.reference if reference_round is None else reference_round
    if reference_round not in uchrom_registration.rounds:
        raise ValueError(f"Reference round not found: {reference_round}")
    if moving_round not in uchrom_registration.rounds:
        raise ValueError(f"Moving round not found: {moving_round}")

    reference_result = uchrom_registration.rounds[reference_round]
    moving_result = uchrom_registration.rounds[moving_round]
    if moving_result.moving_preprocessed is None:
        raise ValueError("QC comparison needs a non-reference moving round.")

    uchrom_panels = _registration_qc_panels(
        moving_result.reference_preprocessed,
        moving_result.moving_preprocessed,
        moving_result.moving_preprocessed_shifted,
        zoom=zoom,
        overlay_gain=overlay_gain,
    )

    pyhim_project_data = Path(pyhim_project_data)
    pyhim_register_global_data = Path(pyhim_register_global_data)
    pyhim_reference_path = pyhim_project_data / f"{reference_result.fiducial.name}.npy"
    pyhim_moving_path = pyhim_project_data / f"{moving_result.fiducial.name}.npy"
    pyhim_corrected_path = (
        pyhim_register_global_data / f"{moving_result.fiducial.name}_registered.npy"
    )
    missing = [
        str(path)
        for path in (pyhim_reference_path, pyhim_moving_path, pyhim_corrected_path)
        if not path.exists()
    ]
    if missing:
        raise FileNotFoundError("Missing pyHiM registration inputs:\n" + "\n".join(missing))

    pyhim_reference = _preprocess_fiducial(np.load(pyhim_reference_path), background_sigma)
    pyhim_moving = _preprocess_fiducial(np.load(pyhim_moving_path), background_sigma)
    pyhim_corrected = np.load(pyhim_corrected_path)
    pyhim_panels = _registration_qc_panels(
        pyhim_reference,
        pyhim_moving,
        pyhim_corrected,
        zoom=zoom,
        overlay_gain=overlay_gain,
    )

    fig, axes = plt.subplots(2, 3, figsize=(15, 8), constrained_layout=True)
    column_titles = ["Uncorrected", "Corrected", "Overlay"]
    row_titles = ["U-Chrom", "pyHiM"]

    for row_idx, panels in enumerate([uchrom_panels, pyhim_panels]):
        for col_idx, panel in enumerate(panels):
            axis = axes[row_idx, col_idx]
            if col_idx < 2:
                axis.imshow(
                    panel,
                    cmap="seismic",
                )
            else:
                axis.imshow(panel)
            if row_idx == 0:
                axis.set_title(column_titles[col_idx])
            if col_idx == 0:
                axis.set_ylabel(row_titles[row_idx], fontsize=12)
            axis.set_xticks([])
            axis.set_yticks([])

    fig.suptitle(f"2D global registration QC: {moving_round} vs {reference_round} fiducial")
    return fig, axes


def _contrast_adjust_projection(image):
    from uchrom.im.reg.register_2d import _image_adjust

    image = exposure.rescale_intensity(np.asarray(image), out_range=(0, 1))
    image, _, _, _, _ = _image_adjust(
        image,
        lower_threshold=0.5,
        higher_threshold=0.9999,
    )
    return np.asarray(image, dtype=np.float32)


def _shift_matrices_from_block_table(block_table, block_shape):
    table = pd.DataFrame(block_table)
    required = ["block_i", "block_j", "shift_z", "shift_x", "shift_y"]
    missing = [column for column in required if column not in table.columns]
    if missing:
        raise ValueError(f"Missing local-registration block columns: {missing}")

    shift_matrices = [np.zeros(block_shape[:2], dtype=np.float32) for _ in range(3)]
    for _, row in table.iterrows():
        block_i = int(row["block_i"])
        block_j = int(row["block_j"])
        if block_i >= block_shape[0] or block_j >= block_shape[1]:
            continue
        shift_matrices[0][block_i, block_j] = float(row["shift_z"])
        shift_matrices[1][block_i, block_j] = float(row["shift_x"])
        shift_matrices[2][block_i, block_j] = float(row["shift_y"])
    return shift_matrices


def _blue_grid(block_sizes):
    blue = np.zeros(block_sizes, dtype=np.float32)
    blue[0, :] = 0.5
    blue[:, 0] = 0.5
    blue[:, -1] = 0.5
    blue[-1, :] = 0.5
    return blue


def _combine_blocks_by_reprojection(block_ref, block_target, shift_matrices, axis):
    block_rows, block_cols = block_ref.shape[:2]
    block_sizes = list(block_ref.shape[2:])
    block_sizes.pop(axis)
    output = np.zeros(
        (block_sizes[0] * block_rows, block_sizes[1] * block_cols, 3),
        dtype=np.float32,
    )
    blue = _blue_grid(tuple(block_sizes))

    for block_i in range(block_rows):
        for block_j in range(block_cols):
            shift_zyx = np.array([matrix[block_i, block_j] for matrix in shift_matrices])
            ref_proj = np.sum(block_ref[block_i, block_j], axis=axis)
            target_proj = np.sum(
                shift_image(block_target[block_i, block_j], shift_zyx),
                axis=axis,
            )
            ref_proj = _contrast_adjust_projection(ref_proj)
            target_proj = _contrast_adjust_projection(target_proj)
            rgb = np.dstack([ref_proj, target_proj, blue])

            y0 = block_i * block_sizes[0]
            y1 = (block_i + 1) * block_sizes[0]
            x0 = block_j * block_sizes[1]
            x1 = (block_j + 1) * block_sizes[1]
            output[y0:y1, x0:x1, :] = rgb
    return output


def _crop_2d_or_rgb(image, crop):
    if crop is None:
        return image
    y0, y1, x0, x1 = crop
    if image.ndim == 2:
        return image[y0:y1, x0:x1]
    return image[y0:y1, x0:x1, :]


def show_local_registration_3d_qc(
    raw_rounds,
    local_registration,
    global_registration=None,
    moving_round="RT27",
    reference_round=None,
    block_size_xy=None,
    z_binning=None,
    lower_threshold=0.9,
    higher_threshold=0.9999,
    block_window=None,
    z_projection_crop=None,
):
    """
    Plot pyHiM-style 3D local-registration QC for one moving round.

    The red channel is the reference fiducial projection, the green channel is
    the moving fiducial after per-block 3D local correction, and blue marks
    block borders. Yellow signal means red/green overlap after correction.
    """
    from uchrom.im.reg.register_local import (
        _apply_xy_shift,
        _as_stack,
        _block_images,
        _global_xy_shift,
        _preprocess_3d_image,
        _reinterpolate_z_remove,
        _round_fiducial,
    )

    reference_round = (
        local_registration.reference if reference_round is None else reference_round
    )
    if reference_round not in raw_rounds:
        raise ValueError(f"Reference round not found: {reference_round}")
    if moving_round not in raw_rounds:
        raise ValueError(f"Moving round not found: {moving_round}")
    if moving_round not in local_registration.rounds:
        raise ValueError(f"Local-registration result missing round: {moving_round}")

    block_table = local_registration.rounds[moving_round].block_table
    if block_table is None or len(block_table) == 0:
        raise ValueError(f"No block table available for round: {moving_round}")
    block_table = pd.DataFrame(block_table)
    if block_size_xy is None:
        if "blockXY" in block_table.columns:
            block_size_xy = int(pd.to_numeric(block_table["blockXY"]).dropna().iloc[0])
        else:
            block_size_xy = 128

    reference_image = _round_fiducial(raw_rounds[reference_round], reference_round)
    moving_image = _round_fiducial(raw_rounds[moving_round], moving_round)
    reference_raw = _reinterpolate_z_remove(
        _as_stack(reference_image, f"{reference_round} fiducial"),
        z_binning,
    )
    moving_raw = _reinterpolate_z_remove(
        _as_stack(moving_image, f"{moving_round} fiducial"),
        z_binning,
    )
    reference_stack = _preprocess_3d_image(
        reference_raw,
        lower_threshold=lower_threshold,
        higher_threshold=higher_threshold,
    )
    moving_stack = _preprocess_3d_image(
        moving_raw,
        lower_threshold=lower_threshold,
        higher_threshold=higher_threshold,
    )
    moving_after_global = _apply_xy_shift(
        moving_stack,
        _global_xy_shift(global_registration, moving_round),
    )
    block_ref, block_target = _block_images(
        reference_stack,
        moving_after_global,
        block_size_xy=block_size_xy,
    )
    shift_matrices = _shift_matrices_from_block_table(block_table, block_ref.shape)
    if block_window is not None:
        row0, row1, col0, col1 = block_window
        block_ref = block_ref[row0:row1, col0:col1]
        block_target = block_target[row0:row1, col0:col1]
        shift_matrices = [matrix[row0:row1, col0:col1] for matrix in shift_matrices]

    z_projection = _combine_blocks_by_reprojection(
        block_ref,
        block_target,
        shift_matrices,
        axis=0,
    )
    x_projection = _combine_blocks_by_reprojection(
        block_ref,
        block_target,
        shift_matrices,
        axis=1,
    )
    y_projection = _combine_blocks_by_reprojection(
        block_ref,
        block_target,
        shift_matrices,
        axis=2,
    )
    z_projection = _crop_2d_or_rgb(z_projection, z_projection_crop)

    fig = plt.figure(figsize=(16, 8), constrained_layout=True)
    grid = fig.add_gridspec(2, 2, width_ratios=[1.05, 1.0])
    ax_z = fig.add_subplot(grid[:, 0])
    ax_x = fig.add_subplot(grid[0, 1])
    ax_y = fig.add_subplot(grid[1, 1])

    ax_z.imshow(z_projection)
    ax_z.set_title("Z-projection")
    ax_x.imshow(x_projection)
    ax_x.set_title("X-projection")
    ax_y.imshow(y_projection)
    ax_y.set_title("Y-projection")
    for axis_obj in (ax_z, ax_x, ax_y):
        axis_obj.set_xticks([])
        axis_obj.set_yticks([])
    fig.suptitle(
        f"3D local registration QC: {moving_round} vs {reference_round} fiducial"
    )
    return fig, (ax_z, ax_x, ax_y)
