"""Takei 2025 cerebellum DNA seqFISH+ — the first ~47 cells of rep 1, FOV 0.

The Zenodo tarball (record 7693825, ~2.8 GB) holds one ~2 GB CSV per field of
view; ``uchrom.datasets.fetch("takei2025_fov0")`` streams it, stops after 400,000
rows of the first FOV and drops the last (possibly cut) cell.  This script loads
the 47 cells with
:func:`uchrom.io.seqfish_multiomics.read_seqfish_multiomics` — 3-D traces
plus 59 per-spot immunofluorescence / RNA-FISH tracks (H3K27ac, H3K9me3,
LaminB1, …), cell types and the published UMAP.

It then adds a histone / IF cell embedding (``--no-if`` skips it):

* ``cells['if.<mark>']`` — per-cell mean of each of the 48 antibody
  channels' spot z-scores (for colouring);
* ``cellm['if_pca' / 'if_tsne' / 'if_umap']`` — from the within-cell
  mark–mark Pearson correlations over all spots (1,128 features),
  z-scored → PCA → t-SNE / UMAP.  On these 47 cells this separated cell
  types better (kNN-5 purity 0.61) than per-cell means (0.44), mark ×
  chromosome (0.39) or mark × 10 Mb means (0.47–0.50); chance ≈ 0.28.

  takei2025_fov0/takei2025_fov0.chromdata.zarr   (~76 MB; not checked in)

Usage::

    python apps/atlas/recipes/build_takei2025_fov0.py
    python apps/atlas/recipes/build_takei2025_fov0.py --update   # only redo the IF embedding
"""

from __future__ import annotations

import argparse
from pathlib import Path

from uchrom.datasets import data_dir, fetch

HERE = Path(__file__).resolve().parent
DATA = data_dir()                       # $UCHROM_DATA, else ~/.cache/uchrom
OUT = DATA / "takei2025_fov0"


def add_if_embedding(cd) -> None:
    """``if.<mark>`` per-cell means + ``if_pca/_tsne/_umap`` from the
    within-cell mark–mark correlations (see the module docstring)."""
    from uchrom.emb import aggregate_tracks, embed_cells
    from uchrom.io.seqfish_multiomics import IF_COLUMNS

    marks = [c for c in IF_COLUMNS if c in cd.spot_tracks.columns]
    aggregate_tracks(cd, marks, prefix="if", stat="mean")
    corr = aggregate_tracks(cd, marks, prefix="if", stat="corr", write=False)
    embed_cells(cd, source="if", matrix=corr.to_numpy(), normalization="zscore",
                features=f"within-cell Pearson correlation of every pair of the {len(marks)} IF "
                         f"channels' spot z-scores ({corr.shape[1]} features)")
    if "umap" in cd.cellm:
        cd.uns.setdefault("embeddings", {})["umap"] = {
            "method": "umap", "label": "Published UMAP (RNA)", "modality": "Published",
            "source": "Takei 2025 clustering CSV (mRNA seqFISH)", "axis_prefix": "UMAP"}



SUFFIX = {"zarr": ".chromdata.zarr", "cdz": ".cdz"}


def existing(stem: Path):
    """The dataset as built by this or an older version of the script."""
    return next((stem.with_name(stem.name + s) for s in SUFFIX.values()
                 if stem.with_name(stem.name + s).exists()), None)


def save(cd, out: Path) -> None:
    """Write ``cd``; the zarr / cdz writer replaces ``out`` atomically, so a
    running browser never sees a half-written store."""
    cd.write(out)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--update", action="store_true", help="reuse the existing dataset; only redo the IF embedding")
    ap.add_argument("--no-if", action="store_true", help="skip the IF / histone embedding")
    ap.add_argument("--format", default="zarr", choices=sorted(SUFFIX), help="output container (default zarr)")
    args = ap.parse_args()
    OUT.mkdir(exist_ok=True)
    stem = OUT / "takei2025_fov0"
    out = stem.with_name(stem.name + SUFFIX[args.format])

    from uchrom import ChromData

    if args.update:
        cd = ChromData.read(existing(stem) or out)
    else:
        src = fetch("takei2025_fov0")      # the first 400,000 rows of FOV 0 (47 cells) + locus map + clustering
        from uchrom.io.seqfish_multiomics import read_seqfish_multiomics

        cd = read_seqfish_multiomics(
            src / "cerebellum_rep1_pos0_cells.csv",
            locus_annotation=src / "LC1-100k-09022022-mm10-25kb-meta.csv",
            cell_clustering=src / "cerebellum_mRNA_cluster_nuc_vol_filtered.csv",
        )
    if not args.no_if:
        add_if_embedding(cd)
    save(cd, out)
    print(cd)


if __name__ == "__main__":
    main()
