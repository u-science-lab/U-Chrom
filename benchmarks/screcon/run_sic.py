"""Si-C (Meng et al. 2021, Nat Commun 12:4369) on an arbitrary contact table.

Uses the precompiled x86-64 binaries of github.com/TheMengLab/Si-C HEAD 2a4d445
(``modeling/``; the C sources cannot be recompiled: they include files that are not in
the repository).  ``get3Dstructure.sh`` is replaced step by step:

1. **contact preparation** (``contact/1kb_prepare/do.sh``) is re-done in Python, because
   the script relies on the MySQL ``replace`` utility to strip ``chr`` and map ``X`` to
   the last chromosome number.  Chromosomes are numbered 1..n in natural order
   (chr1..chr19, chrX = 20 for mouse); per chromosome (pair) the positions go to
   ``<i>_<j>.dat`` exactly as the awk lines of ``do.sh`` write them, then the shipped
   ``gettargetcontact.o`` keeps contacts with another contact within 2 Mb in both anchors
   (Si-C's isolated-contact filter, unchanged);
2. ``contact/target_bk/doall.sh`` + ``contactall/do.sh`` (binning at res x 2^k < 2 Mb,
   bead assignment, merging) - run as shipped, with a chromosome length file
   (``i length``; lengths = the assembly's, never shorter than the largest position);
3. ``MD_simulation/replica/bk/doall.sh <n> <res> <replica>`` - run as shipped, one
   process per replica, ``--jobs`` at a time (the original starts them all with nohup);
4. ``genome.pdb`` -> ``.npz`` (``models_io.read_sic_pdb``): bead k of chromosome i covers
   [k res, (k+1) res) -> 2017 ``pos`` = (k + 1) res; beads without contacts are
   interpolations (``interpolated`` in the npz).

Limits (from the code): at most **20 chromosomes** (``insert_contract_assign.c``:
``chrnum = 20``), so a haploid mouse genome or single chromosomes (e.g. human chr21)
work but a whole human genome does not; resolution in integer kb with
2 x res < 2000 kb (``MD_simulation/.../doall.sh`` starts at the largest res x 2^k below
2 Mb and needs at least one coarser level), so 1 Mb is not possible - use 500 or
250 kb and compare at the truth loci (particles are matched by genomic position).

    python benchmarks/screcon/run_sic.py --sic-dir $SCRATCH/uchrom-nd/sic/modeling \\
        --contacts train.txt.gz --res-kb 100 --assembly mm10 --replicas 10 --jobs 10 \\
        --workdir $L_SCRATCH/sic_cell1 --out RUN/sic.npz
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import stat
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from contacts import chrom_sizes_for, read_contacts  # noqa: E402
from models_io import read_sic_pdb  # noqa: E402

MAX_CHROMS = 20


def check_res(res_kb: int) -> None:
    if int(res_kb) != res_kb or res_kb <= 0:
        raise ValueError("Si-C resolution must be a positive integer number of kb")
    if 2 * res_kb >= 2000:
        raise ValueError(f"Si-C cannot model at {res_kb} kb: its MD schedule needs 2 x res < 2000 kb "
                         "(use 500 or 250 kb and compare by genomic position)")


def prepare_1kb(contacts, chroms: list[str], d: Path, jobs: int = 8) -> dict:
    """Python replacement of contact/1kb_prepare/do.sh (see module docstring)."""
    num = {c: i + 1 for i, c in enumerate(chroms)}
    ia = np.array([num[c] for c in contacts.chrom_a.astype(str)])
    ib = np.array([num[c] for c in contacts.chrom_b.astype(str)])
    pa, pb = contacts.pos_a, contacts.pos_b
    n = len(chroms)
    tasks = []
    for i in range(1, n + 1):
        sel = (ia == i) & (ib == i)
        np.savetxt(d / f"{i}_{i}.dat", np.stack([pa[sel], pb[sel]], 1), fmt="%d")
        tasks.append((f"{i}_{i}.dat", f"intra_{i}_1kb.dat"))
    for i in range(1, n + 1):
        for j in range(i + 1, n + 1):
            s1 = (ia == i) & (ib == j)
            s2 = (ia == j) & (ib == i)
            rows = np.concatenate([np.stack([pa[s1], pb[s1]], 1), np.stack([pb[s2], pa[s2]], 1)])
            np.savetxt(d / f"{i}_{j}.dat", rows, fmt="%d")
            tasks.append((f"{i}_{j}.dat", f"inter_{i}_{j}_1kb.dat"))

    def run(t):
        subprocess.run(["./gettargetcontact.o"], input=f"{t[0]}\n{t[1]}\n", text=True, cwd=d,
                       stdout=subprocess.DEVNULL, check=True)
        return sum(1 for _ in open(d / t[1]))

    with ThreadPoolExecutor(jobs) as ex:
        kept = list(ex.map(run, tasks))
    return {"n_input": int(len(contacts)), "n_kept_after_isolation_filter": int(sum(kept))}


def chmod_x(root: Path) -> None:
    for p in root.rglob("*.o"):
        p.chmod(p.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sic-dir", required=True, help="Si-C 'modeling' directory")
    ap.add_argument("--contacts", required=True)
    ap.add_argument("--res-kb", type=int, default=100)
    ap.add_argument("--assembly", default=None, help="mm10 / hg38 chromosome lengths (default: from the data)")
    ap.add_argument("--replicas", type=int, default=10)
    ap.add_argument("--first-replica", type=int, default=1, help="replica ids (= Si-C seeds) start here")
    ap.add_argument("--jobs", type=int, default=0, help="replicas run in parallel (default: all)")
    ap.add_argument("--workdir", type=Path, required=True)
    ap.add_argument("--keep", action="store_true", help="keep the work directory")
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args(argv)
    check_res(args.res_kb)
    src = Path(args.sic_dir)
    c = read_contacts(args.contacts)
    chroms = c.chroms
    if len(chroms) > MAX_CHROMS:
        raise SystemExit(f"Si-C supports at most {MAX_CHROMS} chromosomes (got {len(chroms)})")
    n = len(chroms)
    res = int(args.res_kb)
    W = args.workdir
    if W.exists():
        shutil.rmtree(W)
    (W / "contact" / "1kb_prepare").mkdir(parents=True)
    shutil.copy2(src / "contact/1kb_prepare/gettargetcontact.o", W / "contact/1kb_prepare/")
    shutil.copytree(src / "contact/target_bk", W / "contact/target_bk")
    shutil.copytree(src / "MD_simulation/replica/bk", W / "MD_simulation/replica/bk")
    chmod_x(W)
    t0 = time.time()
    prep = prepare_1kb(c, chroms, W / "contact/1kb_prepare", jobs=max(os.cpu_count() or 1, 1))
    sizes = chrom_sizes_for(c, args.assembly)
    lenfile = W / "chrlenlist.dat"
    lenfile.write_text("".join(f"{i + 1}\t{sizes[ch]}\n" for i, ch in enumerate(chroms)))
    shutil.copytree(W / "contact/target_bk", W / f"contact/{res}kb_target")
    tdir = W / f"contact/{res}kb_target"
    log = open(W / "sic_contact.log", "w")
    subprocess.run(["bash", "doall.sh", str(n), str(res), str(lenfile)], cwd=tdir, stdout=log, stderr=log, check=True)
    subprocess.run(["bash", "do.sh", str(n)], cwd=tdir / "contactall", stdout=log, stderr=log, check=True)
    t1 = time.time()
    rep_root = W / f"MD_simulation/{res}kb_{args.replicas}replica"
    rep_root.mkdir(parents=True)
    ids = list(range(args.first_replica, args.first_replica + args.replicas))

    def run_rep(r):
        d = rep_root / str(r)
        shutil.copytree(W / "MD_simulation/replica/bk", d)
        ts = time.time()
        with open(d / "run.log", "w") as fh:
            p = subprocess.run(["bash", "doall.sh", str(n), str(res), str(r)], cwd=d, stdout=fh, stderr=fh)
        return r, p.returncode, time.time() - ts

    with ThreadPoolExecutor(args.jobs or len(ids)) as ex:
        runs = list(ex.map(run_rep, ids))
    t2 = time.time()
    assign = np.loadtxt(tdir / f"contactall/assignall{res}.dat", dtype=np.int64, ndmin=2)
    interp = assign[:, 2] < 0
    models, key, failed = [], None, []
    for r, rc, _ in runs:
        pdb = rep_root / str(r) / "genome.pdb"
        if rc != 0 or not pdb.exists():
            failed.append(r)
            continue
        ch, pos, X = read_sic_pdb(pdb, chroms, res * 1000)
        k = (tuple(ch), tuple(pos))
        key = key or k
        if k != key:
            raise SystemExit("Si-C replicas have different beads")
        models.append(X)
    if not models:
        raise SystemExit(f"no Si-C replica finished; see {rep_root}/*/run.log")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(args.out, chrom=np.array(key[0]), pos=np.array(key[1], np.int64), coords=np.stack(models),
                        interpolated=interp[: len(key[0])] if len(interp) >= len(key[0]) else np.zeros(len(key[0]), bool))
    meta = {"method": "Si-C 2a4d445 (shipped binaries)", "contacts": str(args.contacts), "res_kb": res,
            "chroms": chroms, "chrom_lengths": sizes, "prepare": prep, "replicas": ids, "failed": failed,
            "n_beads": len(key[0]), "n_interpolated_beads": int(interp.sum()),
            "contact_seconds": t1 - t0, "md_seconds_wall": t2 - t1,
            "md_seconds_per_replica": [t for _, _, t in runs], "slurm_job_id": os.environ.get("SLURM_JOB_ID")}
    Path(str(args.out) + ".json").write_text(json.dumps(meta, indent=1))
    print(json.dumps({k: v for k, v in meta.items() if k not in ("chrom_lengths",)}), flush=True)
    if not args.keep:
        shutil.rmtree(W, ignore_errors=True)


if __name__ == "__main__":
    main()
