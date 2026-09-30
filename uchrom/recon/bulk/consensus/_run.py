"""``reconstruct_consensus``: bulk Hi-C → one consensus structure (ChromData)."""

from __future__ import annotations

import json
import os
import time
import warnings
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Union

import numpy as np
import pandas as pd

from ._contacts import CoolerSource, MatrixSource, resolve_chroms
from ._params import ConsensusParams
from ._restraints import build_stage, engine_stage, load_stage, resolve_alpha_nu, stage_ladder
from ._superpose import (distance_r, kabsch, pairwise_rmsd, radius_of_gyration, spread, spread_by_group,
                         superpose_to_mean)

METHODS = ("anneal",)

CITATIONS = [
    "Engine / integrator / annealing / restraint form: Stevens T.J. et al. (2017) 3D structures of individual "
    "mammalian genomes studied by single-cell Hi-C. Nature 544:59-64. doi:10.1038/nature21429",
    "Contact-distance power law alpha = 4: Wang S. et al. (2016) Science 353:598-602. doi:10.1126/science.aaf8084; "
    "Shi G. & Thirumalai D. (2021) Phys Rev X 11:011051. doi:10.1103/PhysRevX.11.011051",
    "Lorentzian (robust) objective: Trieu T. & Cheng J. (2017) Nucleic Acids Res 45:1049. doi:10.1093/nar/gkw1155",
    "Knight-Ruiz balancing: Knight P.A. & Ruiz D. (2013) IMA J Numer Anal 33:1029. doi:10.1093/imanum/drs019",
]


def _engine():
    import uchrom_nucdyn

    if not hasattr(uchrom_nucdyn, "calc_consensus"):
        raise ImportError("the installed uchrom_nucdyn has no 'consensus' protocol; rebuild native/nucdyn")
    return uchrom_nucdyn


def native_available() -> bool:
    try:
        _engine()
    except ImportError:
        return False
    return True


def _resolve_device(device: str) -> str:
    if device in ("cpu", "gpu"):
        return device
    if device != "auto":
        raise ValueError(f"device must be 'auto', 'cpu' or 'gpu', got {device!r}")
    return "gpu" if _engine().gpu_available() else "cpu"


def _is_chromdata(x: Any) -> bool:
    return hasattr(x, "bins") and hasattr(x, "coords") and hasattr(x, "spots")


def _source(data: Any, bins: Optional[pd.DataFrame], cool_key: str):
    """Contact source + description of the input."""
    if _is_chromdata(data):
        rec = (data.uns.get("linked_cool") or {})
        if not rec:
            raise ValueError("reconstruct_consensus(cd): cd has no linked cool (cd.link_cool(path)); "
                             "or pass a .cool/.mcool path or a count matrix + bins=")
        from uchrom.core.cdata import _linked_record

        r = _linked_record(rec, cool_key)
        path = str(data.resolve_link_path(r["path"])) if not str(r["path"]).startswith(("http", "s3")) else r["path"]
        return CoolerSource(path), {"input": "ChromData.linked_cool", "path": path, "key": cool_key}
    if isinstance(data, (str, os.PathLike)):
        return CoolerSource(str(data)), {"input": "cooler", "path": str(data)}
    if isinstance(data, tuple) and len(data) == 2:
        data, bins = data
    if bins is None:
        raise ValueError("a count matrix needs bins= (DataFrame with chrom, start, end)")
    return MatrixSource(data, bins), {"input": "matrix"}


def _chrom_sizes(src, chroms) -> Dict[str, int]:
    if hasattr(src, "chromsizes"):
        return {c: int(src.chromsizes[c]) for c in chroms}
    b = src.bins
    return {c: int(b.loc[b["chrom"] == c, "end"].max()) for c in chroms}


def reconstruct_consensus(
    data: Any,
    *,
    method: str = "anneal",
    resolution: Optional[int] = None,
    chrom: Optional[Union[str, Sequence[str]]] = None,
    bins: Optional[pd.DataFrame] = None,
    params: Optional[ConsensusParams] = None,
    n_runs: Optional[int] = None,
    seed: Optional[int] = None,
    device: str = "auto",
    key_added: Optional[str] = "consensus.anneal",
    copy: bool = False,
    cool_key: str = "default",
    return_stages: bool = False,
    **overrides: Any,
):
    """One consensus 3-D structure per bulk Hi-C map (whole genome by default).

    Hierarchical restraint annealing on the native engine (``uchrom_nucdyn``,
    protocol ``consensus``; multi-core CPU f64 or wgpu GPU f32): the contact
    map becomes distance restraints at every stage of a resolution ladder
    (e.g. 4 Mb → 1 Mb → 250 kb); ``n_runs`` independent runs (random starts,
    batched) are annealed through all stages, the whole genome together
    (inter-chromosomal restraints at the coarse stages, carried down to the
    fine ones); the output is the medoid run (or the re-relaxed mean) with the
    per-bin spread across runs.  No TAD partitioning.  Algorithm, defaults and
    their justification: ``benchmarks/bulk/consensus/design.md``.

    Parameters
    ----------
    data
        ``.cool`` / ``.mcool`` path or URL (``.mcool``: the coarsest stored level
        dividing each stage resolution is read and summed); a ChromData with a
        linked cool (``cd.link_cool(path)``; ``cool_key`` selects the record); or
        a raw count matrix (``scipy.sparse`` / dense, any triangle) with
        ``bins=`` (chrom, start, end), or a ``(matrix, bins)`` tuple.
    method
        ``"anneal"`` (the only method).
    resolution
        Final resolution in bp (default: the matrix's; required for a cooler).
    chrom
        Chromosomes to model (default: the whole genome minus
        ``params.exclude_chroms`` (Y, M) and unplaced contigs).  A single name
        gives a single-chromosome model.
    params
        :class:`ConsensusParams`; keyword ``overrides`` replace single fields.
    n_runs, seed
        Shortcuts for ``params.n_runs`` / ``params.seed``.
    device
        ``"auto"`` (GPU when available), ``"cpu"``, ``"gpu"``.
    key_added
        ``results`` key of the per-run table (and of the consensus table in a
        ChromData input with ``copy=False``); ``None`` stores nothing.
    copy
        Only for a ChromData input: ``False`` (default) also stores the
        consensus table (bin, x, y, z, spread) in ``data.results[key_added]``;
        either way a new ChromData with the structure is returned (a
        reconstruction has its own loci, like ``reconstruct_nucdyn``).
    return_stages
        Also keep every stage's runs in ``uns['consensus']['stage_coords']``.

    Returns
    -------
    ChromData with one cell (``consensus``) and one trace per chromosome;
    ``bins`` = all bins of the final resolution (spots only for bins with
    enough coverage); ``coords`` = the consensus structure; ``layers['run_k']``
    = every run superposed on it, ``layers['mean_refined']`` (when computed);
    ``bin_tracks``: ``consensus_spread`` (whole-structure superposition),
    ``consensus_spread_chrom`` (per-chromosome superposition), ``n_restraints``;
    ``uns['consensus']``: parameters, alpha / nu / decay fit, stage logs,
    per-run statistics, run-to-run precision, timings; ``results[key_added]``:
    per-run table.  Units: the distance of adjacent final bins (``scale_nm``:
    nm).
    """
    from uchrom.core import ChromData
    from uchrom.core.results import ResultsStore

    if method not in METHODS:
        raise ValueError(f"unknown method {method!r}; available: {METHODS}")
    p = params if params is not None else ConsensusParams()
    if overrides:
        import dataclasses

        unknown = set(overrides) - {f.name for f in dataclasses.fields(ConsensusParams)}
        if unknown:
            raise TypeError(f"unknown consensus parameters: {sorted(unknown)}")
        p = p.replace(**overrides)
    if n_runs is not None:
        p = p.replace(n_runs=int(n_runs))
    if seed is not None:
        p = p.replace(seed=int(seed))
    p.validate()
    un = _engine()
    t0 = time.time()
    src, input_desc = _source(data, bins, cool_key)
    final = int(resolution) if resolution is not None else int(src.base_res)
    if final % src.base_res:
        raise ValueError(f"resolution {final} is not a multiple of the input resolution {src.base_res}")
    chroms = resolve_chroms(src.chrom_names, chrom, p.exclude_chroms)
    if not chroms:
        raise ValueError("no chromosomes to model")
    ladder = stage_ladder(final, p)
    # ---- contacts of every stage
    pixels = []
    sizes = _chrom_sizes(src, chroms)
    for k, res in enumerate(ladder):
        n_est = int(sum(np.ceil(L / res) for L in sizes.values()))
        # genome-wide (cis + trans, whole chromosomes): the first stage, stages with bins
        # >= trans_max_resolution, and any stage small enough to take every pair
        kind = "genome" if (k == 0 or res >= p.trans_max_resolution or n_est <= p.dense_max_bins) else "cis"
        max_sep = max(p.long_cis_max_bins, p.band_min_bins,
                      int(np.ceil(p.band_factor * (ladder[k - 1] / res))) if k else 0)
        pixels.append(load_stage(src, res, chroms, kind, max_sep, p))
        if p.verbose:
            print(f"[consensus] stage {k + 1} ({res} bp, {kind}): {len(pixels[-1].i)} pixels, "
                  f"{int(pixels[-1].valid.sum())} valid bins, {pixels[-1].seconds:.1f} s", flush=True)
    alpha, nu, decay = resolve_alpha_nu(p, pixels, final)
    # ---- restraints of every stage
    models = []
    for k, px in enumerate(pixels):
        models.append(build_stage(px, k, final, ladder[k - 1] if k else None, models[-1] if k else None, alpha, nu, p))
        pixels[k] = None  # free
        if p.verbose:
            print(f"[consensus] stage {k + 1}: {models[-1].n_beads} beads, restraints {models[-1].counts()}", flush=True)
    t_prep = time.time() - t0
    dev = _resolve_device(device)
    n0 = models[0].n_beads
    rr = p.random_radius if p.random_radius is not None else models[0].D * max(2.0, n0 ** (1 / 3))
    eng_p = {"n_runs": p.n_runs, "seed": p.seed, "device": dev, "n_threads": p.n_threads,
             "lorentz_width": p.lorentz_width, "confinement_radius": p.confinement_radius,
             "confinement_k": p.confinement_k, "random_radius": float(rr), "time_step": p.time_step,
             "keep_stages": bool(return_stages), "verbose": p.verbose}
    stages = [engine_stage(m, k, p) for k, m in enumerate(models)]
    res = un.calc_consensus(stages, json.dumps(eng_p))
    runs = np.asarray(res["coords"], np.float64)
    logs = json.loads(res["stages_json"])
    fin = models[-1]
    # ---- consensus: medoid of the lowest-energy runs
    energy = np.array([r["energy"] for r in logs[-1]["runs"]])
    n_keep = max(1, int(round(p.keep_fraction * p.n_runs)))
    keep = np.argsort(energy, kind="stable")[:n_keep]
    R = pairwise_rmsd(runs) if p.n_runs > 1 else np.zeros((1, 1))
    medoid = int(keep[np.argmin(R[np.ix_(keep, keep)].sum(1))])
    aligned, mean = superpose_to_mean(runs, runs[medoid])
    ref = kabsch(mean, runs[medoid])[0]
    aligned = np.stack([kabsch(ref, r)[0] for r in runs])
    sp_all = spread(aligned)
    sp_chr = spread_by_group(runs, fin.bead_chrom) if p.n_runs > 1 else np.zeros(fin.n_beads)
    rg = radius_of_gyration(ref)
    mean_ref = None
    refine_log = None
    if p.refine_mean and p.n_runs > 1:
        st = dict(stages[-1])
        st.update(temp_start=float(p.mean_refine_temp_start), temp_end=float(p.temp_end),
                  temp_steps=int(p.mean_refine_temp_steps), dyn_steps=int(p.mean_refine_dyn_steps))
        rp = dict(eng_p, n_runs=1, keep_stages=False, seed=p.seed + 1_000_003)
        rres = un.calc_consensus([st], json.dumps(rp), aligned.mean(0)[None].copy())
        mean_ref = kabsch(ref, np.asarray(rres["coords"], np.float64)[0])[0]
        refine_log = json.loads(rres["stages_json"])[0]
    cons = ref if p.consensus == "medoid" else mean_ref
    # run-to-run precision
    iu = np.triu_indices(p.n_runs, 1)
    rng = np.random.default_rng(p.seed)
    nb = fin.n_beads
    npair = min(200_000, nb * (nb - 1) // 2)
    pi = rng.integers(0, nb, npair)
    pj = rng.integers(0, nb, npair)
    ok = pi != pj
    pi, pj = pi[ok], pj[ok]
    rpair = [distance_r(runs[a], runs[b], pairs=(pi, pj)) for a, b in zip(*iu)] if p.n_runs > 1 else []
    precision = {"rmsd_median": float(np.median(R[iu])) if p.n_runs > 1 else 0.0,
                 "rmsd_median_over_rg": float(np.median(R[iu]) / rg) if p.n_runs > 1 else 0.0,
                 "distance_r_median": float(np.median(rpair)) if rpair else 1.0,
                 "distance_r_min": float(np.min(rpair)) if rpair else 1.0,
                 "spread_median": float(np.median(sp_all)), "spread_chrom_median": float(np.nanmedian(sp_chr)),
                 "rg": rg}
    scale = float(p.scale_nm) if p.scale_nm else 1.0
    unit = "nm" if p.scale_nm else "adjacent final-bin distance (D_final = 1)"
    # ---- ChromData
    bins_df = fin.bins[["chrom", "start", "end"]].reset_index(drop=True)
    spots = pd.DataFrame({"bin_id": fin.bead_bin.astype(np.int64),
                          "trace_id": pd.Categorical([f"consensus:{c}" for c in np.asarray(chroms)[fin.bead_chrom]]),
                          "cell_id": "consensus"})
    width = max(1, len(str(p.n_runs - 1)))
    layers = {f"run_{k:0{width}d}": aligned[k] * scale for k in range(p.n_runs)}
    if mean_ref is not None:
        layers["mean_refined"] = mean_ref * scale
    nrest = np.zeros(len(bins_df))
    np.add.at(nrest, fin.bead_bin[fin.rest["i"].to_numpy()], 1)
    np.add.at(nrest, fin.bead_bin[fin.rest["j"].to_numpy()], 1)
    bt = pd.DataFrame({"consensus_spread": np.nan, "consensus_spread_chrom": np.nan, "n_restraints": nrest},
                      index=bins_df.index)
    bt.loc[fin.bead_bin, "consensus_spread"] = sp_all * scale
    bt.loc[fin.bead_bin, "consensus_spread_chrom"] = sp_chr * scale
    run_tab = pd.DataFrame([{**r, "run": k, "kept": bool(k in set(keep.tolist())), "medoid": k == medoid,
                             "rmsd_to_consensus": float(kabsch(cons, aligned[k])[1] * scale)}
                            for k, r in enumerate(logs[-1]["runs"])]).set_index("run")
    stage_info = []
    for m, lg in zip(models, logs):
        stage_info.append({**{k: v for k, v in lg.items() if k != "runs"},
                           "restraints": m.counts(), "D": m.D, **{k: v for k, v in m.info.items()},
                           "runs": lg["runs"]})
    prov = p.to_dict()
    uns_c = {
        "method": "anneal", "protocol": "consensus (native uchrom_nucdyn)", "engine_version": un.__version__,
        "device": dev, "gpu": un.gpu_info() if dev == "gpu" else None, "params": prov,
        "chroms": list(chroms), "resolution": final, "stage_resolutions": ladder, "alpha": alpha, "nu": nu,
        "decay_fit": decay, "input": {**input_desc, **src.describe()}, "stages": stage_info,
        "consensus": p.consensus, "medoid_run": medoid, "kept_runs": keep.tolist(), "precision": precision,
        "random_radius": rr, "mean_refine": refine_log,
        "seconds_prepare": t_prep, "seconds_engine": float(res["seconds_total"]),
        "seconds_total": time.time() - t0, "xyz_unit": unit, "citations": CITATIONS,
    }
    if return_stages:
        uns_c["stage_coords"] = [np.asarray(c) for c in res["stage_coords"]]
        uns_c["stage_beads"] = [{"bin_start": m.bins["start"].to_numpy()[m.bead_bin],
                                 "chrom": np.asarray(chroms)[m.bead_chrom]} for m in models]
    out = ChromData(cons * scale, spots, bins=bins_df, layers=layers,
                    uns={"consensus": uns_c, "xyz_unit": unit})
    out.bin_tracks = bt
    rs = ResultsStore()
    if key_added is not None:
        rs.set(key_added, run_tab.reset_index(), kind="table",
               function="uchrom.recon.bulk.consensus.reconstruct_consensus", params=prov,
               inputs={**input_desc, "resolution": final, "chroms": list(chroms)})
    out.results = rs
    if _is_chromdata(data) and key_added is not None and not copy:
        tab = bins_df.iloc[fin.bead_bin].copy()
        tab[["x", "y", "z"]] = cons * scale
        tab["spread"] = sp_all * scale
        data.results.set(key_added, tab.reset_index(names="bin"), kind="table",
                         function="uchrom.recon.bulk.consensus.reconstruct_consensus", params=prov,
                         inputs={**input_desc, "resolution": final})
    return out
