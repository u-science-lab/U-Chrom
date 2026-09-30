"""Run the native IGM protocol on the IGM demo input (WTC11 Hi-C, 2 Mb, hg38, male)
with the demo configuration, and score how well the population reproduces the input.

    python benchmarks/bulk/igm_demo_run.py --device gpu --n-structures 1000 --seed 1 --out runs/igm_demo/ours_s1

Writes ``<out>/population.npz`` (coords (S, N, 3) float32 nm, bead_bin, bead_copy,
radii, bins), ``<out>/summary.json`` (parameters, per-round log, timing, fit summary of
the final population vs the input) and ``<out>/rounds.jsonl`` (streamed per-round log).
The input ``.hcs`` (GPL-3 repository alberlab/igm) is downloaded on demand
(``--hcs`` to use a local copy); it is not part of U-Chrom.

``--steps-scale 0.02`` shortens every MD stage (smoke test only).
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


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--hcs", type=Path, default=None)
    ap.add_argument("--n-structures", type=int, default=1000)
    ap.add_argument("--device", default="gpu", choices=["cpu", "gpu"])
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--steps-scale", type=float, default=1.0)
    ap.add_argument("--max-iterations", type=int, default=None)
    ap.add_argument("--sigmas", type=float, nargs="*", default=None, help="override both sigma lists")
    ap.add_argument("--chroms", nargs="*", default=None, help="restrict to these chromosomes")
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args(argv)

    import uchrom_nucdyn as un

    hcs = a.hcs or B.fetch_igm_demo()
    d = B.read_hcs(hcs)
    chrom, start, end, i, j, v = d["chrom"], d["start"], d["end"], d["i"], d["j"], d["v"]
    if a.chroms:
        keep = np.isin(chrom, a.chroms)
        new = np.full(len(chrom), -1)
        new[keep] = np.arange(keep.sum())
        m = keep[i] & keep[j]
        i, j, v = new[i[m]], new[j[m]], v[m]
        chrom, start, end = chrom[keep], start[keep], end[keep]
    params = dict(B.DEMO_PARAMS)
    if a.steps_scale != 1.0:
        params["stages"] = [dict(s, mdsteps=max(1, int(s["mdsteps"] * a.steps_scale))) for s in params["stages"]]
        params["relax"] = dict(params["relax"], mdsteps=max(1, int(params["relax"]["mdsteps"] * a.steps_scale)))
    if a.max_iterations:
        params["max_iterations"] = a.max_iterations
    if a.sigmas:
        params["intra_sigma_list"] = list(a.sigmas)
        params["inter_sigma_list"] = list(a.sigmas)
    a.out.mkdir(parents=True, exist_ok=True)
    log_f = open(a.out / "rounds.jsonl", "w")

    def on_round(log, _coords):
        log_f.write(json.dumps(log) + "\n")
        log_f.flush()
        print(f"[round {log['round']}] sigma {log['intra_sigma']} it {log['iteration']}: "
              f"{log['n_pairs_restrained']} pairs restrained, {log['n_hic_bonds'] / max(a.n_structures, 1):.1f} bonds/structure, "
              f"score {log['violation_score']:.4f} (A {log['seconds_astep']:.1f} s, M {log['seconds_mstep']:.1f} s)", flush=True)

    t0 = time.time()
    res = un.calc_population(chrom, start, end, i, j, v, ploidy=B.DEMO_PLOIDY, on_round=on_round,
                             n_structures=a.n_structures, device=a.device, seed=a.seed, verbose=False, **params)
    wall = time.time() - t0
    log_f.close()
    bins_chrom = chrom
    t1 = time.time()
    pc = B.contact_probability(res["coords"], res["bead_bin"], res["bead_copy"], res["radii"], bins_chrom, i, j)
    fit = B.fit_summary(v, pc, bins_chrom[i] == bins_chrom[j], sigma=min(params["intra_sigma_list"]))
    np.savez_compressed(a.out / "population.npz", coords=res["coords"], bead_bin=res["bead_bin"],
                        bead_copy=res["bead_copy"], bead_chain=res["bead_chain"], radii=res["radii"],
                        bin_chrom=chrom, bin_start=start, bin_end=end, pair_i=i, pair_j=j, pair_f=v, pair_model=pc)
    summary = {
        "input": {"hcs": str(hcs), "md5": B.md5(hcs), "n_bins": int(len(chrom)), "n_pairs": int(len(v))},
        "engine": res["engine"], "uchrom_nucdyn": un.__version__, "device": a.device, "seed": a.seed,
        "n_structures": a.n_structures, "n_beads": int(len(res["bead_bin"])), "ploidy": B.DEMO_PLOIDY,
        "params": res["params"], "steps_scale": a.steps_scale,
        "rounds": res["rounds"], "stopped_at_max_iterations": res["stopped_at_max_iterations"],
        "seconds_engine": res["seconds_total"], "seconds_wall": wall, "seconds_scoring": time.time() - t1,
        "seconds_astep_total": float(sum(r["seconds_astep"] for r in res["rounds"])),
        "seconds_mstep_total": float(sum(r["seconds_mstep"] for r in res["rounds"])),
        "fit": fit,
    }
    (a.out / "summary.json").write_text(json.dumps(summary, indent=1))
    print(json.dumps({k: summary[k] for k in ("engine", "n_structures", "seconds_wall", "fit")}, indent=1))


if __name__ == "__main__":
    main()
