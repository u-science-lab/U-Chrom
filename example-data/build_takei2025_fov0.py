"""Takei 2025 cerebellum DNA seqFISH+ — the first ~47 cells of rep 1, FOV 0.

The Zenodo tarball (record 7693825, ~2.8 GB) holds one ~2 GB CSV per field of
view.  This script *streams* it and stops after ``--rows`` rows of the first
FOV, drops the last (possibly truncated) cell and loads the rest with
:func:`uchrom.io.seqfish_multiomics.read_seqfish_multiomics` — 3-D traces
plus 59 per-spot immunofluorescence / RNA-FISH tracks (H3K27ac, H3K9me3,
LaminB1, …), cell types and the published UMAP.

  takei2025_fov0/takei2025_fov0.h5cd   (~220 MB; not checked in)

Usage::

    python example-data/build_takei2025_fov0.py [--rows 400000]
"""

from __future__ import annotations

import argparse
import tarfile
import urllib.request
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
OUT = HERE / "takei2025_fov0"
TARBALL = "https://zenodo.org/records/7693825/files/cerebellum_rep1.tar.gz"
MEMBER = "cerebellum_rep1/cerebellum_rep1_pos0.csv"
GITHUB = "https://media.githubusercontent.com/media/CaiGroup/dna-seqfish-plus-multi-omics/main"
LOCI = f"{GITHUB}/data/annotation/LC1-100k-09022022-mm10-25kb-meta.csv"
CLUSTERS = f"{GITHUB}/data/cerebellum/clustering/100k-002-001-cerebellum_mRNA_cluster_nuc_vol_filtered.csv"


def fetch(url: str, dest: Path) -> Path:
    if not dest.exists():
        urllib.request.urlretrieve(url, dest)
    return dest


def stream_rows(n_rows: int, dest: Path) -> Path:
    """Read the first n_rows of the FOV-0 CSV straight out of the tarball."""
    if dest.exists():
        return dest
    with urllib.request.urlopen(TARBALL) as resp, tarfile.open(fileobj=resp, mode="r|gz") as tar:
        for member in tar:
            if member.name == MEMBER:
                fh = tar.extractfile(member)  # not seekable in stream mode: read raw chunks
                buf, n_lines = bytearray(), 0
                while n_lines <= n_rows:
                    chunk = fh.read(1 << 20)
                    if not chunk:
                        break
                    buf += chunk
                    n_lines += chunk.count(b"\n")
                lines = bytes(buf).split(b"\n")[: n_rows + 1]  # header + rows
                dest.write_bytes(b"\n".join(lines) + b"\n")
                return dest
    raise RuntimeError(f"{MEMBER} not found in {TARBALL}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--rows", type=int, default=400_000)
    args = ap.parse_args()
    OUT.mkdir(exist_ok=True)
    raw = stream_rows(args.rows, OUT / "cerebellum_rep1_pos0_head.csv")
    df = pd.read_csv(raw)
    df = df[df["cellID"] != df["cellID"].iloc[-1]]  # last cell may be cut off
    cells_csv = OUT / "cerebellum_rep1_pos0_cells.csv"
    df.to_csv(cells_csv, index=False)

    from uchrom.io.seqfish_multiomics import read_seqfish_multiomics

    cd = read_seqfish_multiomics(
        cells_csv,
        locus_annotation=fetch(LOCI, OUT / "LC1-100k-09022022-mm10-25kb-meta.csv"),
        cell_clustering=fetch(CLUSTERS, OUT / "cerebellum_mRNA_cluster_nuc_vol_filtered.csv"),
    )
    out = OUT / "takei2025_fov0.h5cd"
    cd.write(out)
    print(cd)


if __name__ == "__main__":
    main()
