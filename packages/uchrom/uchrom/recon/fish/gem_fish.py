"""Joint Hi-C + FISH 3-D reconstruction (GEM-FISH).

Independent PyTorch reimplementation of Abbas et al. 2019
(*Nat. Commun.*, doi:10.1038/s41467-019-10005-6).  Not derived from the
upstream MATLAB source (github.com/ahmedabbas81/GEM-FISH, MIT
licence).

Three-stage pipeline
--------------------
1. **TAD-level coarse model** — optimise the 3-D positions of each TAD
   centre with ``C_g = C_1 + λ_E·C_2 + λ_F·C_3`` (Hi-C KL + polymer
   prior + FISH inter-TAD distance constraints).  See
   :mod:`._tad_level`.
2. **Intra-TAD fine models** — for each TAD, optimise per-bin
   coordinates with ``C_t = C_1 + λ_E·C_2 + λ_R·C_4`` (intra-TAD Hi-C
   KL + polymer prior + FISH radius-of-gyration constraints).  See
   :mod:`._intra_tad`.
3. **Assembly** — translate each intra-TAD cloud so its centroid lies
   at the Stage-1 centre, then rotate each TAD (except the first) so
   its start-anchor points toward the expected neighbouring-TAD
   position.  See :mod:`._assembly`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, List, Optional, Tuple

import numpy as np
import pandas as pd

from ._hic import aggregate_over_tads, load_contact_matrix, contact_to_distance
from ._tad_level import Stage1Params, reconstruct_tad_level
from ._intra_tad import Stage2Params, reconstruct_intra_tad
from ._assembly import assemble


@dataclass
class GEMFISHParams:
    """Runtime parameters for :func:`reconstruct_gem_fish`."""

    # Stage weights
    lambda_E_tad: float = 0.05
    lambda_F: float = 0.01
    lambda_E_intra: float = 0.05
    lambda_R: float = 0.01

    # Stage-1 optimisation
    stage1_iter: int = 1000
    stage1_lr: float = 0.05
    stage1_ensemble: int = 20
    stage1_optimiser: str = "adam"

    # Stage-2 optimisation
    stage2_iter: int = 500
    stage2_lr: float = 0.05
    stage2_ensemble: int = 10

    # Hi-C → distance conversion (Eqn. 10)
    hic_alpha: float = 0.25
    hic_fallback_c: float = 1.0
    hic_fallback_beta: float = 0.5

    # TAD caller passthrough (for the default DI caller)
    tad_di_window: int = 50
    tad_di_smoothing: float = 0.1
    tad_di_min_size_frac: float = 0.05
    tad_max_size_frac: float = 0.05
    """Cap any called TAD at ``tad_max_size_frac * n_bins`` bins.
    Oversized DI windows (often in heterochromatic regions like the
    chr21 p-arm where DI signal is weak) are split into equal chunks.
    Set to 1.0 to disable capping."""

    # Shared
    device: str = "auto"
    verbose: bool = True


# ----------------------------------------------------------------------
# TAD partitioning (default path: strc.tad.get_domains)
# ----------------------------------------------------------------------

def _auto_tads(
    contacts: np.ndarray,
    params: GEMFISHParams,
) -> List[Tuple[int, int]]:
    """Run the Dixon DI TAD caller to partition ``contacts`` into
    contiguous bin windows ``[(s_0, e_0), (s_1, e_1), ...]``.
    """
    import torch
    from uchrom.strc.tad import get_domains

    mat = torch.as_tensor(contacts, dtype=torch.float64)
    windows = get_domains(
        mat,
        smoothing_param=params.tad_di_smoothing,
        min_size_frac=params.tad_di_min_size_frac,
        window=params.tad_di_window,
        device=params.device,
    )
    # get_domains returns end-exclusive (start_idx, end_idx) tuples that
    # mostly tile the chromosome — the last window may stop a few bins
    # short.  Extend it to cover the full matrix so downstream bin
    # counts match.
    out = [(int(s), int(e)) for s, e in windows]
    if out and out[-1][1] < contacts.shape[0]:
        out[-1] = (out[-1][0], int(contacts.shape[0]))

    # Split oversized TADs into equal chunks.  The Dixon DI caller
    # happily lumps low-signal regions (centromeric / heterochromatic
    # arms) into one huge TAD — those break the later assembly step
    # because a 500-bin Gaussian-chain cloud has a Rg so large it
    # can't sit adjacent to a 30-bin neighbour without a pathological
    # boundary bond.
    max_size = max(10, int(contacts.shape[0] * params.tad_max_size_frac))
    capped = []
    for s, e in out:
        n = e - s
        if n <= max_size:
            capped.append((s, e))
            continue
        n_chunks = int(np.ceil(n / max_size))
        chunk = int(np.ceil(n / n_chunks))
        sub_s = s
        while sub_s < e:
            sub_e = min(sub_s + chunk, e)
            capped.append((sub_s, sub_e))
            sub_s = sub_e
    return capped


# ----------------------------------------------------------------------
# FISH aggregation
# ----------------------------------------------------------------------

def _tad_fish_distances(
    fish_cd: Any,
    chrom: str,
    tad_bin_indices: List[Tuple[int, int]],
    bin_df: pd.DataFrame,
) -> np.ndarray:
    """Aggregate FISH-measured distances onto TAD centres.

    For each TAD pair ``(i, j)``, return the median observed distance
    between spots that fall inside TAD i and TAD j across all traces,
    averaged over traces in ``fish_cd``.  NaN if no trace contributes.
    """
    from uchrom.fea.distance import _bin_coord_cube, _pairwise_distance_per_trace

    if fish_cd is None:
        return np.full(
            (len(tad_bin_indices), len(tad_bin_indices)), np.nan,
            dtype=np.float64,
        )

    df = fish_cd.get_chrom(chrom).to_dataframe()
    cube, fish_bin_ids, _ = _bin_coord_cube(df, chrom=chrom)
    # Bin-level distances across all traces
    D = _pairwise_distance_per_trace(cube)  # (n_traces, n_fish_bins, n_fish_bins)
    # Median over traces (ignoring NaN) — our "population" FISH distance
    pop = np.nanmedian(D, axis=0)

    # Map each fish_bin into a TAD index via the Hi-C bin_df start/end,
    # by overlap of FISH (start, end) with the Hi-C bin_df rows.
    hic_bin_starts = bin_df["start"].to_numpy()
    hic_bin_ends = bin_df["end"].to_numpy()
    fish_to_tad = []
    for (fs, fe) in fish_bin_ids:
        mid = 0.5 * (int(fs) + int(fe))
        # find the Hi-C bin that contains this midpoint
        idx = int(np.searchsorted(hic_bin_ends, mid, side="right"))
        if idx >= len(hic_bin_starts) or hic_bin_starts[idx] > mid:
            fish_to_tad.append(-1)
            continue
        # which TAD covers this hic bin?
        tad_of_bin = -1
        for ti, (s, e) in enumerate(tad_bin_indices):
            if s <= idx < e:
                tad_of_bin = ti
                break
        fish_to_tad.append(tad_of_bin)
    fish_to_tad = np.asarray(fish_to_tad, dtype=np.int64)

    n_tads = len(tad_bin_indices)
    sums = np.zeros((n_tads, n_tads), dtype=np.float64)
    cnts = np.zeros((n_tads, n_tads), dtype=np.int64)
    for i in range(pop.shape[0]):
        ti = fish_to_tad[i]
        if ti < 0:
            continue
        for j in range(i + 1, pop.shape[1]):
            tj = fish_to_tad[j]
            if tj < 0:
                continue
            if not np.isfinite(pop[i, j]):
                continue
            sums[ti, tj] += pop[i, j]
            cnts[ti, tj] += 1
            sums[tj, ti] += pop[i, j]
            cnts[tj, ti] += 1
    with np.errstate(invalid="ignore"):
        F = np.where(cnts > 0, sums / np.maximum(cnts, 1), np.nan)
    np.fill_diagonal(F, 0.0)
    return F


def _tad_rg_targets(
    fish_cd: Any,
    chrom: str,
    tad_bin_indices: List[Tuple[int, int]],
    bin_df: pd.DataFrame,
) -> List[Optional[float]]:
    """Per-TAD FISH-derived target :math:`\\hat{R}_g^2`.

    For each TAD, we collect the spots (across all traces) that fall
    inside the TAD's bin range, compute each trace's intra-TAD Rg² (if
    at least 3 finite spots), and return the median across traces.
    Returns ``None`` for TADs without enough data.
    """
    from uchrom.fea.distance import _bin_coord_cube

    if fish_cd is None:
        return [None] * len(tad_bin_indices)

    df = fish_cd.get_chrom(chrom).to_dataframe()
    cube, fish_bin_ids, _ = _bin_coord_cube(df, chrom=chrom)

    # Map FISH bins → TAD index (same as above)
    hic_starts = bin_df["start"].to_numpy()
    hic_ends = bin_df["end"].to_numpy()
    fish_to_tad = []
    for (fs, fe) in fish_bin_ids:
        mid = 0.5 * (int(fs) + int(fe))
        idx = int(np.searchsorted(hic_ends, mid, side="right"))
        if idx >= len(hic_starts) or hic_starts[idx] > mid:
            fish_to_tad.append(-1); continue
        tad_of_bin = -1
        for ti, (s, e) in enumerate(tad_bin_indices):
            if s <= idx < e:
                tad_of_bin = ti; break
        fish_to_tad.append(tad_of_bin)
    fish_to_tad = np.asarray(fish_to_tad, dtype=np.int64)

    out = []
    for ti in range(len(tad_bin_indices)):
        members = np.where(fish_to_tad == ti)[0]
        if members.size < 3:
            out.append(None); continue
        sub_cube = cube[:, members, :]  # (n_traces, n_members, 3)
        # Per-trace Rg² if at least 3 finite spots
        rgs = []
        for t in range(sub_cube.shape[0]):
            coords = sub_cube[t]
            finite = ~np.isnan(coords[:, 0])
            if finite.sum() < 3:
                continue
            xyz = coords[finite]
            centroid = xyz.mean(axis=0)
            rg2 = ((xyz - centroid) ** 2).sum() / xyz.shape[0]
            rgs.append(rg2)
        out.append(float(np.median(rgs)) if rgs else None)
    return out


# ----------------------------------------------------------------------
# Main entry
# ----------------------------------------------------------------------

def reconstruct_gem_fish(
    cd: Any = None,
    chrom: Optional[str] = None,
    resolution: Optional[int] = None,
    fish_cd: Any = None,
    tads: Optional[pd.DataFrame] = None,
    params: Optional[GEMFISHParams] = None,
    return_intermediate: bool = False,
    *,
    contacts: Optional[str] = None,
    fish: Any = None,
    hic_path: Optional[str] = None,
    key_added: Optional[str] = "gem_fish",
) -> Any:
    """End-to-end GEM-FISH reconstruction of one chromosome from a Hi-C map and (optionally) chromatin
    tracing.

    ::

        hic = ds.load("rao2014_imr90_chr21")                 # the map linked to a ChromData
        fish = ds.load("bintu_imr90_hg19")                   # chromatin tracing, same cell line and assembly
        rebin_map(hic, "bulk", resolution=30_000, anchor=fish.bins["start"].min())   # -> "bulk_30kb"
        model = reconstruct_gem_fish(hic, contacts="bulk_30kb", chrom="chr21", fish=fish)

    The path form ``reconstruct_gem_fish("map.cool", "chr21", fish_cd=fish)`` (or ``hic_path=``) still
    works.

    Parameters
    ----------
    cd : ChromData or str
        A ``ChromData`` with the Hi-C map linked (``cd.link_cool``; key ``contacts``), or the path of a
        ``.cool`` / ``.mcool``.  The balanced matrix of the map (its ``weight`` column) is used, at the
        map's resolution.
    chrom : str, optional
        Chromosome as named in the map (may be left out when the map has one chromosome).
    resolution : int, optional
        Required for ``.mcool``; ignored for ``.cool``.
    fish_cd : ChromData, optional
        Older name of ``fish``.
    tads : DataFrame, optional
        Override the TAD partition.  Must have columns ``start`` and
        ``end`` (bp) and be sorted.  If omitted, the Dixon DI caller
        (:func:`uchrom.strc.tad.get_domains`) is run on the Hi-C matrix.
        Only the bins inside these windows are modelled.
    params : GEMFISHParams
    return_intermediate : bool
        If True, return a dict with every intermediate artifact
        (Stage-1 coords, per-TAD coords, loss histories).
    contacts : str, optional
        Key of the linked map (``None``: the only one).
    fish : ChromData, optional
        Chromatin tracing of the same chromosome, same genome assembly as the map (distances in its
        ``coords`` units, e.g. nm).  Supplies the C_3 (TAD-centre distances) and C_4 (per-TAD Rg²)
        targets.  If ``None``, both FISH terms are dropped and the result is a Hi-C-only reconstruction.
    hic_path : str, optional
        Older name of a path ``cd``.
    key_added : str or None
        ``uns`` key of the run's summary and prefix of the stored TAD partition
        (``results["<key_added>.tads"]``); ``None`` stores neither.

    Returns
    -------
    ChromData
        Reconstructed 3-D model with bin-resolution coordinates.  Each
        Hi-C bin of the modelled windows becomes a spot; ``trace_id = 0``
        for the whole chain (single consensus model).  The run summary is
        in ``cd.uns['gem_fish']`` and the TAD partition (``chrom``,
        ``start``, ``end``, ``start_bin``, ``end_bin``; bins of the map,
        end exclusive) in ``cd.results['gem_fish.tads']``.  If
        ``return_intermediate=True``, returns ``(cd, dict)`` with the full
        artefact bundle.
    """
    from uchrom import ChromData

    from uchrom.fea.maps import _is_chromdata, _map_record, map_path

    params = params or GEMFISHParams()
    if hic_path is not None:
        if cd is not None:
            raise TypeError("reconstruct_gem_fish(): pass the map once (cd or hic_path=)")
        cd = hic_path
    if cd is None:
        raise TypeError("reconstruct_gem_fish() needs a ChromData with a linked map, or a path")
    if fish is not None and fish_cd is not None:
        raise TypeError("reconstruct_gem_fish(): pass fish= (or its older name fish_cd=), not both")
    fish_cd = fish if fish is not None else fish_cd
    path = map_path(cd, contacts)
    record = _map_record(cd, contacts)
    if chrom is None:
        import cooler

        names = cooler.Cooler(path if "::" in path or resolution is None else
                              f"{path}::/resolutions/{int(resolution)}").chromnames
        if len(names) != 1:
            raise ValueError(f"the map has {len(names)} chromosomes; pass chrom=")
        chrom = names[0]
    if params.verbose:
        print(f"[gem_fish] loading Hi-C for {chrom} …")
    hic_mat, bin_df = load_contact_matrix(
        path, chrom, resolution=resolution, normalize=True,
    )
    if params.verbose:
        print(f"[gem_fish]   Hi-C matrix: {hic_mat.shape}  "
              f"nnz={int((hic_mat > 0).sum())}")

    # --- TAD partition
    if tads is None:
        if params.verbose:
            print("[gem_fish] calling TADs via Dixon DI …")
        tad_windows = _auto_tads(hic_mat, params)
    else:
        # Convert user-provided (start_bp, end_bp) DataFrame to bin indices
        starts = bin_df["start"].to_numpy()
        ends = bin_df["end"].to_numpy()
        tad_windows = []
        for _, r in tads.iterrows():
            s = int(np.searchsorted(ends, int(r["start"]) + 1, side="left"))
            e = int(np.searchsorted(starts, int(r["end"]), side="left"))
            if e <= s:
                e = s + 1
            tad_windows.append((s, e))
    if params.verbose:
        print(f"[gem_fish]   {len(tad_windows)} TADs")

    # --- Stage 1: TAD-level
    inter_tad_contacts, _ = aggregate_over_tads(
        hic_mat, bin_df,
        pd.DataFrame([
            {"start": int(bin_df["start"].iloc[s]),
             "end":   int(bin_df["end"].iloc[e - 1])}
            for (s, e) in tad_windows
        ]),
    )
    tad_fish_F = _tad_fish_distances(fish_cd, chrom, tad_windows, bin_df)

    if params.verbose:
        print("[gem_fish] Stage 1 — TAD-level reconstruction …")
    s1_params = Stage1Params(
        lambda_E=params.lambda_E_tad,
        lambda_F=params.lambda_F,
        n_iter=params.stage1_iter,
        lr=params.stage1_lr,
        n_ensemble=params.stage1_ensemble,
        optimiser=params.stage1_optimiser,
        device=params.device,
        verbose=params.verbose,
    )
    tad_centres, s1_info = reconstruct_tad_level(
        inter_tad_contacts, tad_fish_F, params=s1_params,
    )

    # --- Stage 2: intra-TAD
    rg_targets = _tad_rg_targets(fish_cd, chrom, tad_windows, bin_df)
    if params.verbose:
        print("[gem_fish] Stage 2 — intra-TAD reconstruction …")
    s2_params = Stage2Params(
        lambda_E=params.lambda_E_intra,
        lambda_R=params.lambda_R,
        n_iter=params.stage2_iter,
        lr=params.stage2_lr,
        n_ensemble=params.stage2_ensemble,
        device=params.device,
        verbose=params.verbose,
    )
    intra_coords, s2_info = reconstruct_intra_tad(
        hic_mat, tad_windows,
        target_rg_sq_per_tad=rg_targets,
        params=s2_params,
    )

    # --- Stage 3: assembly
    if params.verbose:
        print("[gem_fish] Stage 3 — assembly …")
    mid_bp = ((bin_df["start"].to_numpy() + bin_df["end"].to_numpy()) / 2)
    tad_mid_bp = np.array([
        0.5 * (mid_bp[s] + mid_bp[e - 1]) for (s, e) in tad_windows
    ])
    genomic_dist = np.abs(tad_mid_bp[:, None] - tad_mid_bp[None, :])
    inter_tad_gap = contact_to_distance(
        inter_tad_contacts, genomic_distances=genomic_dist,
        alpha=params.hic_alpha,
        fallback_c=params.hic_fallback_c,
        fallback_beta=params.hic_fallback_beta,
    )
    final_coords = assemble(
        tad_centres, intra_coords, inter_tad_distances=inter_tad_gap,
    )
    if params.verbose:
        print(f"[gem_fish] done.  Output: {final_coords.shape}")

    # --- Wrap into ChromData.  The model covers only the bins inside the
    # TAD windows (in window order): user TADs may leave gaps (e.g. the
    # Wang 2016 imaged TADs), so bins outside every window get no spot.
    model_bins = bin_df.iloc[np.concatenate([np.arange(s, e) for (s, e) in tad_windows])]
    if len(model_bins) != len(final_coords):
        raise RuntimeError(f"assembled {len(final_coords)} coordinates for "
                           f"{len(model_bins)} bins in the TAD windows")
    spots = pd.DataFrame({
        "chrom": model_bins["chrom"].values,
        "start": model_bins["start"].astype(int).values,
        "end": model_bins["end"].astype(int).values,
        "trace_id": 0,
    })
    assembly = record.get("genome_assembly") or (cd.uns.get("genome_assembly") if _is_chromdata(cd) else None)
    uns = {
        "xyz_unit": "reduced",   # arbitrary reconstruction units
        "genome_assembly": assembly,
    }
    summary = {
        "n_tads": len(tad_windows),
        "stage1_final_loss": float(s1_info["final_loss"].min()),
        "stage1_best_ensemble": int(s1_info["best_ensemble_idx"]),
        "chrom": str(chrom),
        "contacts": record.get("key", str(path)),
        "fish": fish_cd is not None,
    }
    if key_added is not None:
        uns[key_added] = summary
    model = ChromData(
        coords=final_coords,
        spots=spots,
        uns=uns,
    )
    if key_added is not None:
        tad_table = pd.DataFrame({
            "chrom": str(chrom),
            "start": [int(bin_df["start"].iloc[s]) for s, _ in tad_windows],
            "end": [int(bin_df["end"].iloc[e - 1]) for _, e in tad_windows],
            "start_bin": [int(s) for s, _ in tad_windows],
            "end_bin": [int(e) for _, e in tad_windows],
        })
        model.results.set(
            f"{key_added}.tads", tad_table, kind="table",
            function="uchrom.recon.fish.reconstruct_gem_fish",
            params={k: v for k, v in params.__dict__.items() if k != "verbose"},
            inputs={"contacts": summary["contacts"], "chrom": str(chrom), "fish": summary["fish"],
                    "tads": "given" if tads is not None else "DI caller"},
        )
    if return_intermediate:
        return model, {
            "tad_windows": tad_windows,
            "tad_centres": tad_centres,
            "intra_coords": intra_coords,
            "inter_tad_contacts": inter_tad_contacts,
            "inter_tad_gap": inter_tad_gap,
            "tad_fish_F": tad_fish_F,
            "rg_targets": rg_targets,
            "stage1_info": s1_info,
            "stage2_info": s2_info,
        }
    return model


__all__ = ["GEMFISHParams", "reconstruct_gem_fish"]
