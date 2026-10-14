"""One table of the reconstructions of every dataset (``recon.py``; EMber or NucDynamics): per dataset and variant, the ExN - Oligo
difference of the log2 long / short distance ratio (bootstrap CI, Cliff's delta), the class ranking, and how the
ExN - Oligo difference of every cis pair of the Liu 2025 imaging loci agrees with imaging (Spearman: detrended by
separation; per chromosome and separation; the pair-specific part), next to the split-half ceilings.  A split half
uses half the cells, so the full maps' reliability is the Spearman-Brown value 2r / (1 + r); the correlation with
imaging over the square root of the two reliabilities (``disattenuated``) is the share of the reliable signal the
reconstruction recovers (approximate for Spearman correlations).

Inputs: ``<dir>/recon_<dataset>.json`` and ``<dir>/loci_<dataset>.json`` (the ``results`` folders of the Sherlock
runs, copied through the DTN); output ``--out``/recon_summary.{json,md} (default ``results``; the NucDynamics
run: ``results/nucdyn``).

    python benchmarks/cross_assay/recon_summary.py [--out DIR] DIR [DIR ...]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
LABEL = {"tan2021": "Dip-C (Tan 2021), pairs", "tan2021_maps": "Dip-C (Tan 2021), 1-Mb maps",
         "hires_brain": "HiRES (Liu 2023), pairs", "gageseq_mouse_cortex": "GAGE-seq, 1-Mb maps",
         "dschic_aging_cortex": "dscHi-C, 1-Mb maps", "droplet_hic_mouse_cortex": "Droplet Hi-C, 1-Mb maps",
         "schicar_mouse_cortex": "scHiCAR, 1-Mb maps"}
ORDER = list(LABEL)


def load(dirs):
    rec, loci = {}, {}
    for d in dirs:
        for p in Path(d).glob("recon_*.json"):
            rec[p.stem[len("recon_"):]] = json.loads(p.read_text())
        for p in Path(d).glob("loci_*.json"):
            loci[p.stem[len("loci_"):]] = json.loads(p.read_text())
    return rec, loci


def main(argv=None):
    args = list(argv or sys.argv[1:])
    dest = HERE / "results"
    if "--out" in args:
        i = args.index("--out")
        dest = Path(args[i + 1])
        del args[i:i + 2]
    dest.mkdir(parents=True, exist_ok=True)
    dirs = args or [str(HERE / "results")]
    rec, loci = load(dirs)
    rows, imaging = [], {}
    for ds in sorted(set(rec) | set(loci), key=lambda k: ORDER.index(k) if k in ORDER else 99):
        R = rec.get(ds, {}).get("results", {})
        L = loci.get(ds, {}).get("results", {})
        imaging = imaging or R.get("imaging", {})
        for v, r in R.get("variants", {}).items():
            c = r["dist_ratio"].get("contrast", {})
            row = {"dataset": ds, "label": LABEL.get(ds, ds), "variant": v, "n_cells": r["n_cells"],
                   "n_by_class": r["dist_ratio"]["n_by_class"], "exn_minus_oligo": c.get("diff"), "ci95": c.get("ci95"),
                   "cliff": r["exn_minus_oligo_cliff"].get("cliffs_delta"),
                   "astro_minus_oligo_cliff": r["astro_minus_oligo_cliff"].get("cliffs_delta"),
                   "ranking": r["dist_ratio"]["ranking_high_to_low"], "vs_dip": r.get("vs_dip"),
                   "exponent_exn_oligo": [r["exponent_2_50mb"].get("ExN"), r["exponent_2_50mb"].get("Oligo")]}
            lv = L.get("variants", {}).get(v, {}).get("liu2025", {})
            row["loci_liu"] = {k: x["spearman"] for k, x in lv.items()}
            sh = L.get("variants", {}).get(v, {}).get("shuffled_labels", {}).get("liu2025")
            if sh:
                row["loci_liu_shuffled"] = {k: x["spearman"] for k, x in sh.items()} if "resid" in sh else sh
            ceil = L.get("ceiling", {})
            row["ceiling_liu"] = {k: x["spearman"] for k, x in ceil.get("liu2025", {}).items()}
            row["ceiling_recon"] = {k: x["spearman"] for k, x in ceil.get(f"liu2025_{v}", {}).items()}
            sb = lambda r: 2 * r / (1 + r)  # noqa: E731
            for k in ("resid", "pair"):
                a, b, x = row["ceiling_liu"].get(k), row["ceiling_recon"].get(k), row["loci_liu"].get(k)
                if a and b and x is not None:
                    row[f"disattenuated_{k}"] = x / (sb(a) * sb(b)) ** 0.5
            rows.append(row)
    out = {"rows": rows, "imaging": {k: {"exn_minus_oligo": v["dist_ratio"].get("contrast", {}).get("diff"),
                                         "ranking": v["dist_ratio"]["ranking_high_to_low"],
                                         "exponent": v.get("exponent_2_50mb")} for k, v in imaging.items()},
           "sources": {k: {"recon": rec.get(k, {}).get("provenance", {}).get("revision"),
                           "loci": loci.get(k, {}).get("provenance", {}).get("revision")} for k in set(rec) | set(loci)}}
    (dest / "recon_summary.json").write_text(json.dumps(out, indent=1) + "\n")
    f = lambda x, d=3: "" if x is None else f"{x:+.{d}f}"  # noqa: E731
    g = lambda d, k: "" if not d or d.get(k) is None else f"{d[k]:.2f}"  # noqa: E731
    md = ["| data | variant | cells | ExN - Oligo [95% CI] | Cliff | ranking | loci vs Liu: resid / chrom x sep / pair "
          "| recon split-half (resid / pair) | disattenuated (resid / pair) |", "|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        ci = f"{f(r['exn_minus_oligo'])} [{f(r['ci95'][0])}, {f(r['ci95'][1])}]" if r["ci95"] else ""
        L = r["loci_liu"]
        md.append(f"| {r['label']} | {r['variant']} | {r['n_cells']} | {ci} | {f(r['cliff'], 2)} | "
                  f"{' > '.join(r['ranking'])} | {g(L, 'resid')} / {g(L, 'chromband')} / {g(L, 'pair')} | "
                  f"{g(r['ceiling_recon'], 'resid')} / {g(r['ceiling_recon'], 'pair')} | "
                  f"{g(r, 'disattenuated_resid')} / {g(r, 'disattenuated_pair')} |")
    md.append("")
    for k, v in out["imaging"].items():
        md.append(f"- imaging {k}: ExN - Oligo {f(v['exn_minus_oligo'])}, ranking {' > '.join(v['ranking'])}")
    c = rows[0]["ceiling_liu"] if rows else {}
    md.append(f"- Liu 2025 split-half (resid / chrom x sep / pair): {g(c, 'resid')} / {g(c, 'chromband')} / {g(c, 'pair')}")
    (dest / "recon_summary.md").write_text("\n".join(md) + "\n")
    print("\n".join(md))


if __name__ == "__main__":
    main()
