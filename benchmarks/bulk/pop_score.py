"""Score populations of the EMber-pop benchmark against a held-out truth (``PREREG_POP.md`` §5-6).

``score``  one population (``pop_run.py`` output directory, or a Population ``.npz`` such as the bulk
           cells = the ceiling) vs the truth; writes ``<out>.npz`` (per-locus / per-pair arrays) and
           ``<out>.json`` (summaries)::

               python benchmarks/bulk/pop_score.py score --truth SIM/truth.npz --input SIM/C1.npz \\
                   --pop RUNS/C1/igm_sphere_s1 --out SCORES/C1/igm_sphere_s1

``compare``  paired differences A - B (losses; positive = B better) of the endpoints, averaged over the
           seeds of each method and over units, with chromosome-block bootstrap CIs::

               python benchmarks/bulk/pop_score.py compare --scores SCORES --units C1 C2 C3 \\
                   --a igm_sphere --b ember_pop --out cmp.json
"""

from __future__ import annotations

import argparse
import glob
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import jdump, load_preprocess  # noqa: E402
from bulk_metrics import all_pairs, separation_band, band_label  # noqa: E402
from pop_metrics import (block_sums_locus, block_sums_pair, bootstrap_mean, chrom_codes,  # noqa: E402
                         score_arrays)
from population import Population, load_any  # noqa: E402

N_PAIRS = 50000


def _loci(T: Population) -> pd.DataFrame:
    return pd.DataFrame({"chrom": T.chrom, "start": T.start, "end": T.end})


def cmd_score(a) -> None:
    T = Population.load(a.truth)
    pm = load_preprocess().ProbabilityMatrix.load(a.input)
    prov = pm.provenance.get("simulation", pm.provenance)
    p = Path(a.pop)
    rc = a.rc_nm or prov.get("rc_nm_median")
    if rc is None and p.is_dir() and (p / "population.npz").exists():
        # real input: the model's own contact distance 2 (r_i + r_j) at the median bead radius
        rc = 4.0 * float(np.median(np.load(p / "population.npz")["radii"]))
    if rc is None:
        raise SystemExit("contact distance unknown: pass --rc-nm")
    rc = float(rc)
    if p.is_dir():
        R = load_any(p / "population.npz", _loci(T))
        summ_run = json.loads((p / "summary.json").read_text()) if (p / "summary.json").exists() else {}
        fit = np.load(p / "fit.npz") if (p / "fit.npz").exists() else None
    else:
        R = load_any(p, _loci(T))
        summ_run, fit = {}, None
    i, j = all_pairs(T, N_PAIRS, 0)
    arr, summ = score_arrays(R, T, i=i, j=j, rc=rc, territory_structures=a.territory_structures)
    arr["pair_i"], arr["pair_j"] = i, j
    if fit is not None:
        err = np.abs(fit["model"] - fit["f"])
        arr["fit_err"], arr["fit_i"], arr["fit_j"] = err, fit["i"], fit["j"]
        summ["P3_fit_mae"] = float(err.mean())
        summ["P3_fit_mae_cis"] = float(err[fit["intra"]].mean())
        summ["P3_fit_mae_trans"] = float(err[~fit["intra"]].mean()) if (~fit["intra"]).any() else None
    elif a.ceiling_fit:
        # the bulk cells themselves: their contact frequency at rc vs the input on the input pairs
        from pop_metrics import contact_freq_pairs
        P = pm.probabilities.tocoo()
        k = (P.row < P.col) & (P.data >= 0.01)
        fi, fj, fv = P.row[k], P.col[k], P.data[k]
        intra = T.chrom[fi] == T.chrom[fj]
        k2 = ~intra | (fj - fi > 1)
        fi, fj, fv, intra = fi[k2], fj[k2], fv[k2], intra[k2]
        cf = contact_freq_pairs(R, fi, fj, rc)
        err = np.abs(cf - fv)
        arr["fit_err"], arr["fit_i"], arr["fit_j"] = err, fi, fj
        summ["P3_fit_mae"] = float(err.mean())
    summ["run"] = {k: summ_run.get(k) for k in ("method", "seconds_wall", "n_rounds", "engine", "n_structures",
                                               "seed", "steps_scale", "fit")}
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(str(out) + ".npz", **arr)
    Path(str(out) + ".json").write_text(jdump(summ))
    keys = ["P1_rho_w1_mean", "P2_pair_w1_mean", "P2_cis", "P2_trans", "P3_fit_mae", "rho_mean_spearman",
            "cv_spearman", "territory_mae", "shape_r31_median_R", "shape_r31_median_T", "scale"]
    print(jdump({k: summ.get(k) for k in keys}), flush=True)


# --------------------------------------------------------------------------- compare

def _load(scores: Path, unit: str, method: str):
    files = sorted(glob.glob(str(scores / unit / f"{method}_s*.npz"))) or sorted(glob.glob(str(scores / unit / f"{method}.npz")))
    return [dict(np.load(f)) for f in files], files


def endpoint_blocks(arrs_a, arrs_b, T: Population, key: str):
    """(sums, counts) of the seed-averaged difference A - B for one unit."""
    C = len(dict.fromkeys(T.chrom.tolist()))
    cc, _ = chrom_codes(T.chrom)
    if key == "P1":
        da = np.mean([x["rho_w1"] for x in arrs_a], 0)
        db = np.mean([x["rho_w1"] for x in arrs_b], 0)
        return block_sums_locus(da - db, cc, C), "locus", float(np.nanmean(da)), float(np.nanmean(db))
    if key == "P2":
        da = np.mean([x["pair_w1"] for x in arrs_a], 0)
        db = np.mean([x["pair_w1"] for x in arrs_b], 0)
        i, j = arrs_a[0]["pair_i"], arrs_a[0]["pair_j"]
        return block_sums_pair(da - db, cc[i], cc[j], C), "pair", float(np.nanmean(da)), float(np.nanmean(db))
    if key == "P3":
        # fit pairs can differ between runs only if the input differs; same input -> same pairs
        da = np.mean([x["fit_err"] for x in arrs_a], 0)
        db = np.mean([x["fit_err"] for x in arrs_b], 0)
        i, j = arrs_a[0]["fit_i"], arrs_a[0]["fit_j"]
        return block_sums_pair(da - db, cc[i], cc[j], C), "pair", float(np.nanmean(da)), float(np.nanmean(db))
    raise KeyError(key)


def cmd_compare(a) -> None:
    scores = Path(a.scores)
    out = {"a": a.a, "b": a.b, "units": a.units, "note": "difference A - B of losses (positive = B better)"}
    truths = {u: Population.load(Path(a.truth_dir or scores) / u / "truth.npz") if a.truth_dir else Population.load(a.truth)
              for u in a.units}
    for key in ("P1", "P2", "P3"):
        blocks, kinds, per_unit = [], [], {}
        for u in a.units:
            xa, fa = _load(scores, u, a.a)
            xb, fb = _load(scores, u, a.b)
            if not xa or not xb or (key == "P3" and ("fit_err" not in xa[0] or "fit_err" not in xb[0])):
                continue
            (s, n), kind, ma, mb = endpoint_blocks(xa, xb, truths[u], key)
            blocks.append((s, n))
            kinds.append(kind)
            C = len(s)
            per_unit[u] = {"A": ma, "B": mb, "diff": ma - mb, "n_seeds": [len(xa), len(xb)],
                           **{k: v for k, v in bootstrap_mean([(s, n)], [kind], C, a.n_boot).items() if k != "n_boot"}}
        if blocks:
            C = len(blocks[0][0])
            out[key] = {"pooled": bootstrap_mean(blocks, kinds, C, a.n_boot), "units": per_unit}
    # P2 by band (pooled over units)
    bands = {}
    for u in a.units:
        xa, _ = _load(scores, u, a.a)
        xb, _ = _load(scores, u, a.b)
        if not xa or not xb:
            continue
        T = truths[u]
        i, j = xa[0]["pair_i"], xa[0]["pair_j"]
        band = separation_band(T, i, j)
        da = np.mean([x["pair_w1"] for x in xa], 0)
        db = np.mean([x["pair_w1"] for x in xb], 0)
        cc, _ = chrom_codes(T.chrom)
        C = len(dict.fromkeys(T.chrom.tolist()))
        for b in np.unique(band):
            m = band == b
            bands.setdefault(band_label(int(b)), []).append((block_sums_pair(np.where(m, da - db, np.nan), cc[i], cc[j], C),
                                                           float(np.nanmean(da[m])), float(np.nanmean(db[m]))))
    out["P2_bands"] = {}
    for name, lst in bands.items():
        C = len(lst[0][0][0])
        out["P2_bands"][name] = {"A": float(np.mean([x[1] for x in lst])), "B": float(np.mean([x[2] for x in lst])),
                                 **bootstrap_mean([x[0] for x in lst], ["pair"] * len(lst), C, a.n_boot)}
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(jdump(out))
    for key in ("P1", "P2", "P3"):
        if key in out:
            print(key, jdump(out[key]["pooled"]).replace("\n", " "))
    for name, v in out["P2_bands"].items():
        print("  P2", name, f"A {v['A']:.4f} B {v['B']:.4f} diff {v['estimate']:+.4f} [{v['ci'][0]:+.4f}, {v['ci'][1]:+.4f}]")


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("score")
    s.add_argument("--truth", required=True)
    s.add_argument("--input", required=True)
    s.add_argument("--pop", required=True)
    s.add_argument("--rc-nm", type=float)
    s.add_argument("--territory-structures", type=int, default=300)
    s.add_argument("--ceiling-fit", action="store_true", help="Population .npz: fit to input at rc")
    s.add_argument("--out", required=True)
    s.set_defaults(fn=cmd_score)
    c = sub.add_parser("compare")
    c.add_argument("--scores", required=True)
    c.add_argument("--units", nargs="+", required=True)
    c.add_argument("--truth", help="one truth for all units")
    c.add_argument("--truth-dir", help="<dir>/<unit>/truth.npz")
    c.add_argument("--a", required=True)
    c.add_argument("--b", required=True)
    c.add_argument("--n-boot", type=int, default=2000)
    c.add_argument("--out", required=True)
    c.set_defaults(fn=cmd_compare)
    a = ap.parse_args(argv)
    a.fn(a)


if __name__ == "__main__":
    main()
