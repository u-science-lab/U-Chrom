"""The new single-cell method (``robust``, PREREG.md §7, milestone M2) on an arbitrary contact table.

Native engine (``uchrom_recon``), protocol ``robust``: the NucDynamics 2017 protocol with a
noise-aware observation model (contact restraints re-weighted by their posterior probability of
being true, false-contact rate and contact-kernel width learned by EM).  Same particle schedule,
call and output as ``run_nucdyn.py`` (``.npz``: ``chrom``, ``pos`` [2017 convention], ``coords``
(M, N, 3); plus ``contact_weights``, the final weight of every input contact, NaN = filtered) and
``<out>.json`` (timings, stages with the EM log, parameters)::

    python benchmarks/screcon/run_robust.py --contacts train.txt.gz --res 100000 --device gpu \\
        --n-models 10 --seed 1 --out RUN/robust.npz [--params '{"robust_per_model": true}']

``ROBUST_DEFAULTS`` holds the parameter set used unless ``--params`` overrides it (the frozen set
of the method is recorded here and in ``robust_devlog.md``).
"""

from __future__ import annotations

import argparse
import json
import os
import resource
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from contacts import read_contacts  # noqa: E402
from run_nucdyn import peak_rss_mb, schedule  # noqa: E402

#: parameters of the method (engine defaults otherwise); changed only by dev-set experiments.
#: Recommended set (robust_devlog.md: M2 variant es4 + M3 candidate c2): EM re-weighting before every
#: stage from stage 2 on and once inside it, exponential contact kernel (width and false-contact rate
#: learned), local-support evidence (window 4 x final size); 50 x 50 MD steps per stage, one refinement
#: pass of 10 x 50 steps from T = 500, sampling at T = 1000 for 20 x 20 steps after the final anneal,
#: contact-free particles merged below 25 kb.  The engine defaults of protocol "robust" are the same
#: values (the M2 runs used 500 x 100 steps: pass robust_temp_steps / robust_dynamics_steps to reproduce).
ROBUST_DEFAULTS: dict = {"robust_segments": 2, "robust_refine": 1, "robust_kernel": "exp", "robust_support_rel": 4.0,
                         "robust_temp_steps": [50], "robust_dynamics_steps": [50], "robust_refine_temp_steps": 10,
                         "robust_refine_temp_start": 500.0, "robust_sample_temp": 1000.0, "robust_sample_steps": 20,
                         "robust_sample_dyn_steps": 20, "robust_merge_below": 25000.0}


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--contacts", required=True)
    ap.add_argument("--res", type=float, default=1e5, help="final particle size, bp")
    ap.add_argument("--sizes", help="explicit schedule, Mb, comma separated (overrides --res)")
    ap.add_argument("--device", default="gpu", choices=["cpu", "gpu"])
    ap.add_argument("--n-models", type=int, default=10)
    ap.add_argument("--n-threads", type=int, default=0)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--temp-steps", type=int, help="temperature steps per stage (default: ROBUST_DEFAULTS)")
    ap.add_argument("--dyn-steps", type=int, help="MD steps per temperature step (default: ROBUST_DEFAULTS)")
    ap.add_argument("--params", default="{}", help="JSON of engine parameters overriding ROBUST_DEFAULTS")
    ap.add_argument("--label", default="robust", help="method name written to the .json")
    ap.add_argument("--prior-lr", help=".npy of per-contact likelihood ratios true / false (one per table row)")
    ap.add_argument("--support-w", type=float, help="local-support prior (robust_prior.support_lr), window in bp")
    ap.add_argument("--support-mix", type=float, help="calibrated local-support LR (robust_prior.support_mixture), window in bp")
    ap.add_argument("--oracle-truth", help="DIAGNOSTIC ONLY (simulated tables): truth .npz; noise reads get\n"
                    "likelihood ratio 0 (upper bound of re-weighting)")
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args(argv)
    import uchrom_recon as un

    # $ROBUST_PARAMS (JSON) sits between the defaults and --params (for harnesses that cannot pass --params)
    params = {**ROBUST_DEFAULTS, **json.loads(os.environ.get("ROBUST_PARAMS", "{}")), **json.loads(args.params)}
    sizes = [float(x) * 1e6 for x in args.sizes.split(",")] if args.sizes else schedule(args.res)
    tr = time.time()
    c = read_contacts(args.contacts)
    read_seconds = time.time() - tr
    if args.temp_steps:
        params["robust_temp_steps"] = [args.temp_steps]
    if args.dyn_steps:
        params["robust_dynamics_steps"] = [args.dyn_steps]
    prior_lr = np.load(args.prior_lr) if args.prior_lr else None
    if args.support_w:
        from robust_prior import support_lr
        prior_lr = support_lr(c.chrom_a, c.pos_a, c.chrom_b, c.pos_b, args.support_w)[1]
    if args.support_mix:
        from robust_prior import support_mixture
        prior_lr = support_mixture(c.chrom_a, c.pos_a, c.chrom_b, c.pos_b, args.support_mix)["lr"]
    if args.oracle_truth:
        from robust_diag import noise_flags
        from truth import load_truth
        info = json.loads(Path(args.contacts + ".json").read_text())
        is_noise, ra, rb, _ = noise_flags(load_truth(args.oracle_truth), info)
        assert np.array_equal(ra, c.pos_a) and np.array_equal(rb, c.pos_b)
        prior_lr = np.where(is_noise, 0.0, 1.0)
    t0 = time.time()
    ru0 = resource.getrusage(resource.RUSAGE_SELF)
    res = un.calc_genome_structure(
        c.chrom_a.astype(str), c.pos_a, c.chrom_b.astype(str), c.pos_b, protocol="robust",
        particle_sizes=sizes, n_models=args.n_models, seed=args.seed, device=args.device,
        n_threads=args.n_threads, verbose=True,
        **({"prior_lr": prior_lr} if prior_lr is not None else {}), **params)
    wall = time.time() - t0
    ru1 = resource.getrusage(resource.RUSAGE_SELF)
    pos = np.asarray(res["position"], np.int64)
    if res["position_convention"] == "start":
        pos = pos + int(res["particle_size"])
    args.out.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(args.out, chrom=res["chrom"].astype(str), pos=pos, coords=res["coords"],
                        contact_weights=res["contact_weights"])
    w = res["contact_weights"]
    meta = {"method": args.label, "protocol": "robust", "contacts": str(args.contacts), "n_contacts": len(c),
            "particle_sizes": sizes, "n_models": args.n_models, "seed": args.seed, "device": args.device,
            "robust_params": params, "support_w": args.support_w, "support_mix": args.support_mix, "prior_lr_file": args.prior_lr,
            "oracle": bool(args.oracle_truth), "read_seconds": read_seconds, "wall_seconds": wall, "engine_seconds": res["seconds_total"],
            "cpu_seconds": (ru1.ru_utime - ru0.ru_utime) + (ru1.ru_stime - ru0.ru_stime),
            "peak_rss_mb": peak_rss_mb(), "stages": res["stages"], "params": res["params"],
            "contacts_kept": int(np.isfinite(w).sum()), "mean_weight_kept": float(np.nanmean(w)) if len(w) else None,
            "engine_version": un.__version__, "gpu": un.gpu_info() if args.device == "gpu" else None,
            "slurm_job_id": os.environ.get("SLURM_JOB_ID")}
    Path(str(args.out) + ".json").write_text(json.dumps(meta, indent=1, default=str))
    print(f"{args.contacts}: {res['coords'].shape} in {wall:.1f} s", flush=True)


if __name__ == "__main__":
    main()
