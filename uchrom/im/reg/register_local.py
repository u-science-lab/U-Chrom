from pathlib import Path

import numpy as np
import pandas as pd
from astropy.stats import SigmaClip
from astropy.table import Table
from photutils.background import Background2D, MedianBackground
from scipy.ndimage import shift as shift_image
from skimage import exposure
from skimage.metrics import normalized_root_mse
from skimage.registration import phase_cross_correlation
from skimage.util.shape import view_as_blocks

from uchrom.im._base import (
    Image3D,
    LocalRegistrationResult,
    LocalRegistrationRoundResult,
    ensure_3d_array,
)
from uchrom.im.reg.register_2d import _image_adjust


def _as_stack(image, source):
    if isinstance(image, Image3D):
        return ensure_3d_array(image.data, source=image.name or image.path or source)
    return ensure_3d_array(image, source=source)


def _image_name(image, fallback):
    if isinstance(image, Image3D):
        if image.path:
            return Path(image.path).name
        if image.name:
            return f"{image.name}.tif"
    return f"{fallback}.tif"


def _round_meta(spec):
    if isinstance(spec, dict):
        return dict(spec.get("meta", {}))
    return {}


def _round_fiducial(spec, round_name):
    if not isinstance(spec, dict) or "fiducial" not in spec:
        raise ValueError(f"Round '{round_name}' must contain a 3D fiducial stack.")
    return spec["fiducial"]


def _reinterpolate_z_remove(stack, z_binning):
    stack = np.asarray(stack)
    if z_binning is None or int(z_binning) <= 1:
        return stack
    return stack[range(0, stack.shape[0], int(z_binning))]


def _remove_inhomogeneous_background_3d(stack, box_size=(32, 32), filter_size=(3, 3)):
    stack = np.asarray(stack, dtype=np.float64)
    output = np.zeros_like(stack, dtype=np.float64)
    sigma_clip = SigmaClip(sigma=3)
    bkg_estimator = MedianBackground()
    for z in range(stack.shape[0]):
        background = Background2D(
            stack[z],
            box_size,
            filter_size=filter_size,
            sigma_clip=sigma_clip,
            bkg_estimator=bkg_estimator,
        )
        output[z] = stack[z] - background.background
    return output


def _preprocess_3d_image(stack, lower_threshold, higher_threshold):
    image = exposure.rescale_intensity(np.asarray(stack), out_range=(0, 1))
    image = _remove_inhomogeneous_background_3d(image)
    image, _, _, _, _ = _image_adjust(
        image,
        lower_threshold=lower_threshold,
        higher_threshold=higher_threshold,
    )
    # pyHiM keeps double precision through block3D registration; downcasting here
    # perturbs subpixel phase-correlation results for some blocks.
    return np.asarray(image, dtype=np.float64)


def _global_xy_shift(global_registration, round_name):
    if global_registration is None or round_name not in global_registration.rounds:
        return np.array([0.0, 0.0], dtype=np.float64)
    shift = np.asarray(global_registration.rounds[round_name].shift, dtype=np.float64)
    if shift.shape[0] < 2:
        return np.array([0.0, 0.0], dtype=np.float64)
    return shift[:2]


def _apply_xy_shift(stack, shift_yx):
    shift_zyx = np.array([0.0, float(shift_yx[0]), float(shift_yx[1])])
    return shift_image(stack, shift_zyx)


def _estimate_3d_shift(reference, moving, upsample_factor):
    shift, error, diffphase = phase_cross_correlation(
        reference,
        moving,
        upsample_factor=upsample_factor,
    )
    return np.asarray(shift, dtype=np.float64), float(error), float(diffphase)


def _block_images(reference, moving, block_size_xy):
    if reference.shape != moving.shape:
        raise ValueError(
            f"Reference and moving stacks must share shape: {reference.shape} vs {moving.shape}."
        )
    if reference.shape[1] % block_size_xy or reference.shape[2] % block_size_xy:
        raise ValueError(
            f"pyHiM block3D requires XY shape divisible by block_size_xy. "
            f"Got shape={reference.shape}, block_size_xy={block_size_xy}."
        )
    block_shape = (reference.shape[0], int(block_size_xy), int(block_size_xy))
    block_ref = view_as_blocks(reference, block_shape=block_shape).squeeze()
    block_target = view_as_blocks(moving, block_shape=block_shape).squeeze()
    if block_ref.ndim == 3:
        block_ref = block_ref[np.newaxis, np.newaxis, ...]
        block_target = block_target[np.newaxis, np.newaxis, ...]
    return block_ref, block_target


def _estimate_block_shift_matrices(reference, moving, block_size_xy, upsample_factor):
    block_ref, block_target = _block_images(reference, moving, block_size_xy)
    shift_matrices = [np.zeros(block_ref.shape[:2], dtype=np.float64) for _ in range(3)]
    rows = []
    for block_i in range(block_ref.shape[0]):
        for block_j in range(block_ref.shape[1]):
            shift, _, diffphase = _estimate_3d_shift(
                block_ref[block_i, block_j],
                block_target[block_i, block_j],
                upsample_factor=upsample_factor,
            )
            for matrix, value in zip(shift_matrices, shift):
                matrix[block_i, block_j] = value
            rows.append(
                {
                    "block_i": int(block_i),
                    "block_j": int(block_j),
                    "shift_z": float(shift[0]),
                    "shift_x": float(shift[1]),
                    "shift_y": float(shift[2]),
                    "diffphase": float(diffphase),
                }
            )
    return shift_matrices, block_ref, block_target, pd.DataFrame(rows)


def _quality_matrix_for_axis(block_ref, block_target, shift_matrices, axis):
    quality = np.zeros(block_ref.shape[:2], dtype=np.float64)
    for block_i in range(block_ref.shape[0]):
        for block_j in range(block_ref.shape[1]):
            shift_zyx = np.array([matrix[block_i, block_j] for matrix in shift_matrices])
            ref_block = block_ref[block_i, block_j]
            target_block = shift_image(block_target[block_i, block_j], shift_zyx)
            ref_proj = np.sum(ref_block, axis=axis)
            target_proj = np.sum(target_block, axis=axis)
            ref_proj = exposure.rescale_intensity(ref_proj, out_range=(0, 1))
            target_proj = exposure.rescale_intensity(target_proj, out_range=(0, 1))
            ref_proj, _, _, _, _ = _image_adjust(
                ref_proj,
                lower_threshold=0.5,
                higher_threshold=0.9999,
            )
            target_proj, _, _, _, _ = _image_adjust(
                target_proj,
                lower_threshold=0.5,
                higher_threshold=0.9999,
            )
            quality[block_i, block_j] = normalized_root_mse(
                ref_proj,
                target_proj,
                normalization="euclidean",
            )
    return quality


def _quality_matrices(block_ref, block_target, shift_matrices):
    return [
        _quality_matrix_for_axis(block_ref, block_target, shift_matrices, axis)
        for axis in range(3)
    ]


def _apply_block_shifts_to_stack(stack, block_size_xy, shift_matrices):
    stack = np.asarray(stack, dtype=np.float64)
    if stack.shape[1] % block_size_xy or stack.shape[2] % block_size_xy:
        raise ValueError(
            f"pyHiM block3D requires XY shape divisible by block_size_xy. "
            f"Got shape={stack.shape}, block_size_xy={block_size_xy}."
        )

    block_shape = (stack.shape[0], int(block_size_xy), int(block_size_xy))
    blocks = view_as_blocks(stack, block_shape=block_shape).squeeze()
    if blocks.ndim == 3:
        blocks = blocks[np.newaxis, np.newaxis, ...]
    if blocks.shape[:2] != shift_matrices[0].shape:
        raise ValueError(
            f"Shift matrix shape {shift_matrices[0].shape} does not match "
            f"block grid {blocks.shape[:2]}."
        )

    output = np.zeros_like(stack, dtype=np.float64)
    for block_i in range(blocks.shape[0]):
        for block_j in range(blocks.shape[1]):
            shift_zyx = np.array([matrix[block_i, block_j] for matrix in shift_matrices])
            shifted = shift_image(blocks[block_i, block_j], shift_zyx)
            y0 = block_i * int(block_size_xy)
            y1 = (block_i + 1) * int(block_size_xy)
            x0 = block_j * int(block_size_xy)
            x1 = (block_j + 1) * int(block_size_xy)
            output[:, y0:y1, x0:x1] = shifted
    return output


def _table_prefix(reference_file, aligned_file, block_size_xy, roi, round_name):
    try:
        roi_value = int(roi)
    except (TypeError, ValueError):
        roi_value = -1
    return {
        "reference file": reference_file,
        "aligned file": aligned_file,
        "blockXY": int(block_size_xy),
        "ROI #": roi_value,
        "label": str(round_name),
    }


def _reference_rows(reference_file, block_size_xy, roi, round_name):
    return pd.DataFrame(
        [
            {
                **_table_prefix(reference_file, reference_file, block_size_xy, roi, round_name),
                "block_i": 0,
                "block_j": 0,
                "shift_z": 0.0,
                "shift_x": 0.0,
                "shift_y": 0.0,
                "quality_xy": 1.0,
                "quality_zy": 1.0,
                "quality_zx": 1.0,
            }
        ]
    )


def _ordered_table(table):
    columns = [
        "reference file",
        "aligned file",
        "blockXY",
        "ROI #",
        "label",
        "block_i",
        "block_j",
        "shift_z",
        "shift_x",
        "shift_y",
        "quality_xy",
        "quality_zy",
        "quality_zx",
    ]
    return table[columns]


def _mean_shift_from_table(table):
    if table.empty:
        return np.array([0.0, 0.0, 0.0], dtype=np.float64)
    return np.array(
        [
            table["shift_z"].median(),
            table["shift_x"].median(),
            table["shift_y"].median(),
        ],
        dtype=np.float64,
    )


def register_local(
    rounds,
    global_registration=None,
    reference=None,
    method="block3d",
    block_size_xy=128,
    upsample_factor=100,
    lower_threshold=0.9,
    higher_threshold=0.9999,
    pixel_size_xy=None,
    pixel_size_z=None,
    z_binning=None,
    save=False,
    out_dir=None,
):
    """
    pyHiM-style 3D local registration.

    The key pyHiM steps are preserved: z-plane removal via z_binning, 3D
    preprocessing, existing XY shift application, block3D phase correlation,
    and NRMSE quality matrices from XY/ZX/ZY reprojections.
    """
    if method not in ("block3d", "global3d"):
        raise ValueError(f"Unsupported local registration method: {method}")
    if not isinstance(rounds, dict) or not rounds:
        raise ValueError("rounds must be a non-empty dict.")
    if reference is None:
        if global_registration is not None:
            reference = global_registration.reference
        else:
            raise ValueError("reference must be provided when global_registration is None.")
    if reference not in rounds:
        raise ValueError(f"Reference round '{reference}' is not present in rounds.")

    reference_image = _round_fiducial(rounds[reference], reference)
    reference_raw = _reinterpolate_z_remove(
        _as_stack(reference_image, f"{reference} fiducial"),
        z_binning,
    )
    reference_stack = _preprocess_3d_image(
        reference_raw,
        lower_threshold=lower_threshold,
        higher_threshold=higher_threshold,
    )
    reference_file = _image_name(reference_image, f"{reference}_fiducial")
    roi = _round_meta(rounds[reference]).get("roi")
    round_results = {}
    all_rows = []

    for round_name, spec in rounds.items():
        moving_image = _round_fiducial(spec, round_name)
        moving_raw = _reinterpolate_z_remove(
            _as_stack(moving_image, f"{round_name} fiducial"),
            z_binning,
        )
        if moving_raw.shape != reference_raw.shape:
            raise ValueError(
                f"Round '{round_name}' fiducial shape {moving_raw.shape} does not "
                f"match reference shape {reference_raw.shape}."
            )

        meta = _round_meta(spec)
        roi = meta.get("roi", roi)
        aligned_file = _image_name(moving_image, f"{round_name}_fiducial")

        if round_name == reference:
            total_shift = np.array([0.0, 0.0, 0.0], dtype=np.float64)
            registered = np.asarray(moving_raw, dtype=np.float64)
            block_table = _reference_rows(reference_file, block_size_xy, roi, round_name)
        else:
            moving_stack = _preprocess_3d_image(
                moving_raw,
                lower_threshold=lower_threshold,
                higher_threshold=higher_threshold,
            )
            global_yx = _global_xy_shift(global_registration, round_name)
            moving_after_global = _apply_xy_shift(moving_stack, global_yx)

            if method == "block3d":
                shift_matrices, block_ref, block_target, block_table = (
                    _estimate_block_shift_matrices(
                        reference_stack,
                        moving_after_global,
                        block_size_xy=block_size_xy,
                        upsample_factor=upsample_factor,
                    )
                )
                quality_xy, quality_zy, quality_zx = _quality_matrices(
                    block_ref,
                    block_target,
                    shift_matrices,
                )
                block_table["quality_xy"] = [
                    float(quality_xy[i, j])
                    for i, j in zip(block_table["block_i"], block_table["block_j"])
                ]
                block_table["quality_zy"] = [
                    float(quality_zy[i, j])
                    for i, j in zip(block_table["block_i"], block_table["block_j"])
                ]
                block_table["quality_zx"] = [
                    float(quality_zx[i, j])
                    for i, j in zip(block_table["block_i"], block_table["block_j"])
                ]
                moving_raw_after_global = _apply_xy_shift(
                    np.asarray(moving_raw, dtype=np.float64),
                    global_yx,
                )
                registered = _apply_block_shifts_to_stack(
                    moving_raw_after_global,
                    block_size_xy,
                    shift_matrices,
                )
            else:
                shift, error, _ = _estimate_3d_shift(
                    reference_stack,
                    moving_after_global,
                    upsample_factor=upsample_factor,
                )
                quality = float(
                    normalized_root_mse(
                        np.sum(reference_stack, axis=0),
                        np.sum(shift_image(moving_after_global, shift), axis=0),
                        normalization="euclidean",
                    )
                )
                block_table = pd.DataFrame(
                    [
                        {
                            "block_i": 0,
                            "block_j": 0,
                            "shift_z": float(shift[0]),
                            "shift_x": float(shift[1]),
                            "shift_y": float(shift[2]),
                            "quality_xy": quality,
                            "quality_zy": quality,
                            "quality_zx": quality,
                        }
                    ]
                )

            prefix = _table_prefix(reference_file, aligned_file, block_size_xy, roi, round_name)
            for key, value in prefix.items():
                block_table[key] = value
            block_table = _ordered_table(block_table)
            total_shift = _mean_shift_from_table(block_table)
            if method != "block3d":
                registered = shift_image(
                    moving_raw,
                    np.array(
                        [
                            total_shift[0],
                            total_shift[1] + global_yx[0],
                            total_shift[2] + global_yx[1],
                        ]
                    ),
                ).astype(np.float64)

        block_table = _ordered_table(block_table)
        if round_name != reference:
            all_rows.append(block_table)
        round_results[round_name] = LocalRegistrationRoundResult(
            shift_zyx=total_shift,
            registered_fiducial=registered,
            block_table=block_table,
            meta=meta,
        )

    table = pd.concat(all_rows, ignore_index=True) if all_rows else pd.DataFrame()
    result = LocalRegistrationResult(
        reference=reference,
        rounds=round_results,
        table=table,
        method=method,
    )
    if save not in (False, None, "none"):
        save_local_registration_result(result, out_dir=out_dir, save=save)
    return result


def save_local_registration_result(result, out_dir, save="selected"):
    if save in (False, None, "none"):
        result.out_dir = None
        result.table_path = None
        return result

    out_root = Path(out_dir)
    data_dir = out_root / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    table_path = data_dir / "shifts_block3D.dat"
    Table.from_pandas(result.table).write(table_path, format="ascii.ecsv", overwrite=True)

    if save == "all":
        for round_name, round_result in result.rounds.items():
            np.save(
                data_dir / f"{round_name}_fiducial_3d_registered.npy",
                round_result.registered_fiducial,
            )

    result.out_dir = str(out_root)
    result.table_path = str(table_path)
    return result


__all__ = ["register_local", "save_local_registration_result"]
