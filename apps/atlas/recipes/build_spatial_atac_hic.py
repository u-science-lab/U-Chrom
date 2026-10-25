"""Build a U-Chrom dataset from the processed spatial ATAC-Hi-C data of GEO GSE307620 (Nat Methods 2026).

Spatial ATAC-Hi-C (doi:10.1038/s41592-026-03217-4) profiles chromatin accessibility and chromatin contacts
in the same spots of a 50 x 50 barcode grid (Visium-style positions) on coronal mouse brain sections
(MouseBrainR6 = GSM9228169, MouseBrainR8 = GSM9228170).  GEO has, per section, cellranger-atac style
fragments of the ATAC library and of the Hi-C library (one fragment per line: the contact pairing is not
in the processed files), tissue positions, scale factors and images.  Contact maps need the raw reads (SRA;
see spatial_atac_hic/slurm/) and are linked when they exist.

Writes spatial_atac_hic/mouse_brain.chromdata.zarr, a ChromData without 3-D spots, and the files it links:
  cells   one row per in-tissue spot (id "<section>:<barcode>"): section, array_row / array_col,
          n_fragments_atac, n_fragments_hic (fragments of the two libraries), tsse-free QC
  positions  cell_positions("default"): grid column / row (unit "spot", y down, one frame per section);
          cell_positions("image"): pixels of the section's hires image (fullres x tissue_hires_scalef)
  bins      500-kb bins (chr1-19, X)
  bin_tracks  atac_cpm.<section>: bulk ATAC of the section's in-tissue spots, fragments per million
  cells     atac_cluster: k-means (k = 12) of the first 10 LSI components (a quick view of the ATAC domains)
  cellm     atac_lsi / atac_tsne / atac_umap: TF-IDF + LSI of the 50,000 5-kb bins with the most ATAC
          fragments (all sections together); 100-kb / 500-kb bins carried little tissue structure
  mouse_brain_images/<section>.png  uns["linked_images"]: hires tissue images (grayscale bright-field)
  mouse_brain_atac.h5ad  uns["linked_bin_matrices"]["ATAC"]: spots x 500-kb bins, log1p(CPM) (layer
          "counts": fragment midpoints per bin)

    python -m uchrom.datasets fetch spatial_atac_hic
    python apps/atlas/recipes/build_spatial_atac_hic.py
"""

from __future__ import annotations

import argparse
import gzip
import json
import shutil
import time
from pathlib import Path

import numpy as np
import pandas as pd
from uchrom.datasets import data_dir

HERE = Path(__file__).resolve().parent
DATA = data_dir()                       # $UCHROM_DATA, else ~/.cache/uchrom
ROOT = DATA / "spatial_atac_hic"
RAW = ROOT / "raw" / "GSE307620"
SECTIONS = {"MouseBrainR6": ("GSM9228169", "MBR6merge"), "MouseBrainR8": ("GSM9228170", "MBR8merge")}
CHROMS = [f"chr{i}" for i in range(1, 20)] + ["chrX"]
SOURCE = "GEO GSE307620 (spatial ATAC-Hi-C, Nat Methods 2026, doi:10.1038/s41592-026-03217-4)"


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def read_json_gz(p: Path) -> dict:
    return json.loads(gzip.open(p, "rt").read())


def bin_offsets(chromsizes: pd.Series, res: int):
    n = np.array([-(-int(chromsizes[c]) // res) for c in CHROMS], dtype=np.int64)
    return dict(zip(CHROMS, np.r_[0, np.cumsum(n)[:-1]])), int(n.sum())


def count_fragments(path: Path, spot_index: dict, strip: bool, chromsizes: pd.Series, res_list, chunk: int,
                    select: dict | None = None):
    """Fragment midpoints per (spot, bin) for each resolution; fragments per spot (all spots on the grid).
    ``select`` = {res: bin ids}: only those bins of that resolution are counted (columns in that order)."""
    offs = {r: bin_offsets(chromsizes, r) for r in res_list}
    select = select or {}
    colmap = {}
    for r, ids in select.items():
        m = np.full(offs[r][1], -1, dtype=np.int64)
        m[ids] = np.arange(len(ids))
        colmap[r] = m
    mats = {r: np.zeros((len(spot_index), len(select[r]) if r in select else offs[r][1]),
                        dtype=np.int16 if r in select else np.int32) for r in res_list}
    per_spot = {}
    reader = pd.read_csv(path, sep="\t", header=None, comment="#", usecols=[0, 1, 2, 3], chunksize=chunk,
                         names=["chrom", "start", "end", "bc"], dtype={"chrom": str, "bc": str})
    n = 0
    for df in reader:
        n += len(df)
        bc = df["bc"].str[:-2] if strip else df["bc"]
        vc = bc.value_counts()
        for b, c in vc.items():
            per_spot[b] = per_spot.get(b, 0) + int(c)
        si = bc.map(spot_index)
        ok = si.notna() & df["chrom"].isin(CHROMS)
        d, si = df[ok], si[ok].to_numpy(np.int64)
        mid = ((d["start"].to_numpy(np.int64) + d["end"].to_numpy(np.int64)) // 2)
        for r in res_list:
            off, nb = offs[r]
            b = np.minimum(d["chrom"].map(off).to_numpy(np.int64) + mid // r, nb - 1)
            if r in colmap:
                b = colmap[r][b]
                ok2 = b >= 0
                np.add.at(mats[r], (si[ok2], b[ok2]), 1)
            else:
                np.add.at(mats[r], (si, b), 1)
        if n % (chunk * 10) == 0:
            log(f"    {n:,} fragments")
    return mats, per_spot, n


def bin_totals(paths: list, chromsizes: pd.Series, res: int, chunk: int) -> np.ndarray:
    """Fragments per bin of one resolution over several fragment files (any barcode)."""
    off, nb = bin_offsets(chromsizes, res)
    tot = np.zeros(nb, dtype=np.int64)
    for path in paths:
        for df in pd.read_csv(path, sep="\t", header=None, comment="#", usecols=[0, 1, 2], chunksize=chunk,
                              names=["chrom", "start", "end"], dtype={"chrom": str}):
            df = df[df["chrom"].isin(CHROMS)]
            b = df["chrom"].map(off).to_numpy(np.int64) + ((df["start"].to_numpy(np.int64) + df["end"].to_numpy(np.int64)) // 2) // res
            tot += np.bincount(np.minimum(b, nb - 1), minlength=nb)
    return tot


def add_atac_clusters(cd, k: int = 12, n_comp: int = 10) -> None:
    """cells["atac_cluster"]: k-means of the first ``n_comp`` ATAC LSI components (labels by size)."""
    from sklearn.cluster import KMeans

    X = np.asarray(cd.cellm["atac_lsi"])[:, :n_comp]
    lab = KMeans(n_clusters=k, n_init=10, random_state=0).fit_predict(X)
    order = {old: new for new, (old, _) in enumerate(pd.Series(lab).value_counts().items())}
    cells = cd.cells.copy()
    cells["atac_cluster"] = pd.Categorical([f"A{order[x] + 1}" for x in lab], categories=[f"A{i + 1}" for i in range(k)])
    cd.cells = cells


def main() -> None:
    import anndata as ad
    from PIL import Image
    from scipy import sparse

    import cooler.util

    from uchrom import ChromData
    from uchrom.emb import embed_cells

    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--chunk", type=int, default=5_000_000)
    ap.add_argument("--lsi-res", type=int, default=5_000, help="bin size of the LSI features")
    ap.add_argument("--lsi-bins", type=int, default=50_000, help="bins with the most fragments used for LSI")
    a = ap.parse_args()
    chromsizes = cooler.util.fetch_chromsizes("mm10")
    out = ROOT / "mouse_brain"
    parts, atac100, atac500, tracks, images = [], [], [], {}, {}
    frag_files = [RAW / f"{gsm}_{merged}.fragments.tsv.gz" for gsm, merged in SECTIONS.values()]
    log(f"ATAC fragments per {a.lsi_res // 1000}-kb bin (all sections) to choose the LSI bins")
    tot = bin_totals(frag_files, chromsizes, a.lsi_res, a.chunk)
    lsi_bins = np.sort(np.argsort(tot)[::-1][:a.lsi_bins])
    log(f"  {a.lsi_bins:,} bins of {len(tot):,}: >= {tot[lsi_bins].min():,} fragments each")
    img_dir = out.with_name(out.name + "_images")
    img_dir.mkdir(parents=True, exist_ok=True)
    for sec, (gsm, merged) in SECTIONS.items():
        pos = pd.read_csv(RAW / f"{gsm}_{sec}_tissue_positions_list.csv.gz", header=None,
                          names=["barcode", "in_tissue", "array_row", "array_col", "pxl_row", "pxl_col"])
        sf = read_json_gz(RAW / f"{gsm}_{sec}_scalefactors_json.json.gz")
        tis = pos[pos["in_tissue"] == 1].reset_index(drop=True)
        idx = {b: i for i, b in enumerate(tis["barcode"])}
        log(f"{sec}: {len(tis):,} in-tissue spots of {len(pos):,}")
        (m100, m500), atac_per_spot, n_atac = (lambda r: ((r[0][a.lsi_res], r[0][500_000]), r[1], r[2]))(
            count_fragments(RAW / f"{gsm}_{merged}.fragments.tsv.gz", idx, True, chromsizes, (a.lsi_res, 500_000), a.chunk,
                            select={a.lsi_res: lsi_bins}))
        _, hic_per_spot, n_hic = count_fragments(RAW / f"{gsm}_{merged}.hic.fragments.sorted.header.tsv.gz", idx, False,
                                                 chromsizes, (), a.chunk)
        on_grid = set(pos["barcode"])
        in_t = set(tis["barcode"])
        frac = lambda d, s: sum(v for k, v in d.items() if k in s) / max(1, sum(d.values()))  # noqa: E731
        log(f"  ATAC {n_atac:,} fragments ({frac(atac_per_spot, in_t):.1%} in tissue); Hi-C fragments {n_hic:,} "
            f"({frac(hic_per_spot, in_t):.1%} in tissue)")
        s = sf["tissue_hires_scalef"]
        cells = pd.DataFrame({
            "section": sec, "barcode": tis["barcode"], "array_row": tis["array_row"], "array_col": tis["array_col"],
            "pxl_row_fullres": tis["pxl_row"], "pxl_col_fullres": tis["pxl_col"],
            "image_x": tis["pxl_col"] * s, "image_y": tis["pxl_row"] * s,
            "n_fragments_atac": tis["barcode"].map(atac_per_spot).fillna(0).astype(np.int64),
            "n_fragments_hic": tis["barcode"].map(hic_per_spot).fillna(0).astype(np.int64),
        })
        cells.index = pd.Index(sec + ":" + cells["barcode"], name="cell_id")
        parts.append(cells)
        atac100.append(sparse.csr_matrix(m100))
        atac500.append(m500)
        tracks[f"atac_cpm.{sec}"] = m500.sum(0) / max(1, m500.sum()) * 1e6
        png = img_dir / f"{sec}.png"
        png.write_bytes(gzip.open(RAW / f"{gsm}_{sec}_tissue_hires_image.png.gz").read())
        w, h = Image.open(png).size
        images[sec] = {"path": f"{img_dir.name}/{png.name}", "format": "png", "positions": "image", "region": sec,
                       "extent": [0, w, 0, h], "kind": "bright-field",
                       "description": "hires tissue image of the section (GEO), spot pixels = fullres x tissue_hires_scalef",
                       "scalefactors": sf}
    cells = pd.concat(parts)
    cells["section"] = cells["section"].astype("category")
    # locus axis: 500-kb bins
    off, nb = bin_offsets(chromsizes, 500_000)
    bins = pd.concat([pd.DataFrame({"chrom": c, "start": np.arange(-(-int(chromsizes[c]) // 500_000), dtype=np.int64) * 500_000})
                      for c in CHROMS], ignore_index=True)
    bins["end"] = np.minimum(bins["start"] + 500_000, bins["chrom"].map(chromsizes).astype(np.int64))
    bins["resolution"] = 500_000
    bins["chrom"] = bins["chrom"].astype("category")
    empty = pd.DataFrame({c: pd.Series(dtype=t) for c, t in
                          [("chrom", str), ("start", np.int64), ("end", np.int64), ("trace_id", str), ("cell_id", str)]})
    cd = ChromData(np.zeros((0, 3)), empty, bins=bins, cells=cells,
                   uns={"genome_assembly": "mm10", "source": SOURCE, "title": "spatial ATAC-Hi-C, mouse brain (coronal)",
                        "doi": "10.1038/s41592-026-03217-4",
                        "coordinate_status": "no 3-D coordinates: spots of a spatial barcode grid",
                        "linked_images": images})
    cd.bin_tracks = pd.DataFrame(tracks)
    cd.set_cell_positions(cells[["array_col", "array_row"]].to_numpy(float), unit="spot", frame="tissue",
                          region_col="section", status="measured", y_axis="down",
                          source="tissue_positions_list.csv array_col / array_row")
    cd.set_cell_positions(cells[["image_x", "image_y"]].to_numpy(float), key="image", unit="px", frame="tissue",
                          region_col="section", status="measured", y_axis="down",
                          source="tissue_positions_list.csv fullres pixels x tissue_hires_scalef (hires image)")
    # ATAC embeddings (all sections together)
    x100 = sparse.vstack(atac100).tocsr()
    feat = (f"the {a.lsi_bins:,} {a.lsi_res // 1000}-kb genome bins with the most ATAC fragments (of {len(tot):,}); "
            f"fragment midpoints")
    log(f"ATAC LSI on {feat}")
    embed_cells(cd, source="atac", matrix=x100, normalization="tfidf", n_lsi=30, features=feat)
    add_atac_clusters(cd)
    meta = cd.uns["embeddings"]["atac_lsi"]
    log(f"  dropped LSI components {meta.get('dropped_components')} (depth r {np.round(meta.get('depth_r', [])[:3], 2)})")
    # ATAC per spot x 500-kb bin, linked (browser: genome tracks per spot / group)
    x500 = np.vstack(atac500).astype(np.float32)
    cpm = x500 / np.maximum(x500.sum(1, keepdims=True), 1) * 1e6
    var = bins.assign(chrom=bins["chrom"].astype(str), bin_id=np.arange(len(bins)))
    var.index = var["chrom"] + ":" + var["start"].astype(str) + "-" + var["end"].astype(str) + "@500kb"
    adata = ad.AnnData(X=np.log1p(cpm), obs=cells[["section"]].copy(), var=var,
                       layers={"counts": sparse.csr_matrix(x500.astype(np.int32))})
    h5 = out.with_name(out.name + "_atac.h5ad")
    adata.write_h5ad(h5, compression="gzip")
    cd.uns["linked_bin_matrices"] = {"ATAC": {"path": h5.name, "format": "h5ad", "label": "ATAC log1p CPM",
                                              "description": "ATAC fragment midpoints per spot and 500-kb bin, log1p(CPM); "
                                                             "layer counts = raw counts",
                                              "cell_axis": "obs index = cells index", "var_axis": "var bin_id = row of bins"}}
    store = out.with_name(out.name + ".chromdata.zarr")
    cd.write(store)
    log(f"wrote {store.name}: {cd}")


if __name__ == "__main__":
    main()
