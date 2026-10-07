"""Validation of ``uchrom.strc.loop.call_loops_hiccups`` (HiCCUPS, Rao et al. 2014, in cooltools' formulation)
on real Hi-C.

Sections (each prints a table; all numbers go to ``OUT/hiccups.json``):

``reference``  agreement with cooltools 0.7.1 ``dots`` (Open2C 2024) on the same balanced maps — Rao 2014
               IMR90 and GM12878 chr21 at 5 / 10 / 25 kb, loops up to 2 Mb: the enriched pixels before
               clustering (``pvalue="cooltools"``, cooltools' P(X > obs)): identical sets?, largest relative
               difference of the locally adjusted expecteds, of the q-values; the final calls (clustering
               differs: HiCCUPS' greedy radius here, sklearn Birch in cooltools): summits in common, calls
               within one bin; run times;
``rao2014``    against the authors' HiCCUPS lists (GSE63525; hg19 as the maps), chr21, IMR90 and GM12878:
               recall / precision (a call matches a published loop when both anchor midpoints are within
               25 kb), per resolution and merged across resolutions as Rao 2014 did (5+10, 5+10+25), with the
               defaults (P(X >= obs), loops up to 10 Mb); also the recall among the published loops the kernels
               can reach (anchors at least 2w + 2 bins apart) and cooltools' numbers on the same maps;
``depth``      binomial thinning of the IMR90 chr21 5-kb counts to 20 / 5 / 2 % (the depths of atlas cell-type
               pseudo-bulks), rebinned to 10 / 25 kb and ICE-balanced: calls, recall / precision against the
               published list and against the full-depth calls, next to cooltools;
``chr1``       runtime and peak memory on IMR90 chr1 at 5 kb (49,851 bins, 26.5 M pixels), loops up to 2 and
               10 Mb, per step (band read, dense tiles, summed-area tables, footprint mask, kernel sums,
               λ-chunk histograms, thresholds, clustering) and cooltools ``dots`` on the same map (2 Mb);
               recall / precision against the published chr1 list.

Run from the repository root::

    .venv/bin/python benchmarks/hic_structures/hiccups.py --out SCRATCH/hic_structures \\
        --ref-python SCRATCH/ctenv/bin/python [--only reference,rao2014,depth,chr1]

Inputs (``uchrom.datasets``): ``rao2014_imr90_chr21`` (load), ``rao2014_gm12878_chr21``,
``rao2014_imr90_chr1``, ``rao2014_annotations`` (fetch).  Balanced and thinned maps are written to
``OUT/hiccups_maps`` (reused when present).
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
DEPTHS = (1.0, 0.2, 0.05, 0.02)
TOL = 25_000
LOOP_LISTS = {"imr90": "GSE63525_IMR90_HiCCUPS_looplist.txt.gz",
              "gm12878": "GSE63525_GM12878_primary+replicate_HiCCUPS_looplist.txt.gz"}


# ------------------------------------------------------------------------------------------------ inputs

def _raw_maps() -> dict:
    """The raw 5-kb coolers (hg19) of the Rao 2014 slices."""
    import uchrom.datasets as ds
    from uchrom.fea.maps import map_path

    out = {"imr90_chr21": map_path(ds.load("rao2014_imr90_chr21"), "bulk")}
    for key, name, fname in (("gm12878_chr21", "rao2014_gm12878_chr21", "GM12878_chr21_5kb_hg19.cool"),
                             ("imr90_chr1", "rao2014_imr90_chr1", "IMR90_chr1_5kb_hg19.cool")):
        got = Path(ds.fetch(name))
        out[key] = str(got if got.suffix == ".cool" else next(got.rglob(fname)))
    return out


def _thin(src: str, frac: float, out: Path, seed: int = 0) -> str:
    import cooler

    if out.exists():
        return str(out)
    clr = cooler.Cooler(src)
    px = clr.pixels()[:]
    rng = np.random.default_rng(seed)
    c = rng.binomial(px["count"].to_numpy(np.int64), frac)
    keep = c > 0
    tmp = out.with_suffix(".part")
    cooler.create_cooler(str(tmp), clr.bins()[["chrom", "start", "end"]][:],
                         pd.DataFrame({"bin1_id": px["bin1_id"].to_numpy()[keep],
                                       "bin2_id": px["bin2_id"].to_numpy()[keep], "count": c[keep]}),
                         ordered=True, assembly=clr.info.get("genome-assembly"))
    tmp.rename(out)
    return str(out)


def balanced(src: str, res: int, out: Path) -> str:
    """``src`` summed to ``res`` and ICE-balanced (``uchrom.fea.rebin_map``), cached at ``out``."""
    from uchrom.fea.maps import rebin_map

    if not out.exists():
        rebin_map(src, resolution=res, out=out, key_added=None)
    return str(out)


def prepare(out: Path, *, chr1: bool = False, depth: bool = False) -> dict:
    """``{(sample, res): path}`` of the balanced maps (sample: imr90 / gm12878 / imr90_d20 / ... / imr90_chr1)."""
    d = out / "hiccups_maps"
    d.mkdir(parents=True, exist_ok=True)
    raw = _raw_maps()
    maps = {}
    for cell in ("imr90", "gm12878"):
        for res in (5000, 10000, 25000):
            maps[(cell, res)] = balanced(raw[f"{cell}_chr21"], res, d / f"{cell}_chr21_{res // 1000}k.cool")
    if depth:
        for frac in DEPTHS[1:]:
            tag = f"imr90_d{int(round(frac * 100))}"
            src = _thin(raw["imr90_chr21"], frac, d / f"{tag}_chr21_5k_raw.cool")
            for res in (5000, 10000, 25000):
                maps[(tag, res)] = balanced(src, res, d / f"{tag}_chr21_{res // 1000}k.cool")
    if chr1:
        maps[("imr90_chr1", 5000)] = balanced(raw["imr90_chr1"], 5000, d / "imr90_chr1_5k.cool")
    return maps


def published(cell: str, chrom: str = "21") -> pd.DataFrame:
    import uchrom.datasets as ds

    root = Path(ds.fetch("rao2014_annotations"))
    path = root / LOOP_LISTS[cell] if root.is_dir() else root.parent / LOOP_LISTS[cell]
    t = pd.read_csv(path, sep="\t")
    t = t[t["chr1"].astype(str) == chrom]
    return pd.DataFrame({"chrom1": f"chr{chrom}", "start1": t["x1"].to_numpy(np.int64), "end1": t["x2"].to_numpy(np.int64),
                         "chrom2": f"chr{chrom}", "start2": t["y1"].to_numpy(np.int64), "end2": t["y2"].to_numpy(np.int64),
                         "observed": t["o"].to_numpy()}).reset_index(drop=True)


def _mids(t: pd.DataFrame):
    return ((t["start1"].to_numpy(np.int64) + t["end1"].to_numpy(np.int64)) / 2,
            (t["start2"].to_numpy(np.int64) + t["end2"].to_numpy(np.int64)) / 2)


def matched(a: pd.DataFrame, b: pd.DataFrame, tol: float = TOL) -> np.ndarray:
    """For every row of ``a``: a row of ``b`` with both anchor midpoints within ``tol`` (same chromosome)."""
    if not len(a) or not len(b):
        return np.zeros(len(a), bool)
    a1, a2 = _mids(a)
    b1, b2 = _mids(b)
    same = a["chrom1"].astype(str).to_numpy()[:, None] == b["chrom1"].astype(str).to_numpy()[None, :]
    d = np.maximum(np.abs(a1[:, None] - b1[None, :]), np.abs(a2[:, None] - b2[None, :]))
    return ((d <= tol) & same).any(1)


def scores(calls: pd.DataFrame, ref: pd.DataFrame, tol: float = TOL) -> dict:
    rec = matched(ref, calls, tol)
    prec = matched(calls, ref, tol)
    return {"n": int(len(calls)), "recall": float(rec.mean()) if len(ref) else np.nan,
            "precision": float(prec.mean()) if len(calls) else np.nan, "n_found": int(rec.sum())}


def reachable(ref: pd.DataFrame, res: int) -> np.ndarray:
    """Published loops whose anchors are far enough apart for the kernels at ``res`` (2w + 2 bins)."""
    from uchrom.strc.loop.hiccups import kernel_sizes

    _, w = kernel_sizes(res)
    m1, m2 = _mids(ref)
    return (m2 - m1) >= (2 * w + 2) * res


def cooltools_ref(ref_python: str, path: str, prefix: Path, max_sep: int, pixels: bool = True) -> dict:
    """Run ``hiccups_ref_cooltools.py`` (cached by its outputs)."""
    meta = prefix.with_suffix(".json")
    if meta.exists() and (prefix.parent / (prefix.name + "_dots.tsv")).exists() and \
            (not pixels or (prefix.parent / (prefix.name + "_pixels.tsv")).exists()):
        info = json.loads(meta.read_text())
    else:
        cmd = [ref_python, str(HERE / "hiccups_ref_cooltools.py"), path, str(prefix), str(max_sep)]
        if not pixels:
            cmd.append("--no-pixels")
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode:
            raise RuntimeError(r.stderr[-2000:])
        info = json.loads(r.stdout.strip().splitlines()[-1])
        meta.write_text(json.dumps(info))
    info["dots"] = pd.read_csv(f"{prefix}_dots.tsv", sep="\t")
    if pixels:
        info["pixels"] = pd.read_csv(f"{prefix}_pixels.tsv", sep="\t")
    return info


def _cd():
    from chromdata import ChromData

    return ChromData(np.zeros((0, 3)), pd.DataFrame({"chrom": pd.Series(dtype=str), "start": pd.Series(dtype=np.int64),
                                                     "end": pd.Series(dtype=np.int64),
                                                     "trace_id": pd.Series(dtype=str)}))


def _table(rows, title):
    print(f"\n== {title}")
    with pd.option_context("display.width", 250, "display.max_columns", 40):
        print(pd.DataFrame(rows).to_string(index=False, float_format=lambda v: f"{v:.4g}"))


# ------------------------------------------------------------------------------------------------ sections

def section_reference(maps, out, ref_python) -> list:
    import cooler

    from uchrom.strc.loop.hiccups import KERNELS, HiccupsParams, call_loops_hiccups, hiccups_pixels

    rows = []
    for cell in ("imr90", "gm12878"):
        for res in (5000, 10000, 25000):
            path = maps[(cell, res)]
            ct = cooltools_ref(ref_python, path, out / "hiccups_ref" / f"{cell}_{res // 1000}k_2mb", 2_000_000)
            clr = cooler.Cooler(path)
            params = HiccupsParams(pvalue="cooltools", max_dist=2_000_000)
            t = time.perf_counter()
            px, info = hiccups_pixels(clr, list(clr.chromnames), params)
            t_px = time.perf_counter() - t
            cp = ct["pixels"]
            a, b = set(zip(px["start1"], px["start2"])), set(zip(cp["start1"], cp["start2"]))
            m = px.merge(cp, on=["start1", "start2"])
            lam = max(float(np.max(np.abs(m[f"exp_{k}"] / m[f"la_exp.{k}.value"] - 1))) if len(m) else 0.0
                      for k in KERNELS)
            dq = np.max([np.abs(m[f"fdr_{k}"] - m[f"la_exp.{k}.qval"]).to_numpy() for k in KERNELS], axis=0) \
                if len(m) else np.zeros(1)
            row = {"cell": cell, "res": res, "tested": info["n_tested"], "pixels_ours": len(a), "pixels_ct": len(b),
                   "pixels_common": len(a & b), "lambda_max_rel_diff": lam, "q_max_abs_diff": float(dq.max()),
                   "q_n_diff_gt_1e-3": int((dq > 1e-3).sum())}
            cd = _cd()
            ctd = ct["dots"]
            for label, prm in (("loops", params),
                               ("loops_r10k", HiccupsParams(pvalue="cooltools", max_dist=2_000_000, cluster_radius=10_000)),
                               ("loops_default", HiccupsParams(max_dist=2_000_000))):
                t = time.perf_counter()
                loops = call_loops_hiccups(cd, contacts=path, params=prm, key_added=None)
                dt = time.perf_counter() - t
                same = len(set(zip(loops["start1"], loops["start2"])) & set(zip(ctd["start1"], ctd["start2"])))
                near_o = matched(loops.assign(end1=loops["start1"] + res, end2=loops["start2"] + res),
                                 ctd.assign(end1=ctd["start1"] + res, end2=ctd["start2"] + res), res)
                near_c = matched(ctd.assign(end1=ctd["start1"] + res, end2=ctd["start2"] + res),
                                 loops.assign(end1=loops["start1"] + res, end2=loops["start2"] + res), res)
                row.update({f"{label}_n": len(loops), f"{label}_same_summit": same,
                            f"{label}_within_1bin_of_ct": int(near_o.sum()), f"ct_within_1bin_of_{label}": int(near_c.sum()),
                            f"{label}_s": dt})
            row.update({"dots_ct_n": len(ctd), "pixels_ours_s": t_px, "pixels_ct_s": ct.get("pixels_s"),
                        "dots_ct_s": ct.get("dots_s")})
            rows.append(row)
    _table([{k: v for k, v in r.items() if not k.endswith("_s") or k in ("pixels_ours_s", "dots_ct_s", "loops_s")}
            for r in rows], "reference: cooltools dots on the same maps (loops up to 2 Mb)")
    return rows


def section_rao2014(maps, out, ref_python) -> list:
    from uchrom.strc.loop.hiccups import HiccupsParams, call_loops_hiccups

    rows = []
    for cell in ("imr90", "gm12878"):
        ref = published(cell)
        cd = _cd()
        runs = {f"{r // 1000}kb": [maps[(cell, r)]] for r in (5000, 10000, 25000)}
        runs["5+10kb"] = [maps[(cell, 5000)], maps[(cell, 10000)]]
        runs["5+10+25kb"] = [maps[(cell, r)] for r in (5000, 10000, 25000)]
        for label, paths in runs.items():
            for md in (2_000_000, 10_000_000):
                t = time.perf_counter()
                loops = call_loops_hiccups(cd, contacts=paths if len(paths) > 1 else paths[0],
                                           params=HiccupsParams(max_dist=md), key_added=None)
                row = {"cell": cell, "maps": label, "max_dist_mb": md // 1_000_000, "published": len(ref),
                       **scores(loops, ref), "s": time.perf_counter() - t}
                if len(paths) == 1:
                    res = int(label[:-2]) * 1000
                    reach = reachable(ref, res)
                    row["reachable"] = int(reach.sum())
                    row["recall_reachable"] = float(matched(ref[reach], loops).mean()) if reach.any() else np.nan
                rows.append(row)
        for r in (5000, 10000, 25000):
            ct = cooltools_ref(ref_python, maps[(cell, r)], out / "hiccups_ref" / f"{cell}_{r // 1000}k_2mb", 2_000_000)
            d = ct["dots"].assign(end1=lambda x: x["start1"] + r, end2=lambda x: x["start2"] + r)
            rows.append({"cell": cell, "maps": f"cooltools {r // 1000}kb", "max_dist_mb": 2, "published": len(ref),
                         **scores(d, ref)})
    _table(rows, f"rao2014: published HiCCUPS loops, chr21 (match: both anchor midpoints within {TOL // 1000} kb)")
    return rows


def section_depth(maps, out, ref_python) -> list:
    from uchrom.strc.loop.hiccups import HiccupsParams, call_loops_hiccups

    ref = published("imr90")
    cd = _cd()
    rows, full = [], {}
    for frac in DEPTHS:
        tag = "imr90" if frac == 1.0 else f"imr90_d{int(round(frac * 100))}"
        for label, res_list in (("10kb", [10000]), ("25kb", [25000]), ("10+25kb", [10000, 25000]),
                                ("5+10+25kb", [5000, 10000, 25000])):
            paths = [maps[(tag, r)] for r in res_list]
            t = time.perf_counter()
            loops = call_loops_hiccups(cd, contacts=paths if len(paths) > 1 else paths[0],
                                       params=HiccupsParams(), key_added=None)
            if frac == 1.0:
                full[label] = loops
            row = {"depth": frac, "maps": label, **scores(loops, ref),
                   "full_depth_recovered": float(matched(full[label], loops).mean()) if len(full[label]) else np.nan,
                   "s": time.perf_counter() - t}
            rows.append(row)
        for r in (10000, 25000):
            ct = cooltools_ref(ref_python, maps[(tag, r)], out / "hiccups_ref" / f"{tag}_{r // 1000}k_2mb", 2_000_000,
                               pixels=False)
            d = ct["dots"].assign(end1=lambda x: x["start1"] + r, end2=lambda x: x["start2"] + r)
            rows.append({"depth": frac, "maps": f"cooltools {r // 1000}kb", **scores(d, ref)})
    _table(rows, "depth: binomial thinning of IMR90 chr21 (published loops; full-depth calls of the same maps)")
    return rows


_CHILD = r"""
import json, resource, sys, time
from uchrom.strc.loop.hiccups import HiccupsParams, call_loops_hiccups
from chromdata import ChromData
import numpy as np, pandas as pd
cd = ChromData(np.zeros((0, 3)), pd.DataFrame({"chrom": pd.Series(dtype=str), "start": pd.Series(dtype=np.int64),
               "end": pd.Series(dtype=np.int64), "trace_id": pd.Series(dtype=str)}))
tm = {}
t = time.perf_counter()
loops = call_loops_hiccups(cd, contacts=sys.argv[1], params=HiccupsParams(max_dist=int(sys.argv[2])), key_added=None,
                           timing=tm)
tm["total_s"] = time.perf_counter() - t
tm["max_rss_gb"] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / (1e9 if sys.platform == "darwin" else 1e6)
loops.to_csv(sys.argv[3], sep="\t", index=False)
print(json.dumps(tm))
"""


def section_chr1(maps, out, ref_python) -> list:
    path = maps[("imr90_chr1", 5000)]
    ref = published("imr90", "1")
    rows = []
    for md in (2_000_000, 10_000_000):
        dst = out / "hiccups_ref" / f"ours_chr1_5k_{md // 1_000_000}mb.tsv"
        r = subprocess.run([sys.executable, "-c", _CHILD, path, str(md), str(dst)], capture_output=True, text=True)
        if r.returncode:
            raise RuntimeError(r.stderr[-2000:])
        tm = json.loads(r.stdout.strip().splitlines()[-1])
        loops = pd.read_csv(dst, sep="\t")
        rows.append({"tool": "uchrom", "max_dist_mb": md // 1_000_000, **tm, **scores(loops, ref)})
    ct = cooltools_ref(ref_python, path, out / "hiccups_ref" / "imr90_chr1_5k_2mb", 2_000_000, pixels=False)
    d = ct["dots"].assign(end1=lambda x: x["start1"] + 5000, end2=lambda x: x["start2"] + 5000)
    rows.append({"tool": "cooltools", "max_dist_mb": 2, "total_s": ct["dots_s"] + ct["expected_s"],
                 "max_rss_gb": ct["max_rss_gb"], **scores(d, ref)})
    _table(rows, "chr1 at 5 kb: run time (s) per step, peak memory (GB), published chr1 loops")
    return rows


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", type=Path, default=Path(tempfile.gettempdir()) / "uchrom_hic_structures")
    ap.add_argument("--ref-python", required=True, help="python of a venv with cooltools (reference only)")
    ap.add_argument("--only", default="reference,rao2014,depth,chr1")
    a = ap.parse_args(argv)
    a.out.mkdir(parents=True, exist_ok=True)
    (a.out / "hiccups_ref").mkdir(exist_ok=True)
    only = a.only.split(",")
    maps = prepare(a.out, chr1="chr1" in only, depth="depth" in only)
    path = a.out / "hiccups.json"
    res = json.loads(path.read_text()) if path.exists() else {}
    for name in only:
        t = time.time()
        res[name] = globals()[f"section_{name}"](maps, a.out, a.ref_python)
        print(f"[{name}: {time.time() - t:.0f} s]", flush=True)
        path.write_text(json.dumps(res, indent=1, default=lambda v: None if v is None else float(v)))
    print(f"\nwrote {path}")


if __name__ == "__main__":
    main()
