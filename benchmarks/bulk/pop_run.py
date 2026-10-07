"""Run one population method of the EMber-pop benchmark (``PREREG_POP.md`` section 4) on a
probability-matrix input and write the engine output, the run log and the fit to the input.

    python benchmarks/bulk/pop_run.py --input SIM/C1.npz --cells SIM/bulk_cells.npz --method igm_sphere \\
        --n-structures 1000 --seed 1 --device gpu --out RUNS/C1/igm_sphere_s1

``--cells``: the bulk cells' Population (its ``meta`` gives the imaging calibration:
``nuclear_radius_nm`` = sqrt(5/3) median Rg, ``gyration_semiaxes_nm``).

Methods (configurations of PREREG section 4; ``--params JSON`` adds / overrides engine fields,
development only):

* ``igm_sphere`` - protocol ``igm`` defaults, ``nucleus_radius`` = R_rg, occupancy 0.2;
* ``igm_ellipsoid`` - semi-axes = the bulk cells' gyration semi-axes, radii identical to
  ``igm_sphere`` (occupancy scaled by V_sphere / V_ellipsoid, so occupancy x V is unchanged);
* ``ember_pop`` - the EMber-pop options (``EMBER_POP`` below) on the same genome / radii.

Writes ``<out>/population.npz`` (engine arrays + haploid bins: ``population.load_any`` reads it),
``<out>/fit.npz`` (input pairs with f >= 0.01 and the population's contact probability at the
model's own contact distance) and ``<out>/summary.json``.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _igm_bench as B  # noqa: E402
from _common import jdump, load_preprocess  # noqa: E402
from population import Population  # noqa: E402

#: EMber-pop engine options (development candidate; frozen at tag ember-pop-frozen)
EMBER_POP: dict = {}


def method_params(method: str, cells_meta: dict, prov: dict) -> dict:
    R = float(cells_meta["nuclear_radius_nm"])
    occ = 0.2
    base = dict(occupancy=occ, nucleus_shape="sphere", nucleus_radius=R)
    if method == "igm_sphere":
        return base
    if method == "igm_ellipsoid":
        ax = [float(x) for x in cells_meta["gyration_semiaxes_nm"]]
        scale = R ** 3 / (ax[0] * ax[1] * ax[2])
        if occ * scale >= 1.0:
            raise SystemExit(f"ellipsoid occupancy {occ * scale:.3f} >= 1: radii cannot match the sphere arm")
        return dict(base, nucleus_shape="ellipsoid", nucleus_semiaxes=ax, occupancy=occ * scale)
    if method.startswith("ember_pop"):
        return dict(base, **EMBER_POP)
    raise SystemExit(f"unknown method {method}")


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--input", required=True)
    ap.add_argument("--cells", required=True)
    ap.add_argument("--method", required=True)
    ap.add_argument("--params", default=None, help="JSON object of extra engine fields (development)")
    ap.add_argument("--n-structures", type=int, default=1000)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--device", default="gpu", choices=["cpu", "gpu"])
    ap.add_argument("--ploidy", default="diploid")
    ap.add_argument("--steps-scale", type=float, default=1.0, help="development only")
    ap.add_argument("--fit-sigma", type=float, default=0.01)
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)

    import uchrom_recon as un

    pm = load_preprocess().ProbabilityMatrix.load(a.input)
    prov = pm.provenance
    cells = Population.load(a.cells)
    bins = pm.bins
    P = pm.probabilities.tocoo()
    keep = P.row < P.col
    i, j, v = P.row[keep].astype(np.int64), P.col[keep].astype(np.int64), np.asarray(P.data[keep], float)
    nz = np.isfinite(v) & (v > 0)
    i, j, v = i[nz], j[nz], v[nz]
    params = method_params(a.method, cells.meta, prov)
    if a.params:
        params.update(json.loads(a.params))
    rg = params.get("rg_cap")
    if isinstance(rg, str):                 # "imaging[*f]": f x the bulk cells' median Rg
        f = float(rg.split("*")[1]) if "*" in rg else 1.0
        params["rg_cap"] = f * float(cells.meta["nuclear_radius_nm"]) * np.sqrt(3.0 / 5.0)
    if params.get("gyration_prior") == "imaging":  # the bulk cells' median gyration standard deviations
        params["gyration_prior"] = [float(x) / np.sqrt(5.0) for x in cells.meta["gyration_semiaxes_nm"]]
    if a.steps_scale != 1.0:
        d = un.default_igm_params()
        stages = params.get("stages") or d["stages"]
        params["stages"] = [dict(s, mdsteps=max(1, int(s["mdsteps"] * a.steps_scale))) for s in stages]
        relax = params.get("relax", d.get("relax"))
        if relax:
            params["relax"] = dict(relax, mdsteps=max(1, int(relax["mdsteps"] * a.steps_scale)))
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    log_f = open(out / "rounds.jsonl", "w")

    def on_round(log, _c):
        log_f.write(json.dumps(log) + "\n")
        log_f.flush()
        print(f"[round {log['round']}] sigma {log['intra_sigma']} it {log['iteration']}: "
              f"{log['n_pairs_restrained']} pairs, {log['n_hic_bonds'] / a.n_structures:.1f} bonds/structure, "
              f"score {log['violation_score']:.4f} (A {log['seconds_astep']:.1f} s, M {log['seconds_mstep']:.1f} s)",
              flush=True)

    chrom = np.asarray(bins["chrom"].astype(str).to_numpy(), dtype=str)
    t0 = time.time()
    res = un.calc_population(chrom, bins["start"].to_numpy(), bins["end"].to_numpy(), i, j, v, ploidy=a.ploidy,
                             on_round=on_round, n_structures=a.n_structures, seed=a.seed, device=a.device, **params)
    wall = time.time() - t0
    log_f.close()
    np.savez_compressed(out / "population.npz", coords=res["coords"], bead_bin=res["bead_bin"],
                        bead_copy=res["bead_copy"], radii=res["radii"], chrom=chrom,
                        start=bins["start"].to_numpy(), end=bins["end"].to_numpy())
    # fit to input: pairs with f >= fit_sigma, |i - j| > 1 within a chromosome, all trans pairs
    intra = chrom[i] == chrom[j]
    sel = (v >= a.fit_sigma) & (~intra | (j - i > 1))
    t1 = time.time()
    pc = B.contact_probability(res["coords"], res["bead_bin"], res["bead_copy"], res["radii"], chrom, i[sel], j[sel])
    np.savez_compressed(out / "fit.npz", i=i[sel], j=j[sel], f=v[sel], model=pc, intra=intra[sel])
    fit = {"mae": float(np.mean(np.abs(pc - v[sel]))), "mae_cis": float(np.mean(np.abs(pc - v[sel])[intra[sel]])),
           "mae_trans": float(np.mean(np.abs(pc - v[sel])[~intra[sel]])) if (~intra[sel]).any() else None,
           "pearson": float(np.corrcoef(pc, v[sel])[0, 1]), "n_pairs": int(sel.sum())}
    summary = {"method": a.method, "input": a.input, "cells": a.cells, "engine": res["engine"],
               "n_structures": a.n_structures, "seed": a.seed, "device": a.device, "steps_scale": a.steps_scale,
               "params": res["params"], "seconds_engine": res["seconds_total"], "seconds_wall": wall,
               "seconds_fit": time.time() - t1, "stopped_at_max_iterations": res["stopped_at_max_iterations"],
               "n_rounds": len(res["rounds"]), "fit": fit,
               "seconds_astep_total": float(sum(r["seconds_astep"] for r in res["rounds"])),
               "seconds_mstep_total": float(sum(r["seconds_mstep"] for r in res["rounds"]))}
    (out / "summary.json").write_text(jdump(summary))
    print(jdump({k: summary[k] for k in ("method", "engine", "seconds_wall", "n_rounds", "fit")}), flush=True)


if __name__ == "__main__":
    main()
