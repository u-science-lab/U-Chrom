"""NucDynamics on the native engine (``uchrom_nucdyn``, Rust; CPU and GPU).

The engine is a separate package (``pip install u-chrom[nucdyn]`` or
``pip install ./native/nucdyn``); this module turns contacts into a
:class:`~uchrom.core.ChromData` ensemble.
"""

from __future__ import annotations

import os
import warnings
from typing import Any, Dict, Mapping, Optional, Sequence, Union

import numpy as np
import pandas as pd

__all__ = ["reconstruct_nucdyn", "native_available", "engine_info", "load_contacts"]

#: Default hierarchical schedule (bp), the original's ``-s 8 4 2 0.4 0.2 0.1``.
DEFAULT_PARTICLE_SIZES = (8e6, 4e6, 2e6, 4e5, 2e5, 1e5)


def _engine():
    import uchrom_nucdyn

    return uchrom_nucdyn


def native_available() -> bool:
    """True when the native engine (``uchrom_nucdyn``) can be imported."""
    try:
        _engine()
    except ImportError:
        return False
    return True


def engine_info() -> Dict[str, Any]:
    """Version of the native engine and the GPU it would use."""
    un = _engine()
    return {"version": un.__version__, "gpu_build": bool(un.HAS_GPU), "gpu": un.gpu_info()}


def _resolve_device(device: str) -> str:
    if device in ("cpu", "gpu"):
        return device
    if device != "auto":
        raise ValueError(f"device must be 'auto', 'cpu' or 'gpu', got {device!r}")
    return "gpu" if _engine().gpu_available() else "cpu"


def load_contacts(contacts, genome_ranges=None) -> Dict[str, np.ndarray]:
    """Contacts as arrays ``chrom_a, pos_a, chrom_b, pos_b, ambiguity, active``.

    ``contacts`` is a path (``.ncc`` as written by NucProcess; ``.pairs`` /
    ``.pairs.gz``; a whitespace table ``chr_A pos_A chr_B pos_B`` such as the
    GEO files of Stevens et al. 2017) or a DataFrame with columns
    ``chr1, pos1, chr2, pos2`` (as :func:`uchrom.io.read_pairs` returns) or
    ``chrom1, pos1, chrom2, pos2``; optional ``ambiguity`` / ``active``.
    ``genome_ranges`` keeps only contacts with both ends in the given
    ranges (``"chr19"``, ``"chr1:1000000-5000000"``, or a list).
    """
    un = _engine()
    if isinstance(contacts, (str, os.PathLike)):
        path = str(contacts)
        if path.endswith((".ncc", ".ncc.gz")):
            c = un.read_ncc(path)
        else:
            c = un.read_contact_pairs(path)
    elif isinstance(contacts, pd.DataFrame):
        df = contacts
        cols = {"chr1": "chrom_a", "chrom1": "chrom_a", "pos1": "pos_a",
                "chr2": "chrom_b", "chrom2": "chrom_b", "pos2": "pos_b"}
        df = df.rename(columns={k: v for k, v in cols.items() if k in df.columns})
        missing = {"chrom_a", "pos_a", "chrom_b", "pos_b"} - set(df.columns)
        if missing:
            raise ValueError(f"contact table lacks columns {sorted(missing)}")
        n = len(df)
        c = {
            "chrom_a": df["chrom_a"].astype(str).to_numpy(object),
            "pos_a": df["pos_a"].to_numpy(np.int64),
            "chrom_b": df["chrom_b"].astype(str).to_numpy(object),
            "pos_b": df["pos_b"].to_numpy(np.int64),
            "ambiguity": (df["ambiguity"].to_numpy(np.int64) if "ambiguity" in df
                          else np.arange(1, n + 1, dtype=np.int64)),
            "active": df["active"].to_numpy(bool) if "active" in df else np.ones(n, bool),
        }
    else:
        raise TypeError("contacts must be a path or a DataFrame")
    if genome_ranges:
        from uchrom.io.genome import GenomeRange

        ranges = genome_ranges if isinstance(genome_ranges, (list, tuple)) else [genome_ranges]
        ranges = [g if isinstance(g, GenomeRange) else GenomeRange.parse_text(g) for g in ranges]
        keep = np.zeros(len(c["pos_a"]), bool)
        ka = np.zeros_like(keep)
        kb = np.zeros_like(keep)
        for g in ranges:
            ka |= (c["chrom_a"] == g.chr) & (c["pos_a"] >= g.start) & (c["pos_a"] <= g.end)
            kb |= (c["chrom_b"] == g.chr) & (c["pos_b"] >= g.start) & (c["pos_b"] <= g.end)
        keep = ka & kb
        c = {k: v[keep] for k, v in c.items()}
    if len(c["pos_a"]) == 0:
        raise ValueError("no contacts to calculate a structure from")
    return c


def reconstruct_nucdyn(
    contacts: Union[str, os.PathLike, pd.DataFrame],
    *,
    n_models: int = 10,
    device: str = "auto",
    n_threads: int = 0,
    seed: int = 0,
    protocol: str = "nuc_dynamics_2017",
    particle_sizes: Sequence[float] = DEFAULT_PARTICLE_SIZES,
    genome_ranges=None,
    cell_id: Optional[str] = None,
    key_added: Optional[str] = "nucdyn",
    params: Optional[Mapping[str, Any]] = None,
    verbose: bool = False,
    **engine_params: Any,
):
    """Single-cell Hi-C genome structure ensemble with NucDynamics.

    Runs the hierarchical simulated-annealing protocol of NucDynamics
    (Stevens et al. 2017, *Nature* 544:59) on the native engine and returns
    the ensemble as a new :class:`~uchrom.core.ChromData`.

    Parameters
    ----------
    contacts
        Path (``.ncc``, ``.pairs[.gz]``, GEO ``chr_A pos_A chr_B pos_B``
        table) or DataFrame of contacts, see :func:`load_contacts`.
    n_models
        Number of structures (models) in the ensemble.  All models are
        computed at once (in parallel on the CPU, in one batch on the GPU).
    device
        ``"auto"`` (GPU when available, else CPU), ``"cpu"`` (f64, multi-core)
        or ``"gpu"`` (f32, wgpu: Metal / Vulkan / DX12).
    n_threads
        CPU worker threads (0 = all cores).
    seed
        Random seed (start coordinates and velocities); on the CPU a seed
        gives bitwise-identical results.
    protocol
        ``"nuc_dynamics_2017"`` (default): the code that produced the
        published 2017 structures (tjs23/nuc_dynamics ``master``).
        ``"release_1.3"``: the later bead-size-scaled version with
        ambiguity resolution and model selection (2 x ``n_models`` above 1 Mb,
        the ``n_models`` closest to the mean kept).
        ``"robust"``: the 2017 protocol with a noise-aware observation model
        (contact restraints re-weighted by their posterior probability of
        being true contacts; false-contact rate and contact-kernel width
        learned by EM; ``robust_*`` engine parameters).  Adds the results
        ``<key_added>.em`` (EM log) and ``<key_added>.contact_weights``
        (final weight of every input contact, NaN = filtered out).
    particle_sizes
        Hierarchical particle sizes in bp (coarse to fine).
    genome_ranges
        Restrict the contacts to these ranges (e.g. ``"chr19"``).
    cell_id
        Written to ``spots['cell_id']``.
    key_added
        Key of the provenance record in ``cd.results`` (per-stage log) and
        of ``cd.uns[key_added]``; ``None`` stores neither.
    params
        Further engine parameters (see ``uchrom_nucdyn.default_params()``:
        ``temp_steps``, ``dynamics_steps``, ``temp_start``, ``temp_end``,
        ``time_step``, ``contact_dist_lower``, ...); keyword arguments are
        merged into it.

    Returns
    -------
    ChromData
        One spot per particle; one trace per chromosome.  ``coords`` holds
        model 0 and ``layers['model_<k>']`` holds every model ``k`` (model 0
        included), so the whole ensemble travels with the object.  Units are
        particle radii.  Bins are the particles' genomic intervals: in the
        2017 protocol a particle at sequence position ``p`` collects the
        contacts in ``(p - size, p]`` (``bins.start = p - size``,
        ``bins.end = p``); in release_1.3 ``[p, p + size)``.  ``uns[key_added]``
        records the engine, protocol, parameters and per-stage log.
    """
    from uchrom.core import ChromData

    un = _engine()
    c = load_contacts(contacts, genome_ranges)
    dev = _resolve_device(device)
    p = dict(params or {})
    p.update(engine_params)
    res = un.calc_genome_structure(
        c["chrom_a"], c["pos_a"], c["chrom_b"], c["pos_b"],
        ambiguity=c["ambiguity"], active=c["active"],
        n_models=int(n_models), device=dev, n_threads=int(n_threads), seed=int(seed),
        protocol=protocol, particle_sizes=[float(s) for s in particle_sizes], verbose=verbose, **p)
    size = int(res["particle_size"])
    pos = np.asarray(res["position"], np.int64)
    if res["position_convention"] == "end":
        start = np.maximum(pos - size, 0)
        end = np.maximum(pos, start + 1)
    else:
        start, end = pos, pos + size
    coords = np.asarray(res["coords"], np.float64)
    df = pd.DataFrame({"chrom": res["chrom"].astype(str), "start": start, "end": end,
                       "x": coords[0, :, 0], "y": coords[0, :, 1], "z": coords[0, :, 2]})
    cd = ChromData.from_dataframe(df, cell_id=cell_id)
    # from_dataframe keeps the row order of df; every model in the same order
    width = max(1, len(str(len(coords) - 1)))
    for k in range(len(coords)):
        cd.layers[f"model_{k:0{width}d}"] = coords[k].copy()
    cd.uns.setdefault("xyz_unit", "particle radii (NucDynamics)")
    if key_added is not None:
        stages = pd.DataFrame([{k: v for k, v in s.items() if k not in ("removed_models", "robust")}
                               for s in res["stages"]])
        info = {
            "engine": "uchrom_nucdyn", "engine_version": un.__version__, "device": dev,
            "gpu": un.gpu_info() if dev == "gpu" else None, "protocol": protocol,
            "n_models": int(len(coords)), "seed": int(seed), "particle_size": size,
            "particle_position": res["position_convention"],
            "model_layers": [f"model_{k:0{width}d}" for k in range(len(coords))],
            "seconds": float(res["seconds_total"]),
            "citation": "Stevens et al. 2017, Nature 544:59, doi:10.1038/nature21429",
        }
        cd.uns[key_added] = info
        cd.results.set(f"{key_added}.stages", stages, kind="table",
                       function="uchrom.recon.sc.nucdyn.reconstruct_nucdyn",
                       params={k: v for k, v in res["params"].items() if k != "verbose"},
                       inputs={"contacts": str(contacts) if not isinstance(contacts, pd.DataFrame) else "DataFrame",
                               "n_contacts": int(len(c["pos_a"]))})
        if protocol == "robust":
            # EM log (one row per update) and the final weight of every input contact
            em = pd.DataFrame([{"stage": s["stage"], "particle_size": s["particle_size"], **u}
                               for s in res["stages"] for u in s.get("robust", [])])
            cd.results.set(f"{key_added}.em", em, kind="table",
                           function="uchrom.recon.sc.nucdyn.reconstruct_nucdyn", params={"protocol": "robust"})
            cd.results.set(f"{key_added}.contact_weights", np.asarray(res["contact_weights"], np.float64),
                           kind="array", function="uchrom.recon.sc.nucdyn.reconstruct_nucdyn",
                           params={"protocol": "robust"},
                           inputs={"rows": "input contacts in load_contacts order; NaN = filtered out"})
    return cd
