"""Checks of the reprocessed Chen 2026 per-spot maps that do not use the linking criterion.

The linker picks each run's spot pairing by correlating a spot's compartment profile with the authors'
single-spot A/B (``example-data/link_spatial_hic_chen2026_contacts.py``).  Two checks independent of it:

1. **Tissue image.** The per-spot contact totals of the linked maps, laid out on the section's grid, form
   a coherent picture: Moran's I of log total contacts over the 8-neighbour grid, against the same with the
   spots' maps shuffled among the spots (the value a wrong pairing would give).
2. **Bulk compartments.** Per chromosome (500 kb), the first eigenvector of the bulk map's
   observed / expected correlation against the authors' mean A/B score of the section's spots: median |r| over
   chromosomes (an eigenvector's sign is arbitrary, so |r|).

    python benchmarks/spatial_hic_chen2026_reprocessed.py      # ~2 min; writes benchmarks/results/spatial_hic_chen2026_reprocessed.json
"""

from __future__ import annotations

import json
import warnings
from pathlib import Path

import anndata as ad
import cooler
import h5py
import numpy as np
import pandas as pd

from uchrom import ChromData

warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parents[1]
D = ROOT / "example-data" / "spatial_hic_chen2026"
OUT = ROOT / "benchmarks" / "results" / "spatial_hic_chen2026_reprocessed.json"
STORES = ["e13_embryo_50um", "brain_embryo_20um", "brain_embryo_10um", "cortex_adult_10um", "hippocampus_adult_10um"]


def moran(grid: pd.DataFrame, value: np.ndarray) -> float:
    """Moran's I on the 8-neighbour square grid (rows x cols from the cells' positions)."""
    r = grid["r"].to_numpy(int); c = grid["c"].to_numpy(int)
    v = np.asarray(value, float)
    v = v - np.nanmean(v)
    img = np.full((r.max() + 2, c.max() + 2), np.nan)
    img[r, c] = v
    num, w = 0.0, 0
    for dr, dc in ((0, 1), (1, 0), (1, 1), (1, -1)):
        a = img[: img.shape[0] - dr, max(0, -dc): img.shape[1] - max(0, dc)]
        b = img[dr:, max(0, dc): img.shape[1] - max(0, -dc)]
        ok = np.isfinite(a) & np.isfinite(b)
        num += 2 * np.sum(a[ok] * b[ok]); w += 2 * ok.sum()
    return float((num / w) / np.nanmean(img ** 2))


def e1(clr, chrom: str):
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


def one(store: str, run: str, info: dict, res: dict) -> None:
    cd = ChromData.read(D / f"{store}.chromdata.zarr")
    sec, key, bkey = info["section"], info["key"], info["bulk_key"]
    cells = cd.cells[cd.cells["section"] == sec]
    pos = cd.cell_positions("default").loc[cells.index]
    grid = pd.DataFrame({"r": pos.iloc[:, 1].round().astype(int) - int(pos.iloc[:, 1].min()),
                         "c": pos.iloc[:, 0].round().astype(int) - int(pos.iloc[:, 0].min())}, index=cells.index)
    scool = cd.resolve_link_path(cd.uns["linked_scool"][key]["path"])
    tot = {}
    with h5py.File(scool, "r") as f:
        for name in f["cells"]:
            tot[name] = float(f["cells"][name]["pixels/count"][:].sum())
    t = pd.Series(tot).reindex(grid.index)
    have = t.notna().to_numpy()
    g, v = grid[have], np.log1p(t[have].to_numpy())
    rng = np.random.default_rng(0)
    shuf = np.mean([moran(g, rng.permutation(v)) for _ in range(5)])
    I = moran(g, v)
    # bulk compartments vs the authors' mean A/B of this section's spots
    rec = cd.uns["linked_bin_matrices"]["ssAB"]
    ssab = ad.read_h5ad(cd.resolve_link_path(rec["path"]), backed="r")
    sub = ssab[ssab.obs_names.isin(cells.index), (ssab.var["resolution"] == 500_000).to_numpy()].to_memory()
    ref = pd.Series(np.nanmean(np.asarray(sub.X, float), 0), index=sub.var["chrom"].astype(str) + ":" + sub.var["start"].astype(str))
    mc = cd.resolve_link_path(cd.uns["linked_cool"][bkey]["path"])
    clr = cooler.Cooler(f"{mc}::/resolutions/500000")
    bins = clr.bins()[:]
    rs = {}
    for ch in clr.chromnames:
        if ch in ("chrM", "chrY"):
            continue
        v1 = e1(clr, ch)
        b = bins[bins["chrom"].astype(str) == ch]
        r = ref.reindex(b["chrom"].astype(str) + ":" + b["start"].astype(str)).to_numpy()
        f = np.isfinite(v1[: len(r)]) & np.isfinite(r)
        if f.sum() > 20:
            rs[ch] = float(np.corrcoef(v1[: len(r)][f], r[f])[0, 1])
    res[f"{store}/{sec} ({run})"] = {
        "spots_with_map": int(have.sum()), "spots_in_section": int(len(grid)),
        "moran_log_total_contacts": round(I, 3), "moran_shuffled": round(float(shuf), 3),
        "bulk_E1_vs_ssAB_median_abs_r": round(float(np.median(np.abs(list(rs.values())))), 3),
        "bulk_E1_vs_ssAB_min_abs_r": round(float(np.min(np.abs(list(rs.values())))), 3), "chromosomes": len(rs)}
    x = res[f"{store}/{sec} ({run})"]
    print(f"  {store}/{sec} ({run}): {x['spots_with_map']:,}/{x['spots_in_section']:,} spots; Moran's I {I:.3f} "
          f"(shuffled {shuf:.3f}); bulk E1 vs ssAB median |r| {x['bulk_E1_vs_ssAB_median_abs_r']:.3f} "
          f"(min {x['bulk_E1_vs_ssAB_min_abs_r']:.3f}, {x['chromosomes']} chromosomes)")


if __name__ == "__main__":
    res: dict = {}
    for store in STORES:
        cd = ChromData.read(D / f"{store}.chromdata.zarr", backed=True)
        for run, info in (cd.uns.get("contacts_stats") or {}).get("reprocessed", {}).items():
            if info.get("chosen"):
                one(store, run, info, res)
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(res, indent=1))
    print("wrote", OUT.relative_to(ROOT))
