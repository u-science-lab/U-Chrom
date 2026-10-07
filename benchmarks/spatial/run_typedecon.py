"""In-silico tissue benchmark of cell-type contact-map deconvolution (PREREG §14).

Stages (each writes files the next one reads; ``DIR`` = the run directory)::

    python benchmarks/spatial/run_typedecon.py split  --out DIR/split.tsv
    python benchmarks/spatial/run_typedecon.py cells  --split DIR/split.tsv --data DATA --out DIR/cells [--workers 8]
    python benchmarks/spatial/run_typedecon.py truth  --split DIR/split.tsv --cells DIR/cells --out DIR/truth
    python benchmarks/spatial/run_typedecon.py tissue --split DIR/split.tsv --cells DIR/cells --set dev \\
                                                      --regime low --rep 0 --out DIR/tissues
    python benchmarks/spatial/run_typedecon.py fit    --tissue DIR/tissues/dev_low_r0.npz --truth DIR/truth \\
                                                      --res 1000000 --noise moderate --out DIR/scores \\
                                                      [--variants variants.json] [--spatial] [--save-profiles]
    python benchmarks/spatial/run_typedecon.py aggregate --scores DIR/scores --out DIR/tables

``split``   registered roles of the Tan 2021 cells (``tissue.split_cells``).
``cells``   per cell ``<name>.npy``: (n, 2) int32 50 kb bins of its cis contacts (>= 1 kb, chr1-19, homologs
            merged) and ``cells.tsv`` (n_cis per cell).
``truth``   per resolution ``truth_<res>.npz``: pair counts per type of the TRUTH cells (``P``), of two
            seeded halves of them (``half_a``, ``half_b``) and the all-type truth pseudo-bulk (``ref``).
``tissue``  one in-silico tissue (``tissue.build_tissue``) from the POOL cells of ``--set``; seed =
            ``SEEDS[set] + 100 rep + regime index``.
``fit``     builds the spot matrix at ``--res``, the given composition (``--noise``, seed = tissue seed + 1
            + noise index) and the random control (rows permuted, seed = tissue seed + 7), runs the
            methods, scores them (``scoring.score_profiles``) and writes one JSON per (tissue, res, noise).
``aggregate`` tidy ``scores.csv`` and ``summary.md``: mean over replicates with 95 % bootstrap CIs, paired
            differences TD - baselines.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

import scoring as sc  # noqa: E402
import tissue as ts  # noqa: E402
import typedecon as td  # noqa: E402

SEEDS = {"dev": 140_000, "test": 150_000}
REGIME_INDEX = {"low": 0, "high": 1}
NOISE_INDEX = {"exact": 0, "moderate": 1, "heavy": 2}
HALF_SEED = 20261008
# scoring per resolution: (band in Mb, smoothing radius in bins)
SCORE_CFG = {1_000_000: ((2, 50), 1), 250_000: ((1, 10), 1)}
# spatially varying profiles (secondary S1): P and L6 given as one type "E"; groups = x < 0.55 / >= 0.55
MERGE = {"P": "E", "L6": "E"}
GROUP_X = 0.55


def _types():
    return list(ts.TYPE_CODES)


# --------------------------------------------------------------------------- split / cells

def cmd_split(a):
    d = ts.split_cells()
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    d.to_csv(a.out, sep="\t", index=False)
    print(d.groupby(["type", "role"]).size().unstack())


def _one_cell(args):
    data, name, out = args
    f = Path(out) / f"{name}.npy"
    if f.exists():
        return name, int(np.load(f, mmap_mode="r").shape[0])
    b = ts.cell_bins(ts.cell_file(data, name))
    tmp = f.with_suffix(".tmp.npy")
    np.save(tmp, b)
    tmp.rename(f)
    return name, len(b)


def cmd_cells(a):
    split = pd.read_csv(a.split, sep="\t")
    Path(a.out).mkdir(parents=True, exist_ok=True)
    jobs = [(a.data, n, a.out) for n in split["name"]]
    with ProcessPoolExecutor(a.workers) as ex:
        res = dict(ex.map(_one_cell, jobs))
    split["n_cis"] = split["name"].map(res)
    split.to_csv(Path(a.out) / "cells.tsv", sep="\t", index=False)
    print(split.groupby(["type", "role"]).n_cis.agg(["count", "median", "sum"]))


def load_pool(split: pd.DataFrame, cells_dir, roles) -> dict:
    sub = split[split.role.isin(roles)]
    return {r["name"]: (r["type"], np.load(Path(cells_dir) / f"{r['name']}.npy")) for _, r in sub.iterrows()}


# --------------------------------------------------------------------------- truth

def cmd_truth(a):
    split = pd.read_csv(a.split, sep="\t")
    types = _types()
    base = ts.Layout(ts.BASE_RES)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    truth = split[split.role == "truth"]
    for res in a.res:
        lay = ts.Layout(int(res))
        P = np.zeros((len(types), lay.n_pairs))
        H = np.zeros((2, len(types), lay.n_pairs))
        for k, t in enumerate(types):
            names = sorted(truth[truth.type == t]["name"])
            half = np.random.default_rng(HALF_SEED + k).permutation(len(names)) < len(names) // 2
            for n, h in zip(names, half):
                v = ts.pair_counts(np.load(Path(a.cells) / f"{n}.npy"), lay, base)
                P[k] += v
                H[0 if h else 1, k] += v
        np.savez_compressed(out / f"truth_{int(res)}.npz", P=P, half_a=H[0], half_b=H[1], ref=P.sum(0),
                            types=np.array(types))
        # reliability of the truth: half A vs half B, the registered metrics
        band, smooth = SCORE_CFG.get(int(res), ((2, 50), 1))
        tf = sc.truth_features(_norm(H[1]), lay, band=band, smooth=smooth, P_ref=_norm(P.sum(0)[None])[0])
        rel = sc.score_profiles(_norm(H[0]), tf, lay, band=band, smooth=smooth)
        (out / f"truth_{int(res)}_halves.json").write_text(json.dumps(rel, indent=1))
        print(int(res), "truth contacts per type", P.sum(1).astype(int).tolist(),
              "half-vs-half contrast_r", round(rel["contrast_r"], 3), "comp_r", round(rel["comp_r"], 3))


def _norm(m):
    m = np.asarray(m, float)
    return m / np.maximum(m.sum(-1, keepdims=True), 1e-300)


# --------------------------------------------------------------------------- tissue

def tissue_seed(set_: str, regime: str, rep: int) -> int:
    return SEEDS[set_] + 100 * rep + REGIME_INDEX[regime]


def cmd_tissue(a):
    if a.set == "test" and not a.approved:
        sys.exit("held-back tissues are built only after the freeze is approved (PREREG §14.6): pass --approved")
    split = pd.read_csv(a.split, sep="\t")
    pool = load_pool(split, a.cells, [a.set])
    seed = tissue_seed(a.set, a.regime, a.rep)
    t0 = time.time()
    tis = ts.build_tissue(pool, a.regime, seed, types=_types())
    tis.meta.update({"set": a.set, "rep": a.rep})
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    f = out / f"{a.set}_{a.regime}_r{a.rep}.npz"
    ts.save_tissue(f, tis)
    print(f, tis.meta, f"{time.time() - t0:.1f}s")


# --------------------------------------------------------------------------- fit

DEFAULT_VARIANTS = {"TD": {}}


def _merge_types(comp: np.ndarray, types: list) -> tuple[np.ndarray, list]:
    new = []
    for t in types:
        m = MERGE.get(t, t)
        if m not in new:
            new.append(m)
    out = np.zeros((comp.shape[0], len(new)))
    for k, t in enumerate(types):
        out[:, new.index(MERGE.get(t, t))] += comp[:, k]
    return out, new


def cmd_fit(a):
    tis = ts.load_tissue(a.tissue)
    types = _types()
    T = len(types)
    res = int(a.res)
    lay = ts.Layout(res)
    base = ts.Layout(ts.BASE_RES)
    band, smooth = SCORE_CFG.get(res, ((2, 50), 1))
    tz = np.load(Path(a.truth) / f"truth_{res}.npz")
    P_truth = _norm(tz["P"])
    truth = sc.truth_features(P_truth, lay, band=band, smooth=smooth, P_ref=_norm(tz["ref"][None])[0])
    Y = ts.spot_matrix(tis.spot, tis.bins, tis.n_spots, lay, base)
    true = tis.true_composition(T)
    seed = int(tis.meta["seed"])
    A, cal = ts.observed_composition(true, a.noise, seed + 1 + NOISE_INDEX[a.noise])
    A_rand = ts.permuted_composition(A, seed + 7)
    pair_type = np.zeros((T, lay.n_pairs))
    pidx = lay.pair_index(lay.from_base(tis.bins[:, 0], base), lay.from_base(tis.bins[:, 1], base))
    np.add.at(pair_type, (tis.contact_type(), pidx), 1.0)
    variants = json.loads(Path(a.variants).read_text()) if a.variants else DEFAULT_VARIANTS
    profiles = {"oracle": td.oracle_pool(pair_type)["P"], "dominant": td.dominant_pool(Y, A)["P"],
                "nnls": td.nnls_profiles(Y, A)["P"]}
    info = {}
    for name, kw in variants.items():
        p = td.TDParams(**{k: (np.inf if (k == "refine" and v is None) else v) for k, v in kw.items()})
        t0 = time.time()
        fit = td.fit_td(Y, A, params=p, pair_sep=lay.pair_sep)
        profiles[name] = fit["P"]
        info[name] = {"params": p.to_dict(), "n_iter": fit["n_iter"], "seconds": time.time() - t0,
                      "yield": fit["yield"].tolist()}
        if name == a.random_for:
            profiles["random"] = td.fit_td(Y, A_rand, params=p, pair_sep=lay.pair_sep)["P"]
    rows = []
    for m, P in profiles.items():
        r = sc.score_profiles(P, truth, lay, band=band, smooth=smooth)
        if res == 250_000:
            r.update(sc.score_insulation(P, P_truth, lay))
        rows.append({"method": m, **r})
    meta = {**tis.meta, "res": res, "noise": a.noise, "composition": cal, "types": types,
            "spot_depth_median": float(np.median(np.asarray(Y.sum(1)).ravel())), "variants": info}
    if a.spatial:
        meta["spatial"] = spatial_s1(Y, A, true, types, tis, lay, P_truth, band, smooth, variants, pair_type)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    stem = f"{Path(a.tissue).stem}_{res}_{a.noise}"
    (out / f"{stem}.json").write_text(json.dumps({"meta": meta, "rows": rows}, indent=1, default=float))
    if a.save_profiles:
        np.savez_compressed(out / f"{stem}_profiles.npz", **{k: v for k, v in profiles.items()},
                            types=np.array(types), A=A, true=true)
    print(stem, " ".join(f"{r['method']}:{r['contrast_r']:.3f}/{r['comp_r']:.3f}" for r in rows))


def spatial_s1(Y, A, true, types, tis, lay, P_truth, band, smooth, variants, pair_type) -> dict:
    """Secondary S1: P and L6 given as one type E; E's profile fitted per depth group (x < / >= 0.55);
    score r(L_E,upper - L_E,lower, L_P - L_L6) on the O/E features (truth: TRUTH cells)."""
    Am, mtypes = _merge_types(A, types)
    groups = (tis.xy[:, 0] >= GROUP_X).astype(int)
    e = mtypes.index("E")
    tP, tL = types.index("P"), types.index("L6")
    F_truth = sc.oe_features(P_truth[[tP, tL]], lay, band=band, smooth=smooth)
    target = F_truth[0] - F_truth[1]
    out = {}
    name = next(iter(variants))
    p = td.TDParams(**{k: (np.inf if (k == "refine" and v is None) else v) for k, v in variants[name].items()})
    for gs in (0.0, 0.1, 1.0):
        pg = td.TDParams(**{**p.__dict__, "group_shrink": gs})
        fit = td.fit_td_groups(Y, Am, groups, params=pg, pair_sep=lay.pair_sep)
        Pu, Pl = fit["groups"][0]["P"][e], fit["groups"][1]["P"][e]
        F = sc.oe_features(np.vstack([Pu, Pl]), lay, band=band, smooth=smooth)
        out[f"TD-groups(shrink={gs})"] = sc._r(F[0] - F[1], target)
    # baseline: E-dominant spots pooled per group
    dom = Am.argmax(1) == e
    Pg = []
    for g in (0, 1):
        idx = np.flatnonzero(dom & (groups == g))
        v = np.asarray(Y[idx].sum(0)).ravel()
        Pg.append(v / max(v.sum(), 1))
    F = sc.oe_features(np.vstack(Pg), lay, band=band, smooth=smooth)
    out["dominant-groups"] = sc._r(F[0] - F[1], target)
    # oracle: the true E contacts per group can't be split by type without origin; use origin (P vs L6)
    F = sc.oe_features(_norm(pair_type[[tP, tL]]), lay, band=band, smooth=smooth)
    out["oracle(P vs L6 by origin)"] = sc._r(F[0] - F[1], target)
    out["true_share_L6_in_E_by_group"] = [float((true[groups == g, tL].sum()) /
                                                max(true[groups == g][:, [tP, tL]].sum(), 1e-12)) for g in (0, 1)]
    return out


# --------------------------------------------------------------------------- aggregate

METRICS = ["contrast_r", "comp_r", "oe_r", "ident_accuracy", "ident_margin", "ps_r", "ins_r"]


def cmd_aggregate(a):
    rows = []
    for f in sorted(Path(a.scores).glob("*.json")):
        d = json.loads(f.read_text())
        m = d["meta"]
        for r in d["rows"]:
            row = {"set": m.get("set"), "regime": m["regime"], "rep": m.get("rep"), "res": m["res"],
                   "noise": m["noise"], "method": r["method"], "comp_mae": m["composition"]["mae"],
                   "comp_r_given": m["composition"]["r"]}
            for k in METRICS:
                if k in r:
                    row[k] = r[k]
            for k, t in enumerate(m["types"]):
                row[f"contrast_r.{t}"] = r["contrast_r_type"][k]
                row[f"comp_r.{t}"] = r["comp_r_type"][k]
            rows.append(row)
        if "spatial" in m:
            for k, v in m["spatial"].items():
                if not isinstance(v, list):
                    rows.append({"set": m.get("set"), "regime": m["regime"], "rep": m.get("rep"), "res": m["res"],
                                 "noise": m["noise"], "method": "S1:" + k, "s1_r": v})
    df = pd.DataFrame(rows)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    df.to_csv(out / "scores.csv", index=False)
    lines = ["# Type deconvolution, in-silico tissue: summary", ""]
    keys = ["set", "res", "regime", "noise"]
    for key, g in df[~df.method.str.startswith("S1:")].groupby(keys):
        lines += [f"## {dict(zip(keys, key))}", "", "| method | n | " + " | ".join(METRICS) + " |",
                  "|---|---|" + "---|" * len(METRICS)]
        for m, gm in g.groupby("method"):
            cells = []
            for k in METRICS:
                if k in gm and gm[k].notna().any():
                    mu, lo, hi = sc.bootstrap_ci(gm[k])
                    cells.append(f"{mu:.3f} [{lo:.3f}, {hi:.3f}]")
                else:
                    cells.append("")
            lines.append(f"| {m} | {len(gm)} | " + " | ".join(cells) + " |")
        # paired differences against the first TD variant
        tdm = [m for m in g.method.unique() if m.startswith("TD")]
        if tdm:
            lines += ["", "Paired differences (unit = replicate tissue):", ""]
            for ref in tdm:
                for base in ["dominant", "nnls", "random", "oracle"] + [m for m in tdm if m != ref]:
                    if base not in set(g.method):
                        continue
                    x = g[g.method == ref].set_index("rep")
                    y = g[g.method == base].set_index("rep")
                    parts = []
                    for k in ["contrast_r", "comp_r"]:
                        d = (x[k] - y[k]).dropna()
                        mu, lo, hi = sc.bootstrap_ci(d)
                        parts.append(f"{k} {mu:+.3f} [{lo:+.3f}, {hi:+.3f}]")
                    lines.append(f"* {ref} − {base}: " + "; ".join(parts))
        lines.append("")
    s1 = df[df.method.str.startswith("S1:")]
    if len(s1):
        lines += ["## S1 spatially varying excitatory profile (r of upper − lower vs P − L6)", "",
                  "| set | res | regime | noise | method | n | r |", "|---|---|---|---|---|---|---|"]
        for key, g in s1.groupby(keys + ["method"]):
            mu, lo, hi = sc.bootstrap_ci(g.s1_r)
            lines.append("| " + " | ".join(map(str, key)) + f" | {len(g)} | {mu:.3f} [{lo:.3f}, {hi:.3f}] |")
    (out / "summary.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines[:60]))


# --------------------------------------------------------------------------- main

def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("split"); s.add_argument("--out", required=True); s.set_defaults(fn=cmd_split)
    s = sub.add_parser("cells")
    s.add_argument("--split", required=True); s.add_argument("--data", required=True)
    s.add_argument("--out", required=True); s.add_argument("--workers", type=int, default=4)
    s.set_defaults(fn=cmd_cells)
    s = sub.add_parser("truth")
    s.add_argument("--split", required=True); s.add_argument("--cells", required=True)
    s.add_argument("--out", required=True)
    s.add_argument("--res", type=float, nargs="+", default=[1e6, 2.5e5])
    s.set_defaults(fn=cmd_truth)
    s = sub.add_parser("tissue")
    s.add_argument("--split", required=True); s.add_argument("--cells", required=True)
    s.add_argument("--set", choices=list(SEEDS), required=True)
    s.add_argument("--regime", choices=list(ts.REGIMES), required=True)
    s.add_argument("--rep", type=int, required=True); s.add_argument("--out", required=True)
    s.add_argument("--approved", action="store_true")
    s.set_defaults(fn=cmd_tissue)
    s = sub.add_parser("fit")
    s.add_argument("--tissue", required=True); s.add_argument("--truth", required=True)
    s.add_argument("--res", type=float, default=1e6)
    s.add_argument("--noise", choices=list(ts.NOISE), default="moderate")
    s.add_argument("--variants", help="JSON {name: TDParams kwargs}; first = the one the random control uses")
    s.add_argument("--random-for", default=None)
    s.add_argument("--spatial", action="store_true")
    s.add_argument("--save-profiles", action="store_true")
    s.add_argument("--out", required=True)
    s.set_defaults(fn=cmd_fit)
    s = sub.add_parser("aggregate")
    s.add_argument("--scores", required=True); s.add_argument("--out", required=True)
    s.set_defaults(fn=cmd_aggregate)
    a = ap.parse_args(argv)
    if a.cmd == "fit" and a.random_for is None:
        variants = json.loads(Path(a.variants).read_text()) if a.variants else DEFAULT_VARIANTS
        a.random_for = next(iter(variants))
    a.fn(a)


if __name__ == "__main__":
    main()
