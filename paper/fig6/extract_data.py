"""Extract the small real-data caches that the Fig 6 mock draws (Takei 2025 FOV 0).

    PYTHONPATH=<repo> python paper/fig6/extract_data.py [path/to/takei2025_fov0.chromdata.zarr]

Dataset: `example-data/takei2025_fov0/` (catalogued in example-data/README.md; built by
`example-data/build_takei2025_fov0.py`). Writes `_cache/takei_fov0.npz`.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

from uchrom.core import ChromData
from uchrom.fea.distance import mean_distance_matrix, radius_of_gyration

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
DEFAULT = REPO / "example-data/takei2025_fov0/takei2025_fov0.chromdata.zarr"
CHROM = "chr15"
GROUPS = ["Bergmann", "Granule"]
TRACKS = ["H3K27ac", "H3K9me3", "LaminB1"]
POOL = 1_000_000  # display bins for the Genome pane
DRAW_CHROMS = ["chr1", "chr7", "chr11", "chr15", "chr19"]


def main(path: Path):
    cd = ChromData.read(str(path))
    cells = cd.cells.copy()
    cells["cell_id"] = cells.index.astype(str) if "cell_id" not in cells else cells["cell_id"].astype(str)
    df = cd.spots.copy()
    df[["x", "y", "z"]] = np.asarray(cd.coords, float)
    for tr in TRACKS:
        df[tr] = cd.tracks[tr].to_numpy(float)
    df["cell_id"] = df["cell_id"].astype(str)
    ct = dict(zip(cells["cell_id"], cells["cell_type"].astype(str)))
    df["cell_type"] = df["cell_id"].map(ct)
    out = {
        "cell_id": cells["cell_id"].to_numpy(str),
        "cell_type": cells["cell_type"].astype(str).to_numpy(str),
        "umap": np.asarray(cd.cellm["umap"], float),
        # centroid_x/y/z (format 2.3) or the older x_centroid/…, whichever the store has
        "centroid": cd.cell_positions().reindex(cells["cell_id"].to_numpy())[["x", "y", "z"]].to_numpy(float),
        "nuc_volume": cells["nuc_volume_um3"].to_numpy(float),
    }
    # 3-D pane: spots of a few chromosomes, all cells (x, y, z, cell index, trace index)
    sub = df[df["chrom"].astype(str).isin(DRAW_CHROMS)].sort_values(["trace_id", "start"])
    cidx = {c: i for i, c in enumerate(out["cell_id"])}
    tcodes, _ = sub["trace_id"].astype(str).factorize()
    out["xyz"] = sub[["x", "y", "z"]].to_numpy(float)
    out["xyz_cell"] = sub["cell_id"].map(cidx).to_numpy(int)
    out["xyz_trace"] = tcodes.astype(int)
    out["xyz_chrom"] = sub["chrom"].astype(str).map({c: i for i, c in enumerate(DRAW_CHROMS)}).to_numpy(int)
    out["draw_chroms"] = np.array(DRAW_CHROMS)
    # Genome pane: chr15 median distance per group + H3K27ac per bin per group
    for g in GROUPS:
        gdf = df[df["cell_type"] == g]
        m, bins, n = mean_distance_matrix(gdf, chrom=CHROM)
        starts = np.array([b[0] for b in bins])
        edges = np.arange(0, starts.max() + POOL, POOL)
        k = np.digitize(starts, edges) - 1
        nb = len(edges) - 1
        pooled = np.full((nb, nb), np.nan)
        for i in range(nb):
            ii = k == i
            if not ii.any():
                continue
            for j in range(nb):
                jj = k == j
                if jj.any():
                    blk = m[np.ix_(ii, jj)]
                    if np.isfinite(blk).any():
                        pooled[i, j] = np.nanmedian(blk)
        out[f"dist_{g}"] = pooled
        out[f"ntr_{g}"] = n
        c15 = gdf[gdf["chrom"].astype(str) == CHROM]
        prof = c15.groupby(np.digitize(c15["start"], edges) - 1)["H3K27ac"].mean()
        out[f"h3k27ac_{g}"] = prof.reindex(range(nb)).to_numpy(float)
    # Genome pane in b: IF tracks per 1-Mb bin for the lasso group and for all cells
    c15 = df[df["chrom"].astype(str) == CHROM]
    edges = np.arange(0, c15["start"].max() + POOL, POOL)
    for g, sub_ in [("Bergmann", c15[c15["cell_type"] == "Bergmann"]), ("all", c15)]:
        k = np.digitize(sub_["start"], edges) - 1
        for tr in TRACKS:
            out[f"trk_{tr}_{g}"] = sub_.groupby(k)[tr].mean().reindex(range(len(edges) - 1)).to_numpy(float)
    # Stats pane in b: per-cell IF means
    for tr in TRACKS:
        out[f"cell_if_{tr}"] = cells[f"if.{tr}"].to_numpy(float)
    # Stats pane: Rg per trace (all chromosomes) by cell type
    rg = radius_of_gyration(df)
    tr_ct = df.groupby("trace_id", observed=True)["cell_type"].first()
    # d: every trace's Rg with its cell (the agent's Rg view: selection vs the other cells)
    tr_cell = df.groupby("trace_id", observed=True)["cell_id"].first().astype(str)
    cidx_all = {c: i for i, c in enumerate(out["cell_id"])}
    out["rg_trace"] = rg.to_numpy(float)
    out["rg_trace_cell"] = tr_cell.reindex(rg.index).map(cidx_all).fillna(-1).to_numpy(int)
    out["if_umap"] = np.asarray(cd.cellm["if_umap"], float)
    out["cell_if_SOX2"] = cells["if.SOX2"].to_numpy(float)
    for g in ["Granule", "Bergmann", "Purkinje"]:
        out[f"rg_{g}"] = rg[tr_ct.reindex(rg.index) == g].dropna().to_numpy(float)
        print(g, "median Rg", np.median(out[f"rg_{g}"]).round(3), "n traces", len(out[f"rg_{g}"]))
    print("dist shapes", {g: out[f"dist_{g}"].shape for g in GROUPS}, "xyz", out["xyz"].shape)
    np.savez_compressed(HERE / "_cache/takei_fov0.npz", **out)


if __name__ == "__main__":
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT)
