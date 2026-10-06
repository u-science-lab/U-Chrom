"""Build the dscHi-C store of the atlas (Wu et al. 2025, Cell Discov., doi:10.1038/s41421-025-00770-8).

dscHi-C is droplet-based single-cell Hi-C.  The store holds the mouse cortex at 3, 12 and 23 months (GEO
GSE285812: GSM8709626 / GSM8698919 / GSM8709603), contacts only (no 3-D coordinates):

  dschic2025/dschic_aging_cortex.chromdata.zarr

It links, next to it: ``<stem>_cells_1Mb.scool`` (one map per cell, 1 Mb) and ``<stem>_bulk.mcool`` (all cells
merged, 50 kb - 1 Mb, ICE-balanced).  Cell types are the authors' (``main_celltype`` / ``sub_celltype`` of the GEO
metadata); cell ids are ``<age>m_<barcode>`` (barcodes repeat between ages).  Embedding: scHiCluster of the 1 Mb
maps.

Not used: the dscHi-C-multiome deposit of the 3-month cortex (GSE285233, GSM8698924 / GSM8698925).  Its contact
file holds 15 M contacts on barcodes that match none of the 10,087 RNA cells (2,106 shared barcode sequences,
contact counts uncorrelated with the metadata's, which sum to 88 M; neither file uses a 10x ARC / ATAC
whitelist), so contacts and RNA cannot be paired.

Input: ``python -m uchrom.datasets fetch dschic2025_aging``.

Usage::

    python apps/atlas/recipes/build_dschic2025.py
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sc_hic_common import ContactBinner, balance_mcool, chromsizes, empty_spots, log, stream_pairs  # noqa: E402
from uchrom.datasets import data_dir

HERE = Path(__file__).resolve().parent
DATA = data_dir()                       # $UCHROM_DATA, else ~/.cache/uchrom
OUT = DATA / "dschic2025"
RAW = OUT / "raw"
SOURCE = "Wu et al. 2025, Cell Discov. (doi:10.1038/s41421-025-00770-8)"

SAMPLES = {
    "aging": {"stem": "dschic_aging_cortex", "geo": "GEO GSE285812",
              "parts": [(f"{m} months", RAW / "GSE285812" / f"{gsm}_b{m}-month-BC-dscHiC.contacts.pairs.gz",
                         RAW / "GSE285812" / f"{gsm}_b{m}-month-BC-dscHiC.metadata.txt.gz")
                        for gsm, m in (("GSM8709626", 3), ("GSM8698919", 12), ("GSM8709603", 23))]},
}


def load_cells(spec) -> pd.DataFrame:
    """Cells of every part; cell_id = ``<age>m_<barcode>`` when there are several parts (barcodes repeat)."""
    frames = []
    for age, _, meta in spec["parts"]:
        m = pd.read_csv(meta, sep="\t")
        m["age"] = age
        m["barcode"] = m["cellbarcode"].astype(str)
        m.index = (m["barcode"] if len(spec["parts"]) == 1 else age.split()[0] + "m_" + m["barcode"]).rename("cell_id")
        frames.append(m)
    m = pd.concat(frames)
    cells = pd.DataFrame(index=m.index)
    cells["age"] = pd.Categorical(m["age"], categories=[p[0] for p in spec["parts"]])
    cells["cell_type"] = m["main_celltype"].astype(str).str.replace("_", " ")
    cells["subtype"] = m["sub_celltype"].astype(str)
    cells["barcode"] = m["barcode"]
    for src, dst in (("readsN", "n_reads"), ("contactsN", "n_contacts_published"), ("Interchromosomal", "frac_trans"),
                     ("Intra_le20kb", "frac_cis_le20kb"), ("Intra_ge20kb", "frac_cis_ge20kb"),
                     ("Mitotic_band", "frac_mitotic_band"), ("nCount_RNA", "n_counts_rna"), ("nFeature_RNA", "n_genes_rna")):
        if src in m:
            cells[dst] = m[src].to_numpy()
    return cells


def bin_contacts(spec, cells: pd.DataFrame, stem: Path):
    sizes = chromsizes(spec["parts"][0][1])
    binner = ContactBinner(sizes, cells.index, stem.parent / f".{stem.name}_bins")
    for age, pairs, _ in spec["parts"]:
        prefix = "" if len(spec["parts"]) == 1 else age.split()[0] + "m_"
        t0, n = time.time(), 0
        for df in stream_pairs(pairs, {"cell": 0, "chr1": 1, "pos1": 2, "chr2": 3, "pos2": 4}):
            if prefix:
                df["cell"] = df["cell"].cat.rename_categories(lambda c: prefix + c)
            binner.add_frame(df)
            n += len(df)
            if n % 50_000_000 < len(df):
                log(f"  {age}: {n:,} contacts ({n / (time.time() - t0) / 1e6:.1f} M/s)")
        log(f"  {age}: {n:,} contacts read in {time.time() - t0:.0f} s")
    binner.close()
    log(f"contacts: {binner.n_in:,} read, {binner.n_kept:,} of the {len(cells):,} cells on kept chromosomes")
    scool = stem.with_name(stem.name + "_cells_1Mb.scool")
    names = binner.write_scool(scool)
    log(f"wrote {scool.name}: {len(names):,} cells")
    mcool = binner.write_mcool(stem.with_name(stem.name + "_bulk.mcool"))
    log(f"wrote {mcool.name}")
    per_cell = pd.Series(binner.per_cell, index=binner.cells)
    binner.cleanup()
    return scool, mcool, per_cell


def add_hic_embedding(cd, scool: Path) -> None:
    from uchrom.emb import embed_cells, scool_cell_features

    t0 = time.time()
    chroms = [c for c in chromsizes(None) if c != "chrY"]
    feats, cols, depth = scool_cell_features(str(scool), [str(c) for c in cd.cells.index], chroms=chroms)
    log(f"scHiCluster features {feats.shape} in {time.time() - t0:.0f} s")
    if "n_contacts" not in cd.cells:
        cd.cells["n_contacts"] = np.asarray(depth, dtype=np.int64)
    embed_cells(cd, source="hic", matrix=feats, normalization="none", methods=("pca", "umap"), n_pcs=30,
                features="scHiCluster (convolution + random walk + binarise) of the per-cell 1 Mb maps")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("sample", nargs="?", default="aging", choices=sorted(SAMPLES))
    ap.add_argument("--reuse-contacts", action="store_true", help="keep the existing .scool / .mcool")
    ap.add_argument("--no-hic-embedding", action="store_true")
    args = ap.parse_args()

    from uchrom import ChromData

    spec = SAMPLES[args.sample]
    stem = OUT / spec["stem"]
    cells = load_cells(spec)
    log(f"{args.sample}: {len(cells):,} cells; {cells['cell_type'].value_counts().to_dict()}")
    scool = stem.with_name(stem.name + "_cells_1Mb.scool")
    mcool = stem.with_name(stem.name + "_bulk.mcool")
    if not (args.reuse_contacts and scool.exists() and mcool.exists()):
        scool, mcool, per_cell = bin_contacts(spec, cells, stem)
        cells["n_contacts"] = per_cell.reindex(cells.index).fillna(0).astype(np.int64).to_numpy()
    else:
        log(f"balanced {balance_mcool(mcool)} of {mcool.name}")
    cd = ChromData(np.zeros((0, 3)), empty_spots(), cells=cells,
                   uns={"genome_assembly": "mm10", "source": f"{SOURCE}; {spec['geo']}",
                        "coordinate_status": "no 3-D coordinates: contacts only"})
    cd.link_cool(mcool.name, key="bulk", label="All cells (merged)")
    cd.link_scool(scool.name, key="per_cell", label="Per cell", cell_name="cell_id", genome_assembly="mm10",
                  bin_size=1_000_000)
    if not args.no_hic_embedding:
        add_hic_embedding(cd, scool)
    out = stem.with_name(stem.name + ".chromdata.zarr")
    cd.write(out)
    log(f"wrote {out}: {cd}")


if __name__ == "__main__":
    main()
