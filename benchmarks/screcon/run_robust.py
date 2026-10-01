"""The new single-cell method (``robust``, PREREG.md §7, milestone M2) on an arbitrary contact table.

Native engine (``uchrom_nucdyn``), protocol ``robust``: the NucDynamics 2017 protocol with a
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

#: parameters of the method (engine defaults otherwise); changed only by dev-set experiments
ROBUST_DEFAULTS: dict = {}


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--contacts", required=True)
    ap.add_argument("--res", type=float, default=1e5, help="final particle size, bp")
    ap.add_argument("--sizes", help="explicit schedule, Mb, comma separated (overrides --res)")
    ap.add_argument("--device", default="gpu", choices=["cpu", "gpu"])
    ap.add_argument("--n-models", type=int, default=10)
    ap.add_argument("--n-threads", type=int, default=0)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--temp-steps", type=int, default=500)
    ap.add_argument("--dyn-steps", type=int, default=100)
    ap.add_argument("--params", default="{}", help="JSON of engine parameters overriding ROBUST_DEFAULTS")
    ap.add_argument("--label", default="robust", help="method name written to the .json")
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args(argv)
    import uchrom_nucdyn as un

    params = {**ROBUST_DEFAULTS, **json.loads(args.params)}
    sizes = [float(x) * 1e6 for x in args.sizes.split(",")] if args.sizes else schedule(args.res)
    c = read_contacts(args.contacts)
    t0 = time.time()
    ru0 = resource.getrusage(resource.RUSAGE_SELF)
    res = un.calc_genome_structure(
        c.chrom_a.astype(str), c.pos_a, c.chrom_b.astype(str), c.pos_b, protocol="robust",
        particle_sizes=sizes, n_models=args.n_models, seed=args.seed, device=args.device,
        n_threads=args.n_threads, temp_steps=[args.temp_steps], dynamics_steps=[args.dyn_steps], verbose=True,
        **params)
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
            "robust_params": params, "wall_seconds": wall, "engine_seconds": res["seconds_total"],
            "cpu_seconds": (ru1.ru_utime - ru0.ru_utime) + (ru1.ru_stime - ru0.ru_stime),
            "peak_rss_mb": peak_rss_mb(), "stages": res["stages"], "params": res["params"],
            "contacts_kept": int(np.isfinite(w).sum()), "mean_weight_kept": float(np.nanmean(w)) if len(w) else None,
            "engine_version": un.__version__, "gpu": un.gpu_info() if args.device == "gpu" else None,
            "slurm_job_id": os.environ.get("SLURM_JOB_ID")}
    Path(str(args.out) + ".json").write_text(json.dumps(meta, indent=1, default=str))
    print(f"{args.contacts}: {res['coords'].shape} in {wall:.1f} s", flush=True)


if __name__ == "__main__":
    main()
