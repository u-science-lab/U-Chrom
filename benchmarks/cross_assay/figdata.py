"""Inputs of the nmeth-bc Fig. 2, the cross-assay analysis (u-chrom-paper manuscripts/nmeth-bc/figures/
make_fig2.py; Extended Data until 2026-10-13), gathered from this benchmark's results:

* ``results/cross_assay.json``, ``results/recon/recon_<dataset>.json``, ``results/recon/loci_<dataset>.json``,
  ``results/recon/loci_all_<dataset>.json``, ``results/recon_summary.json``, ``results/transfer.json``;
* the per-locus and per-pair tables (``biology.py`` outputs: ``locus_effects.parquet``, ``cross_assay_loci_maps.parquet``)
  and the per-cell scores of ``transfer.py`` (``scores_*.parquet``), copied from the Sherlock runs.

Writes ``<paper>/manuscripts/nmeth-bc/figures/results/cross_assay_ed_{classes.json,loci.json,cells.json,
maps.parquet,tracks.parquet,scores.parquet}``.

    python benchmarks/cross_assay/figdata.py --biology DIR --scores DIR [--out DIR]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
RES = HERE / "results"
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))

CLASSES = ["InN", "ExN", "OPC", "Astro", "Oligo", "Micro"]
#: in the order of RECON (the datasets that have a reconstruction), then the two without
CONTACTS = [("tan2021_cortex", "Dip-C"), ("hires_brain", "HiRES"), ("gageseq_mouse_cortex", "GAGE-seq"),
            ("dschic_aging_cortex", "dscHi-C"), ("droplet_hic_mouse_cortex", "Droplet Hi-C"),
            ("schicar_mouse_cortex", "scHiCAR"), ("paired_hic_mouse_cortex", "Paired Hi-C"),
            ("hicrna_mouse_brain", "Spatial Hi-C-RNA")]
RECON = [("tan2021", "dip", "Dip-C", "diploid"), ("hires_brain", "dip", "HiRES", "diploid"),
         ("gageseq_mouse_cortex", "hap", "GAGE-seq", "haploid"), ("dschic_aging_cortex", "hap", "dscHi-C", "haploid"),
         ("droplet_hic_mouse_cortex", "hap", "Droplet Hi-C", "haploid"), ("schicar_mouse_cortex", "hap", "scHiCAR", "haploid")]
IMAGING = [("liu2025_mop", "DNA-MERFISH (Liu 2025)"), ("takei2021_brain_labels", "DNA seqFISH+ (Takei 2021)")]
#: transfer.py labels of the reference reconstructions, in RECON order
TRANSFER = ["Dip-C (Tan), diploid", "HiRES, diploid", "GAGE-seq, haploid", "dscHi-C, haploid", "Droplet Hi-C, haploid",
            "scHiCAR, haploid"]
DEPTH = [("hap", "all"), ("hap_c150k", "150k"), ("hap_c45k", "45k"), ("hap_c20k", "20k")]
MAP_SOURCES = ["imaging (Liu 2025)", "Dip-C (Tan), diploid", "scHiCAR, haploid"]
#: labels of the EMber run's biology outputs -> the method-neutral ones
OLD_LABELS = {"Dip-C (Tan), EMber diploid": "Dip-C (Tan), diploid", "HiRES, EMber diploid": "HiRES, diploid",
              "GAGE-seq, EMber": "GAGE-seq, haploid", "dscHi-C, EMber": "dscHi-C, haploid",
              "Droplet Hi-C, EMber": "Droplet Hi-C, haploid", "scHiCAR, EMber": "scHiCAR, haploid"}


def load(p: Path) -> dict:
    d = json.loads(p.read_text())
    return d.get("results", d)


def ranks(medians: dict) -> dict:
    s = pd.Series({c: v for c, v in medians.items() if c in CLASSES and v is not None})
    return {c: int(r) for c, r in s.rank(ascending=False).items()}


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--biology", type=Path, required=True, help="biology.py --out folder (+ figdata/ inside or next)")
    ap.add_argument("--scores", type=Path, required=True, help="transfer.py --out folder (scores_*.parquet)")
    ap.add_argument("--out", type=Path)
    ap.add_argument("--method", default="nucdyn", choices=["ember", "nucdyn"],
                    help="whose reconstructions: results/ (EMber, 2026-10-11) or results/nucdyn/ (NucDynamics, the paper)")
    a = ap.parse_args()
    RR = RES if a.method == "ember" else RES / "nucdyn"     # the reconstructions' results; RES: contacts, imaging
    import pilot as P
    from _paper import paper_root
    from _record import save

    out = a.out or paper_root() / "manuscripts" / "nmeth-bc" / "figures" / "results"
    xa = load(RES / "cross_assay.json")
    fig_prev = load(Path(out) / "cross_assay_figure.json")
    cliff_prev = {r["dataset"]: r.get("exn_minus_oligo") for r in fig_prev["rows"]}

    # ---- classes: medians, ranks, ExN - Oligo Cliff's delta of every dataset in three groups
    rows = []
    med = xa["across"]["class_medians"]
    for name, label in CONTACTS:
        rows.append({"group": "contacts", "dataset": name, "label": label, "medians": med[name],
                     "ranks": ranks(med[name]), "cliff": cliff_prev.get(name) or {},
                     "pooled_only": name == "paired_hic_mouse_cortex"})
    for ds, v, label, mode in RECON:
        variants = load(RR / "recon" / f"recon_{ds}.json")["variants"]
        r = variants[v]
        m = r["dist_ratio"]["median_by_class"]
        rows.append({"group": "reconstructions", "dataset": ds, "label": f"{label} ({mode})", "medians": m,
                     "ranks": ranks(m), "cliff": r["exn_minus_oligo_cliff"],
                     # the same cells reconstructed haploid (phased data only): what the haploid mode costs
                     "cliff_haploid": variants["hap"]["exn_minus_oligo_cliff"] if v == "dip" else None})
    for name, label in IMAGING:
        rows.append({"group": "imaging", "dataset": name, "label": label, "medians": med[name], "ranks": ranks(med[name]),
                     "cliff": cliff_prev.get(name) or {}})
    M = pd.DataFrame({r["label"]: r["medians"] for r in rows}).T.reindex(columns=CLASSES)
    measured = [r["label"] for r in rows if r["group"] != "reconstructions"]     # the independent datasets
    W = {"all_4": P.kendall_w(M[P.CORE]),
         "all_6": P.kendall_w(M[CLASSES]),
         "measured_4": P.kendall_w(M.loc[measured, P.CORE]),
         "measured_6": P.kendall_w(M.loc[measured, CLASSES]),
         "reconstructions_4": P.kendall_w(M.loc[[r["label"] for r in rows if r["group"] == "reconstructions"], P.CORE])}
    classes = {"rows": rows, "kendall_w": W, "classes": CLASSES}

    # ---- loci: agreement with imaging per reconstruction, ceilings, null; all class pairs
    summ = load(RR / "recon_summary.json")["rows"]
    agree = []
    for ds, v, label, mode in RECON:
        r = next(x for x in summ if x["dataset"] == ds and x["variant"] == v)
        ct = RR / "recon" / f"contacts_{ds}.json"           # the same cells' contacts, no 3D model (stage contacts)
        ct = load(ct)["panels"]["liu2025"] if ct.exists() else None
        agree.append({"dataset": ds, "label": f"{label} ({mode})", "loci_liu": r["loci_liu"],
                      "ceiling_recon": r["ceiling_recon"], "ceiling_liu": r["ceiling_liu"],
                      "disattenuated_resid": r.get("disattenuated_resid"), "disattenuated_pair": r.get("disattenuated_pair"),
                      "n_by_class": r["n_by_class"],
                      "contacts": None if ct is None else {
                          "loci_liu": {k: x["spearman"] for k, x in ct["contacts_vs_imaging"].items()},
                          "n_pairs": ct["contacts_vs_imaging"]["resid"]["n_pairs"],
                          "split_half": {k: x["spearman"] for k, x in ct["contacts_split_half"].items()},
                          "same_pairs": {"n_pairs": ct["same_pairs"][v]["n_pairs"],
                                         "contacts": ct["same_pairs"][v]["contacts"]["resid"]["spearman"],
                                         "recon": ct["same_pairs"][v]["recon"]["resid"]["spearman"]}
                          if v in ct["same_pairs"] else None}})
    shuffled = load(RR / "recon" / "loci_tan2021.json")["variants"]["dip"].get("shuffled_labels", {}).get("liu2025", {})
    pairs = {}
    for ds, v, label, mode in RECON:
        p = RR / "recon" / f"loci_all_{ds}.json"
        if p.exists():
            d = load(p)["pairs"]
            pairs[f"{label} ({mode})"] = {k: x["recon_vs_imaging"]["resid"]["spearman"] for k, x in d.items()}
            pairs["imaging split-half"] = {**pairs.get("imaging split-half", {}),
                                           **{k: x["imaging_split_half"]["resid"]["spearman"] for k, x in d.items()}}
    eff = pd.read_parquet(a.biology / "locus_effects.parquet")
    eff = eff.rename(columns=OLD_LABELS)
    rec_cols = [c for c in TRANSFER if c in eff.columns]
    z = (eff[rec_cols] - eff[rec_cols].mean()) / eff[rec_cols].std()
    eff["consensus of reconstructions"] = z.mean(axis=1)
    from scipy.stats import spearmanr

    locus_rho = {c: float(spearmanr(eff[c], eff["imaging (Liu 2025)"], nan_policy="omit").statistic)
                 for c in rec_cols + ["consensus of reconstructions"]}
    loci = {"agreement": agree, "shuffled_labels_tan_dip": {k: x["spearman"] for k, x in shuffled.items()},
            "class_pairs": pairs, "locus_effect_vs_imaging": locus_rho,
            "liu_split_half": agree[0]["ceiling_liu"]}
    keep = ["chrom", "start", "end", "mid", "imaging (Liu 2025)", *rec_cols, "consensus of reconstructions"]
    eff[keep].reset_index().rename(columns={"index": "locus"}).to_parquet(Path(out) / "cross_assay_ed_tracks.parquet")
    mp = next(p for p in (a.biology / "figdata", a.biology.parent / "figdata") if (p / "cross_assay_loci_maps.parquet").exists())
    maps = pd.read_parquet(mp / "cross_assay_loci_maps.parquet")
    maps["source"] = maps["source"].replace(OLD_LABELS)
    maps[maps["source"].isin(MAP_SOURCES)].to_parquet(Path(out) / "cross_assay_ed_maps.parquet")

    # ---- cells: AUROC in both directions, depth series, per-cell scores
    T = load(RR / "transfer.json")
    tan = load(RR / "recon" / "recon_tan2021.json")["variants"]
    tl = load(RR / "recon" / "loci_tan2021.json")["variants"]
    depth = []
    for v, lab in DEPTH:
        if v not in tan:                               # the NucDynamics run has no subsampled variants
            continue
        key = {"hap": "Dip-C (Tan), haploid"}.get(v, f"Dip-C (Tan), haploid {lab}")
        cis = xa["stage_logs"]["tan"]["cis_contacts_median"] if v == "hap" else float(lab[:-1]) * 1000
        depth.append({"variant": v, "label": lab, "median_cis": cis,
                      "exn_minus_oligo": tan[v]["dist_ratio"]["contrast"]["diff"],
                      "loci_resid": tl[v]["liu2025"]["resid"]["spearman"],
                      "auroc_recon_cells_imaging_sig": T["recon_cells"][key]["imaging"]["auroc"],
                      "auroc_recon_cells_scalar": T["recon_cells"][key]["scalar"]["auroc"],
                      "auroc_imaging_cells": T["imaging_cells"][key]["auroc"]})
    cells = {"recon_cells": {lab: T["recon_cells"][lab] for lab in TRANSFER},
             "imaging_cells": T["imaging_cells"], "depth_tan": depth,
             "diploid_tan": {"loci_resid": tl["dip"]["liu2025"]["resid"]["spearman"],
                             "auroc_imaging_cells": T["imaging_cells"]["Dip-C (Tan), diploid"]["auroc"]}}
    sc = []
    for f in sorted(a.scores.glob("scores_*.parquet")):
        t = pd.read_parquet(f).reset_index()
        cols = [c for c in ("cell_id", "cls", "dataset", "imaging", "own data (other half)", "scalar",
                            "all reconstructions (mean)", "imaging (other half)", "n_pairs") if c in t]
        sc.append(t[cols])
    pd.concat(sc, ignore_index=True).to_parquet(Path(out) / "cross_assay_ed_scores.parquet")
    for name, obj in (("classes", classes), ("loci", loci), ("cells", cells)):
        save(Path(out) / f"cross_assay_ed_{name}.json", obj, script="benchmarks/cross_assay/figdata.py",
             datasets=["see benchmarks/cross_assay/results/MANIFEST.md"], params={"method": a.method})
    print(json.dumps({"kendall_w": {k: round(v.get("W", float("nan")), 3) for k, v in W.items()},
                      "locus_effect_vs_imaging": {k: round(v, 3) for k, v in locus_rho.items()}}, indent=1))


if __name__ == "__main__":
    main()
