"""Build the HiRES stores of the atlas (Liu et al. 2023, Science, doi:10.1126/science.adg3797; GEO GSE223917).

HiRES profiles chromatin contacts and RNA of the same single cells; the authors deposit, per cell, the contact
pairs and a diploid 3-D structure (20 kb particles, maternal / paternal copies, hickit).  Two stores:

  hires2023/hires_embryo.chromdata.zarr   mouse embryo E7.0 - E9.5, 7,469 cells (GSE223917_HiRES_emb_metadata)
  hires2023/hires_brain.chromdata.zarr    mouse brain, 399 cells (GSE223917_HiRES_brain_metadata)

Each store has:

* 3-D coordinates: the authors' 20 kb structures coarse-grained to 200 kb (mean of the particles in each
  200 kb bin of each copy); one trace per cell, chromosome and copy (``<cell>_<chrom>_<mat|pat>``).
* cells: the authors' metadata (stage, cell type, cell-cycle phase, QC, RMSD of the structure replicates).
* links, next to the store: ``<stem>_cells_1Mb.scool`` (one map per cell, 1 Mb, from the cell's pairs),
  ``<stem>_bulk.mcool`` (all cells merged, 50 kb - 1 Mb, ICE-balanced), ``<stem>_rna.h5ad`` (the deposited UMI
  counts of every gene; fractional where reads were split between genes).
* embeddings: RNA PCA / UMAP (2,000 most variable genes) and scHiCluster on the 1 Mb maps.

Inputs: ``python example-data/download_data.py --hires2023_meta --hires2023`` (75 GB, per-cell files).

Usage::

    python example-data/build_hires2023.py embryo [--workers 8]
    python example-data/build_hires2023.py brain
"""

from __future__ import annotations

import argparse
import re
import sys
import time
from multiprocessing import Pool
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sc_hic_common import (ContactBinner, balance_mcool, bin_table, chromsizes, empty_spots, hvg_zscores,  # noqa: E402
                           log, rna_h5ad)

HERE = Path(__file__).resolve().parent
OUT = HERE / "hires2023"
RAW = OUT / "raw" / "GSE223917"
CELLS = RAW / "cells"
SOURCE = "Liu et al. 2023, Science (doi:10.1126/science.adg3797); GEO GSE223917"
RES_3D = 200_000

SAMPLES = {
    "embryo": {"stem": "hires_embryo", "meta": "GSE223917_HiRES_emb_metadata.xlsx",
               "rna": "GSE223917_HiRES_emb.rna.umicount.tsv.gz", "type_col": "Celltype"},
    "brain": {"stem": "hires_brain", "meta": "GSE223917_HiRES_brain_metadata.xlsx",
              "rna": "GSE223917_HiRES_brain.rna.umicount.tsv.gz", "type_col": "Cell type"},
}
STAGES = {"E70": "E7.0", "E75": "E7.5", "E80": "E8.0", "E85": "E8.5", "E95": "E9.5", "E105": "E10.5", "E115": "E11.5"}


def cell_files() -> dict:
    """cell name -> (pairs file, 3dg file) of the downloaded per-cell files."""
    files: dict = {}
    for p in CELLS.glob("GSM*"):
        m = re.match(r"GSM\d+_(.+?)\.(pairs\.gz|20k(?:\.0\.clean)?\.3dg\.txt\.gz)$", p.name)
        if m:
            files.setdefault(m.group(1), [None, None])[0 if m.group(2) == "pairs.gz" else 1] = p
    return files


def load_cells(spec) -> pd.DataFrame:
    m = pd.read_excel(RAW / spec["meta"])
    cells = pd.DataFrame(index=pd.Index(m["Cellname"].astype(str), name="cell_id"))
    if "Stage" in m:
        order = [v for v in STAGES.values()]
        cells["stage"] = pd.Categorical(m["Stage"].astype(str).map(lambda s: STAGES.get(s, s)).to_numpy(),
                                        categories=[s for s in order if s in set(m["Stage"].map(STAGES))])
    cells["cell_type"] = m[spec["type_col"]].astype(str).to_numpy()
    if "Cellcycle phase" in m:
        cells["cell_cycle"] = m["Cellcycle phase"].astype(str).to_numpy()
    for src, dst in (("Clean3 contacts", "n_contacts_published"), ("Clean3 inter-contacts", "n_trans_published"),
                     ("Genes number", "n_genes_rna"), ("UMI counts", "n_counts_rna"), ("near%", "frac_near"),
                     ("mitotic%", "frac_mitotic"), ("repli score", "repli_score"), ("G1S.Score", "g1s_score"),
                     ("G2M.Score", "g2m_score"), ("RMSD 20k", "rmsd_20k"), ("CDPS cluster", "cdps_cluster"),
                     ("y/x", "y_over_x")):
        if src in m:
            cells[dst] = m[src].to_numpy()
    return cells


# -- workers -----------------------------------------------------------------------------------------------------

_KM = None


def _init(km):
    global _KM
    _KM = km


def _bin_pairs(args):
    """(cell index, cell keys, bulk keys, n contacts) of one cell's pairs file."""
    ci, path = args
    df = pd.read_csv(path, sep="\t", comment="#", header=None, usecols=[1, 2, 3, 4],
                     names=["chr1", "pos1", "chr2", "pos2"], dtype={"chr1": str, "chr2": str})
    ck, bk = _KM.keys(_KM.chrom_codes(df["chr1"]), df["pos1"].to_numpy(), _KM.chrom_codes(df["chr2"]), df["pos2"].to_numpy())
    return ci, ck, bk, len(df)


def _coarse_3dg(args):
    """One cell's structure at RES_3D: spots (chrom, start, end, trace_id, cell_id, copy) + xyz."""
    cell, path, sizes = args
    df = pd.read_csv(path, sep="\t", header=None, names=["name", "pos", "x", "y", "z"], dtype={"name": str})
    parts = df["name"].str.extract(r"^(chr[^()]+)\((mat|pat)\)$")
    df["chrom"], df["copy"] = parts[0], parts[1]
    df = df[df["chrom"].isin(sizes)]
    df["bin"] = df["pos"].to_numpy() // RES_3D
    g = df.groupby(["chrom", "copy", "bin"], sort=False)[["x", "y", "z"]].mean().reset_index()
    order = {c: i for i, c in enumerate(sizes)}
    g = g.iloc[np.lexsort((g["bin"].to_numpy(), g["copy"].to_numpy(), g["chrom"].map(order).to_numpy()))]
    start = g["bin"].to_numpy(np.int64) * RES_3D
    end = np.minimum(start + RES_3D, g["chrom"].map(sizes).to_numpy())
    spots = pd.DataFrame({"chrom": g["chrom"].to_numpy(), "start": start, "end": end,
                          "trace_id": cell + "_" + g["chrom"] + "_" + g["copy"], "cell_id": cell,
                          "copy": g["copy"].to_numpy()})
    return spots, g[["x", "y", "z"]].to_numpy(np.float32)


# -- steps -------------------------------------------------------------------------------------------------------

def bin_contacts(cells, files, stem: Path, workers: int):
    sizes = chromsizes(files[cells.index[0]][0])
    binner = ContactBinner(sizes, cells.index, stem.parent / f".{stem.name}_bins")
    jobs = [(int(binner.cell_index.get_loc(c)), files[c][0]) for c in cells.index if files.get(c, [None])[0]]
    t0 = time.time()
    with Pool(workers, initializer=_init, initargs=(binner.keymaker(),)) as pool:
        for k, (ci, ck, bk, n) in enumerate(pool.imap_unordered(_bin_pairs, jobs, chunksize=16)):
            binner.add_keys(ci, ck, bk, n)
            if (k + 1) % 1000 == 0:
                log(f"  contacts of {k + 1:,} / {len(jobs):,} cells ({time.time() - t0:.0f} s)")
    binner.close()
    log(f"contacts: {binner.n_in:,} read, {binner.n_kept:,} on kept chromosomes, {len(jobs):,} cells")
    scool = stem.with_name(stem.name + "_cells_1Mb.scool")
    names = binner.write_scool(scool)
    log(f"wrote {scool.name}: {len(names):,} cells")
    mcool = binner.write_mcool(stem.with_name(stem.name + "_bulk.mcool"))
    log(f"wrote {mcool.name}")
    per_cell = pd.Series(binner.per_cell, index=binner.cells)
    binner.cleanup()
    return scool, mcool, per_cell, sizes


def load_rna(spec, cells: pd.DataFrame):
    import scipy.sparse as sp

    blocks, genes = [], []
    for df in pd.read_csv(RAW / spec["rna"], sep="\t", index_col=0, chunksize=2000):
        df = df.reindex(columns=cells.index)
        genes.extend(df.index.astype(str))
        blocks.append(sp.csr_matrix(df.fillna(0).to_numpy(np.float32)))
    x = sp.vstack(blocks).T.tocsr()                           # cells x genes
    return x, pd.DataFrame(index=pd.Index(genes, name="gene"))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("sample", choices=sorted(SAMPLES))
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--reuse-contacts", action="store_true")
    ap.add_argument("--no-hic-embedding", action="store_true")
    ap.add_argument("--test", type=int, default=0, help="only the first N downloaded cells, into <stem>_test")
    args = ap.parse_args()

    from uchrom import ChromData
    from uchrom.emb import embed_cells, scool_cell_features

    spec = SAMPLES[args.sample]
    stem = OUT / spec["stem"]
    cells = load_cells(spec)
    files = cell_files()
    have = [c for c in cells.index if files.get(c) and all(files[c])]
    if args.test:
        cells = cells.loc[have[:args.test]]
        have = list(cells.index)
        stem = stem.with_name(stem.name + "_test")
    log(f"{args.sample}: {len(cells):,} cells in the metadata, {len(have):,} with pairs + structure downloaded")
    if len(have) < len(cells):
        missing = [c for c in cells.index if c not in set(have)]
        raise SystemExit(f"{len(missing)} cells without both files (e.g. {missing[:3]}): finish the download")

    scool = stem.with_name(stem.name + "_cells_1Mb.scool")
    mcool = stem.with_name(stem.name + "_bulk.mcool")
    if args.reuse_contacts and scool.exists() and mcool.exists():
        sizes = chromsizes(files[cells.index[0]][0])
        log(f"balanced {balance_mcool(mcool)} of {mcool.name}")
    else:
        scool, mcool, per_cell, sizes = bin_contacts(cells, files, stem, args.workers)
        cells["n_contacts"] = per_cell.reindex(cells.index).fillna(0).astype(np.int64).to_numpy()

    # small tables + embeddings on a cells-only object
    meta = ChromData(np.zeros((0, 3)), empty_spots(), cells=cells)
    counts, genes = load_rna(spec, cells)
    rna = rna_h5ad(counts, cells.index, genes, stem.with_name(stem.name + "_rna.h5ad"),
                   description="HiRES RNA: deposited UMI counts (X) of every gene, one row per cell of cells; "
                               "fractional values are reads split between genes")
    log(f"RNA: {counts.shape[0]:,} cells x {counts.shape[1]:,} genes")
    z, hvg = hvg_zscores(counts)
    embed_cells(meta, source="rna", matrix=z, normalization="none", methods=("pca", "umap"), n_pcs=30,
                features=f"the {len(hvg):,} most variable genes (log1p CP10k, z-score, clipped at 10)")
    if not args.no_hic_embedding:
        t0 = time.time()
        feats, _, depth = scool_cell_features(str(scool), list(cells.index), chroms=[c for c in sizes if c != "chrY"])
        if "n_contacts" not in meta.cells:
            meta.cells["n_contacts"] = np.asarray(depth, dtype=np.int64)
        embed_cells(meta, source="hic", matrix=feats, normalization="none", methods=("pca", "umap"), n_pcs=30,
                    features="scHiCluster (convolution + random walk + binarise) of the per-cell 1 Mb maps")
        log(f"Hi-C embedding in {time.time() - t0:.0f} s")
    meta.link_cool(mcool.name, key="bulk", label="All cells (merged)")
    meta.link_scool(scool.name, key="per_cell", label="Per cell", cell_name="cell_id", genome_assembly="mm10",
                    bin_size=1_000_000)
    uns = dict(meta.uns)
    uns.update({"genome_assembly": "mm10", "source": SOURCE, "linked_anndata": rna, "xyz_unit": "particle radius",
                "coordinate_status": f"the authors' 20 kb hickit structures (embryo: replicate 0, cleaned, "
                                     f"``*.20k.0.clean.3dg``; brain: ``*.20k.3dg``), coarse-grained to "
                                     f"{RES_3D // 1000} kb by averaging the particles of each bin of each copy"})

    # 3-D coordinates, streamed cell by cell
    out = stem.with_name(stem.name + ".chromdata.zarr")
    bins = bin_table(sizes, RES_3D)
    traces = []
    t0 = time.time()
    with Pool(args.workers) as pool, ChromData.writer(out, bins=bins, coord_dtype="float32",
                                                      memory_budget="8GB") as w:
        jobs = [(c, files[c][1], sizes) for c in cells.index]
        batch_s, batch_x = [], []
        for k, (spots, xyz) in enumerate(pool.imap(_coarse_3dg, jobs, chunksize=8)):
            batch_s.append(spots)
            batch_x.append(xyz)
            t = spots.drop_duplicates("trace_id")[["trace_id", "cell_id", "chrom", "copy"]]
            traces.append(t)
            if len(batch_s) == 200 or k == len(jobs) - 1:
                w.append(coords=np.concatenate(batch_x), spots=pd.concat(batch_s, ignore_index=True))
                batch_s, batch_x = [], []
                log(f"  structures of {k + 1:,} / {len(jobs):,} cells ({time.time() - t0:.0f} s)")
        traces = pd.concat(traces, ignore_index=True).set_index("trace_id")
        w.finish(cells=meta.cells, cellm=dict(meta.cellm), traces=traces, uns=uns)
    log(f"wrote {out}")


if __name__ == "__main__":
    main()
