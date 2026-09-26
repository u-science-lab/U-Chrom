"""Takei 2025 cerebellum DNA seqFISH+ — the first ~47 cells of rep 1, FOV 0.

The Zenodo tarball (record 7693825, ~2.8 GB) holds one ~2 GB CSV per field of
view.  This script *streams* it and stops after ``--rows`` rows of the first
FOV, drops the last (possibly truncated) cell and loads the rest with
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

  takei2025_fov0/takei2025_fov0.chromdata.zarr   (~76 MB; not checked in;
  ``--format h5cd`` writes the deprecated ~200 MB .h5cd instead)

Usage::

    python example-data/takei2025_fov0/build.py [--rows 400000]
    python example-data/takei2025_fov0/build.py --update   # only redo the IF embedding
"""

from __future__ import annotations

import argparse
import tarfile
import urllib.request
from pathlib import Path

import pandas as pd

# this script lives in its dataset folder: example-data/takei2025_fov0/
HERE = Path(__file__).resolve().parent
OUT = HERE
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



SUFFIX = {"zarr": ".chromdata.zarr", "cdz": ".cdz", "h5cd": ".h5cd"}


def existing(stem: Path):
    """The dataset as built by this or an older version of the script."""
    return next((stem.with_name(stem.name + s) for s in SUFFIX.values()
                 if stem.with_name(stem.name + s).exists()), None)


def save(cd, out: Path) -> None:
    """Write ``cd``; replaces ``out`` atomically, so a running browser never
    sees a half-written store (the zarr / cdz writer is atomic itself)."""
    if out.suffix == ".h5cd":
        tmp = out.with_suffix(".tmp.h5cd")
        cd.write(tmp)
        tmp.replace(out)
    else:
        cd.write(out)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--rows", type=int, default=400_000)
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
    if not args.no_if:
        add_if_embedding(cd)
    save(cd, out)
    print(cd)


if __name__ == "__main__":
    main()
