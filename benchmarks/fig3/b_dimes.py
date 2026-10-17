"""Fig. 3b external baseline: DIMES ensembles vs U-Chrom's direct contact frequency.

DIMES (Shi & Thirumalai, Nat Commun 14:1150, 2023, doi:10.1038/s41467-023-36412-4)
takes the mean *squared* pairwise distance matrix of the imaged loci
(its Eq. 10, <r_ij^2> = mean over traces of |x_i - x_j|^2), fits the
maximum-entropy (Gaussian) model to it, and samples conformations from it.
The fit is the code's direct inversion (``method="DI"``), which the
HIPPS-DIMES README recommends for a valid mean squared distance map treated
as exact (when the code refuses a map as not a valid Euclidean distance
matrix — pair-wise missing-spot exclusion can do that — the README's IS is
used instead and the row says so); it is the same maximum-entropy solution that the paper's
iterative scaling (gamma = 10) converges to, reached in one step.  The
paper's IS (gamma = 10, 10,000 iterations = code default) is also run on
the small maps (<= 100 loci) and reported as ``dimes_is``; on Su 2020
(651 loci) IS at gamma = 10 does not converge (relative loss rises from
0.67 to 0.97 over the first 300 iterations, 0.2 s each), so only DI is used.  Here its
contact frequency — the fraction of sampled conformations with
d(i, j) < r — is scored against bulk Hi-C exactly like U-Chrom's direct
imaging contact frequency (``uchrom.fea.distance.contact_frequency``), in
the same run, with the functions of ``b_first_look.py``:

* Bintu 2018 IMR90 / K562 chr21:28-30 Mb and IMR90 chr21:18.6-20.6 Mb vs
  Rao 2014 raw 5 kb Hi-C summed into the 30 kb segments, incl. the
  cross-cell-type controls (the DIMES fit of one cell line vs the other's Hi-C);
* Su 2020 IMR90 whole chr21 (651 x 50 kb) vs the authors' binned Rao 2014 Hi-C;
* Takei 2021 mESC (20 x 60 x 25 kb) vs Bonev 2017 Hi-C (range-read, as in
  ``b_takei_bonev.py``; ``--takei``).

Metrics: Pearson of log10 contact frequency vs log10 Hi-C over off-diagonal
pairs ("log-log r"), the same after dividing every diagonal by its mean
("O/E r"), Spearman, (median distance vs Hi-C), P(s) slope.  Every metric is
computed twice: on each method's own non-zero pairs (the ``b_first_look``
rule, so the U-Chrom numbers reproduce ``uchrom-reproducibility/manuscripts/full/figures/fig3/feasibility``) and on the
pairs where both methods and Hi-C are non-zero (``common``).

DIMES also returns the analytic contact probability of its Gaussian model
(Maxwell distribution with <r^2> from the fit); it is reported as
``dimes_analytic`` (= an infinite ensemble).

HIPPS-DIMES is not vendored; clone it (MIT) and pass ``--hipps-dimes``::

    git clone https://github.com/anyuzx/HIPPS-DIMES
    git -C HIPPS-DIMES checkout beee45d15ed1c99fc32e7b98036cebdf7ef2943e

Usage::

    python benchmarks/fig3/b_dimes.py --hipps-dimes ../HIPPS-DIMES [--takei] \
        [--out uchrom-reproducibility/manuscripts/full/figures/fig3/results/b_dimes.json]
"""

from __future__ import annotations

from uchrom.datasets import data_dir
import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import special, stats

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
from b_first_look import PAIRS, SEG, _oe, compare, hic_segments, load_bintu, ps_slope  # noqa: E402


# --------------------------------------------------------------------------- imaging statistics
def cube_from_df(df: pd.DataFrame) -> np.ndarray:
    from uchrom.fea.distance import _bin_coord_cube

    return _bin_coord_cube(df)[0]


def imaging_stats(cube: np.ndarray, radii, chunk: int = 400) -> dict:
    """Pair-wise NaN-excluded contact frequency, mean squared / mean / median distance."""
    n = cube.shape[1]
    valid, d2, d1 = np.zeros((n, n)), np.zeros((n, n)), np.zeros((n, n))
    hits = {r: np.zeros((n, n)) for r in radii}
    dists = []
    for b in range(0, len(cube), chunk):
        c = cube[b:b + chunk]
        dd = np.linalg.norm(c[:, :, None] - c[:, None], axis=-1)
        ok = np.isfinite(dd)
        valid += ok.sum(0)
        d2 += np.where(ok, dd ** 2, 0).sum(0)
        d1 += np.where(ok, dd, 0).sum(0)
        for r in radii:
            hits[r] += (ok & (dd < r)).sum(0)
        if len(cube) * n * n <= 4e8:
            dists.append(dd.astype(np.float32))
    with np.errstate(invalid="ignore", divide="ignore"):
        out = {"n_valid": valid, "msd": np.where(valid > 0, d2 / valid, np.nan),
               "mean_d": np.where(valid > 0, d1 / valid, np.nan),
               "cf": {r: np.where(valid > 0, hits[r] / valid, np.nan) for r in radii}}
    out["median_d"] = np.nanmedian(np.concatenate(dists), 0) if dists else out["mean_d"]
    return out


# --------------------------------------------------------------------------- DIMES
def import_hd(path: Path | None):
    if path is not None:
        sys.path.insert(0, str(Path(path).resolve()))
    import hipps_dimes as HD

    return HD


def run_dimes(HD, msd: np.ndarray, radii, args, method: str = "DI", seed: int = 0) -> dict:
    """Fit DIMES to a mean squared distance map; sample; contact frequency per radius."""
    np.random.seed(seed)
    t0 = time.time()
    kw = dict(input_matrix=msd, input_type="ddmap", iteration=args.iterations, learning_rate=args.lr,
              no_xyzs=True, verbose=False, show_progress=False)
    try:
        res = HD.run_optimization(method=method, **kw)
    except ValueError as e:
        # DI refuses a map that is not a valid Euclidean distance matrix (pair-wise
        # missing-spot exclusion can cause that); the README then prescribes IS
        if method != "DI" or "not valid Euclidean" not in str(e):
            raise
        method = "IS (DI refused: not a valid EDM)"
        res = HD.run_optimization(method="IS", **kw)
    t_fit = time.time() - t0
    A = res["connectivity_matrix"]
    t0 = time.time()
    xyz = HD.a2xyz_sample(A, ensemble=args.ensemble, force_positive_definite=True)
    st = imaging_stats(xyz, radii, chunk=200)
    t_sample = time.time() - t0
    # analytic contact probability of the Gaussian model: |r_ij| ~ Maxwell, sigma^2 = <r^2>/3
    dmap = res["dmap_final"]                                  # mean distance of the model
    sigma = np.sqrt(3 * np.pi / 8 * dmap ** 2 / 3)
    analytic = {}
    with np.errstate(divide="ignore", invalid="ignore"):
        for r in radii:
            x = r / sigma
            p = special.erf(x / np.sqrt(2)) - np.sqrt(2 / np.pi) * x * np.exp(-x ** 2 / 2)
            np.fill_diagonal(p, 1.0)
            analytic[r] = p
    fit_msd = 3 * np.pi / 8 * dmap ** 2
    iu = np.triu_indices(len(msd), 1)
    ok = np.isfinite(msd[iu]) & (msd[iu] > 0)
    return {"method": method, "cf": st["cf"], "median_d": st["median_d"], "mean_d": st["mean_d"], "analytic": analytic,
            "fit_seconds": t_fit, "sample_seconds": t_sample,
            "final_loss": float(res["optimization"]["final_loss"]),
            "msd_fit_pearson": float(stats.pearsonr(fit_msd[iu][ok], msd[iu][ok])[0]),
            "msd_fit_median_rel_err": float(np.median(np.abs(fit_msd[iu][ok] / msd[iu][ok] - 1)))}


# --------------------------------------------------------------------------- scoring
def compare_common(cfs: dict[str, np.ndarray], hic: np.ndarray) -> dict:
    """Metrics on the pairs where every method and Hi-C are > 0."""
    n = len(hic)
    iu = np.triu_indices(n, 1)
    ok = hic[iu] > 0
    for a in cfs.values():
        ok &= np.isfinite(a[iu]) & (a[iu] > 0)
    h = hic[iu][ok]
    oe_h = np.log10(_oe(hic)[iu][ok])
    out = {"n_pairs": int(ok.sum())}
    for k, a in cfs.items():
        oe_a = np.log10(_oe(a)[iu][ok])
        fin = np.isfinite(oe_a) & np.isfinite(oe_h)
        out[k] = {"pearson_log": float(stats.pearsonr(np.log10(a[iu][ok]), np.log10(h))[0]),
                  "spearman": float(stats.spearmanr(a[iu][ok], h)[0]),
                  "pearson_log_oe": float(stats.pearsonr(oe_a[fin], oe_h[fin])[0])}
    return out


def score_pair(name, img, dm, hic, radii, ps: bool = True, dm_is: dict | None = None) -> dict:
    row = {"pair": name, "hic_contacts_in_region": float(np.triu(hic).sum()), "by_radius": {}}
    if ps:
        row["ps_slope_hic"] = ps_slope(hic)
    for r in radii:
        u = {**compare(img["cf"][r], hic, img["median_d"])}
        d = {**compare(dm["cf"][r], hic, dm["median_d"])}
        a = {**compare(dm["analytic"][r], hic, dm["median_d"])}
        if ps:
            u["ps_slope"] = ps_slope(img["cf"][r])
            d["ps_slope"] = ps_slope(dm["cf"][r])
            a["ps_slope"] = ps_slope(dm["analytic"][r])
        row["by_radius"][int(r) if r >= 1 else r] = {
            "uchrom": u, "dimes": d, "dimes_analytic": a,
            "common": compare_common({"uchrom": img["cf"][r], "dimes": dm["cf"][r]}, hic)}
        if dm_is is not None:
            row["by_radius"][int(r) if r >= 1 else r]["dimes_is"] = {
                **compare(dm_is["cf"][r], hic, dm_is["median_d"]),
                **({"ps_slope": ps_slope(dm_is["cf"][r])} if ps else {})}
    return row


def fmt(row, r):
    v = row["by_radius"][r]
    return (f"   r={r}: log-log U-Chrom {v['uchrom']['pearson_log']:.3f} / DIMES {v['dimes']['pearson_log']:.3f}"
            f" (analytic {v['dimes_analytic']['pearson_log']:.3f}) | O/E U-Chrom {v['uchrom']['pearson_log_oe']:.3f}"
            f" / DIMES {v['dimes']['pearson_log_oe']:.3f} (analytic {v['dimes_analytic']['pearson_log_oe']:.3f})"
            f" | common n={v['common']['n_pairs']}: O/E {v['common']['uchrom']['pearson_log_oe']:.3f}"
            f" / {v['common']['dimes']['pearson_log_oe']:.3f}"
            + (f" | DIMES-IS log-log {v['dimes_is']['pearson_log']:.3f} O/E {v['dimes_is']['pearson_log_oe']:.3f}"
               if "dimes_is" in v else ""))


# --------------------------------------------------------------------------- datasets
def su2020_inputs(data: Path):
    d = data / "su2020_imr90"
    df = pd.read_csv(d / "chromosome21.tsv", sep="\t", usecols=[0, 1, 2, 3, 4])
    df.columns = ["z", "x", "y", "locus", "trace"]
    hic_df = pd.read_csv(d / "Hi-C_contacts_chromosome21.tsv", sep="\t", index_col=0)
    n = len(hic_df)
    df["i"] = df["locus"].map({l: i for i, l in enumerate(hic_df.index)})
    traces = df["trace"].unique()
    ti = pd.Series(np.arange(len(traces)), index=traces)[df["trace"]].to_numpy()
    cube = np.full((len(traces), n, 3), np.nan, np.float32)
    cube[ti, df["i"].to_numpy()] = df[["x", "y", "z"]].to_numpy(np.float32)
    return cube, hic_df.to_numpy(float)


def takei_bonev(HD, args, radii_um) -> dict:
    import cooler
    import fsspec
    import h5py
    from b_takei_bonev import BONEV
    from uchrom import ChromData

    cd = ChromData.from_fofct(str(args.data / "4DNFIHF3JCBY.csv"))
    df = cd.to_dataframe()
    df["chrom"] = df["chrom"].astype(str)
    fh = fsspec.open(BONEV, block_size=2 ** 20, cache_type="blockcache").open()
    clr = cooler.Cooler(h5py.File(fh, "r")["resolutions/25000"])
    keys = ["uchrom", "dimes", "dimes_analytic", "dimes_is"]
    pooled = {"hic": [], **{(k, r): [] for k in keys for r in radii_um},
              **{("oe", k, r): [] for k in keys for r in radii_um}, "oe_hic": []}
    t_u = t_fit = t_sample = 0.0
    losses, losses_is, t_is, methods = [], [], 0.0, {}
    for chrom, sub in df.groupby("chrom"):
        starts = np.sort(sub["start"].unique())
        lo, hi = int(starts.min()), int(starts.max()) + 25_000
        H = clr.matrix(balance=True).fetch(f"{chrom}:{lo}-{hi}")
        H = H[np.ix_(((starts - lo) // 25_000).astype(int), ((starts - lo) // 25_000).astype(int))]
        t0 = time.time()
        img = imaging_stats(cube_from_df(sub), radii_um)
        t_u += time.time() - t0
        dm = run_dimes(HD, img["msd"], radii_um, args)
        t_fit += dm["fit_seconds"]
        t_sample += dm["sample_seconds"]
        losses.append(dm["final_loss"])
        methods[chrom] = dm["method"]
        dmi = run_dimes(HD, img["msd"], radii_um, args, method="IS")
        losses_is.append(dmi["final_loss"])
        t_is += dmi["fit_seconds"]
        iu = np.triu_indices(len(starts), 1)
        ok = np.isfinite(H[iu]) & np.isfinite(img["median_d"][iu])     # b_takei_bonev.py rule
        pooled["hic"].append(H[iu][ok])
        Hn = np.where(np.isfinite(H), H, 0)
        pooled["oe_hic"].append(_oe(Hn)[iu][ok])
        for r in radii_um:
            for k, m in (("uchrom", img["cf"][r]), ("dimes", dm["cf"][r]), ("dimes_analytic", dm["analytic"][r]),
                         ("dimes_is", dmi["cf"][r])):
                pooled[(k, r)].append(m[iu][ok])
                pooled[("oe", k, r)].append(_oe(m)[iu][ok])
    h = np.concatenate(pooled["hic"])
    oh = np.concatenate(pooled["oe_hic"])
    res = {"pair": "Takei2021 mESC 20 x 60 x 25 kb vs Bonev 2017 G1 mESC Hi-C (25 kb, balanced)",
           "n_pairs_hic": int(len(h)), "uchrom_seconds": t_u, "dimes_fit_seconds": t_fit,
           "dimes_sample_seconds": t_sample, "dimes_final_loss_max": float(max(losses)), "dimes_method": methods,
           "dimes_is_fit_seconds": t_is, "dimes_is_final_loss_max": float(max(losses_is)),
           "dimes_is_final_loss_median": float(np.median(losses_is)), "by_radius_um": {}}
    for r in radii_um:
        v = {}
        c_all = {k: np.concatenate(pooled[(k, r)]) for k in keys}
        oe_all = {k: np.concatenate(pooled[("oe", k, r)]) for k in keys}
        common = h > 0
        for k in ("uchrom", "dimes"):
            common &= c_all[k] > 0
        for k in keys:
            c, oe = c_all[k], oe_all[k]
            ok = (c > 0) & (h > 0)
            okoe = ok & (oe > 0) & (oh > 0)
            v[k] = {"n_pairs": int(ok.sum()), "spearman": float(stats.spearmanr(c, h)[0]),
                    "pearson_log": float(stats.pearsonr(np.log10(c[ok]), np.log10(h[ok]))[0]),
                    "pearson_log_oe": float(stats.pearsonr(np.log10(oe[okoe]), np.log10(oh[okoe]))[0])}
        cm = {"n_pairs": int(common.sum())}
        for k in ("uchrom", "dimes"):
            c, oe = c_all[k][common], oe_all[k][common]
            okoe = (oe > 0) & (oh[common] > 0)
            cm[k] = {"pearson_log": float(stats.pearsonr(np.log10(c), np.log10(h[common]))[0]),
                     "pearson_log_oe": float(stats.pearsonr(np.log10(oe[okoe]), np.log10(oh[common][okoe]))[0])}
        v["common"] = cm
        res["by_radius_um"][r] = v
        print(f"   r={r} um: log-log U-Chrom {v['uchrom']['pearson_log']:.3f} / DIMES {v['dimes']['pearson_log']:.3f}"
              f" | O/E U-Chrom {v['uchrom']['pearson_log_oe']:.3f} / DIMES {v['dimes']['pearson_log_oe']:.3f}"
              f" | Spearman {v['uchrom']['spearman']:.3f} / {v['dimes']['spearman']:.3f}"
              f" | DIMES-IS log-log {v['dimes_is']['pearson_log']:.3f} O/E {v['dimes_is']['pearson_log_oe']:.3f}")
    return res


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", type=Path, default=data_dir())
    ap.add_argument("--hipps-dimes", type=Path, default=None, help="path to the HIPPS-DIMES clone")
    ap.add_argument("--radii", type=float, nargs="+", default=[150, 200, 300], help="nm (Bintu, Su)")
    ap.add_argument("--radii-um", type=float, nargs="+", default=[0.15, 0.2, 0.3], help="um (Takei)")
    ap.add_argument("--iterations", type=int, default=10_000, help="IS iterations (code default)")
    ap.add_argument("--lr", type=float, default=10.0, help="IS learning rate (DIMES paper: 10)")
    ap.add_argument("--ensemble", type=int, default=10_000, help="sampled conformations")
    ap.add_argument("--is-max-loci", type=int, default=100,
                    help="also run the paper's IS (gamma=10) where n_loci <= this (DI is the primary fit)")
    ap.add_argument("--takei", action="store_true", help="also Takei 2021 vs Bonev 2017 (HTTP range reads)")
    ap.add_argument("--out", type=Path)
    args = ap.parse_args()
    HD = import_hd(args.hipps_dimes)
    radii = args.radii
    results, fits = [], {}

    # Bintu 2018: one U-Chrom / DIMES computation per imaging dataset, scored vs each Hi-C
    for name, csv, start0, cool in PAIRS:
        if csv not in fits:
            df = load_bintu(args.data / csv, start0)
            t0 = time.time()
            img = imaging_stats(cube_from_df(df), radii)
            t_u = time.time() - t0
            dm = run_dimes(HD, img["msd"], radii, args)
            dmi = run_dimes(HD, img["msd"], radii, args, method="IS") if len(img["msd"]) <= args.is_max_loci else None
            fits[csv] = (df, img, dm, t_u, dmi)
            print(f"{csv}: {df['trace_id'].nunique()} traces | U-Chrom {t_u:.2f} s | DIMES ({dm['method']}) fit "
                  f"{dm['fit_seconds']:.1f} s + sample {dm['sample_seconds']:.1f} s, loss {dm['final_loss']:.4f}, "
                  f"<r2> fit r={dm['msd_fit_pearson']:.4f}")
        df, img, dm, t_u, dmi = fits[csv]
        starts = np.sort(df["start"].unique())
        hic = hic_segments(args.data / cool, "chr21", starts, SEG)
        row = score_pair(name, img, dm, hic, radii, dm_is=dmi)
        if dmi is not None:
            row.update({"dimes_is_fit_seconds": dmi["fit_seconds"], "dimes_is_final_loss": dmi["final_loss"],
                        "dimes_is_msd_fit_pearson": dmi["msd_fit_pearson"]})
        row.update({"n_traces": int(df["trace_id"].nunique()), "n_segments": len(starts),
                    "uchrom_seconds": t_u, "dimes_fit_seconds": dm["fit_seconds"],
                    "dimes_sample_seconds": dm["sample_seconds"], "dimes_final_loss": dm["final_loss"],
                    "dimes_method": dm["method"], "dimes_msd_fit_pearson": dm["msd_fit_pearson"],
                    "dimes_msd_fit_median_rel_err": dm["msd_fit_median_rel_err"]})
        results.append(row)
        print(name)
        for r in radii:
            print(fmt(row, int(r)))

    if (args.data / "su2020_imr90" / "chromosome21.tsv").exists():
        cube, hic = su2020_inputs(args.data)
        t0 = time.time()
        img = imaging_stats(cube, radii)
        t_u = time.time() - t0
        dm = run_dimes(HD, img["msd"], radii, args)
        row = score_pair("Su2020 IMR90 chr21 whole chromosome (651 x 50 kb, authors' Rao 2014 Hi-C)",
                         img, dm, hic, radii, ps=False)
        row.update({"n_traces": int(len(cube)), "n_segments": int(cube.shape[1]), "uchrom_seconds": t_u,
                    "dimes_fit_seconds": dm["fit_seconds"], "dimes_sample_seconds": dm["sample_seconds"],
                    "dimes_final_loss": dm["final_loss"], "dimes_method": dm["method"],
                    "dimes_msd_fit_pearson": dm["msd_fit_pearson"],
                    "dimes_msd_fit_median_rel_err": dm["msd_fit_median_rel_err"],
                    "note": "distance vs Hi-C uses the mean distance for U-Chrom when the cube is too large for a median"})
        results.append(row)
        print(f"{row['pair']}: U-Chrom {t_u:.1f} s | DIMES fit {dm['fit_seconds']:.1f} s + sample "
              f"{dm['sample_seconds']:.1f} s, loss {dm['final_loss']:.4f}")
        for r in radii:
            print(fmt(row, int(r)))

    if args.takei:
        print("Takei 2021 vs Bonev 2017")
        results.append(takei_bonev(HD, args, args.radii_um))

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps({"params": {"method": "DI (primary); IS gamma=10 as 'dimes_is' where n_loci <= "
                                                             f"{args.is_max_loci}", "iterations_is": args.iterations,
                                                   "learning_rate": args.lr, "ensemble": args.ensemble,
                                                   "input": "mean squared distance map (DIMES Eq. 10)",
                                                   "radii_nm": radii, "radii_um_takei": args.radii_um},
                                        "results": results}, indent=1, default=float))
        print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
