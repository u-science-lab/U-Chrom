"""Native 3-D reconstruction engine for U-Chrom (NucDynamics, EMber, IGM).

A Rust re-implementation of NucDynamics (Stevens et al. 2017, *Nature*
544:59, doi:10.1038/nature21429; original code github.com/tjs23/nuc_dynamics,
LGPL-3.0): single-cell Hi-C genome structure calculation by simulated
annealing of a particle model, on a multi-core CPU (f64) or on a GPU via
wgpu (f32; Metal / Vulkan / DX12), with every model of an ensemble computed
in one batched run.

EMber (protocol ``"robust"``) and IGM population modelling (protocol ``"igm"``)
run on the same engine.  Formerly ``uchrom_nucdyn``.  Most users call it through
``uchrom.recon.sc.nucdyn`` / ``uchrom.recon.sc.ember`` / ``uchrom.recon.bulk.deconv``;
this module is the array-level interface::

    from uchrom_recon import calc_genome_structure
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
from .io import read_contact_pairs, read_ncc, read_phased_contacts  # noqa: F401

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
    "read_phased_contacts",
    "resolve_ploidy",
    "HAS_GPU",
    "__version__",
]


def default_params() -> Dict[str, Any]:
    """Default calculation parameters (those of the original command line)."""
    return json.loads(default_params_json())


def resolve_ploidy(names: Sequence[str], ploidy: Any = "auto") -> list:
    """Copies (1 or 2) of each chromosome for diploid input.

    ``"auto"`` (hickit's rule): ``"male"`` when a Y chromosome is among ``names`` (X and Y
    single copy, autosomes two), else every chromosome two copies.  ``"diploid"``,
    ``"male"``, ``"haploid"`` or a dict ``{chrom: copies}`` as :func:`resolve_copies`.
    """
    if ploidy == "auto":
        ploidy = "male" if any(_SEX.get(str(c).lower()) == "Y" for c in names) else "diploid"
    k = resolve_copies(names, ploidy)
    if any(x not in (1, 2) for x in k):
        raise ValueError("diploid input: 1 or 2 copies per chromosome")
    return k


def neighbour_phase_prior(chrom_a, pos_a, chrom_b, pos_b, hap_a, hap_b, *, ploidy: Any = "auto",
                          cis_sep: int = 10_000_000, max_iter: int = 200) -> np.ndarray:
    """EMber's 2-D neighbourhood phase prior (``robust_dip_nbr_prior``; hickit's imputation
    re-implemented): (n, 4) probability of (hap_a, hap_b) per contact, index 2 hap_a + hap_b."""
    from ._engine import diploid_neighbour_prior as _nbr

    ca = np.asarray(chrom_a).astype(str)
    cb = np.asarray(chrom_b).astype(str)
    names = sorted(set(ca.tolist()) | set(cb.tolist()))
    idx = {n: i for i, n in enumerate(names)}
    ia = np.fromiter((idx[c] for c in ca), dtype=np.uint32, count=len(ca))
    ib = np.fromiter((idx[c] for c in cb), dtype=np.uint32, count=len(cb))
    out = _nbr(names, ia, np.ascontiguousarray(pos_a, np.int64), ib, np.ascontiguousarray(pos_b, np.int64),
               np.ascontiguousarray(hap_a, np.int8), np.ascontiguousarray(hap_b, np.int8),
               [int(k) for k in resolve_ploidy(names, ploidy)], int(cis_sep), int(max_iter))
    return np.asarray(out).reshape(len(ia), 4)


def mix_seed_prior(chrom_a, pos_a, chrom_b, pos_b, *, restart: int = 0, **params: Any) -> np.ndarray:
    """Few-cell deconvolution: the first-stage seed (``mix_seed``) of every contact, (n, mix_cells)."""
    from ._engine import mix_seed_prior as _seed

    ca = np.asarray(chrom_a).astype(str)
    cb = np.asarray(chrom_b).astype(str)
    names = sorted(set(ca.tolist()) | set(cb.tolist()))
    idx = {n: i for i, n in enumerate(names)}
    ia = np.fromiter((idx[c] for c in ca), dtype=np.uint32, count=len(ca))
    ib = np.fromiter((idx[c] for c in cb), dtype=np.uint32, count=len(cb))
    p = default_params()
    unknown = set(params) - set(p)
    if unknown:
        raise TypeError(f"unknown parameters: {sorted(unknown)}")
    p.update(params)
    out = _seed(names, ia, np.ascontiguousarray(pos_a, np.int64), ib, np.ascontiguousarray(pos_b, np.int64),
                json.dumps(p), int(restart))
    return np.asarray(out).reshape(len(ia), int(p["mix_cells"]))


def mix_neighbours(chrom_a, pos_a, chrom_b, pos_b, *, radius: int = 10_000_000, min_span: int = 50_000,
                   max_nei: int = 50):
    """2-D neighbours of every contact (hickit's imputation neighbourhood, ``mix::neighbour_lists``):
    (offsets (n + 1,), neighbour indices, weights 1 / (d / span + 0.001))."""
    from ._engine import mix_neighbours as _nb

    ca = np.asarray(chrom_a).astype(str)
    cb = np.asarray(chrom_b).astype(str)
    names = sorted(set(ca.tolist()) | set(cb.tolist()))
    idx = {n: i for i, n in enumerate(names)}
    ia = np.fromiter((idx[c] for c in ca), dtype=np.uint32, count=len(ca))
    ib = np.fromiter((idx[c] for c in cb), dtype=np.uint32, count=len(cb))
    off, nb, w = _nb(names, ia, np.ascontiguousarray(pos_a, np.int64), ib, np.ascontiguousarray(pos_b, np.int64),
                     int(radius), int(min_span), int(max_nei))
    return np.asarray(off), np.asarray(nb), np.asarray(w)


def deconvolve_passes(chrom_a, pos_a, chrom_b, pos_b, *, mix_cells: int, passes: int = 3,
                      group_radius: int = 5_000_000, group_tri_min: int = 1, group_res: int = 1_000_000,
                      group_min_rows: int = 10, group_conf: float = 0.9, group_margin: float = 0.05,
                      group_seed_first: int = 1, group_max_frac: float = 0.8,
                      mix_prior=None, log=None, **params: Any) -> Dict[str, Any]:
    """Few-cell deconvolution in passes (EMber-mix development driver).

    Trans contacts are grouped (2-D single linkage within ``group_radius`` per chromosome pair,
    groups joined by trans-triangle links merged: ``mix_groups``); such groups are almost always of
    one cell.  Pass 1 seeds the largest group to cell 0 (or uses ``mix_prior``); after every pass
    each group of at least ``group_min_rows`` contacts is given, as a whole, the cell its contacts
    prefer in that pass (mean ``cell_probs``, margin ``group_margin``), with probability
    ``group_conf``, and the next pass starts from that seed.  A cell no group was given gets the
    largest group with the weakest preference.  Returns the last pass's result with
    ``passes_log`` (per pass: seeded contacts per cell).
    """
    k = int(mix_cells)
    if group_tri_min == "auto":
        # the smallest trans-triangle threshold whose largest group holds at most `group_max_frac` of
        # one cell's share of the trans rows (deep pools percolate into one mixed group otherwise)
        n_trans = int(np.sum(np.asarray(chrom_a).astype(str) != np.asarray(chrom_b).astype(str)))
        for tm in (1, 2, 3, 5, 10, 20, 40, 80):
            g = mix_groups(chrom_a, pos_a, chrom_b, pos_b, radius=group_radius, min_sep=2**62, tri_min=tm, res=group_res)
            big = np.bincount(g[g >= 0]).max() if (g >= 0).any() else 0
            if big <= group_max_frac * n_trans / k:
                break
    else:
        g = mix_groups(chrom_a, pos_a, chrom_b, pos_b, radius=group_radius, min_sep=2**62, tri_min=int(group_tri_min),
                       res=group_res)
    n = len(g)
    sizes = np.bincount(g[g >= 0]) if (g >= 0).any() else np.zeros(0, int)
    order = np.argsort(sizes)[::-1]
    prior = None if mix_prior is None else np.asarray(mix_prior, np.float64)
    n_first = max(1, min(int(group_seed_first), k))
    if prior is None:
        prior = np.full((n, k), 1.0 / k)
        for j, gi in enumerate(order[:n_first]):
            rows = g == gi
            prior[rows] = (1 - group_conf) / (k - 1)
            prior[rows, j] = group_conf
    plog = []
    res = None
    # cells that have been seeded so far (pass 1: cell 0 only, unless a prior was given); one more
    # cell is seeded per pass, with the largest group that the seeded cells explain worst
    seeded = list(range(k)) if mix_prior is not None else list(range(n_first))
    for it in range(int(passes)):
        res = calc_genome_structure(chrom_a, pos_a, chrom_b, pos_b, mix_cells=k, mix_prior=prior, **params)
        P = res["cell_probs"]
        new = np.full((n, k), 1.0 / k)
        assigned = np.zeros(k, int)
        cand = []
        for gi in order:
            if sizes[gi] < group_min_rows:
                break
            rows = np.flatnonzero(g == gi)
            m = np.nanmean(P[rows], 0)
            if not np.isfinite(m).all():
                continue
            ms = m[seeded]
            j = int(np.argmax(ms))
            s = seeded[j]
            rest = np.delete(m, s)
            if len(seeded) < k and m[seeded].sum() < 0.5:
                cand.append(gi)
                continue
            if m[s] - rest.max() < group_margin:
                continue
            new[rows] = (1 - group_conf) / (k - 1)
            new[rows, s] = group_conf
            assigned[s] += len(rows)
        if len(seeded) < k and cand:
            s = len(seeded)
            rows = g == cand[0]
            new[rows] = (1 - group_conf) / (k - 1)
            new[rows, s] = group_conf
            assigned[s] += int(rows.sum())
            seeded.append(s)
        plog.append({"pass": it + 1, "seeded_per_cell": assigned.tolist(), "cells_seeded": len(seeded),
                     "n_groups": int((sizes >= group_min_rows).sum())})
        if log:
            log(plog[-1])
        prior = new
    res["passes_log"] = plog
    res["groups"] = g
    return res


def mix_groups(chrom_a, pos_a, chrom_b, pos_b, *, radius: int, min_sep: int, tri_min: int = 0,
               res: int = 1_000_000) -> np.ndarray:
    """Few-cell deconvolution: must-link groups of the long-range contacts (2-D single linkage within
    ``radius``; cis contacts closer than ``min_sep`` left out; trans groups joined by >= ``tri_min``
    trans-triangle links merged): group id per contact, -1 = none."""
    from ._engine import mix_groups as _groups

    ca = np.asarray(chrom_a).astype(str)
    cb = np.asarray(chrom_b).astype(str)
    names = sorted(set(ca.tolist()) | set(cb.tolist()))
    idx = {n: i for i, n in enumerate(names)}
    ia = np.fromiter((idx[c] for c in ca), dtype=np.uint32, count=len(ca))
    ib = np.fromiter((idx[c] for c in cb), dtype=np.uint32, count=len(cb))
    return np.asarray(_groups(names, ia, np.ascontiguousarray(pos_a, np.int64), ib, np.ascontiguousarray(pos_b, np.int64),
                              int(radius), int(min_sep), int(tri_min), int(res)))


def calc_genome_structure(
    chrom_a: Sequence[str],
    pos_a: Sequence[int],
    chrom_b: Sequence[str],
    pos_b: Sequence[int],
    *,
    ambiguity: Optional[Sequence[int]] = None,
    active: Optional[Sequence[bool]] = None,
    prior_lr: Optional[Sequence[float]] = None,
    hap_a: Optional[Sequence[int]] = None,
    hap_b: Optional[Sequence[int]] = None,
    ploidy: Any = "auto",
    phase_prior: Optional[Any] = None,
    mix_prior: Optional[Any] = None,
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
    hap_a, hap_b
        Diploid (homolog-resolved) input: haplotype of each contact end, 0, 1 or -1
        (unknown), e.g. ``phase0`` / ``phase1`` of hickit pairs.  Both or neither; with them
        every chromosome copy is its own particle chain (protocols ``nuc_dynamics_2017`` and
        ``robust`` / EMber; see the engine's ``diploid.rs``).
    ploidy
        Diploid input: copies per chromosome, see :func:`resolve_ploidy` (default
        ``"auto"``: male when a Y chromosome is present).
    phase_prior
        Diploid input, optional: (n, 4) prior over the copy pair of each contact (index
        2 hap_a + hap_b), e.g. hickit's imputed ``phase_prob00 .. phase_prob11``; EMber uses
        it as the prior of its candidate copy pairs.
    mix_prior
        Few-cell deconvolution (``mix_cells`` >= 2), optional: (n, k) prior over the cell of every
        contact, used as the first-stage seed instead of ``mix_seed`` (oracle / reference seeding).
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
    Diploid input adds ``copy`` (haplotype of each particle's chain; particles are
    grouped by chromosome, then copy), ``ploidy`` ({chrom: copies}) and ``phase_probs``
    ((n, 4): per input contact the probability of each (hap_a, hap_b) given that it is a
    true contact - EMber's posteriors, or 1 for the closest candidate in the final 2017
    structure; NaN = filtered out); ``contact_weights`` (EMber) is then P(true).
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
    # public name: EMber = protocol "robust" (the engine keeps the internal name)
    p["protocol"] = {"ember": "robust"}.get(p["protocol"], p["protocol"])
    for key in ("temp_steps", "dynamics_steps"):
        if np.isscalar(p[key]):
            p[key] = [int(p[key])]
    p["particle_sizes"] = [float(s) for s in p["particle_sizes"]]
    lr = None if prior_lr is None else np.ascontiguousarray(prior_lr, dtype=np.float64)
    diploid = hap_a is not None or hap_b is not None
    if diploid:
        if hap_a is None or hap_b is None:
            raise ValueError("give both hap_a and hap_b, or neither")
        h_a = np.ascontiguousarray(hap_a, dtype=np.int8)
        h_b = np.ascontiguousarray(hap_b, dtype=np.int8)
        if len(h_a) != n or len(h_b) != n:
            raise ValueError("hap_a / hap_b: one value per contact")
        copies = resolve_ploidy(names, ploidy)
        pr = None
        if phase_prior is not None:
            pr = np.ascontiguousarray(np.asarray(phase_prior, dtype=np.float64).reshape(n, 4)).ravel()
        mp = None if mix_prior is None else np.ascontiguousarray(np.asarray(mix_prior, dtype=np.float64).reshape(n, -1)).ravel()
        res = _calc_genome_structure(names, ia, pa, ib, pb, amb, act, json.dumps(p), lr, h_a, h_b,
                                     [int(k) for k in copies], pr, mp)
    elif mix_prior is not None:
        mp = np.ascontiguousarray(np.asarray(mix_prior, dtype=np.float64).reshape(n, -1)).ravel()
        res = _calc_genome_structure(names, ia, pa, ib, pb, amb, act, json.dumps(p), lr, None, None, None, None, mp)
    else:
        res = _calc_genome_structure(names, ia, pa, ib, pb, amb, act, json.dumps(p), lr)
    ids = list(res["chroms"])
    if res["diploid"]:
        chroms = [names[c // 2] for c in ids]
        copy = np.concatenate([np.full(len(s), c % 2, dtype=np.int8) for c, s in zip(ids, res["seq_pos"])])
    else:
        chroms = [names[c] for c in ids]
    chrom = np.concatenate([np.full(len(s), c, dtype=object) for c, s in zip(chroms, res["seq_pos"])])
    start = np.concatenate(res["seq_pos"]).astype(np.int64)
    out = {
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
        "diploid": bool(res["diploid"]),
    }
    if res.get("mix_cells", 0):
        # few-cell deconvolution: models cell-major (n_models per cell); per input contact
        # P(cell | true) for every cell and P(true) (``contact_weights``), from the final structures
        k = int(res["mix_cells"])
        out["mix_cells"] = k
        out["model_cell"] = np.repeat(np.arange(k), len(res["coords"]) // k)
        out["cell_probs"] = np.asarray(res["cell_probs"], np.float64).reshape(n, k)
    if res["diploid"]:
        out["copy"] = copy
        out["ploidy"] = {c: int(k) for c, k in zip(names, copies)}
        out["phase_probs"] = np.asarray(res["phase_probs"], np.float64).reshape(n, 4)
    return out


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
