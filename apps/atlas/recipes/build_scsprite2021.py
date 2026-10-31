"""scSPRITE (Arrastia et al. 2022, Nat Biotechnol 40:64; GEO GSE154353): multi-way contacts of 1,000 single mouse
ES cells -> an atlas store with the clusters per cell (``ChromData.clusters``) and their contact maps.

The authors' ``GSE154353_filtered_1000_cells_single_cell_cluster_files.zip.gz`` (``python -m uchrom.datasets fetch
arrastia2021_scsprite``) holds one file per cell, named by the cell's barcode (``DPM6bot1.Odd2Bo1.Even2Bo61``: the
first three split-pool rounds), one cluster per line: ``<barcode>\\t<chrom>:<pos>\\t<chrom>:<pos>...`` — the full
barcode (the cell's tags, then the rounds that tell its clusters apart) and one position per read (mm9, the
pipeline's read start; Quinodoz 2018's format).  A read becomes the fragment ``[pos, pos + 1)``.

The store keeps every cluster as written (``clusters["scsprite"]``, cell = file); the maps are the fragment pairs of
the clusters of 2-1,000 reads (the SPRITE convention; unweighted pairs, the authors' heatmaps weight a cluster by
2/n): per cell at 1 Mb (``<store>_1mb.scool``, linked ``per_cell``) and pooled (``<store>_pooled.mcool``, 100 kb -
2 Mb, ICE-balanced, linked ``pooled``), embedded in the store; a scHiCluster embedding of the per-cell maps
(``cellm["hic_pca"]``, ``["hic_umap"]``) and its Leiden clusters (``cells["hic_leiden"]``).  Usage::

    python apps/atlas/recipes/build_scsprite2021.py [--threads 8]
"""

from __future__ import annotations

import argparse
import gzip
import shutil
import sys
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

# UCSC mm9.chrom.sizes, the primary chromosomes
MM9 = {"chr1": 197195432, "chr2": 181748087, "chr3": 159599783, "chr4": 155630120, "chr5": 152537259,
       "chr6": 149517037, "chr7": 152524553, "chr8": 131738871, "chr9": 124076172, "chr10": 129993255,
       "chr11": 121843856, "chr12": 121257530, "chr13": 120284312, "chr14": 125194864, "chr15": 103494974,
       "chr16": 98319150, "chr17": 95272651, "chr18": 90772031, "chr19": 61342430, "chrX": 166650296,
       "chrY": 15902555}
ZIP = "GSE154353_filtered_1000_cells_single_cell_cluster_files.zip.gz"


def read_cells(path: Path):
    """Fragments of every cell file of the zip: (cell ids, frame of cluster / chrom code / pos / cell code,
    chromosome names, per-cell counts, reads off the primary chromosomes)."""
    codes = {c: i for i, c in enumerate(MM9)}
    cluster, chrom, pos, cell = [], [], [], []
    names, stats, other = [], [], 0
    k = 0
    with zipfile.ZipFile(path) as z:
        members = sorted(m for m in z.namelist() if not m.endswith("/"))
        for ci, m in enumerate(members):
            name = Path(m).name
            cl, ch, ps = [], [], []
            n_clusters = 0
            with z.open(m) as fh:
                for line in fh:
                    parts = line.decode().rstrip("\n").split("\t")
                    for tok in parts[1:]:
                        c, p = tok.rsplit(":", 1)
                        code = codes.get(c)
                        if code is None:
                            other += 1
                            continue
                        cl.append(k)
                        ch.append(code)
                        ps.append(int(p))
                    k += 1
                    n_clusters += 1
            cluster.append(np.asarray(cl, np.int64))
            chrom.append(np.asarray(ch, np.int8))
            pos.append(np.asarray(ps, np.int64))
            cell.append(np.full(len(cl), ci, np.int32))
            names.append(name)
            stats.append((name, n_clusters, len(cl)))
            if (ci + 1) % 100 == 0:
                print(f"  {ci + 1} / {len(members)} cells, {sum(len(c) for c in cluster):,} fragments", flush=True)
    frame = pd.DataFrame({"cluster": np.concatenate(cluster), "chrom": pd.Categorical.from_codes(
        np.concatenate(chrom), categories=list(MM9)), "start": np.concatenate(pos)})
    frame["end"] = frame["start"] + 1
    frame["cell"] = pd.Categorical.from_codes(np.concatenate(cell), categories=names)
    cells = pd.DataFrame(stats, columns=["cell_id", "n_clusters", "n_reads"]).set_index("cell_id")
    return frame, cells, other


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--threads", type=int, default=8)
    ap.add_argument("--out", type=Path, help="default <data dir>/arrastia2021_scsprite/arrastia2021_scsprite.chromdata.zarr")
    args = ap.parse_args()

    from chromdata import ChromData
    from chromdata.embedded import embed_links
    from uchrom.datasets import data_dir
    from uchrom.emb import cluster_cells, embed_contacts
    from uchrom.fea.cluster_maps import clusters_to_mcool, clusters_to_scool

    root = data_dir() / "arrastia2021_scsprite"
    store = args.out or root / "arrastia2021_scsprite.chromdata.zarr"
    zpath = root / "raw" / "cells.zip"
    if not (zpath.is_file() and zipfile.is_zipfile(zpath)):      # decompressed once
        with gzip.open(root / "raw" / ZIP, "rb") as src, open(zpath.with_suffix(".part"), "wb") as dst:
            shutil.copyfileobj(src, dst, 1 << 24)
        zpath.with_suffix(".part").rename(zpath)

    frame, cells, other = read_cells(zpath)
    sizes = frame.groupby("cluster", sort=False).size()
    print(f"{len(cells)} cells, {len(sizes):,} clusters, {len(frame):,} reads on the primary chromosomes, "
          f"{other:,} elsewhere", flush=True)
    cell_of = frame.groupby("cluster", sort=False, observed=True)["cell"].first()
    kept = cell_of[sizes.between(2, 1000).reindex(cell_of.index).to_numpy()]
    cells["n_clusters_2_1000"] = kept.value_counts().reindex(cells.index).fillna(0).astype(np.int64).to_numpy()
    empty = pd.DataFrame({"chrom": pd.Series([], dtype=str), "start": pd.Series([], dtype=np.int64),
                          "end": pd.Series([], dtype=np.int64), "trace_id": pd.Series([], dtype=str)})
    cd = ChromData(np.zeros((0, 3)), empty, cells=cells, uns={
        "genome_assembly": "mm9", "source": "scSPRITE, Arrastia et al. 2022, Nat Biotechnol 40:64 "
        "(doi:10.1038/s41587-021-00998-1); GEO GSE154353, the authors' cluster files of 1,000 filtered cells "
        "(U-Chrom apps/atlas/recipes/build_scsprite2021.py)"})
    t = cd.set_clusters("scsprite", frame, cluster="cluster", cell="cell", keep_names=False, attrs={
        "assay": "scSPRITE", "fragments": "one per read: [pos, pos + 1), the pipeline's read start (mm9)",
        "cell": "file = the cell's barcode (DPM.Odd.Even)", "filters": "none (maps: clusters of 2-1,000 reads)"})
    del frame
    print(t, flush=True)

    stem = store.name.removesuffix(".chromdata.zarr")
    st = clusters_to_scool(cd, "scsprite", store.with_name(f"{stem}_1mb.scool"), chromsizes=MM9,
                           resolution=1_000_000, link_key="per_cell",
                           label="Per cell (1 Mb, fragment pairs of the clusters of 2-1,000 reads)")
    for c in ("n_pairs", "n_cis"):
        cd.cells[c] = st[c].reindex(cd.cells.index.astype(str)).to_numpy()
    print(st.describe().T[["mean", "50%", "max"]], flush=True)
    clusters_to_mcool(cd, "scsprite", store.with_name(f"{stem}_pooled.mcool"), chromsizes=MM9,
                      resolutions=[100_000, 200_000, 500_000, 1_000_000, 2_000_000], link_key="pooled",
                      label="All cells (fragment pairs of the clusters of 2-1,000 reads)", n_threads=args.threads)
    embed_contacts(cd, contacts="per_cell", key_added="hic", methods=("pca", "umap"), n_threads=args.threads)
    cluster_cells(cd, use="hic_pca", resolution=0.5, key_added="hic_leiden")
    print(cd.cells["hic_leiden"].value_counts().to_dict(), flush=True)
    for kind in ("linked_scool", "linked_cool"):          # stored relative to the store's folder (read above: absolute)
        for rec in cd.uns[kind].values():
            rec["path"] = Path(rec["path"]).name
    cd.write(store)
    embed_links(str(store))
    print("wrote", store, flush=True)


if __name__ == "__main__":
    sys.exit(main())
