"""SpaceA clusters (process.sbatch) -> a .chromdata.zarr store with the clusters per spot (ChromData.clusters).

A clusters line of get_clusters.py is ``<barcode>\\t<read>\\t<read>...``, the barcode
``ODD.EVEN.ODD.Y.LIGTAG.DPM.<file>`` (the tags of read 2 in read order, SpaceA-Paper
1_Pre-processing/config_spaSPRITE_*.txt: READ2 = ODD|EVEN|ODD|Y|LIGTAG|DPM) and a read ``DNA[<strand>]_<chrom>:<start>-<end>``
(pysam's 0-based start and end).  LIGTAG (50 tags, ``oddTop1-50``) and Y (100 tags, ``evenTop1-100``) are the two
orthogonal sets of microfluidic channels: the spot is the pair (LIGTAG, Y), the authors' spot files are named
``LIGTAG.Y...`` (their reformat_clusters reverses the barcode); the three split-pool rounds ODD.EVEN.ODD tell the
clusters of a spot apart.  The spot's position is its channel pair (``cells`` columns ``centroid_x`` = LIGTAG,
``centroid_y`` = Y, in channel units; the channel pitch and the grid's orientation on the slide are not in the public
data).

The table keeps every cluster as written (get_clusters drops duplicate positions within a cluster); the authors'
filters (cluster size 2-1000, chromosome share > 0.15, cis share >= 0.2, spot QC) are analysis choices, recorded in
the attrs.  Usage::

    python build_store.py CLUSTERS.gz OUT.chromdata.zarr --run CRR2725644 --sample E13.5C6 [--figure grid.png]
"""

from __future__ import annotations

import argparse
import gzip
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

TOKEN = re.compile(r"^(?:DNA|RPM|DPM)\[([+-])\]_([^:]+):(\d+)-(\d+)$")


def parse(path: Path, chunk: int = 500_000):
    """Fragments of the clusters file: one frame per chunk of lines (cluster, spot, chrom, start, end, strand)."""
    k = 0
    rows, spots, bad = [], [], 0
    with gzip.open(path, "rt") as fh:
        for line in fh:
            parts = line.rstrip("\n").split("\t")
            tags = parts[0].split(".")
            spot = f"{tags[4]}.{tags[3]}"           # LIGTAG.Y
            for tok in parts[1:]:
                m = TOKEN.match(tok)
                if m is None:
                    bad += 1
                    continue
                rows.append((k, m.group(2), int(m.group(3)), int(m.group(4)), 1 if m.group(1) == "+" else -1))
            spots.append(spot)
            k += 1
            if len(spots) >= chunk:
                yield _frame(rows, spots, k - len(spots)), bad
                rows, spots = [], []
    if spots:
        yield _frame(rows, spots, k - len(spots)), bad


def _frame(rows, spots, first):
    df = pd.DataFrame(rows, columns=["cluster", "chrom", "start", "end", "strand"])
    sp = np.asarray(spots, dtype=object)
    df["spot"] = sp[df["cluster"].to_numpy() - first]
    df["strand"] = df["strand"].astype(np.int8)
    return df


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("clusters", type=Path)
    ap.add_argument("out", type=Path)
    ap.add_argument("--run", required=True)
    ap.add_argument("--sample", required=True)
    ap.add_argument("--figure", type=Path)
    args = ap.parse_args()

    from chromdata import ChromData, ClusterTable

    frames, bad = [], 0
    for df, bad in parse(args.clusters):
        frames.append(df)
    df = pd.concat(frames, ignore_index=True)
    del frames
    lig = df["spot"].str.extract(r"^oddTop(\d+)\.evenTop(\d+)$").astype(float)
    ok = lig.notna().all(axis=1)
    print(f"fragments {len(df):,}, clusters {df['cluster'].nunique():,}, tokens not parsed {bad}, "
          f"fragments outside the LIGTAG x Y grid {int((~ok).sum()):,}", flush=True)
    df = df[ok.to_numpy()]
    spots = (df.groupby("spot").agg(clusters=("cluster", "nunique"), fragments=("cluster", "size")))
    ids = spots.index.str.extract(r"^oddTop(\d+)\.evenTop(\d+)$").astype(int).to_numpy()
    cells = pd.DataFrame({"lig": ids[:, 0], "y": ids[:, 1], "clusters": spots["clusters"].to_numpy(),
                          "fragments": spots["fragments"].to_numpy(), "sample": args.sample, "run": args.run},
                         index=pd.Index(spots.index, name="cell_id"))
    cells = cells.sort_values(["lig", "y"])
    xy = cells[["lig", "y"]].to_numpy(float)
    cells = cells.drop(columns=["lig", "y"])                   # the position goes to centroid_x / centroid_y
    empty = pd.DataFrame({"chrom": pd.Series([], dtype=str), "start": pd.Series([], dtype=np.int64),
                          "end": pd.Series([], dtype=np.int64), "trace_id": pd.Series([], dtype=str)})
    cd = ChromData(np.zeros((0, 3)), empty, cells=cells, uns={
        "genome_assembly": "mm10", "source": "SpaceA, Ma et al. 2026 Dev Cell (doi:10.1016/j.devcel.2026.09.004); "
        f"GSA CRA038845 run {args.run}, sample {args.sample}; reprocessed with the authors' pipeline "
        "(U-Chrom apps/atlas/recipes/spacea_ma2026)"})
    cd.set_cell_positions(xy, cell_ids=list(cells.index), unit="channel",
                          frame="tissue", status="measured",
                          source="SpaceA barcode grid: LIGTAG channel (x) x Y channel (y); pitch and slide "
                                 "orientation not in the public data")
    t = cd.set_clusters("spacea", df, cluster="cluster", cell="spot", member_columns=["strand"], keep_names=False,
                        attrs={"assay": "SpaceA (spatial SPRITE)", "run": args.run, "sample": args.sample,
                               "fragments": "aligned reads (STAR, MAPQ 255, duplicates removed), pysam coordinates",
                               "spot": "barcode tags LIGTAG.Y", "filters": "none (authors': cluster size 2-1000, "
                               "chromosome share > 0.15, cis share >= 0.2, spot QC)"})
    print(t, flush=True)
    cd.write(args.out)
    sizes = t.sizes()
    print("cluster sizes: " + ", ".join(f"{q}: {np.quantile(sizes, q):g}" for q in (0.5, 0.9, 0.99, 0.999)))
    print(f"spots {len(cells):,}; clusters per spot median {cells['clusters'].median():g}; "
          f"spots with >= 1000 fragments {(cells['fragments'] >= 1000).sum():,}")
    if args.figure:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        gx, gy = xy[:, 0].astype(int), xy[:, 1].astype(int)
        grid = np.zeros((gy.max(), gx.max()))
        grid[gy - 1, gx - 1] = np.log10(cells["fragments"])
        fig, ax = plt.subplots(figsize=(5, 8))
        im = ax.imshow(grid, cmap="viridis", aspect="equal", interpolation="nearest")
        ax.set_xlabel("LIGTAG channel"); ax.set_ylabel("Y channel")
        fig.colorbar(im, ax=ax, label="log10 fragments per spot")
        fig.savefig(args.figure, dpi=150, bbox_inches="tight")


if __name__ == "__main__":
    sys.exit(main())
