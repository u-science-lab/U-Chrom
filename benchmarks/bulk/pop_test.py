"""Endpoints and decision rule of the EMber-pop test (``PREREG_POP.md`` sections 6-7).

Reads the per-locus / per-pair arrays of ``pop_score.py score`` (``<scores>/<unit>/<cond>/<method>_s<seed>.npz``)
and the run summaries, averages every metric over the seeds of a method, and computes the paired
differences A − B (A = a comparator, B = EMber-pop; losses, positive = EMber-pop better) with a
percentile bootstrap resampling chromosomes as blocks, jointly over the units of a dataset and
independently between datasets; the pooled statistic is the mean over the units::

    python benchmarks/bulk/pop_test.py --root RUNS/pop --units su_test takei_test --conds C1 C2 C3 \\
        --b ember_pop --a igm_sphere igm_ellipsoid --real real_imr90 --out test.json

The same code computes the development preview (``--units su_dev``).
"""

from __future__ import annotations

import argparse
import glob
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import jdump  # noqa: E402
from bulk_metrics import band_label, separation_band  # noqa: E402
from pop_metrics import block_sums_locus, block_sums_pair, chrom_codes  # noqa: E402
from population import Population  # noqa: E402

BANDS = ["cis_0-1Mb", "cis_1-2Mb", "cis_2-5Mb", "cis_5-10Mb", "cis_10-20Mb", "cis_20-50Mb", "cis_>50Mb", "trans"]


def load_runs(d: Path, method: str):
    files = sorted(glob.glob(str(d / f"{method}_s*.npz")))
    arrs = [dict(np.load(f)) for f in files]
    summ = [json.loads(Path(f[:-4] + ".json").read_text()) for f in files]
    return arrs, summ


class Unit:
    """One (unit, condition): truth chromosome codes and the seed-averaged arrays of every method."""

    def __init__(self, root: Path, unit: str, cond: str, methods):
        self.name = f"{unit}/{cond}"
        self.dataset = unit
        T = Population.load(root / unit / "truth.npz")
        self.cc, self.chroms = chrom_codes(T.chrom)
        self.C = len(self.chroms)
        self.T = T
        self.m = {}
        for meth in methods:
            arrs, summ = load_runs(root / unit / "scores" / cond, meth)
            if not arrs:
                continue
            self.m[meth] = {
                "n": len(arrs),
                "rho_w1": np.mean([a["rho_w1"] for a in arrs], 0),
                "pair_w1": np.mean([a["pair_w1"] for a in arrs], 0),
                "pair_i": arrs[0]["pair_i"], "pair_j": arrs[0]["pair_j"],
                "fit_err": np.mean([a["fit_err"] for a in arrs], 0) if "fit_err" in arrs[0] else None,
                "fit_i": arrs[0].get("fit_i"), "fit_j": arrs[0].get("fit_j"),
                "seconds": [((s.get("run") or {}).get("seconds_wall")) for s in summ],
            }

    def blocks(self, key: str, a: str, b: str, mask=None):
        A, B = self.m[a], self.m[b]
        if key == "P1":
            d = A["rho_w1"] - B["rho_w1"]
            return block_sums_locus(d, self.cc, self.C), "locus", float(np.nanmean(A["rho_w1"])), float(np.nanmean(B["rho_w1"]))
        if key == "P2":
            d = A["pair_w1"] - B["pair_w1"]
            if mask is not None:
                d = np.where(mask, d, np.nan)
            i, j = A["pair_i"], A["pair_j"]
            sel = np.ones(len(d), bool) if mask is None else mask
            return (block_sums_pair(d, self.cc[i], self.cc[j], self.C), "pair",
                    float(np.nanmean(A["pair_w1"][sel])), float(np.nanmean(B["pair_w1"][sel])))
        if key == "P3":
            d = A["fit_err"] - B["fit_err"]
            i, j = A["fit_i"], A["fit_j"]
            return block_sums_pair(d, self.cc[i], self.cc[j], self.C), "pair", float(np.mean(A["fit_err"])), float(np.mean(B["fit_err"]))
        raise KeyError(key)


def pooled_bootstrap(items, n_boot: int = 2000, seed: int = 0) -> dict:
    """items: list of (dataset, C, (sums, counts), kind).  Mean over items of the block-weighted
    means; chromosomes resampled per dataset (the same draw for all items of a dataset)."""
    datasets = sorted({it[0] for it in items})
    C = {ds: next(it[1] for it in items if it[0] == ds) for ds in datasets}

    def stat(mult):
        vals = []
        for ds, c, (s, n), kind in items:
            m = mult[ds]
            if kind == "locus":
                vals.append((m * s).sum() / (m * n).sum())
            else:
                iu = np.triu_indices(c)
                w = np.outer(m, m)
                np.fill_diagonal(w, m)          # a cis pair belongs to one chromosome block
                w = w[iu]
                vals.append((w * s[iu]).sum() / (w * n[iu]).sum())
        return float(np.mean(vals))

    est = stat({ds: np.ones(C[ds]) for ds in datasets})
    rng = np.random.default_rng(seed)
    reps = []
    for _ in range(n_boot):
        mult = {ds: np.bincount(rng.integers(0, C[ds], C[ds]), minlength=C[ds]).astype(float) for ds in datasets}
        reps.append(stat(mult))
    lo, hi = np.nanpercentile(reps, [2.5, 97.5])
    return {"estimate": est, "ci": [float(lo), float(hi)], "n_boot": n_boot}


def compare(units, a: str, b: str, n_boot: int) -> dict:
    out = {"A": a, "B": b}
    for key in ("P1", "P2", "P3"):
        items, per = [], {}
        for u in units:
            if a not in u.m or b not in u.m or (key == "P3" and (u.m[a]["fit_err"] is None or u.m[b]["fit_err"] is None)):
                continue
            blk, kind, va, vb = u.blocks(key, a, b)
            items.append((u.dataset, u.C, blk, kind))
            per[u.name] = {"A": va, "B": vb, **pooled_bootstrap([(u.dataset, u.C, blk, kind)], n_boot)}
        if items:
            out[key] = {"pooled": pooled_bootstrap(items, n_boot),
                        "A_mean": float(np.mean([v["A"] for v in per.values()])),
                        "B_mean": float(np.mean([v["B"] for v in per.values()])), "units": per}
    bands = {}
    for u in units:
        if a not in u.m or b not in u.m:
            continue
        band = separation_band(u.T, u.m[a]["pair_i"], u.m[a]["pair_j"])
        for bnd in np.unique(band):
            blk, kind, va, vb = u.blocks("P2", a, b, mask=band == bnd)
            bands.setdefault(band_label(int(bnd)), []).append((u.dataset, u.C, blk, kind, va, vb))
    out["P2_bands"] = {k: {"A": float(np.mean([x[4] for x in v])), "B": float(np.mean([x[5] for x in v])),
                           **pooled_bootstrap([x[:4] for x in v], n_boot)} for k, v in bands.items()}
    return out


def decide(sim: dict, real: dict | None, runtime_ratio: float | None, margin_p3: float = 0.2, stratum_rel: float = 0.05) -> dict:
    """PREREG section 7 against one comparator (sim / real: outputs of ``compare``)."""
    res = {}
    c1 = all(k in sim and sim[k]["pooled"]["ci"][0] > 0 for k in ("P1", "P2"))
    res["1_P1_P2_better"] = c1
    p3 = sim.get("P3")
    res["2_P3_noninferior"] = bool(p3 and p3["pooled"]["ci"][0] > -margin_p3 * p3["A_mean"])
    if real is not None:
        res["3_real_not_worse"] = all(k in real and real[k]["pooled"]["ci"][1] >= 0 for k in ("P1", "P2"))
    worse = []
    for key in ("P1", "P2", "P3"):
        for name, v in (sim.get(key) or {}).get("units", {}).items():
            if v["estimate"] < -stratum_rel * v["A"] and v["ci"][1] < 0:
                worse.append(f"{key} {name}")
    for name, v in sim.get("P2_bands", {}).items():
        if v["estimate"] < -stratum_rel * v["A"] and v["ci"][1] < 0:
            worse.append(f"P2 {name}")
    res["4_no_stratum_worse"] = not worse
    res["4_worse_strata"] = worse
    if runtime_ratio is not None:
        res["5_runtime_ratio"] = runtime_ratio
        res["5_runtime_ok"] = runtime_ratio <= 3.0
    res["better"] = all(v for k, v in res.items() if k[0].isdigit() and isinstance(v, bool))
    return res


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", required=True, help="directory holding <unit>/truth.npz and <unit>/scores/<cond>/")
    ap.add_argument("--units", nargs="+", required=True)
    ap.add_argument("--conds", nargs="+", default=["C1", "C2", "C3"])
    ap.add_argument("--b", required=True, help="EMber-pop method name (the B side)")
    ap.add_argument("--a", nargs="+", required=True, help="comparators (IGM-sphere first)")
    ap.add_argument("--real", default=None, help="real unit (truth.npz + scores/real/)")
    ap.add_argument("--runtime-unit", default=None, help="unit/cond whose wall times give the runtime ratio")
    ap.add_argument("--n-boot", type=int, default=2000)
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    root = Path(a.root)
    methods = [a.b] + a.a
    units = [Unit(root, u, c, methods) for u in a.units for c in a.conds if (root / u / "scores" / c).exists()]
    real = [Unit(root, a.real, "real", methods)] if a.real else []
    out = {"units": [u.name for u in units], "real": a.real, "comparisons": {}}
    for comp in a.a:
        sim = compare(units, comp, a.b, a.n_boot)
        rl = compare(real, comp, a.b, a.n_boot) if real else None
        ratio = None
        if a.runtime_unit:
            u = next((x for x in units if x.name == a.runtime_unit), None)
            if u and a.b in u.m and comp in u.m:
                sb = [s for s in u.m[a.b]["seconds"] if s]
                sa = [s for s in u.m[comp]["seconds"] if s]
                if sb and sa:
                    ratio = float(np.median(sb) / np.median(sa))
        out["comparisons"][comp] = {"simulation": sim, "real": rl, "decision": decide(sim, rl, ratio)}
        print(f"== {a.b} vs {comp}")
        for key in ("P1", "P2", "P3"):
            if key in sim:
                p = sim[key]["pooled"]
                print(f"  {key}: {comp} {sim[key]['A_mean']:.4f}  {a.b} {sim[key]['B_mean']:.4f}  "
                      f"diff {p['estimate']:+.4f} [{p['ci'][0]:+.4f}, {p['ci'][1]:+.4f}]")
        if rl:
            for key in ("P1", "P2", "P3"):
                if key in rl:
                    p = rl[key]["pooled"]
                    print(f"  real {key}: diff {p['estimate']:+.4f} [{p['ci'][0]:+.4f}, {p['ci'][1]:+.4f}]")
        print("  decision:", json.dumps(out["comparisons"][comp]["decision"]))
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(jdump(out))


if __name__ == "__main__":
    main()
