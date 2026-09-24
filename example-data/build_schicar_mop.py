"""Build a U-Chrom dataset from the public scHiCAR mouse-brain data (GSE305439).

scHiCAR (Wei et al. 2026, Nat Biotechnol) profiles RNA, ATAC and chromatin
contacts in the same cells — but no 3-D coordinates.  This script turns the
GEO supplementary files into:

  schicar_mop/schicar_mop.h5cd          ChromData without 3-D spots:
                                          cells  (cell type, QC, 500 HVG counts as rna.<gene>)
                                          cellm  (paper_umap, rna_pca/_tsne/_umap)
                                          links  (the contact maps below)
  schicar_mop/contacts_all.mcool        all cells merged, 250 kb … 2 Mb
  schicar_mop/contacts_<type>.cool      pseudo-bulk per cell type, 500 kb
  schicar_mop/contacts_cells_1Mb.scool  one contact map per cell, 1 Mb

Inputs (``python example-data/download_data.py --schicar_rna --schicar_dna``):
example-data/schicar_mop/raw/GSE305439/{RNA matrix/barcodes/features,
metadata, DNA.dedup.pairs.gz}.  Chromosome sizes: UCSC mm10 (via cooler).

Usage::

    python example-data/build_schicar_mop.py [--n-hvg 500] [--chunk 10000000]
"""

from __future__ import annotations

import argparse
import gzip
import re
import time
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
RAW = HERE / "schicar_mop" / "raw" / "GSE305439"
OUT = HERE / "schicar_mop"
CHROMS = [f"chr{i}" for i in range(1, 20)] + ["chrX", "chrY"]


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def load_rna(n_hvg: int):
    """Cells (metadata) + top-n_hvg genes (log-normalised variance) as counts."""
    import scipy.io
    import scipy.sparse as sp

    meta = pd.read_csv(RAW / "GSE305439_mouse_brain_scHiCAR_1_RNA_metadata.txt.gz", sep="\t")
    barcodes = pd.read_csv(RAW / "GSE305439_RNA.barcodes.tsv.gz", header=None)[0].astype(str)
    features = pd.read_csv(RAW / "GSE305439_RNA.features.tsv.gz", sep="\t", header=None)
    genes = features[1].astype(str)
    mat = sp.csc_matrix(scipy.io.mmread(RAW / "GSE305439_RNA.matrix.mtx.gz"))  # genes × cells
    log(f"RNA: {mat.shape[0]} genes × {mat.shape[1]} cells, {mat.nnz:,} non-zeros")

    meta = meta.set_index("RNAbarcode").loc[barcodes]  # align to matrix columns
    x = mat.T.tocsr().astype(np.float64)               # cells × genes
    totals = np.asarray(x.sum(axis=1)).ravel()
    norm = sp.diags(1e4 / np.maximum(totals, 1)) @ x
    norm.data = np.log1p(norm.data)
    frac = np.asarray((x > 0).mean(axis=0)).ravel()
    mean = np.asarray(norm.mean(axis=0)).ravel()
    var = np.asarray(norm.multiply(norm).mean(axis=0)).ravel() - mean**2
    keep = frac >= 0.01
    disp = np.where(keep, var / np.maximum(mean, 1e-9), -np.inf)
    hvg = np.argsort(-disp)[:n_hvg]
    hvg = hvg[np.isfinite(disp[hvg])]
    names = genes.iloc[hvg].tolist()
    log(f"selected {len(names)} HVGs (≥1% cells; top dispersion), e.g. {names[:8]}")

    cells = pd.DataFrame(index=pd.Index(barcodes.tolist(), name="cell_id"))
    cells["cell_type"] = meta["celltype"].astype(str).values
    cells["dna_barcode"] = meta["DNAbarcode"].astype(str).values
    cells["n_counts_rna"] = meta["nCount_RNA"].values
    cells["n_genes_rna"] = meta["nFeature_RNA"].values
    counts = x[:, hvg].toarray()
    cols, seen = [], set()
    for j, g in enumerate(names):
        cols.append(f"rna.{g}" if g not in seen else f"rna.{g}_{j}")
        seen.add(g)
    cells = pd.concat([cells, pd.DataFrame(counts, index=cells.index, columns=cols)], axis=1)
    umap = meta[["UMAP1", "UMAP2"]].to_numpy(dtype=np.float64)
    return cells, umap


def bin_table(chromsizes: pd.Series, res: int) -> pd.DataFrame:
    rows = []
    for c in CHROMS:
        n = int(np.ceil(chromsizes[c] / res))
        starts = np.arange(n, dtype=np.int64) * res
        rows.append(pd.DataFrame({"chrom": c, "start": starts,
                                  "end": np.minimum(starts + res, chromsizes[c])}))
    return pd.concat(rows, ignore_index=True)


def build_contacts(cells: pd.DataFrame, chromsizes: pd.Series, chunk: int):
    """Stream the pairs once; accumulate per-cell 1 Mb, per-type 500 kb and
    all-cell 250 kb contact counts (upper triangle, bin1 <= bin2)."""
    res = {"cell": 1_000_000, "type": 500_000, "all": 250_000}
    offsets = {}
    for k, r in res.items():
        n = np.ceil(chromsizes[CHROMS] / r).astype(np.int64)
        offsets[k] = (dict(zip(CHROMS, np.r_[0, np.cumsum(n.values)[:-1]])), int(n.sum()))
    dna_to_cell = pd.Series(np.arange(len(cells)), index=cells["dna_barcode"].values)
    types = pd.Categorical(cells["cell_type"])
    cell_type_code = types.codes.astype(np.int64)

    acc = {"cell": [], "type": [], "all": []}
    reader = pd.read_csv(RAW / "GSE305439_DNA.dedup.pairs.gz", sep="\t", header=None,
                         usecols=[0, 1, 2, 3, 4], names=["bc", "c1", "p1", "c2", "p2"],
                         dtype={"bc": str, "c1": str, "p1": np.int64, "c2": str, "p2": np.int64},
                         chunksize=chunk)
    n_total = n_used = 0
    for i, df in enumerate(reader):
        n_total += len(df)
        cell = df["bc"].map(dna_to_cell)
        df = df[cell.notna() & df["c1"].isin(CHROMS) & df["c2"].isin(CHROMS)]
        cell = cell[df.index].astype(np.int64).to_numpy()
        n_used += len(df)
        for k, r in res.items():
            off, nb = offsets[k]
            b1 = df["c1"].map(off).to_numpy() + df["p1"].to_numpy() // r
            b2 = df["c2"].map(off).to_numpy() + df["p2"].to_numpy() // r
            lo, hi = np.minimum(b1, b2), np.maximum(b1, b2)
            if k == "all":
                key = lo * nb + hi
            else:
                group = cell if k == "cell" else cell_type_code[cell]
                key = (group * nb + lo) * nb + hi
            u, c = np.unique(key, return_counts=True)
            acc[k].append(pd.Series(c, index=u))
        if i % 3 == 0:
            log(f"  pairs read {n_total:,} (kept {n_used:,})")
    log(f"pairs: {n_total:,} total, {n_used:,} from the {len(cells)} RNA cells on {CHROMS[0]}…{CHROMS[-1]}")
    merged = {k: pd.concat(v).groupby(level=0).sum() for k, v in acc.items()}
    return merged, offsets, res, types


def write_contacts(merged, offsets, res, types, cells, chromsizes) -> dict:
    import cooler

    OUT.mkdir(parents=True, exist_ok=True)
    written = {}

    def pixels(keys: np.ndarray, counts: np.ndarray, nb: int) -> pd.DataFrame:
        return pd.DataFrame({"bin1_id": keys // nb, "bin2_id": keys % nb, "count": counts.astype(np.int64)})

    # all cells → cool at 250 kb, then zoomify to an mcool
    _, nb = offsets["all"]
    s = merged["all"]
    tmp = OUT / "contacts_all_250kb.cool"
    cooler.create_cooler(str(tmp), bin_table(chromsizes, res["all"]),
                         pixels(s.index.to_numpy(), s.to_numpy(), nb), ordered=True, assembly="mm10")
    mcool = OUT / "contacts_all.mcool"
    cooler.zoomify_cooler(str(tmp), str(mcool), [250_000, 500_000, 1_000_000, 2_000_000], chunksize=10_000_000)
    tmp.unlink()
    written["all"] = mcool
    log(f"wrote {mcool.name} ({s.sum():,} contacts)")

    # per cell type → cool at 500 kb
    _, nb = offsets["type"]
    s = merged["type"]
    keys = s.index.to_numpy()
    group = keys // (nb * nb)
    for code, name in enumerate(types.categories):
        sel = group == code
        if not sel.any():
            continue
        safe = re.sub(r"[^A-Za-z0-9]+", "_", name).strip("_")
        path = OUT / f"contacts_{safe}.cool"
        cooler.create_cooler(str(path), bin_table(chromsizes, res["type"]),
                             pixels(keys[sel] % (nb * nb), s.to_numpy()[sel], nb), ordered=True, assembly="mm10")
        written[f"type:{name}"] = path
    log(f"wrote {len(types.categories)} pseudo-bulk cell-type cools")

    # per cell → scool at 1 Mb
    _, nb = offsets["cell"]
    s = merged["cell"]
    keys = s.index.to_numpy()
    cell_idx = keys // (nb * nb)
    order = np.argsort(cell_idx, kind="stable")
    keys, vals, cell_idx = keys[order], s.to_numpy()[order], cell_idx[order]
    bounds = np.searchsorted(cell_idx, np.arange(len(cells) + 1))
    cell_pixels = {}
    for ci, name in enumerate(cells.index):
        lo, hi = bounds[ci], bounds[ci + 1]
        if hi > lo:
            cell_pixels[name] = pixels(keys[lo:hi] % (nb * nb), vals[lo:hi], nb)
    scool = OUT / "contacts_cells_1Mb.scool"
    cooler.create_scool(str(scool), bin_table(chromsizes, res["cell"]), cell_pixels, ordered=True)
    written["cells"] = scool
    log(f"wrote {scool.name} ({len(cell_pixels)} cells)")
    return written


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--n-hvg", type=int, default=500)
    ap.add_argument("--chunk", type=int, default=10_000_000)
    args = ap.parse_args()

    import cooler.util

    from uchrom import ChromData
    from uchrom.emb import embed_cells

    chromsizes = cooler.util.fetch_chromsizes("mm10")
    cells, paper_umap = load_rna(args.n_hvg)
    merged, offsets, res, types = build_contacts(cells, chromsizes, args.chunk)
    files = write_contacts(merged, offsets, res, types, cells, chromsizes)

    empty = pd.DataFrame({c: pd.Series(dtype=t) for c, t in
                          [("chrom", str), ("start", np.int64), ("end", np.int64), ("trace_id", str), ("cell_id", str)]})
    cd = ChromData(np.zeros((0, 3)), empty, cells=cells, cellm={"paper_umap": paper_umap},
                   uns={"genome_assembly": "mm10", "source": "GEO GSE305439 (scHiCAR, Wei et al. 2026)",
                        "coordinate_status": "no 3-D coordinates: contacts only",
                        "embeddings": {"paper_umap": {"method": "umap", "label": "Paper UMAP (RNA)",
                                                      "source": "GSE305439 metadata", "axis_prefix": "UMAP"}}})
    embed_cells(cd, source="rna", library_size=True)
    # link paths relative to the .h5cd (same folder) so the dataset can move
    cd.link_cool(files["all"].name, key="all_cells", label="All cells (merged)")
    for k, path in files.items():
        if k.startswith("type:"):
            cd.link_cool(path.name, key=f"type_{path.stem.removeprefix('contacts_')}", label=f"{k[5:]} (pseudo-bulk)")
    cd.link_scool(files["cells"].name, key="per_cell", cell_name="cell_id (RNA barcode)",
                  barcode_source="DNAbarcode", genome_assembly="mm10", bin_size=1_000_000)
    out = OUT / "schicar_mop.h5cd"
    cd.write(out)
    log(f"wrote {out}: {cd}")


if __name__ == "__main__":
    main()
