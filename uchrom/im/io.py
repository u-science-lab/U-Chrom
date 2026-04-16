from pathlib import Path

import numpy as np
from skimage import io as skio

from uchrom.im._base import Image2D, Image3D


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


def load_rounds(manifest, as_images=True):
    rounds = {}
    for round_name, round_spec in manifest.items():
        fiducial_spec = round_spec["fiducial"]
        fiducial_path = Path(fiducial_spec["path"] if isinstance(fiducial_spec, dict) else fiducial_spec)
        fiducial_data = load_image(fiducial_path)

        images = {}
        for image_name, image_spec in round_spec.get("images", {}).items():
            image_path = Path(image_spec["path"] if isinstance(image_spec, dict) else image_spec)
            image_data = load_image(image_path)
            if as_images:
                images[image_name] = Image3D(
                    image_data,
                    name=image_path.stem,
                    path=str(image_path),
                    meta=dict(round_spec.get("meta", {})),
                )
            else:
                images[image_name] = image_data

        if as_images:
            rounds[round_name] = {
                "fiducial": Image3D(
                    fiducial_data,
                    name=fiducial_path.stem,
                    path=str(fiducial_path),
                    meta=dict(round_spec.get("meta", {})),
                ),
                "images": images,
                "meta": dict(round_spec.get("meta", {})),
            }
        else:
            rounds[round_name] = {
                "fiducial": fiducial_data,
                "images": images,
                "meta": dict(round_spec.get("meta", {})),
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
