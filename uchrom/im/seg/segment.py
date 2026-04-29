from pathlib import Path

import numpy as np
from scipy.ndimage import shift as shift_image
from skimage import filters, measure, morphology

from uchrom.im._base import Image2D, Image3D, MaskResult
from uchrom.im._pyhim import (
    global_shift_for_round,
    labels_to_properties,
    segment_mask_2d_pyhim,
    segment_mask_3d_pyhim,
)


def _threshold_image(image, threshold=None, threshold_over_std=None):
    image = np.asarray(image)
    if threshold is not None:
        return float(threshold)
    if threshold_over_std is not None:
        return float(np.nanmean(image) + threshold_over_std * np.nanstd(image))
    finite = image[np.isfinite(image)]
    if finite.size == 0:
        raise ValueError("Cannot segment an image with no finite values.")
    if np.nanmin(finite) == np.nanmax(finite):
        return float(np.nanmax(finite) + 1)
    return float(filters.threshold_otsu(finite))


def _filter_labels(labels, intensity_image, area_min=None, area_max=None):
    labels = np.asarray(labels)
    filtered = np.zeros_like(labels, dtype=np.int32)
    next_label = 1
    for region in measure.regionprops(labels, intensity_image=intensity_image):
        area = int(region.area)
        if area_min is not None and area < int(area_min):
            continue
        if area_max is not None and area > int(area_max):
            continue
        filtered[labels == region.label] = next_label
        next_label += 1
    return filtered, labels_to_properties(filtered, intensity_image)


def _segment_threshold(
    image_or_stack,
    threshold=None,
    threshold_over_std=None,
    area_min=None,
    area_max=None,
    clear_border=False,
):
    image = np.asarray(image_or_stack)
    if image.ndim not in (2, 3):
        raise ValueError(f"segment expects a 2D image or 3D stack, got shape {image.shape}.")
    cutoff = _threshold_image(
        image,
        threshold=threshold,
        threshold_over_std=threshold_over_std,
    )
    binary = np.asarray(image > cutoff)
    if area_min is not None:
        binary = morphology.remove_small_objects(binary, min_size=int(area_min))
    labels = measure.label(binary)
    if clear_border:
        from skimage.segmentation import clear_border as sk_clear_border

        labels = sk_clear_border(labels)
    labels, properties = _filter_labels(
        labels,
        intensity_image=image,
        area_min=area_min,
        area_max=area_max,
    )
    properties.attrs["threshold"] = cutoff
    return MaskResult(labels=labels, properties=properties, method="threshold")


def _segment_stardist(image_or_stack, model_path=None, **kwargs):
    image = np.asarray(image_or_stack)
    try:
        if image.ndim == 2:
            from stardist.models import StarDist2D

            model = StarDist2D(
                None,
                name=Path(model_path).name,
                basedir=str(Path(model_path).parent),
            )
        elif image.ndim == 3:
            from stardist.models import StarDist3D

            model = StarDist3D(
                None,
                name=Path(model_path).name,
                basedir=str(Path(model_path).parent),
            )
        else:
            raise ValueError(f"StarDist expects 2D or 3D input, got shape {image.shape}.")
    except ImportError as exc:
        raise ImportError(
            "segment(method='stardist') requires the optional 'stardist' package. "
            "Use method='pyhim' to follow pyHiM behavior with the bundled model resolver."
        ) from exc
    except TypeError as exc:
        raise ValueError("segment(method='stardist') requires an explicit model_path.") from exc

    if model_path is None:
        raise ValueError("segment(method='stardist') requires model_path.")

    labels, _ = model.predict_instances(image, **kwargs)
    labels, properties = _filter_labels(
        labels,
        intensity_image=image,
        area_min=kwargs.get("area_min"),
        area_max=kwargs.get("area_max"),
    )
    return MaskResult(
        labels=labels.astype(np.int32),
        properties=properties,
        method="stardist",
    )


def _image_payload(image_or_stack):
    if isinstance(image_or_stack, (Image2D, Image3D)):
        return (
            np.asarray(image_or_stack.data),
            dict(image_or_stack.meta),
            image_or_stack.name or image_or_stack.path,
        )
    return np.asarray(image_or_stack), {}, None


def _ensure_result_meta(result):
    meta = getattr(result, "meta", None)
    if meta is None:
        meta = {}
        result.meta = meta
    return meta


def _global_shift_for_round_compat(global_registration, round_name, roi=None):
    try:
        return global_shift_for_round(global_registration, round_name, roi=roi)
    except TypeError:
        return global_shift_for_round(global_registration, round_name)


def _resolve_pyhim_shift(
    image_meta,
    round_name=None,
    shift_yx=None,
    global_registration=None,
    coordinate_frame="raw",
    apply_global_registration=None,
):
    round_name = round_name or image_meta.get("round")
    if shift_yx is not None:
        return round_name, np.asarray(shift_yx, dtype=np.float64), "global_registered"

    if coordinate_frame == "global_registered":
        return round_name, None, "global_registered"

    if apply_global_registration is None:
        apply_global_registration = global_registration is not None and round_name is not None

    if not apply_global_registration or global_registration is None or round_name is None:
        return round_name, None, "raw"

    return (
        round_name,
        _global_shift_for_round_compat(
            global_registration,
            round_name,
            roi=image_meta.get("roi"),
        ),
        "global_registered",
    )


def _segment_pyhim(image_or_stack, method, **kwargs):
    image, image_meta, source_name = _image_payload(image_or_stack)
    if image.ndim not in (2, 3):
        raise ValueError(f"pyHiM segmentation expects a 2D image or 3D stack, got {image.shape}.")

    role = kwargs.pop("role", image_meta.get("role"))
    round_name = kwargs.pop("round_name", image_meta.get("round"))
    coordinate_frame = kwargs.pop(
        "coordinate_frame",
        image_meta.get("coordinate_frame", "raw"),
    )
    global_registration = kwargs.pop("global_registration", None)
    apply_global_registration = kwargs.pop("apply_global_registration", None)
    shift_yx = kwargs.pop("shift_yx", None)
    round_name, shift_yx, output_frame = _resolve_pyhim_shift(
        image_meta,
        round_name=round_name,
        shift_yx=shift_yx,
        global_registration=global_registration,
        coordinate_frame=coordinate_frame,
        apply_global_registration=apply_global_registration,
    )

    if method == "pyhim_mask_2d":
        if image.ndim != 2:
            raise ValueError(f"method='pyhim_mask_2d' expects 2D input, got {image.shape}.")
        if shift_yx is not None:
            image = shift_image(image, shift=np.asarray(shift_yx, dtype=np.float64))
        result = segment_mask_2d_pyhim(image, **kwargs)
        result.source_name = source_name
        _ensure_result_meta(result).update(
            {
                "round": round_name,
                "role": role,
                "coordinate_frame": output_frame,
            }
        )
        if shift_yx is not None:
            result.meta["global_shift_yx"] = [float(shift_yx[0]), float(shift_yx[1])]
        return result

    if method == "pyhim_mask_3d":
        if image.ndim != 3:
            raise ValueError(f"method='pyhim_mask_3d' expects 3D input, got {image.shape}.")
        result = segment_mask_3d_pyhim(image, shift_yx=shift_yx, **kwargs)
        result.source_name = source_name
        _ensure_result_meta(result).update(
            {
                "round": round_name,
                "role": role,
                "coordinate_frame": output_frame,
            }
        )
        if shift_yx is not None:
            result.meta["global_shift_yx"] = [float(shift_yx[0]), float(shift_yx[1])]
        return result

    if image.ndim == 2:
        if shift_yx is not None:
            image = shift_image(image, shift=np.asarray(shift_yx, dtype=np.float64))
        result = segment_mask_2d_pyhim(image, **kwargs)
    else:
        result = segment_mask_3d_pyhim(image, shift_yx=shift_yx, **kwargs)

    result.source_name = source_name
    _ensure_result_meta(result).update(
        {
            "round": round_name,
            "role": role,
            "coordinate_frame": output_frame,
        }
    )
    if shift_yx is not None:
        result.meta["global_shift_yx"] = [float(shift_yx[0]), float(shift_yx[1])]
    return result


def segment(image_or_stack, method="threshold", **kwargs):
    """
    Segment 2D images or 3D stacks and return a MaskResult.

    Supported methods:
    - `threshold`: lightweight connected-components fallback
    - `stardist`: direct explicit StarDist model call
    - `pyhim`, `pyhim_mask`, `pyhim_mask_2d`, `pyhim_mask_3d`: pyHiM-aligned mask backends
    """
    method = str(method).lower()
    if method == "threshold":
        image, image_meta, source_name = _image_payload(image_or_stack)
        result = _segment_threshold(image, **kwargs)
        result.source_name = source_name
        _ensure_result_meta(result).update(image_meta)
        result.meta.setdefault("coordinate_frame", image_meta.get("coordinate_frame", "raw"))
        return result
    if method == "stardist":
        image, image_meta, source_name = _image_payload(image_or_stack)
        result = _segment_stardist(image, **kwargs)
        result.source_name = source_name
        _ensure_result_meta(result).update(image_meta)
        result.meta.setdefault("coordinate_frame", image_meta.get("coordinate_frame", "raw"))
        return result
    if method in ("pyhim", "pyhim_mask", "pyhim_mask_2d", "pyhim_mask_3d"):
        alias = "pyhim" if method in ("pyhim", "pyhim_mask") else method
        return _segment_pyhim(image_or_stack, method=alias, **kwargs)
    raise ValueError(f"Unsupported segmentation method: {method}")


def save_mask_result(result, out_dir, name="mask"):
    out_dir = Path(out_dir)
    data_dir = out_dir / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    npy_path = data_dir / f"{name}.npy"
    np.save(npy_path, result.labels)
    raw_labels = getattr(result, "raw_labels", None)
    if raw_labels is not None:
        raw_path = data_dir / f"{name}_raw_labels.npy"
        np.save(raw_path, raw_labels)
        _ensure_result_meta(result)["raw_labels_path"] = str(raw_path)
    if result.properties is not None:
        result.properties.to_csv(data_dir / f"{name}_properties.csv", index=False)
    result.saved_path = str(npy_path)
    return result


__all__ = ["segment", "save_mask_result"]
