from pathlib import Path
import os

import matplotlib.pyplot as plt
import numpy as np
from skimage import io

from uchrom.im._base import Image2D, Image3D, ensure_2d_array, ensure_3d_array


VALID_TIFF_SUFFIXES = (".tif", ".tiff")


def _read_stack(path):
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Input file not found: {path}")
    if not path.is_file():
        raise ValueError(f"Expected a TIFF file, got: {path}")
    if path.suffix.lower() not in VALID_TIFF_SUFFIXES:
        raise ValueError(f"Only .tif/.tiff files are supported, got: {path}")

    stack = io.imread(str(path)).squeeze()
    return ensure_3d_array(stack, source=str(path))


def _normalize_z_range(nz, zmin=None, zmax=None):
    zmin = 0 if zmin is None else int(zmin)
    zmax = nz if zmax is None else int(zmax)

    if zmin < 0 or zmax < 0:
        raise ValueError(f"zmin/zmax must be non-negative, got zmin={zmin}, zmax={zmax}")
    if zmin >= zmax:
        raise ValueError(f"zmin must be smaller than zmax, got zmin={zmin}, zmax={zmax}")
    if zmax > nz:
        raise ValueError(
            f"zmax exceeds stack depth: zmax={zmax}, stack_depth={nz}"
        )

    return zmin, zmax


def _project_stack(stack, method="mip"):
    method = str(method).lower()
    if method == "mip":
        return np.max(stack, axis=0)
    if method == "sum":
        return np.sum(stack, axis=0)
    raise ValueError(f"Unsupported projection method: {method}")


def _as_float64(array_2d):
    return np.asarray(array_2d, dtype=np.float64)


def _resolve_output_stem(name, default_stem):
    if name is None:
        return default_stem
    return Path(str(name)).stem


def _resolve_default_out_dir(base_dir):
    return Path(base_dir).parent / "project"


def _ensure_writable_dir(path):
    path = Path(path)
    try:
        data_dir = path / "data"
        preview_dir = path / "preview"
        data_dir.mkdir(parents=True, exist_ok=True)
        preview_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise PermissionError(f"Unable to create output directory: {path}") from exc

    for folder in (data_dir, preview_dir):
        probe = folder / ".uchrom_write_test"
        try:
            with open(probe, "wb") as handle:
                handle.write(b"ok")
        except OSError as exc:
            raise PermissionError(f"Output directory is not writable: {folder}") from exc
        finally:
            if probe.exists():
                probe.unlink()

    return data_dir, preview_dir


def _save_npy(array_2d, data_dir, stem):
    npy_path = Path(data_dir) / f"{stem}.npy"
    np.save(npy_path, array_2d)
    return str(npy_path)


def _save_preview_png(array_2d, preview_dir, stem):
    png_path = Path(preview_dir) / f"{stem}.png"
    plt.imsave(png_path, array_2d, cmap="gray")
    return str(png_path)


def _normalize_save_mode(save):
    if save in (False, None, "none"):
        return None
    if save in (True, "selected", "all"):
        return "all"
    raise ValueError(f"Unsupported save mode: {save}")


def z_project_array(stack, method="mip", zmin=None, zmax=None):
    stack = ensure_3d_array(stack, source="input array")
    zmin, zmax = _normalize_z_range(stack.shape[0], zmin=zmin, zmax=zmax)
    projected = _project_stack(stack[zmin:zmax], method=method)
    return _as_float64(projected)


def project(stack, method="mip", zmin=None, zmax=None):
    """
    Array-first z projection.

    This is the recommended U-Chrom API. File-based helpers such as
    `z_project` remain available for compatibility and explicit I/O.
    """
    return z_project_array(stack, method=method, zmin=zmin, zmax=zmax)


def _image3d_payload(image, default_name, default_meta):
    if isinstance(image, Image3D):
        return image.data, image.name or default_name, dict(image.meta)
    return ensure_3d_array(image, source=default_name), default_name, dict(default_meta)


def project_rounds(rounds, methods=None, z_ranges=None):
    methods = {} if methods is None else methods
    z_ranges = {} if z_ranges is None else z_ranges
    projected = {}

    for round_name, round_spec in rounds.items():
        round_meta = dict(round_spec.get("meta", {}))
        round_methods = methods.get(round_name, {})
        round_z_ranges = z_ranges.get(round_name, {})

        fiducial_data, fiducial_name, fiducial_meta = _image3d_payload(
            round_spec["fiducial"],
            default_name=f"{round_name}_fiducial",
            default_meta={**round_meta, "round": round_name, "role": "fiducial"},
        )
        fid_method = round_methods.get("fiducial", "mip")
        fid_zmin, fid_zmax = round_z_ranges.get("fiducial", (None, None))
        projected_images = {}

        for image_name, image in round_spec.get("images", {}).items():
            image_data, image_label, image_meta = _image3d_payload(
                image,
                default_name=f"{round_name}_{image_name}",
                default_meta={**round_meta, "round": round_name, "role": image_name},
            )
            image_method = round_methods.get(image_name, "mip")
            image_zmin, image_zmax = round_z_ranges.get(image_name, (None, None))
            projected_images[image_name] = Image2D(
                project(image_data, method=image_method, zmin=image_zmin, zmax=image_zmax),
                name=f"{image_label}_2d",
                path=None,
                meta=image_meta,
            )

        projected[round_name] = {
            "fiducial": Image2D(
                project(fiducial_data, method=fid_method, zmin=fid_zmin, zmax=fid_zmax),
                name=f"{fiducial_name}_2d",
                path=None,
                meta=fiducial_meta,
            ),
            "images": projected_images,
            "meta": round_meta,
        }

    return projected


def save_projected_array(array_2d, out_dir, out_name):
    array_2d = _as_float64(ensure_2d_array(array_2d, source="projected array"))
    stem = _resolve_output_stem(out_name, "projection_2d")
    data_dir, preview_dir = _ensure_writable_dir(out_dir)
    return {
        "npy_path": _save_npy(array_2d, data_dir, stem),
        "png_path": _save_preview_png(array_2d, preview_dir, stem),
    }


def z_project(
    src,
    method="mip",
    zmin=None,
    zmax=None,
    save=True,
    out_dir=None,
    out_name=None,
):
    """
    Project a single 3D stack along the z axis.

    Parameters
    ----------
    src : str | os.PathLike | numpy.ndarray
        Input 3D TIFF path or a 3D array with shape (z, y, x).
    method : str
        Projection method. Supports "mip" and "sum".
    zmin, zmax : int | None
        Python-style z slicing range [zmin, zmax). If omitted, use the whole stack.
    save : bool | str
        If truthy, save both .npy and .png outputs. Supported values are
        False/None/"none" and True/"selected"/"all".
    out_dir : str | os.PathLike | None
        Output root directory. Results are saved into out_dir/data and out_dir/preview.
    out_name : str | None
        Output name stem without extension.

    Returns
    -------
    numpy.ndarray
        The 2D projected array.
    """
    save_mode = _normalize_save_mode(save)

    if isinstance(src, (str, os.PathLike)):
        src_path = Path(src)
        stack = _read_stack(src_path)
        default_stem = f"{src_path.stem}_2d"
        if out_dir is None:
            out_root = _resolve_default_out_dir(src_path.parent)
        else:
            out_root = Path(out_dir)
    else:
        stack = ensure_3d_array(src, source="input array")
        default_stem = "projection_2d"
        out_root = Path(out_dir) if out_dir is not None else (Path.cwd() / "project")

    projected = z_project_array(stack, method=method, zmin=zmin, zmax=zmax)

    if save_mode is not None:
        stem = _resolve_output_stem(out_name, default_stem)
        save_projected_array(projected, out_dir=out_root, out_name=stem)

    return projected


def z_project_dir(in_dir, method="mip", zmin=None, zmax=None, out_dir=None):
    """
    Batch project all TIFF files inside a directory.

    Parameters
    ----------
    in_dir : str | os.PathLike
        Input directory containing .tif or .tiff files.
    method : str
        Projection method. Supports "mip" and "sum".
    zmin, zmax : int | None
        Python-style z slicing range [zmin, zmax). If omitted, use the whole stack.
    out_dir : str | os.PathLike | None
        Output root directory. Results are saved into out_dir/data and out_dir/preview.

    Returns
    -------
    list[dict]
        One record per input file with input_path, npy_path and png_path.
    """
    in_dir = Path(in_dir)
    if not in_dir.exists():
        raise FileNotFoundError(f"Input directory not found: {in_dir}")
    if not in_dir.is_dir():
        raise NotADirectoryError(f"Expected a directory, got: {in_dir}")

    tif_files = sorted(
        path for path in in_dir.iterdir()
        if path.is_file() and path.suffix.lower() in VALID_TIFF_SUFFIXES
    )
    if not tif_files:
        raise FileNotFoundError(f"No .tif/.tiff files found in directory: {in_dir}")

    out_root = Path(out_dir) if out_dir is not None else _resolve_default_out_dir(in_dir)

    records = []
    for path in tif_files:
        projected = z_project(
            path,
            method=method,
            zmin=zmin,
            zmax=zmax,
            save=False,
        )
        saved = save_projected_array(projected, out_dir=out_root, out_name=f"{path.stem}_2d")
        records.append(
            {
                "input_path": str(path),
                "npy_path": saved["npy_path"],
                "png_path": saved["png_path"],
            }
        )

    return records


__all__ = [
    "project",
    "project_rounds",
    "z_project_array",
    "save_projected_array",
    "z_project",
    "z_project_dir",
]
