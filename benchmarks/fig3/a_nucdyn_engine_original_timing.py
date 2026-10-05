"""Time the original NucDynamics (tjs23/nuc_dynamics ``master``, Cython) per stage.

A full default run of the original takes hours per model, so each stage is
timed on a sample of its temperature steps and extrapolated (labelled as
such in the output):

* contact preparation is timed exactly (``remove_isolated_contacts`` once;
  per stage ``remove_violated_contacts``, ``calc_restraints`` /
  ``concatenate_restraints`` / start coordinates inside ``anneal_genome``,
  with the model annealing intercepted);
* the annealing of one model is timed on ``--samples`` temperature steps
  spread over the stage's schedule (step k uses the schedule's temperature
  and repulsion of step k, 100 MD steps each, run one after the other as
  ``anneal_model`` does, with its repulsion-list capacity carried over),
  starting from a realistic structure of that stage: the reference 100 kb
  models (``--ref``, e.g. the native engine's output for the same cell)
  interpolated by the original's own ``getInterpolatedCoords``.  The stage's
  annealing time is the mean time per temperature step x 500.

Wall time and process CPU time are both recorded (the machine may be
shared); the original runs in one process, single-threaded.

Run with the original's environment (Python 3.11, numpy<2, cython<3)::

    $ORIG_PY benchmarks/fig3/a_nucdyn_engine_original_timing.py --nd-dir ND_MASTER \\
        --pairs example-data/stevens2017_mesc/GSM2219497_Cell_1_contact_pairs.txt.gz \\
        --ref RUN_DIR/cell1.npz --out u-chrom-paper/figures/fig3/results/a_nucdyn_engine_original_timing_cell1.json
"""

from __future__ import annotations

import argparse
import gzip
import json
import os
import platform
import sys
import time

import numpy as np


def read_pairs(path):
    ca, pa, cb, pb = [], [], [], []
    with gzip.open(path, "rt") as fh:
        for line in fh:
            if line.startswith("#"):
                continue
            r = line.split()
            ca.append(r[0]); pa.append(int(r[1])); cb.append(r[2]); pb.append(int(r[3]))
    return ca, pa, cb, pb


class Timer:
    def __enter__(self):
        self.w, self.c = time.perf_counter(), time.process_time()
        return self

    def __exit__(self, *a):
        self.wall = time.perf_counter() - self.w
        self.cpu = time.process_time() - self.c


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--nd-dir", required=True)
    ap.add_argument("--pairs", required=True)
    ap.add_argument("--ref", required=True, help="npz with chrom, pos (2017 convention), coords (M, N, 3)")
    ap.add_argument("--sizes", default="8,4,2,0.4,0.2,0.1")
    ap.add_argument("--samples", type=int, default=10)
    ap.add_argument("--temp-steps", type=int, default=500)
    ap.add_argument("--dyn-steps", type=int, default=100)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    sys.path.insert(0, args.nd_dir)
    import nuc_dynamics as nd  # noqa: E402
    import dyn_util  # noqa: E402

    ca, pa, cb, pb = read_pairs(args.pairs)
    contact_dict, chroms = {}, set()
    for c1, p1, c2, p2 in zip(ca, pa, cb, pb):
        if c1 > c2:
            c1, c2, p1, p2 = c2, c1, p2, p1
        contact_dict.setdefault(c1, {}).setdefault(c2, []).append((p1, p2, 1, 0))
        chroms |= {c1, c2}
    for a in contact_dict:
        for b in contact_dict[a]:
            contact_dict[a][b] = np.array(contact_dict[a][b]).T
    chromosomes = sorted(chroms)
    report = {"pairs": os.path.basename(args.pairs), "n_contacts": len(ca), "machine": platform.platform(),
              "load_avg_start": os.getloadavg(), "samples_per_stage": args.samples,
              "temp_steps": args.temp_steps, "dyn_steps": args.dyn_steps, "stages": []}
    with Timer() as t:
        nd.remove_isolated_contacts(contact_dict, threshold=int(2e6))
    report["remove_isolated"] = {"wall": t.wall, "cpu": t.cpu}

    # reference structure (100 kb) as the original's coords / seq-pos dicts
    z = np.load(args.ref, allow_pickle=True)
    rchrom, rpos, rX = z["chrom"].astype(str), z["pos"].astype(np.int32), z["coords"][0].astype(float)
    ref_pos = {c: rpos[rchrom == c] for c in np.unique(rchrom)}
    ref_coords = {c: rX[rchrom == c][None] for c in np.unique(rchrom)}

    captured = {}

    def capture(target_func, split_data, common_args, num_cpu=1, collect_output=True):
        captured["common"] = common_args
        captured["coords"] = [c for _, c in split_data]
        return [c for _, c in split_data]

    real_split = nd.parallel_split_job
    nd.parallel_split_job = capture
    gparams = {"dist_power_law": -0.33, "contact_dist_lower": 0.8, "contact_dist_upper": 1.2,
               "backbone_dist_lower": 0.1, "backbone_dist_upper": 1.1, "random_seed": 1, "random_radius": 10.0}
    aparams = {"temp_start": 5000.0, "temp_end": 10.0, "temp_steps": args.temp_steps,
               "dynamics_steps": args.dyn_steps, "time_step": 0.001}
    sizes = [float(s) * 1e6 for s in args.sizes.split(",")]
    for stage, size in enumerate(sizes):
        st = {"particle_size": size}
        if stage > 0 and size < 0.5e6:
            # the original removes violated contacts with the previous stage's models
            prev_size = sizes[stage - 1]
            _, prev_seq = nd.anneal_genome(chromosomes, contact_dict, 1, prev_size, gparams, aparams,
                                           ref_pos, ref_coords, 1)
            prev_coords = nd.unpack_chromo_coords(np.array(captured["coords"]), chromosomes, prev_seq)
            with Timer() as t:
                nd.remove_violated_contacts(contact_dict, prev_coords, prev_seq, size, threshold=6.0)
            st["remove_violated"] = {"wall": t.wall, "cpu": t.cpu}
        with Timer() as t:
            if stage == 0:
                _, seq = nd.anneal_genome(chromosomes, contact_dict, 1, size, gparams, aparams, None, None, 1)
            else:
                _, seq = nd.anneal_genome(chromosomes, contact_dict, 1, size, gparams, aparams,
                                          ref_pos, ref_coords, 1)
        st["prepare"] = {"wall": t.wall, "cpu": t.cpu}
        (schedule, masses, radii, idx, dists, ambig, _t, time_step, dyn_steps, _r, _nrep) = captured["common"]
        coords = np.array(captured["coords"][0])
        st["n_particles"] = int(len(coords))
        st["n_restraints"] = int(len(idx))
        ks = np.unique(np.linspace(0, len(schedule) - 1, args.samples).round().astype(int))
        walls, cpus, nrep = [], [], np.int32(0)
        for k in ks:
            temp, rep = schedule[k]
            with Timer() as t:
                _, nrep = dyn_util.runDynamics(coords, masses, radii, idx, dists, ambig, temp, time_step,
                                               dyn_steps, rep, nRepMax=nrep, printInterval=0)
            nrep = np.int32(1.05 * nrep)
            walls.append(t.wall)
            cpus.append(t.cpu)
        st["sampled_temp_steps"] = ks.tolist()
        st["seconds_per_temp_step_wall"] = walls
        st["seconds_per_temp_step_cpu"] = cpus
        st["anneal_extrapolated_wall"] = float(np.mean(walls) * len(schedule))
        st["anneal_extrapolated_cpu"] = float(np.mean(cpus) * len(schedule))
        prep_w = st["prepare"]["wall"] + st.get("remove_violated", {}).get("wall", 0.0)
        prep_c = st["prepare"]["cpu"] + st.get("remove_violated", {}).get("cpu", 0.0)
        st["stage_per_model_extrapolated_wall"] = st["anneal_extrapolated_wall"] + prep_w
        st["stage_per_model_extrapolated_cpu"] = st["anneal_extrapolated_cpu"] + prep_c
        report["stages"].append(st)
        print(json.dumps({k: v for k, v in st.items() if not k.startswith("seconds_per")}), flush=True)
    nd.parallel_split_job = real_split
    tot_w = sum(s["stage_per_model_extrapolated_wall"] for s in report["stages"]) + report["remove_isolated"]["wall"]
    tot_c = sum(s["stage_per_model_extrapolated_cpu"] for s in report["stages"]) + report["remove_isolated"]["cpu"]
    report["per_model_extrapolated_wall_seconds"] = tot_w
    report["per_model_extrapolated_cpu_seconds"] = tot_c
    report["load_avg_end"] = os.getloadavg()
    with open(args.out, "w") as fh:
        json.dump(report, fh, indent=1)
    print(f"per model (1 core, extrapolated): wall {tot_w / 3600:.2f} h, cpu {tot_c / 3600:.2f} h")


if __name__ == "__main__":
    main()
