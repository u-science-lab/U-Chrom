from __future__ import annotations

import json
import math
import os
import uuid
import warnings
from pathlib import Path
import site

import numpy as np
import pandas as pd
from astropy.convolution import Gaussian2DKernel, convolve
from astropy.stats import SigmaClip, gaussian_fwhm_to_sigma
from photutils.background import Background2D, MedianBackground
from photutils.segmentation import SegmentationImage, deblend_sources, detect_sources
from scipy import ndimage as ndi
from scipy.ndimage import gaussian_filter, shift as ndi_shift
from scipy.spatial import Voronoi
from skimage import exposure, measure
from skimage.feature import peak_local_max
from skimage.segmentation import watershed
from skimage.util.apply_parallel import apply_parallel

from uchrom.im._base import MaskResult, ensure_2d_array, ensure_3d_array
from uchrom.im.reg.register_2d import _image_adjust


PYHIM_MODEL_NAMES = {
    "mask_2d": "DAPI_2D_stardist_nc14_nrays64_epochs40_grid2",
    "mask_3d": "DAPI_3D_stardist_17032021_deconvolved",
    "localize_3d": "PSF_3D_stardist_20210618_simu_deconvolved_thresh_0_01",
}

PYHIM_LOCALIZATION_COLUMNS = [
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


def _repo_root():
    return Path(__file__).resolve().parents[2]


def _existing_dirs(paths):
    unique = []
    seen = set()
    for path in paths:
        if path is None:
            continue
        resolved = Path(path)
        key = str(resolved)
        if key in seen or not resolved.exists() or not resolved.is_dir():
            continue
        seen.add(key)
        unique.append(resolved)
    return unique


def _site_model_roots():
    roots = []
    try:
        roots.extend(site.getsitepackages())
    except AttributeError:
        pass
    try:
        user_site = site.getusersitepackages()
    except AttributeError:
        user_site = None
    if user_site:
        roots.append(user_site)
    return [Path(root) / "stardist_models" for root in roots]


def _candidate_model_roots():
    repo_root = _repo_root()
    env_root = os.environ.get("PYHIM_STARDIST_MODELS") or os.environ.get(
        "UCHROM_PYHIM_STARDIST_MODELS"
    )
    return _existing_dirs(
        [
            Path(env_root) if env_root else None,
            *_site_model_roots(),
            repo_root / "stardist_models",
            repo_root.parent / "pyHiM_ref" / "src" / "stardist_models",
            repo_root.parent.parent / "pyHiM_ref" / "src" / "stardist_models",
        ]
    )


def resolve_pyhim_model(model_kind, model_path=None, model_root=None, model_name=None):
    default_name = PYHIM_MODEL_NAMES[model_kind]

    if model_path is not None:
        candidate = Path(model_path)
        if candidate.is_file():
            candidate = candidate.parent
        if not candidate.exists():
            raise FileNotFoundError(f"StarDist model path does not exist: {candidate}")
        if not candidate.is_dir():
            raise ValueError(f"StarDist model path must be a directory: {candidate}")
        return str(candidate.parent), candidate.name

    if model_root is not None:
        candidate_root = Path(model_root)
        candidate_name = default_name if model_name is None else str(model_name)
        candidate_dir = candidate_root / candidate_name
        if candidate_dir.exists():
            return str(candidate_root), candidate_name
        if candidate_root.exists() and (candidate_root / "config.json").exists():
            return str(candidate_root.parent), candidate_root.name
        raise FileNotFoundError(
            f"Could not find StarDist model '{candidate_name}' inside: {candidate_root}"
        )

    if model_name is not None:
        for root in _candidate_model_roots():
            candidate_dir = root / str(model_name)
            if candidate_dir.exists():
                return str(root), str(model_name)
    else:
        for root in _candidate_model_roots():
            candidate_dir = root / default_name
            if candidate_dir.exists():
                return str(root), default_name

    searched = ", ".join(str(root) for root in _candidate_model_roots())
    raise FileNotFoundError(
        f"Could not resolve pyHiM StarDist model '{model_name or default_name}'. "
        f"Searched roots: {searched}"
    )


def _load_shift_mapping(source):
    if source is None or hasattr(source, "rounds"):
        return None
    if isinstance(source, dict):
        return source
    if isinstance(source, (str, Path)):
        path = Path(source)
        if not path.exists() or path.suffix.lower() != ".json":
            return None
        with path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        if isinstance(payload, dict):
            return payload
    return None


def _shift_from_mapping(mapping, round_name, roi=None):
    if mapping is None or round_name is None:
        return None

    nested = mapping
    if roi is not None:
        roi_key = f"ROI:{roi}"
        roi_payload = mapping.get(roi_key)
        if isinstance(roi_payload, dict):
            nested = roi_payload
    elif len(mapping) == 1:
        only_key = next(iter(mapping))
        only_value = mapping[only_key]
        if str(only_key).startswith("ROI:") and isinstance(only_value, dict):
            nested = only_value

    shift = nested.get(round_name)
    if shift is None:
        return None
    shift = np.asarray(shift, dtype=np.float64).ravel()
    if shift.size < 2:
        return None
    return np.array([shift[0], shift[1]], dtype=np.float64)


def _require_stardist():
    try:
        from csbdeep.data import PadAndCropResizer
        from csbdeep.utils import normalize
        from stardist.models import StarDist2D, StarDist3D
    except ImportError as exc:
        raise ImportError(
            "pyHiM StarDist backends require 'stardist' and 'csbdeep'. "
            "Install them in the U-Chrom environment before using pyHiM-aligned "
            "mask/localization methods."
        ) from exc
    return StarDist2D, StarDist3D, normalize, PadAndCropResizer


def _optional_apifish_fit_subpixel():
    try:
        from apifish.detection.spot_modeling import fit_subpixel
    except ImportError:
        try:
            from apifish.identification.spot_modeling import fit_subpixel
        except ImportError:
            return None
    return fit_subpixel


def _optional_apifish_projection():
    try:
        from apifish.stack import projection
    except ImportError:
        try:
            from apifish.image import projection
        except ImportError:
            return None
    return projection


def labels_to_properties(labels, intensity_image):
    labels = np.asarray(labels)
    intensity_image = np.asarray(intensity_image)
    rows = []
    for region in measure.regionprops(labels.astype(np.int32), intensity_image=intensity_image):
        row = {
            "label": int(region.label),
            "area": int(region.area),
            "max_intensity": float(getattr(region, "intensity_max", region.max_intensity)),
            "mean_intensity": float(region.mean_intensity),
        }
        centroid = region.centroid
        if labels.ndim == 2:
            row.update({"y": float(centroid[0]), "x": float(centroid[1])})
        else:
            row.update(
                {
                    "z": float(centroid[0]),
                    "y": float(centroid[1]),
                    "x": float(centroid[2]),
                }
            )
        rows.append(row)
    return pd.DataFrame(rows)


def _segmentation_to_labels(segmentation):
    if segmentation is None:
        return None
    if isinstance(segmentation, SegmentationImage):
        return np.asarray(segmentation.data, dtype=np.int32)
    return np.asarray(segmentation, dtype=np.int32)


def _filter_segmentation_labels(segmentation, area_min=None, area_max=None):
    labels = _segmentation_to_labels(segmentation)
    if labels is None:
        return np.zeros((0, 0), dtype=np.int32)
    if labels.size == 0:
        return labels.astype(np.int32)

    filtered = np.zeros_like(labels, dtype=np.int32)
    next_label = 1
    for region in measure.regionprops(labels):
        area = int(region.area)
        if area_min is not None and area < int(area_min):
            continue
        if area_max is not None and area > int(area_max):
            continue
        filtered[labels == region.label] = next_label
        next_label += 1
    return filtered


def reinterpolate_z(stack, z_binning=None):
    stack = ensure_3d_array(stack, source="pyHiM 3D input")
    if z_binning is None or int(z_binning) <= 1:
        return np.asarray(stack)
    indices = range(0, stack.shape[0], int(z_binning))
    return np.asarray(stack[list(indices), :, :])


def apply_xy_shift_3d(stack, shift_yx):
    stack = ensure_3d_array(stack, source="pyHiM 3D input")
    if shift_yx is None:
        return np.asarray(stack)
    shift_yx = np.asarray(shift_yx, dtype=float).ravel()
    if shift_yx.size < 2:
        raise ValueError(f"shift_yx must contain 2 values, got: {shift_yx}")
    return ndi_shift(stack, shift=[0.0, float(shift_yx[0]), float(shift_yx[1])])


def remove_inhomogeneous_background_3d(stack, box_size=(64, 64), filter_size=(3, 3)):
    stack = np.asarray(stack, dtype=np.float64)
    output = np.zeros_like(stack, dtype=np.float64)
    sigma_clip = SigmaClip(sigma=3.0)
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


def preprocess_3d_image(stack, lower_threshold=0.99, higher_threshold=0.9999):
    stack = ensure_3d_array(stack, source="pyHiM 3D input")
    image = exposure.rescale_intensity(np.asarray(stack), out_range=(0, 1))
    image = remove_inhomogeneous_background_3d(image)
    image, _, _, _, _ = _image_adjust(
        image,
        lower_threshold=lower_threshold,
        higher_threshold=higher_threshold,
    )
    return np.asarray(image, dtype=np.float32)


def crop_to_focal_volume(stack, block_size_xy=128, z_window=7):
    stack = ensure_3d_array(stack, source="pyHiM 3D input")
    projection = _optional_apifish_projection()
    if projection is not None:
        _, z_range, _ = projection.reinterpolate_focal_plane(
            stack,
            block_size_xy=int(block_size_xy),
            window=int(z_window),
        )
        z_indices = list(z_range[1])
        z_offset = int(z_indices[0]) if z_indices else 0
        return np.asarray(stack[z_indices, :, :]), z_offset

    std_per_plane = np.array([float(np.std(stack[z])) for z in range(stack.shape[0])])
    focus_plane = int(np.argmax(std_per_plane))
    zmin = max(0, focus_plane - int(z_window))
    zmax = min(stack.shape[0], focus_plane + int(z_window) + 1)
    warnings.warn(
        "apifish is not installed; using a simple focal-plane fallback instead of "
        "pyHiM's block-wise focal-plane interpolation.",
        RuntimeWarning,
        stacklevel=2,
    )
    return np.asarray(stack[zmin:zmax, :, :]), zmin


def _filter_label_areas_inplace(segmentation, area_min=None, area_max=None):
    if segmentation is None:
        return None
    if getattr(segmentation, "nlabels", 0) <= 0:
        return segmentation
    for label_id in list(segmentation.labels):
        area = segmentation.get_area(label_id)
        if area_min is not None and area < int(area_min):
            segmentation.remove_label(label=label_id)
            continue
        if area_max is not None and area > int(area_max):
            segmentation.remove_label(label=label_id)
    if getattr(segmentation, "nlabels", 0) > 0:
        segmentation.relabel_consecutive()
    return segmentation


def segment_mask_2d_pyhim(
    image,
    background_method="stardist",
    threshold_over_std=1.0,
    background_sigma=3.0,
    fwhm=3.0,
    area_min=50,
    area_max=500,
    tessellation=False,
    model_path=None,
    model_root=None,
    model_name=None,
    **kwargs,
):
    image = ensure_2d_array(image, source="pyHiM 2D mask input")
    background_method = str(background_method).lower()
    raw_labels = None
    meta = {
        "label_semantics": "filtered_instances_after_border_area_filter",
    }

    if background_method in ("flat", "inhomogeneous"):
        sigma_clip = SigmaClip(sigma=background_sigma)
        bkg_estimator = MedianBackground()
        bkg = Background2D(
            image,
            (64, 64),
            filter_size=(3, 3),
            sigma_clip=sigma_clip,
            bkg_estimator=bkg_estimator,
        )
        threshold = bkg.background + (float(threshold_over_std) * bkg.background_rms)
        sigma = float(fwhm) * gaussian_fwhm_to_sigma
        kernel = Gaussian2DKernel(sigma, x_size=3, y_size=3)
        kernel.normalize()
        data = convolve(image, kernel, mask=None, normalize_kernel=True)
        segmentation = detect_sources(data, threshold, npixels=int(area_min))
        if segmentation is None or getattr(segmentation, "nlabels", 0) <= 0:
            labels = np.zeros_like(image, dtype=np.int32)
        else:
            segmentation.remove_border_labels(border_width=10)
            if getattr(segmentation, "nlabels", 0) <= 0:
                labels = np.zeros_like(image, dtype=np.int32)
            else:
                segmentation = deblend_sources(
                    data,
                    segmentation,
                    npixels=int(area_min),
                    nlevels=32,
                    contrast=0.001,
                    relabel=True,
                    progress_bar=False,
                )
                segmentation = _filter_label_areas_inplace(
                    segmentation,
                    area_min=area_min,
                    area_max=area_max,
                )
                labels = _segmentation_to_labels(segmentation)
    elif background_method == "stardist":
        StarDist2D, _, normalize, _ = _require_stardist()
        basedir, resolved_name = resolve_pyhim_model(
            "mask_2d",
            model_path=model_path,
            model_root=model_root,
            model_name=model_name,
        )
        model = StarDist2D(None, name=resolved_name, basedir=basedir)
        normalized = normalize(image, 1, 99.8, axis=(0, 1))
        labeled, _ = model.predict_instances(normalized)
        raw_labels = np.asarray(labeled, dtype=np.int32)
        segmentation = SegmentationImage(labeled)
        segmentation.remove_border_labels(border_width=10)
        segmentation = _filter_label_areas_inplace(
            segmentation,
            area_min=area_min,
            area_max=area_max,
        )
        labels = _segmentation_to_labels(segmentation)
        meta.update(
            {
                "model_root": str(basedir),
                "model_name": resolved_name,
                "model_dir": str(Path(basedir) / resolved_name),
                "raw_label_semantics": "stardist_instances_before_border_area_filter",
            }
        )
    else:
        raise ValueError(
            f"Unsupported pyHiM 2D mask background_method: {background_method}"
        )

    if labels is None or labels.size == 0:
        labels = np.zeros_like(image, dtype=np.int32)

    if tessellation:
        labels = tessellate_masks(labels)

    labels = np.asarray(labels, dtype=np.int32)
    return MaskResult(
        labels=labels,
        properties=labels_to_properties(labels, image),
        method=f"pyhim_mask_2d:{background_method}",
        meta=meta,
        raw_labels=raw_labels,
    )


def _segment_2d_image_by_thresholding(
    image_2d,
    threshold_over_std=10,
    sigma=3,
    area_min=3,
    area_max=1000,
    nlevels=64,
    contrast=0.001,
):
    image_2d = ensure_2d_array(image_2d, source="pyHiM 2D thresholding input")
    sigma = float(sigma)
    kernel_size = max(3, int(np.ceil(sigma)))
    threshold = np.full(image_2d.shape, float(threshold_over_std) * image_2d.max() / 100.0)
    kernel = Gaussian2DKernel(sigma, x_size=kernel_size, y_size=kernel_size)
    kernel.normalize()
    data = convolve(image_2d, kernel, mask=None, normalize_kernel=True)
    segmentation = detect_sources(data, threshold, npixels=int(area_min))
    if segmentation is None or getattr(segmentation, "nlabels", 0) <= 0:
        return np.zeros_like(image_2d, dtype=np.int32)
    segmentation.remove_border_labels(border_width=10)
    if getattr(segmentation, "nlabels", 0) <= 0:
        return np.zeros_like(image_2d, dtype=np.int32)
    segmentation = deblend_sources(
        data,
        segmentation,
        npixels=int(area_min),
        nlevels=int(nlevels),
        contrast=float(contrast),
        relabel=True,
        mode="exponential",
        progress_bar=False,
    )
    labels = _filter_segmentation_labels(
        segmentation,
        area_min=area_min,
        area_max=area_max,
    )
    labels[labels > 0] = 1
    return labels.astype(np.int32)


def _deblend_3d_segmentation(binary):
    binary = np.asarray(binary) > 0
    try:
        distance = apply_parallel(ndi.distance_transform_edt, binary)
    except RuntimeError:
        distance = ndi.distance_transform_edt(binary)
    coords = peak_local_max(distance, footprint=np.ones((10, 10, 25)), labels=binary)
    if len(coords) == 0:
        return measure.label(binary).astype(np.int32)
    mask = np.zeros(distance.shape, dtype=bool)
    mask[tuple(coords.T)] = True
    markers, _ = ndi.label(mask)
    labels = watershed(-distance, markers, mask=binary)
    return np.asarray(labels, dtype=np.int32)


def segment_spots_3d_thresholding(
    stack,
    threshold_over_std=5,
    sigma=3,
    area_min=10,
    area_max=250,
    nlevels=64,
    contrast=0.001,
    deblend_3d=True,
):
    stack = ensure_3d_array(stack, source="pyHiM 3D thresholding input")
    binary = np.zeros_like(stack, dtype=np.int32)
    for z in range(stack.shape[0]):
        binary[z] = _segment_2d_image_by_thresholding(
            stack[z],
            threshold_over_std=threshold_over_std,
            sigma=sigma,
            area_min=area_min,
            area_max=area_max,
            nlevels=nlevels,
            contrast=contrast,
        )
    labels = measure.label(binary)
    if deblend_3d:
        labels = _deblend_3d_segmentation(binary)
    return np.asarray(binary, dtype=np.int32), np.asarray(labels, dtype=np.int32)


def segment_spots_3d_stardist(
    stack,
    model_path=None,
    model_root=None,
    model_name=None,
):
    stack = ensure_3d_array(stack, source="pyHiM 3D StarDist input")
    _, StarDist3D, normalize, PadAndCropResizer = _require_stardist()
    basedir, resolved_name = resolve_pyhim_model(
        "localize_3d",
        model_path=model_path,
        model_root=model_root,
        model_name=model_name,
    )
    np.random.seed(6)
    model = StarDist3D(None, name=resolved_name, basedir=basedir)
    normalized = normalize(stack, 1, 99.8, axis=(0, 1, 2))
    if normalized.shape[1] < 1000:
        labels, _ = model.predict_instances(normalized)
    else:
        resizer = PadAndCropResizer()
        axes = "ZYX"
        normalized = resizer.before(normalized, axes, model._axes_div_by(axes))
        labels, _ = model.predict_instances(normalized, n_tiles=(1, 8, 8))
        labels = resizer.after(labels, axes)
    mask = np.array(labels > 0, dtype=np.int32)
    return mask, np.asarray(labels, dtype=np.int32)


def segment_mask_3d_pyhim(
    stack,
    model_path=None,
    model_root=None,
    model_name=None,
    z_binning=None,
    shift_yx=None,
    **kwargs,
):
    stack = ensure_3d_array(stack, source="pyHiM 3D mask input")
    stack = reinterpolate_z(stack, z_binning=z_binning)
    stack = apply_xy_shift_3d(stack, shift_yx=shift_yx)

    _, StarDist3D, normalize, PadAndCropResizer = _require_stardist()
    basedir, resolved_name = resolve_pyhim_model(
        "mask_3d",
        model_path=model_path,
        model_root=model_root,
        model_name=model_name,
    )
    model = StarDist3D(None, name=resolved_name, basedir=basedir)
    normalized = normalize(stack, 1, 99.8, axis=(0, 1, 2))
    if normalized.shape[1] < 351:
        labels, _ = model.predict_instances(normalized)
    else:
        resizer = PadAndCropResizer()
        axes = "ZYX"
        normalized = resizer.before(normalized, axes, model._axes_div_by(axes))
        labels, _ = model.predict_instances(normalized, n_tiles=(1, 8, 8))
        labels = resizer.after(labels, axes)

    labels = relabel_masks_3d(labels)
    return MaskResult(
        labels=np.asarray(labels, dtype=np.int32),
        properties=labels_to_properties(labels, stack),
        method="pyhim_mask_3d:stardist",
        meta={
            "model_root": str(basedir),
            "model_name": resolved_name,
            "model_dir": str(Path(basedir) / resolved_name),
        },
    )


def relabel_masks_3d(labeled_img):
    labeled_img = np.asarray(labeled_img)
    relabeled, _ = ndi.label(
        labeled_img,
        structure=np.ones((3, 3, 3), dtype=np.int32),
        output=np.int32,
    )
    return np.asarray(relabeled, dtype=np.int32)


def tessellate_masks(labels):
    labels = np.asarray(labels, dtype=np.int32)
    if labels.ndim != 2:
        raise ValueError(f"Tessellation expects a 2D mask, got shape {labels.shape}")
    if labels.size == 0 or np.max(labels) <= 1:
        return labels

    regions = measure.regionprops(labels)
    if len(regions) < 2:
        return labels

    centroids = []
    for region in regions:
        y0, x0 = region.centroid
        centroids.append([x0, y0])

    xy = np.asarray(centroids, dtype=float)
    x_center, y_center = np.array(labels.shape) / 2.0
    x_max, y_max = np.array(labels.shape, dtype=float)
    corners = np.array(
        [
            [x_center - 100 * x_max, y_center - 100 * y_max],
            [x_center + 100 * x_max, y_center - 100 * y_max],
            [x_center - 100 * x_max, y_center + 100 * y_max],
            [x_center + 100 * x_max, y_center + 100 * y_max],
        ],
        dtype=float,
    )

    voronoi = Voronoi(np.vstack([xy, corners]))
    mask_binary = (labels > 0).astype(float)
    mask_blurred = gaussian_filter(mask_binary, sigma=20)
    mask_blurred = mask_blurred > 0.01
    mask_voronoi = np.zeros(labels.shape, dtype=np.int32)

    ny, nx = labels.shape
    x, y = np.meshgrid(np.arange(nx), np.arange(ny))
    points = np.vstack((x.ravel(), y.ravel())).T

    for label_index in range(len(regions)):
        region_id = label_index + 1
        region_idx = voronoi.point_region[label_index]
        vertex_ids = voronoi.regions[region_idx]
        if not vertex_ids or any(idx == -1 for idx in vertex_ids):
            continue
        vertices = voronoi.vertices[vertex_ids]
        from matplotlib.path import Path as MplPath

        polygon = MplPath(vertices)
        inside = polygon.contains_points(points).reshape((ny, nx))
        mask_voronoi[inside & mask_blurred] = region_id

    return np.asarray(mask_voronoi, dtype=np.int32)


def get_spot_properties(segmented_image_3d, image_3d_aligned, threshold=10, brightest=1000):
    labels = np.asarray(segmented_image_3d, dtype=np.int32)
    image = np.asarray(image_3d_aligned, dtype=float)
    if labels.shape != image.shape:
        raise ValueError(
            "segmented_image_3d and image_3d_aligned must have the same shape, "
            f"got {labels.shape} and {image.shape}"
        )

    foreground = labels > 0
    if not np.any(foreground):
        return [], [], [], [], [], [], [], [], []

    label_values = labels[foreground]
    region_labels, inverse = np.unique(label_values, return_inverse=True)
    n_regions = len(region_labels)
    intensities = image[foreground]
    area = np.bincount(inverse, minlength=n_regions).astype(float)

    peak0 = np.full(n_regions, -np.inf, dtype=float)
    np.maximum.at(peak0, inverse, intensities)

    if brightest in (None, "None"):
        selection = np.arange(n_regions)
    else:
        last_to_keep = min(int(brightest), n_regions)
        if last_to_keep <= 0:
            return [], [], [], [], [], [], [], [], []
        if last_to_keep >= n_regions:
            selection = np.arange(n_regions)
        else:
            highest_peak_value = np.partition(peak0, -last_to_keep)[-last_to_keep]
            selection = np.nonzero(peak0 > highest_peak_value)[0]
            if selection.size == 0:
                selection = np.argsort(peak0)[-last_to_keep:]

    z_coord, y_coord, x_coord = np.nonzero(foreground)
    weighted_sum = np.bincount(inverse, weights=intensities, minlength=n_regions)
    sum_z = np.bincount(inverse, weights=z_coord * intensities, minlength=n_regions)
    sum_y = np.bincount(inverse, weights=y_coord * intensities, minlength=n_regions)
    sum_x = np.bincount(inverse, weights=x_coord * intensities, minlength=n_regions)
    geom_z = np.bincount(inverse, weights=z_coord, minlength=n_regions) / area
    geom_y = np.bincount(inverse, weights=y_coord, minlength=n_regions) / area
    geom_x = np.bincount(inverse, weights=x_coord, minlength=n_regions) / area

    centroid_z = np.divide(
        sum_z,
        weighted_sum,
        out=geom_z.copy(),
        where=weighted_sum != 0,
    )
    centroid_y = np.divide(
        sum_y,
        weighted_sum,
        out=geom_y.copy(),
        where=weighted_sum != 0,
    )
    centroid_x = np.divide(
        sum_x,
        weighted_sum,
        out=geom_x.copy(),
        where=weighted_sum != 0,
    )

    mins = np.full((3, n_regions), np.iinfo(np.int32).max, dtype=np.int64)
    maxs = np.full((3, n_regions), -1, dtype=np.int64)
    for axis, coord in enumerate((z_coord, y_coord, x_coord)):
        np.minimum.at(mins[axis], inverse, coord)
        np.maximum.at(maxs[axis], inverse, coord)
    bbox_shape = maxs - mins + 1
    bbox_area = np.prod(bbox_shape, axis=0).astype(float)
    extent = np.divide(area, bbox_area, out=np.zeros_like(area), where=bbox_area != 0)
    ndim = labels.ndim
    equivalent_diameter = 2.0 * np.power(
        area * math.gamma(ndim / 2.0 + 1.0) / (math.pi ** (ndim / 2.0)),
        1.0 / ndim,
    )

    peak = peak0[selection].astype(float).tolist()
    sharpness = extent[selection].astype(float).tolist()
    roundness1 = equivalent_diameter[selection].astype(float).tolist()
    roundness2 = extent[selection].astype(float).tolist()
    npix = area[selection].astype(int).tolist()
    sky = [0.0 for _ in selection]
    flux = [100.0 * value / float(threshold) for value in peak]

    mag = [-2.5 * np.log10(value) for value in flux]
    spots = np.zeros((len(selection), 3), dtype=np.int64)
    spots[:, 0] = centroid_z[selection].astype(np.int64)
    spots[:, 1] = centroid_y[selection].astype(np.int64)
    spots[:, 2] = centroid_x[selection].astype(np.int64)

    return spots, sharpness, roundness1, roundness2, npix, sky, peak, flux, mag


def fit_subpixel_spots(
    image_3d_aligned,
    spots,
    pixel_size_xy=0.1,
    pixel_size_z=0.25,
    z_binning=1,
    psf_z=500,
    psf_yx=200,
    require_model=False,
):
    if len(spots) == 0:
        return np.zeros((0, 3), dtype=float)

    fit_subpixel = _optional_apifish_fit_subpixel()
    if fit_subpixel is None:
        if require_model:
            raise ImportError(
                "pyHiM 3D localization requires 'apifish' for subpixel fitting. "
                "Install apifish or call localize(..., subpixel_refine=False)."
            )
        warnings.warn(
            "apifish is not installed; falling back to integer spot coordinates "
            "instead of pyHiM subpixel fitting.",
            RuntimeWarning,
            stacklevel=2,
        )
        return np.asarray(spots, dtype=float)

    image_3d_aligned = exposure.rescale_intensity(
        np.asarray(image_3d_aligned),
        out_range=(0, 1),
    )
    voxel_size_z = float(1000.0 * float(pixel_size_z) * float(z_binning))
    voxel_size_yx = float(1000.0 * float(pixel_size_xy))
    try:
        spots_subpixel = fit_subpixel(
            image_3d_aligned,
            np.asarray(spots, dtype=np.int64),
            voxel_size_z=voxel_size_z,
            voxel_size_yx=voxel_size_yx,
            psf_z=float(psf_z),
            psf_yx=float(psf_yx),
        )
    except TypeError:
        spots_subpixel = fit_subpixel(
            image_3d_aligned,
            np.asarray(spots, dtype=np.int64),
            (voxel_size_z, voxel_size_yx, voxel_size_yx),
            (float(psf_z), float(psf_yx), float(psf_yx)),
        )
    return np.asarray(spots_subpixel, dtype=float)


def global_shift_for_round(global_registration, round_name, roi=None):
    mapping = _load_shift_mapping(global_registration)
    shift = _shift_from_mapping(mapping, round_name, roi=roi)
    if shift is not None:
        return shift
    if global_registration is None:
        return np.array([0.0, 0.0], dtype=np.float64)
    rounds = getattr(global_registration, "rounds", {})
    if round_name not in rounds:
        return np.array([0.0, 0.0], dtype=np.float64)
    shift = np.asarray(rounds[round_name].shift, dtype=np.float64).ravel()
    if shift.size < 2:
        return np.array([0.0, 0.0], dtype=np.float64)
    return np.array([shift[0], shift[1]], dtype=np.float64)


def build_pyhim_3d_localization_rows(
    stack,
    round_name,
    roi=None,
    global_shift_yx=None,
    threshold_over_std=5.0,
    backend="stardist",
    reduce_planes=True,
    z_window=7,
    block_size_xy=128,
    lower_threshold=0.99,
    higher_threshold=0.9999,
    area_min=10,
    area_max=250,
    sigma=3,
    box_size=32,
    nlevels=64,
    contrast=0.001,
    brightest=1100,
    pixel_size_xy=0.1,
    pixel_size_z=0.25,
    z_binning=1,
    psf_z=500,
    psf_yx=200,
    model_path=None,
    model_root=None,
    model_name=None,
    subpixel_refine=True,
    cell_id=0,
    **kwargs,
):
    stack = ensure_3d_array(stack, source=f"{round_name} barcode stack")
    stack = reinterpolate_z(stack, z_binning=z_binning)
    backend = str(backend).lower()
    z_offset = 0
    if reduce_planes:
        stack, z_offset = crop_to_focal_volume(
            stack,
            block_size_xy=block_size_xy,
            z_window=z_window,
        )

    image_3d = np.asarray(stack)
    if backend != "stardist":
        image_3d = preprocess_3d_image(
            image_3d,
            lower_threshold=lower_threshold,
            higher_threshold=higher_threshold,
        )
    if global_shift_yx is not None:
        image_3d = apply_xy_shift_3d(image_3d, global_shift_yx)

    if backend == "stardist":
        _, segmented_image_3d = segment_spots_3d_stardist(
            image_3d,
            model_path=model_path,
            model_root=model_root,
            model_name=model_name,
        )
    elif backend in ("thresholding", "threshold"):
        _, segmented_image_3d = segment_spots_3d_thresholding(
            image_3d,
            threshold_over_std=threshold_over_std,
            sigma=sigma,
            area_min=area_min,
            area_max=area_max,
            nlevels=nlevels,
            contrast=contrast,
            deblend_3d=True,
        )
    else:
        raise ValueError(f"Unsupported pyHiM 3D localization backend: {backend}")

    (
        spots,
        sharpness,
        roundness1,
        roundness2,
        npix,
        sky,
        peak,
        flux,
        mag,
    ) = get_spot_properties(
        segmented_image_3d,
        image_3d,
        threshold=threshold_over_std,
        brightest=brightest,
    )

    if len(spots) == 0:
        return []

    if subpixel_refine:
        spots_subpixel = fit_subpixel_spots(
            image_3d,
            spots,
            pixel_size_xy=pixel_size_xy,
            pixel_size_z=pixel_size_z,
            z_binning=z_binning,
            psf_z=psf_z,
            psf_yx=psf_yx,
            require_model=True,
        )
    else:
        spots_subpixel = np.asarray(spots, dtype=float)

    barcode = _barcode_from_round(round_name)
    roi_value = _roi_value(roi)
    rows = []
    for idx in range(spots_subpixel.shape[0]):
        z = float(spots_subpixel[idx, 0]) + float(z_offset)
        y = float(spots_subpixel[idx, 1])
        x = float(spots_subpixel[idx, 2])
        rows.append(
            {
                "Buid": str(uuid.uuid4()),
                "ROI #": roi_value,
                "CellID #": int(cell_id),
                "Barcode #": barcode,
                "id": int(idx),
                "zcentroid": z,
                "xcentroid": x,
                "ycentroid": y,
                "sharpness": float(sharpness[idx]),
                "roundness1": float(roundness1[idx]),
                "roundness2": float(roundness2[idx]),
                "npix": int(npix[idx]),
                "sky": float(sky[idx]),
                "peak": float(peak[idx]),
                "flux": float(flux[idx]),
                "mag": float(mag[idx]),
                "round": str(round_name),
                "label": str(round_name),
            }
        )
    return rows


def _barcode_from_round(round_name):
    digits = "".join(ch for ch in str(round_name) if ch.isdigit())
    return int(digits) if digits else -1


def _roi_value(roi):
    try:
        return int(roi)
    except (TypeError, ValueError):
        return -1
