import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from astropy.stats import SigmaClip
from astropy.table import Table
from photutils.background import Background2D, MedianBackground
from scipy.ndimage import shift as shift_image
from skimage import exposure, measure
from skimage.exposure import match_histograms
from skimage.registration import phase_cross_correlation
from skimage.util.shape import view_as_blocks

from uchrom.im._base import (
    Image2D,
    Registration2DImageResult,
    Registration2DResult,
    Registration2DRoundResult,
    RoundBundle,
    ensure_2d_array,
)


VALID_ARRAY_SUFFIXES = (".npy",)
LOWER_THRESHOLD = 0.999
HIGHER_THRESHOLD = 0.9999999
MIN_NUMBER_POLLSTERS = 4
SHIFT_ERROR_TOLERANCE = 5


def _ensure_rounds_dict(rounds):
    if not isinstance(rounds, dict) or not rounds:
        raise ValueError("rounds must be a non-empty dict keyed by round name.")
    return rounds


def _normalize_save_mode(save):
    if save in (False, None, "none"):
        return None
    if save in (True, "all"):
        return "all"
    if save == "selected":
        return "selected"
    raise ValueError(f"Unsupported save mode: {save}")


def _coerce_image2d(image, name=None, path=None, meta=None, source="input"):
    meta = {} if meta is None else dict(meta)
    if isinstance(image, Image2D):
        image.data = ensure_2d_array(image.data, source=image.name or image.path or source)
        if name is not None and image.name is None:
            image.name = name
        if path is not None and image.path is None:
            image.path = str(path)
        if meta:
            image.meta = {**meta, **image.meta}
        return image
    return Image2D(
        data=ensure_2d_array(image, source=source),
        name=name,
        path=None if path is None else str(path),
        meta=meta,
    )


def _ensure_round_spec(round_name, spec):
    if not isinstance(spec, dict):
        raise ValueError(f"Round '{round_name}' must map to a dict.")
    if "fiducial" not in spec:
        raise ValueError(f"Round '{round_name}' is missing required key 'fiducial'.")
    images = spec.get("images", {})
    if images is None:
        images = {}
    return images, dict(spec.get("meta", {}))


def _ensure_round_bundles(rounds, reference):
    rounds = _ensure_rounds_dict(rounds)
    if reference not in rounds:
        raise ValueError(f"Reference round '{reference}' is not present in rounds.")
    if not all(isinstance(bundle, RoundBundle) for bundle in rounds.values()):
        raise ValueError("Expected rounds to contain RoundBundle values.")
    return rounds


def _load_array_2d(path):
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Input file not found: {path}")
    if not path.is_file():
        raise ValueError(f"Expected a .npy file, got: {path}")
    if path.suffix.lower() not in VALID_ARRAY_SUFFIXES:
        raise ValueError(f"Only .npy 2D arrays are supported, got: {path}")

    array = np.load(path)
    return ensure_2d_array(array, source=str(path)), path


def _normalize_images_mapping(images, round_name, mode):
    if mode == "arrays":
        if not isinstance(images, dict):
            raise ValueError(
                f"Round '{round_name}' key 'images' must be a dict of named arrays."
            )
        return images

    if isinstance(images, dict):
        return images
    if isinstance(images, (list, tuple)):
        mapping = {}
        for image_path in images:
            image_path = Path(image_path)
            mapping[image_path.stem] = str(image_path)
        return mapping
    raise ValueError(
        f"Round '{round_name}' key 'images' must be a dict of named paths or a list of paths."
    )


def _prepare_round_bundles(rounds, reference):
    rounds = _ensure_rounds_dict(rounds)
    if reference not in rounds:
        raise ValueError(f"Reference round '{reference}' is not present in rounds.")

    round_bundles = {}
    reference_shape = None

    for round_name, spec in rounds.items():
        images, meta = _ensure_round_spec(round_name, spec)
        images = _normalize_images_mapping(images, round_name, mode="arrays")

        fiducial = _coerce_image2d(
            spec["fiducial"],
            name=f"{round_name}_fiducial_2d",
            meta=meta,
            source=f"round '{round_name}' fiducial",
        )

        image_mapping = {}
        for image_name, image_array in images.items():
            image_obj = _coerce_image2d(
                image_array,
                name=str(image_name),
                meta=meta,
                source=f"round '{round_name}' image '{image_name}'",
            )
            if image_obj.data.shape != fiducial.data.shape:
                raise ValueError(
                    f"Round '{round_name}' image '{image_name}' shape {image_obj.data.shape} does not "
                    f"match fiducial shape {fiducial.data.shape}."
                )
            image_mapping[str(image_name)] = image_obj

        if reference_shape is None and round_name == reference:
            reference_shape = fiducial.data.shape
        elif reference_shape is not None and fiducial.data.shape != reference_shape:
            raise ValueError(
                f"Round '{round_name}' fiducial shape {fiducial.data.shape} does not match "
                f"reference fiducial shape {reference_shape}."
            )

        round_bundles[round_name] = RoundBundle(
            fiducial=fiducial,
            images=image_mapping,
            meta=meta,
        )

    reference_shape = round_bundles[reference].fiducial.data.shape
    for round_name, bundle in round_bundles.items():
        if bundle.fiducial.data.shape != reference_shape:
            raise ValueError(
                f"Round '{round_name}' fiducial shape {bundle.fiducial.data.shape} "
                f"does not match reference fiducial shape {reference_shape}."
            )

    return round_bundles


def _load_round_bundles_from_paths(rounds, reference):
    rounds = _ensure_rounds_dict(rounds)
    if reference not in rounds:
        raise ValueError(f"Reference round '{reference}' is not present in rounds.")

    round_bundles = {}
    reference_shape = None

    for round_name, spec in rounds.items():
        images, meta = _ensure_round_spec(round_name, spec)
        images = _normalize_images_mapping(images, round_name, mode="paths")

        fiducial_array, fiducial_path = _load_array_2d(spec["fiducial"])
        fiducial = Image2D(
            data=fiducial_array,
            name=fiducial_path.stem,
            path=str(fiducial_path),
            meta=meta,
        )

        image_mapping = {}
        for image_name, image_path in images.items():
            image_array, array_path = _load_array_2d(image_path)
            if image_array.shape != fiducial.data.shape:
                raise ValueError(
                    f"Round '{round_name}' image shape {image_array.shape} does not match "
                    f"fiducial shape {fiducial.data.shape}: {array_path}"
                )
            image_mapping[str(image_name)] = Image2D(
                data=image_array,
                name=array_path.stem,
                path=str(array_path),
                meta=meta,
            )

        if reference_shape is None and round_name == reference:
            reference_shape = fiducial.data.shape
        elif reference_shape is not None and fiducial.data.shape != reference_shape:
            raise ValueError(
                f"Round '{round_name}' fiducial shape {fiducial.data.shape} does not match "
                f"reference fiducial shape {reference_shape}."
            )

        round_bundles[round_name] = RoundBundle(
            fiducial=fiducial,
            images=image_mapping,
            meta=meta,
        )

    reference_shape = round_bundles[reference].fiducial.data.shape
    for round_name, bundle in round_bundles.items():
        if bundle.fiducial.data.shape != reference_shape:
            raise ValueError(
                f"Round '{round_name}' fiducial shape {bundle.fiducial.data.shape} "
                f"does not match reference fiducial shape {reference_shape}."
            )

    return round_bundles


def _normalize_image(image):
    image = np.asarray(image, dtype=np.float64)
    max_value = image.max()
    if max_value == 0:
        return np.zeros_like(image, dtype=np.float64)
    return image / max_value


def _remove_inhomogeneous_background(image, background_sigma):
    sigma_clip = SigmaClip(sigma=background_sigma)
    background = Background2D(
        image,
        (64, 64),
        filter_size=(3, 3),
        sigma_clip=sigma_clip,
        bkg_estimator=MedianBackground(),
    )
    return image - background.background


def _preprocess_fiducial(image, background_sigma):
    normalized = _normalize_image(image)
    return _remove_inhomogeneous_background(normalized, background_sigma)


def _image_adjust(image, lower_threshold=LOWER_THRESHOLD, higher_threshold=HIGHER_THRESHOLD):
    image = exposure.rescale_intensity(image, out_range=(0, 1))
    hist_before = exposure.histogram(image)

    hist_sum = np.zeros(len(hist_before[0]))
    for idx in range(len(hist_before[0]) - 1):
        hist_sum[idx + 1] = hist_sum[idx] + hist_before[0][idx]

    sum_normalized = hist_sum / hist_sum.max()
    lower_cutoff = np.where(sum_normalized > lower_threshold)[0][0] / 255
    higher_cutoff = np.where(sum_normalized > higher_threshold)[0][0] / 255

    adjusted = exposure.rescale_intensity(
        image,
        in_range=(lower_cutoff, higher_cutoff),
        out_range=(0, 1),
    )
    hist_after = exposure.histogram(adjusted)

    return adjusted, hist_before, hist_after, lower_cutoff, higher_cutoff


def _align_2_images_cross_correlation(
    image1_uncorrected,
    image2_uncorrected,
    lower_threshold=LOWER_THRESHOLD,
    higher_threshold=HIGHER_THRESHOLD,
    upsample_factor=100,
):
    image1_adjusted, hist1_before, hist1_after, lower_cutoff1, _ = _image_adjust(
        image1_uncorrected,
        lower_threshold=lower_threshold,
        higher_threshold=higher_threshold,
    )
    image2_adjusted, hist2_before, hist2_after, lower_cutoff2, _ = _image_adjust(
        image2_uncorrected,
        lower_threshold=lower_threshold,
        higher_threshold=higher_threshold,
    )

    lower_thresholds = {"Im1": lower_cutoff1, "Im2": lower_cutoff2}
    histograms = {
        "Im1": (hist1_before, hist1_after),
        "Im2": (hist2_before, hist2_after),
    }

    shift, error, diffphase = phase_cross_correlation(
        image1_adjusted,
        image2_adjusted,
        upsample_factor=upsample_factor,
    )
    corrected = shift_image(image2_adjusted, shift)
    corrected = exposure.rescale_intensity(corrected, out_range=(0, 1))

    return (
        np.asarray(shift, dtype=np.float64),
        float(error),
        float(diffphase),
        lower_thresholds,
        histograms,
        corrected,
        image1_adjusted,
        image2_adjusted,
    )


def _compute_global_shift(
    reference_image,
    moving_image,
    upsample_factor=100,
    lower_threshold=LOWER_THRESHOLD,
    higher_threshold=HIGHER_THRESHOLD,
):
    shift, _, diffphase, _, _, _, _, _ = _align_2_images_cross_correlation(
        reference_image,
        moving_image,
        lower_threshold=lower_threshold,
        higher_threshold=higher_threshold,
        upsample_factor=upsample_factor,
    )
    return shift, diffphase


def _ensure_block_compatible(shape, block_size):
    if shape[0] % block_size != 0 or shape[1] % block_size != 0:
        raise ValueError(
            f"Block alignment requires image shape divisible by block_size. "
            f"Got shape={shape}, block_size={block_size}."
        )


def _calculate_error(shifted_image, reference_image):
    shifted_image = np.asarray(shifted_image)
    shifted_image[shifted_image < 0] = 0
    return float(np.sum(np.sum(np.abs(reference_image - shifted_image), axis=1)))


def _align_images_by_blocks(
    img_1,
    img_2,
    block_size,
    upsample_factor=100,
    min_number_pollsters=MIN_NUMBER_POLLSTERS,
    tolerance=0.1,
    shift_error_tolerance=SHIFT_ERROR_TOLERANCE,
):
    blocks_1 = view_as_blocks(img_1, block_size)
    blocks_2 = view_as_blocks(img_2, block_size)
    shift_image_norm = np.zeros((blocks_1.shape[0], blocks_1.shape[1]))
    shifted_image = np.zeros((blocks_1.shape[0], blocks_1.shape[1], 2))
    rms_image = np.zeros((blocks_1.shape[0], blocks_1.shape[1]))

    for i in range(blocks_1.shape[0]):
        for j in range(blocks_1.shape[1]):
            shift, _, _ = phase_cross_correlation(
                blocks_1[i, j],
                blocks_2[i, j],
                upsample_factor=upsample_factor,
            )
            shift_image_norm[i, j] = np.linalg.norm(shift)
            shifted_image[i, j, 0] = shift[0]
            shifted_image[i, j, 1] = shift[1]
            img_2_aligned = shift_image(img_2, shift)
            rms_image[i, j] = np.sum(np.sum(np.abs(img_1 - img_2_aligned), axis=1))

    threshold = (1 + tolerance) * np.min(rms_image)
    mask = rms_image < threshold

    if rms_image.shape[0] < 2 or rms_image.shape[1] < 2:
        contour = np.array([0, 0])
    else:
        contours = measure.find_contours(rms_image, threshold)
        try:
            contour = sorted(contours, key=len)[-1]
        except IndexError:
            contour = np.array([0, 0])

    mean_shifts = [np.mean(shifted_image[mask, 0]), np.mean(shifted_image[mask, 1])]
    std_shifts = [np.std(shifted_image[mask, 0]), np.std(shifted_image[mask, 1])]
    mean_shift_norm = np.mean(shift_image_norm[mask])
    mean_error = np.mean(rms_image[mask])
    relative_shifts = np.abs(shift_image_norm - mean_shift_norm)

    mean_shifts_global, _, _ = phase_cross_correlation(
        img_1, img_2, upsample_factor=upsample_factor
    )
    img_2_aligned_global = shift_image(img_2, shift)
    mean_error_global = np.sum(np.sum(np.abs(img_1 - img_2_aligned_global), axis=1))

    if (
        np.sum(mask) < min_number_pollsters
        or mean_error_global < mean_error
        or np.max(std_shifts) > shift_error_tolerance
    ):
        mean_shifts = mean_shifts_global

    return np.asarray(mean_shifts, dtype=np.float64), relative_shifts, rms_image, contour


def _compute_shift_by_block(
    reference_image,
    moving_image,
    block_size,
    tolerance,
    upsample_factor=100,
):
    reference_image = np.float32(reference_image)
    moving_image = np.float32(moving_image)
    moving_image = np.float32(match_histograms(moving_image, reference_image))
    shift, relative_shifts, rms_image, contour = _align_images_by_blocks(
        reference_image,
        moving_image,
        (block_size, block_size),
        upsample_factor=upsample_factor,
        min_number_pollsters=MIN_NUMBER_POLLSTERS,
        tolerance=tolerance,
    )
    diffphase = 0.0
    return (
        reference_image,
        moving_image,
        shift,
        diffphase,
        relative_shifts,
        rms_image,
        contour,
    )


def _register_fiducial_pair(
    reference_image,
    moving_image,
    align_by_block,
    block_size,
    tolerance,
    background_sigma,
    upsample_factor,
):
    preprocessed_ref = _preprocess_fiducial(reference_image, background_sigma)
    preprocessed_moving = _preprocess_fiducial(moving_image, background_sigma)

    if align_by_block:
        _ensure_block_compatible(preprocessed_ref.shape, block_size)
        (
            preprocessed_ref,
            preprocessed_moving,
            shift,
            diffphase,
            _,
            _,
            _,
        ) = _compute_shift_by_block(
            preprocessed_ref,
            preprocessed_moving,
            block_size=block_size,
            tolerance=tolerance,
            upsample_factor=upsample_factor,
        )
    else:
        shift, diffphase = _compute_global_shift(
            preprocessed_ref,
            preprocessed_moving,
            upsample_factor=upsample_factor,
        )

    shifted_preprocessed_moving = shift_image(preprocessed_moving, shift)
    error = _calculate_error(shifted_preprocessed_moving, preprocessed_ref)

    preprocessed_ref = np.asarray(preprocessed_ref, dtype=np.float64)
    preprocessed_moving = np.asarray(preprocessed_moving, dtype=np.float64)
    preprocessed_ref[preprocessed_ref < 0] = 0
    preprocessed_moving[preprocessed_moving < 0] = 0
    shifted_preprocessed_moving = np.asarray(
        shifted_preprocessed_moving, dtype=np.float64
    )

    return {
        "shift": np.asarray(shift, dtype=np.float64),
        "error": float(error),
        "diffphase": float(diffphase),
        "reference_preprocessed": preprocessed_ref,
        "moving_preprocessed": preprocessed_moving,
        "moving_preprocessed_shifted": shifted_preprocessed_moving,
    }


def _apply_shift(image, shift):
    image = np.asarray(image)
    if np.issubdtype(image.dtype, np.floating):
        finite = np.isfinite(image)
        if finite.all():
            rounded = np.rint(image)
            if (
                np.allclose(image, rounded, atol=1e-8, rtol=0.0)
                and rounded.min() >= 0
                and rounded.max() <= np.iinfo(np.uint16).max
            ):
                image = rounded.astype(np.uint16)
    shifted = shift_image(image, shift)
    return np.asarray(shifted, dtype=np.float64)


def _resolve_default_out_dir(reference_path):
    reference_path = Path(reference_path)
    if (
        reference_path.parent.name == "data"
        and reference_path.parent.parent.name == "project"
    ):
        return reference_path.parent.parent.parent / "register_global"
    return reference_path.parent / "register_global"


def _resolve_result_out_dir(result, out_dir=None):
    if out_dir is not None:
        return Path(out_dir)

    reference_bundle = result.rounds[result.reference]
    if reference_bundle.fiducial.path:
        return _resolve_default_out_dir(reference_bundle.fiducial.path)
    return Path.cwd() / "register_global"


def _ensure_writable_output_dir(out_root):
    out_root = Path(out_root)
    data_dir = out_root / "data"
    try:
        data_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise PermissionError(f"Unable to create output directory: {out_root}") from exc

    probe = data_dir / ".uchrom_write_test"
    try:
        with open(probe, "wb") as handle:
            handle.write(b"ok")
    except OSError as exc:
        raise PermissionError(f"Output directory is not writable: {data_dir}") from exc
    finally:
        if probe.exists():
            probe.unlink()

    return data_dir


def _name_token(image, fallback):
    if image.path:
        return image.path
    if image.name:
        return image.name
    return fallback


def _image_output_token(round_name, image_name, image):
    if image.path:
        return image.path
    if image.name and image.name.endswith("_2d"):
        return image.name
    return f"{round_name}_{image_name}_2d"


def _registered_path(data_dir, input_token):
    input_path = Path(str(input_token))
    return data_dir / f"{input_path.stem}_registered.npy"


def _overlay_path(data_dir, input_token):
    input_path = Path(str(input_token))
    return data_dir / f"{input_path.stem}_overlay_corrected.png"


def _reference_diff_path(data_dir, input_token):
    input_path = Path(str(input_token))
    return data_dir / f"{input_path.stem}_referenceDifference.png"


def _save_array(path, array):
    np.save(path, np.asarray(array))
    return str(path)


def _save_overlay_png(reference_image, shifted_image, path):
    img_1 = _normalize_image(reference_image)
    img_2 = _normalize_image(shifted_image)
    img_1, _, _, _, _ = _image_adjust(
        img_1, lower_threshold=0.5, higher_threshold=0.9999
    )
    img_2, _, _, _, _ = _image_adjust(
        img_2, lower_threshold=0.5, higher_threshold=0.9999
    )
    rgb = np.dstack([img_1, img_2, np.zeros(reference_image.shape, dtype=np.float64)])
    fig, ax = plt.subplots(figsize=(10, 10))
    ax.imshow(rgb)
    ax.axis("off")
    fig.savefig(path)
    plt.close(fig)
    return str(path)


def _save_reference_difference_png(
    reference_image, shifted_image, unshifted_image, path
):
    img_1, _, _, _, _ = _image_adjust(
        _normalize_image(reference_image), lower_threshold=0.5, higher_threshold=0.9999
    )
    img_2, _, _, _, _ = _image_adjust(
        _normalize_image(unshifted_image), lower_threshold=0.5, higher_threshold=0.9999
    )
    img_3, _, _, _, _ = _image_adjust(
        _normalize_image(reference_image), lower_threshold=0.5, higher_threshold=0.9999
    )
    img_4, _, _, _, _ = _image_adjust(
        _normalize_image(shifted_image), lower_threshold=0.5, higher_threshold=0.9999
    )

    fig, axes = plt.subplots(1, 2, figsize=(20, 10))
    axes[0].imshow(img_1 - img_2, cmap="seismic")
    axes[0].axis("off")
    axes[0].set_title("uncorrected")
    axes[1].imshow(img_3 - img_4, cmap="seismic")
    axes[1].axis("off")
    axes[1].set_title("corrected")
    fig.savefig(path)
    plt.close(fig)
    return str(path)


def _build_shifts_json_payload(round_results, reference_round, roi=None):
    shifts = {
        round_name: [float(round_result.shift[0]), float(round_result.shift[1])]
        for round_name, round_result in round_results.items()
        if round_name != reference_round
    }
    if roi is not None:
        return {f"ROI:{roi}": shifts}
    return shifts


def _save_shifts_json(data_dir, result):
    payload = _build_shifts_json_payload(
        result.rounds,
        reference_round=result.reference,
        roi=result.roi,
    )
    path = data_dir / "shifts.json"
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=4)
    return str(path)


def _table_source_name(path_or_name):
    path = Path(str(path_or_name))
    if path.suffix.lower() == ".npy" and path.stem.endswith("_2d"):
        return f"{path.stem[:-3]}.tif"
    if not path.suffix and path.stem.endswith("_2d"):
        return f"{path.stem[:-3]}.tif"
    if path.suffix:
        return path.name
    return f"{path.stem}.tif"


def _save_shifts_table(data_dir, result):
    path = data_dir / "shifts.table"
    table = Table(
        names=(
            "aligned file",
            "reference file",
            "shift_x",
            "shift_y",
            "error",
            "diffphase",
        ),
        dtype=("S2", "S2", "f4", "f4", "f4", "f4"),
    )

    reference_token = _name_token(
        result.rounds[result.reference].fiducial,
        f"{result.reference}_fiducial_2d",
    )
    reference_file = _table_source_name(reference_token)
    for round_name in sorted(result.rounds):
        if round_name == result.reference:
            continue
        round_result = result.rounds[round_name]
        aligned_token = _name_token(round_result.fiducial, f"{round_name}_fiducial_2d")
        table.add_row(
            [
                _table_source_name(aligned_token),
                reference_file,
                float(round_result.shift[0]),
                float(round_result.shift[1]),
                float(round_result.error),
                float(round_result.diffphase),
            ]
        )

    table.write(path, format="ascii.ecsv", overwrite=True)
    return str(path)


def _register_2d_round_bundles(
    round_bundles,
    reference,
    sample_id=None,
    roi=None,
    upsample_factor=100,
    align_by_block=True,
    block_size=128,
    tolerance=0.1,
    background_sigma=3.0,
):
    round_bundles = _ensure_round_bundles(round_bundles, reference=reference)
    reference_raw_fiducial = np.asarray(round_bundles[reference].fiducial.data)
    round_results = {}

    for round_name, bundle in round_bundles.items():
        raw_fiducial = np.asarray(bundle.fiducial.data)

        if round_name == reference:
            shift = np.array([0.0, 0.0], dtype=np.float64)
            error = None
            diffphase = None
            registered_fiducial = np.asarray(raw_fiducial, dtype=np.float64)
            reference_preprocessed = _preprocess_fiducial(
                reference_raw_fiducial, background_sigma
            )
            moving_preprocessed = None
            moving_preprocessed_shifted = None
        else:
            registration = _register_fiducial_pair(
                reference_raw_fiducial,
                raw_fiducial,
                align_by_block=align_by_block,
                block_size=block_size,
                tolerance=tolerance,
                background_sigma=background_sigma,
                upsample_factor=upsample_factor,
            )
            shift = registration["shift"]
            error = registration["error"]
            diffphase = registration["diffphase"]
            registered_fiducial = registration["moving_preprocessed_shifted"]
            reference_preprocessed = registration["reference_preprocessed"]
            moving_preprocessed = registration["moving_preprocessed"]
            moving_preprocessed_shifted = registration["moving_preprocessed_shifted"]

        image_results = {}
        for image_name, image in bundle.images.items():
            if round_name == reference:
                registered_image = np.asarray(image.data, dtype=np.float64)
            else:
                registered_image = _apply_shift(image.data, shift)
            image_results[image_name] = Registration2DImageResult(
                input_image=image,
                registered=registered_image,
            )

        round_results[round_name] = Registration2DRoundResult(
            shift=np.asarray(shift, dtype=np.float64),
            fiducial=bundle.fiducial,
            registered_fiducial=np.asarray(registered_fiducial, dtype=np.float64),
            images=image_results,
            meta=bundle.meta,
            error=error,
            diffphase=diffphase,
            reference_preprocessed=reference_preprocessed,
            moving_preprocessed=moving_preprocessed,
            moving_preprocessed_shifted=moving_preprocessed_shifted,
        )

    return Registration2DResult(
        reference=reference,
        rounds=round_results,
        sample_id=sample_id,
        roi=roi,
    )


def register_2d_arrays(
    rounds,
    reference,
    sample_id=None,
    roi=None,
    upsample_factor=100,
    align_by_block=True,
    block_size=128,
    tolerance=0.1,
    background_sigma=3.0,
):
    round_bundles = _prepare_round_bundles(rounds, reference=reference)
    return _register_2d_round_bundles(
        round_bundles,
        reference=reference,
        sample_id=sample_id,
        roi=roi,
        upsample_factor=upsample_factor,
        align_by_block=align_by_block,
        block_size=block_size,
        tolerance=tolerance,
        background_sigma=background_sigma,
    )


def _looks_like_path_rounds(rounds):
    first_spec = next(iter(_ensure_rounds_dict(rounds).values()))
    if isinstance(first_spec, RoundBundle):
        return False
    if not isinstance(first_spec, dict):
        return False
    fiducial = first_spec.get("fiducial")
    return isinstance(fiducial, (str, Path))


def register_global(
    rounds,
    reference,
    sample_id=None,
    roi=None,
    upsample_factor=100,
    align_by_block=True,
    block_size=128,
    tolerance=0.1,
    background_sigma=3.0,
    save=False,
    out_dir=None,
    method="pyhim_block",
):
    """
    Array-first 2D global registration.

    Parameters are intentionally close to pyHiM's current 2D registration
    defaults, but I/O is optional and explicit.
    """
    if method not in ("pyhim_block", "phase_cross_correlation"):
        raise ValueError(f"Unsupported global registration method: {method}")

    use_block = align_by_block
    if method == "phase_cross_correlation":
        use_block = False

    if all(isinstance(bundle, RoundBundle) for bundle in _ensure_rounds_dict(rounds).values()):
        round_bundles = rounds
    elif _looks_like_path_rounds(rounds):
        round_bundles = _load_round_bundles_from_paths(rounds, reference=reference)
    else:
        round_bundles = _prepare_round_bundles(rounds, reference=reference)

    result = _register_2d_round_bundles(
        round_bundles,
        reference=reference,
        sample_id=sample_id,
        roi=roi,
        upsample_factor=upsample_factor,
        align_by_block=use_block,
        block_size=block_size,
        tolerance=tolerance,
        background_sigma=background_sigma,
    )

    if save not in (False, None, "none"):
        save_registration_2d_result(result, out_dir=out_dir, save=save)
    return result


def save_registration_2d_result(result, out_dir=None, save="all"):
    save_mode = _normalize_save_mode(save)
    if save_mode is None:
        result.out_dir = None
        result.shift_json_path = None
        result.shift_table_path = None
        return result.to_dict()

    out_root = _resolve_result_out_dir(result, out_dir=out_dir)
    data_dir = _ensure_writable_output_dir(out_root)

    for round_name, round_result in result.rounds.items():
        fiducial_token = _name_token(round_result.fiducial, f"{round_name}_fiducial_2d")
        round_result.registered_path = _save_array(
            _registered_path(data_dir, fiducial_token),
            round_result.registered_fiducial,
        )

        if (
            save_mode == "all"
            and round_name != result.reference
            and round_result.reference_preprocessed is not None
        ):
            round_result.overlay_corrected_path = _save_overlay_png(
                round_result.reference_preprocessed,
                round_result.moving_preprocessed_shifted,
                _overlay_path(data_dir, fiducial_token),
            )
            round_result.reference_difference_path = _save_reference_difference_png(
                round_result.reference_preprocessed,
                round_result.moving_preprocessed_shifted,
                round_result.moving_preprocessed,
                _reference_diff_path(data_dir, fiducial_token),
            )
        else:
            round_result.overlay_corrected_path = None
            round_result.reference_difference_path = None

        for image_name, image_result in round_result.images.items():
            image_token = _image_output_token(
                round_name,
                image_name,
                image_result.input_image,
            )
            image_result.registered_path = _save_array(
                _registered_path(data_dir, image_token),
                image_result.registered,
            )

    result.out_dir = str(out_root)
    result.shift_json_path = _save_shifts_json(data_dir, result)
    result.shift_table_path = _save_shifts_table(data_dir, result)
    return result.to_dict()


def register_2d(
    rounds,
    reference,
    out_dir=None,
    sample_id=None,
    roi=None,
    upsample_factor=100,
    align_by_block=True,
    block_size=128,
    tolerance=0.1,
    background_sigma=3.0,
    save="all",
):
    """
    Register multiple rounds of 2D projected images to a reference round.

    Notes
    -----
    The stored shift vector follows pyHiM's current convention. To preserve
    output compatibility, `shifts.table` keeps the historical column names
    `shift_x` and `shift_y` while writing the two components in the same order
    as pyHiM currently stores them.
    """
    round_bundles = _load_round_bundles_from_paths(rounds, reference=reference)
    result = _register_2d_round_bundles(
        round_bundles,
        reference=reference,
        sample_id=sample_id,
        roi=roi,
        upsample_factor=upsample_factor,
        align_by_block=align_by_block,
        block_size=block_size,
        tolerance=tolerance,
        background_sigma=background_sigma,
    )
    resolved_out_dir = (
        Path(out_dir)
        if out_dir is not None
        else _resolve_default_out_dir(round_bundles[reference].fiducial.path)
    )
    return save_registration_2d_result(result, out_dir=resolved_out_dir, save=save)


__all__ = [
    "register_global",
    "register_2d_arrays",
    "save_registration_2d_result",
    "register_2d",
]
