"""
Shared densification helper for FISH coordinate imputation.

Real multiplexed-FISH / chromatin-tracing data represents a missing locus as an
ABSENT row, not a NaN row.  Every imputation method here needs the data on a
dense ``(haploid x locus-panel)`` grid first -- this mirrors SnapFISH-IMPUTE's
``fill_missing_by_nan`` preprocessing step.

``build_dense_grid`` returns a tidy long DataFrame with one row per
``(haploid, locus)``, sorted by ``(region, haploid, pos)``, with NaN coordinates
where a locus was not observed for that haploid.
"""

import numpy as np
import pandas as pd


def _haploid_key(spots):
    """Unique haploid id per (cell_id, trace_id), or trace_id alone."""
    if "cell_id" in spots.columns:
        return spots["cell_id"].astype(str) + "||" + spots["trace_id"].astype(str)
    return spots["trace_id"].astype(str)


def _normalize_ann(ann):
    """Accept an annotation DataFrame with chrom/region + start + end."""
    a = ann.copy()
    if "chrom" not in a.columns and "region" in a.columns:
        a = a.rename(columns={"region": "chrom"})
    missing = {"chrom", "start", "end"} - set(a.columns)
    if missing:
        raise ValueError(f"ann is missing required columns: {sorted(missing)}")
    return a[["chrom", "start", "end"]]


def build_dense_grid(cd, ann=None):
    """Densify a ChromData onto the per-chrom locus panel.

    Parameters
    ----------
    cd : ChromData
        Input data; missing loci may be absent rows and/or NaN-coord rows.
    ann : pd.DataFrame, optional
        Authoritative locus panel with columns (chrom|region, start, end).
        When given, loci absent from *every* haploid are still restored.
        When omitted, the panel is the union of observed loci per chrom.

    Returns
    -------
    grid : pd.DataFrame
        Columns: chrom, start, end, trace_id, [cell_id], haploid, region, pos,
        x, y, z.  One row per (haploid, locus), sorted by (region, haploid, pos).
        Coordinates are NaN where the locus was not observed for that haploid.
    panel : pd.DataFrame
        Columns: chrom, start, end, pos (1-based per chrom).
    has_cell : bool
        Whether the input carried a cell_id column.
    """
    spots = cd.spots
    has_cell = "cell_id" in spots.columns

    df = pd.DataFrame({
        "chrom": spots["chrom"].astype(str).values,
        "start": spots["start"].astype("int64").values,
        "end": spots["end"].astype("int64").values,
        "trace_id": spots["trace_id"].astype(str).values,
        "x": cd.coords[:, 0],
        "y": cd.coords[:, 1],
        "z": cd.coords[:, 2],
    })
    if has_cell:
        df["cell_id"] = spots["cell_id"].astype(str).values
    df["haploid"] = _haploid_key(spots).values

    # Build the locus panel (one shared panel per chrom).
    if ann is not None:
        panel = _normalize_ann(ann)
        panel = panel.astype({"start": "int64", "end": "int64"})
        panel["chrom"] = panel["chrom"].astype(str)
    else:
        panel = df[["chrom", "start", "end"]]
    panel = panel.drop_duplicates(["chrom", "start"]).sort_values(
        ["chrom", "start"]
    ).reset_index(drop=True)
    panel["pos"] = panel.groupby("chrom", sort=False).cumcount() + 1

    # One haploid lives in one region (chrom); keep its identity columns.
    hap_cols = ["haploid", "chrom", "trace_id"] + (["cell_id"] if has_cell else [])
    hap_tbl = df[hap_cols].drop_duplicates("haploid")

    # Full grid = per chrom, every haploid x every panel locus.
    full = hap_tbl.merge(panel, on="chrom", how="inner")

    # Bring in observed coordinates by (haploid, chrom, start).
    obs = df[["haploid", "chrom", "start", "x", "y", "z"]].drop_duplicates(
        ["haploid", "chrom", "start"]
    )
    grid = full.merge(obs, on=["haploid", "chrom", "start"], how="left")
    grid["region"] = grid["chrom"].astype(str)
    grid = grid.sort_values(["region", "haploid", "pos"]).reset_index(drop=True)

    return grid, panel, has_cell


def grid_to_chromdata(grid, has_cell, template_cd):
    """Build a ChromData from a densified grid.

    Per-spot containers (tracks, layers) are dropped because the row set
    changed; cell/trace-level metadata and uns are preserved.
    """
    from chromdata import ChromData

    cols = ["chrom", "start", "end", "trace_id"] + (["cell_id"] if has_cell else [])
    out_spots = grid[cols].reset_index(drop=True)
    out_coords = grid[["x", "y", "z"]].to_numpy(dtype=float)

    kwargs = dict(
        cells=getattr(template_cd, "cells", None),
        traces=getattr(template_cd, "traces", None),
        cellm=getattr(template_cd, "cellm", None),
        results=getattr(template_cd, "results", None),
        uns=getattr(template_cd, "uns", None),
    )
    # Keep the template's locus axis (and its bin-level tracks / binm /
    # intervals) when every grid locus is one of its bins; a panel with
    # new loci (``ann=``) gets fresh bins.
    bins = getattr(template_cd, "bins", None)
    if bins is not None:
        from chromdata.bins import map_loci_to_bins

        if not (map_loci_to_bins(out_spots, bins) < 0).any():
            out = ChromData(out_coords, out_spots, bins=bins, binm=template_cd.binm,
                            intervals=template_cd.intervals, **kwargs)
            if len(template_cd.bin_tracks.columns):
                out.bin_tracks = template_cd.bin_tracks
            return out
    return ChromData(coords=out_coords, spots=out_spots, **kwargs)
