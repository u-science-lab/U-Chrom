from pathlib import Path
from uuid import NAMESPACE_DNS, uuid5

import numpy as np
import pandas as pd
from astropy.table import Table
from skimage import measure, morphology

from uchrom.im._base import LocalizationResult, MaskResult
from uchrom.im._pyhim import (
    PYHIM_LOCALIZATION_COLUMNS,
    build_pyhim_3d_localization_rows,
    global_shift_for_round,
)


def _barcode_from_round(round_name):
    digits = "".join(ch for ch in str(round_name) if ch.isdigit())
    if digits:
        return int(digits)
    return -1


def _roi_value(roi):
    try:
        return int(roi)
    except (TypeError, ValueError):
        return -1


def _threshold(stack, threshold=None, threshold_over_std=5.0):
    stack = np.asarray(stack)
    if threshold is not None:
        return float(threshold)
    return float(np.nanmean(stack) + threshold_over_std * np.nanstd(stack))


def _mask_label_at(mask, centroid):
    if mask is None:
        return 0
    labels = mask.labels if isinstance(mask, MaskResult) else np.asarray(mask)
    if labels.ndim == 2:
        y = int(np.clip(round(centroid[-2]), 0, labels.shape[0] - 1))
        x = int(np.clip(round(centroid[-1]), 0, labels.shape[1] - 1))
        return int(labels[y, x])
    if labels.ndim == 3 and len(centroid) == 3:
        z = int(np.clip(round(centroid[0]), 0, labels.shape[0] - 1))
        y = int(np.clip(round(centroid[1]), 0, labels.shape[1] - 1))
        x = int(np.clip(round(centroid[2]), 0, labels.shape[2] - 1))
        return int(labels[z, y, x])
    return 0


def _spot_id(round_name, idx, centroid):
    key = f"{round_name}:{idx}:{','.join(f'{float(v):.3f}' for v in centroid)}"
    return str(uuid5(NAMESPACE_DNS, key))


def _spot_rows_for_stack(
    stack,
    round_name,
    roi=None,
    mask=None,
    threshold=None,
    threshold_over_std=5.0,
    npix_min=1,
    npix_max=None,
    cell_id=0,
):
    stack = np.asarray(stack)
    if stack.ndim not in (2, 3):
        raise ValueError(f"localize expects 2D or 3D input, got shape {stack.shape}.")

    cutoff = _threshold(
        stack,
        threshold=threshold,
        threshold_over_std=threshold_over_std,
    )
    binary = stack > cutoff
    if npix_min and npix_min > 1:
        binary = morphology.remove_small_objects(binary, min_size=int(npix_min))
    labels = measure.label(binary)
    rows = []
    barcode = _barcode_from_round(round_name)
    roi_int = _roi_value(roi)

    for idx, region in enumerate(measure.regionprops(labels, intensity_image=stack)):
        npix = int(region.area)
        if npix_min is not None and npix < npix_min:
            continue
        if npix_max is not None and npix > npix_max:
            continue
        centroid = region.weighted_centroid
        if stack.ndim == 2:
            zc = 0.0
            yc = float(centroid[0])
            xc = float(centroid[1])
        else:
            zc = float(centroid[0])
            yc = float(centroid[1])
            xc = float(centroid[2])
        peak = float(region.max_intensity)
        flux = float(region.intensity_image[region.image].sum())
        rows.append(
            {
                "Buid": _spot_id(round_name, idx, (zc, yc, xc)),
                "ROI #": roi_int,
                "CellID #": int(cell_id) if mask is None else _mask_label_at(mask, (zc, yc, xc)),
                "Barcode #": barcode,
                "id": int(idx),
                "zcentroid": zc,
                "xcentroid": xc,
                "ycentroid": yc,
                "sharpness": 0.0,
                "roundness1": 0.0,
                "roundness2": 0.0,
                "npix": npix,
                "sky": 0.0,
                "peak": peak,
                "flux": flux,
                "mag": float(-2.5 * np.log10(max(flux, 1e-12))),
                "round": str(round_name),
                "label": str(round_name),
            }
        )
    return rows


def _pyhim_rows_for_stack(
    stack,
    round_name,
    roi=None,
    masks=None,
    global_registration=None,
    threshold=None,
    threshold_over_std=5.0,
    npix_min=1,
    npix_max=None,
    **kwargs,
):
    area_min = kwargs.pop("area_min", npix_min)
    area_max = kwargs.pop("area_max", npix_max)
    backend = kwargs.pop("backend", "stardist")
    assign_mask_labels = bool(kwargs.pop("assign_mask_labels", False))
    shift_yx = kwargs.pop("shift_yx", None)
    if shift_yx is None:
        shift_yx = global_shift_for_round(global_registration, round_name)
    rows = build_pyhim_3d_localization_rows(
        stack,
        round_name=round_name,
        roi=roi,
        global_shift_yx=shift_yx,
        threshold_over_std=threshold if threshold is not None else threshold_over_std,
        backend=backend,
        area_min=area_min,
        area_max=area_max,
        **kwargs,
    )
    if assign_mask_labels and masks is not None:
        for row in rows:
            row["CellID #"] = _mask_label_at(
                masks,
                (row["zcentroid"], row["ycentroid"], row["xcentroid"]),
            )
    return rows


def localize(
    image_or_stack,
    method="pyhim_3d",
    global_registration=None,
    local_registration=None,
    masks=None,
    roi=None,
    threshold=None,
    threshold_over_std=5.0,
    npix_min=1,
    npix_max=None,
    **kwargs,
):
    """
    Detect 2D/3D spots and return a pyHiM-compatible localization table.

    `method="pyhim_3d"` now follows pyHiM's 3D barcode-localization flow:
    optional focal-plane cropping, pyHiM StarDist/thresholding segmentation,
    pyHiM intensity-derived spot properties, and apifish subpixel fitting when
    available.
    """
    method = str(method).lower()
    if method not in ("pyhim_3d", "threshold", "dog"):
        raise ValueError(f"Unsupported localization method: {method}")

    rows = []
    if isinstance(image_or_stack, dict):
        for round_name, stack in image_or_stack.items():
            if method == "pyhim_3d":
                rows.extend(
                    _pyhim_rows_for_stack(
                        stack,
                        round_name=round_name,
                        roi=roi,
                        masks=masks,
                        global_registration=global_registration,
                        threshold=threshold,
                        threshold_over_std=threshold_over_std,
                        npix_min=npix_min,
                        npix_max=npix_max,
                        **kwargs,
                    )
                )
            else:
                rows.extend(
                    _spot_rows_for_stack(
                        stack,
                        round_name=round_name,
                        roi=roi,
                        mask=masks,
                        threshold=threshold,
                        threshold_over_std=threshold_over_std,
                        npix_min=npix_min,
                        npix_max=npix_max,
                    )
                )
    else:
        round_name = kwargs.get("round_name", "image")
        if method == "pyhim_3d":
            rows.extend(
                _pyhim_rows_for_stack(
                    image_or_stack,
                    round_name=round_name,
                    roi=roi,
                    masks=masks,
                    global_registration=global_registration,
                    threshold=threshold,
                    threshold_over_std=threshold_over_std,
                    npix_min=npix_min,
                    npix_max=npix_max,
                    **kwargs,
                )
            )
        else:
            rows.extend(
                _spot_rows_for_stack(
                    image_or_stack,
                    round_name=round_name,
                    roi=roi,
                    mask=masks,
                    threshold=threshold,
                    threshold_over_std=threshold_over_std,
                    npix_min=npix_min,
                    npix_max=npix_max,
                )
            )

    columns = (
        PYHIM_LOCALIZATION_COLUMNS
        if method == "pyhim_3d"
        else [
            "Buid",
            "ROI #",
            "CellID #",
            "Barcode #",
            "id",
            "zcentroid",
            "xcentroid",
            "ycentroid",
            "sharpness",
            "roundness1",
            "roundness2",
            "npix",
            "sky",
            "peak",
            "flux",
            "mag",
            "round",
            "label",
        ]
    )
    table = pd.DataFrame(rows, columns=columns)
    return LocalizationResult(table=table, method=method)


def save_localizations(result, out_dir, name="localizations_3D_barcode"):
    out_dir = Path(out_dir)
    data_dir = out_dir / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    path = data_dir / f"{name}.dat"
    table = result.table if isinstance(result, LocalizationResult) else result
    Table.from_pandas(table).write(path, format="ascii.ecsv", overwrite=True)
    if isinstance(result, LocalizationResult):
        result.saved_path = str(path)
        return result
    return str(path)


__all__ = ["localize", "save_localizations"]
