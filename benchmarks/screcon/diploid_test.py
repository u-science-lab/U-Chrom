"""Pre-registered diploid test (PREREG.md §6, "diploid test"): endpoints, strata and decision.

Written and committed with the frozen configuration (tag ``ember-diploid-frozen``) before any test
run.  Inputs (test units only):

* ``--sim``  ``diploid_sim.py score`` JSONs of truth cells 3-5 (both datasets, all 24 conditions);
* ``--real`` the per-cell score directories of ``dip_real.sbatch`` for GM12878 cells 5-7, 9-15, 17.

Method labels: ``ember`` (frozen EMber diploid), ``nucdyn`` (NucDynamics 2017 diploid), ``hickit``.

Endpoints (paired differences, 95 % percentile bootstrap, 10,000 resamples, seed 0):

* **D1** simulation within-chain Spearman (``dist_spearman_cis``, median over models),
  ember − nucdyn; tables averaged per truth cell, truth cells (6) resampled.
* **D2** GM12878 strict held-out cis ROC-AUC (``eval_pairs``, median-distance score),
  ember − nucdyn; unit = cell x fold (33), resampled.
* **D3** GM12878 masked-phase accuracy (all masked ends), ember − hickit; unit = cell (11).

Secondary strata ("worse" = point estimate < −0.01 with the 95 % CI excluding 0, as §5):
simulation within-chain / whole-genome / homolog Spearman (− swap fraction) per dataset, depth,
rc, eps and phased fraction, ember − nucdyn; held-out strict trans / all and cis-2 Mb cis / all
AUC, ember − nucdyn; masked-phase accuracy cis < 10 Mb / cis >= 10 Mb / trans, ember − hickit.
Descriptive only (not thresholded): agreement with the published structures, ensemble precision,
run-to-run agreement, wall time.

Decision: **pass** iff D1 CI > 0, D3 CI > 0, D2 CI lower bound > −0.01, and no secondary stratum
worse.  Otherwise reported as "better on X, equal on Y, worse on Z".
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import numpy as np
import pandas as pd

COND = re.compile(r"^(truth_\d+)_d([\d.]+)_rc([\d.]+)_e([\d.]+)_p([\d.]+)_s(\d+)$")
TEST_TRUTHS = {"truth_3", "truth_4", "truth_5"}
TEST_CELLS = [5, 6, 7, 9, 10, 11, 12, 13, 14, 15, 17]
NB = 10_000


def boot(units: np.ndarray, seed: int = 0) -> tuple[float, float, float]:
    units = np.asarray(units, float)
    units = units[np.isfinite(units)]
    rng = np.random.default_rng(seed)
    m = rng.choice(units, (NB, len(units))).mean(1)
    return float(units.mean()), float(np.percentile(m, 2.5)), float(np.percentile(m, 97.5))


def sim_table(root: Path) -> pd.DataFrame:
    rows = []
    for f in sorted(root.glob("*/*.json")):
        m = COND.match(f.stem)
        if not m or m.group(1) not in TEST_TRUTHS:
            continue
        d = json.loads(f.read_text())
        t, depth, rc, eps, ph, _ = m.groups()
        for meth, r in d["methods"].items():
            mo = r["median_over_models"]
            rows.append({"dataset": f.parent.name, "table": f.stem, "truth": f"{f.parent.name}/{t}", "depth": float(depth),
                         "rc": float(rc), "eps": float(eps), "phased": float(ph), "method": meth,
                         "cis": mo["dist_spearman_cis"], "whole": mo["dist_spearman_whole"],
                         "homolog": r["homolog_spearman"], "neg_swap": -r["swap_frac"], "phase": r.get("phase_acc_all")})
    return pd.DataFrame(rows)


def sim_diff(df, metric, a="ember", b="nucdyn", by=None):
    w = df.pivot_table(index=["dataset", "table", "truth", "depth", "rc", "eps", "phased"], columns="method", values=metric).reset_index()
    w["d"] = w[a] - w[b]
    out = {}
    groups = [("all", w)] if by is None else [(f"{by}={k}", g) for k, g in w.groupby(by)]
    for name, g in groups:
        out[name] = boot(g.groupby("truth")["d"].mean().values)
    return out


def real_tables(root: Path):
    held, mask, full = [], [], []
    for k in TEST_CELLS:
        s = root / f"cell{k:02d}" / "scores"
        for ev in ("eval_pairs", "eval_pairs_cis"):
            for f in sorted(s.glob(f"heldout_fold*_{ev}.json")):
                d = json.loads(f.read_text())
                for meth, r in d["methods"].items():
                    held.append({"cell": k, "fold": f.stem.split("_")[1], "eval": ev, "method": meth,
                                 "cis": r["median"]["cis"]["roc_auc"], "trans": r["median"]["trans"]["roc_auc"],
                                 "all": r["median"]["all"]["roc_auc"], "n_pos": r["median"]["all"]["n_pos"]})
        f = s / "mask.json"
        if f.exists():
            for meth, r in json.loads(f.read_text())["methods"].items():
                ph = r.get("phase_holdback", {})
                mask.append({"cell": k, "method": meth, **{x: ph.get(f"acc_{x}") for x in ("all", "cis_lt10mb", "cis_ge10mb", "trans")},
                             "r_chain_dipc": r["vs"]["dipc"]["dist_r_median"], "r_whole_dipc": r["vs"]["dipc"]["whole_r"]})
        f = s / "full.json"
        if f.exists():
            d = json.loads(f.read_text())
            for meth, r in d["methods"].items():
                full.append({"cell": k, "method": meth, "precision_units": r["precision"].get("rmsd_to_mean_per_unit"),
                             **{f"r_chain_{rn}": v["dist_r_median"] for rn, v in r["vs"].items()},
                             **{f"r_whole_{rn}": v["whole_r"] for rn, v in r["vs"].items()}})
            for kk, v in d["refs_vs_refs"].items():
                if "~" in kk:
                    full.append({"cell": k, "method": f"published {kk}", "r_chain_dipc": v["dist_r_median"]})
    return pd.DataFrame(held), pd.DataFrame(mask), pd.DataFrame(full)


def paired_units(df, keys, metric, a, b):
    w = df.pivot_table(index=keys, columns="method", values=metric)
    return (w[a] - w[b]).values


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sim", required=True)
    ap.add_argument("--real", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    sim = sim_table(Path(args.sim))
    held, mask, full = real_tables(Path(args.real))
    sim.to_csv(out / "test_sim_rows.csv", index=False)
    held.to_csv(out / "test_heldout_rows.csv", index=False)
    mask.to_csv(out / "test_mask_rows.csv", index=False)
    full.to_csv(out / "test_full_rows.csv", index=False)
    res = {"n_sim_tables": int(sim[["dataset", "table"]].drop_duplicates().shape[0]), "n_truths": int(sim.truth.nunique()),
           "n_cells_heldout": int(held.cell.nunique()) if len(held) else 0, "n_cells_mask": int(mask.cell.nunique()) if len(mask) else 0}
    res["D1"] = sim_diff(sim, "cis")["all"]
    strict = held[held["eval"] == "eval_pairs"]
    res["D2"] = boot(paired_units(strict, ["cell", "fold"], "cis", "ember", "nucdyn"))
    res["D3"] = boot(paired_units(mask, ["cell"], "all", "ember", "hickit"))
    sec = {}
    for metric in ("cis", "whole", "homolog", "neg_swap"):
        sec[f"sim.{metric}.all"] = sim_diff(sim, metric)["all"]
        for by in ("dataset", "depth", "rc", "eps", "phased"):
            for k, v in sim_diff(sim, metric, by=by).items():
                sec[f"sim.{metric}.{k}"] = v
    for ev, metrics in (("eval_pairs", ("trans", "all")), ("eval_pairs_cis", ("cis", "trans", "all"))):
        sub = held[held["eval"] == ev]
        for m in metrics:
            sec[f"heldout.{ev}.{m}"] = boot(paired_units(sub, ["cell", "fold"], m, "ember", "nucdyn"))
    for m in ("cis_lt10mb", "cis_ge10mb", "trans"):
        sec[f"phase.{m}"] = boot(paired_units(mask, ["cell"], m, "ember", "hickit"))
    res["secondary"] = sec
    worse = {k: v for k, v in sec.items() if v[0] < -0.01 and v[2] < 0}
    res["worse_strata"] = worse
    res["decision"] = {"D1_ci_above_0": res["D1"][1] > 0, "D3_ci_above_0": res["D3"][1] > 0,
                       "D2_lower_above_-0.01": res["D2"][1] > -0.01, "no_stratum_worse": not worse}
    res["pass"] = all(res["decision"].values())
    # descriptive
    res["descriptive"] = {
        "sim_means": sim.groupby(["dataset", "method"])[["cis", "whole", "homolog", "phase"]].mean().round(4).reset_index().to_dict("records"),
        "heldout_means": held.groupby(["eval", "method"])[["cis", "trans", "all", "n_pos"]].mean().round(4).reset_index().to_dict("records"),
        "mask_means": mask.groupby("method").mean(numeric_only=True).round(4).reset_index().to_dict("records"),
        "full_means": full.groupby("method").mean(numeric_only=True).round(4).reset_index().to_dict("records"),
    }
    (out / "diploid_test.json").write_text(json.dumps(res, indent=1, default=float))
    print(json.dumps({k: res[k] for k in ("n_sim_tables", "n_truths", "n_cells_heldout", "n_cells_mask", "D1", "D2", "D3",
                                          "decision", "pass")}, indent=1, default=float))
    print("worse strata:", json.dumps(worse, default=float))


if __name__ == "__main__":
    main()
