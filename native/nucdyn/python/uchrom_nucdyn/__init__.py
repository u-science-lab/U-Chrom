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
    calc_population as _calc_population,
    default_igm_params_json,
    default_params_json,
    gpu_available,
    gpu_info,
    run_dynamics,
)
from .io import read_contact_pairs, read_ncc  # noqa: F401

__all__ = [
    "calc_genome_structure",
    "calc_population",
    "default_igm_params",
    "resolve_copies",
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
    prior_lr: Optional[Sequence[float]] = None,
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
    prior_lr
        Protocol ``"robust"`` only: per-contact likelihood ratio (true / false)
        from evidence other than the structure; multiplies each contact's
        posterior odds (1 = no information, 0 = certainly false).
    **params
        Any field of :func:`default_params` (``particle_sizes``, ``n_models``,
        ``seed``, ``device``, ``n_threads``, ``temp_steps``, ...).

    Returns
    -------
    dict with ``coords`` (n_models, n_particles, 3; particle radii; each
    model centred; superposed only in the release_1.3 protocol), ``chrom`` /
    ``position`` (per particle, see ``position_convention``),
    ``particle_size``, ``model_rmsds`` (release_1.3), ``stages`` (per-stage
    log), ``seconds_total`` and, for ``protocol="robust"``, ``contact_weights``
    (per input contact: the final weight of its restraint, the posterior
    probability that it is a true contact; NaN when it was filtered out).
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
    lr = None if prior_lr is None else np.ascontiguousarray(prior_lr, dtype=np.float64)
    res = _calc_genome_structure(names, ia, pa, ib, pb, amb, act, json.dumps(p), lr)
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
        "position_convention": "end" if p["protocol"] in ("nuc_dynamics_2017", "robust") else "start",
        "particle_size": res["particle_size"],
        "model_rmsds": list(res["model_rmsds"]),
        "stages": json.loads(res["stages_json"]),
        "seconds_total": res["seconds_total"],
        # protocol "robust": final restraint weight of every input contact (NaN = filtered out)
        "contact_weights": np.asarray(res["contact_weights"], np.float64),
        "params": p,
    }


# ---------------------------------------------------------------------------
# Protocol "igm": population modelling of bulk Hi-C (A/M deconvolution)
# ---------------------------------------------------------------------------


def default_igm_params() -> Dict[str, Any]:
    """Default parameters of the ``igm`` protocol (IGM schema + demo annealing)."""
    return json.loads(default_igm_params_json())


_SEX = {"x": "X", "chrx": "X", "y": "Y", "chry": "Y"}


def resolve_copies(chroms: Sequence[str], ploidy: Any = "diploid") -> list:
    """Copies per chromosome: ``"diploid"`` (every chromosome x2, as alabtools
    ``make_diploid``), ``"haploid"`` (x1), ``"male"`` (autosomes x2, X and Y
    x1) or a dict ``{chrom: copies}`` (missing chromosomes: 2)."""
    out = []
    for c in chroms:
        sex = _SEX.get(str(c).lower())
        if isinstance(ploidy, dict):
            out.append(int(ploidy.get(c, 2)))
        elif ploidy == "diploid":
            out.append(2)
        elif ploidy == "haploid":
            out.append(1)
        elif ploidy == "male":
            out.append(1 if sex in ("X", "Y") else 2)
        else:
            raise ValueError(f"unknown ploidy {ploidy!r}")
    return out


def calc_population(
    chrom: Sequence[str],
    start: Sequence[int],
    end: Sequence[int],
    prob_i: Sequence[int],
    prob_j: Sequence[int],
    prob_v: Sequence[float],
    *,
    ploidy: Any = "diploid",
    on_round=None,
    round_coords: bool = False,
    init_pins: Optional[Dict[str, Any]] = None,
    **params: Any,
) -> Dict[str, Any]:
    """Run the ``igm`` protocol on a haploid contact-probability matrix.

    ``chrom`` / ``start`` / ``end``: haploid bins, each chromosome contiguous
    (genome order).  ``prob_i`` / ``prob_j`` / ``prob_v``: the matrix as COO
    (bin indices; upper triangle or symmetric; the diagonal is ignored).
    ``**params``: fields of :func:`default_igm_params` (``n_structures``,
    ``seed``, ``device``, ``occupancy``, ``nucleus_radius``, sigma lists, ...).
    ``on_round(log: dict, coords)`` is called after every M-step (``coords``
    (S, N, 3) float32 when ``round_coords``, else None).
    ``init_pins``: optional dict of equal-length arrays ``structure``,
    ``bin`` (haploid bin index), ``copy`` and ``xyz`` (M, 3) nm — loci placed
    at these initial positions, the beads between two pinned beads of one
    chain linearly interpolated (IGM-Plus expanded initialisation).

    Returns a dict with ``coords`` (S, N, 3) float32 nm, per bead
    ``bead_bin`` / ``bead_copy`` / ``bead_chain`` / ``radii``, ``chroms``
    (chromosome order), ``rounds`` (per-round log), ``final_stats`` (per
    structure), the last A-step (``actdist``: i, j, f, p, p_now, d) and
    ``params``.
    """
    chrom = np.asarray(chrom).astype(str)
    names = list(dict.fromkeys(chrom.tolist()))
    idx = {c: k for k, c in enumerate(names)}
    ci = np.fromiter((idx[c] for c in chrom), dtype=np.uint32, count=len(chrom))
    if np.any(np.diff(ci.astype(np.int64)) < 0):
        raise ValueError("bins must be grouped by chromosome (each chromosome contiguous)")
    copies = resolve_copies(names, ploidy)
    p = default_igm_params()
    unknown = set(params) - set(p)
    if unknown:
        raise TypeError(f"unknown igm parameters: {sorted(unknown)}")
    p.update(params)
    pin_args = ()
    if init_pins is not None:
        xyz = np.ascontiguousarray(init_pins["xyz"], dtype=np.float64).reshape(-1, 3)
        pin_args = (np.ascontiguousarray(init_pins["structure"], dtype=np.uint32),
                    np.ascontiguousarray(init_pins["bin"], dtype=np.uint32),
                    np.ascontiguousarray(init_pins["copy"], dtype=np.uint32),
                    np.ascontiguousarray(xyz.ravel()))
    cb = None
    if on_round is not None:
        def cb(js, coords):
            on_round(json.loads(js), coords)
    res = _calc_population(
        ci, np.ascontiguousarray(start, dtype=np.int64), np.ascontiguousarray(end, dtype=np.int64), copies,
        np.ascontiguousarray(prob_i, dtype=np.uint32), np.ascontiguousarray(prob_j, dtype=np.uint32),
        np.ascontiguousarray(prob_v, dtype=np.float64), json.dumps(p), cb, bool(round_coords), *pin_args)
    return {
        "coords": res["coords"],
        "bead_bin": res["bead_hap"].astype(np.int64),
        "bead_copy": res["bead_copy"].astype(np.int64),
        "bead_chain": res["bead_chain"].astype(np.int64),
        "radii": res["radii"],
        "chroms": names,
        "copies": dict(zip(names, copies)),
        "rounds": json.loads(res["rounds_json"]),
        "final_stats": json.loads(res["final_stats_json"]),
        "relax_init": json.loads(res["relax_json"]),
        "actdist": {k: res["act_" + k] for k in ("i", "j", "f", "p", "p_now", "d")},
        "stopped_at_max_iterations": bool(res["stopped_at_max_iterations"]),
        "seconds_total": float(res["seconds_total"]),
        "engine": res["engine"],
        "params": p,
    }
