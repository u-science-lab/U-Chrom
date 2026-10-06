"""Run the original NucDynamics (``master``) on a Stevens et al. 2017 GEO contact table.

Converts the GEO table (``chr_A pos_A chr_B pos_B``) to the 15-column NCC
format the 2017 code reads (``+`` strands, so the contact position is the
given position; every contact unambiguous and active), runs
``nuc_dynamics.py`` with the given options in its own parallel mode (one
process per model), converts the PDB it writes to the ``.npz`` model format
of ``a_nucdyn_engine_run.py`` and records wall / CPU time.

Run with the original's environment::

    $ORIG_PY benchmarks/fig3/a_nucdyn_engine_original_run.py --nd-dir ND_MASTER --cell 1 \\
        --models 10 --cpu 10 --temps 50 --out RUN_DIR
"""

from __future__ import annotations

import argparse
import gzip
import json
import os
import resource
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
GEO_DIR = ROOT / "example-data" / "stevens2017_mesc"
GSM = {1: "GSM2219497", 2: "GSM2219498", 3: "GSM2219499", 4: "GSM2219500",
       5: "GSM2219501", 6: "GSM2219502", 7: "GSM2219503", 8: "GSM2219504"}
CHAINS = {chr(ord("a") + i): f"chr{i + 1}" for i in range(19)} | {"t": "chrX"}


def to_ncc(src: Path, dst: Path) -> int:
    n = 0
    with gzip.open(src, "rt") as fi, open(dst, "w") as fo:
        for line in fi:
            if line.startswith("#"):
                continue
            ca, pa, cb, pb = line.split()[:4]
            n += 1
            fo.write(f"{ca} {pa} {pa} {pa} {pa} + {cb} {pb} {pb} {pb} {pb} + {n} {n} 0\n")
    return n


def read_pdb(path: Path):
    models, rows = [], []
    with open(path) as fh:
        for line in fh:
            if line.startswith("MODEL"):
                rows = []
            elif line.startswith("HETATM"):
                rows.append((CHAINS.get(line[21], line[21]), int(line.split()[-1]),
                             float(line[30:38]), float(line[38:46]), float(line[46:54])))
            elif line.startswith("ENDMDL"):
                models.append(rows)
    chrom = np.array([r[0] for r in models[0]])
    pos = np.array([r[1] for r in models[0]], np.int64)
    coords = np.array([[r[2:] for r in m] for m in models])
    return chrom, pos, coords


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--nd-dir", required=True)
    ap.add_argument("--cell", type=int, required=True)
    ap.add_argument("--models", type=int, default=10)
    ap.add_argument("--cpu", type=int, default=10)
    ap.add_argument("--temps", type=int, default=500)
    ap.add_argument("--dyns", type=int, default=100)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    ncc = args.out / f"cell{args.cell}.ncc"
    n = to_ncc(GEO_DIR / f"{GSM[args.cell]}_Cell_{args.cell}_contact_pairs.txt.gz", ncc)
    stem = args.out / f"cell{args.cell}_orig"
    cmd = [sys.executable, str(Path(args.nd_dir) / "nuc_dynamics.py"), str(ncc), "-o", f"{stem}.pdb", "-f", "pdb",
           "-m", str(args.models), "-cpu", str(args.cpu), "-temps", str(args.temps), "-dyns", str(args.dyns),
           "-ran", str(args.seed)]
    load0 = os.getloadavg()
    t0 = time.perf_counter()
    r0 = resource.getrusage(resource.RUSAGE_CHILDREN)
    p = subprocess.run(cmd, capture_output=True, text=True, cwd=args.nd_dir)
    wall = time.perf_counter() - t0
    r1 = resource.getrusage(resource.RUSAGE_CHILDREN)
    (args.out / f"cell{args.cell}_orig.log").write_text(p.stdout + p.stderr)
    if p.returncode != 0:
        raise SystemExit(p.stderr[-3000:])
    pdb = Path(f"{stem}.pdb")
    chrom, pos, coords = read_pdb(pdb)
    np.savez_compressed(args.out / f"cell{args.cell}.npz", chrom=chrom, pos=pos, coords=coords)
    peak = r1.ru_maxrss / (1e6 if sys.platform == "darwin" else 1e3)
    meta = {"cell": args.cell, "engine": "nuc_dynamics master (Cython)", "n_contacts_input": n, "cmd": cmd[1:],
            "n_models": int(len(coords)), "wall_seconds": wall,
            "cpu_seconds_children": (r1.ru_utime - r0.ru_utime) + (r1.ru_stime - r0.ru_stime),
            "peak_rss_mb_largest_child": peak, "load_avg_before": load0, "load_avg_after": os.getloadavg()}
    (args.out / f"cell{args.cell}.json").write_text(json.dumps(meta, indent=1))
    print(json.dumps(meta))


if __name__ == "__main__":
    main()
