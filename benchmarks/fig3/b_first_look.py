"""Fig. 3b first look: imaging-derived contact frequency vs real Hi-C.

Feasibility check, not the final benchmark.  For each pairing of a
chromatin-tracing dataset with bulk Hi-C of the same cell type:

* imaging contact frequency = fraction of traces with d(i, j) < r
  (``uchrom.fea.distance.contact_frequency``; NaN spots excluded pair-wise,
  the Bintu 2018 convention), for several radii r;
* Hi-C = raw observed 5 kb counts summed into the imaged 30 kb segments
  (the Bintu 2018 recipe, ``Data/README.md`` of BogdanBintu/ChromatinImaging);
* Pearson / Spearman over the off-diagonal pairs (|i - j| >= 1) of
  log10(imaging) vs log10(Hi-C), plus the median-distance vs Hi-C
  correlation, and the P(s) log-log slopes of both.

Inputs (``example-data/``; see its README):
  IMR90_chr21-18-20Mb.csv, bintu2018/{IMR90,K562}_chr21-28-30Mb.csv  (Bintu 2018)
  rao2014_imr90/IMR90_chr21_5kb_hg19.cool, rao2014_k562/K562_chr21_5kb_hg19.cool
      (``build_rao2014_slices.py``)
  optional: 4DNFIHF3JCBY.csv (Takei 2021 mESC) + an mESC Hi-C .mcool via --mesc-hic

Usage::

    python benchmarks/fig3/b_first_look.py [--data example-data] [--out results.json]
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

from uchrom.fea.distance import contact_frequency, mean_distance_matrix

ROOT = Path(__file__).resolve().parents[2]
SEG = 30_000
# hg19 start of segment 1 (Bintu Data/README.md, "and in hg19")
PAIRS = [
    ("Bintu2018 IMR90 chr21:18.6-20.6Mb", "IMR90_chr21-18-20Mb.csv", 20_000_032,
     "rao2014_imr90/IMR90_chr21_5kb_hg19.cool"),
    ("Bintu2018 IMR90 chr21:28-30Mb", "bintu2018/IMR90_chr21-28-30Mb.csv", 29_372_390,
     "rao2014_imr90/IMR90_chr21_5kb_hg19.cool"),
    ("Bintu2018 K562 chr21:28-30Mb", "bintu2018/K562_chr21-28-30Mb.csv", 29_372_390,
     "rao2014_k562/K562_chr21_5kb_hg19.cool"),
    # cross-cell-type controls: imaging of one cell line vs Hi-C of the other
    ("control: IMR90 imaging vs K562 Hi-C, chr21:28-30Mb", "bintu2018/IMR90_chr21-28-30Mb.csv",
     29_372_390, "rao2014_k562/K562_chr21_5kb_hg19.cool"),
    ("control: K562 imaging vs IMR90 Hi-C, chr21:28-30Mb", "bintu2018/K562_chr21-28-30Mb.csv",
     29_372_390, "rao2014_imr90/IMR90_chr21_5kb_hg19.cool"),
]


def load_bintu(path: Path, start0: int) -> pd.DataFrame:
    df = pd.read_csv(path, skiprows=1)
    df.columns = ["trace_id", "seg", "z", "x", "y"]
    df = df.dropna(subset=["x", "y", "z"])
    df["chrom"] = "chr21"
    df["start"] = start0 + (df["seg"] - 1) * SEG
    df["end"] = df["start"] + SEG
    return df


def hic_segments(cool_path: Path, chrom: str, starts: np.ndarray, width: int) -> np.ndarray:
    """Sum raw 5 kb counts into [start, start + width) segments (nearest 5 kb)."""
    import cooler

    c = cooler.Cooler(str(cool_path))
    res = c.binsize
    lo = int(starts.min()) // res * res
    hi = int(starts.max() + width) // res * res + res
    m = c.matrix(balance=False).fetch(f"{chrom}:{lo}-{hi}").astype(float)
    idx = np.rint((starts - lo) / res).astype(int)
    k = width // res
    out = np.zeros((len(starts), len(starts)))
    for a, ia in enumerate(idx):
        for b, ib in enumerate(idx):
            out[a, b] = m[ia:ia + k, ib:ib + k].sum()
    return out


def ps_slope(mat: np.ndarray, smin: int = 2, smax: int = 40) -> float:
    s = np.arange(smin, smax + 1)
    p = np.array([np.nanmean(np.diagonal(mat, d)) for d in s])
    ok = np.isfinite(p) & (p > 0)
    return float(np.polyfit(np.log10(s[ok] * SEG), np.log10(p[ok]), 1)[0])


def compare(img_cf: np.ndarray, hic: np.ndarray, med: np.ndarray) -> dict:
    n = len(hic)
    iu = np.triu_indices(n, 1)
    a, h, d = img_cf[iu], hic[iu], med[iu]
    ok = np.isfinite(a) & (a > 0) & (h > 0)
    okd = np.isfinite(d) & (h > 0)
    return {
        "n_pairs": int(ok.sum()),
        "pearson_log": float(stats.pearsonr(np.log10(a[ok]), np.log10(h[ok]))[0]),
        "spearman": float(stats.spearmanr(a[ok], h[ok])[0]),
        "pearson_logdist_vs_loghic": float(stats.pearsonr(np.log10(d[okd]), np.log10(h[okd]))[0]),
        # distance-decay removed: observed / expected (mean of each diagonal)
        "pearson_log_oe": float(stats.pearsonr(*[np.log10(_oe(x)[iu][ok]) for x in (img_cf, hic)])[0]),
    }


def _oe(m: np.ndarray) -> np.ndarray:
    out = np.full_like(m, np.nan, dtype=float)
    n = len(m)
    for k in range(1, n):
        dg = np.diagonal(m, k).astype(float)
        e = np.nanmean(np.where(dg > 0, dg, np.nan))
        idx = np.arange(n - k)
        out[idx, idx + k] = dg / e
        out[idx + k, idx] = dg / e
    return out


def su2020(data: Path, radii) -> dict:
    """Whole chr21 (Su 2020), against the authors' own binned Rao 2014 Hi-C.

    7,591 traces x 651 loci is too large for the dense per-trace distance
    cube, so contact counts and mean distances are accumulated over chunks
    of 400 traces (mean rather than median distance)."""
    d = data / "su2020_imr90"
    df = pd.read_csv(d / "chromosome21.tsv", sep="\t", usecols=[0, 1, 2, 3, 4])
    df.columns = ["z", "x", "y", "locus", "trace"]
    hic_df = pd.read_csv(d / "Hi-C_contacts_chromosome21.tsv", sep="\t", index_col=0)
    hic = hic_df.to_numpy(float)
    n = len(hic_df)
    df["i"] = df["locus"].map({l: i for i, l in enumerate(hic_df.index)})
    traces = df["trace"].unique()
    ti = pd.Series(np.arange(len(traces)), index=traces)[df["trace"]].to_numpy()
    cube = np.full((len(traces), n, 3), np.nan, np.float32)
    cube[ti, df["i"].to_numpy()] = df[["x", "y", "z"]].to_numpy(np.float32)
    hits = {r: np.zeros((n, n)) for r in radii}
    valid, dsum = np.zeros((n, n)), np.zeros((n, n))
    for b in range(0, len(traces), 400):
        c = cube[b:b + 400]
        dd = np.linalg.norm(c[:, :, None] - c[:, None], axis=-1)
        ok = np.isfinite(dd)
        valid += ok.sum(0)
        dsum += np.where(ok, dd, 0).sum(0)
        for r in radii:
            hits[r] += (ok & (dd < r)).sum(0)
    mean_d = np.where(valid > 0, dsum / np.maximum(valid, 1), np.nan)
    row = {"pair": "Su2020 IMR90 chr21 whole chromosome (651 x 50 kb, authors' Rao 2014 Hi-C)",
           "n_traces": int(len(traces)), "n_segments": n,
           "hic_contacts_in_region": float(np.triu(hic).sum()), "by_radius_nm": {}}
    for r in radii:
        row["by_radius_nm"][int(r)] = compare(hits[r] / np.maximum(valid, 1), hic, mean_d)
    # P(s) over 0.1-10 Mb in log bins (loci are not all contiguous)
    mid = np.array([int(l.split(":")[1].split("-")[0]) for l in hic_df.index])
    iu = np.triu_indices(n, 1)
    sep = np.abs(mid[:, None] - mid[None])[iu]
    r_ps = max(radii)
    for name, m in (("hic", hic), ("imaging", hits[r_ps] / np.maximum(valid, 1))):
        v = m[iu]
        sel = (sep >= 100_000) & (sep <= 10_000_000) & (v > 0)
        k = np.digitize(sep[sel], np.logspace(5, 7, 21))
        xs = [np.log10(sep[sel][k == j].mean()) for j in np.unique(k)]
        ys = [np.log10(v[sel][k == j].mean()) for j in np.unique(k)]
        row[f"ps_slope_{name}"] = float(np.polyfit(xs, ys, 1)[0])
    row["ps_imaging_radius_nm"] = int(r_ps)
    return row


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", type=Path, default=ROOT / "example-data")
    ap.add_argument("--radii", type=float, nargs="+", default=[100, 150, 200, 300, 500])
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()
    results = []
    for name, csv, start0, cool in PAIRS:
        t0 = time.time()
        df = load_bintu(args.data / csv, start0)
        starts = np.sort(df["start"].unique())
        hic = hic_segments(args.data / cool, "chr21", starts, SEG)
        med, _, n_tr = mean_distance_matrix(df, reduce="median")
        row = {"pair": name, "n_traces": int(n_tr), "n_segments": len(starts),
               "hic_contacts_in_region": float(np.triu(hic).sum()),
               "ps_slope_hic": ps_slope(hic), "by_radius_nm": {}}
        for r in args.radii:
            cf, _, _ = contact_frequency(df, threshold=r)
            row["by_radius_nm"][int(r)] = {**compare(cf, hic, med), "ps_slope_imaging": ps_slope(cf)}
        row["seconds"] = round(time.time() - t0, 1)
        results.append(row)
        best = max(row["by_radius_nm"].items(), key=lambda kv: kv[1]["pearson_log"])
        print(f"{name}: {n_tr} traces, {len(starts)} segs | Hi-C P(s) slope {row['ps_slope_hic']:.2f}")
        for r, v in row["by_radius_nm"].items():
            print(f"   r={r:>4} nm  pearson(log)={v['pearson_log']:.3f}  spearman={v['spearman']:.3f}  "
                  f"O/E r={v['pearson_log_oe']:.3f}  P(s) slope img={v['ps_slope_imaging']:.2f}")
        print(f"   median distance vs Hi-C (log-log) r={best[1]['pearson_logdist_vs_loghic']:.3f}")
    if (args.data / "su2020_imr90" / "chromosome21.tsv").exists():
        row = su2020(args.data, args.radii)
        results.append(row)
        print(f"{row['pair']}: {row['n_traces']} traces | P(s) slope 0.1-10 Mb: Hi-C "
              f"{row['ps_slope_hic']:.2f}, imaging ({row['ps_imaging_radius_nm']} nm) {row['ps_slope_imaging']:.2f}")
        for r, v in row["by_radius_nm"].items():
            print(f"   r={r:>4} nm  pearson(log)={v['pearson_log']:.3f}  spearman={v['spearman']:.3f}  "
                  f"O/E r={v['pearson_log_oe']:.3f}  mean distance vs Hi-C (log-log) r={v['pearson_logdist_vs_loghic']:.3f}")
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(results, indent=1))
        print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
