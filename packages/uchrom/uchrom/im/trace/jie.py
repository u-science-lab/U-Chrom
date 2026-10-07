"""jie — spatial genome aligner entry point.

Independent reimplementation of Jia & Ren 2022 (*Nature Biotechnology*
22, doi:10.1038/s41587-022-01568-9).  Not derived from
``github.com/b2jia/jie`` (GPL-3.0).

Usage
-----
>>> from uchrom.im.trace import align_spots, SpotAlignerParams
>>> traced = align_spots(detections, params=SpotAlignerParams())   # a ChromData
>>> cd = align_spots(spots_df, params=SpotAlignerParams())          # or a table

Input contract
--------------
The detections are a ``ChromData`` (e.g. :func:`uchrom.io.read_seqfish_detections`;
its traces are ignored, ``cell_id`` is required) or a long-format
``pandas.DataFrame``, one row per FISH detection.  Required columns:

- ``cell_id``   — grouping key for per-cell tracing
- ``chrom``     — decoded chromosome
- ``start``,``end`` — decoded genomic locus (bp)
- ``x``,``y``,``z`` — 3-D coordinates (nm)

Optional columns:

- ``sigma_x``,``sigma_y``,``sigma_z`` — per-spot axis-wise localisation
  uncertainty (nm).  If absent, ``params.default_sigma_nm`` is used.
- ``spot_id`` — arbitrary label carried through to the output.

Unlike a FOF-CT table, ``spots_df`` may have **multiple rows per
(cell_id, chrom, start, end)** — the aligner disambiguates them.

Output
------
A :class:`~chromdata.ChromData` whose ``spots`` table contains the
kept detections with a populated ``trace_id``.  ``cd.traces`` has one
row per fiber with ``cell_id, chrom, mean_edge, sister_group``.
``cd.results['ploidy']`` summarises the per-(cell, chrom) fiber count.
``cd.uns['jie_polymer']`` holds the per-chromosome τ fit.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Dict, List, Optional, Tuple

if TYPE_CHECKING:
    from chromdata import ChromData

import numpy as np
import pandas as pd

from ._polymer import (
    PERSISTENCE_LENGTH_BP_DEFAULT,
    fit_scale_factor,
)
from ._graph import (
    iterative_karyotype,
    detect_sister_pairs,
)


@dataclass
class SpotAlignerParams:
    """Runtime parameters for :func:`align_spots`."""

    # ---------- polymer model ----------
    persistence_length_bp: float = PERSISTENCE_LENGTH_BP_DEFAULT
    tau_nm_per_bp: Optional[float] = None
    """Genomic-to-spatial scale.  If ``None``, fit per-chromosome from
    the aggregate observed-distance-vs-genomic-distance curve."""
    scaling_exponent_fixed: bool = True
    """If True, force α=0.5 (ideal Gaussian chain) in the τ fit.  Set
    False to fit α jointly — useful for crumpled-globule chromatin."""
    default_sigma_nm: float = 50.0
    """Fallback localisation σ when ``sigma_*`` columns absent from
    ``spots_df`` (axis-wise, nm)."""

    # ---------- graph construction ----------
    max_skip: int = 3
    gap_penalty: float = 3.0
    """Additive per-skip penalty in the Mahalanobis-cost edge weight.
    A skip-0 edge (adjacent locus) adds nothing; a skip-2 edge adds
    ``2 * gap_penalty``.  Calibrate against typical ``R² / 2S²``
    (around 1.5 for on-chain matches)."""

    # ---------- karyotype ----------
    max_fibers_per_chrom: int = 8
    min_spots_per_fiber: int = 5
    mean_edge_weight_cutoff: float = np.inf

    # ---------- sister detection ----------
    detect_sisters: bool = True
    sister_pair_radius_nm: float = 300.0

    # ---------- runtime ----------
    verbose: bool = False


# ----------------------------------------------------------------------
# Per-chromosome τ fitting (dataset-wide)
# ----------------------------------------------------------------------

def _fit_tau_global(
    spots_df: pd.DataFrame,
    params: SpotAlignerParams,
) -> Dict[str, Tuple[float, float]]:
    """Fit τ per chromosome from the aggregate spot distribution.

    For each chromosome, uses all (cell, locus_i, locus_j) pairs where
    at least one spot exists at each locus in the same cell, and takes
    the **median** observed distance vs genomic separation across all
    such pairs.  Regression is on ``log(<R>)`` vs ``log L``.

    Returns
    -------
    Dict[str, (tau, alpha)]
    """
    out: Dict[str, Tuple[float, float]] = {}

    for chrom, chrom_df in spots_df.groupby("chrom", observed=True):
        # Use one spot per (cell, locus) — pick the first for fitting.
        # (τ-fitting doesn't require correct assignment, only rough scale.)
        agg = chrom_df.groupby(
            ["cell_id", "start", "end"], observed=True
        ).first().reset_index()
        Rvals: List[float] = []
        Lvals: List[float] = []
        for _, cell_spots in agg.groupby("cell_id", observed=True):
            xyz = cell_spots[["x", "y", "z"]].to_numpy()
            mids = (cell_spots["start"].to_numpy()
                    + cell_spots["end"].to_numpy()) / 2
            n = xyz.shape[0]
            if n < 3:
                continue
            for i in range(n):
                for j in range(i + 1, n):
                    L = abs(mids[j] - mids[i])
                    if L <= 0:
                        continue
                    R = float(np.linalg.norm(xyz[i] - xyz[j]))
                    Rvals.append(R)
                    Lvals.append(float(L))
        if len(Rvals) < 10:
            out[str(chrom)] = (0.01, 0.5)  # fallback
            continue
        tau, alpha = fit_scale_factor(
            np.asarray(Rvals), np.asarray(Lvals),
            l_p_bp=params.persistence_length_bp,
            fix_exponent=params.scaling_exponent_fixed,
        )
        out[str(chrom)] = (tau, alpha)
    return out


# ----------------------------------------------------------------------
# Per (cell, chrom) tracing
# ----------------------------------------------------------------------

def _trace_one(
    sub_df: pd.DataFrame,
    chrom: str,
    tau_nm_per_bp: float,
    params: SpotAlignerParams,
) -> Tuple[List[dict], List[int], List[Tuple[int, int]]]:
    """Trace one cell's one chromosome.

    Returns
    -------
    fibers : list of dict
        One per called fiber, with keys ``spots`` (indices into
        ``sub_df``), ``path_weight``, ``mean_edge``.
    sister_group : list of int
        Group index per fiber (same index = sisters).
    bin_ids : list of (start, end)
        Ordered unique (start, end) in ``sub_df``.
    """
    # Build unique locus list (ordered by start)
    uniq = (
        sub_df[["start", "end"]]
        .drop_duplicates()
        .sort_values("start", kind="mergesort")
        .reset_index(drop=True)
    )
    bin_ids = [(int(s), int(e)) for s, e in zip(uniq["start"], uniq["end"])]
    bin_bp = np.array([0.5 * (s + e) for s, e in bin_ids], dtype=np.float64)
    locus_to_idx = {(int(s), int(e)): i for i, (s, e) in enumerate(bin_ids)}

    spot_xyz = sub_df[["x", "y", "z"]].to_numpy(dtype=np.float64)
    spot_locus = np.array(
        [locus_to_idx[(int(r["start"]), int(r["end"]))]
         for _, r in sub_df.iterrows()],
        dtype=np.int64,
    )
    if {"sigma_x", "sigma_y", "sigma_z"}.issubset(sub_df.columns):
        sigma = sub_df[["sigma_x", "sigma_y", "sigma_z"]].to_numpy(
            dtype=np.float64
        )
    else:
        sigma = np.full(spot_xyz.shape[0], params.default_sigma_nm,
                        dtype=np.float64)

    fibers = iterative_karyotype(
        spot_xyz, spot_locus, bin_bp, sigma,
        l_p_bp=params.persistence_length_bp,
        tau_nm_per_bp=tau_nm_per_bp,
        max_skip=params.max_skip,
        gap_penalty=params.gap_penalty,
        max_fibers=params.max_fibers_per_chrom,
        min_spots_per_fiber=params.min_spots_per_fiber,
        mean_edge_weight_cutoff=params.mean_edge_weight_cutoff,
    )

    if params.detect_sisters and fibers:
        groups = detect_sister_pairs(
            fibers, spot_xyz, spot_locus,
            pair_radius_nm=params.sister_pair_radius_nm,
        )
    else:
        groups = list(range(len(fibers)))

    return fibers, groups, bin_ids


# ----------------------------------------------------------------------
# Main entry point
# ----------------------------------------------------------------------

_TO_NM = {"nm": 1.0, "nanometer": 1.0, "um": 1000.0, "micron": 1000.0, "µm": 1000.0,
          "micrometer": 1000.0}


def _detections_table(cd, chrom, cells):
    """A ChromData of detections -> ``(table, subset)``: the aligner's table (coordinates in nm,
    ``cell_id`` / ``chrom`` as str, a ``_row`` column into ``subset``) and the selected detections."""
    from uchrom.convention import select_spots

    unit = str(cd.uns.get("xyz_unit", "nm")).strip().lower()
    if unit not in _TO_NM:
        raise ValueError(f"align_spots: cannot convert xyz_unit {unit!r} to nm")
    sub = select_spots(cd, cells=cells)
    if chrom is not None:
        keep = {str(c) for c in ([chrom] if isinstance(chrom, str) else chrom)}
        sub = sub[sub.spots["chrom"].astype(str).isin(keep).to_numpy()]
    if "cell_id" not in sub.spots.columns:
        raise ValueError("align_spots: the detections need a cell_id column")
    df = sub.to_dataframe()
    # what the aligner reads; the other spot columns come back through _row (see _carry)
    df = df[[c for c in ("spot_id", "cell_id", "chrom", "start", "end", "x", "y", "z",
                         "sigma_x", "sigma_y", "sigma_z") if c in df.columns]].copy()
    df["cell_id"] = df["cell_id"].astype(str)
    df["chrom"] = df["chrom"].astype(str)
    df["_row"] = np.arange(len(df))
    factor = _TO_NM[unit]
    if factor != 1.0:
        df[["x", "y", "z"]] = df[["x", "y", "z"]].to_numpy() * factor
    return df, sub


def align_spots(
    spots_df,
    params: Optional[SpotAlignerParams] = None,
    tau_by_chrom: Optional[Dict[str, float]] = None,
    *,
    chrom=None,
    cells=None,
) -> "ChromData":
    """Assign detected FISH spots to chromatin fibers.

    Parameters
    ----------
    spots_df : ChromData or DataFrame
        The detections (see the module docstring): a ``ChromData`` whose spots carry ``cell_id`` (its
        ``trace_id`` is ignored — e.g. one candidate set per cell and chromosome, as
        :func:`uchrom.io.read_seqfish_detections` gives), or a table with ``cell_id, chrom, start, end,
        x, y, z`` in nm.
    params : SpotAlignerParams, optional
    tau_by_chrom : dict, optional
        τ (nm per bp) per chromosome; fitted from the data when omitted.
    chrom : str or list, optional
        Align these chromosomes only.
    cells : list, optional
        Align these cells only.

    Returns
    -------
    ChromData
        The detections placed on a fibre, ``trace_id`` = the fibre; ``traces`` (one row per fibre),
        ``results['ploidy']``, ``uns['jie_polymer']`` / ``uns['jie_params']``.  From a ``ChromData`` the
        result keeps its locus axis (``bins``), ``cells``, ``uns``, coordinate unit, the other spot columns
        (``spot_id``, ``label``, …) and ``spot_tracks``; from a table, coordinates are in nm.
    """
    from chromdata import ChromData

    params = params or SpotAlignerParams()
    source = None
    if isinstance(spots_df, pd.DataFrame):
        if cells is not None:
            spots_df = spots_df[spots_df["cell_id"].astype(str).isin({str(c) for c in cells})]
        if chrom is not None:
            keep = {str(c) for c in ([chrom] if isinstance(chrom, str) else chrom)}
            spots_df = spots_df[spots_df["chrom"].astype(str).isin(keep)]
    else:
        spots_df, source = _detections_table(spots_df, chrom, cells)

    required = {"cell_id", "chrom", "start", "end", "x", "y", "z"}
    missing = required - set(spots_df.columns)
    if missing:
        raise ValueError(f"spots_df missing required columns: {missing}")

    # ---------------------------------------------------------
    # τ fitting
    # ---------------------------------------------------------
    if tau_by_chrom is None:
        if params.tau_nm_per_bp is None:
            if params.verbose:
                print("[jie] fitting τ per chromosome...")
            fits = _fit_tau_global(spots_df, params)
            tau_by_chrom = {c: t for c, (t, _) in fits.items()}
            uns_polymer = {
                c: {"tau_nm_per_bp": float(t),
                    "scaling_exponent": float(a),
                    "l_p_bp": float(params.persistence_length_bp)}
                for c, (t, a) in fits.items()
            }
        else:
            tau_by_chrom = {
                str(c): float(params.tau_nm_per_bp)
                for c in spots_df["chrom"].unique()
            }
            uns_polymer = {
                c: {"tau_nm_per_bp": float(params.tau_nm_per_bp),
                    "scaling_exponent": 0.5,
                    "l_p_bp": float(params.persistence_length_bp)}
                for c in tau_by_chrom
            }
    else:
        uns_polymer = {
            c: {"tau_nm_per_bp": float(t),
                "scaling_exponent": 0.5,
                "l_p_bp": float(params.persistence_length_bp)}
            for c, t in tau_by_chrom.items()
        }

    if params.verbose:
        print(f"[jie] τ per chrom: "
              f"{ {c: round(t, 5) for c, t in tau_by_chrom.items()} }")

    # ---------------------------------------------------------
    # Per (cell, chrom) trace assignment
    # ---------------------------------------------------------
    spots_out: List[dict] = []
    coords_out: List[np.ndarray] = []
    traces_out: List[dict] = []
    ploidy_out: List[dict] = []
    next_global_tid = 0
    next_global_sg = 0

    total_groups = spots_df.groupby(["cell_id", "chrom"], observed=True).ngroups
    for gi, ((cell_id, chrom), sub_df) in enumerate(
        spots_df.groupby(["cell_id", "chrom"], observed=True)
    ):
        sub_df = sub_df.reset_index(drop=True)
        tau = tau_by_chrom.get(str(chrom), 0.01)
        fibers, sis_groups, _ = _trace_one(
            sub_df, str(chrom), tau, params,
        )
        # Re-number sister groups into the global namespace
        sg_map = {}
        for sg in sis_groups:
            if sg not in sg_map:
                sg_map[sg] = next_global_sg
                next_global_sg += 1

        for fi, fiber in enumerate(fibers):
            tid = next_global_tid
            next_global_tid += 1
            sg_id = sg_map[sis_groups[fi]]
            for spot_idx in fiber["spots"]:
                row = sub_df.iloc[spot_idx]
                spot_entry = {
                    "chrom": str(chrom),
                    "start": int(row["start"]),
                    "end": int(row["end"]),
                    "trace_id": tid,
                    "cell_id": cell_id,
                }
                if "spot_id" in sub_df.columns:
                    spot_entry["spot_id"] = row["spot_id"]
                if source is not None:
                    spot_entry["_row"] = int(row["_row"])
                spots_out.append(spot_entry)
                coords_out.append(np.asarray([
                    row["x"], row["y"], row["z"],
                ], dtype=np.float64))
            traces_out.append({
                "trace_id": tid,
                "cell_id": cell_id,
                "chrom": str(chrom),
                "n_spots": len(fiber["spots"]),
                "path_weight": float(fiber["path_weight"]),
                "mean_edge": float(fiber["mean_edge"]),
                "sister_group": sg_id,
            })

        ploidy_out.append({
            "cell_id": cell_id,
            "chrom": str(chrom),
            "n_fibers": len(fibers),
            "n_sister_groups": len(sg_map),
            "tau_nm_per_bp": float(tau),
        })
        if params.verbose and (gi + 1) % 20 == 0:
            print(f"[jie] traced {gi + 1}/{total_groups} (cell, chrom) groups")

    if not coords_out:
        raise ValueError(
            "No fibers called — check inputs, min_spots_per_fiber, "
            "and gap_penalty calibration."
        )

    coords = np.vstack(coords_out)
    spots = pd.DataFrame(spots_out)
    traces = pd.DataFrame(traces_out)
    ploidy = pd.DataFrame(ploidy_out)

    uns = {
        "jie_polymer": uns_polymer,
        "jie_params": {
            "persistence_length_bp": params.persistence_length_bp,
            "max_skip": params.max_skip,
            "gap_penalty": params.gap_penalty,
            "default_sigma_nm": params.default_sigma_nm,
            "min_spots_per_fiber": params.min_spots_per_fiber,
        },
    }
    if source is not None:
        cd = _carry(source, spots, traces, ploidy, uns)
    else:
        cd = ChromData(
            coords=coords,
            spots=spots,
            traces=traces,
            uns=uns,
            results={"ploidy": ploidy},
        )
    if params.verbose:
        print(f"[jie] → {len(traces)} fibers across "
              f"{spots_df['cell_id'].nunique()} cells")
    return cd


def _carry(source, spots, traces, ploidy, uns):
    """The aligned spots as a ChromData that keeps the input's coordinates (and unit), locus axis, cells,
    uns, spot columns and spot tracks (rows of ``source`` picked by ``spots['_row']``)."""
    from chromdata import ChromData

    rows = spots["_row"].to_numpy(dtype=np.int64)
    coords = np.asarray(source.coords, dtype=np.float64)[rows]
    src = source.spots
    out = spots.drop(columns=["_row"])
    for c in src.columns:
        if c not in out.columns and c not in ("trace_id", "bin_id", "chrom", "start", "end"):
            out[c] = src[c].to_numpy()[rows]
    out = out.drop(columns=["chrom", "start", "end"])
    out["bin_id"] = src["bin_id"].to_numpy()[rows]
    tracks = source.spot_tracks.iloc[rows].reset_index(drop=True) if len(source.spot_tracks.columns) else None
    cells = source.cells if len(source.cells) else None
    return ChromData(coords, out, bins=source.bins, cells=cells, traces=traces, spot_tracks=tracks,
                     uns={**source.uns, **uns}, results={"ploidy": ploidy})


__all__ = [
    "SpotAlignerParams",
    "align_spots",
]
