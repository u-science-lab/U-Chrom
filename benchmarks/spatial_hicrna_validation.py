"""Spatial Hi-C-RNA (GSE311199): the reprocessed contacts against the published data.

Run after ``apps/atlas/recipes/build_spatial_hicrna.py`` and ``apps/atlas/recipes/link_spatial_hicrna_contacts.py``::

    python benchmarks/spatial_hicrna_validation.py        # ~5 min; writes benchmarks/results/spatial_hicrna_validation.json

1. **Same spots** (all stores): every published in-tissue spot has RNA and a contact map; per-spot RNA
   UMI vs Hi-C contacts (Spearman) and the spatial coherence of both (Moran's I on the grid).
2. **Bulk compartments between replicates**: compartment E1 (500 kb, per chromosome, from the bulk
   maps) of r1 against r2 of brain / embryo E13.5 / melanoma (median |r| over chromosomes).
3. **Single-spot A/B** (mouse_brain_r1; the published ``X_abcompartment`` linked as ssAB): per spot,
   the compartment profile of the spot's own contacts (each 1-Mb bin: the contact-weighted mean of the
   bulk E1 of the bins it touches) against the spot's published ssAB (both minus their mean over spots);
   median Pearson r over spots, against the same with the spot assignments shuffled.
4. **Hi-C separates the published cell types**: the 15 nearest neighbours of a spot in the PCA of the
   per-spot profiles share its published cell type (TACCO label; clusters) more often than by chance.
5. **E13.5 mask**: share of RNA UMI outside the published tissue mask (the Hi-C pairs outside the mask
   are in the pipeline log: ``no_spot``).
"""

from __future__ import annotations

from uchrom.datasets import data_dir
import json
import sys
import warnings
from pathlib import Path

import h5py
import numpy as np
import pandas as pd
from scipy.stats import spearmanr

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(data_dir()))
from link_spatial_hicrna_contacts import CONTACTS, bulk_e1, mouse_ssab_layout  # noqa: E402
from uchrom import ChromData  # noqa: E402

DATA = data_dir() / "spatial_hicrna"
OUT = ROOT / "benchmarks" / "results" / "spatial_hicrna_validation.json"
warnings.filterwarnings("ignore")


def moran(c: pd.DataFrame, col: str) -> float:
    v = np.log1p(c[col].to_numpy(float))
    n = int(max(c["grid_row"].max(), c["grid_col"].max())) + 1
    img = np.full((n, n), np.nan)
    img[c["grid_row"].astype(int), c["grid_col"].astype(int)] = v - np.nanmean(v)
    a, b = img[:-1] * img[1:], img[:, :-1] * img[:, 1:]
    return float((np.nansum(a) + np.nansum(b)) / (np.isfinite(a).sum() + np.isfinite(b).sum()) / np.nanmean(img ** 2))


def same_spots(res: dict) -> None:
    print("[1] same spots")
    for store in ("hicrna_mouse_brain", "hicrna_mouse_embryo", "hicrna_human_melanoma"):
        cd = ChromData.read(DATA / f"{store}.chromdata.zarr", backed=True)
        linked = set((cd.uns.get("linked_scool") or {}).keys())
        for sec, c in cd.cells.groupby("section", observed=True):
            n_map = int(c["hic_contacts"].gt(0).sum())
            r = {"spots": int(len(c)), "with_hic": n_map, "linked_map": f"per_spot.{sec}" in linked,
                 "spearman_rna_umi_vs_hic_contacts": round(float(spearmanr(c["rna_umi"], c["hic_contacts"]).statistic), 3),
                 "moran_log_rna_umi": round(moran(c, "rna_umi"), 3), "moran_log_hic_contacts": round(moran(c, "hic_contacts"), 3),
                 "hic_contacts_median": float(c["hic_contacts"].median())}
            res.setdefault("same_spots", {})[str(sec)] = r
            print(f"  {sec}: {r['spots']:,} spots, {n_map:,} with Hi-C, map linked {r['linked_map']}; spearman(RNA UMI, Hi-C) "
                  f"{r['spearman_rna_umi_vs_hic_contacts']:.3f}; Moran I RNA {r['moran_log_rna_umi']:.3f} / Hi-C {r['moran_log_hic_contacts']:.3f}")
        for sec, m in (cd.uns.get("spot_mask") or {}).items():
            res.setdefault("mask", {})[sec] = m


def replicates(res: dict) -> None:
    print("[2] bulk compartments between replicates (500 kb, |r| of E1 per chromosome)")
    chroms = {"mouse": [f"chr{i}" for i in range(1, 20)] + ["chrX"], "human": [f"chr{i}" for i in range(1, 23)] + ["chrX"]}
    for a, b, sp in [("mouse_brain_r1", "mouse_brain_r2", "mouse"), ("mouse_embryo_E13.5_r1", "mouse_embryo_E13.5_r2", "mouse"),
                     ("human_melanoma_r1", "human_melanoma_r2", "human")]:
        rs = []
        for c in chroms[sp]:
            ea, eb = (bulk_e1(CONTACTS / f"{s}.bulk.mcool", c) for s in (a, b))
            n = min(len(ea), len(eb))
            f = np.isfinite(ea[:n]) & np.isfinite(eb[:n])
            rs.append(abs(np.corrcoef(ea[:n][f], eb[:n][f])[0, 1]))
        res.setdefault("replicates", {})[f"{a} vs {b}"] = {"median_abs_r": round(float(np.median(rs)), 3),
                                                            "min_abs_r": round(float(np.min(rs)), 3), "chromosomes": len(rs)}
        print(f"  {a} vs {b}: median |r| {np.median(rs):.3f} (min {np.min(rs):.3f}, {len(rs)} chromosomes)")


def spot_profiles(sample: str, store: str, bulk_res: int = 1_000_000):
    """Per spot: contact-weighted mean E1 (1 Mb, bulk) of the bins its cis contacts touch.  Returns
    (cell ids, matrix spots x bins, bins table of the scool)."""
    scool = DATA / f"hicrna_{store}.{sample}.spots_1Mb.scool"
    with h5py.File(scool, "r") as f:
        names = np.asarray(f["chroms/name"][:]).astype(str)
        bins = pd.DataFrame({"chrom": names[f["bins/chrom"][:]], "start": f["bins/start"][:]})
    e1 = np.full(len(bins), np.nan)
    for c in dict.fromkeys(bins["chrom"]):
        if c in ("chrX", "chrY") or not c.startswith("chr"):
            continue
        idx = np.flatnonzero((bins["chrom"] == c).to_numpy())
        e = bulk_e1(CONTACTS / f"{sample}.bulk.mcool", c, bulk_res)
        e1[idx[: len(e)]] = e[: len(idx)]
    chrom_code = pd.factorize(bins["chrom"])[0]
    ids, rows = [], []
    with h5py.File(scool, "r") as f:
        for name in f["cells"]:
            g = f["cells"][name]
            b1, b2 = g["pixels/bin1_id"][:], g["pixels/bin2_id"][:]
            cnt = g["pixels/count"][:].astype(float)
            cis = chrom_code[b1] == chrom_code[b2]
            b1, b2, cnt = b1[cis], b2[cis], cnt[cis]
            e = np.nan_to_num(e1)
            n = len(bins)
            num = np.bincount(b1, cnt * e[b2], n) + np.bincount(b2, cnt * e[b1], n) - np.bincount(b1[b1 == b2], cnt[b1 == b2] * e[b1[b1 == b2]], n)
            den = np.bincount(b1, cnt, n) + np.bincount(b2, cnt, n) - np.bincount(b1[b1 == b2], cnt[b1 == b2], n)
            with np.errstate(invalid="ignore", divide="ignore"):
                rows.append(np.where(den >= 5, num / den, np.nan).astype(np.float32))
            ids.append(name)
    return pd.Index(ids), np.vstack(rows), bins, np.isfinite(e1)


def single_spot_ab(res: dict) -> None:
    print("[3] single-spot A/B (mouse_brain_r1)")
    store, sample = "mouse_brain", "mouse_brain_r1"
    cd = ChromData.read(DATA / f"hicrna_{store}.chromdata.zarr", backed=True)
    import anndata as ad

    rec = cd.uns["linked_bin_matrices"]["ssAB"]
    a = ad.read_h5ad(cd.resolve_link_path(rec["path"]))
    ids, P, bins, ok = spot_profiles(sample, store)
    # the authors' ssAB (500 kb) on the 1-Mb bins of the scool
    key = bins["chrom"] + ":" + (bins["start"] // 1_000_000).astype(str)
    col = pd.Series(np.arange(len(bins)), index=key.values)
    tgt = (a.var["chrom"].astype(str) + ":" + (a.var["start"] // 1_000_000).astype(str)).map(col).to_numpy()
    X = np.asarray(a.X, float)
    S = np.full((X.shape[0], len(bins)), np.nan)
    acc, cnt = np.zeros_like(S), np.zeros(len(bins))
    acc[:] = 0
    for j in np.flatnonzero(~np.isnan(tgt)):
        acc[:, int(tgt[j])] += X[:, j]
        cnt[int(tgt[j])] += 1
    S[:, cnt > 0] = acc[:, cnt > 0] / cnt[cnt > 0]
    row = pd.Series(np.arange(len(a)), index=a.obs_names)
    sel = np.array([i in row.index for i in ids])
    P, S = P[sel], S[row[ids[sel]].to_numpy()]
    use = np.isfinite(S).all(0) & ok & (np.isfinite(P).mean(0) > 0.9)
    P, S = P[:, use], S[:, use]
    P = np.where(np.isfinite(P), P, np.nanmean(P, 0))
    Pc, Sc = P - P.mean(0), S - S.mean(0)
    def rows_r(A, B):
        A, B = A - A.mean(1, keepdims=True), B - B.mean(1, keepdims=True)
        return (A * B).sum(1) / np.maximum(np.sqrt((A ** 2).sum(1) * (B ** 2).sum(1)), 1e-12)
    r = rows_r(Pc, Sc)
    rng = np.random.default_rng(0)
    shuf = rows_r(Pc, Sc[rng.permutation(len(Sc))])
    res["single_spot_ab"] = {"spots": int(len(r)), "bins": int(use.sum()), "median_r": round(float(np.median(r)), 4),
                             "iqr": [round(float(np.percentile(r, 25)), 4), round(float(np.percentile(r, 75)), 4)],
                             "frac_positive": round(float((r > 0).mean()), 3),
                             "shuffled_median_r": round(float(np.median(shuf)), 4),
                             "shuffled_frac_positive": round(float((shuf > 0).mean()), 3)}
    print(f"  {len(r):,} spots x {use.sum()} bins: median r {np.median(r):.3f} (IQR {np.percentile(r, 25):.3f}-{np.percentile(r, 75):.3f}, "
          f"{(r > 0).mean():.0%} > 0); shuffled spots: median {np.median(shuf):.3f} ({(shuf > 0).mean():.0%} > 0)")
    res["_profiles"] = (ids[sel], P)


def cell_types(res: dict) -> None:
    print("[4] Hi-C separates the published cell types (mouse_brain_r1)")
    from sklearn.decomposition import PCA
    from sklearn.neighbors import NearestNeighbors

    ids, P = res.pop("_profiles")
    cd = ChromData.read(DATA / "hicrna_mouse_brain.chromdata.zarr", backed=True)
    c = cd.cells.loc[ids]
    Z = PCA(20, random_state=0).fit_transform((P - P.mean(0)) / np.maximum(P.std(0), 1e-6))
    nn = NearestNeighbors(n_neighbors=16).fit(Z).kneighbors(Z, return_distance=False)[:, 1:]
    rng = np.random.default_rng(0)
    out = {}
    for lab in ("cell_type", "cluster_cellcharter", "cluster_cellcharter_fh"):
        y = c[lab].astype(str).to_numpy()
        agree = float((y[nn] == y[:, None]).mean())
        chance = float(np.mean([(y[nn] == y[rng.permutation(len(y))][:, None]).mean() for _ in range(5)]))
        # the same for the spatial neighbours on the grid (an upper reference: tissue domains are spatially smooth)
        xy = c[["grid_col", "grid_row"]].to_numpy(float)
        sn = NearestNeighbors(n_neighbors=16).fit(xy).kneighbors(xy, return_distance=False)[:, 1:]
        spatial = float((y[sn] == y[:, None]).mean())
        out[lab] = {"hic_knn_agreement": round(agree, 3), "shuffled": round(chance, 3), "spatial_knn_agreement": round(spatial, 3),
                    "labels": int(len(set(y)))}
        print(f"  {lab} ({len(set(y))} labels): 15-NN in the Hi-C profile PCA share the label {agree:.3f} (shuffled {chance:.3f}; "
              f"15 spatial neighbours {spatial:.3f})")
    res["hic_vs_cell_types"] = out


def main() -> None:
    res: dict = {}
    same_spots(res)
    replicates(res)
    single_spot_ab(res)
    cell_types(res)
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(res, indent=1, default=float))
    print("wrote", OUT.relative_to(ROOT))


if __name__ == "__main__":
    main()
