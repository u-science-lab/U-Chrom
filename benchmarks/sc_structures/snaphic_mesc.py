"""SnapHiC on the mES cells of the SnapHiC paper, against bulk mESC loops — by number of cells.

    python benchmarks/sc_structures/snaphic_mesc.py bonev      --out DIR             # bulk reference (once)
    python benchmarks/sc_structures/snaphic_mesc.py run        --out DIR --n 100 --rep 0 [--chrom ...]
    python benchmarks/sc_structures/snaphic_mesc.py pseudobulk --out DIR --n 100 --rep 0
    python benchmarks/sc_structures/snaphic_mesc.py summary    --out DIR

Cells: ``ds.load("nagano2017_dip_serum")`` (``snaphic_data.py``), the 742 with the most contacts
(``snaphic_top742``).  As in the paper, subsets are the first N cells of a random permutation of the 742
(``--rep`` seeds the permutation; N = 742 is all of them).

* ``bonev``: HiCCUPS (``uchrom.strc.loop.call_loops_hiccups``, 10 kb, loops <= 2 Mb) and the insulation score
  and boundaries (``insulation_score``, 100 kb diamond) of the Bonev et al. 2017 mESC Hi-C (``bonev2017_mesc_4dn``, the 4DN
  mcool read directly) on chr1-19.
* ``run``: ``call_loops_snaphic`` (loops 100 kb - 1 Mb as in the paper; window ``auto``; anchors on SnapHiC's
  mm10 low-mappability / blacklist bins excluded) on the subset; calls and timing saved.
* ``pseudobulk``: the same cells summed (``uchrom.fea.pseudobulk``, cis, 10 kb, ICE) and HiCCUPS with its default
  and with the paper's "optimal" sparse settings (p = 4, w = 15, single-pixel q-value sum 0.4).
* ``summary``: per call set, the paper's measures (overlap = both anchors within 20 kb): precision against
  SnapHiC's combined mESC reference (HiCCUPS on bulk Hi-C + MAPS on H3K4me3 PLAC-seq, cohesin / H3K27ac
  HiChIP; the paper's source data), recall of its bulk HiCCUPS loops and of our HiCCUPS on Bonev, F1; the
  agreement with the authors' own SnapHiC calls (source data of Fig. 1: N = 742, and the six N-cell subsets);
  the APA of the calls on the Bonev map.  JSON + table.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import snaphic_common as C  # noqa: E402

RES = 10_000
MAX_DIST = 1_000_000


def bonev_path() -> str:
    return str(C.data_dir() / "bonev2017_mesc" / "4DNFIC21MG3U.mcool")


def filter_regions() -> Path:
    return C.data_dir() / "snaphic" / "mm10_filter_regions.txt"


def load_cells():
    import uchrom.datasets as ds
    import uchrom.datasets._load_snaphic  # noqa: F401

    cd = ds.load("nagano2017_dip_serum")
    top = cd.cells.index[cd.cells["snaphic_top742"].to_numpy(bool)]
    return cd, sorted(map(str, top))


def subset(cells, n: int, rep: int):
    if n >= len(cells):
        return list(cells)
    perm = np.random.default_rng(rep).permutation(len(cells))
    return [cells[k] for k in perm[:n]]


def excluded(t: pd.DataFrame) -> np.ndarray:
    """Loops with an anchor on an excluded bin (SnapHiC's mm10 filter regions)."""
    f = pd.read_csv(filter_regions(), sep="\t", header=None, usecols=[0, 1])
    bad = set(zip(f[0].astype(str), f[1].astype(np.int64)))
    a = [(c, s) in bad for c, s in zip(t["chrom1"].astype(str), (t["start1"] // RES) * RES)]
    b = [(c, s) in bad for c, s in zip(t["chrom2"].astype(str), (t["start2"] // RES) * RES)]
    return np.asarray(a) | np.asarray(b)


# ------------------------------------------------------------------------------------------------- stages

def stage_bonev(args):
    from uchrom.strc.loop import HiccupsParams, call_loops_hiccups
    from uchrom.strc.tad import insulation_score

    out = args.out
    info = json.loads((out / "bonev.json").read_text()) if (out / "bonev.json").exists() else {}
    if not (out / "bonev_hiccups_10kb.tsv").exists():
        t0 = time.time()
        tm = {}
        loops = call_loops_hiccups(bonev_path(), resolution=RES, chrom=C.MM10_AUTOSOMES,
                                   params=HiccupsParams(max_dist=2_000_000), key_added=None, timing=tm)
        loops.to_csv(out / "bonev_hiccups_10kb.tsv", sep="\t", index=False)
        info.update({"n_loops": int(len(loops)), "hiccups_s": time.time() - t0, "timing": tm})
    if not (out / "bonev_insulation_10kb.tsv").exists():
        t0 = time.time()
        ins = insulation_score(bonev_path(), resolution=RES, chrom=C.MM10_AUTOSOMES, windows=100_000,
                               key_added=None)
        ins.to_csv(out / "bonev_insulation_10kb.tsv", sep="\t", index=False)
        info.update({"insulation_s": time.time() - t0, "n_boundaries": int(ins["is_boundary_100000"].sum())})
    t0 = time.time()
    C.bonev_band(out / "bonev_band_10kb.cool", url=bonev_path(), max_dist=1_500_000)   # for the APAs
    info.update({"band_s": time.time() - t0, "peak_rss_gb": C.peak_rss_gb()})
    print(json.dumps(info, indent=1, default=str))
    C.write_json(info, out / "bonev.json")


def stage_run(args):
    from uchrom.strc.loop.snaphic import SnapHiCParams, call_loops_snaphic

    cd, top = load_cells()
    cells = subset(top, args.n, args.rep)
    params = SnapHiCParams(max_dist=MAX_DIST, window=args.window, batch=args.batch)
    tm = {}
    t0 = time.time()
    loops = call_loops_snaphic(cd, cells=cells, chrom=args.chrom, params=params, exclude=filter_regions(),
                               key_added=None, backend=args.backend, n_threads=args.threads, timing=tm)
    dt = time.time() - t0
    tag = f"N{len(cells)}_r{args.rep}" + (f"_{args.tag}" if args.tag else "")
    loops.to_csv(args.out / f"snaphic_{tag}.tsv", sep="\t", index=False)
    info = {"n_cells": len(cells), "rep": args.rep, "n_loops": int(len(loops)), "seconds": dt,
            "timing": tm, "peak_rss_gb": C.peak_rss_gb(), "load": C.load_avg(), "cpu": cpu_name(),
            "threads": args.threads, "backend": tm.get("backend"), "cells": cells}
    print(json.dumps({k: v for k, v in info.items() if k != "cells"}, indent=1, default=str))
    C.write_json(info, args.out / f"snaphic_{tag}.json")


def stage_pseudobulk(args):
    from uchrom.fea import pseudobulk
    from uchrom.strc.loop import HiccupsParams, call_loops_hiccups

    cd, top = load_cells()
    cells = subset(top, args.n, args.rep)
    tag = f"N{len(cells)}_r{args.rep}"
    pbdir = args.out / "pseudobulk"
    t0 = time.time()
    summ = pseudobulk(cd, groupby=pd.Series("all", index=cells), contacts="per_cell", trans=False,
                      out_dir=pbdir, key_prefix=f"pb_{tag}")
    key = summ["key"].iloc[0]
    t1 = time.time()
    res = {"n_cells": len(cells), "n_cis": int(summ["n_cis"].iloc[0]), "pseudobulk_s": t1 - t0}
    for name, p in (("default", HiccupsParams(max_dist=MAX_DIST)),
                    ("sparse", HiccupsParams(p=4, w=15, fdr_orphan=0.4, max_dist=MAX_DIST))):
        t2 = time.time()
        loops = call_loops_hiccups(cd, contacts=key, chrom=C.MM10_AUTOSOMES, params=p, key_added=None)
        loops.to_csv(args.out / f"hiccups_pb_{name}_{tag}.tsv", sep="\t", index=False)
        res[f"n_loops_{name}"] = int(len(loops))
        res[f"hiccups_{name}_s"] = time.time() - t2
    print(json.dumps(res, indent=1))
    C.write_json(res, args.out / f"pseudobulk_{tag}.json")


def cpu_name() -> str:
    try:
        for line in open("/proc/cpuinfo"):
            if line.startswith("model name"):
                return line.split(":", 1)[1].strip()
    except OSError:
        pass
    import platform

    return platform.processor()


#: the band of the Bonev map (stage bonev; set by summary): one small file for the many APAs
APA_MAP = None


def apa(calls: pd.DataFrame) -> dict:
    from uchrom.fea import pileup

    if not len(calls):
        return {"apa": float("nan"), "n": 0}
    band = APA_MAP if APA_MAP is not None and Path(APA_MAP).exists() else bonev_path()
    r = pileup(str(band), calls, resolution=RES, shifts=(-1_000_000, -500_000, 500_000, 1_000_000),
               key_added=None)
    return {"apa": float(r["apa"]), "zscore_ll": float(r.get("zscore_ll", np.nan)), "n": int(r["n"]),
            "control": float(r.get("control", np.nan))}


def stage_summary(args):
    global APA_MAP
    out = args.out
    APA_MAP = out / "bonev_band_10kb.cool"
    union = C.reference_union()
    bulk_paper = C.snaphic_published("Bulk_HiC_filter")
    ours = pd.read_csv(out / "bonev_hiccups_10kb.tsv", sep="\t")
    ours = C.in_range(ours, 100_000, MAX_DIST, C.MM10_AUTOSOMES)
    ours = ours[~excluded(ours)].reset_index(drop=True)
    rows = []

    def measure(name, n, rep, calls, extra=None):
        calls = C.in_range(calls, 100_000, MAX_DIST, C.MM10_AUTOSOMES)
        r = {"set": name, "n_cells": n, "rep": rep, "n_loops": int(len(calls))}
        pr = C.precision_recall(calls, bulk_paper, precision_reference=union)
        r.update({"precision_union": pr["precision"], "recall_bulk_hiccups_paper": pr["recall"], "f1": pr["f1"]})
        pr2 = C.precision_recall(calls, ours)
        r.update({"precision_bonev_ours": pr2["precision"], "recall_bonev_ours": pr2["recall"]})
        r["recall_union"] = float(C.overlap(union, calls).mean()) if len(calls) else 0.0
        if extra:
            r.update(extra)
        if args.apa:
            a = apa(calls)
            r.update({"apa_bonev": a["apa"], "apa_control": a.get("control"), "apa_n": a["n"]})
        rows.append(r)
        return calls

    sheets = [s for s in C.published_sheets() if s.startswith("Permu")]
    for js in sorted(out.glob("snaphic_N*_r*.json")):
        info = json.loads(js.read_text())
        tsv = js.with_suffix(".tsv")
        calls = pd.read_csv(tsv, sep="\t")
        n, rep = info["n_cells"], info["rep"]
        paper_n = n if f"Permu0_{n}" in sheets else None
        extra = {"seconds": info["seconds"], "peak_rss_gb": info["peak_rss_gb"], "backend": info.get("backend"),
                 "tag": tsv.stem}
        calls = measure("snaphic_uchrom", n, rep, calls, extra)
        if paper_n is not None:
            permus = [s for s in sheets if s.endswith(f"_{n}")]
            agree = []
            for s in permus:
                theirs = C.in_range(C.snaphic_published(s), 100_000, MAX_DIST)
                agree.append({"sheet": s, "n_theirs": len(theirs),
                              "ours_in_theirs": float(C.overlap(calls, theirs).mean()) if len(calls) else np.nan,
                              "theirs_in_ours": float(C.overlap(theirs, calls).mean()) if len(theirs) else np.nan})
            rows[-1]["vs_paper_snaphic"] = agree
    for s in [s for s in sheets if s.startswith("Permu0_")]:
        n = int(s.split("_")[1])
        measure("snaphic_paper", n, 0, C.snaphic_published(s))
    for js in sorted(out.glob("pseudobulk_N*_r*.json")):
        info = json.loads(js.read_text())
        tag = js.stem.replace("pseudobulk_", "")
        for name in ("default", "sparse"):
            t = pd.read_csv(out / f"hiccups_pb_{name}_{tag}.tsv", sep="\t")
            measure(f"hiccups_pseudobulk_{name}", info["n_cells"], int(tag.split("_r")[1]), t)
    measure("hiccups_bonev_ours", 0, 0, ours)
    table = pd.DataFrame(rows)
    cols = ["set", "n_cells", "rep", "n_loops", "precision_union", "recall_bulk_hiccups_paper", "f1",
            "precision_bonev_ours", "recall_bonev_ours", "recall_union"] + (["apa_bonev", "apa_control"] if args.apa else [])
    print(table[cols].sort_values(["set", "n_cells", "rep"]).to_string(index=False, float_format=lambda x: f"{x:.3f}"))
    for r in rows:
        if "vs_paper_snaphic" in r:
            v = r["vs_paper_snaphic"]
            print(f"{r['tag']}: ours in theirs {np.mean([x['ours_in_theirs'] for x in v]):.3f}, theirs in ours "
                  f"{np.mean([x['theirs_in_ours'] for x in v]):.3f} (mean over {len(v)} paper subsets; their "
                  f"n = {np.mean([x['n_theirs'] for x in v]):.0f})")
    C.write_json({"rows": rows, "n_reference_union": len(union), "n_bulk_paper": len(bulk_paper),
                  "n_bonev_ours": len(ours)}, out / "snaphic_mesc_summary.json")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("stage", choices=["bonev", "run", "pseudobulk", "summary"])
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--n", type=int, default=742)
    ap.add_argument("--rep", type=int, default=0)
    ap.add_argument("--chrom", nargs="*", default=None)
    ap.add_argument("--window", default="auto", help="bp, 'auto' (SnapHiC2's rule) or 'none' (whole chromosomes)")
    ap.add_argument("--batch", type=int, default=0, help="cells imputed at once (native; 0: one per thread)")
    ap.add_argument("--backend", default=None)
    ap.add_argument("--threads", type=int, default=0)
    ap.add_argument("--tag", default="")
    ap.add_argument("--apa", action="store_true")
    args = ap.parse_args()
    args.window = None if str(args.window).lower() == "none" else (
        "auto" if args.window == "auto" else int(args.window))
    args.out.mkdir(parents=True, exist_ok=True)
    {"bonev": stage_bonev, "run": stage_run, "pseudobulk": stage_pseudobulk, "summary": stage_summary}[args.stage](args)


if __name__ == "__main__":
    main()
