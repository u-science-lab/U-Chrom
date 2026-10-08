"""Inputs of the scA/B validation jobs (run once, in a job): genome FASTAs, stores, CpG tracks; a smoke run.

    python benchmarks/sc_structures/scab_prep.py [--workers 8] [--smoke-cells 300]

1. ``ds.fetch`` of the registered whole-genome FASTAs (``mm10_genome``, ``hg19_genome``, ``hg38_genome``, md5
   checked) and of ``hg19_chr21`` / ``hg38_to_hg19_chain`` / ``rao2014_gm12878_chr21`` (already there when copied
   from another data directory).
2. ``ds.load`` of ``kim2020_scihic``, ``tan2018_gm12878``, ``wu2025_scmicroc`` (built into the data directory on
   first use).
3. The CpG frequency tracks of every genome and bin size the jobs use, computed in parallel processes into
   ``$SCAB_CACHE`` (:func:`scab_common.cpg_track`).
4. Smoke run: ``single_cell_compartments`` on the first ``--smoke-cells`` cells of the dscHi-C atlas store (over
   HTTP) and of each local store; prints shapes, NaN fractions and the stages.
"""

from __future__ import annotations

import argparse
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from scab_common import cpg_track, load_average  # noqa: E402

AUTOSOMES_MM = [f"chr{k}" for k in range(1, 20)]


def _sizes():
    from uchrom.datasets._load_schic import HG19, HG38

    return {"hg19": HG19, "hg38": HG38}


def _track(job):
    genome, sizes, res = job
    t0 = time.perf_counter()
    t = cpg_track(genome, sizes, res, Path("cache"))
    return genome, res, len(t), time.perf_counter() - t0


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--smoke-cells", type=int, default=300)
    a = ap.parse_args()
    import uchrom.datasets as ds
    from chromdata.embedded import open_all

    from uchrom.strc.comp.single_cell import single_cell_compartments

    print(f"load: {load_average()}", flush=True)
    for name in ("mm10_genome", "hg19_genome", "hg38_genome", "hg19_chr21", "hg38_to_hg19_chain",
                 "rao2014_gm12878_chr21"):
        t0 = time.perf_counter()
        print(f"{name}: {ds.fetch(name)} ({time.perf_counter() - t0:.0f} s)", flush=True)
    stores = {}
    for name in ("kim2020_scihic", "tan2018_gm12878", "wu2025_scmicroc"):
        t0 = time.perf_counter()
        stores[name] = ds.load(name)
        print(f"{name}: {len(stores[name].cells)} cells ({time.perf_counter() - t0:.0f} s)", flush=True)

    atlas = ds.load("dschic_aging_cortex")
    mm10 = open_all(atlas._links_from())["per_cell"].chromsizes()
    jobs = [("mm10", mm10, 1_000_000)]
    hg = _sizes()
    jobs += [("hg19", hg["hg19"], r) for r in (250_000, 500_000, 1_000_000, 2_500_000)]
    jobs += [("hg38", hg["hg38"], r) for r in (250_000, 500_000, 1_000_000)]
    with ProcessPoolExecutor(a.workers) as ex:
        for genome, res, n, sec in ex.map(_track, jobs):
            print(f"CpG {genome} {res:,} bp: {n:,} bins ({sec:.0f} s)", flush=True)

    # smoke runs
    track = cpg_track("mm10", mm10, 1_000_000, Path("cache"))
    ids = list(atlas.cells.index[: a.smoke_cells])
    t0 = time.perf_counter()
    f = single_cell_compartments(atlas, track=track, cells=ids, chrom=AUTOSOMES_MM)
    print(f"atlas smoke: {f.shape}, NaN {f.isna().to_numpy().mean():.3f}, {time.perf_counter() - t0:.1f} s, "
          f"{atlas.results.record('compartments.scab').inputs['seconds']}", flush=True)
    for name, genome, res in (("kim2020_scihic", "hg19", 500_000), ("tan2018_gm12878", "hg19", 1_000_000),
                              ("wu2025_scmicroc", "hg38", 1_000_000)):
        cd = stores[name]
        t = cpg_track(genome, hg[genome], res, Path("cache"))
        t0 = time.perf_counter()
        f = single_cell_compartments(cd, track=t, cells=list(cd.cells.index[: a.smoke_cells]), resolution=res)
        print(f"{name} smoke: {f.shape}, NaN {f.isna().to_numpy().mean():.3f}, {time.perf_counter() - t0:.1f} s",
              flush=True)
    print(f"load: {load_average()}")


if __name__ == "__main__":
    main()
