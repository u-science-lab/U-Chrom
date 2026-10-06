"""Fig. 3d: wall time of ONE single-cell model, every method, 500 kb ... 1 kb.

Same input for every method: Stevens et al. 2017 Cell 1 (GSE80280, haploid mESC), the full
GEO contact table ``GSM2219497_Cell_1_contact_pairs.txt.gz`` (111,838 contacts).  Every run
is one model, seed 1, in a fresh process, through the screcon runners
(``benchmarks/screcon/run_*.py``):

=============  ===========================================================================
method         run
=============  ===========================================================================
nucdyn_cpu     U-Chrom native NucDynamics (``uchrom_recon``), CPU f64, 1 and 16 threads
nucdyn_gpu     U-Chrom native NucDynamics, GPU f32 (wgpu / Vulkan), one H100
orig           original NucDynamics (tjs23/nuc_dynamics master 778697a, Cython), one process
hickit         hickit 0.1.1 release binary (Dip-C schedule, haploid ``-P1``), one process
sic            Si-C HEAD 2a4d445 shipped binaries, one replica, one process at a time
robust_cpu/gpu U-Chrom "robust" (branch ``Nanguage/sc-robust``; pending)
=============  ===========================================================================

Schedules (one per method, ending at the target resolution):

* NucDynamics (U-Chrom and original): the 2017 particle sizes extended below 100 kb exactly
  as for the 10 kb / 1 kb GPU runs (``engine_10kb.sbatch`` / ``engine_1kb.sbatch``):
  8, 4, 2, 0.4, 0.2, 0.1, 0.05, 0.02, 0.01, 0.005, 0.002, 0.001 Mb, truncated above the
  target, target appended (500 kb: 8, 4, 2, 0.5); 500 x 100 steps per stage.
* hickit: the Dip-C schedule (4m, 1m, 200k, 50k, 20k; ``-D5`` before stages < 200 kb)
  truncated above the target, target appended (``run_hickit.hickit_args``).
* Si-C: its own ladder (res x 2^k below 2 Mb, then refined down to res; integer kb).

Timed (``wall_seconds``): the method's own work from its input table to its model file -
parsing the contacts, filtering / preparation, the annealing / simulation, writing the model:
U-Chrom = reading the GEO table + ``calc_genome_structure``; original = the
``nuc_dynamics.py`` process (reads NCC, writes N3D); hickit = the ``hickit`` process (reads
.pairs, writes .3dg); Si-C = the 1 kb contact preparation (``do.sh`` re-done in Python + the
shipped ``gettargetcontact.o`` isolation filter), binning / merging (shipped scripts) and the
replica's MD (``doall.sh``, writes ``genome.pdb``).  Not timed: environment setup, building,
and the conversion of the GEO table into another method's input format (NCC / .pairs) and
of its output into ``.npz`` (``wall_total_seconds`` includes them).  Each run is capped at
48 h (or the job's remaining time minus 10 min, whichever is smaller); a run that reaches
the cap is killed and reported as censored (``> cap``), never extrapolated in the table.
Repeats: a run of <= 15 min is repeated to 3 runs, of <= 1 h to 2 runs, longer runs once
(median reported).

Subcommands::

    python speed_one_model.py manifest --methods nucdyn_cpu,orig,hickit,sic --out tasks.tsv
    python speed_one_model.py run --task-file tasks.tsv --task 3 --out-dir RUNS/speed_one_model
    python speed_one_model.py run --method nucdyn_gpu --res all --out-dir RUNS/speed_one_model
    python speed_one_model.py aggregate --records RUNS/speed_one_model/records \\
        --out u-chrom-paper/manuscripts/full/figures/fig3/results/speed_one_model.json

The robust method (``robust_cpu``, ``robust_gpu``) runs ``benchmarks/screcon/run_robust.py``
of ``--robust-repo`` (default: this repo) if it exists, else ``run_nucdyn.py --protocol
robust``; either must take ``run_nucdyn.py``'s arguments (``--contacts --sizes --device
--n-models --n-threads --seed --out``) and write ``<out>.json`` with ``wall_seconds`` (and
``read_seconds``).  Interpreter: ``--robust-python`` / ``$ROBUST_PY``.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import resource
import shutil
import signal
import statistics
import subprocess
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SC = ROOT / "benchmarks" / "screcon"
GEO_NAME = "GSM2219497_Cell_1_contact_pairs.txt.gz"
RESOLUTIONS = [500_000, 100_000, 50_000, 20_000, 10_000, 1_000]
LADDER_MB = [8, 4, 2, 0.4, 0.2, 0.1, 0.05, 0.02, 0.01, 0.005, 0.002, 0.001]   # engine_1kb.sbatch
CAP_SECONDS = 48 * 3600
METHODS = {
    "nucdyn_cpu": dict(label="U-Chrom NucDynamics, CPU", device="cpu", threads=[1, 16]),
    "nucdyn_gpu": dict(label="U-Chrom NucDynamics, GPU", device="gpu", threads=[0]),
    "orig": dict(label="NucDynamics (original)", device="cpu", threads=[1]),
    "hickit": dict(label="hickit (Dip-C)", device="cpu", threads=[1]),
    "sic": dict(label="Si-C", device="cpu", threads=[1]),
    "robust_cpu": dict(label="U-Chrom robust, CPU", device="cpu", threads=[1, 16]),
    "robust_gpu": dict(label="U-Chrom robust, GPU", device="gpu", threads=[0]),
}
GPU_METHODS = ("nucdyn_gpu", "robust_gpu")


def tag(res: int) -> str:
    return f"{res // 1_000_000}Mb" if res % 1_000_000 == 0 else f"{res // 1000}kb"


def nucdyn_sizes(res: int) -> list[float]:
    """The extended 2017 schedule (Mb) ending at ``res`` (bp)."""
    r = res / 1e6
    return [s for s in LADDER_MB if s > r * 1.0001] + [r]


# --------------------------------------------------------------------------- environment

def sh(cmd: str) -> str:
    try:
        return subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=60).stdout.strip()
    except Exception:  # noqa: BLE001
        return ""


def cpu_model() -> str:
    try:
        for line in open("/proc/cpuinfo"):
            if line.startswith("model name"):
                return line.split(":", 1)[1].strip()
    except OSError:
        pass
    return platform.processor()


def job_seconds_left() -> float | None:
    """Remaining wall time of the Slurm job (one squeue call), None outside Slurm."""
    jid = os.environ.get("SLURM_JOB_ID")
    if not jid:
        return None
    if os.environ.get("SLURM_ARRAY_TASK_ID"):
        jid = f"{os.environ['SLURM_ARRAY_JOB_ID']}_{os.environ['SLURM_ARRAY_TASK_ID']}"
    s = (sh(f"squeue -h -j {jid} -o %L").splitlines() or [""])[0].strip()
    if not s or s in ("INVALID", "UNLIMITED"):
        return None
    d = 0
    if "-" in s:
        d_, s = s.split("-", 1)
        d = int(d_)
    parts = [int(x) for x in s.split(":")]
    while len(parts) < 3:
        parts.insert(0, 0)
    return d * 86400 + parts[0] * 3600 + parts[1] * 60 + parts[2]


class GpuMem:
    """Peak ``memory.used`` of the visible GPU(s) during a run (nvidia-smi every second)."""

    def __init__(self):
        self.ok = shutil.which("nvidia-smi") is not None
        self.base = self._read() if self.ok else None
        self.peak = self.base
        self._stop = threading.Event()

    def _read(self):
        out = sh("nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits")
        try:
            return sum(float(x) for x in out.split())
        except ValueError:
            return None

    def __enter__(self):
        if self.ok:
            self._t = threading.Thread(target=self._loop, daemon=True)
            self._t.start()
        return self

    def _loop(self):
        while not self._stop.wait(1.0):
            v = self._read()
            if v is not None and (self.peak is None or v > self.peak):
                self.peak = v

    def __exit__(self, *a):
        self._stop.set()

    def result(self):
        if not self.ok or self.peak is None or self.base is None:
            return None
        return {"peak_used_mb": self.peak, "baseline_mb": self.base, "peak_above_baseline_mb": self.peak - self.base}


# --------------------------------------------------------------------------- one run

def build(method: str, res: int, threads: int, args, work: Path) -> tuple[list[str], Path]:
    out = work / "model.npz"
    geo = str(args.contacts)
    if method in ("nucdyn_cpu", "nucdyn_gpu", "robust_cpu", "robust_gpu"):
        dev = "gpu" if method.endswith("gpu") else "cpu"
        py = args.python
        runner, extra = SC / "run_nucdyn.py", []
        if method.startswith("robust"):
            repo = Path(args.robust_repo or ROOT)
            py = args.robust_python or os.environ.get("ROBUST_PY") or args.python
            rr = repo / "benchmarks" / "screcon" / "run_robust.py"
            runner, extra = (rr, []) if rr.exists() else (repo / "benchmarks/screcon/run_nucdyn.py", ["--protocol", "robust"])
        sizes = ",".join(f"{s:g}" for s in nucdyn_sizes(res))
        cmd = [py, str(runner), "--contacts", geo, "--sizes", sizes, "--device", dev, "--n-models", "1",
               "--n-threads", str(threads), "--seed", "1", *extra, "--out", str(out)]
    elif method == "orig":
        sizes = ",".join(f"{s:g}" for s in nucdyn_sizes(res))
        cmd = [args.orig_python, str(SC / "run_nucdyn_original.py"), "--nd-dir", args.nd_dir, "--contacts", geo,
               "--sizes", sizes, "--models", "1", "--cpu", "1", "--seed", "1", "--out", str(out)]
    elif method == "hickit":
        cmd = [args.python, str(SC / "run_hickit.py"), "--hickit", args.hickit, "--contacts", geo, "--res", str(res),
               "--assembly", "mm10", "--n-models", "1", "--jobs", "1", "--seed", "1", "--out", str(out)]
    elif method == "sic":
        if res % 1000:
            raise ValueError("Si-C needs an integer number of kb")
        cmd = [args.python, str(SC / "run_sic.py"), "--sic-dir", args.sic_dir, "--contacts", geo,
               "--res-kb", str(res // 1000), "--assembly", "mm10", "--replicas", "1", "--jobs", "1",
               "--prep-jobs", "1", "--workdir", str(work / "sic_work"), "--out", str(out)]
    else:
        raise ValueError(method)
    return cmd, out


def method_seconds(method: str, meta: dict) -> float:
    if method.startswith(("nucdyn", "robust")):
        return float(meta.get("read_seconds", 0.0)) + float(meta["wall_seconds"])
    if method == "orig":
        return float(meta["wall_seconds"])
    if method == "hickit":
        return float(meta["seconds_per_model"][0])
    if method == "sic":
        return float(meta["contact_seconds"]) + float(meta["md_seconds_wall"])
    raise ValueError(method)


def particles(method: str, meta: dict, out: Path) -> dict:
    p = {}
    if method.startswith(("nucdyn", "robust")) and meta.get("stages"):
        p["n_particles"] = int(meta["stages"][-1]["n_particles"])
    elif method == "hickit":
        p["n_particles"] = (meta.get("n_beads_hickit") or [None])[0]       # merged beads (variable length)
        p["n_particles_grid"] = meta.get("n_particles")
    elif method == "sic":
        p["n_particles"] = meta.get("n_beads")
    if "n_particles" not in p or p["n_particles"] is None:
        try:
            import numpy as np

            p["n_particles"] = int(np.load(out)["coords"].shape[1])
        except Exception:  # noqa: BLE001
            pass
    return p


def run_once(method: str, res: int, threads: int, rep: int, args, cap: float) -> dict:
    name = f"{method}_t{threads}_{tag(res)}_r{rep}"
    work = Path(args.out_dir) / "work" / f"{name}_{os.environ.get('SLURM_JOB_ID', 'local')}"
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)
    rec = {"method": method, "label": METHODS[method]["label"], "device": METHODS[method]["device"],
           "threads": threads, "res": res, "res_tag": tag(res), "repeat": rep, "seed": 1, "n_models": 1,
           "host": platform.node(), "cpu_model": cpu_model(), "cpus_allocated": len(os.sched_getaffinity(0))
           if hasattr(os, "sched_getaffinity") else os.cpu_count(),
           "slurm_job_id": os.environ.get("SLURM_JOB_ID"), "slurm_array_task": os.environ.get("SLURM_ARRAY_TASK_ID"),
           "slurm_partition": os.environ.get("SLURM_JOB_PARTITION"),
           "slurm_mem_mb": os.environ.get("SLURM_MEM_PER_NODE"), "cap_seconds": cap,
           "load_avg_before": os.getloadavg(), "started_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    try:
        cmd, out = build(method, res, threads, args, work)
    except ValueError as e:
        rec.update(status="not_run", reason=str(e))
        return rec
    rec["cmd"] = cmd
    env = dict(os.environ)
    nt = str(threads or rec["cpus_allocated"])
    env.update(OMP_NUM_THREADS=nt, OPENBLAS_NUM_THREADS=nt, MKL_NUM_THREADS=nt, RAYON_NUM_THREADS=nt)
    if method in GPU_METHODS:
        rec["gpu_name"] = sh("nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader")
    t0 = time.perf_counter()
    with GpuMem() if method in GPU_METHODS else _Null() as gm, open(work / "runner.log", "w") as log:
        p = subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT, env=env, start_new_session=True)
        try:
            rc = p.wait(timeout=cap)
        except subprocess.TimeoutExpired:
            for sig in (signal.SIGTERM, signal.SIGKILL):
                try:
                    os.killpg(p.pid, sig)
                except ProcessLookupError:
                    break
                try:
                    p.wait(timeout=30)
                    break
                except subprocess.TimeoutExpired:
                    continue
            rc = None
    elapsed = time.perf_counter() - t0
    rec["wall_total_seconds"] = elapsed
    rec["peak_rss_mb_children_job_max"] = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss / 1e3
    rec["load_avg_after"] = os.getloadavg()
    if gm is not None and hasattr(gm, "result"):
        rec["gpu_memory"] = gm.result()
    log_tail = (work / "runner.log").read_text(errors="replace")[-3000:]
    if rc is None:
        rec.update(status="censored", wall_seconds_lower_bound=elapsed,
                   reason=f"killed at the cap ({cap / 3600:.2f} h)")
    elif rc != 0:
        why = f"exit code {rc}"
        if rc in (-9, 137):
            why += f" (SIGKILL: most likely out of memory, job memory {rec['slurm_mem_mb']} MB)"
        rec.update(status="failed", reason=why, log_tail=log_tail)
    else:
        meta = json.loads(Path(str(out) + ".json").read_text())
        rec["wall_seconds"] = method_seconds(method, meta)
        rec.update(particles(method, meta, out))
        rec["peak_rss_mb"] = meta.get("peak_rss_mb", meta.get("peak_rss_mb_largest_child"))
        rec["runner_meta"] = {k: v for k, v in meta.items() if k not in ("stages", "chrom_lengths", "chroms", "params")}
        if meta.get("stages"):
            rec["stages"] = [{k: s.get(k) for k in ("particle_size", "n_particles", "seconds_prepare",
                                                     "seconds_dynamics", "device")} for s in meta["stages"]]
        rec["status"] = "ok"
    rec["log_tail"] = log_tail[-1500:]
    if not args.keep:
        shutil.rmtree(work, ignore_errors=True)
    return rec


class _Null:
    def __enter__(self):
        return None

    def __exit__(self, *a):
        return False


def run_config(method: str, res_list: list[int], threads: int, args) -> None:
    recdir = Path(args.out_dir) / "records"
    recdir.mkdir(parents=True, exist_ok=True)
    t_job0 = time.time()
    left = job_seconds_left()
    budget = min(CAP_SECONDS, left - 600) if left else CAP_SECONDS
    for res in res_list:
        rep = 1
        while True:
            remaining = budget - (time.time() - t_job0)
            if remaining < 60:
                print(f"no time left for {method} {tag(res)} r{rep}", flush=True)
                return
            rec = run_once(method, res, threads, rep, args, cap=min(CAP_SECONDS, remaining))
            rec["cap_is_full"] = rec["cap_seconds"] >= CAP_SECONDS - 1
            f = recdir / f"{method}_t{threads}_{tag(res)}_r{rep}_{os.environ.get('SLURM_JOB_ID', 'local')}.json"
            f.write_text(json.dumps(rec, indent=1, default=str))
            print(json.dumps({k: rec.get(k) for k in ("method", "threads", "res_tag", "repeat", "status", "wall_seconds",
                                                       "wall_total_seconds", "n_particles", "peak_rss_mb", "reason")}),
                  flush=True)
            if rec["status"] != "ok":
                break
            w = rec["wall_total_seconds"]
            want = 3 if w <= 900 else 2 if w <= 3600 else 1
            if rep >= want or (time.time() - t_job0) + 1.5 * w > budget:
                break
            rep += 1


# --------------------------------------------------------------------------- manifest / aggregate

def configs(methods: list[str]) -> list[tuple[str, int]]:
    return [(m, t) for m in methods for t in METHODS[m]["threads"]]


def cmd_manifest(args) -> None:
    lines = []
    for m, t in configs(args.methods.split(",")):
        if m in GPU_METHODS:
            lines.append(f"{m}\t{t}\tall")
        else:
            lines.extend(f"{m}\t{t}\t{r}" for r in RESOLUTIONS)
    Path(args.out).write_text("\n".join(lines) + "\n")
    print(f"{args.out}: {len(lines)} tasks")


def cmd_run(args) -> None:
    if args.task_file:
        m, t, r = Path(args.task_file).read_text().splitlines()[args.task - 1].split("\t")
        args.method, args.threads, args.res = m, int(t), r
    res_list = RESOLUTIONS if args.res == "all" else [int(float(x)) for x in str(args.res).split(",")]
    threads = args.threads if args.threads is not None else METHODS[args.method]["threads"][0]
    print(f"host={platform.node()} cpu={cpu_model()} method={args.method} threads={threads} res={res_list}", flush=True)
    run_config(args.method, res_list, threads, args)


def _fit_extrapolation(rows_ok: list[dict], res: int) -> dict | None:
    """Power law t = a * (1/res)^b through the finished resolutions of one configuration."""
    import math

    pts = sorted(((r["res"], r["median_wall_seconds"]) for r in rows_ok), key=lambda x: -x[0])
    pts = [p for p in pts if p[0] <= 500_000][-3:]
    if len(pts) < 2:
        return None
    xs = [math.log(1 / p[0]) for p in pts]
    ys = [math.log(p[1]) for p in pts]
    mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
    b = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sum((x - mx) ** 2 for x in xs)
    a = my - b * mx
    return {"seconds": math.exp(a + b * math.log(1 / res)), "exponent": b,
            "fit_resolutions": [p[0] for p in pts], "label": "EXTRAPOLATED (power-law fit), not measured"}


def cmd_aggregate(args) -> None:
    recs = []
    for f in sorted(Path(args.records).glob("*.json")):
        recs.append(json.loads(f.read_text()))
    groups: dict[tuple, list[dict]] = {}
    for r in recs:
        groups.setdefault((r["method"], int(r["threads"]), int(r["res"])), []).append(r)
    rows = []
    for m, t in configs(list(METHODS)):
        for res in RESOLUTIONS:
            g = groups.get((m, t, res), [])
            ok = [r for r in g if r["status"] == "ok"]
            cens = [r for r in g if r["status"] == "censored"]
            fail = [r for r in g if r["status"] == "failed"]
            row = {"method": m, "label": METHODS[m]["label"], "device": METHODS[m]["device"], "threads": t,
                   "res": res, "res_tag": tag(res), "n_runs": len(g)}
            if ok:
                w = [r["wall_seconds"] for r in ok]
                row.update(status="ok", n=len(ok), median_wall_seconds=statistics.median(w), wall_seconds=w,
                           wall_total_seconds=[r["wall_total_seconds"] for r in ok],
                           peak_rss_mb=max(r.get("peak_rss_mb") or 0 for r in ok) or None,
                           n_particles=ok[0].get("n_particles"), n_particles_grid=ok[0].get("n_particles_grid"),
                           hosts=sorted({r["host"] for r in ok}), cpu_model=sorted({r["cpu_model"] for r in ok}))
                gm = [r.get("gpu_memory") for r in ok if r.get("gpu_memory")]
                if gm:
                    row["gpu_memory_peak_above_baseline_mb"] = max(x["peak_above_baseline_mb"] for x in gm)
                    row["gpu_name"] = ok[0].get("gpu_name")
                if cens or fail:
                    row["other_runs"] = [{"status": r["status"], "reason": r.get("reason")} for r in cens + fail]
            elif cens:
                full = [r for r in cens if r.get("cap_is_full")]
                c = max(cens, key=lambda r: r["cap_seconds"])
                row.update(status="censored" if full else "censored_short_cap",
                           censored_at_seconds=c["wall_seconds_lower_bound"], cap_seconds=c["cap_seconds"],
                           reason=c["reason"], hosts=[c["host"]], cpu_model=[c["cpu_model"]])
            elif fail:
                f = fail[-1]
                row.update(status="failed", reason=f["reason"], log_tail=f.get("log_tail", "")[-600:],
                           hosts=[f["host"]], cpu_model=[f["cpu_model"]])
            elif g and all(r["status"] == "not_run" for r in g):
                row.update(status="not_run", reason=g[0]["reason"])
            elif m.startswith("robust"):
                row.update(status="pending", reason="method under development (branch Nanguage/sc-robust); "
                           "add with: speed_one_model.py manifest --methods robust_cpu,robust_gpu")
            else:
                row.update(status="pending", reason="no record yet (queued or running)")
            rows.append(row)
    extrap = []
    for m, t in configs(list(METHODS)):
        cfg = [r for r in rows if r["method"] == m and r["threads"] == t]
        ok = [r for r in cfg if r["status"] == "ok"]
        for r in cfg:
            if r["status"].startswith("censored"):
                e = _fit_extrapolation(ok, r["res"])
                if e:
                    extrap.append({"method": m, "threads": t, "res": r["res"], **e})
    cpu_models = sorted({c for r in rows if r["device"] == "cpu" for c in r.get("cpu_model", [])})
    gpu_names = sorted({r["gpu_name"] for r in rows if r.get("gpu_name")})
    report = {
        "what": "wall time to compute ONE single-cell model (seed 1), Stevens 2017 Cell 1, per method and resolution",
        "input": f"{GEO_NAME} (GSE80280, haploid mESC, full contact table, 111,838 contacts); same file for all methods",
        "timed": "method's own work from its input table to its model file (contact parsing, filtering / preparation, "
                 "annealing / simulation, model output); excluded: environment setup, conversion of the GEO table to "
                 "NCC (original) / .pairs (hickit) and of the outputs to .npz (wall_total_seconds includes them)",
        "hardware": {"cpu": cpu_models, "gpu": gpu_names,
                     "cpu_runs": "Slurm --constraint=CPU_SKU:9754 (AMD EPYC 9754, 256-core nodes, shared with "
                                 "other jobs), --cpus-per-task = thread count, one process per run",
                     "gpu_runs": "one NVIDIA H100 SXM5 80 GB (-G 1, -C GPU_SKU:H100_SXM5), wgpu / Vulkan, f32"},
        "threads": "1 thread for every CPU method (original NucDynamics, hickit and Si-C are single-threaded per "
                   "model); U-Chrom CPU (and robust CPU) also with 16 threads (parallel force loops)",
        "cap_hours": CAP_SECONDS / 3600,
        "repeats": "<= 15 min: 3 runs, <= 1 h: 2 runs, longer: 1 run; median reported; same seed in every repeat",
        "schedules": {
            "nucdyn": f"2017 schedule extended below 100 kb ({', '.join(f'{s:g}' for s in LADDER_MB)} Mb), "
                      "truncated above the target, target appended; 500 temperature x 100 dynamics steps per stage",
            "hickit": "Dip-C: -r1m -c1 -r10m -c5 then -b4m -b1m -b200k (-D5 -b50k) (-D5 -b20k) truncated above the "
                      "target, -b<target> appended, -P1 (haploid, no -S / imputation); empty beads merged",
            "sic": "Si-C's own ladder: res x 2^k < 2 Mb, refined down to res (integer kb); one replica",
        },
        "caveats": [
            "Si-C runs its precompiled x86-64 binaries (the C sources cannot be rebuilt); its 1 kb contact "
            "preparation is re-done in Python (the shipped script needs MySQL's `replace`).",
            "hickit merges consecutive beads without contacts, so it simulates far fewer beads than the "
            "nominal resolution (n_particles = its final bead count; n_particles_grid = the regular grid).",
            "Each method uses its own schedule (stages, steps); times are for each method's default protocol "
            "at the target resolution, not for equal work.",
            "CPU nodes are shared with other jobs (fixed core count, not exclusive): memory bandwidth "
            "contention can add noise; load averages are in the records.",
            "The GPU runs use 8 host cores of the GPU node (Intel Xeon 8462Y+), a different CPU from the CPU runs.",
        ],
        "rows": rows,
        "extrapolation": {"note": "separate from the measured table: power-law fit (t ~ (1/res)^b) of the finished "
                                  "resolutions of the same configuration; NOT measured", "rows": extrap},
    }
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(report, indent=1, default=str))
    for r in rows:
        v = (f"{r['median_wall_seconds']:.1f} s (n={r['n']})" if r["status"] == "ok"
             else f"> {r['censored_at_seconds'] / 3600:.1f} h" if r["status"].startswith("censored") else r.get("reason", ""))
        print(f"{r['method']:11s} t{r['threads']:<3d} {r['res_tag']:>6s}  {r['status']:9s} {v}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("manifest")
    a.add_argument("--methods", default="nucdyn_cpu,nucdyn_gpu,orig,hickit,sic")
    a.add_argument("--out", required=True)
    r = sub.add_parser("run")
    r.add_argument("--task-file")
    r.add_argument("--task", type=int)
    r.add_argument("--method", choices=list(METHODS))
    r.add_argument("--res", default="all", help="bp, comma separated, or 'all'")
    r.add_argument("--threads", type=int)
    r.add_argument("--out-dir", required=True)
    r.add_argument("--contacts", default=os.environ.get("CONTACTS", str(ROOT / "example-data/stevens2017_mesc" / GEO_NAME)))
    r.add_argument("--python", default=os.environ.get("PY", sys.executable))
    r.add_argument("--orig-python", default=os.environ.get("ORIG_PY", sys.executable))
    r.add_argument("--nd-dir", default=os.environ.get("ND"))
    r.add_argument("--hickit", default=os.environ.get("HICKIT"))
    r.add_argument("--sic-dir", default=os.environ.get("SIC"))
    r.add_argument("--robust-repo", default=os.environ.get("ROBUST_REPO"))
    r.add_argument("--robust-python", default=None)
    r.add_argument("--keep", action="store_true", help="keep the work directories (models, logs)")
    g = sub.add_parser("aggregate")
    g.add_argument("--records", required=True)
    g.add_argument("--out", required=True)
    args = ap.parse_args()
    {"manifest": cmd_manifest, "run": cmd_run, "aggregate": cmd_aggregate}[args.cmd](args)


if __name__ == "__main__":
    main()
