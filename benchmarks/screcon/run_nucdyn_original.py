"""Original NucDynamics (tjs23/nuc_dynamics ``master``, 2017) on an arbitrary contact table.

The logic of ``benchmarks/fig3/a_nucdyn_engine_original_run.py``, generalised: the table
(GEO or .pairs) is converted to the 15-column NCC format the 2017 code reads (``+``
strands, so the contact position is the given position; every contact unambiguous and
active), ``nuc_dynamics.py`` runs in its own parallel mode (one process per model) with
the schedule of ``run_nucdyn.schedule`` (``-s``, Mb), and its **N3D** output (which
names chromosomes explicitly; the PDB export encodes them only as chain letters, whose
order shifts if a chromosome loses all particles) is converted to the common ``.npz``.

Run with the original's environment (venv-orig: numpy < 2, cython < 3)::

    $ORIG_PY benchmarks/screcon/run_nucdyn_original.py --nd-dir ND_MASTER --contacts train.txt.gz \\
        --res 100000 --models 10 --cpu 10 --seed 1 --out RUN/nucdyn_orig.npz
"""

from __future__ import annotations

import argparse
import json
import os
import resource
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from contacts import read_contacts, sort_chroms  # noqa: E402
from run_nucdyn import schedule  # noqa: E402


def to_ncc(contacts, dst: Path) -> int:
    with open(dst, "w") as fo:
        for n, (ca, pa, cb, pb) in enumerate(zip(contacts.chrom_a, contacts.pos_a, contacts.chrom_b, contacts.pos_b), 1):
            fo.write(f"{ca} {pa} {pa} {pa} {pa} + {cb} {pb} {pb} {pb} {pb} + {n} {n} 0\n")
    return len(contacts)


def read_n3d(path: Path):
    """N3D (``chrom n_particles n_models`` then ``pos x0 y0 z0 x1 ...``) -> chrom, pos, coords (M, N, 3)."""
    blocks = {}
    with open(path) as fh:
        lines = fh.read().splitlines()
    k = 0
    while k < len(lines):
        head = lines[k].split()
        if not head:
            k += 1
            continue
        chrom, n, m = head[0], int(head[1]), int(head[2])
        rows = [lines[k + 1 + i].split() for i in range(n)]
        pos = np.array([int(r[0]) for r in rows], np.int64)
        xyz = np.array([[float(v) for v in r[1:]] for r in rows]).reshape(n, m, 3).transpose(1, 0, 2)
        blocks[chrom] = (pos, xyz)
        k += 1 + n
    chroms = sort_chroms(blocks)
    chrom = np.concatenate([np.full(len(blocks[c][0]), c, dtype=object) for c in chroms]).astype(str)
    pos = np.concatenate([blocks[c][0] for c in chroms])
    X = np.concatenate([blocks[c][1] for c in chroms], axis=1)
    return chrom, pos, X


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--nd-dir", required=True)
    ap.add_argument("--contacts", required=True)
    ap.add_argument("--res", type=float, default=1e5)
    ap.add_argument("--sizes", help="explicit schedule, Mb, comma separated (overrides --res)")
    ap.add_argument("--models", type=int, default=10)
    ap.add_argument("--cpu", type=int, default=10)
    ap.add_argument("--temps", type=int, default=500)
    ap.add_argument("--dyns", type=int, default=100)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args(argv)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    stem = args.out.with_suffix("")
    ncc = Path(f"{stem}.ncc")
    c = read_contacts(args.contacts)
    n = to_ncc(c, ncc)
    sizes = [float(x) for x in args.sizes.split(",")] if args.sizes else [s / 1e6 for s in schedule(args.res)]
    n3d = Path(f"{stem}.n3d")
    cmd = [sys.executable, str(Path(args.nd_dir) / "nuc_dynamics.py"), str(ncc), "-o", str(n3d), "-f", "n3d",
           "-m", str(args.models), "-cpu", str(args.cpu), "-temps", str(args.temps), "-dyns", str(args.dyns),
           "-ran", str(args.seed), "-s", *[f"{s:g}" for s in sizes]]
    t0 = time.perf_counter()
    r0 = resource.getrusage(resource.RUSAGE_CHILDREN)
    p = subprocess.run(cmd, capture_output=True, text=True, cwd=args.nd_dir)
    wall = time.perf_counter() - t0
    r1 = resource.getrusage(resource.RUSAGE_CHILDREN)
    Path(f"{stem}.log").write_text(p.stdout + p.stderr)
    if p.returncode != 0:
        raise SystemExit(p.stderr[-3000:])
    chrom, pos, X = read_n3d(n3d)
    np.savez_compressed(args.out, chrom=chrom, pos=pos, coords=X)
    ncc.unlink(missing_ok=True)
    meta = {"method": "nuc_dynamics master (Cython)", "contacts": str(args.contacts), "n_contacts": n,
            "cmd": cmd[1:], "particle_sizes_mb": sizes, "n_models": int(len(X)), "wall_seconds": wall,
            "cpu_seconds_children": (r1.ru_utime - r0.ru_utime) + (r1.ru_stime - r0.ru_stime),
            "peak_rss_mb_largest_child": r1.ru_maxrss / (1e6 if sys.platform == "darwin" else 1e3),
            "slurm_job_id": os.environ.get("SLURM_JOB_ID")}
    Path(str(args.out) + ".json").write_text(json.dumps(meta, indent=1))
    print(json.dumps(meta))


if __name__ == "__main__":
    main()
