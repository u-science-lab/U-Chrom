"""hickit / Dip-C 3-D modelling (Tan et al. 2018, github.com/lh3/hickit) on an arbitrary table.

Uses the prebuilt release binary ``hickit-0.1.1_x64-linux`` (x86-64, dynamically linked
against glibc >= 2.15 and zlib only, so it runs on CentOS 7)::

    curl -L https://github.com/lh3/hickit/releases/download/v0.1.1/hickit-0.1.1_x64-linux.tar.bz2 | tar -jxf -

hickit is built for *diploid, phased* data: the Dip-C command
``-i impute.pairs -Sr1m -c1 -r10m -c5 -b4m -b1m -b200k -D5 -b50k -D5 -b20k -O out.3dg``
separates homologs (``-S``) using imputed phases.  For haploid input (Stevens 2017
haploid mESC; the simulated haploid truths) the phasing steps are dropped and ploidy is
set to 1 (``-P1`` before ``-i``, so hickit does not split chrX/chrY as male
haplotypes); everything else is the Dip-C schedule, truncated at ``--res``:

    hickit -s SEED -P1 -i in.pairs -r1m -c1 -r10m -c5 -b4m -b1m -b200k -D5 -b<res> -O out.3dg

(the ``-D5`` filters - drop contacts > 5 units apart in the previous structure - are
applied before every stage finer than 200 kb, as in Dip-C).  One model per seed.

Diploid (``--diploid``, phased input: hickit ``.pairs`` with ``phase0`` / ``phase1`` or Dip-C
``.con``): the Dip-C pipeline of the hickit README — phases imputed from the 2-D neighbourhood
(``-u``), homologs split at imputed probability >= 0.75 (``-S``), then the same schedule::

    hickit -s SEED -i in.pairs -u -S -r1m -c1 -r10m -c5 -b4m -b1m -b200k -D5 -b<res> -O out.3dg

(ploidy hickit's default: two copies, male X / Y single when a Y chromosome is present).  Copy
chains ``chr1a`` / ``chr1b`` are renamed ``chr1(0)`` / ``chr1(1)`` (``diploid.py``); the
imputed phase probabilities (``hickit -i in.pairs -u -o``) are mapped back to the input rows
and saved as ``phase_probs`` (NaN for rows hickit dropped).

Limitations: input strands are unknown in GEO tables (``.``), which hickit treats as
"same strand" when filtering close legs (< 1 kb apart; irrelevant at >= 20 kb);
hickit merges consecutive beads without contacts (variable bead length; ``-M`` would
disable it) - the 3dg is resampled onto the regular ``--res`` grid (a grid bin takes the
coordinates of the bead covering its midpoint, ``models_io.resample_3dg``).

    python benchmarks/screcon/run_hickit.py --hickit $BASE/hickit-0.1.1_x64-linux/hickit \\
        --contacts train.txt.gz --res 100000 --assembly mm10 --n-models 10 --out RUN/hickit.npz
"""

from __future__ import annotations

import argparse
import json
import os
import resource
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from contacts import chrom_sizes_for, read_contacts, write_pairs  # noqa: E402
from models_io import read_3dg, resample_3dg  # noqa: E402


def fmt_bp(x: int) -> str:
    if x % 1_000_000 == 0:
        return f"{x // 1_000_000}m"
    if x % 1000 == 0:
        return f"{x // 1000}k"
    return str(x)


def hickit_args(res: int) -> list[str]:
    """Dip-C schedule (4m, 1m, 200k, 50k, 20k) truncated at ``res``, ``-D5`` before stages < 200 kb."""
    stages = [s for s in (4_000_000, 1_000_000, 200_000, 50_000, 20_000) if s > res] + [res]
    out = ["-r1m", "-c1", "-r10m", "-c5"]
    for s in stages:
        if s < 200_000:
            out.append("-D5")
        out.append(f"-b{fmt_bp(s)}")
    return out


def _spans(c):
    chroms = c.chroms
    lo = [int(min(c.pos_a[c.chrom_a == g].min(initial=2 ** 62), c.pos_b[c.chrom_b == g].min(initial=2 ** 62))) for g in chroms]
    hi = [int(max(c.pos_a[c.chrom_a == g].max(initial=0), c.pos_b[c.chrom_b == g].max(initial=0))) for g in chroms]
    return chroms, lo, hi


def _final_beads(log: Path):
    """Bead count of the last stage (``hk_bmap_merge_beads A => B``: B after merging empty beads)."""
    n = None
    if log.exists():
        for line in log.read_text().splitlines():
            if "hk_bmap_merge_beads" in line and "=>" in line:
                n = int(line.rsplit("=>", 1)[1].split()[0])
    return n


def map_imputed(c, path) -> np.ndarray:
    """hickit's imputed pairs (sorted, upper triangle, some rows dropped) -> (len(c), 4)
    phase probabilities in the orientation of the input rows; NaN where hickit dropped a row."""
    from diploid import read_phased
    h = read_phased(path)
    if h.phase_prob is None:
        return np.full((len(c), 4), np.nan)
    table = {}
    for k in range(len(h)):
        p = h.phase_prob[k]
        table[(h.chrom_a[k], h.pos_a[k], h.chrom_b[k], h.pos_b[k])] = p
        table.setdefault((h.chrom_b[k], h.pos_b[k], h.chrom_a[k], h.pos_a[k]), p[[0, 2, 1, 3]])
    out = np.full((len(c), 4), np.nan)
    for k in range(len(c)):
        v = table.get((c.chrom_a[k], c.pos_a[k], c.chrom_b[k], c.pos_b[k]))
        if v is not None:
            out[k] = v
    return out


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--hickit", required=True)
    ap.add_argument("--contacts", required=True)
    ap.add_argument("--res", type=int, default=100_000)
    ap.add_argument("--assembly", default=None)
    ap.add_argument("--n-models", type=int, default=10)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--jobs", type=int, default=0)
    ap.add_argument("--diploid", action="store_true", help="phased input: Dip-C imputation + homolog split")
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args(argv)
    stem = args.out.with_suffix("")
    stem.parent.mkdir(parents=True, exist_ok=True)
    pairs = Path(f"{stem}.pairs.gz")
    sched = hickit_args(args.res)
    extra = {}
    if args.diploid:
        from diploid import read_phased, write_phased
        c = read_phased(args.contacts)
        sizes = chrom_sizes_for(c, args.assembly)
        write_phased(pairs, c, sizes)
        spans = {g: (lo, hi) for g, lo, hi in zip(*_spans(c))}
        imp = Path(f"{stem}.impute.pairs.gz")
        with open(str(imp)[:-3], "w") as fh:
            subprocess.run([args.hickit, "-i", str(pairs), "-u", "-o", "-"], stdout=fh, check=True, stderr=subprocess.DEVNULL)
        extra["phase_probs"] = map_imputed(c, str(imp)[:-3])
        os.remove(str(imp)[:-3])
        head = ["-u", "-S"]
        ploidy = {g: 2 for g in c.chroms}
        if any(g.upper().endswith("Y") for g in c.chroms):           # hickit: male when chrY is present
            ploidy.update({g: 1 for g in c.chroms if g.upper().endswith(("X", "Y"))})
        from diploid import copy_name
        spans = {copy_name(g, h, ploidy[g]): v for g, v in spans.items() for h in range(ploidy[g])}
    else:
        c = read_contacts(args.contacts)
        sizes = chrom_sizes_for(c, args.assembly)
        write_pairs(pairs, c, sizes)
        spans = {g: (lo, hi) for g, lo, hi in zip(*_spans(c))}
        head = []
        ploidy = None

    def run(k):
        seed = args.seed + k
        out3 = Path(f"{stem}.m{k}.3dg")
        p_opt = [] if args.diploid else ["-P1"]
        cmd = [args.hickit, "-s", str(seed), *p_opt, "-i", str(pairs), *head, *sched, "-O", str(out3)]
        ts = time.time()
        p = subprocess.run(cmd, capture_output=True, text=True)
        Path(f"{stem}.m{k}.log").write_text(" ".join(cmd) + "\n" + p.stderr)
        return k, p.returncode, time.time() - ts, out3, cmd

    t0 = time.time()
    with ThreadPoolExecutor(args.jobs or args.n_models) as ex:
        runs = list(ex.map(run, range(args.n_models)))
    models, key, failed = [], None, []
    for k, rc, _, out3, _ in runs:
        if rc != 0 or not out3.exists():
            failed.append(k)
            continue
        ch, st, xyz = read_3dg(out3)
        if args.diploid:
            from diploid import hickit_copy
            ch = np.array([hickit_copy(x, ploidy) for x in ch])
        ch, pos, X = resample_3dg(ch, st, xyz, args.res, spans)
        kk = (tuple(ch), tuple(pos))
        if key is None:
            key = kk
        if kk != key:                                  # different spans: keep the common grid
            common = sorted(set(zip(*key)) & set(zip(*kk)))
            key = (tuple(x[0] for x in common), tuple(x[1] for x in common))
        models.append((ch, pos, X))
    if not models:
        raise SystemExit(f"no hickit model finished; see {stem}.m*.log")
    idx_key = {k: i for i, k in enumerate(zip(*key))}
    stack = []
    for ch, pos, X in models:
        m = {k: i for i, k in enumerate(zip(ch.tolist(), pos.tolist()))}
        stack.append(X[[m[k] for k in zip(*key)]])
    np.savez_compressed(args.out, chrom=np.array(key[0]), pos=np.array(key[1], np.int64), coords=np.stack(stack),
                        **extra)
    meta = {"method": "hickit 0.1.1 (diploid, -u -S)" if args.diploid else "hickit 0.1.1 (haploid, -P1)", "contacts": str(args.contacts), "res": args.res,
            "cmd": runs[0][4][1:], "n_models": len(stack), "failed": failed, "wall_seconds": time.time() - t0,
            "seconds_per_model": [r[2] for r in runs], "n_particles": len(idx_key),
            "n_beads_hickit": [_final_beads(Path(f"{stem}.m{k}.log")) for k, *_ in runs],
            "peak_rss_mb_largest_child": resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss
            / (1e6 if sys.platform == "darwin" else 1e3),
            "slurm_job_id": os.environ.get("SLURM_JOB_ID")}
    Path(str(args.out) + ".json").write_text(json.dumps(meta, indent=1))
    print(json.dumps(meta), flush=True)


if __name__ == "__main__":
    main()
