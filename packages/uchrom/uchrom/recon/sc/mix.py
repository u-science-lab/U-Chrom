"""Few-cell deconvolution (working name "EMber-mix"; in development, not validated).

Given the pooled single-cell Hi-C contacts of ``n_cells`` haploid cells, infer one structure
ensemble per cell and the cell of origin of every contact: the native engine's protocol
``"robust"`` (EMber) with ``mix_cells = n_cells`` (``packages/uchrom-recon/src/mix.rs``) — EMber's
mixture observation model with the cell as a latent variable, all cells annealed together, no
nuclear shape prior (optional shape-free density cap).

    from uchrom.recon.sc import deconvolve_cells
    cd = deconvolve_cells("pool.pairs.gz", n_cells=2, device="auto")
    cd.cells                                   # one row per recovered cell
    cd.results["ember_mix.cell_probs"]         # (n_contacts, n_cells) P(cell | true)

**Status**: development (``benchmarks/screcon/PREREG.md`` §12, ``mix_devlog.md``).  The method
recovers the cells from a partially correct seed (e.g. ``mix_prior``), but not yet reliably from
the pooled contacts alone; the defaults are not frozen.
"""

from __future__ import annotations

import os
from typing import Any, Mapping, Optional, Sequence, Union

import numpy as np
import pandas as pd

from .nucdyn.native import DEFAULT_PARTICLE_SIZES, _engine, _resolve_device, load_contacts

__all__ = ["deconvolve_cells"]


def deconvolve_cells(
    contacts: Union[str, os.PathLike, pd.DataFrame],
    *,
    n_cells: int,
    chrom: Union[None, str, Sequence[str]] = None,
    n_models: int = 2,
    params: Optional[Mapping[str, Any]] = None,
    mix_prior: Optional[np.ndarray] = None,
    device: str = "auto",
    n_threads: int = 0,
    seed: int = 0,
    particle_sizes: Sequence[float] = DEFAULT_PARTICLE_SIZES,
    key_added: Optional[str] = "ember_mix",
    copy: bool = False,
    verbose: bool = False,
    **engine_params: Any,
):
    """Deconvolve pooled contacts of ``n_cells`` haploid cells into per-cell structures.

    Parameters
    ----------
    contacts
        Pooled contacts (path or DataFrame, see :func:`uchrom.recon.sc.nucdyn.load_contacts`).
    n_cells
        Number of cells in the pool (>= 2).
    chrom
        ``None`` (all) or a chromosome / range / list (calling convention).
    n_models
        Replicate models per recovered cell.
    params, engine_params
        Engine parameters (``uchrom_recon.default_params()``; EMber's ``robust_*`` and the
        deconvolution's ``mix_*`` fields).
    mix_prior
        Optional (n_contacts, n_cells) prior over the cell of every contact (e.g. from a
        reference), used as the first-stage seed.
    device, n_threads, seed, particle_sizes, verbose
        As :func:`uchrom.recon.sc.ember.reconstruct_ember`.
    key_added
        Prefix of ``cd.results`` (``<key>.cell_probs``, ``<key>.contact_weights``, ``<key>.stages``)
        and of ``cd.uns[key]``; ``None`` stores neither.
    copy
        Accepted for the calling convention (a new ChromData is always returned).

    Returns
    -------
    ChromData: one **cell** per recovered structure (``cell_id`` ``mix0`` …), one trace per
    (cell, chromosome) (``mix0:chr1``), one spot per particle; ``coords`` = model 0 of every
    cell, ``layers['model_<r>']`` = replicate r of every cell; units particle radii.
    """
    from uchrom.core import ChromData

    del copy
    if int(n_cells) < 2:
        raise ValueError("n_cells must be >= 2")
    un = _engine()
    c = load_contacts(contacts, chrom)
    dev = _resolve_device(device)
    p = {"mix_cells": int(n_cells), **dict(params or {}), **engine_params}
    kw = {} if mix_prior is None else {"mix_prior": np.asarray(mix_prior, np.float64)}
    res = un.calc_genome_structure(
        c["chrom_a"], c["pos_a"], c["chrom_b"], c["pos_b"], ambiguity=c["ambiguity"], active=c["active"],
        n_models=int(n_models), device=dev, n_threads=int(n_threads), seed=int(seed), protocol="robust",
        particle_sizes=[float(s) for s in particle_sizes], verbose=verbose, **kw, **p)
    k = int(res["mix_cells"])
    size = int(res["particle_size"])
    pos = np.asarray(res["position"], np.int64)
    start = np.maximum(pos - size, 0)
    end = np.maximum(pos, start + 1)
    chrom_arr = res["chrom"].astype(str)
    coords = np.asarray(res["coords"], np.float64)              # (k * m, N, 3), cell-major
    m = len(coords) // k
    n = len(pos)
    cell_ids = [f"mix{s}" for s in range(k)]
    spots = pd.DataFrame({
        "chrom": np.tile(chrom_arr, k), "start": np.tile(start, k), "end": np.tile(end, k),
        "cell_id": np.repeat(cell_ids, n),
        "trace_id": [f"{cid}:{ch}" for cid in cell_ids for ch in chrom_arr],
    })
    cd = ChromData(np.concatenate([coords[s * m] for s in range(k)]), spots)
    width = max(1, len(str(m - 1)))
    for r in range(m):
        cd.layers[f"model_{r:0{width}d}"] = np.concatenate([coords[s * m + r] for s in range(k)])
    probs = np.asarray(res["cell_probs"], np.float64)
    cd.cells = pd.DataFrame({"n_contacts_assigned": np.bincount(np.argmax(np.nan_to_num(probs, nan=-1), 1),
                                                                minlength=k)}, index=pd.Index(cell_ids, name="cell_id"))
    cd.uns.setdefault("xyz_unit", "particle radii (NucDynamics)")
    if key_added is not None:
        func = "uchrom.recon.sc.mix.deconvolve_cells"
        cd.uns[key_added] = {"method": "ember_mix", "status": "development (PREREG §12), not frozen",
                             "engine": "uchrom_recon", "engine_version": un.__version__, "device": dev,
                             "n_cells": k, "n_models_per_cell": m, "seed": int(seed), "particle_size": size,
                             "seconds": float(res["seconds_total"])}
        inputs = {"rows": "input contacts in load_contacts order", "n_contacts": int(len(c["pos_a"]))}
        cd.results.set(f"{key_added}.cell_probs", probs, kind="array", function=func,
                       params={k_: v for k_, v in res["params"].items() if k_.startswith("mix_")}, inputs=inputs)
        cd.results.set(f"{key_added}.contact_weights", np.asarray(res["contact_weights"], np.float64), kind="array",
                       function=func, params={"protocol": "robust"}, inputs=inputs)
        stages = pd.DataFrame([{x: v for x, v in s.items() if x not in ("removed_models", "robust")} for s in res["stages"]])
        cd.results.set(f"{key_added}.stages", stages, kind="table", function=func,
                       params={k_: v for k_, v in res["params"].items() if k_ != "verbose"})
    return cd
