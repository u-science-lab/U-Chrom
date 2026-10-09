"""Benchmark results with their provenance: what was run, on what, where — so that scores and speeds measured
during development stay comparable and can be checked again.

Every benchmark writes its numbers with :func:`save` (a JSON ``{"results": ..., "provenance": ...}``); the
headline files are committed under ``benchmarks/<name>/results/`` (small: numbers, not data), the large outputs
of a run (call tables, maps, models) are archived on Oak (``$OAK/uchrom/results/<name>/<date>_<revision>/``),
and :func:`compare` tells how a new run differs from a committed one::

    from _record import save, compare
    save(out / "insulation.json", results, script=__file__, datasets=["rao2014_imr90_chr21"], params=vars(args))
    compare("benchmarks/hic_structures/results/insulation.json", out / "insulation.json", rtol=0.02)

The revision is the git commit of the code that ran (``+dirty`` with uncommitted changes); a repo copy synced to
a cluster has no ``.git``, so the sync writes it into ``REVISION`` at the copy's root
(``git describe --always --dirty --abbrev=12 > REVISION`` before the rsync), and a job exports it as
``UCHROM_REVISION`` when it starts.
"""

from __future__ import annotations

import datetime as _dt
import json
import math
import os
import platform
import socket
import subprocess
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

REPO = Path(__file__).resolve().parents[1]
PACKAGES = ("numpy", "scipy", "pandas", "cooler", "zarr", "torch", "uchrom", "chromdata", "uchrom_maps",
            "uchrom_recon")


def revision(repo: Path = REPO) -> str:
    """The code revision: ``$UCHROM_REVISION`` when set (a job fixes it at its start, so that a repo copy synced
    while the job runs does not change what it records), else the git revision of ``repo`` (``+dirty`` when it has
    uncommitted changes), else its ``REVISION`` file."""
    if os.environ.get("UCHROM_REVISION"):
        return os.environ["UCHROM_REVISION"]
    try:
        out = subprocess.run(["git", "-C", str(repo), "describe", "--always", "--dirty=+dirty", "--abbrev=12"],
                             capture_output=True, text=True, timeout=20)
        if out.returncode == 0 and out.stdout.strip():
            return out.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        pass
    f = repo / "REVISION"
    return f.read_text().strip() if f.exists() else "unknown"


def _cpu() -> str:
    try:
        if platform.system() == "Darwin":
            return subprocess.run(["sysctl", "-n", "machdep.cpu.brand_string"], capture_output=True, text=True,
                                  timeout=5).stdout.strip()
        for line in Path("/proc/cpuinfo").read_text().splitlines():
            if line.startswith("model name"):
                return line.split(":", 1)[1].strip()
    except (OSError, subprocess.SubprocessError):
        pass
    return platform.processor() or "unknown"


def _versions() -> Dict[str, str]:
    import importlib

    out = {"python": platform.python_version()}
    for name in PACKAGES:
        try:
            mod = importlib.import_module(name)
        except Exception:  # noqa: BLE001 - absent or broken: not recorded
            continue
        out[name] = str(getattr(mod, "__version__", "?"))
    return out


def provenance(*, script: Optional[str] = None, datasets: Sequence[str] = (), params: Optional[dict] = None,
               **extra: Any) -> Dict[str, Any]:
    """Where and how a result was produced: revision, date, host, CPU, threads, Slurm job, load, versions,
    script, datasets, parameters (and anything in ``extra``)."""
    try:
        load = os.getloadavg()[0]
    except OSError:
        load = None
    return {
        "revision": revision(),
        "date": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"),
        "host": socket.gethostname(),
        "cpu": _cpu(),
        "cpus": int(os.environ.get("SLURM_CPUS_PER_TASK") or os.cpu_count() or 0),
        "slurm_job": os.environ.get("SLURM_JOB_ID"),
        "load_avg_1min": load,
        "versions": _versions(),
        "script": None if script is None else str(Path(script).resolve().relative_to(REPO))
        if str(Path(script).resolve()).startswith(str(REPO)) else str(script),
        "datasets": list(datasets),
        "params": params or {},
        **extra,
    }


def _plain(x):
    """JSON-ready: numpy scalars / arrays, paths, NaN as null."""
    try:
        import numpy as np

        if isinstance(x, np.generic):
            x = x.item()
        elif isinstance(x, np.ndarray):
            return [_plain(v) for v in x.tolist()]
    except ImportError:
        pass
    if isinstance(x, float) and not math.isfinite(x):
        return None
    if isinstance(x, dict):
        return {str(k): _plain(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_plain(v) for v in x]
    if isinstance(x, Path):
        return str(x)
    return x


def save(path, results: Any, *, script: Optional[str] = None, datasets: Sequence[str] = (),
         params: Optional[dict] = None, **extra: Any) -> Path:
    """Write ``{"results": results, "provenance": provenance(...)}`` to ``path`` (JSON)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    doc = {"results": _plain(results),
           "provenance": _plain(provenance(script=script, datasets=datasets, params=params, **extra))}
    path.write_text(json.dumps(doc, indent=1, sort_keys=False) + "\n")
    return path


def load(path) -> Dict[str, Any]:
    """A results file: ``{"results", "provenance"}`` (a bare JSON written before this module: ``provenance`` None)."""
    doc = json.loads(Path(path).read_text())
    if isinstance(doc, dict) and "results" in doc and "provenance" in doc:
        return doc
    return {"results": doc, "provenance": None}


def _walk(a, b, prefix: str, rtol: float, atol: float, out: List[str]) -> None:
    if isinstance(a, dict) and isinstance(b, dict):
        for k in sorted(set(a) | set(b)):
            if k not in a or k not in b:
                out.append(f"{prefix}{k}: only in {'new' if k not in a else 'old'}")
            else:
                _walk(a[k], b[k], f"{prefix}{k}.", rtol, atol, out)
    elif isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            out.append(f"{prefix[:-1]}: length {len(a)} -> {len(b)}")
        for k, (u, v) in enumerate(zip(a, b)):
            _walk(u, v, f"{prefix}{k}.", rtol, atol, out)
    elif isinstance(a, (int, float)) and isinstance(b, (int, float)) and not isinstance(a, bool):
        if not math.isclose(a, b, rel_tol=rtol, abs_tol=atol):
            out.append(f"{prefix[:-1]}: {a:g} -> {b:g}")
    elif a != b:
        out.append(f"{prefix[:-1]}: {a!r} -> {b!r}")


def compare(old, new, *, rtol: float = 0.0, atol: float = 0.0, keys: Optional[Iterable[str]] = None,
            ignore: Iterable[str] = ("seconds", "time", "rss", "load", "date")) -> List[str]:
    """How the results of ``new`` differ from ``old`` (paths or loaded documents): one line per number outside
    ``rtol`` / ``atol``, per changed value, per key present in one only.  Timing-like keys (``ignore``: any key
    containing one of these words) are left out — compare speeds with care, on the same machine.  ``keys``:
    only these top-level result keys."""
    a = old if isinstance(old, dict) and "results" in old else load(old)
    b = new if isinstance(new, dict) and "results" in new else load(new)
    ra, rb = a["results"], b["results"]
    if keys is not None and isinstance(ra, dict) and isinstance(rb, dict):
        ra = {k: ra.get(k) for k in keys}
        rb = {k: rb.get(k) for k in keys}
    out: List[str] = []
    _walk(ra, rb, "", rtol, atol, out)
    words = tuple(w.lower() for w in ignore)
    return [line for line in out if not any(w in line.split(":", 1)[0].lower() for w in words)]


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="Compare two benchmark result files")
    ap.add_argument("old")
    ap.add_argument("new")
    ap.add_argument("--rtol", type=float, default=0.0)
    a = ap.parse_args()
    diffs = compare(a.old, a.new, rtol=a.rtol)
    print("\n".join(diffs) if diffs else "no differences")
