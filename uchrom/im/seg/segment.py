from pathlib import Path

import numpy as np
from skimage import filters, measure, morphology

from uchrom.im._base import MaskResult
from uchrom.im._pyhim import (
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


def _segment_pyhim(image_or_stack, method, **kwargs):
    image = np.asarray(image_or_stack)
    if image.ndim not in (2, 3):
        raise ValueError(f"pyHiM segmentation expects a 2D image or 3D stack, got {image.shape}.")

    if method == "pyhim_mask_2d":
        if image.ndim != 2:
            raise ValueError(f"method='pyhim_mask_2d' expects 2D input, got {image.shape}.")
        return segment_mask_2d_pyhim(image, **kwargs)

    if method == "pyhim_mask_3d":
        if image.ndim != 3:
            raise ValueError(f"method='pyhim_mask_3d' expects 3D input, got {image.shape}.")
        return segment_mask_3d_pyhim(image, **kwargs)

    if image.ndim == 2:
        return segment_mask_2d_pyhim(image, **kwargs)
    return segment_mask_3d_pyhim(image, **kwargs)


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
        return _segment_threshold(image_or_stack, **kwargs)
    if method == "stardist":
        return _segment_stardist(image_or_stack, **kwargs)
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
    if result.properties is not None:
        result.properties.to_csv(data_dir / f"{name}_properties.csv", index=False)
    result.saved_path = str(npy_path)
    return result


__all__ = ["segment", "save_mask_result"]
