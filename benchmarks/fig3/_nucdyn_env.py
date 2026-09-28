"""Shared helpers for the Fig. 3a NucDynamics benchmark scripts (cluster-ready).

* ``data_dir()``: the Stevens et al. 2017 GEO files (``<GSM>_Cell_<n>_*.gz``):
  ``$NUCDYN_GEO_DIR``, else ``$UCHROM_EXAMPLE_DATA/stevens2017_mesc``, else
  ``<repo>/example-data/stevens2017_mesc``.
* ``environment()``: host, CPU, GPU, library versions, Slurm job and load
  average, printed by every script and stored in its JSON output.
"""

from __future__ import annotations

import os
import platform
import socket
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GSM = {1: "GSM2219497", 2: "GSM2219498", 3: "GSM2219499", 4: "GSM2219500",
       5: "GSM2219501", 6: "GSM2219502", 7: "GSM2219503", 8: "GSM2219504"}


def data_dir() -> Path:
    if os.environ.get("NUCDYN_GEO_DIR"):
        return Path(os.environ["NUCDYN_GEO_DIR"])
    if os.environ.get("UCHROM_EXAMPLE_DATA"):
        return Path(os.environ["UCHROM_EXAMPLE_DATA"]) / "stevens2017_mesc"
    return ROOT / "example-data" / "stevens2017_mesc"


def geo_pairs(cell: int, geo_dir: Path | None = None) -> Path:
    return Path(geo_dir or data_dir()) / f"{GSM[cell]}_Cell_{cell}_contact_pairs.txt.gz"


def geo_pdb(cell: int, geo_dir: Path | None = None) -> Path:
    return Path(geo_dir or data_dir()) / f"{GSM[cell]}_Cell_{cell}_genome_structure_model.pdb.gz"


def _cpu_model() -> str:
    try:
        if sys.platform == "darwin":
            return subprocess.run(["sysctl", "-n", "machdep.cpu.brand_string"], capture_output=True,
                                  text=True).stdout.strip()
        with open("/proc/cpuinfo") as fh:
            for line in fh:
                if line.startswith("model name"):
                    return line.split(":", 1)[1].strip()
    except Exception:
        pass
    return platform.processor()


def _nvidia() -> str | None:
    try:
        p = subprocess.run(["nvidia-smi", "--query-gpu=name,driver_version,memory.total", "--format=csv,noheader"],
                           capture_output=True, text=True, timeout=10)
        return p.stdout.strip() or None
    except Exception:
        return None


def environment() -> dict:
    env = {
        "host": socket.gethostname(),
        "platform": platform.platform(),
        "cpu": _cpu_model(),
        "cpu_count": os.cpu_count(),
        "slurm_cpus_per_task": os.environ.get("SLURM_CPUS_PER_TASK"),
        "slurm_job_id": os.environ.get("SLURM_JOB_ID"),
        "python": sys.version.split()[0],
        "load_avg": list(os.getloadavg()) if hasattr(os, "getloadavg") else None,
        "nvidia_smi": _nvidia(),
    }
    try:
        import numpy

        env["numpy"] = numpy.__version__
    except ImportError:
        pass
    try:
        import uchrom_nucdyn as un

        env["uchrom_nucdyn"] = un.__version__
        env["uchrom_nucdyn_gpu_build"] = bool(un.HAS_GPU)
        env["gpu"] = un.gpu_info()
    except ImportError:
        pass
    try:
        import Cython

        env["cython"] = Cython.__version__
    except ImportError:
        pass
    return env


def print_environment(tag: str = "") -> dict:
    env = environment()
    print(f"[environment{(' ' + tag) if tag else ''}] " + " ".join(f"{k}={v}" for k, v in env.items()), flush=True)
    return env
