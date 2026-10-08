"""SnapHiC and single-cell boundaries on the GM12878 single cells, against Rao et al. 2014 (chr21) — a small check.

    python benchmarks/sc_structures/snaphic_gm12878.py --out DIR

Cells: Tan 2018 Dip-C (``ds.load("tan2018_gm12878")``, 14 cells, hg19) and Wu 2025 scMicro-C
(``ds.load("wu2025_scmicroc")``, the 10 cells passing QC, hg38; chr21 bins lifted to hg19 through the UCSC chain,
``ds.fetch("hg38_to_hg19_chain")``): 24 cells, their chr21 maps summed from 5 kb to 10 kb into one ``.scool``.

* SnapHiC (``call_loops_snaphic``: 10 kb, loops 100 kb - 1 Mb, whole chromosome — the default — and SnapHiC2's
  windows, SnapHiC's hg19 filter regions) and HiCCUPS on the pseudo-bulk of the 24 cells (default settings and the paper's sparse ones), against
  Rao 2014 GM12878 HiCCUPS loops on chr21 (``ds.fetch("rao2014_annotations")``) with SnapHiC's overlap rule
  (anchors within 20 kb); APA of each call set on Rao's chr21 map (``ds.fetch("rao2014_gm12878_chr21")``, 5 kb).
* ``single_cell_boundaries`` (insulation of each cell's imputed map, 100 kb diamond) against Rao's Arrowhead
  domain edges on chr21: share of the consensus boundaries within 2 bins of an edge (chance: the same for every
  bin), frequency at the edges vs elsewhere.

24 cells are far fewer than SnapHiC needs (the paper: >= 75-100); the numbers are reported as they come.
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
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "hic_structures"))
import snaphic_common as C  # noqa: E402

RES = 10_000
HG19_CHR21 = 48129895


def build_scool(out: Path) -> Path:
    import cooler

    import uchrom.datasets as ds
    from pseudobulk_gm12878 import chain_blocks, lift
    from uchrom.fea.impute_rwr import _ScoolCells

    path = out / "gm12878_chr21_10kb.scool"
    if path.exists():
        return path
    n = -(-HG19_CHR21 // RES)
    maps = {}
    tan = ds.load("tan2018_gm12878")
    wu = ds.load("wu2025_scmicroc")
    chain = chain_blocks(ds.fetch("hg38_to_hg19_chain"))
    for cd, lifted in ((tan, False), (wu, True)):
        ids = [str(c) for c in cd.cells.index]
        if "qc_pass" in cd.cells.columns:
            ids = [c for c, ok in zip(ids, cd.cells["qc_pass"]) if bool(ok)]
        src = _ScoolCells(cd.linked_scool_path("per_cell"))
        res0 = src.binsize
        for c in ids:
            i, j, cnt = src.cis(c, "chr21")
            if lifted:
                pi = lift(i * res0 + res0 // 2, chain)
                pj = lift(j * res0 + res0 // 2, chain)
                ok = (pi >= 0) & (pj >= 0) & (pi < HG19_CHR21) & (pj < HG19_CHR21)
                a, b, cnt = pi[ok] // RES, pj[ok] // RES, cnt[ok]
            else:
                a, b = (i * res0) // RES, (j * res0) // RES
            lo, hi = np.minimum(a, b), np.maximum(a, b)
            k, inv = np.unique(lo * n + hi, return_inverse=True)
            maps[f"{'tan' if not lifted else 'wu'}_{c}"] = pd.DataFrame(
                {"bin1_id": k // n, "bin2_id": k % n, "count": np.bincount(inv, weights=cnt).astype(np.int64)})
        src.close()
    starts = np.arange(n, dtype=np.int64) * RES
    bins = pd.DataFrame({"chrom": "chr21", "start": starts, "end": np.minimum(starts + RES, HG19_CHR21)})
    cooler.create_scool(str(path), bins, maps, ordered=True, assembly="hg19")
    return path


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    import uchrom.datasets as ds
    from chromdata import ChromData
    from uchrom.fea import pileup, pseudobulk
    from uchrom.io import read_juicer_domains, read_juicer_loops
    from uchrom.strc.loop import HiccupsParams, call_loops_hiccups
    from uchrom.strc.loop.snaphic import SnapHiCParams, call_loops_snaphic
    from uchrom.strc.tad.single_cell import SingleCellBoundaryParams, single_cell_boundaries

    t0 = time.time()
    scool = build_scool(args.out)
    names = list(__import__("uchrom.fea.impute_rwr", fromlist=["_ScoolCells"])._ScoolCells(scool).names)
    no = pd.DataFrame({c: pd.Series(dtype=t) for c, t in [("chrom", str), ("start", np.int64), ("end", np.int64),
                                                          ("trace_id", str), ("cell_id", str)]})
    cd = ChromData(np.zeros((0, 3)), no, cells=pd.DataFrame(index=pd.Index(names, name="cell_id")),
                   uns={"genome_assembly": "hg19"})
    cd.link_scool(str(scool), key="per_cell", bin_size=RES, genome_assembly="hg19")
    ann = ds.fetch("rao2014_annotations")
    ann = ann if ann.is_dir() else ann.parent
    rao = read_juicer_loops(ann / "GSE63525_GM12878_primary+replicate_HiCCUPS_looplist.txt.gz", chrom="chr21")
    rao_in = C.in_range(rao, 100_000, 1_000_000)
    rao_map = str(ds.fetch("rao2014_gm12878_chr21"))
    excl = C.data_dir() / "snaphic" / "hg19_filter_regions.txt"
    res = {"n_cells": len(names), "n_rao_loops_chr21": int(len(rao)), "n_rao_loops_100k_1M": int(len(rao_in)),
           "build_s": time.time() - t0}
    sets = {}
    tm = {}
    t1 = time.time()
    sets["snaphic"] = call_loops_snaphic(cd, chrom="chr21", params=SnapHiCParams(max_dist=1_000_000),
                                         exclude=excl, key_added=None, timing=tm)
    sets["snaphic_windows"] = call_loops_snaphic(cd, chrom="chr21",
                                                 params=SnapHiCParams(max_dist=1_000_000, window="auto"),
                                                 exclude=excl, key_added=None)
    res["snaphic_s"] = time.time() - t1
    res["snaphic_timing"] = tm
    pb = pseudobulk(cd, contacts="per_cell", trans=False, out_dir=args.out / "pb", key_prefix="pb")
    for name, p in (("default", HiccupsParams(max_dist=1_000_000)),
                    ("sparse", HiccupsParams(p=4, w=15, fdr_orphan=0.4, max_dist=1_000_000))):
        sets[f"hiccups_pseudobulk_{name}"] = call_loops_hiccups(cd, contacts=pb["key"].iloc[0], chrom="chr21",
                                                                params=p, key_added=None)
    for name, t in sets.items():
        t = C.in_range(t, 100_000, 1_000_000)
        pr = C.precision_recall(t, rao_in)
        r = {**pr}
        if len(t):
            a = pileup(rao_map, t, resolution=5000, shifts=(-1_000_000, -500_000, 500_000, 1_000_000),
                       key_added=None)
            r.update({"apa_rao": float(a["apa"]), "apa_control": float(a.get("control", np.nan))})
        res[name] = r
        print(f"{name:28s} n={pr['n_calls']:4d} precision={pr['precision']:.3f} recall={pr['recall']:.3f} "
              f"apa={r.get('apa_rao', float('nan')):.2f} (shifted {r.get('apa_control', float('nan')):.2f})")
        t.to_csv(args.out / f"{name}.tsv", sep="\t", index=False)
    a = pileup(rao_map, rao_in, resolution=5000, key_added=None)
    res["apa_rao_loops_on_rao_map"] = float(a["apa"])
    # single-cell boundaries vs Arrowhead edges
    t2 = time.time()
    b = single_cell_boundaries(cd, chrom="chr21", params=SingleCellBoundaryParams(insulation_window=100_000),
                               key_added=None)
    res["boundaries_s"] = time.time() - t2
    dom = read_juicer_domains(ann / "GSE63525_GM12878_primary+replicate_Arrowhead_domainlist.txt.gz", chrom="chr21")
    edges = np.unique(np.r_[dom["start1"] if "start1" in dom else dom["start"],
                            dom["end1"] if "end1" in dom else dom["end"]] // RES)
    nb = len(b)
    near = np.zeros(nb, bool)
    for e in edges:
        near[max(0, e - 2):min(nb, e + 3)] = True
    cons = b["consensus"].to_numpy(bool)
    f = b["frequency"].to_numpy()
    covered = b["n_cells"].to_numpy() > 0
    res["boundaries"] = {"n_consensus": int(cons.sum()), "n_arrowhead_edges": int(len(edges)),
                         "consensus_near_edge": float(near[cons].mean()) if cons.any() else None,
                         "chance": float(near[covered].mean()),
                         "edges_with_consensus_within_2_bins": float(np.mean(
                             [cons[max(0, e - 2):e + 3].any() for e in edges if e < nb])),
                         "frequency_near_edges": float(np.nanmean(f[near & covered])),
                         "frequency_elsewhere": float(np.nanmean(f[~near & covered]))}
    print(json.dumps(res["boundaries"], indent=1))
    C.write_json(res, args.out / "snaphic_gm12878.json")


if __name__ == "__main__":
    main()
