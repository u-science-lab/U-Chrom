"""Build the GAGE-seq stores of the atlas (Zhou et al. 2024, Nat. Genet., doi:10.1038/s41588-024-01745-3;
GEO GSE238001).

GAGE-seq profiles chromatin contacts and RNA of the same single cells (combinatorial indexing; a cell is a well
pair such as ``A1,A4`` within a library).  Two stores, contacts + RNA, no 3-D coordinates:

  gageseq2024/gageseq_mouse_cortex.chromdata.zarr   mouse brain cortex, libraries mBC-0716-1 / -0716-2 / -0814-1
  gageseq2024/gageseq_human_bm_cd34.chromdata.zarr  human bone marrow CD34+, libraries CD-0722-1 / -2 / -4

Cells are the authors' annotated cells (GitHub ma-compbio/GAGE-seq ``meta_info/cell_type_annotation``: 3,296
mouse, 1,445 human), cell id ``<library>_<well pair>`` as there.  Each store links, next to it:
``<stem>_cells_1Mb.scool``, ``<stem>_bulk.mcool`` (all annotated cells, 50 kb - 1 Mb) and ``<stem>_rna.h5ad``
(UMIs per gene; gene symbols from Ensembl 98).  Embeddings: RNA PCA / UMAP and scHiCluster on the 1 Mb maps.

Inputs: ``python example-data/download_data.py --gageseq2024`` (38 GB).

Usage::

    python example-data/build_gageseq2024.py mouse
    python example-data/build_gageseq2024.py human
"""

from __future__ import annotations

import argparse
import gzip
import re
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sc_hic_common import (ContactBinner, balance_mcool, chromsizes, empty_spots, hvg_zscores, log,  # noqa: E402
                           rna_h5ad, stream_pairs)

HERE = Path(__file__).resolve().parent
OUT = HERE / "gageseq2024"
RAW = OUT / "raw"
SOURCE = "Zhou et al. 2024, Nat. Genet. (doi:10.1038/s41588-024-01745-3); GEO GSE238001"

SAMPLES = {
    "mouse": {"stem": "gageseq_mouse_cortex", "assembly": "mm10", "prefix": "mm10_",
              "meta": "meta-Seurat_mBC_complete_mm10_filtered.csv", "type_col": "Idents.obj.",
              "gtf": "Mus_musculus.GRCm38.98.gtf.gz",
              "libs": {"mBC-0716-1": ("GSM7657698_contact_mBC-HiC-0716-1.pairs.gz", "GSM7657697_RNA_mBC-RNA-0716-1.tsv.gz"),
                       "mBC-0716-2": ("GSM7657700_contact_mBC-HiC-0716-2.pairs.gz", "GSM7657699_RNA_mBC-RNA-0716-2.tsv.gz"),
                       "mBC-0814-1": ("GSM7657702_contact_mBC-HiC-0814-1.pairs.gz", "GSM7657701_RNA_mBC-RNA-0814-1.tsv.gz")}},
    "human": {"stem": "gageseq_human_bm_cd34", "assembly": "hg38", "prefix": "hg38_",
              "meta": "meta-python_CD_complete_hg38_filtered.csv", "type_col": "cell type",
              "gtf": "Homo_sapiens.GRCh38.98.gtf.gz",
              "libs": {"CD-0722-1": ("GSM7657704_contact_CD-HiC-0722-1.pairs.gz", "GSM7657703_RNA_CD-RNA-0722-1.tsv.gz"),
                       "CD-0722-2": ("GSM7657706_contact_CD-HiC-0722-2.pairs.gz", "GSM7657705_RNA_CD-RNA-0722-2.tsv.gz"),
                       "CD-0722-4": ("GSM7657708_contact_CD-HiC-0722-4.pairs.gz", "GSM7657707_RNA_CD-RNA-0722-4.tsv.gz")}},
}


def load_cells(spec) -> pd.DataFrame:
    m = pd.read_csv(RAW / "github" / spec["meta"], index_col=0)
    cells = pd.DataFrame(index=pd.Index(m.index.astype(str), name="cell_id"))
    cells["library"] = cells.index.str.rsplit("_", n=1).str[0]
    cells["cell_type"] = m[spec["type_col"]].astype(str).to_numpy()
    if "louvain" in m:
        cells["louvain"] = m["louvain"].astype(str).to_numpy()
    return cells


def gene_names(gtf: Path) -> pd.Series:
    ids, names = [], []
    with gzip.open(gtf, "rt") as fh:
        for line in fh:
            if line.startswith("#"):
                continue
            f = line.split("\t", 9)
            if f[2] != "gene":
                continue
            gid = re.search(r'gene_id "([^"]+)"', f[8])
            gn = re.search(r'gene_name "([^"]+)"', f[8])
            if gid:
                ids.append(gid.group(1))
                names.append(gn.group(1) if gn else gid.group(1))
    return pd.Series(names, index=ids)


def bin_contacts(spec, cells, stem: Path):
    libs = spec["libs"]
    first = RAW / "GSE238001" / next(iter(libs.values()))[0]
    sizes = chromsizes(None, spec["assembly"])
    binner = ContactBinner(sizes, cells.index, stem.parent / f".{stem.name}_bins")
    strip = len(spec["prefix"])
    for lib, (pairs, _) in libs.items():
        t0, n = time.time(), 0
        for df in stream_pairs(RAW / "GSE238001" / pairs, {"chr1": 0, "pos1": 1, "chr2": 2, "pos2": 3, "cell": 4}):
            for c in ("chr1", "chr2"):
                df[c] = df[c].cat.rename_categories(lambda s: s[strip:] if s.startswith(spec["prefix"]) else "_" + s)
            df["cell"] = df["cell"].cat.rename_categories(lambda s: f"{lib}_{s}")
            binner.add_frame(df)
            n += len(df)
        log(f"  {lib}: {n:,} contacts in {time.time() - t0:.0f} s")
    binner.close()
    log(f"contacts: {binner.n_in:,} read, {binner.n_kept:,} of the {len(cells):,} annotated cells")
    scool = stem.with_name(stem.name + "_cells_1Mb.scool")
    names = binner.write_scool(scool)
    log(f"wrote {scool.name}: {len(names):,} cells")
    mcool = binner.write_mcool(stem.with_name(stem.name + "_bulk.mcool"))
    per_cell = pd.Series(binner.per_cell, index=binner.cells)
    binner.cleanup()
    return scool, mcool, per_cell, sizes, first


def load_rna(spec, cells):
    import scipy.sparse as sp

    rows, cols, genes = [], [], {}
    index = {c: i for i, c in enumerate(cells.index)}
    for lib, (_, rna) in spec["libs"].items():
        for df in pd.read_csv(RAW / "GSE238001" / rna, sep="\t", header=None, names=["chrom", "bc", "gene"],
                              dtype=str, chunksize=20_000_000):
            ci = (lib + "_" + df["bc"]).map(index)
            ok = ci.notna().to_numpy()
            g = df["gene"].to_numpy()[ok]
            gi = np.array([genes.setdefault(x, len(genes)) for x in g], dtype=np.int64)
            rows.append(ci[ok].astype(np.int64).to_numpy())
            cols.append(gi)
    r, c = np.concatenate(rows), np.concatenate(cols)
    x = sp.csr_matrix((np.ones(len(r), np.float32), (r, c)), shape=(len(cells), len(genes)))
    x.sum_duplicates()
    ids = pd.Index(list(genes), name="gene_id")
    names = gene_names(RAW / "ensembl98" / spec["gtf"]).reindex(ids)
    var = pd.DataFrame({"gene_id": ids}, index=pd.Index(names.fillna(pd.Series(ids, index=ids)).to_numpy(), name="gene"))
    return x, var


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("sample", choices=sorted(SAMPLES))
    ap.add_argument("--reuse-contacts", action="store_true")
    args = ap.parse_args()

    from uchrom import ChromData
    from uchrom.emb import embed_cells, scool_cell_features

    spec = SAMPLES[args.sample]
    stem = OUT / spec["stem"]
    cells = load_cells(spec)
    log(f"{args.sample}: {len(cells):,} annotated cells; {cells['cell_type'].value_counts().head(12).to_dict()}")
    scool = stem.with_name(stem.name + "_cells_1Mb.scool")
    mcool = stem.with_name(stem.name + "_bulk.mcool")
    sizes = chromsizes(None, spec["assembly"])
    if not (args.reuse_contacts and scool.exists() and mcool.exists()):
        scool, mcool, per_cell, sizes, _ = bin_contacts(spec, cells, stem)
        cells["n_contacts"] = per_cell.reindex(cells.index).fillna(0).astype(np.int64).to_numpy()
    else:
        log(f"balanced {balance_mcool(mcool)} of {mcool.name}")
    counts, var = load_rna(spec, cells)
    cells["n_counts_rna"] = np.asarray(counts.sum(1)).ravel()
    cells["n_genes_rna"] = np.asarray((counts > 0).sum(1)).ravel()
    cd = ChromData(np.zeros((0, 3)), empty_spots(), cells=cells,
                   uns={"genome_assembly": spec["assembly"], "source": SOURCE,
                        "coordinate_status": "no 3-D coordinates: contacts only"})
    cd.uns["linked_anndata"] = rna_h5ad(counts, cells.index, var, stem.with_name(stem.name + "_rna.h5ad"),
                                        description="GAGE-seq RNA: UMIs per gene (X), one row per cell of cells; "
                                                    "var index = gene symbol (Ensembl 98), gene_id = Ensembl id")
    log(f"RNA: {counts.shape[0]:,} cells x {counts.shape[1]:,} genes, {int(counts.sum()):,} UMIs")
    z, hvg = hvg_zscores(counts)
    embed_cells(cd, source="rna", matrix=z, normalization="none", methods=("pca", "umap"), n_pcs=30,
                features=f"the {len(hvg):,} most variable genes (log1p CP10k, z-score, clipped at 10)")
    feats, _, depth = scool_cell_features(str(scool), list(cells.index), chroms=[c for c in sizes if c != "chrY"])
    if "n_contacts" not in cd.cells:
        cd.cells["n_contacts"] = np.asarray(depth, dtype=np.int64)
    embed_cells(cd, source="hic", matrix=feats, normalization="none", methods=("pca", "umap"), n_pcs=30,
                features="scHiCluster (convolution + random walk + binarise) of the per-cell 1 Mb maps")
    cd.link_cool(mcool.name, key="bulk", label="All cells (merged)")
    cd.link_scool(scool.name, key="per_cell", label="Per cell", cell_name="cell_id", genome_assembly=spec["assembly"],
                  bin_size=1_000_000)
    out = stem.with_name(stem.name + ".chromdata.zarr")
    cd.write(out)
    log(f"wrote {out}: {cd}")


if __name__ == "__main__":
    main()
