"""Takei 2025 cerebellum rep 1 — diagnostic of the published homolog (allele) calls.

The DNA-spot CSVs carry three allele assignments per spot (DBSCAN →
+ local-density-peak filter → + neighbour recovery):
``dbscan_allele``, ``dbscan_ldp_allele`` and ``dbscan_ldp_nbr_allele``
(``read_seqfish_multiomics`` builds traces from the last one by default).
For every (cell, chromosome, allele) trace under each column, this script
computes

* spots and distinct loci per trace, per chromosome (vs the loci in the
  25-kb design, ``LC1-100k…meta.csv``);
* duplicated loci (one homolog should see each locus at most once; two
  merged homologs share loci by chance ≈ n1·n2 / L);
* traces per (cell, chromosome) — a diploid autosome should give two;
* the Spearman correlation between genomic and spatial distance over spot
  pairs (≤ 300 random spots per trace, seed 0) and the fraction of traces with
  ρ < 0.1 / < 0.2;
* for ``dbscan_ldp_nbr_allele``: ρ of the LDP spots alone vs ρ of the spots
  added by neighbour recovery (``dbscan_ldp_allele == -1``).

Diagnosis only — nothing is changed in the loader or the data.

    python benchmarks/fig2/allele_qc.py [--max-spots 300]

Reads ``takei2025_cerebellum/raw/*.csv`` (kept by the builder) and writes
``u-chrom-paper/manuscripts/full/figures/fig2/results/allele_qc.json``.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import rankdata

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _common as C  # noqa: E402

ALLELES = ("dbscan_allele", "dbscan_ldp_allele", "dbscan_ldp_nbr_allele")
COLS = ["rep", "fov", "cellID", "name", "chrom", "x_um", "y_um", "z_um", *ALLELES]
EXAMPLE = ("1_0_34", "chr6", 1)


def spearman_gs(start: np.ndarray, xyz: np.ndarray, rng, cap: int) -> float:
    n = len(start)
    if n < 20:
        return np.nan
    if n > cap:
        idx = rng.choice(n, cap, replace=False)
        start, xyz = start[idx], xyz[idx]
        n = cap
    iu = np.triu_indices(n, 1)
    g = np.abs(start[:, None] - start[None, :])[iu]
    d = np.linalg.norm(xyz[:, None, :] - xyz[None, :, :], axis=-1)[iu]
    rg, rd = rankdata(g), rankdata(d)
    return float(np.corrcoef(rg, rd)[0, 1])


def per_trace(df: pd.DataFrame, col: str, cap: int) -> pd.DataFrame:
    d = df[df[col] >= 0]
    rng = np.random.default_rng(0)
    rows = []
    for (cell, chrom, a), g in d.groupby(["cell_id", "chrom", col], sort=False, observed=True):
        start = g["start"].to_numpy(np.float64)
        xyz = g[["x_um", "y_um", "z_um"]].to_numpy()
        n, nu = len(g), g["name"].nunique()
        rec = {"cell_id": cell, "chrom": chrom, "allele": int(a), "n_spots": n, "n_loci": nu,
               "n_dup_spots": n - nu, "rho": spearman_gs(start, xyz, rng, cap)}
        if col == "dbscan_ldp_nbr_allele":
            core = g["dbscan_ldp_allele"].to_numpy() >= 0
            rec["n_core"] = int(core.sum())
            rec["rho_core"] = spearman_gs(start[core], xyz[core], rng, cap)
            rec["rho_added"] = spearman_gs(start[~core], xyz[~core], rng, cap)
        rows.append(rec)
    return pd.DataFrame(rows)


def q(s: pd.Series) -> dict:
    s = s.dropna()
    if not len(s):
        return {}
    return {k: float(v) for k, v in zip(("p5", "q1", "median", "q3", "p95", "max"),
                                        np.percentile(s, [5, 25, 50, 75, 95, 100]))}


def summarize(t: pd.DataFrame, loci_per_chrom: pd.Series) -> dict:
    tpc = t.groupby(["cell_id", "chrom"], observed=True).size()
    both = t.merge(tpc.rename("traces_in_cell_chrom").reset_index(), on=["cell_id", "chrom"])
    one = both[both.traces_in_cell_chrom == 1]["n_spots"].median()
    two = both[both.traces_in_cell_chrom == 2]["n_spots"].median()
    auto = both[~both.chrom.isin(["chrX", "chrY"])]
    per_chrom = {}
    for chrom, g in t.groupby("chrom", observed=True):
        per_chrom[str(chrom)] = {"n_traces": int(len(g)), "design_loci": int(loci_per_chrom.get(chrom, 0)),
                                 "spots_per_trace": q(g["n_spots"]), "loci_per_trace": q(g["n_loci"]),
                                 "rho_median": float(g["rho"].median()),
                                 "frac_rho_lt_0.1": float((g["rho"] < 0.1).mean())}
    out = {
        "n_traces": int(len(t)), "n_cells": int(t["cell_id"].nunique()),
        "spots_per_trace": q(t["n_spots"]), "loci_per_trace": q(t["n_loci"]),
        "frac_traces_with_duplicate_loci": float((t["n_dup_spots"] > 0).mean()),
        "dup_spot_fraction": q(t["n_dup_spots"] / t["n_spots"]),
        "rho": q(t["rho"]), "frac_rho_lt_0.1": float((t["rho"] < 0.1).mean()),
        "frac_rho_lt_0.2": float((t["rho"] < 0.2).mean()),
        "traces_per_cell_chrom": {str(k): int(v) for k, v in tpc.value_counts().sort_index().items()},
        "autosome_cell_chroms_with_1_trace": float((auto.groupby(["cell_id", "chrom"], observed=True).size() == 1).mean()),
        "median_spots_when_1_trace": float(one), "median_spots_when_2_traces": float(two),
        "per_chrom": per_chrom,
    }
    if "rho_core" in t:
        out["rho_core_ldp_spots"] = q(t["rho_core"])
        out["rho_added_by_neighbour_recovery"] = q(t["rho_added"])
        out["added_spot_fraction"] = q(1 - t["n_core"] / t["n_spots"])
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--max-spots", type=int, default=300)
    args = ap.parse_args()
    raw = sorted((C.TAKEI_DIR / "raw").glob("cerebellum_rep1_pos*.csv"))
    if not raw:
        raise SystemExit("no raw CSVs — run apps/atlas/recipes/build_takei2025_cerebellum.py (without --drop-raw)")
    loci = pd.read_csv(C.TAKEI_DIR / "LC1-100k-09022022-mm10-25kb-meta.csv", usecols=["name", "chrom", "start"])
    loci_per_chrom = loci.groupby("chrom").size()
    traces = {c: [] for c in ALLELES}
    n_spots = {"total": 0, **{c: 0 for c in ALLELES}}
    for p in raw:
        df = pd.read_csv(p, usecols=COLS, low_memory=False)
        df = df.merge(loci[["name", "start"]], on="name", how="inner")
        df["cell_id"] = (df["rep"].astype(int).astype(str) + "_" + df["fov"].astype(int).astype(str) + "_"
                         + df["cellID"].astype(int).astype(str))
        n_spots["total"] += len(df)
        for c in ALLELES:
            n_spots[c] += int((df[c] >= 0).sum())
            traces[c].append(per_trace(df, c, args.max_spots))
            print(f"{p.name} {c}: {len(traces[c][-1])} traces", flush=True)
        del df
    res = {"panel": "supplement (allele QC)", "dataset": "Takei 2025 cerebellum rep 1, all FOVs, raw spot CSVs",
           "files": [p.name for p in raw], "n_spots": n_spots, "max_spots_for_rho": args.max_spots,
           "loci_per_chrom_design": {str(k): int(v) for k, v in loci_per_chrom.items()}, "columns": {}}
    for c in ALLELES:
        t = pd.concat(traces[c], ignore_index=True)
        res["columns"][c] = summarize(t, loci_per_chrom)
        ex = t[(t.cell_id == EXAMPLE[0]) & (t.chrom == EXAMPLE[1]) & (t.allele == EXAMPLE[2])]
        res["columns"][c]["example_1_0_34_chr6_a1"] = ex.iloc[0].to_dict() if len(ex) else None
        s = res["columns"][c]
        print(f"{c:22s} traces {s['n_traces']:6d}  spots/trace median {s['spots_per_trace']['median']:.0f}  "
              f"ρ median {s['rho']['median']:.2f}  ρ<0.1 {s['frac_rho_lt_0.1']:.1%}  dup-loci traces "
              f"{s['frac_traces_with_duplicate_loci']:.1%}  1-trace autosome cell-chroms "
              f"{s['autosome_cell_chroms_with_1_trace']:.1%}")
    C.write_json("allele_qc", res)
    print(C.RESULTS / "allele_qc.json")


if __name__ == "__main__":
    main()
