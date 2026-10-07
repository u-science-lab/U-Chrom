"""Validation of ``uchrom.strc.loop.call_loops_mustache`` (Mustache, Roayaei Ardakany et al. 2020) on real Hi-C.

1. **Kernel identity** — the reference's own kernels (``mustache-hic`` 1.3.3, run in a separate venv by
   ``mustache_reference_blocks.py``) on the same pixels: the normalised values, and the calls of every
   reference block (10-Mb / 20-Mb blocks of the reference) against ours on the same block.
2. **Reference agreement on whole chromosomes** (IMR90 and GM12878 chr21 at 5 and 10 kb): the reference
   (= its command line; the block runner reproduces it exactly) against ours (chromosome-wide statistics):
   calls of each, shared exactly / within 1 / 2 bins.
3. **Published loops**: recall / precision against the Rao 2014 HiCCUPS lists (GEO GSE63525), anchors within
   25 kb (``uchrom.strc.loop.match_loops`` on anchor starts); recall also over the HiCCUPS loops shorter than
   Mustache's 2-Mb limit.
4. **Depth**: binomial thinning of the IMR90 chr21 counts to 20 / 5 / 2 % (seeded), balanced again, at 5, 10
   and 25 kb.
5. **chr1 at 5 kb** (IMR90, the largest chromosome): runtime, peak memory and a profile, ours and the
   reference; recall / precision there too.

Data: ``uchrom.datasets`` (``rao2014_imr90_chr21``, ``rao2014_gm12878_chr21``, ``rao2014_imr90_chr1``,
``rao2014_annotations``).  Maps are copied and ICE-balanced (``cooler balance --cis-only`` defaults) into
``--out``; results go to ``--out/mustache_validate.json`` (not into the repository).

    python benchmarks/hic_structures/mustache_validate.py --out DIR --ref-python CTENV/bin/python \
        [--sections chr21,depth,chr1]
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
warnings.filterwarnings("ignore")


# ----------------------------------------------------------------------------------------------------------
# maps
# ----------------------------------------------------------------------------------------------------------

def _balance(path):
    import cooler

    cooler.balance_cooler(cooler.Cooler(str(path)), store=True, cis_only=True)


def balanced(src, out: Path, name: str, coarse=(10_000,)):
    """``{name}_5kb.cool`` (a balanced copy of ``src``) and, per ``coarse`` resolution, ``{name}_<res>kb.cool``
    (summed from the 5 kb map, balanced)."""
    import cooler

    f5 = out / f"{name}_5kb.cool"
    if not f5.exists():
        shutil.copy(src, f"{f5}.tmp")
        _balance(f"{f5}.tmp")
        os.replace(f"{f5}.tmp", f5)
    files = {5000: str(f5)}
    for res in coarse:
        f = out / f"{name}_{res // 1000}kb.cool"
        if not f.exists():
            cooler.coarsen_cooler(str(f5), f"{f}.tmp", factor=res // 5000, chunksize=10_000_000)
            _balance(f"{f}.tmp")
            os.replace(f"{f}.tmp", f)
        files[res] = str(f)
    return files


def thinned(src, out: Path, name: str, frac: float, seed: int = 0, coarse=(10_000,)):
    """Binomial thinning of the raw counts of ``src`` to ``frac``, then :func:`balanced`."""
    import cooler

    raw = out / f"{name}_raw.cool"
    if not raw.exists():
        clr = cooler.Cooler(str(src))
        px = clr.pixels()[:]
        px["count"] = np.random.default_rng(seed).binomial(px["count"].to_numpy(), frac)
        px = px[px["count"] > 0]
        cooler.create_cooler(f"{raw}.tmp", clr.bins()[:][["chrom", "start", "end"]], px, ordered=True)
        os.replace(f"{raw}.tmp", raw)
    return balanced(raw, out, name, coarse)


def hiccups(cell: str, chrom: str) -> pd.DataFrame:
    import uchrom.datasets as ds

    root = ds.fetch("rao2014_annotations", verbose=False)
    name = {"IMR90": "GSE63525_IMR90_HiCCUPS_looplist.txt.gz",
            "GM12878": "GSE63525_GM12878_primary+replicate_HiCCUPS_looplist.txt.gz"}[cell]
    t = pd.read_csv(Path(root) / name, sep="\t")
    t = t[t["chr1"].astype(str) == chrom.replace("chr", "")]
    return pd.DataFrame({"chrom1": chrom, "start1": t["x1"].to_numpy(), "start2": t["y1"].to_numpy(),
                         "end2": t["y2"].to_numpy()}).reset_index(drop=True)


# ----------------------------------------------------------------------------------------------------------
# runs
# ----------------------------------------------------------------------------------------------------------

def reference_pixels(cool: str, chrom: str):
    """The balanced pixels the reference reads: ``|x - y| <= D``, value > 0 (NaN -> dropped)."""
    import cooler

    from uchrom.fea.band import read_band
    from uchrom.strc.loop.mustache import default_max_dist

    clr = cooler.Cooler(cool)
    res = int(clr.binsize)
    D = default_max_dist(res) // res
    band = read_band(clr, chrom=chrom, max_dist=D * res)
    v = band.values()
    keep = np.isfinite(v) & (v > 0)
    return band.i[keep], band.j[keep], v[keep], res, D, band.n


def run_reference(cool: str, chrom: str, work: Path, ref_python: str, tag: str):
    from uchrom.strc.loop.mustache import MustacheParams

    p = MustacheParams()
    x, y, v, res, D, n = reference_pixels(cool, chrom)
    src, dst = work / f"{tag}_px.npz", work / f"{tag}_ref.npz"
    np.savez(src, x=x, y=y, v=v, res=res, D=D, pt=p.fdr, st=p.sparsity, sigma0=p.sigma0, octaves=p.octaves)
    t = time.perf_counter()
    subprocess.run([ref_python, str(HERE / "mustache_reference_blocks.py"), str(src), str(dst)], check=True,
                   capture_output=True)
    sec = time.perf_counter() - t
    r = dict(np.load(dst))
    calls = pd.DataFrame({"chrom1": chrom, "start1": (r["calls"][:, 0] * res).astype(np.int64),
                          "start2": (r["calls"][:, 1] * res).astype(np.int64), "fdr": r["calls"][:, 2],
                          "summit_i": r["calls"][:, 0].astype(np.int64),
                          "summit_j": r["calls"][:, 1].astype(np.int64)}).drop_duplicates(["summit_i", "summit_j"])
    os.remove(src)
    return calls.reset_index(drop=True), sec, r, (x, y, v, res, D, n)


def run_ours(cool: str, chrom: str, **kw):
    from uchrom.strc.loop.mustache import call_loops_mustache

    t = time.perf_counter()
    calls = call_loops_mustache(cool, chrom=chrom, key_added=None, **kw)
    return calls, time.perf_counter() - t


def kernel_identity(r: dict, pix) -> dict:
    """Our normalisation and per-block calls against the reference's on its own blocks."""
    from uchrom.strc.loop.mustache import MustacheParams, _detect, _normalize

    x, y, v, res, D, n = pix
    p = MustacheParams()
    z = _normalize(x, y, v, n, D, res, p)
    diff = float(np.abs(z - r["z"]).max())
    bc = r["block_calls"]
    same = mine = ref = near1 = 0
    for b, (s, e) in enumerate(zip(r["starts"], r["ends"])):
        sel = (x >= s) & (x < e) & (y >= s) & (y < e)
        m = int(r["chunk"])
        ours = _detect("c", np.arange(m) * res, res, x[sel] - s, y[sel] - s, r["z"][sel], p, D=D)
        A = set(zip(ours["summit_i"] + s, ours["summit_j"] + s))
        B = {(int(a), int(c)) for a, c in bc[bc[:, 0] == b][:, 1:3]}
        mine, ref, same = mine + len(A), ref + len(B), same + len(A & B)
        near1 += sum(any(max(abs(a - a2), abs(c - c2)) <= 3 for a2, c2 in A) for a, c in B)
    return {"normalised_max_abs_diff": diff, "normalised_max_rel_diff": diff / float(np.abs(r["z"]).max()),
            "blocks": len(r["starts"]), "block_calls_ours": mine, "block_calls_reference": ref,
            "block_calls_identical": same, "block_calls_reference_within_3_px": near1}


def near(a: pd.DataFrame, b: pd.DataFrame, tol_bins: int) -> float:
    """Share of the loops of ``a`` with a loop of ``b`` within ``tol_bins`` (Chebyshev, summit bins)."""
    if len(a) == 0:
        return float("nan")
    if len(b) == 0:
        return 0.0
    A, B = np.c_[a["summit_i"], a["summit_j"]], np.c_[b["summit_i"], b["summit_j"]]
    d = np.maximum(np.abs(A[:, None, 0] - B[None, :, 0]), np.abs(A[:, None, 1] - B[None, :, 1]))
    return float((d.min(1) <= tol_bins).mean())


def vs_hiccups(calls: pd.DataFrame, ref: pd.DataFrame, tol: int = 25_000, max_dist: int = 2_000_000) -> dict:
    from uchrom.strc.loop import match_loops

    if len(calls) == 0:
        return {"n": 0, "recall": 0.0, "recall_le_2mb": 0.0, "precision": float("nan")}
    found = match_loops(ref, calls, tol=tol)
    short = (ref["start2"] - ref["start1"]) <= max_dist
    prec = match_loops(calls, ref, tol=tol).mean()
    return {"n": int(len(calls)), "recall": float(found.mean()), "recall_le_2mb": float(found[short].mean()),
            "precision": float(prec)}


# ----------------------------------------------------------------------------------------------------------
# chr1 profile (own process: clean peak memory)
# ----------------------------------------------------------------------------------------------------------

def profile_chr1(cool: str, tile: int) -> dict:
    import cProfile
    import pstats
    import resource

    import cooler

    from uchrom.fea.band import read_band
    from uchrom.strc.loop import mustache as mm

    def rss():
        r = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        return r / 2 ** 20 if sys.platform == "darwin" else r / 2 ** 10      # MB

    clr = cooler.Cooler(cool)
    chrom = clr.chromnames[0]
    res = int(clr.binsize)
    p = mm.MustacheParams()
    D = mm.default_max_dist(res) // res
    base = rss()
    out = {"chrom": chrom, "resolution": res, "tile": tile}
    t0 = time.perf_counter()
    band = read_band(clr, chrom=chrom, max_dist=D * res)
    v = band.values()
    keep = np.isfinite(v) & (v > 0)
    x, y, v, starts = band.i[keep], band.j[keep], v[keep], band.starts
    out["n_bins"], out["n_pixels"] = int(band.n), int(len(x))
    del band, keep
    out["peak_rss_after_read_mb"] = rss()
    t1 = time.perf_counter()
    z = mm._normalize(x, y, v, len(starts), D, res, p)
    t2 = time.perf_counter()
    out["peak_rss_after_normalise_mb"] = rss()
    prof = cProfile.Profile()
    prof.enable()
    calls = mm._detect(chrom, starts, res, x, y, z, p, D=D, tile=tile, verbose=True)
    prof.disable()
    t3 = time.perf_counter()
    st = pstats.Stats(prof)
    by = {}
    for (fname, line, func), (cc, nc, tt, ct, callers) in st.stats.items():
        by[func] = by.get(func, 0.0) + tt
    top = sorted(by.items(), key=lambda kv: -kv[1])[:12]
    out.update({"seconds_read": t1 - t0, "seconds_normalise": t2 - t1, "seconds_detect": t3 - t2,
                "seconds_total": t3 - t0, "peak_rss_mb": rss(), "rss_before_mb": base,
                "self_time_by_function_s": {k: round(v, 2) for k, v in top}, "n_calls": int(len(calls))})
    calls.to_csv(Path(cool).with_suffix(".ours.tsv"), sep="\t", index=False)
    return out


# ----------------------------------------------------------------------------------------------------------
# main
# ----------------------------------------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", required=True, help="work / output directory (scratch, not the repository)")
    ap.add_argument("--ref-python", default=os.environ.get("MUSTACHE_PYTHON"),
                    help="python of a venv with mustache-hic 1.3.3 (reference runs skipped without it)")
    ap.add_argument("--sections", default="chr21,depth,chr1", help="comma-separated: chr21, depth, chr1")
    ap.add_argument("--profile-chr1", help=argparse.SUPPRESS)
    ap.add_argument("--tile", type=int, default=256)
    args = ap.parse_args()
    if args.profile_chr1:
        print(json.dumps(profile_chr1(args.profile_chr1, args.tile)))
        return

    import uchrom.datasets as ds

    sections = set(args.sections.split(","))
    out = Path(args.out)
    maps = out / "maps"
    maps.mkdir(parents=True, exist_ok=True)
    ref_py = args.ref_python
    dst = out / "mustache_validate.json"
    results = json.loads(dst.read_text()) if dst.exists() else {}
    results["reference"] = "mustache-hic 1.3.3 (defaults: -pt 0.1, -st 0.88, -sz 1.6, -oc 2, 2 Mb)"
    pd.set_option("display.width", 250)

    cells = {"IMR90": ds.fetch("rao2014_imr90_chr21", verbose=False),
             "GM12878": ds.fetch("rao2014_gm12878_chr21", verbose=False)}
    full = {c: balanced(src, maps, f"{c.lower()}_chr21") for c, src in cells.items()}
    keep_calls = {}

    def full_calls(cell, res, who):
        if (cell, res, who) not in keep_calls:
            cool = full[cell][res]
            keep_calls[(cell, res, who)] = run_ours(cool, "chr21")[0] if who == "ours" else \
                run_reference(cool, "chr21", out, ref_py, f"{cell}_chr21_{res // 1000}kb")[0]
        return keep_calls[(cell, res, who)]

    # 1-3: kernel identity, agreement, published loops
    if "chr21" in sections:
        rows, ident = [], {}
        for cell, files in full.items():
            hl = hiccups(cell, "chr21")
            for res, cool in files.items():
                tag = f"{cell}_chr21_{res // 1000}kb"
                ours, sec = run_ours(cool, "chr21")
                keep_calls[(cell, res, "ours")] = ours
                row = {"map": tag, "ours_n": len(ours), "ours_s": round(sec, 1)}
                h = vs_hiccups(ours, hl)
                row.update({"ours_recall": h["recall"], "ours_recall_le2mb": h["recall_le_2mb"],
                            "ours_precision": h["precision"]})
                if ref_py:
                    ref, rsec, r, pix = run_reference(cool, "chr21", out, ref_py, tag)
                    keep_calls[(cell, res, "ref")] = ref
                    ident[tag] = kernel_identity(r, pix)
                    hr = vs_hiccups(ref, hl)
                    row.update({"ref_n": len(ref), "ref_s": round(rsec, 1), "ref_recall": hr["recall"],
                                "ref_recall_le2mb": hr["recall_le_2mb"], "ref_precision": hr["precision"],
                                "ours_in_ref_exact": near(ours, ref, 0), "ref_in_ours_exact": near(ref, ours, 0),
                                "ours_in_ref_1bin": near(ours, ref, 1), "ref_in_ours_1bin": near(ref, ours, 1),
                                "ours_in_ref_2bin": near(ours, ref, 2), "ref_in_ours_2bin": near(ref, ours, 2)})
                row["hiccups_n"] = len(hl)
                rows.append(row)
                print(row, flush=True)
        results["chr21"] = rows
        results["kernel_identity"] = ident
        print("\nchr21: ours vs reference vs Rao 2014 HiCCUPS (tolerance 25 kb)")
        print(pd.DataFrame(rows).set_index("map").round(3).T.to_string())
        if ident:
            print("\nkernel identity (reference kernels on the reference's own blocks)")
            print(pd.DataFrame(ident).T.to_string())

    # 4: depth thinning (IMR90 chr21)
    if "depth" in sections:
        from uchrom.strc.loop.mustache import MustacheParams

        hl = hiccups("IMR90", "chr21")
        full["IMR90"] = balanced(cells["IMR90"], maps, "imr90_chr21", (10_000, 25_000))
        drows = []
        for frac in (1.0, 0.2, 0.05, 0.02):
            files = full["IMR90"] if frac == 1.0 else \
                thinned(cells["IMR90"], maps, f"imr90_chr21_d{int(frac * 100)}", frac, coarse=(10_000, 25_000))
            for res, cool in files.items():
                row = {"fraction": frac, "res_kb": res // 1000}
                ours = full_calls("IMR90", res, "ours") if frac == 1.0 else run_ours(cool, "chr21")[0]
                h = vs_hiccups(ours, hl)
                row.update({"ours_n": h["n"], "ours_recall": h["recall"], "ours_precision": h["precision"],
                            "ours_vs_full": near(full_calls("IMR90", res, "ours"), ours, 2)})
                if frac < 1.0:
                    relaxed = run_ours(cool, "chr21", params=MustacheParams(sparsity=0.8))[0]
                    hx = vs_hiccups(relaxed, hl)
                    row.update({"ours_st0.8_n": hx["n"], "ours_st0.8_recall": hx["recall"],
                                "ours_st0.8_precision": hx["precision"]})
                if ref_py:
                    ref = full_calls("IMR90", res, "ref") if frac == 1.0 else \
                        run_reference(cool, "chr21", out, ref_py, f"thin{frac}_{res}")[0]
                    hr = vs_hiccups(ref, hl)
                    row.update({"ref_n": hr["n"], "ref_recall": hr["recall"], "ref_precision": hr["precision"],
                                "ref_in_ours_2bin": near(ref, ours, 2)})
                drows.append(row)
                print(row, flush=True)
        results["depth"] = drows
        print("\ndepth thinning, IMR90 chr21 (recall / precision vs HiCCUPS, 25 kb; ours_vs_full: share of the "
              "full-depth calls recovered within 2 bins)")
        print(pd.DataFrame(drows).round(3).to_string(index=False))

    # 5: chr1 at 5 kb
    if "chr1" in sections:
        src = ds.fetch("rao2014_imr90_chr1", verbose=False)
        f5 = maps / "imr90_chr1_5kb.cool"
        if not f5.exists():
            shutil.copy(src, f"{f5}.tmp")
            _balance(f"{f5}.tmp")
            os.replace(f"{f5}.tmp", f5)
        prof = subprocess.run([sys.executable, __file__, "--out", str(out), "--profile-chr1", str(f5),
                               "--tile", str(args.tile)], check=True, capture_output=True, text=True)
        rec = json.loads(prof.stdout.strip().splitlines()[-1])
        ours = pd.read_csv(f5.with_suffix(".ours.tsv"), sep="\t")
        h1 = hiccups("IMR90", "chr1")
        rec["ours_vs_hiccups"] = vs_hiccups(ours, h1)
        rec["hiccups_n"] = len(h1)
        if ref_py:
            ref, rsec, r, pix = run_reference(str(f5), "chr1", out, ref_py, "IMR90_chr1_5kb")
            rec["reference_n"] = int(len(ref))
            rec["reference_seconds_single_process"] = rsec
            rec["reference_vs_hiccups"] = vs_hiccups(ref, h1)
            rec["ours_in_ref_2bin"], rec["ref_in_ours_2bin"] = near(ours, ref, 2), near(ref, ours, 2)
            rec["ours_in_ref_exact"], rec["ref_in_ours_exact"] = near(ours, ref, 0), near(ref, ours, 0)
        results["chr1_5kb"] = rec
        print("\nchr1 at 5 kb")
        print(json.dumps(rec, indent=1))

    dst.write_text(json.dumps(results, indent=1, default=float))
    print(f"\nwritten {dst}")


if __name__ == "__main__":
    main()
