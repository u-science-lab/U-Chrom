"""Native NucDynamics engine for U-Chrom.

A Rust re-implementation of NucDynamics (Stevens et al. 2017, *Nature*
544:59, doi:10.1038/nature21429; original code github.com/tjs23/nuc_dynamics,
LGPL-3.0): single-cell Hi-C genome structure calculation by simulated
annealing of a particle model, on a multi-core CPU (f64) or on a GPU via
wgpu (f32; Metal / Vulkan / DX12), with every model of an ensemble computed
in one batched run.

Most users call it through ``uchrom.recon.sc.nucdyn``; this module is the
array-level interface::

    from uchrom_nucdyn import calc_genome_structure
    res = calc_genome_structure(chr_a, pos_a, chr_b, pos_b, n_models=10, device="cpu")
    res["coords"]      # (n_models, n_particles, 3), particle radii
    res["particles"]   # DataFrame-like dict: chrom, start per particle
"""

from __future__ import annotations

import json
from typing import Any, Dict, Optional, Sequence

import numpy as np

from ._engine import (  # noqa: F401
    HAS_GPU,
    __version__,
    calc_genome_structure as _calc_genome_structure,
    default_params_json,
    gpu_available,
    gpu_info,
    run_dynamics,
)
from .io import read_contact_pairs, read_ncc  # noqa: F401

__all__ = [
    "calc_genome_structure",
    "default_params",
    "gpu_available",
    "gpu_info",
    "run_dynamics",
    "read_ncc",
    "read_contact_pairs",
    "HAS_GPU",
    "__version__",
]


def default_params() -> Dict[str, Any]:
    """Default calculation parameters (those of the original command line)."""
    return json.loads(default_params_json())


def calc_genome_structure(
    chrom_a: Sequence[str],
    pos_a: Sequence[int],
    chrom_b: Sequence[str],
    pos_b: Sequence[int],
    *,
    ambiguity: Optional[Sequence[int]] = None,
    active: Optional[Sequence[bool]] = None,
    **params: Any,
) -> Dict[str, Any]:
    """Run the hierarchical NucDynamics protocol on single-cell contacts.

    Parameters
    ----------
    chrom_a, pos_a, chrom_b, pos_b
        Contact ends (one entry per contact / read pair).
    ambiguity
        Ambiguity group of each contact (contacts of one group are
        alternative explanations of one read pair).  ``None``: every contact
        is its own group (unambiguous).
    active
        NCC activity flag; inactive contacts are only considered from the
        ``struct_ambig_size`` stage on.  ``None``: all active.
    **params
        Any field of :func:`default_params` (``particle_sizes``, ``n_models``,
        ``seed``, ``device``, ``n_threads``, ``temp_steps``, ...).

    Returns
    -------
    dict with ``coords`` (n_models, n_particles, 3; particle radii; each
    model centred; superposed only in the release_1.3 protocol), ``chrom`` /
    ``position`` (per particle, see ``position_convention``),
    ``particle_size``, ``model_rmsds`` (release_1.3), ``stages`` (per-stage
    log) and ``seconds_total``.
    """
    ca = np.asarray(chrom_a).astype(str)
    cb = np.asarray(chrom_b).astype(str)
    names = sorted(set(ca.tolist()) | set(cb.tolist()))
    idx = {n: i for i, n in enumerate(names)}
    ia = np.fromiter((idx[c] for c in ca), dtype=np.uint32, count=len(ca))
    ib = np.fromiter((idx[c] for c in cb), dtype=np.uint32, count=len(cb))
    n = len(ia)
    pa = np.ascontiguousarray(pos_a, dtype=np.int64)
    pb = np.ascontiguousarray(pos_b, dtype=np.int64)
    amb = (np.arange(1, n + 1, dtype=np.int64) if ambiguity is None
           else np.ascontiguousarray(ambiguity, dtype=np.int64))
    act = (np.ones(n, dtype=bool) if active is None
           else np.ascontiguousarray(active, dtype=bool))
    p = default_params()
    unknown = set(params) - set(p)
    if unknown:
        raise TypeError(f"unknown NucDynamics parameters: {sorted(unknown)}")
    p.update(params)
    for key in ("temp_steps", "dynamics_steps"):
        if np.isscalar(p[key]):
            p[key] = [int(p[key])]
    p["particle_sizes"] = [float(s) for s in p["particle_sizes"]]
    res = _calc_genome_structure(names, ia, pa, ib, pb, amb, act, json.dumps(p))
    chroms = [names[c] for c in res["chroms"]]
    chrom = np.concatenate([np.full(len(s), c, dtype=object) for c, s in zip(chroms, res["seq_pos"])])
    start = np.concatenate(res["seq_pos"]).astype(np.int64)
    return {
        "coords": res["coords"],
        "chrom": chrom,
        # particle sequence position as the original reports it: 2017 protocol
        # = end of the particle's interval (start - size, start]; release_1.3 =
        # start of [start, start + size)
        "position": start,
        "position_convention": "end" if p["protocol"] == "nuc_dynamics_2017" else "start",
        "particle_size": res["particle_size"],
        "model_rmsds": list(res["model_rmsds"]),
        "stages": json.loads(res["stages_json"]),
        "seconds_total": res["seconds_total"],
        "params": p,
    }
