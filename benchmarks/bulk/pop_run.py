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
* ``ember_pop`` - the EMber-pop options (``EMBER_POP`` below) on the same genome / radii: no envelope,
  the bulk cells' gyration-shape prior, non-contact restraints at the last sigma, at most 5 iterations
  per sigma.

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

#: EMber-pop engine options (development candidate "B5" of POP_DEVLOG.md; frozen at tag ember-pop-frozen).
#: The gyration prior is the bulk cells' median gyration standard deviations ("imaging").
EMBER_POP: dict = {
    "nucleus_shape": "none",
    "gyration_prior": "imaging",
    "gyration_kspring": 0.1,
    "noncontact_kspring": 1.0,
    "noncontact_from_sigma": 5,
    "advance_on_max_iterations": True,
    "max_iterations": 5,
}


def cell_gyration_sds(cells: Population) -> np.ndarray:
    """(n_cells, 3) gyration standard deviations sigma1 >= sigma2 >= sigma3 of every imaged cell (nm)."""
    out = []
    for X in cells.coords:
        Y = X.reshape(-1, 3)
        Y = Y[np.isfinite(Y).all(1)].astype(np.float64)
        if len(Y) > 3:
            lam = np.sort(np.linalg.eigvalsh(np.cov((Y - Y.mean(0)).T, bias=True)))[::-1]
            out.append(np.sqrt(np.maximum(lam, 1.0)))
    return np.array(out)


def method_params(method: str, cells_meta: dict, prov: dict, bins=None, copies=None) -> dict:
    R = float(cells_meta["nuclear_radius_nm"])
    occ = 0.2
    base = dict(occupancy=occ, nucleus_shape="sphere", nucleus_radius=R)
    if method == "igm_sphere":
        return base
    if method == "igm_ellipsoid":
        ax = [float(x) for x in cells_meta["gyration_semiaxes_nm"]]
        scale = R ** 3 / (ax[0] * ax[1] * ax[2])
        if occ * scale < 1.0:
            return dict(base, nucleus_shape="ellipsoid", nucleus_semiaxes=ax, occupancy=occ * scale)
        # the sphere arm's beads do not fit at an occupancy < 1: one radius for every bead, the median
        # radius of the sphere arm (bead_radius; occupancy off)
        if bins is None:
            raise SystemExit(f"ellipsoid occupancy {occ * scale:.3f} >= 1 and no bins for the bead_radius fallback")
        size = (bins["end"] - bins["start"]).to_numpy(float)
        total = float(sum(size[bins["chrom"].astype(str).to_numpy() == c].sum() * k for c, k in copies.items()))
        rho = occ * 4.0 / 3.0 * np.pi * R ** 3 / total
        r_med = float(np.median((rho * size / (4.0 * np.pi / 3.0)) ** (1.0 / 3.0)))
        return dict(base, nucleus_shape="ellipsoid", nucleus_semiaxes=ax, occupancy=0.0, bead_radius=r_med)
    if method.startswith("ember_pop"):
        return dict(base, **EMBER_POP)
    raise SystemExit(f"unknown method {method}")


def _copies(bins, ploidy):
    import uchrom_recon as un
    names = list(dict.fromkeys(bins["chrom"].astype(str).tolist()))
    return names, un.resolve_copies(names, ploidy)


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
    copies = dict(zip(*_copies(bins, a.ploidy)))
    params = method_params(a.method, cells.meta, prov, bins, copies)
    if a.params:
        params.update(json.loads(a.params))
    rg = params.get("rg_cap")
    if isinstance(rg, str):                 # "imaging[*f]": f x the bulk cells' median Rg
        f = float(rg.split("*")[1]) if "*" in rg else 1.0
        params["rg_cap"] = f * float(cells.meta["nuclear_radius_nm"]) * np.sqrt(3.0 / 5.0)
    if params.get("gyration_prior") == "imaging":  # the bulk cells' median gyration standard deviations
        params["gyration_prior"] = [float(x) / np.sqrt(5.0) for x in cells.meta["gyration_semiaxes_nm"]]
    elif params.get("gyration_prior") == "imaging_cells":
        # every structure gets the gyration standard deviations of one bulk cell (drawn with the run's
        # seed), so the population keeps the imaged cells' size and shape variation
        sd = cell_gyration_sds(cells)
        pick = np.random.default_rng([a.seed, 0x6779]).choice(len(sd), a.n_structures, replace=len(sd) < a.n_structures)
        params["gyration_targets"] = sd[pick].tolist()
        params["gyration_prior"] = np.median(sd, axis=0).tolist()
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
