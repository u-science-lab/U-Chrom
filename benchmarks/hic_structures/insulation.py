"""Validation of ``uchrom.strc.tad.insulation`` (diamond insulation score, TAD boundaries and domains) on real
Hi-C.

Sections (each prints a table; all numbers go to ``OUT/insulation.json``):

``reference``  agreement with cooltools 0.7.1 ``insulation`` (scores, valid-pixel counts, boundary strengths,
               boundaries) on Rao 2014 IMR90 and GM12878 chr21 at 10 and 25 kb, windows of 3 / 5 / 10 / 25 bins;
``arrowhead``  boundaries against the edges of the authors' Arrowhead domains (Rao 2014, GSE63525; hg19, as
               the maps): recall / precision with a tolerance of 2 bins between an Arrowhead edge and the
               boundary bin, next to the chance level (as many boundaries at random scored bins, 200 draws);
               windows, Li vs Otsu; IMR90 chr21 + chr1, GM12878 chr21;
``di``         against the directionality-index caller (``call_tads_di``) on the same maps;
``arcfish``    against ArcFISH TAD boundaries from chromatin tracing of IMR90 chr21 (Su 2020,
               ``ds.load("su2020_chr21")``).  Imaging loci are hg38; the Hi-C is the authors' Rao 2014 map
               summed into the same hg38 loci (linked as ``rao2014``), so no liftover is needed —
               ``compare_boundaries`` on the loci (tolerance 1 locus);
``depth``      binomial thinning of the IMR90 chr21 5 kb counts to 20 / 5 / 2 % (atlas cell-type pseudo-bulk
               depths), rebinned to 10 / 25 kb and ICE-balanced: boundaries vs the full map and vs Arrowhead;
``chr1``       runtime / memory on IMR90 chr1 at 5 kb (49,851 bins, 26.5 M pixels) per step and window, and
               cooltools on the same map.

Run from the repository root::

    .venv/bin/python benchmarks/hic_structures/insulation.py --out SCRATCH/hic_structures \
        --ref-python SCRATCH/ct2/bin/python [--only reference,arrowhead,...]

Inputs (``uchrom.datasets``): ``rao2014_imr90_chr21`` (load), ``rao2014_imr90_chr1``,
``rao2014_gm12878_chr21``, ``rao2014_annotations`` (fetch), ``su2020_chr21`` (load).  Balanced maps and the
thinned maps are written to ``OUT/maps``.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
import tracemalloc
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

HERE = Path(__file__).resolve().parent
REF_SCRIPT = HERE / "insulation_ref_cooltools.py"
FACTORS = (3, 5, 10, 20, 25)        # windows, in bins
TOL_BINS = 2                        # Arrowhead tolerance
DEPTHS = (1.0, 0.2, 0.05, 0.02)


# ----------------------------------------------------------------------------------------------------------
# maps
# ----------------------------------------------------------------------------------------------------------

def _balanced(src: str, res: int, out: Path) -> str:
    """``src`` (a raw 5 kb .cool) summed to ``res`` and ICE-balanced (``rebin_map``), cached in ``out``."""
    from uchrom.fea.maps import rebin_map

    if out.exists():
        return str(out)
    return rebin_map(src, resolution=res, out=out)


def prepare(outdir: Path) -> dict:
    import uchrom.datasets as ds

    maps = outdir / "maps"
    maps.mkdir(parents=True, exist_ok=True)
    imr21 = ds.load("rao2014_imr90_chr21")
    src = {"IMR90 chr21": imr21.linked_cool_path("bulk"),
           "GM12878 chr21": str(ds.fetch("rao2014_gm12878_chr21")),
           "IMR90 chr1": str(ds.fetch("rao2014_imr90_chr1"))}
    out = {}
    for name, path in src.items():
        tag = name.replace(" ", "_").lower()
        for res in (5_000, 10_000, 25_000):
            t = time.time()
            out[(name, res)] = _balanced(path, res, maps / f"{tag}_{res // 1000}k.cool")
            print(f"  map {name} {res // 1000} kb: {time.time() - t:.1f} s", flush=True)
    out["raw IMR90 chr21"] = src["IMR90 chr21"]
    return out


def _arrowhead(cell: str, chrom: str) -> np.ndarray:
    import uchrom.datasets as ds

    folder = Path(ds.fetch("rao2014_annotations"))
    name = {"IMR90": "GSE63525_IMR90_Arrowhead_domainlist.txt.gz",
            "GM12878": "GSE63525_GM12878_primary+replicate_Arrowhead_domainlist.txt.gz"}[cell]
    path = next(folder.rglob(name)) if not (folder / name).exists() else folder / name
    dom = pd.read_csv(path, sep="\t")
    dom = dom[dom["chr1"].astype(str) == chrom.replace("chr", "")]
    return np.unique(np.r_[dom["x1"].to_numpy(), dom["x2"].to_numpy()]).astype(np.int64)


# ----------------------------------------------------------------------------------------------------------
# metrics
# ----------------------------------------------------------------------------------------------------------

def _dist(edges: np.ndarray, starts: np.ndarray, ends: np.ndarray) -> np.ndarray:
    """(len(edges), len(bins)) distance of a position to a bin interval (0 inside / on its edges)."""
    e = np.asarray(edges, dtype=np.int64)[:, None]
    return np.maximum(0, np.maximum(np.asarray(starts)[None, :] - e, e - np.asarray(ends)[None, :]))


def recall_precision(edges, starts, ends, tol) -> tuple:
    if len(edges) == 0 or len(starts) == 0:
        return float("nan"), float("nan")
    d = _dist(edges, starts, ends)
    return float((d.min(1) <= tol).mean()), float((d.min(0) <= tol).mean())


def chance(edges, scored_starts, res, n, tol, draws=200, seed=0) -> tuple:
    rng = np.random.default_rng(seed)
    rec, pre = [], []
    for _ in range(draws):
        s = np.sort(rng.choice(scored_starts, size=min(n, len(scored_starts)), replace=False))
        r, p = recall_precision(edges, s, s + res, tol)
        rec.append(r)
        pre.append(p)
    return float(np.mean(rec)), float(np.mean(pre))


def _bounds(table: pd.DataFrame, w: int) -> pd.DataFrame:
    return table.loc[table[f"is_boundary_{w}"].astype(bool), ["chrom", "start", "end"]]


def _scored(table: pd.DataFrame, w: int) -> np.ndarray:
    from uchrom.strc.tad.insulation import full_diamond

    nv = table[f"n_valid_pixels_{w}"].to_numpy()
    ok = np.isfinite(table[f"log2_insulation_score_{w}"].to_numpy()) & (nv >= 0.66 * nv.max())
    return table["start"].to_numpy()[ok]


def _ref(args, cool: str, windows, threshold="Li") -> tuple:
    """cooltools' table (subprocess in the reference venv) and its run time."""
    with tempfile.NamedTemporaryFile(suffix=".tsv", delete=False) as fh:
        out = fh.name
    cmd = [args.ref_python, str(REF_SCRIPT), cool, out, *map(str, windows), "--threshold", str(threshold)]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=args.ref_timeout)
    if r.returncode:
        raise RuntimeError(r.stderr[-2000:])
    table = pd.read_csv(out, sep="\t")
    os.unlink(out)
    return table, float(r.stdout.strip().splitlines()[-1])


# ----------------------------------------------------------------------------------------------------------
# sections
# ----------------------------------------------------------------------------------------------------------

def section_reference(args, maps) -> list:
    from uchrom.strc.tad.insulation import insulation_score

    rows = []
    for name in ("IMR90 chr21", "GM12878 chr21"):
        for res in (10_000, 25_000):
            cool = maps[(name, res)]
            windows = [f * res for f in FACTORS]
            t = time.time()
            mine = insulation_score(cool, windows=windows)
            t_mine = time.time() - t
            ref, t_ref = _ref(args, cool, windows)
            assert (mine["start"].to_numpy() == ref["start"].to_numpy()).all()
            for w in windows:
                a, b = mine[f"log2_insulation_score_{w}"].to_numpy(), ref[f"log2_insulation_score_{w}"].to_numpy()
                fin = np.isfinite(a) & np.isfinite(b)
                sa, sb = mine[f"boundary_strength_{w}"].to_numpy(), ref[f"boundary_strength_{w}"].to_numpy()
                ba, bb = mine[f"is_boundary_{w}"].to_numpy(bool), ref[f"is_boundary_{w}"].to_numpy(bool)
                rows.append({"map": name, "res_kb": res // 1000, "window_kb": w // 1000,
                             "nan_mask_identical": bool((np.isfinite(a) == np.isfinite(b)).all()),
                             "max_abs_diff_log2": float(np.abs(a[fin] - b[fin]).max()),
                             "n_valid_identical": bool((mine[f"n_valid_pixels_{w}"].to_numpy()
                                                        == ref[f"n_valid_pixels_{w}"].to_numpy()).all()),
                             "minima": int(np.isfinite(sa).sum()), "minima_ref": int(np.isfinite(sb).sum()),
                             "max_abs_diff_strength": float(np.nanmax(np.abs(sa - sb))),
                             "boundaries": int(ba.sum()), "boundaries_ref": int(bb.sum()),
                             "boundaries_differ": int((ba != bb).sum()),
                             "seconds": round(t_mine, 3), "seconds_ref": round(t_ref, 3)})
    # Otsu, one map
    cool = maps[("IMR90 chr21", 25_000)]
    from uchrom.strc.tad.insulation import InsulationParams

    w = 10 * 25_000
    mine = insulation_score(cool, windows=[w], params=InsulationParams(threshold="otsu"))
    ref, _ = _ref(args, cool, [w], threshold="Otsu")
    rows.append({"map": "IMR90 chr21 (Otsu)", "res_kb": 25, "window_kb": w // 1000,
                 "boundaries": int(mine[f"is_boundary_{w}"].sum()),
                 "boundaries_ref": int(ref[f"is_boundary_{w}"].sum()),
                 "boundaries_differ": int((mine[f"is_boundary_{w}"].to_numpy(bool)
                                           != ref[f"is_boundary_{w}"].to_numpy(bool)).sum())})
    return rows


def section_arrowhead(args, maps) -> list:
    from uchrom.strc.tad.insulation import DEFAULT_WINDOW_BP, InsulationParams, insulation_score

    rows = []
    for name in ("IMR90 chr21", "GM12878 chr21", "IMR90 chr1"):
        cell, chrom = name.split()
        edges = _arrowhead(cell, chrom)
        for res in (5_000, 10_000, 25_000):
            cool = maps[(name, res)]
            windows = sorted({f * res for f in FACTORS} | {DEFAULT_WINDOW_BP})
            for rule in ("li", "otsu"):
                table = insulation_score(cool, windows=windows, params=InsulationParams(threshold=rule))
                for w in windows:
                    b = _bounds(table, w)
                    tol = TOL_BINS * res
                    st, en = b["start"].to_numpy(), b["end"].to_numpy()
                    rec, pre = recall_precision(edges, st, en, tol)
                    rec20, pre20 = recall_precision(edges, st, en, 20_000)
                    crec, cpre = chance(edges, _scored(table, w), res, len(b), tol)
                    rows.append({"map": name, "res_kb": res // 1000, "window_kb": w // 1000, "threshold": rule,
                                 "arrowhead_edges": int(len(edges)), "boundaries": int(len(b)),
                                 "recall": rec, "precision": pre, "chance_recall": crec,
                                 "chance_precision": cpre, "recall_tol20kb": rec20, "precision_tol20kb": pre20})
    return rows


def _di_bounds(table: pd.DataFrame, bins: pd.DataFrame) -> pd.DataFrame:
    """Boundary bins of a DI domain table: the first bin of every domain but the first."""
    k = table["start_bin"].to_numpy()[1:]
    return bins.iloc[k][["start", "end"]]


def section_di(args, maps) -> list:
    """DI with the tutorial's settings (smoothing / minimum size as fractions of the chromosome's bins) and
    with bin-scale settings (window 20 bins, smoothing 3 bins, minimum domain 5 bins — the best of a small
    grid against the same Arrowhead edges, so an optimistic DI)."""
    import cooler
    import uchrom.datasets as ds
    from uchrom.strc.tad import DICallerParams, call_tads_di
    from uchrom.strc.tad.insulation import call_tads_insulation

    rows = []
    for name in ("IMR90 chr21", "GM12878 chr21", "IMR90 chr1"):
        cell, chrom = name.split()
        edges = _arrowhead(cell, chrom)
        cd = ds.load("rao2014_imr90_chr21")
        for res in (10_000, 25_000):
            cool = maps[(name, res)]
            key = f"m{res}"
            cd.link_cool(cool, key=key)
            bins = cooler.Cooler(cool).bins().fetch(chrom).reset_index(drop=True)
            n = len(bins)
            tol = TOL_BINS * res
            t = time.time()
            call_tads_insulation(cd, contacts=key, chrom=chrom, key_added="ins")          # defaults
            t_ins = time.time() - t
            ib = cd.results["ins.boundaries"]
            r_in, p_in = recall_precision(edges, ib["start"].to_numpy(), ib["end"].to_numpy(), tol)
            rows.append({"map": name, "res_kb": res // 1000, "caller": "insulation (default 100 kb)",
                         "boundaries": int(len(ib)), "recall": r_in, "precision": p_in,
                         "seconds": round(t_ins, 2)})
            if n > 12_000:            # call_tads_di reads a dense matrix: chr1 at 10 kb would be 5 GB
                continue
            settings = {"DI, tutorial (10 bins, fractions .01 / .005)":
                        DICallerParams(window=10, smoothing_param=0.01, min_size_frac=0.005),
                        "DI, bin-scale (20 / 3 / 5 bins)":
                        DICallerParams(window=20, smoothing_param=3 / n, min_size_frac=5 / n)}
            for label, p in settings.items():
                t = time.time()
                di = call_tads_di(cd, contacts=key, chrom=chrom, device="cpu", key_added=None, params=p)
                t_di = time.time() - t
                dib = _di_bounds(di, bins)
                r_di, p_di = recall_precision(edges, dib["start"].to_numpy(), dib["end"].to_numpy(), tol)
                d = _dist(ib["start"].to_numpy(), dib["start"].to_numpy(), dib["end"].to_numpy())
                rows.append({"map": name, "res_kb": res // 1000, "caller": label, "boundaries": int(len(dib)),
                             "recall": r_di, "precision": p_di,
                             "insulation_near_di": float((d.min(1) <= tol).mean()) if d.size else float("nan"),
                             "di_near_insulation": float((d.min(0) <= tol).mean()) if d.size else float("nan"),
                             "seconds": round(t_di, 2)})
    return rows


def section_arcfish(args, maps) -> list:
    import uchrom.datasets as ds
    from uchrom.strc.tad import (DICallerParams, TADCallerParams, call_tads_by_pval, call_tads_di,
                                 compare_boundaries, tad_boundaries)
    from uchrom.strc.tad.insulation import InsulationParams, call_tads_insulation

    su = ds.load("su2020_chr21")
    t = time.time()
    arc = call_tads_by_pval(su, params=TADCallerParams(window_bp=2e5, hierarchical=False), key_added="arcfish")
    t_arc = time.time() - t
    calls = {"DI (10 loci)": call_tads_di(su, contacts="rao2014", device="cpu", key_added="di",
                                          params=DICallerParams(window=10, smoothing_param=0.01,
                                                                min_size_frac=0.005))}
    for w in (3, 5, 10):
        calls[f"insulation ({w} loci)"] = call_tads_insulation(
            su, contacts="rao2014", params=InsulationParams(window_bp=w * 50_000), key_added=f"ins{w}")
    rows = []
    n_arc = len(tad_boundaries(su, arc))
    for name, table in calls.items():
        q = compare_boundaries(su, table, arc, tol=1)
        r = compare_boundaries(su, arc, table, tol=1)
        rows.append({"call": name, "boundaries": q["n_query"], "arcfish_boundaries": n_arc,
                     "frac_near_arcfish": q["fraction_near"], "chance": q["chance"],
                     "enrichment": q["enrichment"], "arcfish_recovered": r["fraction_near"],
                     "arcfish_chance": r["chance"]})
    rows.append({"call": "ArcFISH (imaging)", "boundaries": n_arc, "seconds": round(t_arc, 1)})
    return rows


def section_depth(args, maps) -> list:
    import cooler
    from uchrom.fea.maps import rebin_map
    from uchrom.strc.tad.insulation import insulation_score

    outdir = Path(args.out) / "maps"
    raw = cooler.Cooler(maps["raw IMR90 chr21"])
    bins = raw.bins()[:][["chrom", "start", "end"]]
    px = raw.pixels()[:]
    edges = _arrowhead("IMR90", "chr21")
    rng = np.random.default_rng(0)
    full, rows = {}, []
    for frac in DEPTHS:
        tag = f"{frac * 100:g}"
        f5 = outdir / f"imr90_chr21_thin{tag}_5k.cool"
        if not f5.exists():
            p = px.copy()
            if frac < 1:
                p["count"] = rng.binomial(p["count"].to_numpy(), frac)
                p = p[p["count"] > 0]
            cooler.create_cooler(str(f5), bins, p, ordered=True, assembly="hg19")
        n = int(cooler.Cooler(str(f5)).info["sum"])
        for res in (10_000, 25_000):
            cool = outdir / f"imr90_chr21_thin{tag}_{res // 1000}k.cool"
            if not cool.exists():
                rebin_map(str(f5), resolution=res, out=cool)
            windows = [100_000, 250_000]                     # the default; 10 bins at 25 kb
            table = insulation_score(str(cool), windows=windows)
            for w in windows:
                b = _bounds(table, w)
                s = table[f"log2_insulation_score_{w}"].to_numpy()
                if frac == 1.0:
                    full[(res, w)] = (b, s)
                fb, fs = full[(res, w)]
                ok = np.isfinite(s) & np.isfinite(fs)
                rf, pf = recall_precision(fb["start"].to_numpy(), b["start"].to_numpy(), b["end"].to_numpy(), res)
                ra, pa = recall_precision(edges, b["start"].to_numpy(), b["end"].to_numpy(), TOL_BINS * res)
                rows.append({"depth": frac, "contacts_M": round(n / 1e6, 2), "res_kb": res // 1000,
                             "window_kb": w // 1000, "boundaries": int(len(b)),
                             "full_depth_recovered": rf, "precision_vs_full": pf,
                             "arrowhead_recall": ra, "arrowhead_precision": pa,
                             "pearson_r_log2_vs_full": float(np.corrcoef(s[ok], fs[ok])[0, 1]),
                             "scored_bins": int(np.isfinite(s).sum())})
            if frac == min(DEPTHS) and args.ref_python and res == 25_000:
                ref, _ = _ref(args, str(cool), windows)
                for w in windows:
                    a, r = table[f"is_boundary_{w}"].to_numpy(bool), ref[f"is_boundary_{w}"].to_numpy(bool)
                    rows.append({"depth": frac, "res_kb": res // 1000, "window_kb": w // 1000,
                                 "boundaries": int(a.sum()), "cooltools_boundaries": int(r.sum()),
                                 "differ_from_cooltools": int((a != r).sum())})
    return rows


def section_chr1(args, maps) -> list:
    import cooler
    from uchrom.fea.band import read_band
    from uchrom.strc.tad.insulation import (CHUNK, InsulationParams, _ignore_diags, _log2_score, boundary_strength,
                                            diamond_sums, full_diamond, n_valid_pixels, threshold_li)

    cool = maps[("IMR90 chr1", 5_000)]
    clr = cooler.Cooler(cool)
    ig = _ignore_diags(clr, InsulationParams())
    rows = []
    for w in (5, 10, 20, 50, 100, 200):
        tracemalloc.start()
        t0 = time.perf_counter()
        band = read_band(clr, chrom="chr1", max_dist=2 * (w - 1) * 5_000, chunk=CHUNK)
        t1 = time.perf_counter()
        v = band.values(True)
        nv = n_valid_pixels(band.valid, w, ig)
        t2 = time.perf_counter()
        sums, nnz = diamond_sums(band.i, band.j, v, band.n, w, ig)
        t3 = time.perf_counter()
        log2 = _log2_score(sums, nnz, nv, "mean")
        usable = nv >= 0.66 * full_diamond(w, ig)
        s = np.full(band.n, np.nan)
        s[usable] = boundary_strength(log2[usable])
        t4 = time.perf_counter()
        thr = threshold_li(s)
        t5 = time.perf_counter()
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        rows.append({"window_kb": w * 5, "window_bins": w, "band_pixels_M": round(len(band.i) / 1e6, 2),
                     "read_band_s": round(t1 - t0, 3), "values_n_valid_s": round(t2 - t1, 3),
                     "diamond_sums_s": round(t3 - t2, 3), "log2_strength_s": round(t4 - t3, 3),
                     "threshold_s": round(t5 - t4, 3), "total_s": round(t5 - t0, 3),
                     "peak_traced_MB": round(peak / 1e6, 1), "boundaries": int((s >= thr).sum())})
        del band, v, sums
    # one call, fresh process: wall time and peak resident memory
    code = ("import resource, sys, time; from uchrom.strc.tad.insulation import call_tads_insulation, "
            "insulation_score; t = time.perf_counter(); "
            f"d = call_tads_insulation({cool!r}); t1 = time.perf_counter() - t; t = time.perf_counter(); "
            f"insulation_score({cool!r}, windows=[25_000, 50_000, 100_000, 250_000, 500_000, 1_000_000]); "
            "t2 = time.perf_counter() - t; r = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss; "
            "print(t1, t2, len(d), r / (1e6 if sys.platform == 'darwin' else 1e3))")
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True).stdout.split()
    rows.append({"window_kb": "100 (call_tads_insulation, defaults)", "total_s": round(float(out[0]), 3),
                 "domains": int(out[2]), "max_rss_MB": round(float(out[3]), 1)})
    rows.append({"window_kb": "25,50,100,250,500,1000 (one insulation_score call)",
                 "total_s": round(float(out[1]), 3)})
    if args.ref_python:
        for w in (25_000, 50_000, 100_000):
            try:
                _, t_ref = _ref(args, cool, [w])
                rows.append({"window_kb": w // 1000, "cooltools_s": round(t_ref, 2)})
            except subprocess.TimeoutExpired:
                rows.append({"window_kb": w // 1000, "cooltools_s": f">{args.ref_timeout}"})
    return rows


SECTIONS = {"reference": section_reference, "arrowhead": section_arrowhead, "di": section_di,
            "arcfish": section_arcfish, "depth": section_depth, "chr1": section_chr1}


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", default=os.environ.get("HIC_BENCH_OUT",
                                                    str(Path(tempfile.gettempdir()) / "hic_structures")))
    ap.add_argument("--ref-python", default=os.environ.get("COOLTOOLS_PYTHON"),
                    help="python of an environment with cooltools (reference comparisons; skipped without)")
    ap.add_argument("--ref-timeout", type=int, default=1800)
    ap.add_argument("--only", default=",".join(SECTIONS))
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    pd.set_option("display.width", 250)
    pd.set_option("display.max_columns", 30)
    print("preparing maps", flush=True)
    maps = prepare(out)
    path = out / "insulation.json"
    results = json.loads(path.read_text()) if path.exists() else {}
    for name in args.only.split(","):
        if name == "reference" and not args.ref_python:
            print("reference: skipped (no --ref-python)")
            continue
        t = time.time()
        rows = SECTIONS[name](args, maps)
        results[name] = rows
        print(f"\n== {name} ({time.time() - t:.0f} s)")
        print(pd.DataFrame(rows).to_string(index=False, float_format=lambda x: f"{x:.4g}"), flush=True)
        path.write_text(json.dumps(results, indent=1, default=float))
    print(f"\nwritten: {path}")


if __name__ == "__main__":
    main()
