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
  storage layers treat as a path separator.  To keep a clean store
  round trip, the loader renames it to ``KAT3B_p300``.
"""

from __future__ import annotations

import gc
import glob as _glob
import re
import shutil
import tarfile
import urllib.request
import warnings
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Dict, Iterable, List, Optional, Tuple, Union

if TYPE_CHECKING:
    from chromdata import ChromData

import numpy as np
import pandas as pd


PathLike = Union[str, Path]


ZENODO_RECORD = "7693825"
ZENODO_BASE_URL = f"https://zenodo.org/api/records/{ZENODO_RECORD}/files"
TRANSCRIPTOMIC_ZIP_NAME = "transcriptomic-data.zip"
TRANSCRIPTOMIC_ZIP_URL = f"{ZENODO_BASE_URL}/{TRANSCRIPTOMIC_ZIP_NAME}/content"
GITHUB_MEDIA_BASE_URL = (
    "https://media.githubusercontent.com/media/"
    "CaiGroup/dna-seqfish-plus-multi-omics/main"
)
CEREBELLUM_LOCUS_25KB_PATH = (
    "data/annotation/LC1-100k-09022022-mm10-25kb-meta.csv"
)
CEREBELLUM_CLUSTERING_PATH = (
    "data/cerebellum/clustering/"
    "100k-002-001-cerebellum_mRNA_cluster_nuc_vol_filtered.csv"
)


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

#: the 48 immunofluorescence (antibody) channels among the z-score tracks,
#: as ``tracks`` column names (CPSF6 … SOX2); the rest are DNA-FISH repeat
#: probes (rDNA … MinSat) and RNA-FISH probes (… _RNA)
IF_COLUMNS: Tuple[str, ...] = tuple(_SLASH_RENAME.get(c, c) for c in Z_SCORE_COLUMNS[:48])


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
    out: Optional[PathLike] = None,
    memory_budget=None,
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
        ``cell_type``, the cell position ``centroid_x/y/z`` — voxel
        coordinates in the FOV, recorded in ``uns['cell_spatial']`` with the
        voxel size, so ``cd.cell_positions(physical=True)`` is in µm in the
        frame of ``coords`` — ``fov`` (``"{rep}_{fov}"``), nuclear volume,
        doublet, batch) and ``cellm['umap']``.  (Before format 2.3 the
        centroid columns were ``x_centroid`` …; ``cell_positions()`` still
        reads them.)
    leiden_to_cell_type
        Mapping from leiden cluster id (int) to cell-type string.  Used
        to derive ``cells.cell_type``.  If ``None``, the published
        cerebellum mapping is used (Granule/Bergmann/MLI1/Purkinje/MLI2+PLI),
        with all uncovered clusters labelled ``'Other'``.
    allele_col
        Which homologous-chromosome assignment defines ``trace_id``.
        One of ``'dbscan_allele'``, ``'dbscan_ldp_allele'``,
        ``'dbscan_ldp_nbr_allele'``.  Defaults to the highest-recall
        ``dbscan_ldp_nbr_allele`` (the column referenced as canonical in
        the published analysis notebooks).

        .. warning::
           ``dbscan_ldp_nbr_allele`` often merges the two homologs of a
           chromosome into one trace.  On the Takei 2025 cerebellum data
           (1e7 spots) 75.6 % of its traces observe some locus twice and
           the median genomic–spatial Spearman ρ per trace is 0.19;
           ``dbscan_ldp_allele`` gives 0 % such traces and ρ = 0.41 but
           keeps only 54 % of the spots.  For analyses that need one
           fibre per trace (distance maps, TAD / loop calling, tracing
           statistics) prefer ``allele_col="dbscan_ldp_allele"``; check
           ``traces["n_duplicate_loci"]`` whichever column you use.
    keep_unclustered
        DBSCAN noise spots have ``allele == -1``.  When ``False``
        (default) these are dropped before constructing the
        ``ChromData``.  Set ``True`` to keep them as their own
        ``allele=-1`` traces (useful for QC).
    out
        **Streaming import**: write the result to this ``.chromdata.zarr``
        store, one CSV (FOV) at a time, with
        :class:`~chromdata.stream.ChromDataWriter`, and return it opened
        backed.  Peak memory is one FOV's parse (the raw CSV frame) — not
        the sum of the FOVs — plus the writer's merge pieces (bounded by
        ``memory_budget``).  The store equals
        ``read_seqfish_multiomics(...).write(out)``.
    memory_budget
        Working-memory budget of the streaming writer (default
        :data:`uchrom.settings.memory_budget`).

    Returns
    -------
    ChromData
        - ``coords``: (n_spots, 3) μm
        - ``spots``: chrom / start / end / trace_id / cell_id (composite
          ``f"{rep}_{fov}_{cellID}"`` and
          ``f"{rep}_{fov}_{cellID}_{chrom}_a{allele}"``)
        - ``tracks``: 62 columns = 59 z-scores +
          ``dot_int, n_rad_score, n_per_dist(um)``
        - ``traces`` (index ``trace_id``): ``allele`` (the ``allele_col``
          value that defines the trace), ``n_spots``, ``n_loci``,
          ``n_duplicate_loci`` (spots whose locus already occurs in the
          trace — > 0 means homologs were merged), and for each other
          allele column ``<col>_majority`` / ``<col>_agreement`` (its most
          common value in the trace and the fraction of spots with it)
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

    if out is not None:
        return _read_seqfish_streaming(
            paths, locus_df, out=Path(out), cell_clustering=cell_clustering, leiden_map=leiden_map,
            allele_col=allele_col, keep_unclustered=keep_unclustered, memory_budget=memory_budget)

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
    uns = _build_uns(leiden_map, allele_col, keep_unclustered, cells=cells_kept)

    from chromdata import ChromData
    return ChromData(
        coords=coords,
        spots=spots,
        bins=_panel_bins(locus_df, spots),
        cells=cells_kept,
        cellm=cellm if cellm else None,
        spot_tracks=tracks,          # per-spot z-scores (not per-locus)
        traces=traces,
        uns=uns,
    )


def _read_seqfish_streaming(paths, locus_df, *, out: Path, cell_clustering, leiden_map,
                            allele_col, keep_unclustered, memory_budget):
    """:func:`read_seqfish_multiomics` with ``out=``: FOV by FOV into a
    :class:`~chromdata.stream.ChromDataWriter`."""
    from chromdata import ChromData
    from chromdata.stream import ChromDataWriter

    w = ChromDataWriter(out, memory_budget=memory_budget)
    try:
        traces_chunks: List[pd.DataFrame] = []
        for p in paths:
            if not p.exists():
                raise FileNotFoundError(p)
            chunk = _process_one_csv(p, locus_df, allele_col=allele_col,
                                     keep_unclustered=keep_unclustered)
            w.append(coords=chunk["coords"], spots=chunk["spots"], spot_tracks=chunk["tracks"])
            traces_chunks.append(chunk["traces"])
            del chunk
            gc.collect()
        traces = pd.concat(traces_chunks) if len(traces_chunks) > 1 else traces_chunks[0]
        # the loci / cell ids seen stand in for the spots (same result)
        loci = w.loci()
        cells_kept, cellm = _build_cells_and_umap(
            cell_clustering, leiden_map, pd.DataFrame({"cell_id": w.unique("cell_id")}))
        w.finish(bins=_panel_bins(locus_df, loci), cells=cells_kept, cellm=cellm or None,
                 traces=traces, uns=_build_uns(leiden_map, allele_col, keep_unclustered, cells=cells_kept))
    except BaseException:
        if not w._closed:
            w.abort()
        raise
    return ChromData.read(out, backed=True)


def _panel_bins(locus_df: pd.DataFrame, spots: pd.DataFrame) -> Optional[pd.DataFrame]:
    """The probe panel as ``bins`` (one row per annotated locus, with its
    ``name``), restricted to the chromosomes that have spots.  ``None`` —
    bins then come from the spot loci — if the panel has duplicate loci or
    misses a spot locus (e.g. a spot whose source chrom disagrees)."""
    from chromdata.bins import map_loci_to_bins, normalise_bins

    chroms = set(spots["chrom"].astype(str))
    panel = locus_df[locus_df["chrom"].astype(str).isin(chroms)]
    panel = panel.sort_values(["chrom", "start", "end"], kind="mergesort")
    panel = panel[["chrom", "start", "end", "name"]].reset_index(drop=True)
    try:
        bins = normalise_bins(panel)
    except (ValueError, TypeError):
        return None
    if (map_loci_to_bins(spots, bins) < 0).any():
        return None
    return bins


def read_seqfish_transcriptome(
    transcriptomic_data: PathLike | Iterable[PathLike] | None = None,
    *,
    dataset: str = "cerebellum",
    assay: str = "mrna",
    replicate: Optional[int] = None,
    observed_cell_ids: Optional[Iterable[str]] = None,
    download: bool = False,
    data_dir: Optional[PathLike] = None,
    chunksize: int = 500_000,
):
    """Read Takei 2025 RNA seqFISH spot CSVs into a cell × gene AnnData.

    The Zenodo transcriptomic archive stores super-resolved RNA spots,
    not a precomputed expression matrix.  This function aggregates those
    spots into a sparse count matrix with cell ids matching
    :func:`read_seqfish_multiomics`: ``rep_fov_cellID``.
    """
    try:
        import anndata as ad
        from scipy import sparse
    except ImportError as e:
        raise ImportError(
            "anndata and scipy are required to build the Takei 2025 h5ad. "
            "Install with `pip install anndata scipy`."
        ) from e

    sources = _resolve_transcriptome_sources(
        transcriptomic_data,
        dataset=dataset,
        assay=assay,
        replicate=replicate,
        download=download,
        data_dir=data_dir,
    )
    if not sources:
        raise ValueError(
            f"No transcriptomic CSVs found for dataset={dataset!r}, "
            f"assay={assay!r}, replicate={replicate!r}."
        )

    observed_order = None
    observed = None
    if observed_cell_ids is not None:
        observed_order = [str(x) for x in observed_cell_ids]
        observed = set(observed_order)

    counts: Optional[pd.Series] = None
    intensity: Optional[pd.Series] = None
    source_names: List[str] = []
    for source in sources:
        source_names.append(source.name)
        source_rep = _infer_replicate(source.name, default=replicate)
        for chunk in _iter_csv_chunks(source, chunksize=chunksize):
            expr = _normalise_transcriptome_chunk(chunk, replicate=source_rep)
            if observed is not None:
                expr = expr[expr["cell_id"].isin(observed)]
            if expr.empty:
                continue
            grp = expr.groupby(["cell_id", "geneID"], sort=False).size()
            counts = grp if counts is None else counts.add(grp, fill_value=0)
            if "intensity" in expr.columns:
                inten_grp = expr.groupby(["cell_id", "geneID"], sort=False)["intensity"].sum()
                intensity = inten_grp if intensity is None else intensity.add(inten_grp, fill_value=0)

    if counts is None or counts.empty:
        raise ValueError("No RNA spots remained after filtering; cannot build AnnData.")

    counts = counts.astype(np.int64)
    idx = counts.index
    if observed_order is None:
        cell_ids = list(pd.Index(idx.get_level_values("cell_id")).unique())
    else:
        cell_ids = observed_order
    genes = list(pd.Index(idx.get_level_values("geneID")).unique())

    cell_pos = {c: i for i, c in enumerate(cell_ids)}
    gene_pos = {g: i for i, g in enumerate(genes)}
    rows = np.array([cell_pos[c] for c in idx.get_level_values("cell_id")], dtype=np.int64)
    cols = np.array([gene_pos[g] for g in idx.get_level_values("geneID")], dtype=np.int64)
    x = sparse.csr_matrix(
        (counts.to_numpy(dtype=np.float64), (rows, cols)),
        shape=(len(cell_ids), len(genes)),
    )

    obs = pd.DataFrame(index=pd.Index(cell_ids, name="cell_id"))
    obs["n_transcripts"] = np.asarray(x.sum(axis=1)).ravel().astype(np.int64)
    obs["n_genes_by_counts"] = np.asarray((x > 0).sum(axis=1)).ravel().astype(np.int64)
    var = pd.DataFrame(index=pd.Index(genes, name="geneID"))
    var["n_cells_by_counts"] = np.asarray((x > 0).sum(axis=0)).ravel().astype(np.int64)

    adata = ad.AnnData(X=x, obs=obs, var=var)
    if intensity is not None and not intensity.empty:
        intensity = intensity.reindex(idx).fillna(0.0)
        adata.layers["intensity_sum"] = sparse.csr_matrix(
            (intensity.to_numpy(dtype=np.float64), (rows, cols)),
            shape=x.shape,
        )
    adata.uns["takei2025_transcriptome"] = {
        "dataset": dataset,
        "assay": assay,
        "replicate": replicate,
        "source_files": source_names,
        "zenodo_record": ZENODO_RECORD,
    }
    return adata


def load_seqfish_multiomics_linked(
    spot_glob: Union[str, Iterable[PathLike]],
    *,
    locus_annotation: PathLike,
    cell_clustering: Optional[PathLike] = None,
    transcriptomic_data: PathLike | Iterable[PathLike] | None = None,
    transcriptome_dataset: str = "cerebellum",
    transcriptome_assay: str = "mrna",
    transcriptome_replicate: Optional[int] = None,
    transcriptome_chunksize: int = 500_000,
    download_transcriptome: bool = False,
    data_dir: Optional[PathLike] = None,
    cd_path: Optional[PathLike] = None,
    h5ad_path: Optional[PathLike] = None,
    h5cd_path: Optional[PathLike] = None,
    **kwargs,
):
    """Build linked Takei 2025 ChromData and AnnData artifacts.

    Returns a ``ChromData`` that stores chromatin tracing geometry and
    spot-level tracks.  The aggregated RNA expression matrix is attached
    as ``cd.linked_adata``.  Both objects are ordered on the same cell
    ids, and the ChromData receives ``adata.obs``/``adata.obsm`` via
    :meth:`ChromData.link_anndata`.

    ``cd_path`` is where the ChromData is written (``.chromdata.zarr`` or
    ``.cdz``).  ``h5cd_path`` is its deprecated former name.
    """
    if h5cd_path is not None:
        warnings.warn("h5cd_path= is deprecated; use cd_path= (a .chromdata.zarr / .cdz path)",
                      DeprecationWarning, stacklevel=2)
        if cd_path is None:
            cd_path = h5cd_path
    cd = read_seqfish_multiomics(
        spot_glob,
        locus_annotation=locus_annotation,
        cell_clustering=cell_clustering,
        **kwargs,
    )
    observed_ids = [str(x) for x in cd.spots["cell_id"].unique()]
    adata = read_seqfish_transcriptome(
        transcriptomic_data,
        dataset=transcriptome_dataset,
        assay=transcriptome_assay,
        replicate=transcriptome_replicate,
        observed_cell_ids=observed_ids,
        download=download_transcriptome,
        data_dir=data_dir,
        chunksize=transcriptome_chunksize,
    )
    matched = cd.link_anndata(adata)
    if matched == 0:
        raise ValueError("RNA AnnData had no cell_id overlap with ChromData.")
    adata = _align_anndata_to_chromdata(adata, cd)
    cd.linked_adata = adata

    cd.uns["linked_anndata"] = {
        "n_obs": int(adata.n_obs),
        "n_vars": int(adata.n_vars),
        "cell_id_axis": "obs_names",
    }
    if h5ad_path is not None:
        h5ad_path = Path(h5ad_path)
        h5ad_path.parent.mkdir(parents=True, exist_ok=True)
        adata.write_h5ad(h5ad_path)
        cd.uns["linked_anndata"]["path"] = str(h5ad_path)
    if cd_path is not None:
        cd_path = Path(cd_path)
        cd_path.parent.mkdir(parents=True, exist_ok=True)
        cd.write(cd_path)
    return cd


def load_takei2025_cerebellum(
    *,
    replicate: int = 1,
    data_dir: Optional[PathLike] = None,
    download: bool = True,
    rebuild: bool = False,
    transcriptome_chunksize: int = 500_000,
    **kwargs,
):
    """Load linked Takei 2025 cerebellum ``ChromData`` + AnnData.

    This convenience loader returns a ``ChromData``.  The aggregated RNA
    expression matrix is available as ``cd.linked_adata``.  If paired
    ``.chromdata.zarr`` / ``.h5ad`` artifacts already exist under ``data_dir``, they are reused.  Otherwise, when ``download=True``, the required
    DNA seqFISH+ archive and transcriptome zip are downloaded from
    Zenodo record 7693825, annotation/clustering tables are downloaded
    from the CaiGroup GitHub repository, and linked artifacts are built.

    Parameters
    ----------
    replicate
        Cerebellum replicate to load.  Currently ``1`` or ``2``.
    data_dir
        Cache/build directory for downloaded raw files and linked
        artifacts (default: ``<uchrom.datasets.data_dir()>/takei2025_cerebellum``).
    download
        If False, missing raw/build artifacts raise ``FileNotFoundError``.
    rebuild
        If True, rebuild the paired artifacts even when they exist.
    transcriptome_chunksize
        Chunk size used while aggregating RNA spot CSVs into AnnData.
    **kwargs
        Forwarded to :func:`load_seqfish_multiomics_linked`.
    """
    if replicate not in (1, 2):
        raise ValueError("replicate must be 1 or 2 for the cerebellum dataset")

    from chromdata import ChromData

    if data_dir is None:
        from uchrom.datasets import data_dir as _root

        data_dir = _root() / "takei2025_cerebellum"
    data_dir = Path(data_dir)
    cd_path = data_dir / f"takei2025_cerebellum_rep{replicate}.chromdata.zarr"
    legacy = data_dir / f"takei2025_cerebellum_rep{replicate}.h5cd"
    h5ad_path = data_dir / f"takei2025_cerebellum_rep{replicate}.h5ad"
    if not cd_path.exists() and legacy.exists() and not rebuild:
        # an older build: convert it once to the current store
        from .upgrade import upgrade_h5cd

        upgrade_h5cd(legacy, cd_path)
    if cd_path.exists() and not rebuild:
        cd = ChromData.read(cd_path)
        if h5ad_path.exists():
            cd.uns.setdefault("linked_anndata", {})["path"] = str(h5ad_path)
        return cd

    if not download:
        raise FileNotFoundError(
            f"{cd_path} does not exist. Pass download=True to build it."
        )

    archive_name = f"cerebellum_rep{replicate}.tar.gz"
    archive = _download_file(
        f"{ZENODO_BASE_URL}/{archive_name}/content",
        data_dir / "downloads" / archive_name,
    )
    extract_dir = data_dir / f"cerebellum_rep{replicate}"
    _extract_tar_once(archive, extract_dir)

    locus = _download_file(
        f"{GITHUB_MEDIA_BASE_URL}/{CEREBELLUM_LOCUS_25KB_PATH}",
        data_dir / "annotation" / Path(CEREBELLUM_LOCUS_25KB_PATH).name,
    )
    clustering = _download_file(
        f"{GITHUB_MEDIA_BASE_URL}/{CEREBELLUM_CLUSTERING_PATH}",
        data_dir / "clustering" / Path(CEREBELLUM_CLUSTERING_PATH).name,
    )
    transcriptome_zip = _download_file(
        TRANSCRIPTOMIC_ZIP_URL,
        data_dir / "downloads" / TRANSCRIPTOMIC_ZIP_NAME,
    )

    return load_seqfish_multiomics_linked(
        str(extract_dir / "**" / f"cerebellum_rep{replicate}*.csv"),
        locus_annotation=locus,
        cell_clustering=clustering,
        transcriptomic_data=transcriptome_zip,
        transcriptome_replicate=replicate,
        transcriptome_chunksize=transcriptome_chunksize,
        cd_path=cd_path,
        h5ad_path=h5ad_path,
        **kwargs,
    )


# ----------------------------------------------------------------------
# Internal helpers
# ----------------------------------------------------------------------


@dataclass(frozen=True)
class _TranscriptomeSource:
    name: str
    path: Path
    member: Optional[str] = None


def _download_file(url: str, dest: Path) -> Path:
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and dest.stat().st_size > 0:
        return dest

    tmp = dest.with_suffix(dest.suffix + ".tmp")
    with urllib.request.urlopen(url) as r, open(tmp, "wb") as fh:
        shutil.copyfileobj(r, fh)
    tmp.replace(dest)
    return dest


def _extract_tar_once(archive: Path, dest: Path) -> Path:
    dest = Path(dest)
    if dest.exists() and any(dest.iterdir()):
        return dest
    dest.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive, "r:gz") as tf:
        tf.extractall(dest)
    return dest


def _resolve_transcriptome_sources(
    transcriptomic_data: PathLike | Iterable[PathLike] | None,
    *,
    dataset: str,
    assay: str,
    replicate: Optional[int],
    download: bool,
    data_dir: PathLike,
) -> List[_TranscriptomeSource]:
    if transcriptomic_data is None:
        if not download:
            raise ValueError(
                "transcriptomic_data is required unless download=True."
            )
        transcriptomic_data = _download_transcriptomic_zip(data_dir)

    paths = _resolve_transcriptome_paths(transcriptomic_data)
    sources: List[_TranscriptomeSource] = []
    for path in paths:
        if path.is_dir():
            for csv_path in sorted(path.rglob("*.csv")):
                name = str(csv_path.relative_to(path))
                if _transcriptome_file_matches(name, dataset, assay, replicate):
                    sources.append(_TranscriptomeSource(name=name, path=csv_path))
        elif path.suffix.lower() == ".zip":
            with zipfile.ZipFile(path) as zf:
                for member in sorted(zf.namelist()):
                    if member.endswith("/") or not member.lower().endswith(".csv"):
                        continue
                    if _transcriptome_file_matches(member, dataset, assay, replicate):
                        sources.append(_TranscriptomeSource(name=member, path=path, member=member))
        else:
            name = path.name
            if _transcriptome_file_matches(name, dataset, assay, replicate):
                sources.append(_TranscriptomeSource(name=name, path=path))
    return sources


def _resolve_transcriptome_paths(
    transcriptomic_data: PathLike | Iterable[PathLike],
) -> List[Path]:
    if isinstance(transcriptomic_data, (str, Path)):
        s = str(transcriptomic_data)
        matches = sorted(_glob.glob(s))
        if matches:
            return [Path(m) for m in matches]
        return [Path(s)]
    return [Path(p) for p in transcriptomic_data]


def _download_transcriptomic_zip(data_dir: Optional[PathLike]) -> Path:
    if data_dir is None:
        from uchrom.datasets import data_dir as _root

        data_dir = _root() / "takei2025_cerebellum"
    data_dir = Path(data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    out = data_dir / TRANSCRIPTOMIC_ZIP_NAME
    if out.exists() and out.stat().st_size > 0:
        return out
    tmp = out.with_suffix(out.suffix + ".tmp")
    with urllib.request.urlopen(TRANSCRIPTOMIC_ZIP_URL) as r, open(tmp, "wb") as fh:
        shutil.copyfileobj(r, fh)
    tmp.replace(out)
    return out


def _transcriptome_file_matches(
    name: str,
    dataset: str,
    assay: str,
    replicate: Optional[int],
) -> bool:
    lower = name.lower()
    dataset_key = dataset.lower()
    if dataset_key in {"cerebellum", "cb"}:
        if "cerebellum" not in lower:
            return False
    elif dataset_key == "e14":
        if "e14" not in lower:
            return False
    elif dataset_key == "nmumg":
        if "nmumg" not in lower:
            return False
    else:
        raise ValueError("dataset must be one of 'cerebellum', 'E14', or 'NMuMG'")

    if replicate is not None and f"replicate{int(replicate)}" not in lower:
        return False

    assay_key = assay.lower().replace("-", "_")
    if assay_key == "all":
        return "seqfish" in lower
    if assay_key == "intron":
        return "intron" in lower
    if assay_key in {"mrna", "m_rna"}:
        return "mrna" in lower
    if assay_key in {"mrna_barcoded", "barcoded"}:
        return "mrna" in lower and "non-barcoded" not in lower
    if assay_key in {"mrna_non_barcoded", "non_barcoded"}:
        return "mrna" in lower and "non-barcoded" in lower
    raise ValueError(
        "assay must be one of 'mrna', 'mrna_barcoded', "
        "'mrna_non_barcoded', 'intron', or 'all'"
    )


def _infer_replicate(name: str, default: Optional[int] = None) -> int:
    match = re.search(r"replicate[_-]?(\d+)", name, flags=re.IGNORECASE)
    if match:
        return int(match.group(1))
    match = re.search(r"(?:^|[_/-])rep[_-]?(\d+)", name, flags=re.IGNORECASE)
    if match:
        return int(match.group(1))
    if default is not None:
        return int(default)
    return 1


def _iter_csv_chunks(source: _TranscriptomeSource, *, chunksize: int):
    if source.member is None:
        yield from pd.read_csv(source.path, chunksize=chunksize, low_memory=False)
        return
    with zipfile.ZipFile(source.path) as zf:
        with zf.open(source.member) as fh:
            yield from pd.read_csv(fh, chunksize=chunksize, low_memory=False)


def _normalise_transcriptome_chunk(df: pd.DataFrame, *, replicate: int) -> pd.DataFrame:
    missing = {"fov", "cellID", "geneID"} - set(df.columns)
    if missing:
        raise ValueError(
            f"transcriptomic CSV missing required columns: {sorted(missing)}"
        )
    out = df[["fov", "cellID", "geneID"]].copy()
    if "rep" in df.columns:
        rep = df["rep"].astype(int).astype(str)
    else:
        rep = pd.Series(str(int(replicate)), index=df.index)
    out["cell_id"] = (
        rep.astype(str) + "_"
        + df["fov"].astype(int).astype(str) + "_"
        + df["cellID"].astype(int).astype(str)
    )
    out["geneID"] = out["geneID"].astype(str)
    out = out[out["geneID"].notna() & out["geneID"].ne("")]
    if "intensity" in df.columns:
        out["intensity"] = pd.to_numeric(df["intensity"], errors="coerce").fillna(0.0)
    return out[["cell_id", "geneID"] + (["intensity"] if "intensity" in out.columns else [])]


def _align_anndata_to_chromdata(adata, cd):
    cell_ids = [str(x) for x in cd.cells.index]
    have = [str(x) for x in adata.obs_names]
    pos = {cell_id: i for i, cell_id in enumerate(have)}
    missing = [cell_id for cell_id in cell_ids if cell_id not in pos]
    if missing:
        raise ValueError(f"Linked AnnData missing ChromData cell ids: {missing[:5]}")
    out = adata[[pos[cell_id] for cell_id in cell_ids]].copy()
    out.obs = cd.cells.copy()
    out.obs.index = pd.Index(cell_ids, name="cell_id")
    out.uns.setdefault("uchrom_link", {})["cell_id_axis"] = "obs_names"
    return out


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

    traces = _trace_table(merged, allele_col)

    del merged, df
    gc.collect()

    return {
        "coords": coords,
        "spots": spots,
        "tracks": tracks,
        "traces": traces,
    }


def _trace_table(merged: pd.DataFrame, allele_col: str) -> pd.DataFrame:
    """Per-trace diagnostics (vectorised; no per-trace Python loop).

    ``allele`` is constant within a trace by construction.  The other
    allele columns can disagree within a trace, so they are summarised
    as majority value + agreement fraction rather than an arbitrary
    first spot's value.
    """
    g = merged.groupby("trace_id", sort=False)
    traces = pd.DataFrame({
        "allele": g[allele_col].first().astype(np.int64),
        "n_spots": g.size().astype(np.int64),
        "n_loci": g["name"].nunique().astype(np.int64),
    })
    dup = merged.duplicated(["trace_id", "name"])
    traces["n_duplicate_loci"] = (
        dup.groupby(merged["trace_id"], sort=False).sum().reindex(traces.index).astype(np.int64)
    )
    for col in _ALLELE_COLUMNS:
        if col == allele_col or col not in merged.columns:
            continue
        counts = (merged.groupby(["trace_id", col], sort=False, observed=True).size()
                  .rename("_n").reset_index())
        top = (counts.sort_values(["trace_id", "_n"], ascending=[True, False], kind="mergesort")
               .drop_duplicates("trace_id").set_index("trace_id"))
        traces[f"{col}_majority"] = top[col].reindex(traces.index).astype(np.int64)
        traces[f"{col}_agreement"] = (top["_n"].reindex(traces.index) / traces["n_spots"]).astype(float)
    traces.index.name = "trace_id"
    return traces


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
        # cell positions (ChromData schema, uns['cell_spatial']): the CSV's
        # x, y, z are voxel coordinates in the FOV (103 nm xy, 250 nm z)
        "fov": (df["rep"].astype(int).astype(str) + "_" + df["fov"].astype(int).astype(str)).values,
        "centroid_x": df["x"].values,
        "centroid_y": df["y"].values,
        "centroid_z": df["z"].values,
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


#: voxel size of the Takei 2025 DNA seqFISH+ images (x, y, z; µm)
VOXEL_SIZE_UM = (0.103, 0.103, 0.25)


def _cell_spatial_record() -> dict:
    """``uns['cell_spatial']['default']`` for the clustering CSV centroids."""
    from chromdata.cellspatial import position_record

    return position_record(
        ("centroid_x", "centroid_y", "centroid_z"), unit="voxel", voxel_size=VOXEL_SIZE_UM,
        voxel_unit="um", frame="fov", region_col="fov", in_coords_frame=True, status="measured",
        source="cell clustering CSV (Takei et al. 2025): x, y, z voxel coordinates of each cell",
        method="segmentation (Takei et al. 2025)")


def _build_uns(
    leiden_map: Dict[int, str], allele_col: str, keep_unclustered: bool, cells=None,
) -> dict:
    # HDF5 attribute keys must be strings; stringify the leiden->cell_type
    # dict for storage.  Callers can recover int keys via
    # ``{int(k): v for k, v in cd.uns['leiden_to_cell_type'].items()}``.
    uns = _base_uns(leiden_map, allele_col, keep_unclustered)
    if cells is not None and "centroid_x" in getattr(cells, "columns", ()):
        uns["cell_spatial"] = {"default": _cell_spatial_record()}
    return uns


def _base_uns(leiden_map: Dict[int, str], allele_col: str, keep_unclustered: bool) -> dict:
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
