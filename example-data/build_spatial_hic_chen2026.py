"""Build U-Chrom datasets from the processed spatial Hi-C data of Chen, Guo et al. 2026.

Spatial Hi-C (Chen, Guo et al. 2026, Nat Methods, doi:10.1038/s41592-026-03218-3) profiles chromatin
contacts in spots of a barcoded grid laid over a tissue section (spot width 10, 20 or 50 um), with
spatial RNA on adjacent sections.  The processed data (Zenodo 17961135, CC-BY-4.0) are Seurat
objects per tissue (one per section) with per-spot single-spot A/B compartment scores (ssA/B, from
Higashi imputation) over 500-kb (and 250-kb) bins, clusters, annotations and embeddings, the spatial
RNA, and one per-read cis BEDPE (E13.5 embryo, section 1).  Raw reads (GSA CRA016676) are not used.

For each tissue this script writes spatial_hic_chen2026/<tissue>.chromdata.zarr, a ChromData without
3-D spots, and the files it links (paths relative to the store):
  cells   one row per spot (id "<section>:<col>x<row>"; Hi-C and RNA sections): section, assay
          (hic / rna), grid column and row, image coordinates, and the Seurat metadata (QC, clusters,
          annotations, label-transfer scores; R factors become categories)
  positions  cell_positions("default"): grid column / row (unit "spot", one frame per section);
          cell_positions("image"): the Seurat image coordinates (px), where the object has an image
  bins    the 500-kb (and 250-kb) bins of the ssA/B scores (column resolution)
  cellm   <assay>_<reduction>.<Seurat object>: the published PCA / UMAP / BANKSY embeddings (NaN for
          spots of other objects)
  <tissue>_ssab.h5ad   uns["linked_ssab"]: single-spot A/B scores (Higashi-imputed), Hi-C spots x
          bins (var bin_id = row of bins)
  <tissue>_rna.h5ad    uns["linked_anndata"]: spatial RNA counts, RNA spots x genes
  E13.5 embryo only: <tissue>_spots_1Mb.scool (one cis map per spot of section 1, cells named by
          cell id) and <tissue>_bulk.mcool (all its spots, 25 kb .. 1 Mb), from the per-read BEDPE

Spot barcodes of the BEDPE (the last two "_" fields of the read name, barcode B then A) are placed
with the barcode table of the authors' test data (Zenodo 22144954, test_data/stat_cropped.csv: 50
A and 50 B barcodes with their indices); Seurat spot "<col>x<row>" = (51 - iA) x iB for all 1,999
spots of that section.  Barcodes with one mismatch (sequencing N) are corrected when unambiguous.

Inputs: ``python example-data/download_data.py --spatial_hic_chen2026``, then the Seurat export
(needs R with qs and Seurat, see spatial_hic_chen2026_export.R)::

    python example-data/build_spatial_hic_chen2026.py --export   # runs the R exporter on every .qs
    python example-data/build_spatial_hic_chen2026.py            # builds all tissues
    python example-data/build_spatial_hic_chen2026.py --tissues e13_embryo_50um
"""

from __future__ import annotations

import argparse
import csv
import gzip
import itertools
import json
import re
import subprocess
import time
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE / "spatial_hic_chen2026"
RAW = ROOT / "raw" / "zenodo17961135"
EXPORT = ROOT / "export"
CODE_ZIP = ROOT / "raw" / "code" / "Spatial-Hi-C-v1.0.0.zip"
RSCRIPT_DEFAULT = Path.home() / ".local/share/mamba/envs/uchrom-r/bin/Rscript"

TISSUES = {
    "e13_embryo_50um": dict(hic="seurat_E13_hic_embyro_final_50um", rna="seurat_E13_rna_embyro_final_50um",
                            spot_um=50, label="E13.5 mouse embryo, 50-um spots",
                            bedpe={"E13_HiC_R1": "cis.E13all.R1_hicup_dedup.sort.bedpe.gz"}),
    "cerebellum_adult_20um": dict(hic="seurat_Cere_hic_adult_final_20um", rna="seurat_Cere_rna_adult_final_20um",
                                  spot_um=20, label="adult mouse cerebellum, 20-um spots"),
    "brain_embryo_20um": dict(hic="seurat_brain_hic_embyro_final_20um", rna="seurat_brain_rna_empyro_final_20um",
                              spot_um=20, label="embryonic mouse brain, 20-um spots"),
    "brain_embryo_10um": dict(hic="seurat_brain_hic_embyro_final_10um", rna="seurat_brain_rna_embyro_final_10um",
                              spot_um=10, label="embryonic mouse brain, 10-um spots"),
    "cortex_adult_10um": dict(hic="seurat_brain_hic_cortex_final_10um", rna="seurat_brain_rna_cortex_final_10um",
                              spot_um=10, label="adult mouse cortex, 10-um spots"),
    "hippocampus_adult_10um": dict(hic="seurat_brain_hic_hippo_final_10um", rna="seurat_brain_rna_hippo_final_10um",
                                   spot_um=10, label="adult mouse hippocampus, 10-um spots"),
}
#: Seurat Hi-C assay -> (label, bin size)
HIC_ASSAYS = {"Spatial": ("ssAB_500kb", 500_000), "scAB500k": ("ssAB_500kb", 500_000),
              "scAB250k": ("ssAB_250kb", 250_000)}
CHROMS = [f"chr{i}" for i in range(1, 20)] + ["chrX"]
SOURCE = "Zenodo 17961135 (Chen, Guo et al. 2026, Nat Methods; CC-BY-4.0)"


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


# --------------------------------------------------------------------------- Seurat export (R)

def export_all(rscript: Path) -> None:
    script = HERE / "spatial_hic_chen2026_export.R"
    for t in TISSUES.values():
        for name in (t["hic"], t["rna"]):
            out = EXPORT / name
            if out.exists() and any(out.iterdir()):
                log(f"[skip] {name} already exported")
                continue
            log(f"export {name}")
            env_path = f"{rscript.parent}:{Path('/usr/bin')}:{Path('/bin')}"
            subprocess.run([str(rscript), str(script), str(RAW / f"{name}.qs"), str(out)], check=True,
                           env={"PATH": env_path, "HOME": str(Path.home())})


def read_csc(d: Path):
    from scipy import sparse
    n_f, n_s = (int(x) for x in (d / "shape.txt").read_text().split())
    p = np.fromfile(d / "p.i32", dtype="<i4")
    i = np.fromfile(d / "i.i32", dtype="<i4")
    x = np.fromfile(d / "x.f32", dtype="<f4")
    m = sparse.csc_matrix((x, i, p), shape=(n_f, n_s))
    feats = (d / "features.txt").read_text().splitlines()
    spots = (d / "spots.txt").read_text().splitlines()
    return m, feats, spots


def sections(export: Path):
    """(section name, dir) of an exported .qs, in a stable order."""
    return sorted((p.name, p) for p in export.iterdir() if p.is_dir())


# --------------------------------------------------------------------------- per-spot contacts (BEDPE)

def barcode_table() -> tuple[dict, dict]:
    with zipfile.ZipFile(CODE_ZIP) as z:
        name = next(n for n in z.namelist() if n.endswith("test_data/stat_cropped.csv"))
        rows = list(csv.DictReader(z.read(name).decode().splitlines()))
    a = {r["bc_A"]: int(r["iA"]) for r in rows}
    b = {r["bc_B"]: int(r["iB"]) for r in rows}
    assert len(a) == 50 and len(b) == 50, (len(a), len(b))
    return a, b


def with_mismatches(table: dict) -> dict:
    """Exact barcodes plus every one-mismatch variant (A, C, G, T or N) that maps to a single barcode."""
    out, seen = dict(table), {}
    for bc, idx in table.items():
        for k, base in itertools.product(range(len(bc)), "ACGTN"):
            v = bc[:k] + base + bc[k + 1:]
            if v != bc:
                seen.setdefault(v, set()).add(idx)
    for v, idxs in seen.items():
        if v not in out and len(idxs) == 1:
            out[v] = next(iter(idxs))
    return out


def bin_table(chromsizes: pd.Series, res: int) -> pd.DataFrame:
    rows = []
    for c in CHROMS:
        n = int(np.ceil(chromsizes[c] / res))
        starts = np.arange(n, dtype=np.int64) * res
        rows.append(pd.DataFrame({"chrom": c, "start": starts, "end": np.minimum(starts + res, chromsizes[c])}))
    return pd.concat(rows, ignore_index=True)


def build_contacts(bedpe: Path, spot_names: list, cell_ids: list, stem: Path, chromsizes: pd.Series, chunk: int,
                   redo: bool = False) -> dict:
    """Per-spot 1-Mb cis maps (.scool, one cell per ``cell_ids`` entry) and a bulk .mcool of the spots
    in ``spot_names`` ("<col>x<row>")."""
    import cooler

    done = {"scool": stem.with_name(stem.name + "_spots_1Mb.scool"), "mcool": stem.with_name(stem.name + "_bulk.mcool")}
    stats_json = stem.with_name(stem.name + "_contacts_stats.json")
    if not redo and stats_json.exists() and all(p.exists() for p in done.values()):
        log(f"  [reuse] {done['scool'].name}, {done['mcool'].name} (--redo-contacts rebuilds them)")
        return {**done, "stats": json.loads(stats_json.read_text())}
    a_tab, b_tab = (with_mismatches(t) for t in barcode_table())
    spot_index = {s: k for k, s in enumerate(spot_names)}
    res_spot, res_bulk = 1_000_000, 25_000
    offs = {}
    for res in (res_spot, res_bulk):
        n = np.ceil(chromsizes[CHROMS] / res).astype(np.int64)
        offs[res] = (pd.Series(np.r_[0, np.cumsum(n.to_numpy())[:-1]], index=CHROMS), int(n.sum()))
    spot_acc, bulk_acc = [], []
    stats = dict(lines=0, kept=0, no_barcode=0, not_in_tissue=0, other_chrom=0)
    reader = pd.read_csv(bedpe, sep="\t", header=None, usecols=[0, 1, 2, 3, 4, 5, 6], chunksize=chunk,
                         names=["c1", "s1", "e1", "c2", "s2", "e2", "name"],
                         dtype={"c1": str, "c2": str, "name": str})
    for df in reader:
        stats["lines"] += len(df)
        ok = df["c1"].isin(CHROMS) & (df["c1"] == df["c2"])
        stats["other_chrom"] += int((~ok).sum())
        df = df[ok]
        tail = df["name"].str.rsplit("_", n=2, expand=True)
        ia = tail[2].map(a_tab)
        ib = tail[1].map(b_tab)
        has = ia.notna() & ib.notna()
        stats["no_barcode"] += int((~has).sum())
        spot = (51 - ia[has].astype(int)).astype(str) + "x" + ib[has].astype(int).astype(str)
        si = spot.map(spot_index)
        keep = si.notna()
        stats["not_in_tissue"] += int((~keep).sum())
        d = df[has][keep.to_numpy()]
        si = si[keep].to_numpy(np.int64)
        stats["kept"] += len(d)
        p1 = ((d["s1"].to_numpy() + d["e1"].to_numpy()) // 2).astype(np.int64)
        p2 = ((d["s2"].to_numpy() + d["e2"].to_numpy()) // 2).astype(np.int64)
        lo, hi = np.minimum(p1, p2), np.maximum(p1, p2)
        for res, acc, with_spot in ((res_spot, spot_acc, True), (res_bulk, bulk_acc, False)):
            off, n = offs[res]
            base = d["c1"].map(off).to_numpy(np.int64)
            b1, b2 = base + lo // res, base + hi // res
            key = b1 * n + b2
            if with_spot:
                key = si * (n * n) + key
            k, c = np.unique(key, return_counts=True)
            acc.append(pd.Series(c, index=k))
            if len(acc) >= 8:                                  # bound memory: merge partial sums
                acc[:] = [pd.concat(acc).groupby(level=0).sum()]
        log(f"  {stats['lines']:,} lines, {stats['kept']:,} kept")
    written = {}
    for res, acc, with_spot in ((res_spot, spot_acc, True), (res_bulk, bulk_acc, False)):
        s = pd.concat(acc).groupby(level=0).sum()
        _, n = offs[res]
        keys, vals = s.index.to_numpy(np.int64), s.to_numpy(np.int64)
        if with_spot:
            spot_of = keys // (n * n)
            pix = keys % (n * n)
            bounds = np.searchsorted(spot_of, np.arange(len(spot_names) + 1))
            per = {}
            for k, name in enumerate(cell_ids):
                lo_, hi_ = bounds[k], bounds[k + 1]
                if hi_ > lo_:
                    per[name] = pd.DataFrame({"bin1_id": pix[lo_:hi_] // n, "bin2_id": pix[lo_:hi_] % n,
                                              "count": vals[lo_:hi_]})
            path = stem.with_name(stem.name + "_spots_1Mb.scool")
            cooler.create_scool(str(path), bin_table(chromsizes, res), per, ordered=True)
            written["scool"] = path
            stats["spots_with_contacts"] = len(per)
        else:
            tmp = stem.with_name(stem.name + "_bulk_25kb.cool")
            cooler.create_cooler(str(tmp), bin_table(chromsizes, res),
                                 pd.DataFrame({"bin1_id": keys // n, "bin2_id": keys % n, "count": vals}),
                                 ordered=True)
            path = stem.with_name(stem.name + "_bulk.mcool")
            cooler.zoomify_cooler(str(tmp), str(path), [25_000, 50_000, 100_000, 250_000, 500_000, 1_000_000],
                                  chunksize=10_000_000)
            tmp.unlink()
            written["mcool"] = path
    log(f"  contacts: {stats}")
    stats_json.write_text(json.dumps(stats, indent=1))
    written["stats"] = stats
    return written


# --------------------------------------------------------------------------- one tissue

def parse_bins(features: list) -> pd.DataFrame:
    m = [re.match(r"^(chr[^:]+):(\d+)-(\d+)$", f) for f in features]
    assert all(m), "non-bin feature"
    return pd.DataFrame({"chrom": [x.group(1) for x in m], "start": [int(x.group(2)) for x in m],
                         "end": [int(x.group(3)) for x in m]})


def natural(c: str):
    s = c.removeprefix("chr")
    return (0, int(s)) if s.isdigit() else (1, s)


def build_tissue(name: str, spec: dict, chromsizes: pd.Series, chunk: int, contacts: bool = True,
                 redo_contacts: bool = False) -> Path:
    import anndata as ad
    from scipy import sparse

    from uchrom import ChromData

    stem = ROOT / name
    metas, hic_mats, rna_mats, reds = [], [], [], []
    for assay in ("hic", "rna"):
        for sec, d in sections(EXPORT / spec[assay]):
            if assay not in sec.lower():                       # Hi-C and RNA sections may share a name
                sec = f"{sec}_{'HiC' if assay == 'hic' else 'RNA'}"
            factors = [c for c in (d / "factors.txt").read_text().splitlines() if c]
            md = pd.read_csv(d / "meta.csv", low_memory=False, dtype={c: str for c in factors})
            md.insert(0, "cell_id", sec + ":" + md["spot"].astype(str))
            md.insert(1, "section", sec)
            md.insert(2, "assay", assay)
            metas.append(md)
            obj = (d / "object.txt").read_text().strip()
            for red in sorted(d.glob("red_*.csv")):
                e = pd.read_csv(red).set_index("spot")
                e.index = sec + ":" + e.index.astype(str)
                reds.append((f"{assay}_{red.stem.removeprefix('red_')}.{obj}", e, assay, red.stem[4:], obj))
            for ad_ in sorted(d.glob("assay_*")):
                if assay == "hic" and ad_.name.removeprefix("assay_") not in HIC_ASSAYS:
                    continue                                   # e.g. BANKSY-smoothed scores
                m, feats, spots = read_csc(ad_)
                ids = [f"{sec}:{s}" for s in spots]
                layer = (ad_ / "layer.txt").read_text().strip()
                if assay == "rna" and any(r[3][0] == ids[0] for r in rna_mats):
                    continue                                   # one RNA matrix per section
                (hic_mats if assay == "hic" else rna_mats).append((ad_.name.removeprefix("assay_"), m, feats, ids, layer))
    cells = pd.concat(metas, ignore_index=True).set_index("cell_id")
    for c in cells.columns:
        if not pd.api.types.is_numeric_dtype(cells[c]):        # labels (R factors) and strings
            cells[c] = cells[c].where(cells[c].isna(), cells[c].astype(str)).astype("category")
    n = len(cells)
    pos = {cid: k for k, cid in enumerate(cells.index)}
    log(f"{name}: {n:,} spots ({(cells['assay'] == 'hic').sum():,} Hi-C, {(cells['assay'] == 'rna').sum():,} RNA) "
        f"in {cells['section'].nunique()} sections")

    # ssA/B: Hi-C spots x bins of every resolution (the store's bins axis), linked as an AnnData
    # (cellm is read on open, and 40k spots x 14k bins would be ~2 GB)
    hic_ids = cells.index[cells["assay"] == "hic"]
    hpos = {cid: k for k, cid in enumerate(hic_ids)}
    bins_parts, blocks, assays_used = [], [], {}
    by_res = {}
    for assay, m, feats, ids, layer in hic_mats:
        _, res = HIC_ASSAYS[assay]
        by_res.setdefault(res, []).append((m, feats, ids))
        assays_used.setdefault(res, set()).add(f"{assay}[{layer}]")
    for res, mats in sorted(by_res.items(), reverse=True):
        b = pd.concat([parse_bins(f) for _, f, _ in mats]).drop_duplicates()
        b = b.assign(_o=b["chrom"].map(natural)).sort_values(["_o", "start"]).drop(columns="_o")
        b["resolution"] = res
        bins_parts.append(b)
        col = {(c, s): k for k, (c, s) in enumerate(zip(b["chrom"], b["start"]))}
        arr = np.full((len(hic_ids), len(b)), np.nan, dtype=np.float32)
        for m, feats, ids in mats:
            fb = parse_bins(feats)
            cols = np.array([col[(c, s)] for c, s in zip(fb["chrom"], fb["start"])])
            rows = np.array([hpos[i] for i in ids])
            arr[np.ix_(rows, cols)] = m.toarray().T.astype(np.float32)   # spots x features
        blocks.append(arr)
    bins = pd.concat(bins_parts, ignore_index=True)
    bins["chrom"] = bins["chrom"].astype("category")
    var = bins.assign(chrom=bins["chrom"].astype(str), bin_id=np.arange(len(bins)))
    var.index = (var["chrom"] + ":" + var["start"].astype(str) + "-" + var["end"].astype(str)
                 + "@" + (var["resolution"] // 1000).astype(str) + "kb")
    ssab = ad.AnnData(X=np.hstack(blocks), obs=cells.loc[hic_ids, ["section"]].copy(), var=var)
    ssab.obs.index.name = "cell_id"
    ssab_path = stem.with_name(stem.name + "_ssab.h5ad")
    ssab.write_h5ad(ssab_path, compression="gzip")
    log(f"  ssA/B: {ssab.n_obs:,} spots x {ssab.n_vars:,} bins "
        f"({', '.join(f'{r // 1000} kb' for r in sorted(by_res, reverse=True))}) -> {ssab_path.name}")
    cellm = {}

    # embeddings are per Seurat object (one section, or several merged ones sharing one embedding)
    embeddings = {}
    for key, e, assay, red, obj in reds:
        if key not in cellm:
            cellm[key] = np.full((n, e.shape[1]), np.nan, dtype=np.float32)
        cellm[key][[pos[i] for i in e.index]] = e.to_numpy(np.float32)
        embeddings[key] = {"method": "umap" if "umap" in red.lower() else red, "reduction": red,
                           "modality": "Hi-C (ssA/B)" if assay == "hic" else "RNA",
                           "label": f"{obj} · {assay.upper()} {red}", "source": f"{SOURCE}; Seurat object {obj}"}

    empty = pd.DataFrame({c: pd.Series(dtype=t) for c, t in
                          [("chrom", str), ("start", np.int64), ("end", np.int64), ("trace_id", str), ("cell_id", str)]})
    cd = ChromData(np.zeros((0, 3)), empty, bins=bins, cells=cells, cellm=cellm,
                   uns={"genome_assembly": "mm10", "source": SOURCE, "title": spec["label"],
                        "doi": "10.1038/s41592-026-03218-3",
                        "coordinate_status": "no 3-D coordinates: spots of a spatial barcode grid",
                        "spot_size_um": spec["spot_um"], "embeddings": embeddings,
                        "linked_ssab": {"path": ssab_path.name, "format": "h5ad",
                                        "description": "single-spot A/B compartment score (Higashi-imputed), "
                                                       "the Seurat assay values as published",
                                        "seurat_assays": {f"{r // 1000}kb": sorted(v) for r, v in assays_used.items()},
                                        "cell_axis": "obs index = cells index (Hi-C spots)",
                                        "var_axis": "var bin_id = row of bins (column resolution)"}})
    cd.set_cell_positions(cells[["grid_col", "grid_row"]].to_numpy(float), unit="spot", frame="tissue",
                          region_col="section", status="measured",
                          source="spot grid column / row from the Seurat spot names (<col>x<row>)",
                          spot_size_um=spec["spot_um"])
    if {"image_imagecol", "image_imagerow"} <= set(cells.columns):
        cd.set_cell_positions(cells[["image_imagecol", "image_imagerow"]].to_numpy(float), key="image",
                              unit="px", frame="tissue", region_col="section", status="measured",
                              source="Seurat GetTissueCoordinates (image column, row)")

    # spatial RNA: spots x genes counts, linked as AnnData
    if rna_mats:
        genes = sorted(set().union(*(f for _, _, f, _, _ in rna_mats)))
        gi = {g: k for k, g in enumerate(genes)}
        blocks, obs = [], []
        for _, m, feats, ids, _ in rna_mats:
            perm = sparse.csr_matrix((np.ones(len(feats)), (np.arange(len(feats)), [gi[f] for f in feats])),
                                     shape=(len(feats), len(genes)))
            blocks.append((m.T.tocsr() @ perm).astype(np.float32))
            obs += ids
        adata = ad.AnnData(X=sparse.vstack(blocks).tocsr(), obs=pd.DataFrame(index=pd.Index(obs, name="cell_id")),
                           var=pd.DataFrame(index=pd.Index(genes, name="gene")))
        adata.obs = adata.obs.join(cells[["section"]])
        h5ad = stem.with_name(stem.name + "_rna.h5ad")
        adata.write_h5ad(h5ad, compression="gzip")
        cd.uns["linked_anndata"] = {"path": h5ad.name, "format": "h5ad", "modality": "spatial RNA",
                                    "seurat_assays": sorted({f"{a}[{l}]" for a, *_, l in rna_mats}),
                                    "cell_axis": "obs index = cells index (RNA spots)"}
        log(f"  RNA: {adata.n_obs:,} spots x {adata.n_vars:,} genes -> {h5ad.name}")

    for sec, fname in (spec.get("bedpe", {}) if contacts else {}).items():
        in_sec = cells["section"] == sec
        files = build_contacts(RAW / fname, cells.loc[in_sec, "spot"].astype(str).tolist(),
                               cells.index[in_sec].tolist(), stem, chromsizes, chunk, redo=redo_contacts)
        cd.link_scool(files["scool"].name, key=f"per_spot.{sec}", cell_name="cell id (<section>:<col>x<row>)",
                      genome_assembly="mm10", bin_size=1_000_000)
        cd.link_cool(files["mcool"].name, key=f"bulk.{sec}", label=f"{sec}, all spots (merged)",
                     genome_assembly="mm10")
        cd.uns.setdefault("contacts_stats", {})[sec] = files["stats"]

    out = stem.with_name(stem.name + ".chromdata.zarr")
    cd.write(out)
    log(f"wrote {out.name}: {cd}")
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--export", action="store_true", help="run the R exporter on every .qs first")
    ap.add_argument("--rscript", type=Path, default=RSCRIPT_DEFAULT)
    ap.add_argument("--tissues", default=",".join(TISSUES))
    ap.add_argument("--redo-contacts", action="store_true", help="rebuild existing .scool / .mcool")
    ap.add_argument("--no-contacts", action="store_true", help="skip the BEDPE -> .scool / .mcool step")
    ap.add_argument("--chunk", type=int, default=5_000_000, help="BEDPE rows per chunk")
    a = ap.parse_args()
    if a.export:
        export_all(a.rscript)
    import cooler.util
    chromsizes = cooler.util.fetch_chromsizes("mm10")
    for t in a.tissues.split(","):
        build_tissue(t, TISSUES[t], chromsizes, a.chunk, contacts=not a.no_contacts,
                     redo_contacts=a.redo_contacts)


if __name__ == "__main__":
    main()
