"""Are the shared ExN - Oligo locus differences A/B compartments?  Liu et al. 2025 report stronger A/B compartments in
neurons and megadomains in oligodendrocytes.  Per sequencing dataset (dscHi-C, GAGE-seq: the most oligodendrocytes),
the per-cell maps of ExN and of Oligo are summed into one map each, at matched depth (``sample_cells_by_depth``: the
same number of cis contacts), with ``uchrom.fea.pseudobulk``; their cis eigenvectors (``call_compartments_eig``,
oriented by GC content: E1 > 0 = A) and saddle strengths (``compartment_strength``) are compared, and the locus
differences of imaging and of the reconstructions (``recon.py`` stage loci, ``resid``) are related to them:

* pair type by the ExN E1 signs (AA, AB, BB): the mean difference of each (stronger segregation in neurons -> AB
  pairs farther, AA / BB pairs closer in ExN);
* Spearman of the pair difference with -E1_i E1_j (ExN, Oligo, and their difference), and the R^2 of a linear model
  on both products;
* per locus: the mean difference over its pairs (``biology.py``) against E1 (ExN, Oligo, ExN - Oligo).

    python benchmarks/cross_assay/compartments.py --recon-root $SCRATCH/uchrom-nd/runs/xassay --panel liu2025_panel.parquet \\
        --fasta $UCHROM_DATA/genomes/mm10/mm10.fa.gz --xa-work DIR --out DIR
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))

AUTOS = [f"chr{k}" for k in range(1, 20)]
DATASETS = ["dschic_aging_cortex", "gageseq_mouse_cortex"]
RECON = [("recon_tan", "dip"), ("recon_hires_brain", "dip"), ("recon_gageseq_mouse_cortex", "hap"),
         ("recon_dschic_aging_cortex", "hap"), ("recon_droplet_hic_mouse_cortex", "hap"),
         ("recon_schicar_mouse_cortex", "hap")]
RES = 1_000_000


def class_maps(name: str, xa_work: Path, out: Path, seed: int) -> dict:
    """Matched-depth pseudo-bulk maps of ExN and Oligo (cis), compartments and saddle strength of each."""
    import pilot as P
    import uchrom.datasets as ds
    from uchrom.fea import pseudobulk, sample_cells_by_depth

    P._pandas_compat()
    cd = ds.load(name)
    spec = P.DATASETS[name]
    t = pd.read_parquet(xa_work / f"cells_{name}.parquet")
    t["cls"] = t[spec["column"]].astype(str).map(spec["classes"])
    t = t[t.cls.isin(["ExN", "Oligo"])]
    depth = float(t.groupby("cls")["n_cis"].sum().min()) * 0.95          # the smaller class, almost all of it
    tab = pd.DataFrame({"cls": t["cls"], "n_cis": t["n_cis"]}, index=t.index.astype(str))
    sets = sample_cells_by_depth(tab, "cls", n_contacts=depth, contacts="n_cis", seed=seed)
    summary = pseudobulk(cd, sets["group"], contacts="per_cell", trans=False, out_dir=out / "pseudobulk" / name,
                         key_prefix="pb", workers=6)
    return {"cd": cd, "summary": summary, "depth_cis": depth, "n_cells": sets["group"].value_counts().to_dict()}


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--recon-root", type=Path, required=True)
    ap.add_argument("--panel", type=Path, required=True)
    ap.add_argument("--fasta", type=Path, required=True)
    ap.add_argument("--xa-work", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--results", type=Path, default=HERE / "results")
    ap.add_argument("--seed", type=int, default=0)
    a = ap.parse_args()
    from _record import save
    from scipy.stats import spearmanr
    from uchrom.strc.comp.eig import call_compartments_eig, compartment_strength

    a.out.mkdir(parents=True, exist_ok=True)
    bins = pd.read_parquet(a.panel)
    panel = bins[bins["chrom"].astype(str).isin(AUTOS)][["chrom", "start", "end"]].copy()
    panel["chrom"] = panel["chrom"].astype(str)
    panel["mid"] = (panel["start"] + panel["end"]) // 2
    # the locus differences: imaging and the consensus (z-scored mean) of the reference reconstructions
    img = pd.read_parquet(a.recon_root / "recon_tan" / "loci_liu2025_imaging.parquet")
    Z = []
    for folder, v in RECON:
        p = a.recon_root / folder / f"loci_liu2025_{v}.parquet"
        if p.exists():
            r = pd.read_parquet(p)["resid"]
            Z.append((r - r.mean()) / r.std())
    pairs = pd.DataFrame({"imaging": img["resid"], "consensus": pd.concat(Z, axis=1).mean(axis=1)}).dropna()
    pairs = pairs.join(img[["sep"]])
    res = {"datasets": {}}
    loci_rows = []
    for name in DATASETS:
        m = class_maps(name, a.xa_work, a.out, a.seed)
        cd = m["cd"]
        E, S = {}, {}
        for c in ("ExN", "Oligo"):
            comp = call_compartments_eig(cd, contacts=f"pb.{c}", phasing=str(a.fasta), key_added=f"comp.{c}")
            st = compartment_strength(cd, contacts=f"pb.{c}", compartments=f"comp.{c}", key_added=f"saddle.{c}")
            E[c] = comp
            S[c] = float(st["strength"]) if not isinstance(st, dict) else float(st["strength"])
        # E1 of the bin holding each panel locus's midpoint
        e1 = {}
        for c in ("ExN", "Oligo"):
            t = E[c][["chrom", "start", "E1"]].copy()
            t["chrom"] = t["chrom"].astype(str)
            key = pd.MultiIndex.from_arrays([t["chrom"], t["start"] // RES])
            lk = pd.Series(t["E1"].to_numpy(), index=key)
            e1[c] = pd.Series(lk.reindex(pd.MultiIndex.from_arrays([panel["chrom"], panel["mid"] // RES])).to_numpy(),
                              index=panel.index)
        loci_rows.append(pd.DataFrame({"dataset": name, "E1_ExN": e1["ExN"], "E1_Oligo": e1["Oligo"]}, index=panel.index))
        r = pairs.reset_index()
        ei = {c: e1[c].reindex(r["i"]).to_numpy() for c in e1}
        ej = {c: e1[c].reindex(r["j"]).to_numpy() for c in e1}
        r["P_ExN"], r["P_Oligo"] = ei["ExN"] * ej["ExN"], ei["Oligo"] * ej["Oligo"]
        r["dP"] = r["P_ExN"] - r["P_Oligo"]
        sign_i, sign_j = np.sign(ei["ExN"]), np.sign(ej["ExN"])
        r["type"] = np.where((sign_i > 0) & (sign_j > 0), "AA", np.where((sign_i < 0) & (sign_j < 0), "BB", "AB"))
        r = r.dropna(subset=["P_ExN", "P_Oligo"])
        out = {"depth_cis": m["depth_cis"], "n_cells": m["n_cells"], "saddle_strength": S,
               "E1_ExN_vs_Oligo_spearman": float(spearmanr(e1["ExN"], e1["Oligo"], nan_policy="omit").statistic),
               "E1_ExN_vs_Oligo_per_chrom": {ch: float(spearmanr(e1["ExN"][panel.chrom == ch],
                                                                 e1["Oligo"][panel.chrom == ch], nan_policy="omit").statistic)
                                             for ch in AUTOS},
               "n_pairs": int(len(r))}
        for tgt in ("imaging", "consensus"):
            y = r[tgt].to_numpy()
            X = np.c_[np.ones(len(r)), r["P_ExN"], r["P_Oligo"]]
            beta, *_ = np.linalg.lstsq(X, y, rcond=None)
            r2 = 1 - np.sum((y - X @ beta) ** 2) / np.sum((y - y.mean()) ** 2)
            out[tgt] = {"spearman_minus_P_ExN": float(spearmanr(y, -r["P_ExN"]).statistic),
                        "spearman_minus_P_Oligo": float(spearmanr(y, -r["P_Oligo"]).statistic),
                        "spearman_minus_dP": float(spearmanr(y, -r["dP"]).statistic),
                        "r2_linear_P_ExN_P_Oligo": float(r2), "coef_P_ExN_P_Oligo": [float(beta[1]), float(beta[2])],
                        "mean_by_type": {k: float(v) for k, v in r.groupby("type")[tgt].mean().items()},
                        "n_by_type": {k: int(v) for k, v in r.groupby("type").size().items()}}
        res["datasets"][name] = out
        print(f"[compartments] {name}: {json.dumps({k: out[k] for k in ('saddle_strength', 'E1_ExN_vs_Oligo_spearman')})}"
              f" imaging {json.dumps(out['imaging'])}", flush=True)
        r.to_parquet(a.out / f"pairs_{name}.parquet")
    pd.concat(loci_rows).to_parquet(a.out / "loci_E1.parquet")
    path = save(a.results / "compartments.json", res, script="benchmarks/cross_assay/compartments.py",
                datasets=DATASETS + ["liu2025_mop"],
                params={"resolution": RES, "phasing": "GC content (mm10 FASTA)", "depth": "matched cis contacts",
                        "seed": a.seed, "targets": "recon.py loci resid: imaging; z-mean of the reference reconstructions"})
    print(f"results: {path}", flush=True)


if __name__ == "__main__":
    main()
