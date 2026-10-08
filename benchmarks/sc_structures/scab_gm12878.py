"""scA/B of single GM12878 cells against the bulk compartments of GM12878 (Rao et al. 2014), chr21.

    .venv/bin/python benchmarks/sc_structures/scab_gm12878.py [--out DIR] [--res 250000 500000 1000000]

Single cells: Tan 2018 Dip-C (``ds.load("tan2018_gm12878")``, 14 cells, ~1 M contacts each, hg19) and Wu 2025
scMicro-C (``ds.load("wu2025_scmicroc")``, the 10 cells passing QC, ~2-3 M contacts, hg38); per-cell maps at
5 kb, summed by ``single_cell_compartments(resolution=...)``.  scA/B with the Dip-C defaults (all contacts, ranks
per cell over the genome) and the scHiCluster form (cis, raw), the CpG frequency of ``hg19_genome`` /
``hg38_genome``.  The scMicro-C chr21 bins are lifted to hg19 (bin midpoints through the UCSC hg38ToHg19 chain,
``hg38_to_hg19_chain``) and averaged per hg19 bin.

Reference: Rao 2014 GM12878 in situ Hi-C chr21 (``rao2014_gm12878_chr21``, 5 kb raw counts, hg19) summed to the
same bin size, ICE-balanced (``uchrom.fea.rebin_map``), E1 by ``call_compartments_eig`` oriented by GC content
(``hg19_chr21``).  Reported per resolution and dataset: Pearson r of each cell's chr21 scA/B with E1 (median,
range), r of the mean over the cells, the CpG track alone vs E1 (the baseline: scA/B averages CpG), the partial
r of the cell mean given CpG, and A/B sign agreement of the mean (rank > median of chr21 bins).

Results: a table on stdout and ``scab_gm12878.json`` in ``--out``.
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "hic_structures"))
from scab_common import cpg_track, load_average, partial_r, pearson, spearman  # noqa: E402


def rao_e1(res: int, out: Path) -> pd.DataFrame:
    import uchrom.datasets as ds
    from uchrom.fea.maps import rebin_map
    from uchrom.strc.comp import call_compartments_eig

    cool = ds.fetch("rao2014_gm12878_chr21")
    path = rebin_map(str(cool), resolution=res, out=out / f"rao_gm12878_chr21_{res // 1000}kb.cool")
    t = call_compartments_eig(str(path), phasing=str(ds.fetch("hg19_chr21")), n_eigs=3)
    return t[t["chrom"] == "chr21"][["chrom", "start", "end", "E1"]].reset_index(drop=True)


def lift_to_hg19(frame: pd.DataFrame, res: int, blocks) -> pd.DataFrame:
    """hg38 chr21 bins (columns of ``frame``: cells x 'chr21:start-end') -> hg19 bins of ``res`` (mean of the
    hg38 bins whose midpoint lifts into it)."""
    from pseudobulk_gm12878 import lift

    cols = [c for c in frame.columns if c.startswith("chr21:")]
    starts = np.array([int(c.split(":")[1].split("-")[0]) for c in cols])
    q = lift(starts + res // 2, blocks)
    ok = q >= 0
    target = (q[ok] // res) * res
    sub = frame[[c for c, k in zip(cols, ok) if k]].T
    sub.index = target
    lifted = sub.groupby(level=0).mean().T
    lifted.columns = [f"chr21:{s}-{s + res}" for s in lifted.columns]
    return lifted


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--out", type=Path, default=Path(tempfile.gettempdir()) / "uchrom_scab_gm12878")
    ap.add_argument("--res", type=int, nargs="*", default=[250_000, 500_000, 1_000_000])
    a = ap.parse_args()
    import uchrom.datasets as ds
    from pseudobulk_gm12878 import chain_blocks

    from uchrom.io.pairs_maps import pairs_chromsizes  # noqa: F401  (sizes come from the maps)
    from uchrom.strc.comp.single_cell import ScABParams, single_cell_compartments

    a.out.mkdir(parents=True, exist_ok=True)
    print(f"load: {load_average()}")
    sets = {"Tan 2018 Dip-C": ("tan2018_gm12878", "hg19", None),
            "Wu 2025 scMicro-C": ("wu2025_scmicroc", "hg38", "qc_pass")}
    blocks = chain_blocks(ds.fetch("hg38_to_hg19_chain"))
    rows, res_json = [], {"load_start": load_average()}
    for res in a.res:
        ref = rao_e1(res, a.out)
        keys = [f"chr21:{s}-{e}" for s, e in zip(ref["start"], ref["end"])]
        E1 = pd.Series(ref["E1"].to_numpy(), index=keys)
        cpg19 = cpg_track("hg19", _sizes("hg19"), res, a.out / "cache")
        cpg = cpg19[cpg19["chrom"] == "chr21"].set_index(cpg19[cpg19["chrom"] == "chr21"].apply(
            lambda r: f"chr21:{r.start}-{r.end}", axis=1))["value"].reindex(keys)
        base = {"resolution": res, "r_cpg_E1": pearson(cpg, E1), "rho_cpg_E1": spearman(cpg, E1),
                "n_bins_E1": int(E1.notna().sum())}
        pooled = {}
        for label, (name, genome, qc) in sets.items():
            cd = ds.load(name)
            ids = list(cd.cells.index) if qc is None else list(cd.cells.index[cd.cells[qc].astype(bool)])
            track = cpg_track(genome, _sizes(genome), res, a.out / "cache")
            chroms = [c for c in track["chrom"].unique() if c != "chrY" and c != "chrM"]
            for form, params in (("Dip-C (all, rank)", ScABParams()),
                                 ("scHiCluster (cis, raw)", ScABParams(contacts="cis", normalize="none"))):
                frame = single_cell_compartments(cd, track=track, cells=ids, resolution=res, params=params,
                                                 chrom=chroms, key_added=None)
                if genome == "hg38":
                    frame = lift_to_hg19(frame, res, blocks)
                X = frame.reindex(columns=keys).astype(float)
                per = [pearson(X.loc[c], E1) for c in X.index]
                mean = X.mean(axis=0)
                pooled.setdefault(form, []).append(X)
                med = np.nanmedian(mean)
                agree = ((mean > med) == (E1 > 0))[mean.notna() & E1.notna()].mean()
                row = {**base, "dataset": label, "form": form, "n_cells": len(X),
                       "r_cell_median": float(np.nanmedian(per)), "r_cell_min": float(np.nanmin(per)),
                       "r_cell_max": float(np.nanmax(per)), "r_mean_E1": pearson(mean, E1),
                       "rho_mean_E1": spearman(mean, E1), "partial_r_mean_E1_given_cpg": partial_r(mean, E1, cpg),
                       "AB_agreement_mean": float(agree), "bins_per_cell_median": float(X.notna().sum(1).median())}
                rows.append(row)
                print(f"{res // 1000:>5} kb  {label:<18s} {form:<24s} {len(X):>2} cells: r per cell median "
                      f"{row['r_cell_median']:.3f} ({row['r_cell_min']:.3f}-{row['r_cell_max']:.3f}); mean r "
                      f"{row['r_mean_E1']:.3f}, partial|CpG {row['partial_r_mean_E1_given_cpg']:.3f}, A/B "
                      f"{agree:.3f}; CpG alone r {base['r_cpg_E1']:.3f}", flush=True)
        for form, xs in pooled.items():
            X = pd.concat(xs)
            mean = X.mean(axis=0)
            rows.append({**base, "dataset": "both (24 cells)", "form": form, "n_cells": len(X),
                         "r_mean_E1": pearson(mean, E1), "rho_mean_E1": spearman(mean, E1),
                         "partial_r_mean_E1_given_cpg": partial_r(mean, E1, cpg)})
    tab = pd.DataFrame(rows)
    cols = ["resolution", "dataset", "form", "n_cells", "r_cell_median", "r_cell_min", "r_cell_max", "r_mean_E1",
            "rho_mean_E1", "partial_r_mean_E1_given_cpg", "AB_agreement_mean", "r_cpg_E1"]
    print()
    print(tab[cols].to_string(index=False, float_format=lambda v: f"{v:.3f}"))
    res_json["rows"] = json.loads(tab.to_json(orient="records"))
    res_json["load_end"] = load_average()
    out = a.out / "scab_gm12878.json"
    out.write_text(json.dumps(res_json, indent=1, default=float))
    print(f"\n-> {out}")


def _sizes(genome: str) -> dict:
    """Chromosome sizes of the per-cell maps of each genome (chr1-22, X)."""
    from uchrom.datasets._load_schic import HG38

    if genome == "hg38":
        return HG38
    from uchrom.datasets._load_schic import HG19

    return HG19


if __name__ == "__main__":
    main()
