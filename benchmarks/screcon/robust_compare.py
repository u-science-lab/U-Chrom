"""Paired comparison of ``robust`` variants with NucDynamics on the DEVELOPMENT set (PREREG.md §2).

Reads the robust score JSONs (``sim/scores/<variant>/<dataset>/<table>.json``,
``heldout/scores/<variant>/cell<c>_fold<f>.json``) and the existing baseline scores
(``runs/screcon/{sim,heldout}/scores``), keeps development units only (truth cells 1-2, cells
1-4; anything else raises), and reports for every variant the P1 / P2 analogues (paired
difference robust - nucdyn_gpu, 95 % bootstrap CI) and every secondary stratum::

    python benchmarks/screcon/robust_compare.py --robust-sim RB/sim/scores --base-sim S/scores \\
        [--robust-heldout RB/heldout/scores --base-heldout H/scores] --out RB/compare
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from aggregate import heldout_rows, sim_rows  # noqa: E402

BASE = "nucdyn_gpu"
CONTEXT = ["hickit", "sic", "orig"]
SIM_KEYS = ["dataset", "truth", "depth_per_mb", "rc_rel", "eps"]
DEV_TRUTHS = {"truth_1", "truth_2"}
DEV_CELLS = {1, 2, 3, 4}


def boot_ci(diff: np.ndarray, groups: np.ndarray | None = None, n_boot: int = 2000, seed: int = 0):
    """Mean and 95 % percentile CI, resampling units (or groups of units)."""
    diff = np.asarray(diff, float)
    rng = np.random.default_rng(seed)
    if groups is None:
        groups = np.arange(len(diff))
    ug = np.unique(groups)
    idx = [np.flatnonzero(groups == g) for g in ug]
    if len(ug) < 2:
        return float(diff.mean()), None, None
    vals = []
    for _ in range(n_boot):
        k = rng.integers(0, len(ug), len(ug))
        vals.append(diff[np.concatenate([idx[i] for i in k])].mean())
    lo, hi = np.percentile(vals, [2.5, 97.5])
    return float(diff.mean()), float(lo), float(hi)


def _fmt(m, lo, hi):
    return f"{m:+.4f} [{lo:+.4f}, {hi:+.4f}]" if lo is not None else f"{m:+.4f}"


def sim_table(robust_dir: Path, base_dir: Path) -> pd.DataFrame:
    rows = []
    for vdir in sorted(p for p in robust_dir.iterdir() if p.is_dir()):
        for r in sim_rows(vdir):
            r["method"] = f"robust:{vdir.name}"
            rows.append(r)
    rows += sim_rows(base_dir)
    df = pd.DataFrame(rows)
    df = df[df["kind"] == "method"]
    bad = set(df.loc[df["method"].str.startswith("robust:"), "truth"]) - DEV_TRUTHS
    if bad:
        raise SystemExit(f"robust scores on non-development truth cells {bad}: stop and report")
    return df[df["truth"].isin(DEV_TRUTHS)].copy()


def sim_report(df: pd.DataFrame, metric: str = "med_dist_spearman_cis") -> tuple[list[str], list[dict]]:
    lines, recs = [], []
    piv = df.pivot_table(index=SIM_KEYS, columns="method", values=metric)
    variants = [c for c in piv.columns if c.startswith("robust:")]
    for v in variants:
        sub = piv[[v, BASE]].dropna()
        if sub.empty:
            continue
        d = (sub[v] - sub[BASE]).to_numpy()
        grp = np.array([f"{a}|{b}" for a, b in zip(sub.index.get_level_values(0), sub.index.get_level_values(1))])
        m, lo, hi = boot_ci(d)
        mg, log_, hig = boot_ci(d, grp)
        lines.append(f"\n## {v}  ({metric}; {len(sub)} paired units)")
        lines.append(f"P2 analogue: mean diff {_fmt(m, lo, hi)} (units); cluster CI (dataset x truth) "
                     f"{_fmt(mg, log_, hig)}; robust {sub[v].mean():.4f} vs {BASE} {sub[BASE].mean():.4f}")
        recs.append({"variant": v, "metric": metric, "stratum": "all", "n": len(sub), "robust": sub[v].mean(),
                     "base": sub[BASE].mean(), "diff": m, "lo": lo, "hi": hi})
        for key in ["dataset", "eps", "depth_per_mb", "rc_rel"]:
            levels = sub.index.get_level_values("dataset" if key == "dataset" else key)
            ds = sub.index.get_level_values("dataset")
            combos = sorted(set(zip(ds, levels))) if key != "dataset" else sorted(set(zip(ds, ds)))
            for dset, lev in combos:
                sel = (ds == dset) & (levels == lev)
                dd = d[sel]
                mm, l2, h2 = boot_ci(dd)
                worse = l2 is not None and hi is not None and mm < -0.01 and h2 < 0
                flag = "  <-- WORSE" if (h2 is not None and h2 < 0) else ("  better" if (l2 is not None and l2 > 0) else "")
                lines.append(f"  {dset:14s} {key}={lev:<6} n={sel.sum():2d}  robust {sub[v][sel].mean():.3f}  "
                             f"base {sub[BASE][sel].mean():.3f}  diff {_fmt(mm, l2, h2)}{flag}")
                recs.append({"variant": v, "metric": metric, "stratum": f"{dset}:{key}={lev}", "n": int(sel.sum()),
                             "robust": sub[v][sel].mean(), "base": sub[BASE][sel].mean(), "diff": mm, "lo": l2,
                             "hi": h2, "worse_gt_0.01": bool(worse)})
    ctx = [c for c in CONTEXT if c in piv.columns]
    if ctx:
        lines.append("\ncontext (dev means): " + ", ".join(f"{c} {piv[c].mean():.3f}" for c in ctx + [BASE]))
    return lines, recs


def heldout_table(robust_dir: Path, base_dir: Path) -> pd.DataFrame:
    rows = []
    for vdir in sorted(p for p in robust_dir.iterdir() if p.is_dir()):
        for r in heldout_rows(vdir):
            if r["method"] == "robust":
                r["method"] = f"robust:{vdir.name}"
            rows.append(r)
    rows += heldout_rows(base_dir)
    df = pd.DataFrame(rows)
    bad = set(df.loc[df["method"].str.startswith("robust:"), "cell"]) - DEV_CELLS
    if bad:
        raise SystemExit(f"robust held-out scores on non-development cells {bad}: stop and report")
    return df[df["cell"].isin(DEV_CELLS)].copy()


def heldout_report(df: pd.DataFrame) -> tuple[list[str], list[dict]]:
    lines, recs = [], []
    band = df[(df["subset"] == "cis_band")]
    p1 = band.groupby(["method", "score", "cell", "fold"])["roc_auc"].mean().unstack("method")
    variants = [c for c in p1.columns if c.startswith("robust:")]
    for v in variants:
        lines.append(f"\n## held-out {v}")
        for score in ("median", "frac"):
            sub = p1.loc[score][[v, BASE]].dropna()
            if sub.empty:
                continue
            d = (sub[v] - sub[BASE]).to_numpy()
            cells = sub.index.get_level_values("cell").to_numpy()
            m, lo, hi = boot_ci(d, cells)
            tag = "P1 analogue" if score == "median" else "frac score"
            lines.append(f"{tag} (mean of 5 cis bands, {score}): {_fmt(m, lo, hi)} over {len(sub)} (cell, fold); "
                         f"robust {sub[v].mean():.4f} vs {BASE} {sub[BASE].mean():.4f}")
            recs.append({"variant": v, "stratum": f"heldout:{score}:bands_mean", "n": len(sub), "robust": sub[v].mean(),
                         "base": sub[BASE].mean(), "diff": m, "lo": lo, "hi": hi})
            strata = [("cis_band", b) for b in ["2-4", "4-16", "16-64", "64-256", "256-inf"]] + [("trans", None), ("cis", None), ("all", None)]
            for subset, b in strata:
                x = df[(df["score"] == score) & (df["subset"] == subset)]
                if b is not None:
                    x = x[x["band"] == b]
                pv = x.pivot_table(index=["cell", "fold"], columns="method", values="roc_auc")
                if v not in pv or BASE not in pv:
                    continue
                pv = pv[[v, BASE]].dropna()
                dd = (pv[v] - pv[BASE]).to_numpy()
                mm, l2, h2 = boot_ci(dd, pv.index.get_level_values("cell").to_numpy())
                flag = "  <-- WORSE" if (h2 is not None and h2 < 0) else ("  better" if (l2 is not None and l2 > 0) else "")
                lines.append(f"  {score:6s} {subset:8s} {b or '':8s} robust {pv[v].mean():.4f} base {pv[BASE].mean():.4f} "
                             f"diff {_fmt(mm, l2, h2)}{flag}")
                recs.append({"variant": v, "stratum": f"heldout:{score}:{subset}:{b}", "n": len(pv), "robust": pv[v].mean(),
                             "base": pv[BASE].mean(), "diff": mm, "lo": l2, "hi": h2})
            # PR-AUC (cis)
            x = df[(df["score"] == score) & (df["subset"] == "cis")]
            pv = x.pivot_table(index=["cell", "fold"], columns="method", values="pr_auc")
            if v in pv and BASE in pv:
                pv = pv[[v, BASE]].dropna()
                dd = (pv[v] - pv[BASE]).to_numpy()
                mm, l2, h2 = boot_ci(dd, pv.index.get_level_values("cell").to_numpy())
                lines.append(f"  {score:6s} PR-AUC cis        robust {pv[v].mean():.4f} base {pv[BASE].mean():.4f} diff {_fmt(mm, l2, h2)}")
        ctx = [c for c in CONTEXT if c in p1.columns]
        lines.append("  context (median score, bands mean): " + ", ".join(f"{c} {p1.loc['median'][c].mean():.4f}" for c in ctx))
    return lines, recs


REAL_KEYS = ["prec_rmsd_to_mean_per_unit", "viol_nd_pct_viol_gt3", "viol_nd_pct_viol_gt4", "viol_sic_pct_viol_gt2units",
             "viol_median_contact_dist_units", "ref_dist_r_median", "ref_rmsd_rel_median"]


def real_report(robust_dir: Path, base_dir: Path, base_label: str = "nucdyn_gpu") -> tuple[list[str], list[dict]]:
    """Precision / violations / vs-GEO on development cells: robust variants vs the baseline, paired by tag."""
    from aggregate import real_rows
    import re
    rows = []
    for vdir in sorted(p for p in robust_dir.iterdir() if p.is_dir()):
        for r in real_rows(vdir):
            if r["method"] == "robust":
                r["method"] = f"robust:{vdir.name}"
                rows.append(r)
            elif r["method"] == base_label:
                rows.append(r)
    rows += [r for r in real_rows(base_dir) if r["method"] == base_label]
    df = pd.DataFrame(rows)
    df["cell"] = df["tag"].map(lambda t: int(re.search(r"cell(\d+)", t).group(1)))
    if set(df.loc[df["method"].str.startswith("robust:"), "cell"]) - DEV_CELLS:
        raise SystemExit("robust real-data scores on non-development cells: stop and report")
    df = df[df["cell"].isin(DEV_CELLS)].drop_duplicates(["tag", "method"])
    lines, recs = [], []
    for v in sorted(m for m in df["method"].unique() if m.startswith("robust:")):
        lines.append(f"\n## real-data checks {v} (dev cells; paired by table)")
        for k in REAL_KEYS:
            if k not in df:
                continue
            pv = df.pivot_table(index="tag", columns="method", values=k)
            if v not in pv or base_label not in pv:
                continue
            pv = pv[[v, base_label]].dropna()
            d = (pv[v] - pv[base_label]).to_numpy()
            m, lo, hi = boot_ci(d, np.array([re.search(r"cell(\d+)", t).group(1) for t in pv.index]))
            lines.append(f"  {k:32s} robust {pv[v].mean():.4f}  {base_label} {pv[base_label].mean():.4f}  diff {_fmt(m, lo, hi)}  (n={len(pv)})")
            recs.append({"variant": v, "stratum": f"real:{k}", "n": len(pv), "robust": pv[v].mean(),
                         "base": pv[base_label].mean(), "diff": m, "lo": lo, "hi": hi})
    return lines, recs


def summary_markdown(recs: list[dict], metric: str = "med_dist_spearman_cis") -> str:
    """One row per variant: P2-dev, the eps strata, the worst simulation stratum, held-out P1 / frac."""
    df = pd.DataFrame(recs)
    if df.empty:
        return ""
    rows = ["| variant | n | P2-dev [95 % CI] | su eps 0 | su eps 0.2 | takei eps 0 | takei eps 0.2 | worst sim stratum | "
            "held-out P1 | held-out frac |", "|---|---|---|---|---|---|---|---|---|---|"]
    sim = df[df.get("metric", pd.Series(dtype=str)) == metric] if "metric" in df else df.iloc[0:0]

    def cell(v, stratum, d=sim):
        x = d[(d["variant"] == v) & (d["stratum"] == stratum)]
        if x.empty:
            return ""
        r = x.iloc[0]
        ci = f" [{r['lo']:+.3f}, {r['hi']:+.3f}]" if pd.notna(r["lo"]) else ""
        return f"{r['diff']:+.4f}{ci}"

    for v in sorted(set(df["variant"])):
        s = sim[sim["variant"] == v]
        n = int(s[s["stratum"] == "all"]["n"].iloc[0]) if not s[s["stratum"] == "all"].empty else 0
        strata = s[(s["stratum"] != "all") & ~s["stratum"].str.contains("dataset=")]
        worst = strata.sort_values("diff").iloc[0] if not strata.empty else None
        w = f"{worst['stratum']} {worst['diff']:+.4f}" if worst is not None else ""
        ho = df[df["variant"] == v]
        rows.append(f"| {v.replace('robust:', '')} | {n} | {cell(v, 'all')} | {cell(v, 'su2020_chr21:eps=0.0')} | "
                    f"{cell(v, 'su2020_chr21:eps=0.2')} | {cell(v, 'takei2021_1mb:eps=0.0')} | "
                    f"{cell(v, 'takei2021_1mb:eps=0.2')} | {w} | {cell(v, 'heldout:median:bands_mean', ho)} | "
                    f"{cell(v, 'heldout:frac:bands_mean', ho)} |")
    return "\n".join(rows)


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--robust-sim", type=Path)
    ap.add_argument("--base-sim", type=Path)
    ap.add_argument("--robust-heldout", type=Path)
    ap.add_argument("--base-heldout", type=Path)
    ap.add_argument("--robust-real", type=Path, help="robust score_real outputs: <dir>/<variant>/<tag>.json")
    ap.add_argument("--base-real", type=Path, help="baseline score_real outputs of the same tables")
    ap.add_argument("--metrics", nargs="+", default=["med_dist_spearman_cis", "med_rmsd_rel", "ens_dist_spearman_cis"])
    ap.add_argument("--out", type=Path)
    args = ap.parse_args(argv)
    lines, recs = [], []
    if args.robust_sim:
        df = sim_table(args.robust_sim, args.base_sim)
        for metric in args.metrics:
            sign = -1 if "rmsd" in metric else 1
            d2 = df.copy()
            d2[metric] = sign * d2[metric]
            if sign < 0:
                lines.append(f"\n(# {metric}: sign flipped, positive = robust better)")
            l, r = sim_report(d2, metric)
            lines += l
            recs += r
        if args.out:
            args.out.mkdir(parents=True, exist_ok=True)
            df.to_csv(args.out / "sim_dev.csv", index=False)
    if args.robust_heldout:
        df = heldout_table(args.robust_heldout, args.base_heldout)
        l, r = heldout_report(df)
        lines += l
        recs += r
        if args.out:
            df.to_csv(args.out / "heldout_dev.csv", index=False)
    if args.robust_real:
        l, r = real_report(args.robust_real, args.base_real)
        lines += l
        recs += r
    text = "\n".join(lines)
    print(text)
    if args.out:
        args.out.mkdir(parents=True, exist_ok=True)
        (args.out / "report.txt").write_text(text)
        (args.out / "summary.md").write_text(summary_markdown(recs, args.metrics[0]) + "\n")
        pd.DataFrame(recs).to_csv(args.out / "strata.csv", index=False)


if __name__ == "__main__":
    main()
