"""Cross-check the native NucDynamics engine against the original Cython code.

Two interpreters are involved, because the original needs ``cython<3`` /
``numpy<2`` (a separate venv) and the engine lives in the U-Chrom env:

1. ``orig`` (run with the original's venv, ``--nd-dir`` = a built checkout of
   tjs23/nuc_dynamics, branch ``master`` (2017) or ``release_1.3``): builds
   the first-stage restraints with the original ``anneal_genome``
   (``parallel_split_job`` is intercepted to capture its inputs), then runs
   the original ``run_dynamics`` / ``runDynamics`` for a few temperature steps
   with a fixed numpy seed, and saves inputs, velocity draws and outputs.
2. ``native`` (run with the U-Chrom env): rebuilds the same stage with
   ``uchrom_nucdyn`` and compares the restraint set exactly, then feeds the
   original's restraints, start coordinates and velocity draws to
   ``uchrom_nucdyn.run_dynamics`` and reports coordinate differences after
   the same number of steps (with the original's neighbour-list schedule and
   with the engine's exact cell grid), plus the growth of a 1e-12
   perturbation (the intrinsic chaos of the dynamics) as a yardstick.

Usage::

    ORIG_PY=/path/to/orig-venv/bin/python
    $ORIG_PY benchmarks/fig3/a_nucdyn_engine_crosscheck.py orig --branch master \\
        --nd-dir ND --pairs PAIRS --size 2e6 --out x.npz
    python benchmarks/fig3/a_nucdyn_engine_crosscheck.py native --npz x.npz --pairs PAIRS --out x.json
"""

from __future__ import annotations

import argparse
import gzip
import json
import sys
import time

import numpy as np

CASES = [(0, 1), (0, 10), (0, 100), (250, 100), (499, 100)]


def read_pairs(path):
    op = gzip.open if str(path).endswith(".gz") else open
    ca, pa, cb, pb = [], [], [], []
    with op(path, "rt") as fh:
        for line in fh:
            if line.startswith("#") or not line.strip():
                continue
            r = line.split()
            if r[1].isdigit():
                c1, p1, c2, p2 = r[0], int(r[1]), r[2], int(r[3])
            else:
                c1, p1, c2, p2 = r[1], int(r[2]), r[3], int(r[4])
            ca.append(c1)
            pa.append(p1)
            cb.append(c2)
            pb.append(p2)
    return ca, pa, cb, pb


def cmd_orig(args):
    sys.path.insert(0, args.nd_dir)
    import nuc_dynamics as nd  # noqa: E402
    import dyn_util  # noqa: E402

    ca, pa, cb, pb = read_pairs(args.pairs)
    captured = {}

    def capture(target_func, split_data, common_args, num_cpu=1, collect_output=True):
        captured["common"] = common_args
        captured["coords"] = [c for _, c in split_data]
        return [c for _, c in split_data]

    nd.parallel_split_job = capture
    gparams = {"dist_power_law": -0.33, "contact_dist_lower": 0.8, "contact_dist_upper": 1.2,
               "backbone_dist_lower": 0.1, "backbone_dist_upper": 1.1, "random_seed": 1,
               "random_radius": 10.0}
    aparams = {"temp_start": 5000.0, "temp_end": 10.0, "temp_steps": 500, "dynamics_steps": 100,
               "time_step": 0.001}
    out = {"branch": args.branch, "size": args.size}
    if args.branch == "master":
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
        nd.remove_isolated_contacts(contact_dict, threshold=int(2e6))
        n_contacts = sum(v.shape[1] for d in contact_dict.values() for v in d.values())
        _, seq_pos = nd.anneal_genome(chromosomes, contact_dict, 1, args.size, gparams, aparams)
        (schedule, masses, radii, idx, dists, ambig, _t, time_step, dyn_steps, _r, _nrep) = captured["common"]
        weight = np.ones(len(idx))
        dist, bead = 25.0, 1.0
    else:
        contact_dict = {}
        for i, (c1, p1, c2, p2) in enumerate(zip(ca, pa, cb, pb)):
            if c1 > c2:
                c1, c2, p1, p2 = c2, c1, p2, p1
            contact_dict.setdefault(c1, {}).setdefault(c2, []).append(((p1, p2), i + 1, i))
        for a in contact_dict:
            for b in contact_dict[a]:
                contact_dict[a][b] = np.array(contact_dict[a][b], dtype=nd.Contact)
        clean = nd.initial_clean_contacts(contact_dict, threshold_cis=int(2e6), threshold_trans=int(10e6))
        n_contacts = sum(len(v) for d in clean.values() for v in d.values())
        _, seq_pos = nd.anneal_genome(clean, 1, args.size, gparams, aparams)
        (schedule, masses, radii, restraints, rep_dists, ambig, _t, time_step, dyn_steps, _r,
         dist, bead) = captured["common"]
        idx, dists, weight = restraints["indices"], restraints["dists"], restraints["weight"]
    coords0 = np.array(captured["coords"][0])
    out.update({
        "coords0": coords0, "masses": masses, "radii": radii,
        "rest_indices": idx.astype(np.int32), "rest_limits": dists, "rest_weight": weight,
        "rest_ambig": ambig.astype(np.int32), "dist": dist, "bead": bead,
        "schedule": np.array(schedule), "n_contacts": n_contacts, "n_particles": len(coords0),
    })
    for k, (ti, ns) in enumerate(CASES):
        temp, rep = schedule[ti]
        c = coords0.copy()
        np.random.seed(1000 + k)
        vel = np.random.normal(0.0, 1.0, (len(c), 3))
        np.random.seed(1000 + k)
        t0 = time.time()
        if args.branch == "master":
            dyn_util.runDynamics(c, masses, radii, idx, dists, ambig, temp, time_step, ns, rep,
                                 nRepMax=args.n_rep_max, printInterval=0)
        else:
            dyn_util.run_dynamics(c, masses, radii, rep_dists, idx, dists, weight, ambig, temp, time_step,
                                  ns, rep, dist, bead, args.n_rep_max, print_interval=0)
        out[f"case{k}_t"] = np.array([ti, ns, time.time() - t0])
        out[f"case{k}_vel"] = vel
        out[f"case{k}_out"] = c
    np.savez_compressed(args.out, **out)
    print(f"saved {args.out}: {len(coords0)} particles, {len(idx)} restraints")


def cmd_native(args):
    import uchrom_nucdyn as un

    z = np.load(args.npz)
    branch = str(z["branch"])
    protocol = "nuc_dynamics_2017" if branch == "master" else "release_1.3"
    report = {"branch": branch, "size": float(z["size"]), "n_particles": int(z["n_particles"])}
    if args.pairs:
        ca, pa, cb, pb = read_pairs(args.pairs)
        names = sorted(set(ca) | set(cb))
        idx = {n: i for i, n in enumerate(names)}
        p = un.default_params()
        p["protocol"] = protocol
        s = un._engine.debug_setup_stage(
            names, np.array([idx[c] for c in ca], np.uint32), np.array(pa, np.int64),
            np.array([idx[c] for c in cb], np.uint32), np.array(pb, np.int64),
            np.arange(1, len(ca) + 1, dtype=np.int64), np.ones(len(ca), bool), json.dumps(p),
            float(z["size"]))
        pairs = s["rest_pairs"].reshape(-1, 2)
        lim = s["rest_lim"].reshape(-1, 2)

        def key(P, L, W):
            P = np.sort(P, axis=1)
            return sorted(zip(map(tuple, P.tolist()), map(tuple, L.tolist()), np.asarray(W).tolist()))

        same = key(pairs, lim, s["rest_w"]) == key(z["rest_indices"], z["rest_limits"], z["rest_weight"])
        seq = np.concatenate(s["seq_pos"])
        report["restraints"] = {
            "native": int(len(pairs)), "original": int(len(z["rest_indices"])),
            "identical_set_bitwise": bool(same),
            "n_particles_native": int(len(seq)), "n_particles_original": int(z["n_particles"]),
            "n_contacts_native": int(s["n_contacts"]), "n_contacts_original": int(z["n_contacts"]),
            "dist_const_native": float(s["f_dist"]), "dist_const_original": float(z["dist"]),
        }
    cases = []
    bead = float(z["bead"])
    common = dict(beta=10.0, tot0=20.458, protocol=protocol)
    k = 0
    while f"case{k}_t" in z:
        ti, ns, t_orig = z[f"case{k}_t"]
        ti, ns = int(ti), int(ns)
        temp, rep = z["schedule"][ti]
        args_ = (z["masses"], z["radii"], z["rest_indices"], z["rest_limits"], z["rest_weight"],
                 z["rest_ambig"], float(temp), 0.001, ns, float(rep), float(z["dist"]))
        ref = z[f"case{k}_out"]
        moved = np.linalg.norm(ref - z["coords0"], axis=1) / bead
        row = {"temp_step": ti, "n_steps": ns, "median_displacement_radii": float(np.median(moved)),
               "seconds_original_1core": float(t_orig)}
        for mode, kw in (("original_nl_schedule", dict(original_nl_schedule=True, skin=2.0 * bead)),
                         ("exact_cell_grid", dict(use_cells=True))):
            t0 = time.time()
            c, _ = un.run_dynamics(z["coords0"], *args_, veloc=z[f"case{k}_vel"], **common, **kw)
            d = np.linalg.norm(c - ref, axis=1) / bead
            row[mode] = {"max_diff_radii": float(d.max()), "median_diff_radii": float(np.median(d)),
                         "seconds_native_1thread": time.time() - t0}
        rng = np.random.default_rng(k)
        pert = z["coords0"] + rng.normal(0, 1e-12 * bead, z["coords0"].shape)
        c1, _ = un.run_dynamics(z["coords0"], *args_, veloc=z[f"case{k}_vel"], use_cells=True, **common)
        c2, _ = un.run_dynamics(pert, *args_, veloc=z[f"case{k}_vel"], use_cells=True, **common)
        d = np.linalg.norm(c1 - c2, axis=1) / bead
        row["native_vs_native_1e-12_perturbed"] = {"max_diff_radii": float(d.max()),
                                                   "median_diff_radii": float(np.median(d))}
        cases.append(row)
        k += 1
    report["dynamics"] = cases
    print(json.dumps(report, indent=1))
    if args.out:
        with open(args.out, "w") as fh:
            json.dump(report, fh, indent=1)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    o = sub.add_parser("orig")
    o.add_argument("--branch", choices=["master", "release_1.3"], default="master")
    o.add_argument("--nd-dir", required=True)
    o.add_argument("--pairs", required=True)
    o.add_argument("--size", type=float, default=2e6)
    o.add_argument("--out", required=True)
    o.add_argument("--n-rep-max", type=int, default=0,
                   help="repulsion list capacity (0: the original default; large: avoids its overflow path)")
    n = sub.add_parser("native")
    n.add_argument("--npz", required=True)
    n.add_argument("--pairs")
    n.add_argument("--out")
    args = ap.parse_args()
    {"orig": cmd_orig, "native": cmd_native}[args.cmd](args)


if __name__ == "__main__":
    main()
