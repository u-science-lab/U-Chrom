"""Run the native NucDynamics engine on the Stevens et al. 2017 cells.

For every requested cell the GEO contact table (GSE80280,
``example-data/stevens2017_mesc/<GSM>_Cell_<n>_contact_pairs.txt.gz``) is run
through ``uchrom_nucdyn.calc_genome_structure`` with the original schedule
(8, 4, 2, 0.4, 0.2, 0.1 Mb; 500 x 100 steps per stage) and the models are
written as ``<out>/cell<n>.npz`` with the keys the validation harness reads
(``chrom``, ``pos`` = particle sequence position in the 2017 convention,
i.e. the particle covers ``(pos - size, pos]``, ``coords`` (models,
particles, 3)), plus the per-stage log,
wall time and peak memory in ``<out>/cell<n>.json``.

Usage::

    python benchmarks/fig3/a_nucdyn_engine_run.py --cells 1-8 --device cpu --n-models 10 --out RUN_DIR
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import resource
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
GEO_DIR = ROOT / "example-data" / "stevens2017_mesc"
GSM = {1: "GSM2219497", 2: "GSM2219498", 3: "GSM2219499", 4: "GSM2219500",
       5: "GSM2219501", 6: "GSM2219502", 7: "GSM2219503", 8: "GSM2219504"}


def parse_cells(s: str) -> list[int]:
    out = []
    for part in s.split(","):
        if "-" in part:
            a, b = part.split("-")
            out.extend(range(int(a), int(b) + 1))
        else:
            out.append(int(part))
    return out


def peak_rss_mb() -> float:
    r = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return r / 1e6 if sys.platform == "darwin" else r / 1e3


def main() -> None:
    import uchrom_nucdyn as un

    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cells", default="1-8")
    ap.add_argument("--device", default="cpu", choices=["cpu", "gpu"])
    ap.add_argument("--n-models", type=int, default=10)
    ap.add_argument("--n-threads", type=int, default=0)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--protocol", default="nuc_dynamics_2017")
    ap.add_argument("--particle-sizes", default="8,4,2,0.4,0.2,0.1", help="Mb")
    ap.add_argument("--temp-steps", type=int, default=500)
    ap.add_argument("--dyn-steps", type=int, default=100)
    ap.add_argument("--geo-dir", type=Path, default=GEO_DIR)
    ap.add_argument("--extra", default="{}", help="JSON of further engine parameters")
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    sizes = [float(x) * 1e6 for x in args.particle_sizes.split(",")]
    for cell in parse_cells(args.cells):
        path = args.geo_dir / f"{GSM[cell]}_Cell_{cell}_contact_pairs.txt.gz"
        c = un.read_contact_pairs(str(path))
        t0 = time.time()
        ru0 = resource.getrusage(resource.RUSAGE_SELF)
        load0 = os.getloadavg()
        res = un.calc_genome_structure(
            c["chrom_a"], c["pos_a"], c["chrom_b"], c["pos_b"],
            protocol=args.protocol, particle_sizes=sizes, n_models=args.n_models, seed=args.seed,
            device=args.device, n_threads=args.n_threads, temp_steps=[args.temp_steps],
            dynamics_steps=[args.dyn_steps], verbose=True, **json.loads(args.extra))
        wall = time.time() - t0
        ru1 = resource.getrusage(resource.RUSAGE_SELF)
        cpu = (ru1.ru_utime - ru0.ru_utime) + (ru1.ru_stime - ru0.ru_stime)
        # pos in the 2017 convention (particle = (pos - size, pos]); release_1.3
        # particles are [p, p + size), i.e. pos = p + size
        pos = np.asarray(res["position"], np.int64)
        if res["position_convention"] == "start":
            pos = pos + int(res["particle_size"])
        np.savez_compressed(args.out / f"cell{cell}.npz", chrom=res["chrom"].astype(str), pos=pos,
                            coords=res["coords"])
        meta = {
            "cell": cell, "input": str(path.name), "n_contacts_input": int(len(c["pos_a"])),
            "device": args.device, "n_models": args.n_models, "n_threads": args.n_threads,
            "seed": args.seed, "protocol": args.protocol, "wall_seconds": wall,
            "engine_seconds": res["seconds_total"], "cpu_seconds": cpu, "peak_rss_mb": peak_rss_mb(),
            "load_avg_before": load0, "load_avg_after": os.getloadavg(),
            "stages": res["stages"], "params": res["params"], "engine_version": un.__version__,
            "gpu": un.gpu_info() if args.device == "gpu" else None,
            "machine": platform.platform(), "processor": platform.processor(),
        }
        (args.out / f"cell{cell}.json").write_text(json.dumps(meta, indent=1))
        print(f"cell {cell}: {res['coords'].shape} in {wall:.1f} s, peak RSS {meta['peak_rss_mb']:.0f} MB", flush=True)


if __name__ == "__main__":
    main()
