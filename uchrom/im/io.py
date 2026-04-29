from pathlib import Path

import numpy as np
from skimage import io as skio

from uchrom.im._base import Image3D


VALID_IMAGE_SUFFIXES = (".tif", ".tiff", ".npy")


def load_image(path, squeeze=True):
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Input image not found: {path}")
    if path.suffix.lower() not in VALID_IMAGE_SUFFIXES:
        raise ValueError(f"Unsupported image suffix: {path.suffix}")
    if path.suffix.lower() == ".npy":
        image = np.load(path)
    else:
        image = skio.imread(str(path))
    if squeeze:
        image = np.asarray(image).squeeze()
    return np.asarray(image)


def _image_path_and_meta(spec, round_name, default_role, round_meta):
    if isinstance(spec, dict):
        path = spec["path"]
        image_meta = {key: value for key, value in spec.items() if key != "path"}
    else:
        path = spec
        image_meta = {}

    merged_meta = dict(round_meta)
    merged_meta.update(image_meta)
    merged_meta.setdefault("round", round_name)
    merged_meta.setdefault("role", default_role)
    return Path(path), merged_meta


def load_rounds(manifest, as_images=True):
    rounds = {}
    for round_name, round_spec in manifest.items():
        round_meta = dict(round_spec.get("meta", {}))
        fiducial_path, fiducial_meta = _image_path_and_meta(
            round_spec["fiducial"],
            round_name=round_name,
            default_role="fiducial",
            round_meta=round_meta,
        )
        fiducial_data = load_image(fiducial_path)

        images = {}
        for image_name, image_spec in round_spec.get("images", {}).items():
            image_path, image_meta = _image_path_and_meta(
                image_spec,
                round_name=round_name,
                default_role=image_name,
                round_meta=round_meta,
            )
            image_data = load_image(image_path)
            if as_images:
                images[image_name] = Image3D(
                    image_data,
                    name=image_path.stem,
                    path=str(image_path),
                    meta=image_meta,
                )
            else:
                images[image_name] = image_data

        if as_images:
            rounds[round_name] = {
                "fiducial": Image3D(
                    fiducial_data,
                    name=fiducial_path.stem,
                    path=str(fiducial_path),
                    meta=fiducial_meta,
                ),
                "images": images,
                "meta": round_meta,
            }
        else:
            rounds[round_name] = {
                "fiducial": fiducial_data,
                "images": images,
                "meta": round_meta,
            }

    return rounds


def save_array(path, array):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    np.save(path, np.asarray(array))
    return str(path)


def save_image(path, image):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    skio.imsave(str(path), np.asarray(image))
    return str(path)


def save_project(*args, **kwargs):
    from uchrom.im.prep import save_projected_array

    return save_projected_array(*args, **kwargs)


def save_registration(*args, **kwargs):
    from uchrom.im.reg import save_registration_2d_result

    return save_registration_2d_result(*args, **kwargs)


def save_localizations(*args, **kwargs):
    from uchrom.im.loc import save_localizations as save_localizations_result

    return save_localizations_result(*args, **kwargs)


def save_traces(*args, **kwargs):
    from uchrom.im.trace import save_traces as save_trace_result

    return save_trace_result(*args, **kwargs)


__all__ = [
    "load_image",
    "load_rounds",
    "save_array",
    "save_image",
    "save_project",
    "save_registration",
    "save_localizations",
    "save_traces",
]
