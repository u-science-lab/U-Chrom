"""Spatial Hi-C-RNA (Guo et al. 2026, Cell; GEO GSE311199) -> three .chromdata.zarr stores.

Hi-C and RNA are read from the **same spots** (one barcode grid per chip: 100 x 100, 80 x 80 or
200 x 200).  The stores are ChromData without 3-D spots, as the other spatial Hi-C datasets
(build_spatial_hic_chen2026.py, build_spatial_atac_hic.py)::

    spatial_hicrna/hicrna_mouse_brain.chromdata.zarr      mouse_brain_r1, mouse_brain_r2           (mm10)
    spatial_hicrna/hicrna_mouse_embryo.chromdata.zarr     E11.5, E13.5_r1, E13.5_r2                (mm10)
    spatial_hicrna/hicrna_human_melanoma.chromdata.zarr   human_melanoma_r1, human_melanoma_r2     (hg38)

(the ``hicrna_`` prefix keeps the dataset names apart from the ATAC-Hi-C ``mouse_brain`` in the browser, which
saves layouts per dataset name)

Input (``download_data.py --spatial_hicrna``, ``spatial_hicrna/raw/GSE311199/``, 2.0 GB): per sample the
10x RNA matrix of every barcode of the grid, the Visium-style positions (``tissue_positions_list.csv``:
barcode, in_tissue, array_row, array_col, pxl_row, pxl_col), the tissue image, and for three samples
the authors' processed Hi-C + RNA AnnData (cell types, clusters, latent spaces, single-spot A/B).
Optional ``contacts/<sample>.spot_stats.tsv`` (Sherlock pipeline, ``spatial_hicrna/sherlock/``) adds the
Hi-C contacts per spot.  The contact maps themselves are linked by ``link_spatial_hicrna_contacts.py``.

What a store holds
  cells        one row per **published in-tissue spot** (``<section>:<barcode>``): grid position,
               image pixels, RNA UMI / genes, Hi-C contacts, the authors' annotations where they
               published them, and ``rna.<gene>`` (log1p CP10k) of the top highly variable genes plus
               marker genes, so the browser can colour by expression
  cellm        ``rna_pca`` / ``rna_umap`` (this script: top-2,000 HVGs of all the store's spots, no batch
               correction) and, for the sections with a published AnnData, UMAPs of the published latent
               spaces (``published_scvi_umap`` ...; NaN for the other sections)
  linked       ``hicrna_<store>_rna.h5ad`` (raw counts, all genes, ``uns['linked_anndata']``) and the tissue images
               (``hicrna_<store>_images/<section>.png``, ``uns['linked_images']``)
  positions    ``cell_positions``: the spot grid ("default") and image pixels ("image"), per section

Grid and image axes: the published ``array_col`` runs **against** the image columns (``array_col = 99``
sits at ``pxl_col = 4``), so ``grid_col = n_cols - 1 - array_col``; rows agree.

    python example-data/build_spatial_hicrna.py [--stores mouse_brain,mouse_embryo,human_melanoma]
"""

from __future__ import annotations

import argparse
import gzip
import json
import re
import tarfile
import time
import warnings
from pathlib import Path

import anndata as ad
import numpy as np
import pandas as pd
import scipy.io
import scipy.sparse as sp

from uchrom import ChromData
from uchrom.emb.cells import embed_cells

ROOT = Path(__file__).resolve().parent / "spatial_hicrna"
RAW = ROOT / "raw" / "GSE311199"
CONTACTS = ROOT / "contacts"
SOURCE = "Guo et al. 2026, Cell (doi:10.1016/j.cell.2026.07.039); GEO GSE311199"

#: main chromosomes of the pairs files (`#chromsize:` headers of the GEO `.nodups.pairs.gz`)
MM10 = {"chr1": 195471971, "chr2": 182113224, "chr3": 160039680, "chr4": 156508116, "chr5": 151834684,
        "chr6": 149736546, "chr7": 145441459, "chr8": 129401213, "chr9": 124595110, "chr10": 130694993,
        "chr11": 122082543, "chr12": 120129022, "chr13": 120421639, "chr14": 124902244, "chr15": 104043685,
        "chr16": 98207768, "chr17": 94987271, "chr18": 90702639, "chr19": 61431566, "chrX": 171031299,
        "chrY": 91744698}
HG38 = {"chr1": 248956422, "chr2": 242193529, "chr3": 198295559, "chr4": 190214555, "chr5": 181538259,
        "chr6": 170805979, "chr7": 159345973, "chr8": 145138636, "chr9": 138394717, "chr10": 133797422,
        "chr11": 135086622, "chr12": 133275309, "chr13": 114364328, "chr14": 107043718, "chr15": 101991189,
        "chr16": 90338345, "chr17": 83257441, "chr18": 80373285, "chr19": 58617616, "chr20": 64444167,
        "chr21": 46709983, "chr22": 50818468, "chrX": 156040895, "chrY": 57227415}

STORES = {
    "mouse_brain": {
        "title": "spatial Hi-C-RNA, mouse brain (coronal)", "assembly": "mm10", "chroms": MM10,
        "sections": [
            {"key": "mouse_brain_r1", "rna": "GSM9320917_mouse_brain_r1_RNA.tar.gz",
             "image": "GSM9320917_mouse_brain_r1_Image.tar.gz", "h5ad": "GSM9320916_mouse_brain_r1_HIC_RNA.h5ad.gz"},
            {"key": "mouse_brain_r2", "rna": "GSM9320919_mouse_brain_r2_RNA.tar.gz",
             "image": "GSM9320919_mouse_brain_r2_Image.tar.gz", "h5ad": None},
        ],
        "markers": "Snap25 Rbfox3 Slc17a7 Slc17a6 Gad1 Gad2 Slc32a1 Sst Pvalb Vip Lamp5 Cux2 Rorb Fezf2 Bcl11b "
                   "Tbr1 Satb2 Mbp Plp1 Mog Olig1 Olig2 Pdgfra Gfap Aqp4 Aldh1l1 Slc1a3 Cx3cr1 P2ry12 Csf1r "
                   "Pecam1 Cldn5 Flt1 Dcn Npy Reln Calb1 Calb2 Prox1 Neurod6 Camk2a Nrgn",
    },
    "mouse_embryo": {
        "title": "spatial Hi-C-RNA, mouse embryo (E11.5, E13.5)", "assembly": "mm10", "chroms": MM10,
        "sections": [
            {"key": "mouse_embryo_E11.5", "rna": "GSM9320921_mouse_embryo_E11.5_RNA.tar.gz",
             "image": "GSM9320921_mouse_embryo_E11.5_Image.tar.gz",
             "h5ad": "GSM9320920_mouse_embryo_E11.5_HIC_RNA.h5ad.gz"},
            {"key": "mouse_embryo_E13.5_r1", "rna": "GSM9738332_mouse_embryo_E13.5_RNA_r1.tar.gz",
             "image": "GSM9738332_mouse_embryo_E13.5_r1_Image.tar.gz", "h5ad": None},
            {"key": "mouse_embryo_E13.5_r2", "rna": "GSM9738334_mouse_embryo_E13.5_RNA_r2.tar.gz",
             "image": "GSM9738334_mouse_embryo_E13.5_r2_Image.tar.gz", "h5ad": None},
        ],
        "markers": "Sox2 Nes Pax6 Neurod1 Tubb3 Myh6 Myl7 Nkx2-5 Hba-a1 Hbb-bs Alb Afp Sox9 Col2a1 Acta1 Myog "
                   "Pax3 Pax7 Krt5 Krt14 Epcam Pecam1 Hoxa9 Hoxb9 Hoxd13 Mki67 Top2a Gata1 Cdh1 Lyz2 Tbx5 "
                   "Foxa2 Sftpc Nkx2-1 Isl1 Phox2b Th Olig2 Mbp Dcn Col1a1",
    },
    "human_melanoma": {
        "title": "spatial Hi-C-RNA, human melanoma", "assembly": "hg38", "chroms": HG38,
        "sections": [
            {"key": "human_melanoma_r1", "rna": "GSM9320923_Human_melanoma_RNA.tar.gz",
             "image": "GSM9320923_Human_melanoma_Image.tar.gz",
             "h5ad": "GSM9320922_Human_melanoma_HIC_RNA.h5ad.gz"},
            {"key": "human_melanoma_r2", "rna": "GSM9738330_Human_melanoma_RNA_r2.tar.gz",
             "image": "GSM9738330_Human_melanoma_r2_Image.tar.gz", "h5ad": None},
        ],
        "markers": "MLANA PMEL TYR SOX10 MITF AXL PTPRC CD3E CD8A CD4 CD68 CD14 CD19 MS4A1 PECAM1 VWF COL1A1 "
                   "COL1A2 ACTA2 KRT5 KRT14 MKI67 CD274 PDCD1 FOXP3 CD79A JCHAIN LYZ S100B NGFR EGFR",
    },
}
POS_COLS = ["barcode", "in_tissue", "array_row", "array_col", "pxl_row", "pxl_col"]
N_HVG = 2000
N_RNA_COLUMNS = 100        # highly variable genes kept as cells columns (rna.<gene>), besides the markers


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


# ---- reading the GEO files -------------------------------------------------------------------

def _member(t: tarfile.TarFile, suffix: str):
    return next(m for m in t.getmembers() if m.name.endswith(suffix) and "@eaDir" not in m.name)


def read_rna(path: Path):
    """(barcodes, genes table [gene_id, symbol], counts genes x barcodes as CSC) of a 10x raw matrix tar."""
    with tarfile.open(path) as t:
        barcodes = gzip.open(t.extractfile(_member(t, "raw/barcodes.tsv.gz")), "rt").read().split()
        genes = pd.read_csv(t.extractfile(_member(t, "raw/features.tsv.gz")), sep="\t", header=None,
                            names=["gene_id", "symbol", "type"], compression="gzip")
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            x = scipy.io.mmread(gzip.open(t.extractfile(_member(t, "raw/matrix.mtx.gz")))).tocsc()
    return barcodes, genes, x


def read_image_tar(path: Path):
    """(positions, scale factors, PNG bytes) of a Visium-style image tar."""
    with tarfile.open(path) as t:
        pos = pd.read_csv(t.extractfile(_member(t, "tissue_positions_list.csv")), header=None, names=POS_COLS)
        sf = json.load(t.extractfile(_member(t, "scalefactors_json.json")))
        png = t.extractfile(_member(t, "tissue_lowres_image.png")).read()
    return pos, sf, png


def unique_symbols(genes: pd.DataFrame) -> pd.Index:
    """Gene symbols; a symbol shared by several genes gets its Ensembl id appended."""
    sym = genes["symbol"].astype(str)
    dup = sym.duplicated(keep=False)
    return pd.Index(np.where(dup, sym + "_" + genes["gene_id"].astype(str), sym))


# ---- one section -----------------------------------------------------------------------------

def read_section(spec: dict, assembly_hint: str):
    """Everything of one section: cells table (in-tissue spots), counts, genes, image, published AnnData."""
    key = spec["key"]
    barcodes, genes, x = read_rna(RAW / spec["rna"])
    pos, sf, png = read_image_tar(RAW / spec["image"])
    assert set(pos["barcode"]) == set(barcodes), f"{key}: positions and RNA barcodes differ"
    # the grid column runs against the image column in every sample: grid_col follows the image
    r = np.corrcoef(pos["array_col"], pos["pxl_col"])[0, 1]
    assert r < -0.99 and np.corrcoef(pos["array_row"], pos["pxl_row"])[0, 1] > 0.99, f"{key}: axes {r:.3f}"
    n_cols = int(pos["array_col"].max()) + 1
    pos["grid_col"] = n_cols - 1 - pos["array_col"]
    pos["grid_row"] = pos["array_row"]
    col = pd.Series(np.arange(len(barcodes)), index=barcodes)
    pos = pos[pos["in_tissue"] == 1].reset_index(drop=True)          # the published in-tissue spots
    idx = col[pos["barcode"]].to_numpy()
    counts = x[:, idx].T.tocsr().astype(np.float32)                  # spots x genes
    cells = pd.DataFrame({
        "section": key, "barcode": pos["barcode"].to_numpy(),
        "array_row": pos["array_row"].to_numpy(), "array_col": pos["array_col"].to_numpy(),
        "grid_col": pos["grid_col"].to_numpy(), "grid_row": pos["grid_row"].to_numpy(),
        "image_x": pos["pxl_col"].to_numpy(float), "image_y": pos["pxl_row"].to_numpy(float),
        "rna_umi": np.asarray(counts.sum(1)).ravel(), "rna_genes": np.asarray((counts > 0).sum(1)).ravel(),
    }, index=pd.Index(key + ":" + pos["barcode"], name="cell_id"))
    # the full grid, for reporting what the published mask leaves out
    umi_all = pd.Series(np.asarray(x.sum(0)).ravel(), index=barcodes)
    stats = CONTACTS / f"{key}.spot_stats.tsv"
    if stats.exists():
        st = pd.read_csv(stats, sep="\t").set_index("barcode")
        cells["hic_contacts"] = st["n_contacts"].reindex(cells["barcode"]).to_numpy()
        cells["hic_cis_fraction"] = st["cis_fraction"].reindex(cells["barcode"]).to_numpy()
    return {"key": key, "cells": cells, "counts": counts, "genes": genes, "png": png, "scale": sf,
            "umi_all": umi_all, "n_grid": int(len(barcodes)), "positions": pos}


def add_published(cells: pd.DataFrame, spec: dict, work: Path):
    """Annotations and latent spaces of a section's published Hi-C + RNA AnnData (None without one)."""
    if not spec["h5ad"]:
        return None
    src = RAW / spec["h5ad"]
    dst = work / src.name.removesuffix(".gz")
    if not dst.exists():
        with gzip.open(src, "rb") as f, open(dst, "wb") as o:
            while chunk := f.read(1 << 24):
                o.write(chunk)
    a = ad.read_h5ad(dst, backed="r")
    sec = spec["key"]
    ids = sec + ":" + pd.Index(a.obs_names.astype(str))
    miss = ids.difference(cells.index)
    assert len(miss) == 0, f"{sec}: {len(miss)} published spots are not in the in-tissue list"
    obs = a.obs.copy()
    obs.index = ids
    ann = pd.DataFrame(index=cells.index)
    ann.loc[ids, "in_published_analysis"] = True
    ann["in_published_analysis"] = ann["in_published_analysis"].fillna(False).astype(bool)
    rename = {"max_prop_cell_type": "cell_type", "confidence": "cell_type_confidence"}
    for c in obs.columns:
        if c not in rename and not c.startswith("cluster_"):
            continue
        v, new = obs[c], rename.get(c, c)
        if v.dtype.kind in "fiu":
            ann[new] = np.nan
            ann.loc[ids, new] = v.to_numpy(float)
        else:
            ann[new] = pd.Series(pd.NA, index=ann.index, dtype=object)
            ann.loc[ids, new] = v.astype(str).to_numpy()
    latents = {k: np.asarray(a.obsm[k], dtype=np.float32) for k in ("X_scVI", "X_fh", "X_concat") if k in a.obsm}
    abc = np.asarray(a.obsm["X_abcompartment"], dtype=np.float32) if "X_abcompartment" in a.obsm else None
    return {"ids": ids, "ann": ann, "latents": latents, "abcompartment": abc, "n_published": len(ids),
            "obsm": sorted(a.obsm.keys())}


# ---- RNA: normalisation, highly variable genes ------------------------------------------------

def log_normalise(counts: sp.csr_matrix) -> sp.csr_matrix:
    """log1p of counts per 10,000 (spots x genes)."""
    lib = np.asarray(counts.sum(1)).ravel()
    x = sp.diags(1e4 / np.maximum(lib, 1)).dot(counts).tocsr()
    x.data = np.log1p(x.data)
    return x


def highly_variable(x: sp.csr_matrix, min_frac: float = 0.01, n_bins: int = 20) -> np.ndarray:
    """Gene order by normalised dispersion (log var/mean within mean bins, z-scored), best first;
    genes detected in fewer than ``min_frac`` of the spots are left out (index -1 at the end)."""
    n = x.shape[0]
    mean = np.asarray(x.mean(0)).ravel()
    var = np.asarray(x.multiply(x).mean(0)).ravel() - mean ** 2
    frac = np.asarray((x > 0).sum(0)).ravel() / n
    ok = (frac >= min_frac) & (mean > 0)
    disp = np.full(len(mean), -np.inf)
    d = np.log(np.maximum(var[ok], 1e-12) / mean[ok])
    bins = pd.qcut(mean[ok], n_bins, labels=False, duplicates="drop")
    g = pd.DataFrame({"d": d, "b": bins})
    z = (g["d"] - g.groupby("b")["d"].transform("mean")) / g.groupby("b")["d"].transform("std").replace(0, np.nan)
    disp[ok] = z.fillna(0).to_numpy()
    return np.argsort(-disp)


def umap2d(latent: np.ndarray, seed: int = 0, n_neighbors: int = 15, min_dist: float = 0.3) -> np.ndarray:
    import umap

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return umap.UMAP(n_neighbors=n_neighbors, min_dist=min_dist, random_state=seed).fit_transform(latent)


# ---- one store -------------------------------------------------------------------------------

def build_store(name: str, work: Path, redo_umap: bool = True) -> Path:
    cfg = STORES[name]
    log(f"== {name}: {cfg['title']}")
    secs = [read_section(s, cfg["assembly"]) for s in cfg["sections"]]
    genes = secs[0]["genes"]
    for s in secs[1:]:
        assert s["genes"]["gene_id"].tolist() == genes["gene_id"].tolist(), "gene lists differ between sections"
    symbols = unique_symbols(genes)
    cells = pd.concat([s["cells"] for s in secs])
    counts = sp.vstack([s["counts"] for s in secs]).tocsr()
    n = len(cells)
    for s in secs:
        c = s["cells"]
        log(f"  {s['key']}: {len(c):,} in-tissue spots of {s['n_grid']:,}; RNA UMI median {c['rna_umi'].median():.0f}, "
            f"genes {c['rna_genes'].median():.0f}"
            + (f"; Hi-C contacts median {c['hic_contacts'].median():,.0f}" if "hic_contacts" in c else ""))

    # published annotations and latent spaces
    pub = {s["key"]: add_published(s["cells"], sp_, work) for s, sp_ in zip(secs, cfg["sections"])}
    ann = pd.concat([p["ann"] for p in pub.values() if p is not None]) if any(pub.values()) else None
    if ann is not None:
        ann = ann.reindex(cells.index)
        ann["in_published_analysis"] = ann["in_published_analysis"].fillna(False).astype(bool)
        for c in ann.columns:
            cells[c] = ann[c].to_numpy()
        log(f"  published AnnData for {', '.join(k for k, p in pub.items() if p)}: "
            f"annotations {[c for c in ann.columns if c != 'in_published_analysis']}")

    # RNA: log-CP10k, highly variable genes, expression columns for the browser
    xn = log_normalise(counts)
    order = highly_variable(xn)
    hvg = order[:N_HVG]
    want = [m.lower() for m in cfg["markers"].split()]
    sym_lower = pd.Series(np.arange(len(symbols)), index=[s.lower() for s in symbols])
    sym_lower = sym_lower[~sym_lower.index.duplicated()]
    marker_idx = [int(sym_lower[m]) for m in want if m in sym_lower.index]
    # expression columns: the most variable *named* genes (not Ensembl-id-only / predicted ones) and the markers
    named = ~symbols.str.match(r"^(ENS[A-Z]*G\d+|Gm\d+|[A-Z]{2}\d{6}\.\d+|LINC\d+|.*Rik|.*-AS\d)")
    top = [int(g) for g in order[:20 * N_RNA_COLUMNS] if named[g]][:N_RNA_COLUMNS]
    cols_idx = list(dict.fromkeys(top + marker_idx))
    expr = xn[:, cols_idx].toarray().astype(np.float32)
    cells = pd.concat([cells, pd.DataFrame(expr, index=cells.index, columns=[f"rna.{symbols[g]}" for g in cols_idx])], axis=1)
    log(f"  rna.<gene> columns: {len(cols_idx)} ({len(top)} most variable named genes + {len(marker_idx)} of {len(want)} markers)")

    for c in cells.columns:
        if not pd.api.types.is_numeric_dtype(cells[c]) and not pd.api.types.is_bool_dtype(cells[c]):
            cells[c] = cells[c].where(cells[c].notna(), None).astype("category")
    cells["section"] = cells["section"].astype("category")

    # locus axis: 500-kb bins of the main chromosomes
    chroms = cfg["chroms"]
    bins = pd.concat([pd.DataFrame({"chrom": c, "start": np.arange(-(-L // 500_000), dtype=np.int64) * 500_000})
                      for c, L in chroms.items()], ignore_index=True)
    bins["end"] = np.minimum(bins["start"] + 500_000, bins["chrom"].map(chroms).astype(np.int64))
    bins["resolution"] = 500_000
    bins["chrom"] = bins["chrom"].astype("category")

    stem = ROOT / f"hicrna_{name}"
    out = stem.with_name(stem.name + ".chromdata.zarr")
    empty = pd.DataFrame({c: pd.Series(dtype=t) for c, t in
                          [("chrom", str), ("start", np.int64), ("end", np.int64), ("trace_id", str), ("cell_id", str)]})
    mask_info = {}
    for s in secs:
        c = s["cells"]
        out_umi = float(s["umi_all"].drop(c["barcode"]).sum() / s["umi_all"].sum())
        mask_info[s["key"]] = {"grid_spots": s["n_grid"], "in_tissue": int(len(c)),
                               "rna_umi_outside_mask": round(out_umi, 4)}
    uns = {"genome_assembly": cfg["assembly"], "source": SOURCE, "title": cfg["title"],
           "doi": "10.1016/j.cell.2026.07.039", "geo": "GSE311199",
           "coordinate_status": "no 3-D coordinates: spots of a spatial barcode grid; Hi-C and RNA come from the same spots",
           "spot_mask": mask_info}
    cd = ChromData(np.zeros((0, 3)), empty, bins=bins, cells=cells, uns=uns)
    cd.set_cell_positions(cells[["grid_col", "grid_row"]].to_numpy(float), unit="spot", frame="tissue",
                          region_col="section", status="measured", y_axis="down",
                          source="tissue_positions_list.csv array_row; array_col mirrored to run with the image columns")
    cd.set_cell_positions(cells[["image_x", "image_y"]].to_numpy(float), key="image", unit="px", frame="tissue",
                          region_col="section", status="measured", y_axis="down",
                          source="tissue_positions_list.csv pxl_col / pxl_row, pixels of tissue_lowres_image.png "
                                 "(tissue_lowres_scalef = 1)")

    # images
    from PIL import Image
    import io

    img_dir = stem.with_name(stem.name + "_images")
    img_dir.mkdir(exist_ok=True)
    images = {}
    for s in secs:
        dst = img_dir / f"{s['key']}.png"
        dst.write_bytes(s["png"])
        w, h = Image.open(io.BytesIO(s["png"])).size
        images[s["key"]] = {"path": f"{img_dir.name}/{dst.name}", "format": "png", "positions": "image",
                            "region": s["key"], "extent": [0, w, 0, h], "kind": "tissue image (grayscale)",
                            "description": "tissue_lowres_image.png of the section (GEO): black outside the "
                                           "published in-tissue region; spot pixels are its pixels",
                            "scalefactors": s["scale"]}
    cd.uns["linked_images"] = images

    # linked RNA counts
    adata = ad.AnnData(X=counts, obs=cells[["section"]].copy(),
                       var=pd.DataFrame({"gene_id": genes["gene_id"].to_numpy(), "symbol": genes["symbol"].to_numpy()}, index=symbols))
    adata.obs.index.name = "cell_id"
    h5 = stem.with_name(stem.name + "_rna.h5ad")
    adata.write_h5ad(h5, compression="gzip")
    cd.uns["linked_anndata"] = {"path": h5.name, "format": "h5ad", "modality": "spatial RNA",
                                "description": "raw UMI counts (X) of every gene, one row per spot of cells",
                                "cell_axis": "obs index = cells index", "var_axis": "var index = gene symbol (gene_id: Ensembl id)"}
    log(f"  RNA: {adata.n_obs:,} spots x {adata.n_vars:,} genes -> {h5.name} ({h5.stat().st_size / 1e6:.0f} MB)")

    # embeddings: RNA of all the store's spots, and the published latent spaces of the sections that have them
    z = xn[:, hvg].toarray()
    z = (z - z.mean(0)) / np.where(z.std(0) > 0, z.std(0), 1)
    z = np.clip(z, -10, 10).astype(np.float32)
    t0 = time.time()
    embed_cells(cd, source="rna", matrix=z, normalization="none", methods=("pca", "umap"), n_pcs=30,
                features=f"the {N_HVG:,} most variable genes (log1p CP10k, z-score, clipped at 10) of all spots of the store; "
                         "no batch correction between sections")
    log(f"  rna_pca / rna_umap on {n:,} spots x {N_HVG} genes ({time.time() - t0:.0f} s)")
    names = {"X_scVI": ("published_scvi", "scVI latent"), "X_fh": ("published_xfh", "X_fh latent"),
             "X_concat": ("published_xconcat", "X_concat latent")}
    row = {cid: k for k, cid in enumerate(cells.index)}
    reg = dict(cd.uns.get("embeddings") or {})
    cellm = dict(cd.cellm)
    for latent_key, (key, label) in names.items():
        have = [(k, p) for k, p in pub.items() if p is not None and latent_key in p["latents"]]
        if not have:
            continue
        for k, p in have:
            t0 = time.time()
            e = umap2d(p["latents"][latent_key])
            arr = cellm.setdefault(f"{key}_umap", np.full((n, 2), np.nan, dtype=np.float32))
            arr[[row[i] for i in p["ids"]]] = e
            log(f"  {key}_umap: {k}, {len(e):,} spots, {p['latents'][latent_key].shape[1]}-D latent ({time.time() - t0:.0f} s)")
        reg[f"{key}_umap"] = {"method": "umap", "modality": "Published", "label": f"{label} UMAP (published)",
                              "axis_prefix": "UMAP", "source": f"UMAP (n_neighbors 15, min_dist 0.3) of obsm['{latent_key}'] of the "
                                                                 "published AnnData; sections without one are NaN"}
    cd.uns["embeddings"] = reg
    cd.cellm = cellm

    # single-spot A/B of the published AnnData: linked by link_spatial_hicrna_contacts.py (needs the bin layout)
    for k, p in pub.items():
        if p is not None and p["abcompartment"] is not None:
            np.save(work / f"{k}.abcompartment.npy", p["abcompartment"])
            pd.Series(p["ids"]).to_csv(work / f"{k}.abcompartment.ids.csv", index=False, header=False)
    cd.write(out)
    log(f"wrote {out.name}: {cd}")
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--stores", default=",".join(STORES))
    ap.add_argument("--work", type=Path, default=ROOT / "work", help="scratch folder (decompressed published AnnData, ssA/B matrices)")
    a = ap.parse_args()
    a.work.mkdir(parents=True, exist_ok=True)
    for name in a.stores.split(","):
        build_store(name, a.work)


if __name__ == "__main__":
    main()
