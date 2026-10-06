"""U-Chrom native NucDynamics engine (``uchrom_recon``) on an arbitrary contact table.

Same calls as ``benchmarks/fig3/a_nucdyn_engine_run.py``, but for any GEO / .pairs table
(held-out training tables, simulated tables) and any final resolution.  The particle
schedule is the NucDynamics one (8, 4, 2, 0.4, 0.2, 0.1 Mb) truncated above the final
size, with the final size appended (e.g. 1 Mb -> 8, 4, 2, 1; 50 kb -> ..., 0.1, 0.05).

Writes ``--out`` (``.npz``: ``chrom``, ``pos`` [2017 convention], ``coords`` (M, N, 3),
particle radii) and ``<out>.json`` (timings, stages, parameters)::

    python benchmarks/screcon/run_nucdyn.py --contacts train.txt.gz --res 100000 --device cpu \\
        --n-models 10 --seed 1 --out RUN/nucdyn_cpu.npz
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

DEFAULT_SIZES = [8e6, 4e6, 2e6, 4e5, 2e5, 1e5]


def schedule(res: float, sizes=DEFAULT_SIZES) -> list[float]:
    """NucDynamics particle sizes (bp) ending at ``res``."""
    out = [s for s in sizes if s > res * 1.0001]
    return out + [float(res)]


def peak_rss_mb() -> float:
    r = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return r / 1e6 if sys.platform == "darwin" else r / 1e3


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--contacts", required=True)
    ap.add_argument("--res", type=float, default=1e5, help="final particle size, bp")
    ap.add_argument("--sizes", help="explicit schedule, Mb, comma separated (overrides --res)")
    ap.add_argument("--device", default="cpu", choices=["cpu", "gpu"])
    ap.add_argument("--n-models", type=int, default=10)
    ap.add_argument("--n-threads", type=int, default=0)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--protocol", default="nuc_dynamics_2017")
    ap.add_argument("--temp-steps", type=int, default=500)
    ap.add_argument("--dyn-steps", type=int, default=100)
    ap.add_argument("--extra", default="{}", help="JSON of further engine parameters")
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args(argv)
    import uchrom_recon as un

    sizes = [float(x) * 1e6 for x in args.sizes.split(",")] if args.sizes else schedule(args.res)
    tr = time.time()
    c = read_contacts(args.contacts)
    read_seconds = time.time() - tr
    t0 = time.time()
    ru0 = resource.getrusage(resource.RUSAGE_SELF)
    res = un.calc_genome_structure(
        c.chrom_a.astype(str), c.pos_a, c.chrom_b.astype(str), c.pos_b, protocol=args.protocol,
        particle_sizes=sizes, n_models=args.n_models, seed=args.seed, device=args.device,
        n_threads=args.n_threads, temp_steps=[args.temp_steps], dynamics_steps=[args.dyn_steps], verbose=True,
        **json.loads(args.extra))
    wall = time.time() - t0
    ru1 = resource.getrusage(resource.RUSAGE_SELF)
    pos = np.asarray(res["position"], np.int64)
    if res["position_convention"] == "start":
        pos = pos + int(res["particle_size"])
    args.out.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(args.out, chrom=res["chrom"].astype(str), pos=pos, coords=res["coords"])
    meta = {"method": f"uchrom_nucdyn_{args.device}", "contacts": str(args.contacts), "n_contacts": len(c),
            "particle_sizes": sizes, "n_models": args.n_models, "seed": args.seed, "device": args.device,
            "read_seconds": read_seconds, "wall_seconds": wall, "engine_seconds": res["seconds_total"],
            "cpu_seconds": (ru1.ru_utime - ru0.ru_utime) + (ru1.ru_stime - ru0.ru_stime),
            "peak_rss_mb": peak_rss_mb(), "stages": res["stages"], "params": res["params"],
            "engine_version": un.__version__, "gpu": un.gpu_info() if args.device == "gpu" else None,
            "slurm_job_id": os.environ.get("SLURM_JOB_ID")}
    Path(str(args.out) + ".json").write_text(json.dumps(meta, indent=1, default=str))
    print(f"{args.contacts}: {res['coords'].shape} in {wall:.1f} s", flush=True)


if __name__ == "__main__":
    main()
