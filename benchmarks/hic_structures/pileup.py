"""Validation of ``uchrom.fea.pileup`` (APA, Rao et al. 2014): known loops and boundaries scored in maps too
sparse to call them.

Sections (each prints a table; all numbers go to ``OUT/pileup.json``):

``depth``        the authors' HiCCUPS loops of IMR90 chr21 (GSE63525) piled up on the IMR90 chr21 map thinned to
                 100 / 20 / 5 / 2 % (binomial, as ``hiccups.py``), at 10 and 25 kb, ±100 kb: APA (P2LL),
                 z-score (pooled ratio, the default; and the mean of the O/E windows), against loops of random
                 position at the same separations (20 draws: mean and 95th percentile), next to the share of
                 the published loops ``call_loops_hiccups`` recovers on the same map — does the APA stay above
                 1 where calling fails?
``specificity``  IMR90-only, shared and GM12878-only published loops (shared: anchors within 25 kb in both
                 lists) piled up on the IMR90 maps (full and thinned) and on GM12878 — cell-type-specific loops
                 are told apart by the pileup;
``single_cells`` (needs ``--pseudobulk``: the GM12878 single-cell pseudo-bulk of chr21, a raw 5-kb hg19 cooler
                 — ``pseudobulk_gm12878.py`` writes ``combined_chr21_5kb.cool``) HiCCUPS calls and the APA of
                 the GM12878 loops, of the IMR90-only loops and of random pairs in that map;
``boundaries``   the edges of the authors' Arrowhead domains (IMR90 chr21) piled up on the diagonal at 25 kb
                 (±250 kb): boundary score (within / across), against the edges shifted by half a window;
``imaging``      loops called from chromatin tracing (ArcFISH axis-wise F test on Su 2020 IMR90 chr21,
                 ``ds.load("su2020_chr21")``) piled up on the Rao 2014 IMR90 map summed into the imaged loci
                 (hg38, linked as ``rao2014``): APA against random locus pairs at the same separations;
``chr1``         run time / memory of pileups on IMR90 chr1 at 5 kb (published chr1 loops; 20,000 random pairs).

Run from the repository root (after ``hiccups.py``, whose maps it reuses)::

    .venv/bin/python benchmarks/hic_structures/pileup.py --out SCRATCH/hic_structures \\
        [--pseudobulk PB/combined_chr21_5kb.cool] [--only depth,specificity,single_cells,boundaries,imaging,chr1]
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from hiccups import DEPTHS, _cd, _table, balanced, matched, prepare, published  # noqa: E402

FLANK = 100_000
N_RANDOM = 20


def _random_like(t: pd.DataFrame, n_bins: int, res: int, rng, *, margin: int = 0) -> pd.DataFrame:
    """Pairs at the separations of ``t`` (bins), at random positions on the chromosome."""
    sep = ((t["start2"] + t["end2"]) // 2 - (t["start1"] + t["end1"]) // 2).to_numpy() // res
    hi = np.maximum(n_bins - sep - margin, margin + 1)
    a = rng.integers(margin, hi)
    return pd.DataFrame({"chrom1": t["chrom1"].to_numpy(), "start1": a * res, "end1": a * res + res,
                         "chrom2": t["chrom1"].to_numpy(), "start2": (a + sep) * res, "end2": (a + sep) * res + res})


def _apa(path, feats, **kw) -> dict:
    from uchrom.fea import pileup

    r = pileup(path, feats, key_added=None, **kw)
    return {"n": r["n"], "apa": r.get("apa"), "zscore_ll": r.get("zscore_ll"), "p2m": r.get("p2m"),
            "score": r.get("score"), "center": r.get("center"), "frac_center_gt_1":
            float((r["features"].loc[r["features"]["used"], "center"] > 1).mean()) if r["n"] else np.nan}


def _control(path, feats, res, n_bins, flank=FLANK, **kw) -> dict:
    rng = np.random.default_rng(0)
    vals = [_apa(path, _random_like(feats, n_bins, res, rng, margin=12), flank=flank, **kw)["apa"]
            for _ in range(N_RANDOM)]
    vals = np.asarray([v for v in vals if v is not None and np.isfinite(v)])
    return {"random_apa_mean": float(vals.mean()), "random_apa_p95": float(np.quantile(vals, 0.95))}


def _n_bins(path) -> int:
    import cooler

    return int(cooler.Cooler(path).info["nbins"])


def section_depth(maps, out, args) -> list:
    from uchrom.strc.loop.hiccups import HiccupsParams, call_loops_hiccups

    ref = published("imr90")
    rows = []
    for frac in DEPTHS:
        tag = "imr90" if frac == 1.0 else f"imr90_d{int(round(frac * 100))}"
        for res in (10000, 25000):
            path = maps[(tag, res)]
            loops = call_loops_hiccups(_cd(), contacts=path, params=HiccupsParams(), key_added=None)
            a = _apa(path, ref, flank=FLANK)
            am = _apa(path, ref, flank=FLANK, aggregate="mean")
            rows.append({"depth": frac, "res": res, "published_piled": a["n"], "apa": a["apa"],
                         "zscore_ll": a["zscore_ll"], "apa_mean": am["apa"], "zscore_ll_mean": am["zscore_ll"],
                         "frac_center_gt_1": a["frac_center_gt_1"],
                         **_control(path, ref, res, _n_bins(path)),
                         "hiccups_calls": len(loops), "hiccups_recall": float(matched(ref, loops).mean())})
    _table(rows, f"depth: APA of the published IMR90 chr21 loops (±{FLANK // 1000} kb) vs random pairs, HiCCUPS recall")
    return rows


def _split_specific(a: pd.DataFrame, b: pd.DataFrame):
    sa, sb = matched(a, b), matched(b, a)
    return a[~sa], a[sa], b[~sb]


def section_specificity(maps, out, args) -> list:
    imr, gm = published("imr90"), published("gm12878")
    imr_only, shared, gm_only = _split_specific(imr, gm)
    rows = []
    for tag in ("imr90", "imr90_d5", "imr90_d2", "gm12878"):
        if (tag, 10000) not in maps:
            continue
        for res in (10000, 25000):
            path = maps[(tag, res)]
            row = {"map": tag, "res": res}
            for name, t in (("imr90_only", imr_only), ("shared", shared), ("gm12878_only", gm_only)):
                a = _apa(path, t, flank=FLANK)
                row[f"{name}_n"], row[f"{name}_apa"] = a["n"], a["apa"]
            rows.append(row)
    print(f"\nloops: {len(imr_only)} IMR90-only, {len(shared)} shared (IMR90 side), {len(gm_only)} GM12878-only")
    _table(rows, "specificity: APA of cell-type-specific published loops")
    return rows


def section_single_cells(maps, out, args) -> list:
    import cooler

    from uchrom.strc.loop.hiccups import HiccupsParams, call_loops_hiccups

    if not args.pseudobulk:
        print("\n== single_cells: skipped (no --pseudobulk)")
        return []
    src = str(args.pseudobulk)
    d = out / "hiccups_maps"
    raw = cooler.Cooler(src)
    n_contacts = int(raw.pixels()[:]["count"].sum())
    imr, gm = published("imr90"), published("gm12878")
    imr_only, _, gm_only = _split_specific(imr, gm)
    rows = []
    for res in (10000, 25000):
        path = balanced(src, res, d / f"gm12878_pseudobulk_chr21_{res // 1000}k.cool")
        try:
            loops = call_loops_hiccups(_cd(), contacts=path, params=HiccupsParams(), key_added=None)
            n_calls, rec = len(loops), float(matched(gm, loops).mean())
            prec = float(matched(loops, gm).mean()) if len(loops) else np.nan
        except Exception as e:                     # noqa: BLE001 - a map too sparse to balance / score
            n_calls, rec, prec = f"failed ({type(e).__name__})", np.nan, np.nan
        row = {"res": res, "chr21_contacts": n_contacts, "hiccups_calls": n_calls, "hiccups_recall_gm12878": rec,
               "hiccups_precision_gm12878": prec}
        for name, t in (("gm12878", gm), ("gm12878_only", gm_only), ("imr90_only", imr_only)):
            a = _apa(path, t, flank=FLANK)
            row[f"{name}_n"], row[f"{name}_apa"], row[f"{name}_z"] = a["n"], a["apa"], a["zscore_ll"]
            row[f"{name}_apa_mean"] = _apa(path, t, flank=FLANK, aggregate="mean")["apa"]
        row.update(_control(path, gm, res, _n_bins(path)))
        rows.append(row)
    _table(rows, f"single cells: GM12878 pseudo-bulk ({Path(src).name}), chr21")
    return rows


def section_boundaries(maps, out, args) -> list:
    import uchrom.datasets as ds

    root = Path(ds.fetch("rao2014_annotations"))
    dom = pd.read_csv(root / "GSE63525_IMR90_Arrowhead_domainlist.txt.gz", sep="\t")
    dom = dom[dom["chr1"].astype(str) == "21"]
    edges = np.unique(np.r_[dom["x1"].to_numpy(), dom["x2"].to_numpy()])
    pts = pd.DataFrame({"chrom": "chr21", "start": edges, "end": edges + 1})
    rows = []
    for frac in DEPTHS:
        tag = "imr90" if frac == 1.0 else f"imr90_d{int(round(frac * 100))}"
        path = maps[(tag, 25000)]
        a = _apa(path, pts, flank=250_000)
        s = _apa(path, pts.assign(start=pts["start"] + 125_000, end=pts["end"] + 125_000), flank=250_000)
        rows.append({"depth": frac, "edges": a["n"], "boundary_score": a["score"], "shifted_score": s["score"]})
    _table(rows, "boundaries: Arrowhead domain edges, IMR90 chr21, 25 kb, ±250 kb")
    return rows


def section_imaging(maps, out, args) -> list:
    import uchrom.datasets as ds
    from uchrom.fea.maps import map_path
    from uchrom.strc.loop import call_loops_axiswise_f

    cd = ds.load("su2020_chr21")
    cache = out / "arcfish_su2020_chr21.tsv"
    t = time.perf_counter()
    if cache.exists():
        loops = pd.read_csv(cache, sep="\t")
    else:
        loops = call_loops_axiswise_f(cd, key_added=None)
        loops.to_csv(cache, sep="\t", index=False)
    t_call = time.perf_counter() - t
    path = map_path(cd, "rao2014")
    loci = cd.bins.reset_index(drop=True)
    rows = []
    for flank in (100_000, 150_000):
        a = _apa(path, loops, flank=flank)
        rng = np.random.default_rng(0)
        si = (loops["start1"].map(dict(zip(loci["start"], loci.index)))).to_numpy()
        sj = (loops["start2"].map(dict(zip(loci["start"], loci.index)))).to_numpy()
        sep = sj - si
        vals = []
        for _ in range(N_RANDOM):
            a0 = rng.integers(5, len(loci) - sep - 5)
            r = pd.DataFrame({"chrom1": "chr21", "start1": loci["start"].to_numpy()[a0], "end1": loci["end"].to_numpy()[a0],
                              "chrom2": "chr21", "start2": loci["start"].to_numpy()[a0 + sep],
                              "end2": loci["end"].to_numpy()[a0 + sep]})
            vals.append(_apa(path, r, flank=flank)["apa"])
        vals = np.asarray(vals, float)
        rows.append({"arcfish_loops": len(loops), "flank_kb": flank // 1000, "piled": a["n"], "apa": a["apa"],
                     "zscore_ll": a["zscore_ll"], "random_apa_mean": float(np.nanmean(vals)),
                     "random_apa_p95": float(np.nanquantile(vals, 0.95)), "arcfish_s": t_call})
    _table(rows, "imaging: ArcFISH loops (Su 2020 IMR90 chr21) in Rao 2014 Hi-C summed into the imaged loci")
    return rows


_CHILD = r"""
import json, resource, sys, time
import numpy as np, pandas as pd
from uchrom.fea import pileup
feats = pd.read_csv(sys.argv[2], sep="\t")
t = time.perf_counter()
r = pileup(sys.argv[1], feats, flank=int(sys.argv[3]), key_added=None)
out = {"seconds": time.perf_counter() - t, "n": r["n"], "apa": r["apa"],
       "max_rss_gb": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / (1e9 if sys.platform == "darwin" else 1e6)}
print(json.dumps(out))
"""


def section_chr1(maps, out, args) -> list:
    import subprocess

    path = maps[("imr90_chr1", 5000)]
    ref = published("imr90", "1")
    rng = np.random.default_rng(0)
    rand = _random_like(pd.concat([ref] * 25, ignore_index=True), _n_bins(path), 5000, rng, margin=12)[:20_000]
    rows = []
    for name, t in (("published chr1 loops", ref), ("random pairs", rand)):
        f = out / f"pileup_chr1_{name.split()[0]}.tsv"
        t.to_csv(f, sep="\t", index=False)
        for flank in (50_000, 100_000):
            r = subprocess.run([sys.executable, "-c", _CHILD, path, str(f), str(flank)], capture_output=True, text=True)
            if r.returncode:
                raise RuntimeError(r.stderr[-2000:])
            rows.append({"features": name, "count": len(t), "flank_kb": flank // 1000,
                         **json.loads(r.stdout.strip().splitlines()[-1])})
    _table(rows, "chr1 at 5 kb: pileup run time and peak memory")
    return rows


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", type=Path, default=Path(tempfile.gettempdir()) / "uchrom_hic_structures")
    ap.add_argument("--pseudobulk", type=Path, default=None,
                    help="raw 5-kb hg19 cooler of the GM12878 single-cell pseudo-bulk (chr21)")
    ap.add_argument("--only", default="depth,specificity,single_cells,boundaries,imaging,chr1")
    a = ap.parse_args(argv)
    a.out.mkdir(parents=True, exist_ok=True)
    only = a.only.split(",")
    maps = prepare(a.out, chr1="chr1" in only, depth=True)
    path = a.out / "pileup.json"
    res = json.loads(path.read_text()) if path.exists() else {}
    for name in only:
        t = time.time()
        res[name] = globals()[f"section_{name}"](maps, a.out, a)
        print(f"[{name}: {time.time() - t:.0f} s]", flush=True)
        path.write_text(json.dumps(res, indent=1, default=lambda v: None if v is None else float(v)))
    print(f"\nwrote {path}")


if __name__ == "__main__":
    main()
