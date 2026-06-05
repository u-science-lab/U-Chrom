"""Loader for Takei 2025 cerebellum DNA seqFISH+ multi-omics.

Takei et al. 2025 *Nature* "Spatial multi-omics reveals cell-type-specific
nuclear compartments" (doi:10.1038/s41586-025-08838-x; data on Zenodo
record 7693825) profiles the adult mouse cerebellum with two-layer DNA
seqFISH+ at ~100k loci × 25 kb resolution, jointly with 59 spot-level
z-scores (IF + DNA-FISH repeat probes + RNA-FISH probes), per-cell
clustering, UMAP, and centroid metadata.

The spot CSVs are too custom for :meth:`ChromData.from_fofct` or
:meth:`ChromData.from_dataframe` to ingest directly.  This module
provides :func:`read_seqfish_multiomics`, the dedicated loader.

Notes
-----
* The published spot CSVs name homologous-chromosome assignments in
  three columns: ``dbscan_allele``, ``dbscan_ldp_allele``, and
  ``dbscan_ldp_nbr_allele`` (DBSCAN → +LDP → +neighboring-spot recovery,
  in order of increasing recall).  The Zenodo readme mentions
  ``*_sorted`` variants, but those columns are NOT present in the
  released cerebellum CSVs; the published analysis notebooks treat the
  unsorted ``dbscan_ldp_nbr_allele`` as canonical.  Allele numbering is
  per-(cell, chrom) with no global ordering.
* The 25-kb locus annotation
  (``LC1-100k-09022022-mm10-25kb-meta.csv``) and the per-cell clustering
  CSV come from the CaiGroup/dna-seqfish-plus-multi-omics GitHub repo.
* One source column — ``KAT3B/p300`` — contains a forward slash, which
  HDF5 interprets as a path separator.  To preserve a clean ``.h5cd``
  round-trip, the loader renames it to ``KAT3B_p300``.
"""

from __future__ import annotations

import gc
import glob as _glob
import warnings
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple, Union

import numpy as np
import pandas as pd


PathLike = Union[str, Path]


DEFAULT_CEREBELLUM_LEIDEN_MAP: Dict[int, str] = {
    0: "Granule",
    1: "Granule",
    2: "Bergmann",
    4: "MLI1",
    6: "Purkinje",
    11: "Purkinje",
    7: "MLI2+PLI",
}


# 59 z-score columns from the cerebellum DNA spot CSV — IF + DNA-FISH
# repeats + RNA-FISH probes — order verbatim from the source file
# (cerebellum_rep1/cerebellum_rep1_pos0.csv columns 10-68).  The
# ``KAT3B/p300`` source name contains a forward slash; we keep the
# original name in this constant for clarity but apply
# ``_SLASH_RENAME`` before exposing it as a ``tracks`` column.
Z_SCORE_COLUMNS: Tuple[str, ...] = (
    "CPSF6", "ATRX", "H4K8ac", "HDAC2", "H3K9ac", "H3K9me3", "H3K9me2",
    "RNAPIISer2-P", "H3", "H3K36me2", "UBTF", "LaminB1", "RNAPIISer5-P",
    "RYBP", "HP1beta", "RING1B", "H2A.X", "H3K4me1", "H4K20me2",
    "H3K27me2", "JARID2", "SF3A66", "CBP", "H2AK119u1", "EZH2",
    "H3K4me2", "BRG1", "HP1alpha", "Fibrillarin", "KAP1", "H3K27ac",
    "H3K4me3", "H3K36ac", "H3K14ac", "H4K20me1", "HP1gamma", "H4K20me3",
    "H3K27me3", "mH2A1", "CHD4", "KAT3B/p300", "H3K56ac", "H3K36me3",
    "HDAC1", "SUZ12", "H4K16ac", "BRD4", "SOX2", "rDNA", "MajSat",
    "LINE1", "SINEB1", "Telomere", "MinSat", "Xist_RNA", "ITS1_RNA",
    "Rnu2_RNA", "polyA_RNA", "Malat1_RNA",
)


_EXTRA_TRACK_COLUMNS: Tuple[str, ...] = (
    "dot_int", "n_rad_score", "n_per_dist(um)",
)


# Source-to-internal column rename for names HDF5 cannot store directly.
_SLASH_RENAME: Dict[str, str] = {"KAT3B/p300": "KAT3B_p300"}


_ALLELE_COLUMNS = ("dbscan_allele", "dbscan_ldp_allele", "dbscan_ldp_nbr_allele")
_COORD_COLUMNS = ("x_um", "y_um", "z_um")
_REQUIRED_SPOT_INPUT_COLUMNS = (
    "rep", "fov", "cellID", "name", "chrom", *_ALLELE_COLUMNS, *_COORD_COLUMNS,
)
_REQUIRED_CLUSTER_COLUMNS = (
    "rep", "fov", "cellID", "leiden", "umap_1", "umap_2",
    "x", "y", "z", "nuc_volume(um3)", "doublet", "batch",
)


# ----------------------------------------------------------------------
# Public API
# ----------------------------------------------------------------------


def read_seqfish_multiomics(
    spot_glob: Union[str, Iterable[PathLike]],
    *,
    locus_annotation: PathLike,
    cell_clustering: Optional[PathLike] = None,
    leiden_to_cell_type: Optional[Dict[int, str]] = None,
    allele_col: str = "dbscan_ldp_nbr_allele",
    keep_unclustered: bool = False,
) -> "ChromData":
    """Load Takei 2025 DNA seqFISH+ cerebellum data into a ChromData.

    Parameters
    ----------
    spot_glob
        Either a single CSV path, a glob string (e.g.
        ``'cerebellum_rep*/cerebellum_rep*_pos*.csv'``), or an iterable
        of paths.  Each file is the per-FOV DNA seqFISH+ spot table
        with 76 columns documented in the Zenodo 7693825 readme.
    locus_annotation
        Path to the 25-kb locus map CSV from the
        CaiGroup/dna-seqfish-plus-multi-omics GitHub repo
        (``data/annotation/LC1-100k-09022022-mm10-25kb-meta.csv``).
        Used to resolve the ``name`` column (e.g. ``chr7-1628``) to
        ``chrom/start/end``.
    cell_clustering
        Optional path to the per-cell clustering CSV
        (``data/cerebellum/clustering/100k-002-001-cerebellum_mRNA_cluster_nuc_vol_filtered.csv``).
        If given, the loader populates ``cells`` (with ``leiden``,
        ``cell_type``, centroid, nuclear volume, doublet, batch) and
        ``cellm['umap']``.
    leiden_to_cell_type
        Mapping from leiden cluster id (int) to cell-type string.  Used
        to derive ``cells.cell_type``.  If ``None``, the published
        cerebellum mapping is used (Granule/Bergmann/MLI1/Purkinje/MLI2+PLI),
        with all uncovered clusters labelled ``'Other'``.
    allele_col
        Which homologous-chromosome assignment to use for ``trace_id``.
        One of ``'dbscan_allele'``, ``'dbscan_ldp_allele'``,
        ``'dbscan_ldp_nbr_allele'``.  Defaults to the highest-recall
        ``dbscan_ldp_nbr_allele`` (the column referenced as canonical in
        the published analysis notebooks).
    keep_unclustered
        DBSCAN noise spots have ``allele == -1``.  When ``False``
        (default) these are dropped before constructing the
        ``ChromData``.  Set ``True`` to keep them as their own
        ``allele=-1`` traces (useful for QC).

    Returns
    -------
    ChromData
        - ``coords``: (n_spots, 3) μm
        - ``spots``: chrom / start / end / trace_id / cell_id (composite
          ``f"{rep}_{fov}_{cellID}"`` and
          ``f"{rep}_{fov}_{cellID}_{chrom}_a{allele}"``)
        - ``tracks``: 62 columns = 59 z-scores +
          ``dot_int, n_rad_score, n_per_dist(um)``
        - ``traces``: diagnostic ``dbscan_allele`` / ``dbscan_ldp_allele``
          per trace
        - ``cells`` and ``cellm['umap']`` if ``cell_clustering`` is given
        - ``uns``: genome_assembly='mm10', xyz_unit='um', voxel sizes,
          Zenodo record id, the leiden map actually used, and the
          allele-column choice
    """
    if allele_col not in _ALLELE_COLUMNS:
        raise ValueError(
            f"allele_col must be one of {_ALLELE_COLUMNS!r}, got {allele_col!r}"
        )

    leiden_map = (
        dict(DEFAULT_CEREBELLUM_LEIDEN_MAP)
        if leiden_to_cell_type is None
        else dict(leiden_to_cell_type)
    )

    locus_df = _load_locus_annotation(Path(locus_annotation))
    paths = _resolve_spot_paths(spot_glob)
    if not paths:
        raise ValueError(f"spot_glob matched no files: {spot_glob!r}")

    # Stream per-CSV: process and immediately filter each file so the
    # heavy raw frames (~12 GB / FOV) do not all live in memory at once.
    coords_chunks: List[np.ndarray] = []
    spots_chunks: List[pd.DataFrame] = []
    tracks_chunks: List[pd.DataFrame] = []
    traces_chunks: List[pd.DataFrame] = []
    for p in paths:
        if not p.exists():
            raise FileNotFoundError(p)
        chunk = _process_one_csv(
            p, locus_df,
            allele_col=allele_col, keep_unclustered=keep_unclustered,
        )
        coords_chunks.append(chunk["coords"])
        spots_chunks.append(chunk["spots"])
        tracks_chunks.append(chunk["tracks"])
        traces_chunks.append(chunk["traces"])

    coords = (np.concatenate(coords_chunks, axis=0)
              if len(coords_chunks) > 1 else coords_chunks[0])
    spots = (pd.concat(spots_chunks, ignore_index=True)
             if len(spots_chunks) > 1 else spots_chunks[0])
    tracks = (pd.concat(tracks_chunks, ignore_index=True)
              if len(tracks_chunks) > 1 else tracks_chunks[0])
    # ``traces`` keeps trace_id as the index; per-CSV trace_id sets are
    # disjoint because the prefix encodes (rep, fov), so a straight concat
    # is equivalent to a global groupby-first.
    traces = (pd.concat(traces_chunks)
              if len(traces_chunks) > 1 else traces_chunks[0])
    del coords_chunks, spots_chunks, tracks_chunks, traces_chunks
    gc.collect()

    cells_kept, cellm = _build_cells_and_umap(
        cell_clustering, leiden_map, spots,
    )
    uns = _build_uns(leiden_map, allele_col, keep_unclustered)

    from uchrom.core import ChromData
    return ChromData(
        coords=coords,
        spots=spots,
        cells=cells_kept,
        cellm=cellm if cellm else None,
        tracks=tracks,
        traces=traces,
        uns=uns,
    )


# ----------------------------------------------------------------------
# Internal helpers
# ----------------------------------------------------------------------


def _resolve_spot_paths(spot_glob: Union[str, Iterable[PathLike]]) -> List[Path]:
    if isinstance(spot_glob, (str, Path)):
        s = str(spot_glob)
        matches = sorted(_glob.glob(s))
        if matches:
            return [Path(m) for m in matches]
        # No glob match — fall through and treat as a literal path so the
        # error below is informative.
        return [Path(s)]
    return [Path(p) for p in spot_glob]


def _load_locus_annotation(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    missing = {"name", "chrom", "start", "end"} - set(df.columns)
    if missing:
        raise ValueError(
            f"locus annotation {path} missing columns: {missing}"
        )
    return df[["name", "chrom", "start", "end"]].copy()


def _process_one_csv(
    path: Path, locus_df: pd.DataFrame, *,
    allele_col: str, keep_unclustered: bool,
) -> Dict[str, "Union[np.ndarray, pd.DataFrame]"]:
    """Read one DNA spot CSV → filtered coords/spots/tracks/traces chunk.

    The heavy original frame is dropped before returning, so the caller
    accumulates only the post-filter sub-frames.  Memory profile: peak
    ~1× the source CSV in pandas (≈ 6× the on-disk size for the
    cerebellum DNA seqFISH+ data), released by the time this function
    returns.
    """
    raw = pd.read_csv(path, low_memory=False)
    missing = set(_REQUIRED_SPOT_INPUT_COLUMNS) - set(raw.columns)
    if missing:
        raise ValueError(
            f"spot CSV {path} missing required columns: {sorted(missing)}"
        )
    df = _assign_trace_id(raw, allele_col=allele_col,
                          keep_unclustered=keep_unclustered)
    del raw

    merged = df.merge(
        locus_df.rename(columns={"chrom": "_locus_chrom"}),
        on="name", how="left",
    )
    miss = merged["start"].isna()
    if miss.any():
        n_missing = int(miss.sum())
        warnings.warn(
            f"{n_missing} spot(s) in {path.name} had no matching locus in "
            f"the 25-kb annotation and were dropped.  Examples: "
            f"{merged.loc[miss, 'name'].unique()[:5].tolist()}",
            stacklevel=4,
        )
        merged = merged.loc[~miss].reset_index(drop=True)
    mismatched = merged["chrom"].astype(str) != merged["_locus_chrom"].astype(str)
    if mismatched.any():
        warnings.warn(
            f"{int(mismatched.sum())} spot(s) in {path.name} had a 'chrom' "
            f"value disagreeing with the 25-kb annotation; trusting the "
            f"source 'chrom'.",
            stacklevel=4,
        )
    merged = merged.drop(columns=["_locus_chrom"])

    coords = merged[list(_COORD_COLUMNS)].to_numpy(dtype=np.float64)

    spots = pd.DataFrame({
        "chrom": merged["chrom"].astype(str).values,
        "start": merged["start"].astype(np.int64).values,
        "end": merged["end"].astype(np.int64).values,
        "trace_id": merged["trace_id"].values,
        "cell_id": merged["cell_id"].values,
        "name": merged["name"].astype(str).values,
    })

    tracks_cols = list(Z_SCORE_COLUMNS) + list(_EXTRA_TRACK_COLUMNS)
    # Real data varies in which marker columns are present (rep2 of the
    # cerebellum release, for example, drops LINE1 and SINEB1).  Fill the
    # missing tracks with NaN so the output schema is stable across FOVs
    # and reps, and warn so users can filter / impute them downstream.
    absent = [c for c in tracks_cols if c not in merged.columns]
    if absent:
        warnings.warn(
            f"{path.name}: {len(absent)} track column(s) missing from this "
            f"FOV; filling with NaN: {absent}",
            stacklevel=4,
        )
        for c in absent:
            merged[c] = np.nan
    tracks = merged[tracks_cols].copy()
    tracks = tracks.rename(columns=_SLASH_RENAME)
    for col in tracks.columns:
        tracks[col] = pd.to_numeric(tracks[col], errors="coerce")
    tracks = tracks.reset_index(drop=True)

    traces = (
        merged.groupby("trace_id", sort=False)
        .agg({"dbscan_allele": "first", "dbscan_ldp_allele": "first"})
    )
    traces.index.name = "trace_id"

    del merged, df
    gc.collect()

    return {
        "coords": coords,
        "spots": spots,
        "tracks": tracks,
        "traces": traces,
    }


def _assign_trace_id(
    df: pd.DataFrame, *, allele_col: str, keep_unclustered: bool,
) -> pd.DataFrame:
    """Add composite ``cell_id`` and ``trace_id`` columns to ``df``."""
    df = df.copy()
    rep = df["rep"].astype(int).astype(str)
    fov = df["fov"].astype(int).astype(str)
    cell = df["cellID"].astype(int).astype(str)
    df["cell_id"] = rep + "_" + fov + "_" + cell
    allele = df[allele_col].astype(int)
    if not keep_unclustered:
        mask = allele != -1
        df = df.loc[mask].copy()
        allele = allele.loc[mask]
    df["trace_id"] = (
        df["cell_id"].astype(str) + "_" + df["chrom"].astype(str) + "_a"
        + allele.astype(str)
    )
    return df


def _load_cells(
    cluster_csv: Path, leiden_map: Dict[int, str],
) -> Tuple[pd.DataFrame, np.ndarray]:
    df = pd.read_csv(cluster_csv)
    missing = set(_REQUIRED_CLUSTER_COLUMNS) - set(df.columns)
    if missing:
        raise ValueError(
            f"clustering CSV {cluster_csv} missing columns: {sorted(missing)}"
        )
    df = df.copy()
    df["cell_id"] = (
        df["rep"].astype(int).astype(str) + "_"
        + df["fov"].astype(int).astype(str) + "_"
        + df["cellID"].astype(int).astype(str)
    )
    df["leiden"] = df["leiden"].astype(int)
    df["cell_type"] = df["leiden"].map(leiden_map).fillna("Other")
    cells = pd.DataFrame({
        "leiden": df["leiden"].values,
        "cell_type": df["cell_type"].values,
        "x_centroid": df["x"].values,
        "y_centroid": df["y"].values,
        "z_centroid": df["z"].values,
        "nuc_volume_um3": df["nuc_volume(um3)"].values,
        "doublet": df["doublet"].astype(int).values,
        "batch": df["batch"].astype(int).values,
    }, index=pd.Index(df["cell_id"].values, name="cell_id"))
    umap = df[["umap_1", "umap_2"]].to_numpy(dtype=np.float64)
    return cells, umap


def _build_cells_and_umap(
    cell_clustering: Optional[PathLike],
    leiden_map: Dict[int, str],
    spots: pd.DataFrame,
) -> Tuple[Optional[pd.DataFrame], Dict[str, np.ndarray]]:
    """Load + filter the clustering CSV against observed spot cell_ids."""
    if cell_clustering is None:
        return None, {}
    cells_df, umap_arr = _load_cells(Path(cell_clustering), leiden_map)
    observed = pd.Index(spots["cell_id"].unique())
    keep_mask = cells_df.index.isin(observed)
    if not keep_mask.any():
        warnings.warn(
            "cell_clustering had no overlap with the spot table; "
            "cells / cellm['umap'] will be empty.",
            stacklevel=3,
        )
        return pd.DataFrame(), {}
    cells_kept = cells_df.loc[keep_mask].copy()
    cellm: Dict[str, np.ndarray] = {}
    keep_mask_arr = np.asarray(keep_mask)
    if umap_arr is not None:
        cellm["umap"] = np.asarray(umap_arr)[keep_mask_arr]
    n_missing = int((~observed.isin(cells_df.index)).sum())
    if n_missing:
        warnings.warn(
            f"{n_missing} cell_id value(s) in spots had no clustering "
            f"row; their cells/cellm entries are absent.",
            stacklevel=3,
        )
    return cells_kept, cellm


def _build_uns(
    leiden_map: Dict[int, str], allele_col: str, keep_unclustered: bool,
) -> dict:
    # HDF5 attribute keys must be strings; stringify the leiden->cell_type
    # dict for storage.  Callers can recover int keys via
    # ``{int(k): v for k, v in cd.uns['leiden_to_cell_type'].items()}``.
    return {
        "genome_assembly": "mm10",
        "xyz_unit": "um",
        "voxel_xy_nm": 103,
        "voxel_z_nm": 250,
        "source": "Takei2025_cerebellum",
        "zenodo_record": "7693825",
        "leiden_to_cell_type": {str(k): v for k, v in leiden_map.items()},
        "allele_col": allele_col,
        "keep_unclustered": keep_unclustered,
    }
