"""Barcode pair -> published spot maps of the Chen et al. 2026 adult cortex / hippocampus 10 um sections.

The per-spot pairs reprocessed from GSA CRA016676 name a spot by its barcode pair (``<bcB>_<bcA>``);
``benchmarks/screcon/chen_spots.py`` (PREREG §13.3) needs the published spot behind it (grid position,
image centroid, published regions / clusters).  The pairing is the one ``link_spatial_hic_chen2026_contacts.py``
chose on the data and recorded in the store (``uns['contacts_stats']['reprocessed'][<run>]['chosen']``); it is
applied here to every barcode pair of the 96 x 96 chip with that script's ``candidates()``.

    python apps/atlas/recipes/build_chen2026_spot_maps.py [--local]

Reads the atlas stores ``chen2026_cortex_adult_10um`` / ``chen2026_hippocampus_adult_10um`` (``uchrom.datasets.atlas``,
over HTTP; ``--local``: the stores built under the data directory, ``spatial_hic_chen2026/<tissue>.chromdata.zarr``)
and writes ``<data dir>/spatial_hic_chen2026/spot_maps/chen2026_<tissue>_<run>_spots.tsv.gz``.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
SECTIONS = (("cortex_adult_10um", "CRR1829219"), ("hippocampus_adult_10um", "CRR1829220"))
KEEP = ["run", "barcode_pair", "spot", "section", "grid_col", "grid_row", "image_centroid_x", "image_centroid_y",
        "seurat_clusters", "banksy_cluster", "Region", "anno", "cell_type", "Short_Long_Ratio"]


def out_dir() -> Path:
    from uchrom.datasets import data_dir
    return data_dir() / "spatial_hic_chen2026" / "spot_maps"


def spot_map(cd, run: str) -> tuple[pd.DataFrame, str]:
    sys.path.insert(0, str(HERE))
    from link_spatial_hic_chen2026_contacts import barcode_lists, candidates
    info = cd.uns["contacts_stats"]["reprocessed"][run]
    if not info.get("chosen"):
        raise SystemExit(f"{run}: no pairing chosen in the store")
    cells = cd.cells[cd.cells["section"] == info["section"]]
    b1, b2 = barcode_lists(96)
    names = pd.Series([f"{x}_{y}" for x in b1 for y in b2])          # every barcode pair of the chip
    m = candidates(names, cells, 96)[info["chosen"]]
    df = pd.DataFrame({"barcode_pair": list(m.keys()), "spot": list(m.values())})
    c = cells.copy()
    for col in c.columns:
        if str(c[col].dtype) == "category":
            c[col] = c[col].astype(str)
    df = df.merge(c, left_on="spot", right_index=True, how="left")
    df.insert(0, "run", run)
    return df[[k for k in KEEP if k in df.columns]], info["chosen"]


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--local", action="store_true", help="read the stores built under the data directory")
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args(argv)
    out = args.out or out_dir()
    out.mkdir(parents=True, exist_ok=True)
    for tissue, run in SECTIONS:
        if args.local:
            from chromdata import ChromData
            from uchrom.datasets import data_dir
            cd = ChromData.read(data_dir() / "spatial_hic_chen2026" / f"{tissue}.chromdata.zarr", backed=True)
        else:
            from uchrom.datasets import atlas
            cd = atlas(f"chen2026_{tissue}")
        df, chosen = spot_map(cd, run)
        f = out / f"chen2026_{tissue}_{run}_spots.tsv.gz"
        df.to_csv(f, sep="\t", index=False)
        print(f"{f}: {len(df)} spots ({chosen})", flush=True)


if __name__ == "__main__":
    main()
