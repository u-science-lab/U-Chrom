"""Structures of each spatial Hi-C section's pooled map (all its spots), the reference set the per-spot local scores
are measured on: insulation boundaries (250-kb window) and HiCCUPS loops at 25 kb, cis-eigenvector compartments at
100 kb; and the windows of those boundaries, of domain interiors (controls) and of the loops (``uchrom.io.boundary_windows`` / ``loop_windows``) that the
second pass over the pairs counts per spot (``spatial_pairs_windows.py`` of the recipe).

    python benchmarks/spatial_variable/bulk_calls.py --stats $OAK/uchrom/spatial_3dgenome --out $OUT/bulk_calls \
        --samples mouse_brain_r1 mouse_brain_r2 --name mouse_brain

The pooled map is the sum of the samples' ``<sample>.bulk.mcool`` 25-kb levels (MAPQ >= 30, in-tissue spots; no
balancing weights) — both sections of a tissue, so that each structure is scored in both — ICE-balanced into the
output folder first (``uchrom.fea.rebin_map``).
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

RES = 25_000
BOUNDARY_WINDOW = 250_000          # the insulation diamond of the calls and the flanks of the per-spot counts
COMP_RES = 100_000


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, flush=True)


def _empty_cd(assembly):
    from chromdata import ChromData

    cd = ChromData(coords=np.zeros((0, 3)), spots=pd.DataFrame({"chrom": pd.Series([], dtype=str), "start": [],
                                                                "end": [], "trace_id": []}))
    cd.uns["genome_assembly"] = assembly
    return cd


def call_sample(samples, sample: str, stats_root: Path, out: Path, workers: int) -> dict:
    """Calls on the pooled map of ``samples`` (their 25-kb levels summed when several: one reference set of
    structures for all of them, so that a structure can be compared between sections), files named ``sample``."""
    import cooler

    from uchrom.fea import rebin_map
    from uchrom.io import boundary_windows, loop_windows
    from uchrom.strc.comp import call_compartments_eig
    from uchrom.strc.loop import call_loops_hiccups
    from uchrom.strc.tad import InsulationParams, call_tads_insulation

    out.mkdir(parents=True, exist_ok=True)
    t = time.time()
    levels = [f"{stats_root / s / f'{s}.bulk.mcool'}::/resolutions/{RES}" for s in samples]
    if len(levels) == 1:
        source = levels[0]
    else:
        source = str(out / f"{sample}.merged_25kb.cool")
        if not Path(source).exists():
            cooler.merge_coolers(source, levels, mergebuf=20_000_000)
    c25 = out / f"{sample}.bulk_25kb.balanced.cool"
    c100 = out / f"{sample}.bulk_100kb.balanced.cool"
    if not c25.exists():
        rebin_map(source, resolution=RES, out=c25)
    if not c100.exists():
        rebin_map(source, resolution=COMP_RES, out=c100)
    log(f"{sample}: pooled {samples}, balanced maps in {time.time() - t:.0f} s")

    asm = cooler.Cooler(str(c25)).info.get("genome-assembly")
    cd = _empty_cd(asm)
    cd.link_cool(c25, key="bulk")
    cd.link_cool(c100, key="bulk_100kb")
    t = time.time()
    call_tads_insulation(cd, contacts="bulk", params=InsulationParams(window_bp=BOUNDARY_WINDOW))
    bounds = cd.results["tads.insulation.boundaries"]
    log(f"{sample}: {len(bounds)} boundaries in {time.time() - t:.0f} s")
    t = time.time()
    loops = call_loops_hiccups(cd, contacts="bulk")
    log(f"{sample}: {len(loops)} loops in {time.time() - t:.0f} s")
    t = time.time()
    comp = call_compartments_eig(cd, contacts="bulk_100kb")
    log(f"{sample}: compartments in {time.time() - t:.0f} s")
    b = pd.DataFrame({"chrom": bounds["chrom"].astype(str), "pos": bounds["start"].astype(np.int64)})
    # controls: the midpoints of the domains at least two windows long (no boundary within a window), the same
    # three windows -- a spot's own cross / within ratio without a boundary (its contact-decay shape)
    mid = []
    for chrom, g in b.sort_values(["chrom", "pos"]).groupby("chrom", sort=False):
        p = g["pos"].to_numpy()
        gap = np.diff(p)
        ok = gap >= 2 * BOUNDARY_WINDOW + 2 * RES
        mid.append(pd.DataFrame({"chrom": chrom, "pos": (p[:-1][ok] + gap[ok] // 2) // RES * RES}))
    interior = pd.concat(mid, ignore_index=True) if mid else b.iloc[:0]
    lp = pd.DataFrame({"chrom1": loops["chrom1"].astype(str), "start1": loops["start1"].astype(np.int64),
                       "start2": loops["start2"].astype(np.int64)})
    w = pd.concat([boundary_windows(b, window=BOUNDARY_WINDOW, resolution=RES).assign(kind="boundary"),
                   boundary_windows(interior, window=BOUNDARY_WINDOW, resolution=RES).assign(kind="interior"),
                   loop_windows(lp, resolution=RES).assign(kind="loop")], ignore_index=True)
    interior.to_parquet(out / f"{sample}.interior.parquet")
    bounds.to_parquet(out / f"{sample}.boundaries.parquet")
    loops.to_parquet(out / f"{sample}.loops.parquet")
    pd.DataFrame(comp).to_parquet(out / f"{sample}.compartments.parquet")
    w.to_parquet(out / f"{sample}.windows.parquet")
    return {"n_boundaries": int(len(bounds)), "n_interior": int(len(interior)), "n_loops": int(len(loops)),
            "n_windows": int(len(w)),
            "assembly": asm}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--stats", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--samples", nargs="+", required=True, help="pooled into one map")
    ap.add_argument("--name", default=None, help="name of the pooled map (default: the sample when one)")
    ap.add_argument("--workers", type=int, default=8)
    a = ap.parse_args(argv)
    name = a.name or (a.samples[0] if len(a.samples) == 1 else None)
    if name is None:
        sys.exit("several samples: give --name")
    summary = call_sample(a.samples, name, Path(a.stats), Path(a.out), a.workers)
    summary["samples"] = list(a.samples)
    log(name, summary)
    with open(Path(a.out) / f"{name}.bulk_calls.json", "w") as fh:
        json.dump(summary, fh, indent=1)


if __name__ == "__main__":
    main()
