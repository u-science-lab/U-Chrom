"""Command line / file-level entry point: ``python -m uchrom.recon.sc.nucdyn``."""

from __future__ import annotations

import os
import warnings

from .native import DEFAULT_PARTICLE_SIZES, native_available, reconstruct_nucdyn

# keyword arguments of the Taichi port and their native equivalents
_LEGACY_MAP = {
    "random_seed": "seed",
    "hot": "temp_start",
    "cold": "temp_end",
    "dyns": "temp_steps",
    "pow": "dist_power_law",
    "lower": "contact_dist_lower",
    "upper": "contact_dist_upper",
    "bb_lower": "backbone_dist_lower",
    "bb_upper": "backbone_dist_upper",
    "max_radius": "random_radius",
    "violated_threshold": "violated_threshold_2017",
}
# Taichi-port-only knobs that have no meaning for the native engine
_LEGACY_IGNORED = {"repulsive_lim", "use_grid", "grid_range_scale", "cell_capacity",
                   "shift_freq", "min_skip", "scale"}
_GPU_ARCHS = {"gpu", "cuda", "metal", "vulkan", "opengl", "dx11", "dx12"}


def main(in_file, out_file, arch="gpu", device_memory_fraction=0.9, cell_id=None,
         engine="auto", n_models=None, device=None, n_threads=0, seed=None,
         protocol="nuc_dynamics_2017", size_steps=None, genome_ranges=None, **kwargs):
    """Calculate a single-cell genome structure from contacts and write it.

    ``in_file``: contacts (``.pairs[.gz]``, ``.ncc``, GEO contact table; the
    Taichi port also reads ``.cool``).  ``out_file``: ``.chromdata.zarr`` /
    ``.cdz`` / ``.h5cd`` (the whole ensemble: ``coords`` = model 0,
    ``layers['model_<k>']`` = every model) or ``.csv`` (model 0 only).

    ``engine``: ``"auto"`` uses the native engine (``uchrom_nucdyn``) when it
    is installed, otherwise the deprecated Taichi port; ``"native"`` /
    ``"taichi"`` force one.  ``device`` (``auto`` / ``cpu`` / ``gpu``)
    defaults from ``arch`` (``cpu`` -> cpu; ``gpu`` / ``cuda`` / ``metal`` ->
    gpu).  ``size_steps``: particle sizes in Mb (default 8 4 2 0.4 0.2 0.1).
    Other keyword arguments: native engine parameters, or the Taichi port's
    (``dyns``, ``hot``, ``cold``, ``random_seed``, ... are mapped to the
    native ones).
    """
    use_native = engine == "native" or (engine == "auto" and native_available())
    if engine not in ("auto", "native", "taichi"):
        raise ValueError(f"engine must be 'auto', 'native' or 'taichi', got {engine!r}")
    if engine == "native" and not native_available():
        raise ImportError("the native NucDynamics engine is not installed (pip install u-chrom[nucdyn])")
    if not use_native:
        # the Taichi port warns (DeprecationWarning) itself
        from .nucdyn import main as taichi_main

        legacy = dict(kwargs)
        if size_steps is not None:
            legacy["size_steps"] = list(size_steps)
        if genome_ranges is not None:
            legacy["genome_ranges"] = genome_ranges
        if seed is not None:
            legacy.setdefault("random_seed", seed)
        return taichi_main(in_file, out_file, arch=arch, device_memory_fraction=device_memory_fraction,
                           cell_id=cell_id, **legacy)

    params = {}
    for k, v in kwargs.items():
        if k in _LEGACY_IGNORED:
            warnings.warn(f"nucdyn: parameter {k!r} of the Taichi port is ignored by the native engine",
                          UserWarning, stacklevel=2)
            continue
        params[_LEGACY_MAP.get(k, k)] = v
    if seed is None:
        seed = params.pop("seed", 0)
    else:
        params.pop("seed", None)
    if device is None:
        device = "cpu" if str(arch).lower() not in _GPU_ARCHS else "auto"
    sizes = [float(s) * 1e6 for s in size_steps] if size_steps is not None else DEFAULT_PARTICLE_SIZES
    for key in ("temp_steps", "dynamics_steps"):
        if key in params and not isinstance(params[key], (list, tuple)):
            params[key] = [int(params[key])]
    if cell_id is None:
        base = os.path.basename(str(out_file).rstrip("/"))
        for suffix in (".chromdata.zarr", ".cdz", ".h5cd", ".csv"):
            if base.endswith(suffix):
                base = base[: -len(suffix)]
                break
        cell_id = base
    cd = reconstruct_nucdyn(str(in_file), n_models=n_models or 10, device=device, n_threads=n_threads,
                            seed=int(seed), protocol=protocol, particle_sizes=sizes,
                            genome_ranges=genome_ranges, cell_id=cell_id, params=params, verbose=True)
    out = str(out_file)
    if out.endswith(".csv"):
        df = cd.to_dataframe()
        df.to_csv(out)
    else:
        cd.write(out)
    return cd
