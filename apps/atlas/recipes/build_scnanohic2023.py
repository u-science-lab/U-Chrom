"""scNanoHi-C (Li et al. 2023, Nat Methods 20:1493; GEO GSE217189): multi-way contacts of single GM12878 cells read
as nanopore concatemers -> an atlas store with every cell's reads as clusters (``ChromData.clusters``) and maps of
the authors' contacts.

``GSM6706395_GM12878_high_clean_parquet.tar.gz`` (``python -m uchrom.datasets fetch li2023_scnanohic``) holds one
parquet table per cell (``GM12878_high_MboI_<barcode>_GRCh38_PG.contacts.clean.parquet``, GRCh38): one row per
contact the authors kept, a pair of alignments of one read (``align1_*`` / ``align2_*``: chrom, start, end,
haplotype -1 / 1 / 2) with the read (``read_idx``) and whether the two are adjacent in it (``contact_is_direct``).

The store keeps, per cell, every read as a cluster of its alignments that take part in a kept contact
(``clusters["scnanohic"]``: fragments = the alignments, member column ``haplotype``); the maps are the authors'
contacts (direct and indirect, the rows of the tables): per cell at 1 Mb (``_cells_1Mb.scool``, linked ``per_cell``)
and all cells (``_bulk.mcool``, 50 kb - 1 Mb, ICE-balanced, linked ``bulk``), embedded in the store; a scHiCluster
embedding of the per-cell maps and its Leiden clusters.  Usage::

    python apps/atlas/recipes/build_scnanohic2023.py [--workers 8]
"""

from __future__ import annotations

import argparse
import io
import re
import sys
import tarfile
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sc_hic_common import HG38, ContactBinner, balance_mcool, chromsizes, empty_spots, log  # noqa: E402

TAR = "GSM6706395_GM12878_high_clean_parquet.tar.gz"
COLS = ["read_idx", "contact_is_direct"] + [f"align{k}_{c}" for k in (1, 2)
                                             for c in ("align_idx", "chrom", "start", "end", "haplotype")]


def read_cells(path: Path):
    """{cell: contact table} of every parquet member of the tarball."""
    import pyarrow.parquet as pq
    out = {}
    with tarfile.open(path) as t:
        for mem in t:
            m = re.search(r"_MboI_(\w+?)_GRCh38_PG\.contacts\.clean\.parquet$", mem.name)
            if mem.isfile() and m:
                out[m[1]] = pq.read_table(io.BytesIO(t.extractfile(mem).read()), columns=COLS).to_pandas()
    return dict(sorted(out.items()))


def fragments(cell: str, df: pd.DataFrame) -> pd.DataFrame:
    """The alignments of a cell's reads, once each (a read's cluster)."""
    parts = [df[["read_idx"] + [f"align{k}_{c}" for c in ("align_idx", "chrom", "start", "end", "haplotype")]]
             .set_axis(["read", "align", "chrom", "start", "end", "haplotype"], axis=1) for k in (1, 2)]
    f = pd.concat(parts, ignore_index=True).drop_duplicates(["read", "align"])
    f["chrom"] = f["chrom"].astype(str)
    f["cluster"] = cell + ":" + f["read"].astype(str)
    f["cell"] = cell
    return f


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--workers", type=int, default=8)
    args = ap.parse_args()

    from chromdata import ChromData
    from chromdata.embedded import embed_links
    from uchrom.datasets import data_dir
    from uchrom.emb import cluster_cells, embed_contacts

    root = data_dir() / "li2023_scnanohic"
    stem = root / "li2023_scnanohic_gm12878"
    tables = read_cells(root / "raw" / TAR)
    sizes = chromsizes(None, "hg38", keep=HG38)
    log(f"{len(tables)} cells, {sum(len(d) for d in tables.values()):,} contacts")

    binner = ContactBinner(sizes, list(tables), stem.parent / f".{stem.name}_bins")
    km = binner.keymaker()
    rows, frags = [], []
    for ci, (cell, df) in enumerate(zip(binner.cells, (tables[c] for c in binner.cells))):
        c1 = km.chrom_codes(df["align1_chrom"].astype(str))
        c2 = km.chrom_codes(df["align2_chrom"].astype(str))
        p1 = ((df["align1_start"] + df["align1_end"]) // 2).to_numpy()      # an alignment at its midpoint
        p2 = ((df["align2_start"] + df["align2_end"]) // 2).to_numpy()
        ck, bk = km.keys(c1, p1, c2, p2)
        binner.add_keys(ci, ck, bk, len(df))
        ok = (c1 >= 0) & (c2 >= 0)
        f = fragments(cell, df)
        rows.append({"cell_id": cell, "n_reads": int(df["read_idx"].nunique()), "n_fragments": len(f),
                     "n_contacts_published": len(df), "n_direct": int(df["contact_is_direct"].sum()),
                     "n_cis": int((c1[ok] == c2[ok]).sum()),
                     "frac_phased": float((f["haplotype"] > 0).mean())})
        frags.append(f)
    binner.close()
    cells = pd.DataFrame(rows).set_index("cell_id")
    cells["n_contacts"] = pd.Series(binner.per_cell, index=binner.cells).reindex(cells.index).to_numpy()
    cells["frac_cis"] = cells["n_cis"] / cells["n_contacts"]
    cells["cell_type"] = "GM12878"
    scool = stem.with_name(stem.name + "_cells_1Mb.scool")
    binner.write_scool(scool)
    mcool = binner.write_mcool(stem.with_name(stem.name + "_bulk.mcool"))
    binner.cleanup()
    log(f"balanced {balance_mcool(mcool)} of {mcool.name}; per cell: {cells.median(numeric_only=True).to_dict()}")

    frame = pd.concat(frags, ignore_index=True)
    frame = frame[frame["chrom"].isin(sizes)]
    cd = ChromData(np.zeros((0, 3)), empty_spots(), cells=cells, uns={
        "genome_assembly": "hg38", "coordinate_status": "no 3-D coordinates: contacts only",
        "source": "scNanoHi-C, Li et al. 2023, Nat Methods 20:1493 (doi:10.1038/s41592-023-01978-w); GEO GSE217189 "
                  "(GSM6706395), the authors' clean contact tables of the GM12878 high-depth cells "
                  "(U-Chrom apps/atlas/recipes/build_scnanohic2023.py)"})
    t = cd.set_clusters("scnanohic", frame, cluster="cluster", cell="cell", member_columns=["haplotype"],
                        keep_names=False, attrs={
                            "assay": "scNanoHi-C (nanopore concatemers)",
                            "fragments": "the alignments of a read that take part in a contact the authors kept",
                            "haplotype": "the authors' phasing of the alignment: 1 / 2, -1 unphased",
                            "cell": "the parquet file (the cell barcode)"})
    log(str(t))
    cd.link_cool(str(mcool), key="bulk", label=f"All {len(cells)} cells (merged; the authors' contacts)")
    cd.link_scool(str(scool), key="per_cell", label="Per cell (1 Mb; the authors' contacts)", cell_name="cell_id",
                  genome_assembly="hg38", bin_size=1_000_000)
    embed_contacts(cd, contacts="per_cell", key_added="hic", methods=("pca", "umap"), n_threads=args.workers)
    labels = cluster_cells(cd, use="hic_pca", resolution=1.0, key_added="hic_leiden")
    log(f"hic_leiden: {labels.value_counts().to_dict()}")
    for kind in ("linked_scool", "linked_cool"):          # stored relative to the store's folder
        for rec in cd.uns[kind].values():
            rec["path"] = Path(rec["path"]).name
    store = stem.with_name(stem.name + ".chromdata.zarr")
    cd.write(store)
    embed_links(str(store))
    log(f"wrote {store}")


if __name__ == "__main__":
    sys.exit(main())
