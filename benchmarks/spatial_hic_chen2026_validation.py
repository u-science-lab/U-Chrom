"""Real-data checks of the Chen, Guo et al. 2026 spatial Hi-C stores (build_spatial_hic_chen2026.py).

1. Per-spot contacts of E13.5 section 1 (our .scool, from the per-read BEDPE and the barcode table)
   against the authors' per-spot statistics (test_data/stat_cropped.csv, cis_contact).
2. The published single-spot A/B scores (linked ssA/B AnnData, 500-kb bins, mean over the section's spots) against
   the compartment eigenvector of our bulk map of the same section (500 kb, per chromosome: first
   eigenvector of the correlation of the observed / expected map).  An eigenvector's sign is
   arbitrary, so |r| is reported, plus how many chromosomes already agree in sign.
3. Every store: opens, links resolve, cell positions cover every spot, ssA/B present for every
   Hi-C spot and absent for every RNA spot, linked RNA AnnData aligned with the RNA spots.

    python benchmarks/spatial_hic_chen2026_validation.py
"""

from __future__ import annotations

from uchrom.datasets import data_dir
import glob
import io
import warnings
import sys
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = data_dir()
sys.path.insert(0, str(ROOT))
import build_spatial_hic_chen2026 as build  # noqa: E402

from uchrom import ChromData  # noqa: E402

D = build.ROOT


def spot_counts() -> None:
    import h5py

    cd = ChromData.read(D / "e13_embryo_50um.chromdata.zarr")
    path = cd.resolve_link_path(cd.uns["linked_scool"]["per_spot.E13_HiC_R1"]["path"])
    tot = {}
    with h5py.File(path, "r") as f:
        for name in f["cells"]:
            tot[name.split(":", 1)[1]] = int(f["cells"][name]["pixels"]["count"][:].sum())
    with zipfile.ZipFile(build.CODE_ZIP) as z:
        st = pd.read_csv(io.BytesIO(z.read(next(n for n in z.namelist() if n.endswith("stat_cropped.csv")))))
    st["spot"] = (51 - st["iA"]).astype(str) + "x" + st["iB"].astype(str)
    j = st.set_index("spot").join(pd.Series(tot, name="ours"), how="inner")
    r = np.corrcoef(np.log1p(j["cis_contact"]), np.log1p(j["ours"]))[0, 1]
    rho = j[["cis_contact", "ours"]].corr(method="spearman").iloc[0, 1]
    print(f"[1] spots matched {len(j)}/{len(st)}; per-spot contacts ours / authors' cis_contact: "
          f"median ratio {np.median(j['ours'] / j['cis_contact']):.3f}, Pearson r (log) {r:.3f}, Spearman {rho:.3f}; "
          f"total {j['ours'].sum():,} vs {j['cis_contact'].sum():,}")


def eig_vs_ssab() -> None:
    import cooler

    cd = ChromData.read(D / "e13_embryo_50um.chromdata.zarr")
    mc = cd.resolve_link_path(cd.uns["linked_cool"]["bulk.E13_HiC_R1"]["path"])
    clr = cooler.Cooler(f"{mc}::/resolutions/500000")
    import anndata as ad

    ssab = ad.read_h5ad(cd.resolve_link_path(cd.uns["linked_bin_matrices"]["ssAB"]["path"]))
    ssab = ssab[ssab.obs["section"] == "E13_HiC_R1", (ssab.var["resolution"] == 500_000).to_numpy()]
    ss = np.nanmean(np.asarray(ssab.X), axis=0)
    bins = cd.bins.iloc[ssab.var["bin_id"].to_numpy()].reset_index(drop=True)
    rows = []
    for chrom in build.CHROMS:
        m = clr.matrix(balance=False).fetch(chrom).astype(float)
        b = clr.bins().fetch(chrom)
        cov = m.sum(0)
        ok = cov > np.percentile(cov[cov > 0], 5)
        m = m[np.ix_(ok, ok)]
        m = m / np.sqrt(np.outer(m.sum(0), m.sum(0)))           # coverage-normalised
        n = len(m)
        idx = np.abs(np.subtract.outer(np.arange(n), np.arange(n)))
        exp = np.array([np.nanmean(np.diagonal(m, k)) for k in range(n)])
        oe = m / exp[idx]
        c = np.corrcoef(np.nan_to_num(oe))
        w, v = np.linalg.eigh(np.nan_to_num(c))
        e1 = v[:, -1]
        starts = b["start"].to_numpy()[ok]
        sel = (bins["chrom"] == chrom).to_numpy()
        s = pd.Series(ss[sel], index=bins["start"].to_numpy()[sel]).reindex(starts).to_numpy()
        good = np.isfinite(s)
        rr = np.corrcoef(e1[good], s[good])[0, 1]
        rows.append((chrom, good.sum(), rr))
    t = pd.DataFrame(rows, columns=["chrom", "n", "r"])
    print(f"[2] bulk E1 (500 kb, our mcool) vs mean ssA/B of section 1, per chromosome: median |r| "
          f"{t['r'].abs().median():.3f} (min {t['r'].abs().min():.3f}, {t.loc[t['r'].abs().idxmin(), 'chrom']}); "
          f"{len(t)} chromosomes, {(t['r'] > 0).sum()} with r > 0 before sign alignment")


def stores() -> None:
    for p in sorted(glob.glob(str(D / "*.chromdata.zarr"))):
        cd = ChromData.read(p)
        c = cd.cells
        hic = (c["assay"] == "hic").to_numpy()
        pos = cd.cell_positions()
        import anndata

        ssab = anndata.read_h5ad(cd.resolve_link_path(cd.uns["linked_bin_matrices"]["ssAB"]["path"]))
        x = np.asarray(ssab.X)
        cover = {f"{r // 1000}kb": float(np.isfinite(x[:, (ssab.var["resolution"] == r).to_numpy()]).any(1).mean())
                 for r in sorted(ssab.var["resolution"].unique(), reverse=True)}
        hic_ok = set(ssab.obs_names) == set(c.index[hic])
        ad = cd.linked_adata
        rna_ids = c.index[~hic]
        aligned = ad is not None and ad.n_obs == len(rna_ids) and set(ad.obs_names) == set(rna_ids)
        print(f"[3] {Path(p).name}: {len(c):,} spots, {c['section'].nunique()} sections, links {cd.validate_links() or 'ok'}, "
              f"positions {pos.notna().all(axis=1).mean():.3f}, ssA/B {ssab.n_obs:,} x {ssab.n_vars:,} aligned {hic_ok} "
              f"coverage {cover}, RNA AnnData aligned {aligned}, cellm {len(cd.cellm)} embeddings")


if __name__ == "__main__":
    warnings.filterwarnings("ignore", category=RuntimeWarning)
    spot_counts()
    eig_vs_ssab()
    stores()
