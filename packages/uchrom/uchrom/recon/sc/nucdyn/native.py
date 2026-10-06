"""NucDynamics on the native engine (``uchrom_recon``, Rust; CPU and GPU).

The engine is a separate package (``pip install u-chrom[recon]`` or
``pip install ./packages/uchrom-recon``); this module turns contacts into a
:class:`~chromdata.ChromData` ensemble.
"""

from __future__ import annotations

import os
import warnings
from typing import Any, Dict, Mapping, Optional, Sequence, Union

import numpy as np
import pandas as pd

__all__ = ["reconstruct_nucdyn", "native_available", "engine_info", "load_contacts", "is_phased_file",
           "phasing_stats", "imputed_phase_table"]

#: Default hierarchical schedule (bp), the original's ``-s 8 4 2 0.4 0.2 0.1``.
DEFAULT_PARTICLE_SIZES = (8e6, 4e6, 2e6, 4e5, 2e5, 1e5)

#: Public names of engine protocols: EMber is protocol "robust" of the native engine.
PROTOCOL_ALIASES = {"ember": "robust"}


def _engine():
    try:
        import uchrom_recon
    except ImportError:
        try:                                # a build from before the rename (u-chrom-nucdyn)
            import uchrom_nucdyn as uchrom_recon
        except ImportError:
            raise ImportError("the native engine is not installed: pip install ./packages/uchrom-recon") from None
    return uchrom_recon


def native_available() -> bool:
    """True when the native engine (``uchrom_recon``) can be imported."""
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


def is_phased_file(path) -> bool:
    """True for phased contact files: Dip-C ``.con`` (``.con.gz``, ``.con.txt[.gz]``) and
    ``.pairs`` whose ``#columns:`` header has ``phase0`` / ``phase1`` (hickit)."""
    import gzip

    path = str(path)
    name = path[:-3] if path.endswith(".gz") else path
    if name.endswith((".con", ".con.txt")):
        return True
    if not name.endswith(".pairs"):
        return False
    opener = gzip.open if path.endswith(".gz") else open
    with opener(path, "rt") as fh:
        for line in fh:
            if not line.startswith("#"):
                return False
            if line.startswith("#columns:"):
                cols = line.split()[1:]
                return "phase0" in cols and "phase1" in cols
    return False


def _hap_column(x) -> np.ndarray:
    s = pd.Series(x)
    if s.dtype == object:
        s = s.astype(str).replace({".": "-1", "nan": "-1", "": "-1"})
    return s.astype(float).fillna(-1).to_numpy().astype(np.int8)


def load_contacts(contacts, genome_ranges=None) -> Dict[str, np.ndarray]:
    """Contacts as arrays ``chrom_a, pos_a, chrom_b, pos_b, ambiguity, active``.

    ``contacts`` is a path (``.ncc`` as written by NucProcess; ``.pairs`` /
    ``.pairs.gz``; a whitespace table ``chr_A pos_A chr_B pos_B`` such as the
    GEO files of Stevens et al. 2017) or a DataFrame with columns
    ``chr1, pos1, chr2, pos2`` (as :func:`uchrom.io.read_pairs` returns) or
    ``chrom1, pos1, chrom2, pos2``; optional ``ambiguity`` / ``active``.
    ``genome_ranges`` keeps only contacts with both ends in the given
    ranges (``"chr19"``, ``"chr1:1000000-5000000"``, or a list).

    Phased (homolog-resolved) contacts add ``hap_a`` / ``hap_b`` (int8: 0, 1, -1 = unknown)
    and, for hickit's imputed pairs, ``phase_prob`` ((n, 4), index 2 hap_a + hap_b): files
    for which :func:`is_phased_file` is true (hickit ``.pairs`` with ``phase0`` /
    ``phase1``; Dip-C ``.con``), or DataFrames with ``hap1`` / ``hap2`` (or ``phase0`` /
    ``phase1``; ``.`` = unknown) and optionally ``phase_prob00 .. phase_prob11``
    (:func:`uchrom.io.read_phased_pairs`).
    """
    un = _engine()
    if isinstance(contacts, (str, os.PathLike)):
        path = str(contacts)
        if path.endswith((".ncc", ".ncc.gz")):
            c = un.read_ncc(path)
        elif is_phased_file(path):
            c = un.read_phased_contacts(path)
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
        for ha, hb in (("hap1", "hap2"), ("hap_a", "hap_b"), ("phase0", "phase1")):
            if ha in df.columns and hb in df.columns:
                c["hap_a"] = _hap_column(df[ha])
                c["hap_b"] = _hap_column(df[hb])
                break
        probs = [f"phase_prob{x}" for x in ("00", "01", "10", "11")]
        if "hap_a" in c and all(k in df.columns for k in probs):
            c["phase_prob"] = df[probs].to_numpy(np.float64)
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


def phasing_stats(hap_a, hap_b, chrom_a=None, chrom_b=None, ploidy=None) -> Dict[str, Any]:
    """Phasing of the input contacts: fraction of phased ends; contacts with both / one /
    no end phased.  With ``ploidy``, ends on single-copy chromosomes count as phased."""
    ha = np.asarray(hap_a) >= 0
    hb = np.asarray(hap_b) >= 0
    if ploidy is not None and chrom_a is not None:
        single = {c for c, k in ploidy.items() if k == 1}
        ha = ha | np.isin(np.asarray(chrom_a).astype(str), list(single))
        hb = hb | np.isin(np.asarray(chrom_b).astype(str), list(single))
    n = len(ha)
    return {"n_contacts": int(n), "frac_ends_phased": float((ha.sum() + hb.sum()) / max(2 * n, 1)),
            "n_both_phased": int((ha & hb).sum()), "n_one_phased": int((ha ^ hb).sum()),
            "n_none_phased": int((~ha & ~hb).sum())}


def imputed_phase_table(hap_a, hap_b, phase_probs) -> pd.DataFrame:
    """Per input contact: input haplotypes, the most probable (hap_a, hap_b) and its
    probability (given that the contact is true); -1 / NaN when the contact was filtered out."""
    pp = np.asarray(phase_probs, np.float64)
    ok = np.isfinite(pp).all(1)
    best = np.where(ok, np.argmax(np.nan_to_num(pp, nan=-1.0), axis=1), -1)
    return pd.DataFrame({
        "hap_a": np.asarray(hap_a, np.int8), "hap_b": np.asarray(hap_b, np.int8),
        "imputed_a": np.where(ok, best >> 1, -1).astype(np.int8),
        "imputed_b": np.where(ok, best & 1, -1).astype(np.int8),
        "prob": np.where(ok, np.nan_to_num(pp).max(1), np.nan),
    })


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
    ploidy: Any = None,
    hap_names: Sequence[str] = ("pat", "mat"),
    phase_prior: bool = False,
    _method: str = "nucdyn",
    **engine_params: Any,
):
    """Single-cell Hi-C genome structure ensemble with NucDynamics.

    Runs the hierarchical simulated-annealing protocol of NucDynamics
    (Stevens et al. 2017, *Nature* 544:59) on the native engine and returns
    the ensemble as a new :class:`~chromdata.ChromData`.

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
        ``"robust"`` (public name **EMber**, alias ``"ember"``; see
        :func:`uchrom.recon.sc.ember.reconstruct_ember`): the 2017 protocol with a noise-aware observation model
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
        Further engine parameters (see ``uchrom_recon.default_params()``:
        ``temp_steps``, ``dynamics_steps``, ``temp_start``, ``temp_end``,
        ``time_step``, ``contact_dist_lower``, ...); keyword arguments are
        merged into it.
    ploidy
        Phased (homolog-resolved) contacts — hickit ``.pairs`` with ``phase0`` / ``phase1``,
        Dip-C ``.con``, a DataFrame with ``hap1`` / ``hap2`` (see :func:`load_contacts`) — are
        reconstructed as a diploid genome (protocols ``"nuc_dynamics_2017"`` and
        ``"robust"`` / EMber): one particle chain per chromosome copy, contacts with an
        unphased end ambiguous between the candidate copies (2017: NucDynamics ambiguous
        restraint; EMber: the copy pair is inferred by EM from the structure).  ``ploidy``
        gives the copies per chromosome: ``None`` / ``"auto"`` (male — X and Y single copy —
        when a Y chromosome is present, as hickit), ``"diploid"``, ``"male"``, a dict
        ``{chrom: 1 | 2}``, or ``"haploid"`` (ignore the phases: one chain per chromosome).
    hap_names
        Names of haplotypes 0 and 1 in the trace ids (default Dip-C's ``("pat", "mat")``:
        traces ``chr1(pat)`` / ``chr1(mat)``; single-copy chromosomes keep the plain name).
    phase_prior
        Also use hickit's imputed ``phase_prob00 .. phase_prob11`` (when present) as a prior over
        the candidate copy pairs (default ``False``, the frozen diploid EMber configuration:
        EMber's own 2-D neighbourhood prior ``robust_dip_nbr_prior`` only, no external prior).

    Returns
    -------
    ChromData
        One spot per particle; one trace per chromosome (diploid: per chromosome copy, spot
        column ``haplotype`` = 0 / 1; both copies share the bins).  ``coords`` holds
        model 0 and ``layers['model_<k>']`` holds every model ``k`` (model 0
        included), so the whole ensemble travels with the object.  Units are
        particle radii.  Bins are the particles' genomic intervals: in the
        2017 protocol a particle at sequence position ``p`` collects the
        contacts in ``(p - size, p]`` (``bins.start = p - size``,
        ``bins.end = p``); in release_1.3 ``[p, p + size)``.  ``uns[key_added]``
        records the engine, protocol, parameters and per-stage log.
    """
    from chromdata import ChromData

    un = _engine()
    protocol = PROTOCOL_ALIASES.get(protocol, protocol)
    func = f"uchrom.recon.sc.{_method}.reconstruct_{_method}"
    c = load_contacts(contacts, genome_ranges)
    dev = _resolve_device(device)
    p = dict(params or {})
    p.update(engine_params)
    diploid = "hap_a" in c and ploidy != "haploid"
    dip_kw = {}
    if diploid:
        if protocol not in ("nuc_dynamics_2017", "robust"):
            raise ValueError(f"phased (diploid) contacts need protocol nuc_dynamics_2017 or robust (EMber), not {protocol!r}")
        if len(hap_names) != 2 or hap_names[0] == hap_names[1]:
            raise ValueError("hap_names: two different names")
        dip_kw = dict(hap_a=c["hap_a"], hap_b=c["hap_b"], ploidy="auto" if ploidy is None else ploidy,
                      phase_prior=c.get("phase_prob") if phase_prior else None)
    res = un.calc_genome_structure(
        c["chrom_a"], c["pos_a"], c["chrom_b"], c["pos_b"],
        ambiguity=c["ambiguity"], active=c["active"],
        n_models=int(n_models), device=dev, n_threads=int(n_threads), seed=int(seed),
        protocol=protocol, particle_sizes=[float(s) for s in particle_sizes], verbose=verbose,
        **dip_kw, **p)
    size = int(res["particle_size"])
    pos = np.asarray(res["position"], np.int64)
    if res["position_convention"] == "end":
        start = np.maximum(pos - size, 0)
        end = np.maximum(pos, start + 1)
    else:
        start, end = pos, pos + size
    coords = np.asarray(res["coords"], np.float64)
    if res.get("diploid"):
        chrom = res["chrom"].astype(str)
        copy = np.asarray(res["copy"], np.int8)
        k = res["ploidy"]
        trace = [f"{ch}({hap_names[h]})" if k[ch] == 2 else ch for ch, h in zip(chrom, copy)]
        spots = pd.DataFrame({"chrom": chrom, "start": start, "end": end, "trace_id": trace, "haplotype": copy})
        if cell_id is not None:
            spots["cell_id"] = cell_id
        cd = ChromData(coords[0].copy(), spots)
    else:
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
            "method": _method, "engine": "uchrom_recon", "engine_version": un.__version__, "device": dev,
            "gpu": un.gpu_info() if dev == "gpu" else None, "protocol": protocol,
            "n_models": int(len(coords)), "seed": int(seed), "particle_size": size,
            "particle_position": res["position_convention"],
            "model_layers": [f"model_{k:0{width}d}" for k in range(len(coords))],
            "seconds": float(res["seconds_total"]),
            "citation": ("U-Chrom EMber (engine protocol \"robust\"), built on " if protocol == "robust" else "")
            + "NucDynamics: Stevens et al. 2017, Nature 544:59, doi:10.1038/nature21429",
        }
        cd.uns[key_added] = info
        cd.results.set(f"{key_added}.stages", stages, kind="table",
                       function=func,
                       params={k: v for k, v in res["params"].items() if k != "verbose"},
                       inputs={"contacts": str(contacts) if not isinstance(contacts, pd.DataFrame) else "DataFrame",
                               "n_contacts": int(len(c["pos_a"]))})
        if res.get("diploid"):
            phasing = phasing_stats(c["hap_a"], c["hap_b"], c["chrom_a"], c["chrom_b"], res["ploidy"])
            info["diploid"] = {"ploidy": res["ploidy"], "hap_names": list(hap_names),
                               "phase_prior": bool(phase_prior and "phase_prob" in c), **phasing}
            cd.uns[key_added] = info
            pp =np.asarray(res["phase_probs"], np.float64)
            cd.results.set(f"{key_added}.phase_probs", pp, kind="array", function=func,
                           params={"protocol": protocol, "diploid_cis_sep": res["params"]["diploid_cis_sep"]},
                           inputs={"rows": "input contacts in load_contacts order; columns P(hap_a, hap_b | true) "
                                           "for (0,0), (0,1), (1,0), (1,1); NaN = filtered out",
                                   "method": "EM posterior of the last update" if protocol == "robust"
                                   else "closest candidate copy pair in the final structure"})
            cd.results.set(f"{key_added}.imputed_phase", imputed_phase_table(c["hap_a"], c["hap_b"], pp), kind="table",
                           function=func, params={"protocol": protocol},
                           inputs={"rows": "input contacts in load_contacts order"})
        if protocol == "robust":
            # EM log (one row per update) and the final weight of every input contact
            em = pd.DataFrame([{"stage": s["stage"], "particle_size": s["particle_size"], **u}
                               for s in res["stages"] for u in s.get("robust", [])])
            cd.results.set(f"{key_added}.em", em, kind="table",
                           function=func, params={"protocol": "robust"})
            cd.results.set(f"{key_added}.contact_weights", np.asarray(res["contact_weights"], np.float64),
                           kind="array", function=func,
                           params={"protocol": "robust"},
                           inputs={"rows": "input contacts in load_contacts order; NaN = filtered out"})
    return cd
