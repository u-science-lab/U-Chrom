"""Build the Droplet Hi-C stores of the atlas (Chang et al. 2024, Nat. Biotechnol., doi:10.1038/s41587-024-02447-1;
GEO GSE253407).

Droplet Hi-C runs single-cell Hi-C in 10x droplets; Paired Hi-C adds the RNA of the same nuclei (10x Multiome).
Two stores of the adult mouse cortex, no 3-D coordinates:

  droplet_hic2024/droplet_hic_mouse_cortex.chromdata.zarr   Droplet Hi-C, libraries LC462 + LC716 (cells of
                                                             GSE253407_Droplet_Hi-C_mouse_ctx_metadata, cell
                                                             type = ``rnatype``, the authors' label transfer)
  droplet_hic2024/paired_hic_mouse_cortex.chromdata.zarr    Paired Hi-C, Hi-C LC464 / LC465 / LC608 with RNA
                                                             LC466 / LC467 / LC613 (cells of
                                                             GSE253407_Paired_Hi-C_mouse_ctx_metadata: RNA
                                                             barcode ``bc`` <-> Hi-C barcode ``atac_bc``; cell type
                                                             ``Anno_yel``)

The deposited pairs keep every read pair; cis pairs closer than 1 kb (ligation products of one fragment, the
metadata's ``cis_1kb-``) are dropped.  Each store links ``<stem>_cells_1Mb.scool``, ``<stem>_bulk.mcool``
(50 kb - 1 Mb) and, Paired Hi-C, ``<stem>_rna.h5ad`` (10x counts of the cells).  Embeddings: scHiCluster on the
1 Mb maps; Paired Hi-C also RNA PCA / UMAP.

Inputs: ``python example-data/download_data.py --droplet_hic2024_meta --droplet_hic2024`` (72 GB).

Usage::

    python example-data/build_droplet_hic2024.py droplet
    python example-data/build_droplet_hic2024.py paired
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sc_hic_common import (ContactBinner, chromsizes, empty_spots, hvg_zscores, log, rna_h5ad,  # noqa: E402
                           stream_pairs)

HERE = Path(__file__).resolve().parent
OUT = HERE / "droplet_hic2024"
RAW = OUT / "raw" / "GSE253407"
SOURCE = "Chang et al. 2024, Nat. Biotechnol. (doi:10.1038/s41587-024-02447-1); GEO GSE253407"
PAIRS = {"LC462": "GSM8020244_LC462_mm10.sc.pairs.gz", "LC716": "GSM8020245_LC716_mm10.sc.pairs.gz",
         "LC464": "GSM8020251_LC464_merged_mm10.sc.pairs.gz", "LC465": "GSM8020253_LC465_mm10.sc.pairs.gz",
         "LC608": "GSM8020255_LC608_mm10.sc.pairs.gz"}
RNA_H5 = {"LC466": "GSM8020252_LC466_raw_feature_bc_matrix.h5", "LC467": "GSM8020254_LC467_raw_feature_bc_matrix.h5",
          "LC613": "GSM8020256_LC613_raw_feature_bc_matrix.h5"}


def load_cells(sample: str):
    """(cells, Hi-C key -> cell id) where the Hi-C key is ``<library>_<barcode>`` of the pairs."""
    if sample == "droplet":
        m = pd.read_csv(RAW / "GSE253407_Droplet_Hi-C_mouse_ctx_metadata.xls.gz", sep="\t", index_col=0)
        ids = (m["sample"].astype(str) + "_" + m["bc"].astype(str)).to_numpy()
        cells = pd.DataFrame({"library": m["sample"].astype(str).to_numpy(), "cell_type": m["rnatype"].astype(str).to_numpy(),
                              "cell_type_score": m["score"].to_numpy(), "n_pairs_published": m["total"].to_numpy(),
                              "n_cis_1kb_published": m["cis_1kb+"].to_numpy(), "n_trans_published": m["trans"].to_numpy()},
                             index=pd.Index(ids, name="cell_id"))
        return cells, pd.Series(ids, index=ids)
    m = pd.read_csv(RAW / "GSE253407_Paired_Hi-C_mouse_ctx_metadata.xls.gz", sep="\t", index_col=0)
    ids = (m["rna"].astype(str) + "_" + m["bc"].astype(str)).to_numpy()
    cells = pd.DataFrame({"rna_library": m["rna"].astype(str).to_numpy(), "hic_library": m["dna"].astype(str).to_numpy(),
                          "hic_barcode": m["atac_bc"].astype(str).to_numpy(),
                          "cell_type": m["Anno_yel"].astype(str).to_numpy(),
                          "cell_type_predicted": m["predicted.id"].astype(str).to_numpy(),
                          "n_counts_rna": m["nCount_RNA"].to_numpy(), "n_genes_rna": m["nFeature_RNA"].to_numpy(),
                          "percent_mt": m["percent.mt"].to_numpy(), "n_pairs_published": m["total"].to_numpy(),
                          "n_cis_1kb_published": m["cis_1kb."].to_numpy(), "n_trans_published": m["trans"].to_numpy()},
                         index=pd.Index(ids, name="cell_id"))
    keys = (m["dna"].astype(str) + "_" + m["atac_bc"].astype(str)).to_numpy()
    return cells, pd.Series(ids, index=keys)


def bin_contacts(cells, hic_key: pd.Series, stem: Path):
    libs = sorted({k.split("_", 1)[0] for k in hic_key.index})
    sizes = chromsizes(None, "mm10")
    binner = ContactBinner(sizes, cells.index, stem.parent / f".{stem.name}_bins", min_cis=1000)
    for lib in libs:
        t0, n = time.time(), 0
        for df in stream_pairs(RAW / PAIRS[lib], {"chr1": 1, "pos1": 2, "chr2": 3, "pos2": 4, "cell": 8}):
            df["cell"] = df["cell"].cat.rename_categories(lambda b: hic_key.get(f"{lib}_{b}", f"-{lib}_{b}"))
            binner.add_frame(df)
            n += len(df)
            if n % 200_000_000 < len(df):
                log(f"  {lib}: {n:,} pairs ({n / (time.time() - t0) / 1e6:.1f} M/s)")
        log(f"  {lib}: {n:,} pairs in {time.time() - t0:.0f} s")
    binner.close()
    log(f"pairs: {binner.n_in:,} read, {binner.n_kept:,} kept (annotated cells, >= 1 kb or trans)")
    scool = stem.with_name(stem.name + "_cells_1Mb.scool")
    names = binner.write_scool(scool)
    log(f"wrote {scool.name}: {len(names):,} cells")
    mcool = binner.write_mcool(stem.with_name(stem.name + "_bulk.mcool"))
    per_cell = pd.Series(binner.per_cell, index=binner.cells)
    binner.cleanup()
    return scool, mcool, per_cell, sizes


def read_10x_h5(path: Path):
    """(cells x genes csr, barcodes, gene symbols, gene ids) of a Cell Ranger ``*_feature_bc_matrix.h5``."""
    import h5py
    import scipy.sparse as sp

    with h5py.File(path, "r") as f:
        g = f["matrix"]
        x = sp.csc_matrix((g["data"][:], g["indices"][:], g["indptr"][:]), shape=tuple(g["shape"][:]))
        bcs = np.array([b.decode() for b in g["barcodes"][:]])
        ft = g["features"]
        names = np.array([b.decode() for b in ft["name"][:]])
        ids = np.array([b.decode() for b in ft["id"][:]])
        kind = np.array([b.decode() for b in ft["feature_type"][:]]) if "feature_type" in ft else np.full(len(ids), "Gene Expression")
    keep = kind == "Gene Expression"
    return x.T.tocsr()[:, keep], bcs, names[keep], ids[keep]


def load_rna(cells):
    import scipy.sparse as sp

    blocks, order = [], []
    var = None
    for lib, h5 in RNA_H5.items():
        x, bcs, names, ids = read_10x_h5(RAW / h5)
        sub = cells[cells["rna_library"] == lib]
        want = pd.Index(sub.index.str.split("_", n=1).str[1])
        rows = pd.Index(bcs).get_indexer(want)
        if (rows < 0).any():
            raise SystemExit(f"{lib}: {(rows < 0).sum()} cells not in {h5}")
        blocks.append(x[rows])
        order.extend(sub.index)
        v = pd.DataFrame({"gene_id": ids}, index=pd.Index(names, name="gene"))
        if var is not None and not (var["gene_id"].to_numpy() == ids).all():
            raise SystemExit("the RNA libraries have different genes")
        var = v
    x = sp.vstack(blocks).tocsr()[pd.Index(order).get_indexer(cells.index)]
    return x, var


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("sample", choices=("droplet", "paired"))
    ap.add_argument("--reuse-contacts", action="store_true")
    args = ap.parse_args()

    from uchrom import ChromData
    from uchrom.emb import embed_cells, scool_cell_features

    stem = OUT / ("droplet_hic_mouse_cortex" if args.sample == "droplet" else "paired_hic_mouse_cortex")
    cells, hic_key = load_cells(args.sample)
    log(f"{args.sample}: {len(cells):,} cells; {cells['cell_type'].value_counts().head(12).to_dict()}")
    scool = stem.with_name(stem.name + "_cells_1Mb.scool")
    mcool = stem.with_name(stem.name + "_bulk.mcool")
    sizes = chromsizes(None, "mm10")
    if not (args.reuse_contacts and scool.exists() and mcool.exists()):
        scool, mcool, per_cell, sizes = bin_contacts(cells, hic_key, stem)
        cells["n_contacts"] = per_cell.reindex(cells.index).fillna(0).astype(np.int64).to_numpy()
    cd = ChromData(np.zeros((0, 3)), empty_spots(), cells=cells,
                   uns={"genome_assembly": "mm10", "source": SOURCE,
                        "coordinate_status": "no 3-D coordinates: contacts only",
                        "contacts_filter": "cis pairs closer than 1 kb dropped"})
    if args.sample == "paired":
        counts, var = load_rna(cells)
        cd.uns["linked_anndata"] = rna_h5ad(counts, cells.index, var, stem.with_name(stem.name + "_rna.h5ad"),
                                            description="Paired Hi-C RNA: 10x UMI counts (X), one row per cell of cells "
                                                        "(raw_feature_bc_matrix of LC466 / LC467 / LC613)")
        log(f"RNA: {counts.shape[0]:,} cells x {counts.shape[1]:,} genes")
        z, hvg = hvg_zscores(counts)
        embed_cells(cd, source="rna", matrix=z, normalization="none", methods=("pca", "umap"), n_pcs=30,
                    features=f"the {len(hvg):,} most variable genes (log1p CP10k, z-score, clipped at 10)")
    feats, _, _ = scool_cell_features(str(scool), list(cells.index), chroms=[c for c in sizes if c != "chrY"])
    embed_cells(cd, source="hic", matrix=feats, normalization="none", methods=("pca", "umap"), n_pcs=30,
                features="scHiCluster (convolution + random walk + binarise) of the per-cell 1 Mb maps")
    cd.link_cool(mcool.name, key="bulk", label="All cells (merged)")
    cd.link_scool(scool.name, key="per_cell", label="Per cell", cell_name="cell_id", genome_assembly="mm10",
                  bin_size=1_000_000)
    out = stem.with_name(stem.name + ".chromdata.zarr")
    cd.write(out)
    log(f"wrote {out}: {cd}")


if __name__ == "__main__":
    main()
