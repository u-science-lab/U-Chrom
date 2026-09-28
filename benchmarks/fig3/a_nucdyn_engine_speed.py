"""Speed of the native NucDynamics engine (and of the old Taichi port).

Every configuration runs in its own subprocess (so peak memory is its own)
on the same input, Stevens et al. 2017 Cell 1 (GEO contact table), and
records wall time, process CPU time (user + system of the subprocess), peak
RSS and the load average (the machine may be shared: CPU time divided by
the thread count is the wall time the run would need on idle cores).

Suites (``--suite``):

* ``ensemble``  : 10 models, full default schedule (8 → 0.1 Mb, 500 x 100
  steps per stage): GPU; CPU with all threads; CPU 1 thread with 1 model
  (per-model cost).
* ``models``    : throughput vs ensemble size, n_models 1 … 64, GPU and CPU
  (all threads), schedule shortened to ``--temp-steps`` temperature steps
  per stage (per-step costs do not depend on the number of temperature
  steps; totals are reported as measured and scaled to 500 steps).
* ``particles`` : final resolution 1 Mb, 500 kb, 200 kb, 100 kb (10 models,
  shortened schedule), GPU and CPU.
* ``taichi``    : the old Taichi port (``uchrom.recon.sc.nucdyn.nucdyn``,
  default settings, 500 steps per stage), CPU and GPU (Metal/CUDA), one
  model per run.

Usage::

    python benchmarks/fig3/a_nucdyn_engine_speed.py --suite ensemble models particles taichi \\
        --out paper/fig3/results/a_nucdyn_engine_speed.json
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import resource
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GEO = ROOT / "example-data" / "stevens2017_mesc" / "GSM2219497_Cell_1_contact_pairs.txt.gz"
PAIRS = ROOT / "example-data" / "cell1.pairs"


def worker(cfg: dict) -> dict:
    """Run one configuration in this process and return its measurements."""
    t0, c0 = time.perf_counter(), time.process_time()
    if cfg["engine"] == "native":
        import uchrom_nucdyn as un

        c = un.read_contact_pairs(str(GEO))
        kw = dict(n_models=cfg["n_models"], device=cfg["device"], n_threads=cfg.get("n_threads", 0), seed=1,
                  particle_sizes=cfg.get("particle_sizes", [8e6, 4e6, 2e6, 4e5, 2e5, 1e5]),
                  temp_steps=[cfg.get("temp_steps", 500)], dynamics_steps=[100])
        res = un.calc_genome_structure(c["chrom_a"], c["pos_a"], c["chrom_b"], c["pos_b"], **kw)
        out = {"stages": [{k: s[k] for k in ("particle_size", "n_particles", "n_models", "seconds_dynamics",
                                              "seconds_prepare")} for s in res["stages"]],
               "engine_seconds": res["seconds_total"], "n_particles": int(res["coords"].shape[1]),
               "gpu": un.gpu_info() if cfg["device"] == "gpu" else None}
    else:
        import warnings

        warnings.simplefilter("ignore", DeprecationWarning)
        from uchrom.recon.sc.nucdyn.nucdyn import main as taichi_main

        with tempfile.TemporaryDirectory() as d:
            taichi_main(str(PAIRS), os.path.join(d, "out.csv"), arch=cfg["arch"])
        out = {}
    out["wall_seconds"] = time.perf_counter() - t0
    out["cpu_seconds"] = time.process_time() - c0
    r = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    out["peak_rss_mb"] = r / 1e6 if sys.platform == "darwin" else r / 1e3
    return out


def run_sub(cfg: dict) -> dict:
    load0 = os.getloadavg()
    t0 = time.perf_counter()
    p = subprocess.run([sys.executable, __file__, "--worker", json.dumps(cfg)], capture_output=True, text=True)
    if p.returncode != 0:
        return {**cfg, "error": p.stderr[-2000:], "wall_seconds_outer": time.perf_counter() - t0}
    line = [x for x in p.stdout.splitlines() if x.startswith("{")][-1]
    res = json.loads(line)
    res.update(cfg)
    res["load_avg_before"] = load0
    res["load_avg_after"] = os.getloadavg()
    print(json.dumps({k: v for k, v in res.items() if k != "stages"}), flush=True)
    return res


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--worker")
    ap.add_argument("--suite", nargs="+", default=["ensemble"])
    ap.add_argument("--temp-steps", type=int, default=50)
    ap.add_argument("--threads", type=int, default=os.cpu_count())
    ap.add_argument("--devices", nargs="+", default=["gpu", "cpu"], help="native engine devices to run")
    ap.add_argument("--out", type=Path)
    args = ap.parse_args()
    if args.worker:
        print(json.dumps(worker(json.loads(args.worker))))
        return
    import uchrom_nucdyn as un

    report = {"machine": platform.platform(), "processor": platform.processor(), "cpu_count": os.cpu_count(),
              "gpu": un.gpu_info(), "engine_version": un.__version__, "input": GEO.name, "runs": {}}
    if args.out and args.out.exists():
        report = json.loads(args.out.read_text())
    devs = set(args.devices)

    def save():
        if args.out:
            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.write_text(json.dumps(report, indent=1))

    ts = args.temp_steps
    for suite in args.suite:
        runs = []
        if suite == "ensemble":
            if "gpu" in devs:
                runs.append(run_sub({"engine": "native", "device": "gpu", "n_models": 10}))
            if "cpu" in devs:
                runs.append(run_sub({"engine": "native", "device": "cpu", "n_models": 10, "n_threads": args.threads}))
                runs.append(run_sub({"engine": "native", "device": "cpu", "n_models": 1, "n_threads": 1}))
        elif suite == "models":
            for dev in [d for d in ("gpu", "cpu") if d in devs]:
                for m in (1, 2, 4, 8, 16, 32, 64):
                    runs.append(run_sub({"engine": "native", "device": dev, "n_models": m, "temp_steps": ts,
                                         "n_threads": args.threads}))
        elif suite == "particles":
            schedules = {"1Mb": [8e6, 4e6, 2e6, 1e6], "500kb": [8e6, 4e6, 2e6, 5e5],
                         "200kb": [8e6, 4e6, 2e6, 4e5, 2e5], "100kb": [8e6, 4e6, 2e6, 4e5, 2e5, 1e5]}
            for dev in [d for d in ("gpu", "cpu") if d in devs]:
                for name, sizes in schedules.items():
                    runs.append(run_sub({"engine": "native", "device": dev, "n_models": 10, "temp_steps": ts,
                                         "particle_sizes": sizes, "final": name, "n_threads": args.threads}))
        elif suite == "taichi":
            for arch in ("cpu", "gpu"):
                runs.append(run_sub({"engine": "taichi", "arch": arch}))
        key = suite if devs == {"gpu", "cpu"} or suite == "taichi" else f"{suite}_{'_'.join(sorted(devs))}"
        report["runs"][key] = runs
        save()


if __name__ == "__main__":
    main()
