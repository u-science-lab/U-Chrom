"""GM12878 pseudo-bulk maps from single cells vs bulk in situ Hi-C (Rao et al. 2014), chr21.

    .venv/bin/python benchmarks/hic_structures/pseudobulk_gm12878.py [--chain hg38ToHg19.over.chain.gz] [--out DIR]

Single cells: Tan 2018 Dip-C (``ds.load("tan2018_gm12878")``, 14 cells with hickit pairs, hg19) and Wu 2025
scMicro-C (``ds.load("wu2025_scmicroc")``, the 10 deep cells passing QC, hg38), per-cell maps at 5 kb.
``uchrom.fea.pseudobulk`` sums each set into one genome-wide 5 kb map (cis + trans, ICE).  The scMicro-C map
is lifted to hg19 for chr21 (bin midpoints through the UCSC hg38ToHg19 chain, ``ds.fetch("hg38_to_hg19_chain")``
unless ``--chain``) and added to the
Dip-C map: the combined GM12878 pseudo-bulk.

Compared with Rao 2014 GM12878 in situ Hi-C (``ds.fetch("rao2014_gm12878_chr21")``, primary + replicate, 5 kb
raw counts, hg19) on chr21:

* depth: contacts per cell, cis fraction, chr21 contacts;
* distance decay P(s): per-diagonal mean of the raw 5 kb counts over the total, log-binned; the slope in
  100 kb - 3 Mb and the RMS difference of log10 P(s) from Rao's (curves normalised on 10 kb - 10 Mb);
* the chr21 maps at 100 kb and 25 kb (every map summed to that bin size and ICE-balanced on chr21 alone, the
  same treatment for all): Pearson of log balanced contacts, Pearson of log observed / expected and the
  stratum-adjusted correlation (SCC, HiCRep; Yang et al. 2017 Genome Res 27:1939; no smoothing, h = 0) up to
  5 Mb (100 kb) / 2 Mb (25 kb).  Controls: Rao IMR90 (``rao2014_imr90_chr21``, another cell type at bulk
  depth), Rao GM12878 binomially thinned to the combined pseudo-bulk's chr21 depth (the sampling ceiling at
  that depth) and the two pseudo-bulks against each other;
* runtime / peak memory of building the per-cell maps (``ds.load``) and of ``pseudobulk``, and a profile of
  the scMicro-C pseudo-bulk: summing + writing without ICE, then ``cooler.balance_cooler`` alone (iterations,
  seconds per iteration, memory).

Results: a table on stdout and ``pseudobulk_gm12878.json`` in ``--out`` (default: the system temp directory).
"""

from __future__ import annotations

import argparse
import gzip
import json
import tempfile
import time
from pathlib import Path

import numpy as np
import pandas as pd

from pseudobulk_dschic import PeakRSS

HG19_CHR21 = 48129895
RES = 5000


# ------------------------------------------------------------------------------------------------ liftover

def chain_blocks(path, t_chrom="chr21", q_chrom="chr21"):
    """Aligned blocks of a UCSC chain file from ``t_chrom`` to ``q_chrom``: (t_start, size, q_start, strand,
    q_size) arrays, the chains' order (best score first) kept."""
    out, cur = [], None
    with gzip.open(path, "rt") as fh:
        for line in fh:
            f = line.split()
            if not f:
                continue
            if f[0] == "chain":
                tn, ts, qn, qsz, qstr, qs = f[2], int(f[5]), f[7], int(f[8]), f[9], int(f[10])
                cur = [ts, qs, qstr, qsz] if (tn == t_chrom and qn == q_chrom) else None
                continue
            if cur is None:
                continue
            size = int(f[0])
            out.append((cur[0], size, cur[1], cur[2] == "-", cur[3]))
            if len(f) == 3:
                cur[0] += size + int(f[1])
                cur[1] += size + int(f[2])
    b = np.array(out, dtype=np.int64)
    return b[:, 0], b[:, 1], b[:, 2], b[:, 3].astype(bool), b[:, 4]


def lift(pos, blocks):
    """hg38 positions -> hg19 positions (-1: unmapped); the first (best) chain covering a position wins."""
    ts, size, qs, minus, qsize = blocks
    out = np.full(len(pos), -1, np.int64)
    order = np.argsort(ts, kind="stable")
    ts_o = ts[order]
    k = np.searchsorted(ts_o, pos, side="right") - 1
    for shift in range(0, 4):                      # overlapping chains: look at a few preceding blocks
        kk = k - shift
        ok = (kk >= 0) & (out < 0)
        b = order[np.clip(kk, 0, None)]
        inside = ok & (pos >= ts[b]) & (pos < ts[b] + size[b])
        off = pos - ts[b]
        q = np.where(minus[b], qsize[b] - 1 - (qs[b] + off), qs[b] + off)
        out[inside] = q[inside]
    return out


# ------------------------------------------------------------------------------------------------ maps

def chr21_pixels(path, chrom="chr21"):
    """(bin1, bin2, count) of the chromosome, chromosome-local 5 kb bins (raw counts)."""
    import cooler

    clr = cooler.Cooler(str(path))
    lo, _ = clr.extent(chrom)
    px = clr.matrix(balance=False, as_pixels=True).fetch(chrom)
    return (px["bin1_id"].to_numpy(np.int64) - lo, px["bin2_id"].to_numpy(np.int64) - lo,
            px["count"].to_numpy(np.int64))


def write_chr21(path, b1, b2, c, size=HG19_CHR21, res=RES):
    """A chr21-only raw cooler on the hg19 grid (pixels summed, upper triangle)."""
    import cooler

    n = -(-size // res)
    a, b = np.minimum(b1, b2), np.maximum(b1, b2)
    k = a * n + b
    uk, inv = np.unique(k, return_inverse=True)
    cnt = np.bincount(inv, weights=c).astype(np.int64)
    starts = np.arange(n, dtype=np.int64) * res
    bins = pd.DataFrame({"chrom": "chr21", "start": starts, "end": np.minimum(starts + res, size)})
    cooler.create_cooler(str(path), bins, pd.DataFrame({"bin1_id": uk // n, "bin2_id": uk % n, "count": cnt}),
                         ordered=True, assembly="hg19")
    return path


def balanced_chr21(path, res, out):
    """The chr21 map summed into ``res`` bins and ICE-balanced on chr21 alone -> (matrix, valid mask)."""
    import cooler

    from uchrom.fea import rebin_map

    p = rebin_map(str(path), resolution=res, chrom="chr21", out=out)
    clr = cooler.Cooler(p)
    M = np.asarray(clr.matrix(balance=True).fetch("chr21"), float)
    w = clr.bins().fetch("chr21")["weight"].to_numpy()
    return M, np.isfinite(w)


# ------------------------------------------------------------------------------------------------ metrics

def p_of_s(b1, b2, c, n_bins, res=RES):
    """Contact probability per separation (per-diagonal mean of raw counts / total), log-binned."""
    d = np.abs(b2 - b1)
    per = np.bincount(d, weights=c, minlength=n_bins)[:n_bins] / np.maximum(n_bins - np.arange(n_bins), 1)
    per = per / c.sum()
    s = np.arange(n_bins) * res
    edges = np.unique(np.round(np.logspace(np.log10(res), np.log10(s[-1]), 60) / res).astype(int))
    mids, vals = [], []
    for lo, hi in zip(edges[:-1], edges[1:]):
        v = per[lo:hi]
        if len(v) and v.mean() > 0:
            mids.append(np.sqrt(lo * max(hi - 1, lo)) * res)
            vals.append(v.mean())
    return np.array(mids), np.array(vals)


def slope(s, p, lo=1e5, hi=3e6):
    m = (s >= lo) & (s <= hi) & (p > 0)
    return float(np.polyfit(np.log10(s[m]), np.log10(p[m]), 1)[0])


def ps_rms(s1, p1, s2, p2, lo=1e4, hi=1e7):
    """RMS of log10 P(s) differences on common separations, each curve normalised to sum 1 in [lo, hi]."""
    m1 = (s1 >= lo) & (s1 <= hi)
    m2 = (s2 >= lo) & (s2 <= hi)
    common = np.intersect1d(np.round(s1[m1]), np.round(s2[m2]))
    a = pd.Series(p1[m1], index=np.round(s1[m1])).reindex(common)
    b = pd.Series(p2[m2], index=np.round(s2[m2])).reindex(common)
    a, b = a / a.sum(), b / b.sum()
    return float(np.sqrt(np.mean((np.log10(a) - np.log10(b)) ** 2)))


def _diag(M, valid, d):
    n = len(M)
    i = np.arange(n - d)
    ok = valid[i] & valid[i + d]
    return M[i[ok], i[ok] + d]


def map_corr(A, va, B, vb, dmax_bins):
    """Pearson of log balanced, Pearson of log O/E (per-diagonal mean of each map), SCC (h = 0)."""
    from scipy.stats import pearsonr, rankdata

    valid = va & vb
    la, lb, oa, ob = [], [], [], []
    num = den = 0.0
    for d in range(1, dmax_bins + 1):
        a, b = _diag(A, valid, d), _diag(B, valid, d)
        keep = (a > 0) & (b > 0)
        if keep.sum() < 3:
            continue
        a, b = a[keep], b[keep]
        la.append(np.log(a))
        lb.append(np.log(b))
        oa.append(np.log(a / a.mean()))
        ob.append(np.log(b / b.mean()))
        N = len(a)
        if a.std() > 0 and b.std() > 0:
            rho = pearsonr(a, b)[0]
            w = N * np.sqrt(np.var(rankdata(a) / N) * np.var(rankdata(b) / N))
            num += w * rho
            den += w
    la, lb, oa, ob = (np.concatenate(x) for x in (la, lb, oa, ob))
    return {"pearson_log": float(np.corrcoef(la, lb)[0, 1]), "pearson_log_oe": float(np.corrcoef(oa, ob)[0, 1]),
            "scc": float(num / den), "n_pixels": int(len(la))}


# ------------------------------------------------------------------------------------------------ main

def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--out", type=Path, default=Path(tempfile.gettempdir()) / "uchrom_pseudobulk_gm12878")
    ap.add_argument("--chain", type=Path, default=None,
                    help="UCSC hg38ToHg19.over.chain.gz (default: fetch hg38_to_hg19_chain)")
    a = ap.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)

    import uchrom.datasets as ds
    from uchrom.fea import pseudobulk

    res: dict = {"runtime": {}}
    sets = {}
    for name, kw in (("tan2018_gm12878", {}), ("wu2025_scmicroc", {"qc": True})):
        t0 = time.perf_counter()
        with PeakRSS() as mem:
            cd = ds.load(name)
        res["runtime"][f"load {name}"] = {"s": time.perf_counter() - t0, "peak_rss_gb": mem.peak / 1e9}
        cells = list(cd.cells.index[cd.cells["qc_pass"].to_numpy(bool)]) if kw.get("qc") else None
        t0 = time.perf_counter()
        with PeakRSS() as mem:
            summary = pseudobulk(cd, None, cells=cells, key_prefix=name, out_dir=a.out / "maps", overwrite=True)
        res["runtime"][f"pseudobulk {name}"] = {
            "s": time.perf_counter() - t0, "peak_rss_gb": mem.peak / 1e9,
            "rss_increase_gb": (mem.peak - mem.base) / 1e9,
            "stages_s": cd.results.record(name).inputs["seconds"]}
        row = summary.iloc[0]
        sets[name] = {"cd": cd, "path": row["path"], "n_cells": int(row["n_cells"]),
                      "n_contacts": int(row["n_contacts"]), "n_cis": int(row["n_cis"]),
                      "assembly": cd.uns["genome_assembly"]}
        print(f"{name}: {row['n_cells']} cells, {row['n_contacts']:,} contacts "
              f"({row['n_contacts'] / row['n_cells']:,.0f} per cell, {row['n_cis'] / row['n_contacts']:.1%} cis), "
              f"pseudobulk {res['runtime'][f'pseudobulk {name}']['s']:.1f} s")

    # chr21 5 kb raw maps on hg19: Dip-C as is, scMicro-C lifted, both combined; Rao GM12878 / IMR90
    blocks = chain_blocks(a.chain or ds.fetch("hg38_to_hg19_chain"))
    t1, t2, tc = chr21_pixels(sets["tan2018_gm12878"]["path"])
    w1, w2, wc = chr21_pixels(sets["wu2025_scmicroc"]["path"])
    l1 = lift(w1 * RES + RES // 2, blocks)
    l2 = lift(w2 * RES + RES // 2, blocks)
    ok = (l1 >= 0) & (l2 >= 0)
    lift_stats = {"pixels": int(len(wc)), "contacts": int(wc.sum()), "contacts_lifted": int(wc[ok].sum()),
                  "frac_lifted": float(wc[ok].sum() / wc.sum())}
    print("scMicro-C chr21 lifted to hg19:", lift_stats)
    l1, l2, lc = l1[ok] // RES, l2[ok] // RES, wc[ok]
    maps5 = {
        "dipc": write_chr21(a.out / "dipc_chr21_5kb.cool", t1, t2, tc),
        "scmicroc": write_chr21(a.out / "scmicroc_chr21_5kb_hg19.cool", l1, l2, lc),
        "combined": write_chr21(a.out / "combined_chr21_5kb.cool", np.r_[t1, l1], np.r_[t2, l2], np.r_[tc, lc]),
        "rao_gm12878": Path(ds.fetch("rao2014_gm12878_chr21")),
        "rao_imr90": Path(ds.fetch("rao2014_imr90_chr21")),
    }
    # Rao GM12878 thinned to the combined pseudo-bulk's chr21 depth (binomial, fixed seed)
    b1, b2, c = chr21_pixels(maps5["rao_gm12878"])
    frac = int(np.r_[tc, lc].sum()) / int(c.sum())
    thin = np.random.default_rng(0).binomial(c, frac)
    maps5["rao_gm12878_thinned"] = write_chr21(a.out / "rao_gm12878_thinned_chr21_5kb.cool", b1[thin > 0],
                                               b2[thin > 0], thin[thin > 0])
    res["thinning_fraction"] = frac
    n5 = -(-HG19_CHR21 // RES)
    ps, depth = {}, {}
    for k, p in maps5.items():
        b1, b2, c = chr21_pixels(p)
        ps[k] = p_of_s(b1, b2, c, n5)
        depth[k] = int(c.sum())
    ncell = {"dipc": sets["tan2018_gm12878"]["n_cells"], "scmicroc": sets["wu2025_scmicroc"]["n_cells"]}
    ncell["combined"] = ncell["dipc"] + ncell["scmicroc"]
    res["depth"] = {
        "contacts_per_cell": {k: sets[n]["n_contacts"] / sets[n]["n_cells"] for k, n in
                              (("dipc", "tan2018_gm12878"), ("scmicroc", "wu2025_scmicroc"))},
        "frac_cis": {k: sets[n]["n_cis"] / sets[n]["n_contacts"] for k, n in
                     (("dipc", "tan2018_gm12878"), ("scmicroc", "wu2025_scmicroc"))},
        "chr21_contacts": depth, "n_cells": ncell,
        "chr21_fraction_of_rao": {k: depth[k] / depth["rao_gm12878"] for k in depth}}
    res["lift"] = lift_stats
    res["p_of_s"] = {k: {"slope_100kb_3Mb": slope(*ps[k]), "slope_1_10Mb": slope(*ps[k], 1e6, 1e7),
                         "rms_log10_vs_rao_gm12878": ps_rms(*ps[k], *ps["rao_gm12878"]),
                         "s": ps[k][0].tolist(), "p": ps[k][1].tolist()} for k in ps}

    # correlations of the balanced chr21 maps
    pairs = [("dipc", "rao_gm12878"), ("scmicroc", "rao_gm12878"), ("combined", "rao_gm12878"),
             ("rao_gm12878_thinned", "rao_gm12878"), ("combined", "rao_imr90"), ("rao_imr90", "rao_gm12878"),
             ("dipc", "scmicroc")]
    res["correlation"] = {}
    for r, dmax in ((100_000, 5_000_000), (25_000, 2_000_000)):
        mats = {k: balanced_chr21(p, r, a.out / f"{k}_chr21_{r // 1000}kb.cool") for k, p in maps5.items()}
        res["correlation"][r] = {f"{x} vs {y}": map_corr(*mats[x], *mats[y], dmax // r) for x, y in pairs}
        res["correlation"][r]["valid_bins"] = {k: int(v.sum()) for k, (_, v) in mats.items()}

    # profile: the scMicro-C pseudo-bulk without ICE, then ICE alone (uchrom's in-memory ICE vs cooler's)
    import logging

    import cooler

    from uchrom.fea import ice

    cd = sets["wu2025_scmicroc"]["cd"]
    cells = list(cd.cells.index[cd.cells["qc_pass"].to_numpy(bool)])
    t0 = time.perf_counter()
    with PeakRSS() as mem:
        s = pseudobulk(cd, None, cells=cells, key_prefix="profile", out_dir=a.out / "profile", overwrite=True,
                       balance=False)
    prof = {"sum_and_write_s": time.perf_counter() - t0, "sum_and_write_rss_increase_gb": (mem.peak - mem.base) / 1e9,
            "stages_s": cd.results.record("profile").inputs["seconds"], "n_pixels": int(s["n_pixels"].iloc[0])}
    iters = []

    class Count(logging.Handler):
        def emit(self, record):
            if "variance is" in record.getMessage():
                iters.append(1)

    log = logging.getLogger("cooler")
    saved = (log.handlers[:], log.level, log.propagate)
    log.handlers, log.propagate = [Count()], False
    log.setLevel(logging.INFO)
    clr = cooler.Cooler(s["path"].iloc[0])
    t0 = time.perf_counter()
    with PeakRSS() as mem:
        ref, st = cooler.balance_cooler(clr)
    t_bal = time.perf_counter() - t0
    log.handlers, log.level, log.propagate = saved
    px = clr.pixels()[:]
    offsets = clr._load_dset("indexes/chrom_offset")
    t0 = time.perf_counter()
    with PeakRSS() as mem2:
        ours, st2 = ice(px["bin1_id"].to_numpy(), px["bin2_id"].to_numpy(), px["count"].to_numpy(), offsets)
    t_ice = time.perf_counter() - t0
    ok = np.isfinite(ref)
    prof.update({"cooler_balance_s": t_bal, "cooler_iterations": len(iters),
                 "cooler_s_per_iteration": t_bal / max(len(iters), 1),
                 "cooler_rss_increase_gb": (mem.peak - mem.base) / 1e9, "cooler_converged": bool(st["converged"]),
                 "uchrom_ice_s": t_ice, "uchrom_ice_rss_increase_gb": (mem2.peak - mem2.base) / 1e9,
                 "same_mask": bool(np.array_equal(ok, np.isfinite(ours))),
                 "max_rel_diff": float(np.max(np.abs(ours[ok] / ref[ok] - 1))),
                 "n_bins": int(clr.info["nbins"])})
    res["profile_scmicroc_5kb"] = prof
    print("profile (scMicro-C 5 kb pseudo-bulk):", json.dumps({k: (round(v, 3) if isinstance(v, float) else v)
                                                              for k, v in prof.items()}))

    # report
    print("\ndepth (chr21 contacts; fraction of Rao GM12878):")
    for k in maps5:
        print(f"  {k:12s} {depth[k]:>12,}  {depth[k] / depth['rao_gm12878']:.4f}")
    print("\nP(s): slope 100 kb-3 Mb, slope 1-10 Mb, RMS log10 vs Rao GM12878")
    for k, v in res["p_of_s"].items():
        print(f"  {k:12s} {v['slope_100kb_3Mb']:+.3f}  {v['slope_1_10Mb']:+.3f}  {v['rms_log10_vs_rao_gm12878']:.3f}")
    for r, tab in res["correlation"].items():
        print(f"\nchr21 at {r // 1000} kb: pearson(log) pearson(log O/E) SCC")
        for k, v in tab.items():
            if k != "valid_bins":
                print(f"  {k:36s} {v['pearson_log']:.3f}  {v['pearson_log_oe']:.3f}  {v['scc']:.3f}  "
                      f"(n={v['n_pixels']:,})")
    print("\nruntime:", json.dumps({k: {kk: (round(vv, 2) if isinstance(vv, float) else vv) for kk, vv in v.items()}
                                     for k, v in res["runtime"].items()}))
    res["correlation"] = {str(k): v for k, v in res["correlation"].items()}
    out = a.out / "pseudobulk_gm12878.json"
    out.write_text(json.dumps(res, indent=1, default=float))
    print(f"\n-> {out}")


if __name__ == "__main__":
    import sys
    import warnings

    warnings.filterwarnings("ignore")
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    main()
