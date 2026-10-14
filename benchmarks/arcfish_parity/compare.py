"""Compare U-Chrom with the authors' ArcFISH on the parity datasets (``run_upstream.py`` / ``run_ours.py``) and
write ``results/parity.json`` (``benchmarks/_record.py``).

    python benchmarks/arcfish_parity/compare.py --runs OUT [--out benchmarks/arcfish_parity/results/parity.json]

Per dataset: identical loci and trace counts; the axis weights, normalised variances (in memory and streaming)
and counts; the TAD per-locus statistics, FDR and boundary calls, and the domains (every level); the loop test
matrices, candidates, clusters (as partitions), summits and loops; the compartment eigenvectors (up to sign) and
A/B calls.  Numbers: the largest relative difference over the finite entries (``rel``), whether the NaN patterns
agree; calls: whether they are identical.
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


def rel(a, b) -> dict:
    a, b = np.asarray(a, dtype=float), np.asarray(b, dtype=float)
    if a.shape != b.shape:
        return {"shape": [list(a.shape), list(b.shape)], "ok": False}
    na, nb = ~np.isfinite(a), ~np.isfinite(b)
    same_nan = bool((na == nb).all())
    f = ~na & ~nb
    if not f.any():
        return {"rel": 0.0, "same_nan": same_nan, "n": 0}
    d = np.abs(a[f] - b[f]) / np.maximum(np.maximum(np.abs(a[f]), np.abs(b[f])), 1e-300)
    return {"rel": float(d.max()), "same_nan": same_nan, "n": int(f.sum()), "n_nan_diff": int((na != nb).sum())}


def same(a, b) -> dict:
    a, b = np.asarray(a), np.asarray(b)
    if a.shape != b.shape:
        return {"identical": False, "shape": [list(a.shape), list(b.shape)]}
    return {"identical": bool((a == b).all()), "n_true": [int(a.sum()), int(b.sum())] if a.dtype == bool else None,
            "n_diff": int((a != b).sum())}


def partition(label) -> set:
    lab = np.asarray(label, dtype=float)
    iu = np.triu_indices_from(lab, 1)
    up = lab[iu]
    groups = {}
    for i, j, v in zip(iu[0], iu[1], up):
        if np.isfinite(v):
            groups.setdefault(v, set()).add((int(i), int(j)))
    return {frozenset(g) for g in groups.values()}


def compare(name: str, runs: Path) -> dict:
    u = np.load(runs / f"{name}.upstream.npz", allow_pickle=False)
    o = np.load(runs / f"{name}.ours.npz", allow_pickle=False)
    r = {"timing_upstream": json.loads(str(u["timing"])), "timing_ours": json.loads(str(o["timing"]))}
    r["loci"] = same(u["starts"], o["starts"])
    r["n_traces"] = [int(u["n_traces"]), int(o["n_traces"])]
    if not r["loci"]["identical"]:
        return r
    r["weight"] = rel(u["weight"], o["weight"])
    r["weight_streaming"] = rel(u["weight"], o["stream_weight"])
    r["norm_var"] = {c: rel(u[f"var_{c}"], o[f"var_{c}"]) for c in "XYZ"}
    r["norm_var_streaming"] = {c: rel(u[f"var_{c}"], o[f"stream_var_{c}"]) for c in "XYZ"}
    r["count"] = {c: same(u[f"count_{c}"], o[f"count_{c}"]) for c in "XYZ"}
    r["count_streaming"] = {c: same(u[f"count_{c}"], o[f"stream_count_{c}"]) for c in "XYZ"}
    r["tad_stats"] = {k: rel(u[f"tad_{k}"], o[f"tad_{k}"]) for k in ("stat", "stat_prox", "pval", "fdr")}
    r["tad_calls"] = {k: same(u[f"tad_{k}"].astype(bool), o[f"tad_{k}"].astype(bool))
                      for k in ("peak", "raw_peak", "fdr_peak")}
    ut = pd.read_csv(runs / f"{name}.upstream.tads.csv")
    ot = pd.read_parquet(runs / f"{name}.ours.tads.parquet")
    uset = {(int(a), int(b), int(c)) for a, b, c in zip(ut["s1"], ut["s2"], ut["level"])}
    oset = {(int(a), int(b), int(c)) for a, b, c in zip(ot["start1"], ot["start2"], ot["level"])}
    r["tad_domains"] = {"identical": uset == oset, "n": [len(uset), len(oset)],
                        "n_level0": [int((ut["level"] == 0).sum()), int((ot["level"] == 0).sum())],
                        "only_upstream": sorted(uset - oset)[:10], "only_ours": sorted(oset - uset)[:10]}
    r["insulation"] = {"score": rel(u["ins_score"], o["ins_score"]),
                       "peak": same(u["ins_peak"].astype(bool), o["ins_peak"].astype(bool))}
    ui = pd.read_csv(runs / f"{name}.upstream.ins.csv")
    oi = pd.read_parquet(runs / f"{name}.ours.ins.parquet")
    us = {(int(a), int(b), int(c)) for a, b, c in zip(ui["s1"], ui["s2"], ui["level"])}
    os_ = {(int(a), int(b), int(c)) for a, b, c in zip(oi["start1"], oi["start2"], oi["level"])}
    r["insulation"]["domains"] = {"identical": us == os_, "n": [len(us), len(os_)]}
    r["loop_stats"] = {k: rel(u[f"loop_{k}"], o[f"loop_{k}"]) for k in ("stat", "pval", "fdr")}
    r["loop_axis_pval"] = rel(u["loop_axis_pval"], o["loop_axis_pval"])
    r["loop_calls"] = {k: same(u[f"loop_{k}"].astype(bool), o[f"loop_{k}"].astype(bool))
                       for k in ("candidate", "summit", "final")}
    r["loop_clusters"] = {"identical": partition(u["loop_label"]) == partition(o["loop_label"]),
                          "n": [len(partition(u["loop_label"])), len(partition(o["loop_label"]))]}
    up_c, our_c = runs / f"{name}.upstream.cpmt.csv", runs / f"{name}.ours.cpmt.parquet"
    if up_c.exists() and our_c.exists():
        uc, oc = pd.read_csv(up_c), pd.read_parquet(our_c)
        eig = {}
        for c in "xyz":
            a, b = uc[f"eig_{c}"].to_numpy(), oc[f"eig_{c}"].to_numpy()
            sgn = 1.0 if float(a @ b) >= 0 else -1.0
            eig[c] = rel(a, sgn * b)
        ab_u = np.where(uc["cpmt"].to_numpy() == 0, "A", "B")
        r["cpmt"] = {"eig": eig, "calls": {"identical": bool((ab_u == oc["compartment"].to_numpy()).all()),
                                           "n_A": [int((ab_u == "A").sum()), int((oc["compartment"] == "A").sum())]}}
    else:
        r["cpmt"] = {"upstream_error": str(u["cpmt_error"]) if "cpmt_error" in u else None,
                     "ours_error": str(o["cpmt_error"]) if "cpmt_error" in o else None}
    return r


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--runs", type=Path, required=True)
    ap.add_argument("--out", type=Path, default=HERE / "results" / "parity.json")
    a = ap.parse_args()
    names = sorted({p.name.split(".")[0] for p in a.runs.glob("*.upstream.npz")}
                   & {p.name.split(".")[0] for p in a.runs.glob("*.ours.npz")})
    res = {n: compare(n, a.runs) for n in names}
    from _record import save

    save(a.out, res, script=__file__, datasets=["takei", "takei2021_rep2", "su2020_chr2_parm", "takei2025_fov0",
                                                "bintu_imr90", "su2020_chr21"],
         params={"upstream": "github.com/hyuyu104/ArcFISH@a21d889321826517876c6c81e7aade10237a10ae"})
    print(json.dumps(res, indent=1, default=str)[:6000])


if __name__ == "__main__":
    main()
