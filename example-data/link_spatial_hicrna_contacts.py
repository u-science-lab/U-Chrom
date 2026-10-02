"""Link the reprocessed spatial Hi-C-RNA contact maps (GEO GSE311199) into the hicrna_* stores.

The contacts come from our Sherlock pipeline (example-data/spatial_hicrna/sherlock/: the published
``.nodups.pairs.gz`` of each sample -> per-spot 1-Mb ``.scool`` + bulk ``.mcool``), one folder per
sample on Oak.  Copy ``<sample>.spots_1Mb.scool`` and ``<sample>.bulk.mcool`` into
``example-data/spatial_hicrna/contacts/`` over the DTN (17.8 GB for the 7 samples; README), then::

    python example-data/link_spatial_hicrna_contacts.py [SAMPLE ...]

Unlike the spatial Hi-C datasets of Chen 2026 / Wang 2026 there is nothing to decide here: the pairs
files carry the same 16-base barcodes as the RNA matrix and the positions, so a map's name *is* the
spot's barcode.  Per sample this

  * renames the cells of the ``.scool`` to the store's ids ``<sample>:<barcode>``
    (``hicrna_<store>.<sample>.spots_1Mb.scool``) and links it as ``per_spot.<sample>``,
  * links the bulk map as ``bulk.<sample>`` (``contacts/<sample>.bulk.mcool``),
  * records the pipeline counts and the checks in ``uns['contacts_stats'][<sample>]``.

It also links the authors' **single-spot A/B** (``obsm['X_abcompartment']`` of the published AnnData) of
``mouse_brain_r1`` as ``uns['linked_bin_matrices']['ssAB']``.  The AnnData does not say which genome bin a
column is.  The columns are the autosomal 500-kb bins from 3 Mb, without a last bin shorter than 100 kb
(chr1-19: 4,816 = the published number; the layout of the spatial Hi-C of Chen et al. 2026 minus chrX and the
bins in assembly gaps).  Checked on the data: per chromosome, the bulk-map compartment E1 against the mean
ssAB over spots is best at shift 0 (median |r| 0.959; 0.90 / 0.85 at +1 / -1 bins), recorded in
``uns['ssab_layout_check']``.  The human melanoma AnnData (5,359 columns) is **not** linked: no layout tried
(500-kb bins of chr1-22 [+X], from 0, without short tail bins, minus bins under a coverage threshold or in the
UCSC hg38 cytoBand acen / gvar / stalk regions) gives 5,359 bins that pass the same check.
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import gzip
import warnings

import anndata as ad
import cooler
import h5py
import numpy as np
import pandas as pd

from uchrom import ChromData

ROOT = Path(__file__).resolve().parent / "spatial_hicrna"
RAW = ROOT / "raw" / "GSE311199"
CONTACTS = ROOT / "contacts"
STORE_OF = {"mouse_brain_r1": "mouse_brain", "mouse_brain_r2": "mouse_brain",
            "mouse_embryo_E11.5": "mouse_embryo", "mouse_embryo_E13.5_r1": "mouse_embryo",
            "mouse_embryo_E13.5_r2": "mouse_embryo",
            "human_melanoma_r1": "human_melanoma", "human_melanoma_r2": "human_melanoma"}


def rename_scool(src: Path, dst: Path, section: str) -> tuple[int, int]:
    """Copy ``src`` to ``dst`` with every cell ``<barcode>`` renamed ``<section>:<barcode>``;
    returns (cells, pixels)."""
    tmp = dst.with_suffix(".tmp")
    shutil.copyfile(src, tmp)
    with h5py.File(tmp, "r+") as f:
        cells = f["cells"]
        for name in list(cells.keys()):
            cells.move(name, f"{section}:{name}")
        n = len(cells)
        pixels = int(sum(cells[c]["pixels"]["count"].shape[0] for c in cells))
    tmp.replace(dst)
    return n, pixels


MM10_AUTOSOMES = {"chr1": 195471971, "chr2": 182113224, "chr3": 160039680, "chr4": 156508116, "chr5": 151834684,
                  "chr6": 149736546, "chr7": 145441459, "chr8": 129401213, "chr9": 124595110, "chr10": 130694993,
                  "chr11": 122082543, "chr12": 120129022, "chr13": 120421639, "chr14": 124902244, "chr15": 104043685,
                  "chr16": 98207768, "chr17": 94987271, "chr18": 90702639, "chr19": 61431566}
RES = 500_000


def mouse_ssab_layout() -> pd.DataFrame:
    """chrom, start of the 4,816 ssAB columns: autosomal 500-kb bins from 3 Mb, no last bin under 100 kb."""
    rows = []
    for c, length in MM10_AUTOSOMES.items():
        n = (length - 3_000_000) // RES + (1 if (length - 3_000_000) % RES >= 100_000 else 0)
        rows += [(c, 3_000_000 + i * RES) for i in range(n)]
    return pd.DataFrame(rows, columns=["chrom", "start"])


def bulk_e1(mcool: Path, chrom: str, res: int = RES) -> np.ndarray:
    """Compartment E1 of one chromosome from the bulk map: O/E, Pearson, first eigenvector; NaN for bins
    below the 5th percentile of the coverage."""
    clr = cooler.Cooler(f"{mcool}::/resolutions/{res}")
    m = clr.matrix(balance=False).fetch(chrom).astype(float)
    cov = m.sum(0)
    ok = cov > np.percentile(cov[cov > 0], 5)
    s = m[np.ix_(ok, ok)]
    s = s / np.sqrt(np.outer(s.sum(0), s.sum(0)))
    d = np.abs(np.subtract.outer(np.arange(len(s)), np.arange(len(s))))
    exp = np.array([np.nanmean(np.diagonal(s, k)) for k in range(len(s))])
    v = np.linalg.eigh(np.nan_to_num(np.corrcoef(np.nan_to_num(s / exp[d]))))[1][:, -1]
    out = np.full(len(m), np.nan)
    out[np.flatnonzero(ok)] = v
    return out


def published_ssab(h5ad_gz: Path, work: Path):
    """(cell ids without the section, X_abcompartment) of a published AnnData."""
    dst = work / h5ad_gz.name.removesuffix(".gz")
    if not dst.exists():
        with gzip.open(h5ad_gz, "rb") as f, open(dst, "wb") as o:
            while chunk := f.read(1 << 24):
                o.write(chunk)
    a = ad.read_h5ad(dst, backed="r")
    return pd.Index(a.obs_names.astype(str)), np.asarray(a.obsm["X_abcompartment"], dtype=np.float32)


def link_ssab(cd: ChromData, store: str, sample: str, h5ad_gz: Path, work: Path) -> dict:
    """Link the authors' single-spot A/B of ``sample`` (mouse layout) and check the column layout."""
    ids, X = published_ssab(h5ad_gz, work)
    lay = mouse_ssab_layout()
    assert X.shape[1] == len(lay), f"ssAB has {X.shape[1]} columns, the layout {len(lay)}"
    # layout check: bulk E1 vs the mean ssAB over spots, per chromosome, at bin shifts 0, +-1, +-2
    mean = X.mean(0)
    mcool = CONTACTS / f"{sample}.bulk.mcool"
    check = {s: [] for s in (0, 1, -1, 2, -2)}
    for c, x in lay.groupby("chrom", sort=False):
        e = bulk_e1(mcool, c)
        col = np.flatnonzero((lay["chrom"] == c).to_numpy())
        for sh in check:
            idx = x["start"].to_numpy() // RES + sh
            ok = (idx >= 0) & (idx < len(e))
            v, a = e[idx[ok]], mean[col[ok]]
            f = np.isfinite(v)
            check[sh].append(abs(np.corrcoef(v[f], a[f])[0, 1]))
    summary = {f"shift_{sh:+d}": {"median_abs_r": round(float(np.median(r)), 4), "min_abs_r": round(float(np.min(r)), 4)}
               for sh, r in check.items()}
    bins = cd.bins.reset_index(drop=True)
    row = pd.Series(np.arange(len(bins)), index=pd.MultiIndex.from_arrays([bins["chrom"].astype(str), bins["start"]]))
    bin_id = row.reindex(pd.MultiIndex.from_arrays([lay["chrom"], lay["start"]])).to_numpy()
    assert not np.isnan(bin_id).any()
    var = pd.DataFrame({"chrom": lay["chrom"], "start": lay["start"],
                        "end": np.minimum(lay["start"] + RES, lay["chrom"].map(MM10_AUTOSOMES)),
                        "resolution": RES, "bin_id": bin_id.astype(int)})
    var.index = (var["chrom"] + ":" + var["start"].astype(str) + "-" + var["end"].astype(str) + "@500kb")
    cell_ids = sample + ":" + ids
    assert cell_ids.isin(cd.cells.index).all()
    a = ad.AnnData(X=X, obs=cd.cells.loc[cell_ids, ["section"]].astype({"section": str}).copy(), var=var)
    a.obs.index.name = "cell_id"
    path = ROOT / f"hicrna_{store}_ssab.h5ad"
    a.write_h5ad(path, compression="gzip")
    cd.uns["linked_bin_matrices"] = {"ssAB": {
        "path": path.name, "format": "h5ad", "label": "ssA/B",
        "description": f"single-spot A/B compartment score of {sample}, obsm['X_abcompartment'] of the published "
                       "AnnData; columns = autosomal 500-kb bins from 3 Mb without a last bin < 100 kb "
                       "(layout inferred, see uns['ssab_layout_check'])",
        "cell_axis": "obs index = cells index (the sample's spots)", "var_axis": "var bin_id = row of bins"}}
    cd.uns["ssab_layout_check"] = {"sample": sample, "columns": int(X.shape[1]), **summary}
    print(f"  ssAB {sample}: {X.shape[0]:,} spots x {X.shape[1]:,} bins; layout check median |r| "
          + ", ".join(f"{k}: {v['median_abs_r']:.3f}" for k, v in summary.items()))
    return summary


def main(samples: list) -> None:
    by_store: dict = {}
    for s in samples:
        by_store.setdefault(STORE_OF[s], []).append(s)
    for store, secs in by_store.items():
        path = ROOT / f"hicrna_{store}.chromdata.zarr"
        cd = ChromData.read(path)
        stats = dict(cd.uns.get("contacts_stats") or {})
        for sample in secs:
            scool, mcool = CONTACTS / f"{sample}.spots_1Mb.scool", CONTACTS / f"{sample}.bulk.mcool"
            if not scool.exists() or not mcool.exists():
                print(f"{sample}: {scool.name} / {mcool.name} missing (copy them from Oak first) — skipped")
                continue
            cells = cd.cells[cd.cells["section"] == sample]
            with h5py.File(scool, "r") as f:
                names = list(f["cells"].keys())
            have = pd.Index([f"{sample}:{n}" for n in names])
            missing = cells.index.difference(have)
            extra = have.difference(cells.index)
            assert len(extra) == 0, f"{sample}: {len(extra)} maps of spots that are not in the store"
            out = ROOT / f"hicrna_{store}.{sample}.spots_1Mb.scool"
            n_maps, n_pix = rename_scool(scool, out, sample)
            cd.link_scool(out.name, key=f"per_spot.{sample}", cell_name="cell id (<sample>:<barcode>)",
                          genome_assembly=cd.uns["genome_assembly"], bin_size=1_000_000,
                          label=f"{sample}, per spot",
                          source="published .nodups.pairs.gz of GSE311199, "
                                 "example-data/spatial_hicrna/sherlock (cis pairs, MAPQ >= 30)")
            cd.link_cool(f"contacts/{mcool.name}", key=f"bulk.{sample}", label=f"{sample}, all spots (merged)",
                         genome_assembly=cd.uns["genome_assembly"])
            log = json.loads((CONTACTS / f"{sample}.log.json").read_text())
            st = pd.read_csv(CONTACTS / f"{sample}.spot_stats.tsv", sep="\t").set_index("barcode")
            info = {k: log[k] for k in ("lines", "kept", "low_mapq", "no_spot", "n_spots_in_tissue",
                                       "n_spots_with_contacts", "min_mapq") if k in log}
            info.update({"spots_in_store": int(len(cells)), "maps": n_maps, "store_spots_without_map": int(len(missing)),
                         "scool_pixels": n_pix,
                         "contacts_per_spot_median": float(cells["hic_contacts"].median())})
            stats[sample] = info
            print(f"{sample}: linked {n_maps:,} of {len(cells):,} spots ({len(missing)} without a map); "
                  f"pipeline kept {log['kept']:,} of {log['lines']:,} pairs; per-spot contacts median "
                  f"{cells['hic_contacts'].median():,.0f}")
        cd.uns["contacts_stats"] = stats
        if store == "mouse_brain" and "mouse_brain_r1" in secs:
            work = ROOT / "work"
            work.mkdir(exist_ok=True)
            link_ssab(cd, store, "mouse_brain_r1", RAW / "GSM9320916_mouse_brain_r1_HIC_RNA.h5ad.gz", work)
        cd.write(path)
        print("wrote", path.name)


if __name__ == "__main__":
    main(sys.argv[1:] or list(STORE_OF))
