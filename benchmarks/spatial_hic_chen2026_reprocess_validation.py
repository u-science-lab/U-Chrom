"""Reprocessed spatial Hi-C (Sherlock pipeline, raw reads of GSA CRA016676) vs the authors' results.

For a run whose authors' per-read contacts are public (CRR1161506 = E13.5 section 1):
1. per-spot cis contacts: ours (barcode_stats.tsv) vs the authors' stat_cropped.csv (cis_contact) and vs
   the contacts of the authors' BEDPE (e13_embryo_50um_spots_1Mb.scool, built by
   build_spatial_hic_chen2026.py);
2. bulk maps at 500 kb, per chromosome: Pearson r of the observed / expected matrices and of the
   compartment eigenvectors (ours vs from the authors' BEDPE); and our E1 vs the published ssA/B.
3. the pipeline's read accounting (barcodes, mapping, duplicates).

    python benchmarks/spatial_hic_chen2026_reprocess_validation.py DIR   # DIR = $OAK/.../CRR1161506 copied locally
"""

from __future__ import annotations

from uchrom.datasets import data_dir
import io
import json
import sys
import warnings
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = data_dir() / "spatial_hic_chen2026"
CHROMS = [f"chr{i}" for i in range(1, 20)] + ["chrX"]


def oe(m: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    cov = m.sum(0)
    ok = cov > np.percentile(cov[cov > 0], 5)
    m = m[np.ix_(ok, ok)].astype(float)
    m = m / np.sqrt(np.outer(m.sum(0), m.sum(0)))
    n = len(m)
    idx = np.abs(np.subtract.outer(np.arange(n), np.arange(n)))
    exp = np.array([np.nanmean(np.diagonal(m, k)) for k in range(n)])
    return m / exp[idx], ok


def e1(o: np.ndarray) -> np.ndarray:
    c = np.nan_to_num(np.corrcoef(np.nan_to_num(o)))
    return np.linalg.eigh(c)[1][:, -1]


def main(d: Path) -> None:
    import cooler

    warnings.filterwarnings("ignore", category=RuntimeWarning)
    run = d.name
    log = json.loads((d / f"{run}.log.json").read_text())
    bcs = json.loads((d / f"{run}.barcodes_stats.json").read_text())
    print(f"[3] read pairs {bcs['pairs']:,}; barcodes found {bcs['kept']:,} ({bcs['kept'] / bcs['pairs']:.1%}); "
          f"pairs after mapping/parse {log['lines']:,}; whitelist-corrected + mapq + main chroms + unique "
          f"{log['kept']:,} (bad barcode {log['bad_barcode']:,}, low mapq {log['low_mapq']:,}, "
          f"duplicates {log['duplicates']:,})")
    ours = pd.read_csv(d / f"{run}.barcode_stats.tsv", sep="\t")
    with zipfile.ZipFile(ROOT / "raw" / "code" / "Spatial-Hi-C-v1.0.0.zip") as z:
        st = pd.read_csv(io.BytesIO(z.read(next(n for n in z.namelist() if n.endswith("stat_cropped.csv")))))
    st["barcode_pair"] = st["bc_B"] + "_" + st["bc_A"]
    j = st.merge(ours, on="barcode_pair", how="left")
    # contacts of the authors' BEDPE, per spot (scool of the store: cells "E13_HiC_R1:<col>x<row>")
    sc = ROOT / "e13_embryo_50um_spots_1Mb.scool"
    import h5py

    tot = {}
    with h5py.File(sc, "r") as f:
        for name in f["cells"]:
            tot[name.split(":", 1)[1]] = int(f["cells"][name]["pixels"]["count"][:].sum())
    j["spot"] = (51 - j["iA"]).astype(str) + "x" + j["iB"].astype(str)
    j["authors_bedpe"] = j["spot"].map(tot)
    lg = lambda s: np.log1p(s.astype(float))  # noqa: E731
    print(f"[1] spots {len(j)}: ours cis total {j['cis'].sum():,} vs authors' cis_contact {j['cis_contact'].sum():,} "
          f"(ratio {j['cis'].sum() / j['cis_contact'].sum():.2f}) vs authors' BEDPE {j['authors_bedpe'].sum():,}; "
          f"Pearson r (log) ours~cis_contact {np.corrcoef(lg(j['cis']), lg(j['cis_contact']))[0, 1]:.3f}, "
          f"ours~BEDPE {np.corrcoef(lg(j['cis']), lg(j['authors_bedpe']))[0, 1]:.3f}; Spearman "
          f"{j[['cis', 'cis_contact']].corr(method='spearman').iloc[0, 1]:.3f}")
    ours_m = cooler.Cooler(f"{d / run}.bulk.mcool::/resolutions/500000")
    theirs = cooler.Cooler(f"{ROOT / 'e13_embryo_50um_bulk.mcool'}::/resolutions/500000")
    import anndata as ad

    ssab = ad.read_h5ad(ROOT / "e13_embryo_50um_ssab.h5ad")
    ssab = ssab[ssab.obs["section"] == "E13_HiC_R1"]
    ss = pd.Series(np.nanmean(np.asarray(ssab.X), axis=0), index=ssab.var_names)
    rows = []
    for c in CHROMS:
        a = ours_m.matrix(balance=False).fetch(c)
        b = theirs.matrix(balance=False).fetch(c)
        oa, ok_a = oe(a)
        ob, ok_b = oe(b)
        ok = ok_a & ok_b
        oa2, _ = oe(a)
        # common bins: recompute on the intersection
        ia, ib = np.flatnonzero(ok_a), np.flatnonzero(ok_b)
        common = np.intersect1d(ia, ib)
        sa, sb = np.searchsorted(ia, common), np.searchsorted(ib, common)
        xa, xb = oa[np.ix_(sa, sa)], ob[np.ix_(sb, sb)]
        tri = np.triu_indices(len(common), 1)
        fin = np.isfinite(xa[tri]) & np.isfinite(xb[tri])
        r_oe = np.corrcoef(np.log(xa[tri][fin] + 1e-9), np.log(xb[tri][fin] + 1e-9))[0, 1]
        ea, eb = e1(xa), e1(xb)
        r_e1 = abs(np.corrcoef(ea, eb)[0, 1])
        starts = ours_m.bins().fetch(c)["start"].to_numpy()[common]
        keys = [f"{c}:{s}-{s + 500000}@500kb" for s in starts]
        sv = ss.reindex(keys).to_numpy()
        g = np.isfinite(sv)
        r_ss = abs(np.corrcoef(ea[g], sv[g])[0, 1]) if g.sum() > 10 else np.nan
        rows.append((c, len(common), r_oe, r_e1, r_ss))
    t = pd.DataFrame(rows, columns=["chrom", "bins", "r_oe", "r_e1", "r_e1_vs_ssAB"])
    print(f"[2] bulk 500 kb, {len(t)} chromosomes: O/E Pearson r (log) median {t.r_oe.median():.3f} "
          f"(min {t.r_oe.min():.3f}); |r| of E1 ours vs authors' BEDPE median {t.r_e1.median():.3f} "
          f"(min {t.r_e1.min():.3f}); |r| our E1 vs published ssA/B median {t.r_e1_vs_ssAB.median():.3f}")
    print(t.round(3).to_string(index=False))


if __name__ == "__main__":
    main(Path(sys.argv[1]))
