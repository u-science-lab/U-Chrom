"""Nanoscale DNA tracing of the Ellenberg lab (LoopTrace; Beckwith et al. 2025, *Cell* and *Nat. Commun.*).

The authors' tables (figshare 27003022 and 27613239, CC BY 4.0) hold one row per fitted spot: the 3-D Gaussian
fit (``x, y, z`` in nm, ``A`` signal over background, ``BG``, ``sigma_xy``, ``sigma_z``), the probe library
(``region`` / ``region_name``) and the spot's genomic position in it (``g_pos``, hg38).  Three tables:

* ``mitofold_traces.csv.gz`` (*Cell* 2025, mitotic chromosomes): HeLa Kyoto WT, SMC4-depleted (``HK_dSMC4``) and
  TSA-treated cells, eight libraries (1-Mb regions at 12 kb, 10-Mb regions at 200 kb, chromosomes 2 and 14 at
  1 Mb); ``trace_id``, ``nuc_label`` (nucleus of the field ``position``), ``phase`` (inter / pro / prometa / meta)
  and the authors' spot ``QC`` (1 = passed); coordinates in the field of view;
* ``looptrace_RPE1_denaturing_nondenaturing_FISH_comparison.csv.gz`` (*Nat. Commun.* 2025): RPE-1 traced with the
  non-denaturing (``RPE1``) and the denaturing (``RPE1_HF``) protocol, six regions; ``trace_id``, ``nuc_id``,
  ``nuc_total_int`` (DAPI, G1 / G2);
* ``looptrace_RPE1_HKWT_dRAD21_dCTCF_dWAPL_experimental_data_combined.csv.gz`` (*Nat. Commun.* 2025): RPE-1, HeLa
  Kyoto WT and HeLa with RAD21, CTCF or WAPL depleted, ten regions; coordinates in each trace's crop, and **no
  trace column** although the README names one: the leading row index runs in blocks of one row per frame of
  the library, in a fixed frame order — each block is one trace (blocks dropped by the authors' trace filter
  leave gaps in the index).

``g_pos`` is the centre of the library's spot (the mean probe position, rounded to 1 kb in the *Cell* table).  A
locus is a window of the library's spot size centred on it, clipped halfway to its neighbours.
"""

from __future__ import annotations

import re
from pathlib import Path

import numpy as np
import pandas as pd

#: the spot sizes (bp) of the libraries (Beckwith et al. 2025, Methods of both papers; IRF1, which neither
#: describes, at the 10-kb tiling of its spots)
SPOT_SIZE = {
    "Chr2_1MB": 12_000, "Chr5_1MB": 12_000, "Chr14_1MB": 12_000,
    "Chr2_12Mb": 30_000, "Chr14_11Mb": 30_000, "Chr18_13Mb": 30_000,
    "Chr2_full": 100_000, "Chr14_full": 30_000,
    "HIST1": 10_000, "MEOX1": 10_000, "WAPL": 10_000, "YARS2": 10_000, "IRF1": 10_000, "lncRNA": 4_000,
    "Chr2-A": 8_000, "Chr4-B": 8_000, "HoxA": 8_000, "SHH": 8_000,
}
_FIT = ("A", "BG", "sigma_z", "sigma_xy")


def _kind(columns) -> str:
    if "phase" in columns and "QC" in columns:
        return "mitosis"
    if "region_name" in columns:
        return "looptrace" if "trace_id" in columns else "looptrace_blocks"
    raise ValueError(f"not a LoopTrace table (Beckwith et al. 2025): columns {list(columns)}")


def _windows(g_pos: np.ndarray, size: int) -> tuple:
    """Start / end of each spot centre in ``g_pos`` (sorted, unique): ``size`` wide, clipped halfway to the
    neighbours."""
    lo, hi = g_pos - size / 2, g_pos + size / 2
    mid = (g_pos[1:] + g_pos[:-1]) / 2
    lo[1:] = np.maximum(lo[1:], mid)
    hi[:-1] = np.minimum(hi[:-1], mid)
    start = np.round(lo).astype(np.int64)
    return start, np.maximum(np.round(hi).astype(np.int64), start + 1)


def _block_traces(raw: pd.DataFrame) -> np.ndarray:
    """Trace of each row of the table without a trace column: blocks of consecutive row indices, one row per
    frame of the library in a fixed order."""
    trace = np.empty(len(raw), dtype=object)
    r = raw.sort_values("row", kind="stable")              # index labels = positions in raw (a RangeIndex)
    for key, g in r.groupby(["cell_type", "exp", "region_name"], sort=False):
        nf = g["frame_name"].nunique()
        idx, pos, frame = g["row"].to_numpy(), g["position"].to_numpy(), g["frame_name"].to_numpy()
        cut = np.flatnonzero((np.diff(idx) != 1) | (pos[1:] != pos[:-1])) + 1
        k, first = 0, None
        for a, b in zip(np.r_[0, cut], np.r_[cut, len(g)]):
            blocks = frame[a:b].reshape(-1, nf) if (b - a) % nf == 0 else None
            if first is None and blocks is not None:
                first = blocks[0]
            if blocks is None or not (blocks == first).all():
                raise ValueError(f"rows {idx[a]}..{idx[b - 1]} of {key} are not whole traces of {nf} frames")
            n = (b - a) // nf
            labels = [f"{key[0]}.{key[1]}.{key[2]}.{k + i}" for i in range(n)]
            trace[g.index[a:b]] = np.repeat(labels, nf)
            k += n
    return trace


def read_looptrace(path, *, spot_size: dict | None = None):
    """Read a LoopTrace table of Beckwith et al. 2025 into a ``ChromData`` of traces.

    Parameters
    ----------
    path : path or file object
        One of the three tables (``.csv`` / ``.csv.gz``); the table is recognised by its columns.
    spot_size : dict, optional
        Spot size (bp) of each library, default :data:`SPOT_SIZE`.

    Returns
    -------
    ChromData
        One spot per fitted locus (rows without a genomic position — the region-detection frame — are left out),
        coordinates in nm; bins = windows of the library's spot size centred on ``g_pos`` (clipped halfway to the
        neighbours), ``bins['region']`` the library.  The fit (``A``, ``BG``, ``sigma_xy``, ``sigma_z``) is in
        ``spot_tracks``; ``g_pos``, the frame and the field ``position`` are spot columns.  Mitotic table: the
        authors' ``QC`` is the spot column ``qc_pass``, ``coords`` hold the spots that passed it (NaN otherwise) and
        ``layers['fit']`` every fit; cells = nuclei (``<exp>/<position>/<nuc_label>``) with ``cell_type`` and
        ``phase``.  Comparison table: cells = nuclei with ``nuc_total_int``.  Combined table: traces numbered per
        (cell type, experiment, region) from the row blocks, no cells (coordinates in each trace's crop).
        ``traces`` hold ``region``, ``chrom``, ``cell_type``, ``exp``, ``position`` (and ``cell_id`` / ``phase``).
    """
    from chromdata import ChromData

    sizes = {**SPOT_SIZE, **(spot_size or {})}
    raw = pd.read_csv(path, float_precision="round_trip")      # the values as written
    raw = raw.rename(columns={raw.columns[0]: "row"}) if str(raw.columns[0]).startswith("Unnamed") else raw
    kind = _kind(raw.columns)
    lib_col = "region" if kind == "mitosis" else "region_name"
    if kind == "looptrace_blocks":
        raw["trace_id"] = _block_traces(raw)
    n_rows = len(raw)
    raw = raw[raw["g_pos"].notna()].reset_index(drop=True)

    lib = raw[lib_col].astype(str)
    if "chr" in raw.columns:
        chrom = raw["chr"].astype(str)
    else:
        chrom = "chr" + lib.str.extract(r"^Chr(\w+?)_", expand=False)
    missing = sorted(set(lib) - set(sizes))
    if missing:
        raise ValueError(f"no spot size for libraries {missing}: pass spot_size=")

    # loci: per library, the spot centres -> windows
    g = raw["g_pos"].to_numpy(dtype=np.float64)
    bins, bin_of = [], np.empty(len(raw), dtype=np.int64)
    for name in sorted(set(lib), key=lambda s: (chrom[lib == s].iloc[0], g[(lib == s).to_numpy()].min())):
        rows = (lib == name).to_numpy()
        centres, inv = np.unique(g[rows], return_inverse=True)
        start, end = _windows(centres, sizes[name])
        bin_of[rows] = sum(len(b) for b in bins) + inv
        bins.append(pd.DataFrame({"chrom": chrom[rows].iloc[0], "start": start, "end": end, "region": name,
                                  "g_pos": centres, "resolution": sizes[name]}))
    bins = pd.concat(bins, ignore_index=True)

    if kind == "mitosis":
        trace = "t" + raw["trace_id"].astype(np.int64).astype(str)
        cell = raw["exp"].astype(str) + "/" + raw["position"].astype(str).str.replace(".zarr", "", regex=False) + \
            "/" + raw["nuc_label"].astype(np.int64).astype(str)
    elif kind == "looptrace":
        trace = "t" + raw["trace_id"].astype(np.int64).astype(str)
        cell = raw["exp"].astype(str) + "/" + raw["nuc_id"].astype(str).str.replace(".zarr", "", regex=False)
    else:
        trace, cell = raw["trace_id"].astype(str), None

    spots = pd.DataFrame({"bin_id": bin_of, "trace_id": trace.to_numpy()})
    if cell is not None:
        spots["cell_id"] = cell.to_numpy()
    spots["g_pos"] = g
    spots["position"] = raw["position"].astype(str).str.replace(".zarr", "", regex=False).to_numpy()
    for c in ("frame", "frame_name", "ref_frame", "ref_ch", "trace_ch", "pos_index"):
        if c in raw.columns:
            spots[c] = raw[c].to_numpy()
    xyz = raw[["x", "y", "z"]].to_numpy(dtype=np.float64)
    layers = None
    if kind == "mitosis":
        qc = raw["QC"].to_numpy() == 1
        spots["qc_pass"] = qc
        layers = {"fit": xyz.copy()}
        xyz[~qc] = np.nan
    tracks = pd.DataFrame({c: raw[c].to_numpy(dtype=np.float64) for c in _FIT if c in raw.columns})

    meta = pd.DataFrame({"trace_id": trace.to_numpy(), "region": lib.to_numpy(), "chrom": chrom.to_numpy(),
                         "cell_type": raw["cell_type"].astype(str).to_numpy(), "exp": raw["exp"].astype(str).to_numpy(),
                         "position": spots["position"].to_numpy()})
    if cell is not None:
        meta["cell_id"] = cell.to_numpy()
    if kind == "mitosis":
        meta["phase"] = raw["phase"].astype(str).to_numpy()
    traces = meta.drop_duplicates("trace_id").set_index("trace_id")
    traces["n_spots"] = spots["trace_id"].value_counts().reindex(traces.index).to_numpy()
    if kind == "mitosis":
        traces["n_qc_pass"] = spots.groupby("trace_id")["qc_pass"].sum().reindex(traces.index).to_numpy()

    cells = None
    if cell is not None:
        cm = {"cell_id": cell.to_numpy(), "cell_type": meta["cell_type"].to_numpy(), "exp": meta["exp"].to_numpy(),
              "position": meta["position"].to_numpy()}
        if kind == "mitosis":
            cm["phase"] = meta["phase"].to_numpy()
        else:
            cm["nuc_total_int"] = raw["nuc_total_int"].to_numpy(dtype=np.float64)
        cells = pd.DataFrame(cm).drop_duplicates("cell_id").set_index("cell_id")
        cells["n_traces"] = traces.groupby("cell_id").size().reindex(cells.index).to_numpy()

    name = Path(getattr(path, "name", str(path))).name
    uns = {"xyz_unit": "nm", "genome_assembly": "hg38",
           "source": f"LoopTrace table {name} (Beckwith et al. 2025)",
           "looptrace": {"table": kind, "rows": int(n_rows), "rows_without_locus": int(n_rows - len(raw)),
                         "loci": "a window of the library's spot size centred on g_pos (the spot centre), clipped "
                                 "halfway to its neighbours",
                         "spot_size": {k: int(sizes[k]) for k in sorted(set(lib))}}}
    if kind == "mitosis":
        uns["looptrace"]["coords"] = "spots that passed the authors' QC; layers['fit'] holds every fit"
        uns["coord_frame"] = "field of view (nm)"
    elif kind == "looptrace_blocks":
        uns["looptrace"]["traces"] = ("numbered per (cell type, experiment, region) from blocks of consecutive row "
                                      "indices of the authors' table, one row per frame; no nuclei")
        uns["coord_frame"] = "each trace's crop (nm)"
    else:
        uns["coord_frame"] = "field of view (nm)"
    return ChromData(xyz, spots, bins=bins, cells=cells, traces=traces, spot_tracks=tracks, layers=layers, uns=uns)


__all__ = ["read_looptrace", "SPOT_SIZE"]
