"""Run time, memory and agreement of the RWR imputation and SnapHiC's sums: numpy reference vs native kernel.

    python benchmarks/sc_structures/impute_speed.py all --out DIR [--threads 1 4 16 32]

On real cells (``nagano2017_dip_serum``, the 742 deepest; ``snaphic_data.py``), SnapHiC's settings (10 kb, restart
0.05, window ``auto`` = SnapHiC2's rule on these cells, band to 1.05 Mb):

* ``band``: one cell's RWR band (``uchrom.fea.impute_rwr.rwr_band``) on chr19 (6,130 bins) and chr1 (19,548
  bins), numpy (dense LAPACK per window) vs native (profile Cholesky + selected inversion, windows in
  parallel) at each thread count; best of 3; then the cell's z-scores and local background (the profile of
  one cell's SnapHiC steps); largest relative difference of the bands and of the z-scores;
* ``sums``: SnapHiC's sums over N cells (``uchrom.strc.loop.snaphic.snaphic_sums``) on chr19 for N = 16 (numpy
  and native) and 64 (native) by threads; differences of the sums, outlier counts equal or not.

Every configuration runs in its own process (peak RSS per configuration).  Prints a table, writes
``impute_speed.json`` to ``--out``.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import snaphic_common as C  # noqa: E402

RES = 10_000
MAX_DIAG = 105          # 1 Mb + 50 kb buffer
OUT_DIAG = 100


def _inputs(chrom: str, n_cells: int):
    from uchrom.fea.impute_rwr import _cells_and_source, read_cell_pixels
    from snaphic_mesc import load_cells

    cd, top = load_cells()
    ids, scool = _cells_and_source(cd, "per_cell", top[:n_cells])
    n, pix = read_cell_pixels(scool, ids, chrom)
    return n, pix, scool, top


def _window(cache: Path) -> int:
    """SnapHiC2's window for the 742 cells (computed once, cached)."""
    f = cache / "window.json"
    if f.exists():
        return json.loads(f.read_text())["window_bins"]
    from uchrom.fea.impute_rwr import ImputeParams, _cells_and_source, _resolve_window
    from snaphic_mesc import load_cells

    cd, top = load_cells()
    ids, scool = _cells_and_source(cd, "per_cell", top)
    wbp = _resolve_window(ImputeParams(), scool, ids, RES, C.MM10_AUTOSOMES)
    f.write_text(json.dumps({"window_bp": wbp, "window_bins": wbp // RES}))
    return wbp // RES


def one(args):
    from uchrom.fea import impute_rwr as IM
    from uchrom.strc.loop import snaphic as S

    w = args.window
    step = w // 2
    res = {"what": args.what, "chrom": args.chrom, "backend": args.backend, "threads": args.threads,
           "window_bins": w, "cpu": cpu_name()}
    if args.what == "band":
        n, pix, _, _ = _inputs(args.chrom, 1)
        i, j = pix[0]
        times = []
        for _ in range(3):
            t = time.perf_counter()
            band = IM.rwr_band(i, j, n, window=w, step=step, max_diag=MAX_DIAG, backend=args.backend,
                               n_threads=args.threads)
            times.append(time.perf_counter() - t)
        res.update({"n_bins": n, "n_contacts": int(len(i)), "seconds": min(times), "times": times})
        np.save(args.tmp / f"band_{args.chrom}_{args.backend}_{args.threads}.npy", band)
        # the other per-cell steps of SnapHiC (profile: where the reference spends its time)
        t = time.perf_counter()
        z = IM.zscore_band(band, edge=5, backend=args.backend, n_threads=args.threads)
        res["zscore_s"] = time.perf_counter() - t
        t = time.perf_counter()
        if args.backend == "numpy":
            S._local_background_numpy(z, OUT_DIAG, 2, 5)
        else:
            import uchrom_maps

            uchrom_maps.local_background(z, OUT_DIAG, 2, 5, args.threads)
        res["local_background_s"] = time.perf_counter() - t
    else:
        n, pix, _, _ = _inputs(args.chrom, args.n_cells)
        reps = 3 if args.backend == "native" or args.n_cells <= 16 else 1
        times = []
        for _ in range(reps):
            t = time.perf_counter()
            acc = S.snaphic_sums(n, pix, window=w, step=step, max_diag=MAX_DIAG, out_diag=OUT_DIAG,
                                 backend=args.backend, n_threads=args.threads)
            times.append(time.perf_counter() - t)
        res.update({"n_bins": n, "n_cells": args.n_cells, "seconds": min(times), "times": times})
        np.savez(args.tmp / f"sums_{args.chrom}_{args.n_cells}_{args.backend}_{args.threads}.npz",
                 **{k: v for k, v in acc.items() if k != "n_cells"})
    res["peak_rss_gb"] = C.peak_rss_gb()
    print(json.dumps(res))


def cpu_name() -> str:
    try:
        for line in open("/proc/cpuinfo"):
            if line.startswith("model name"):
                return line.split(":", 1)[1].strip()
    except OSError:
        pass
    return ""


def run_all(args):
    args.out.mkdir(parents=True, exist_ok=True)
    tmp = args.out / "arrays"
    tmp.mkdir(exist_ok=True)
    w = _window(args.out)
    rows = []

    def go(*extra):
        cmd = [sys.executable, __file__, "one", "--out", str(args.out), "--window", str(w), *extra]
        env = dict(os.environ)
        r = subprocess.run(cmd, capture_output=True, text=True, env=env)
        if r.returncode:
            print(r.stderr[-3000:], file=sys.stderr)
            raise SystemExit(f"failed: {' '.join(extra)}")
        rows.append(json.loads(r.stdout.strip().splitlines()[-1]))
        print(rows[-1], flush=True)

    for chrom in ("chr19", "chr1"):
        go("--what", "band", "--chrom", chrom, "--backend", "numpy", "--threads", "0")
        for t in args.threads:
            go("--what", "band", "--chrom", chrom, "--backend", "native", "--threads", str(t))
    for n in (16, 64):
        if n == 16:                                           # the numpy path: ~minutes per cell batch
            go("--what", "sums", "--chrom", "chr19", "--n-cells", str(n), "--backend", "numpy", "--threads", "0")
        for t in args.threads:
            go("--what", "sums", "--chrom", "chr19", "--n-cells", str(n), "--backend", "native", "--threads", str(t))
    # agreement
    agree = {}
    for chrom in ("chr19", "chr1"):
        a = np.load(tmp / f"band_{chrom}_numpy_0.npy")
        b = np.load(tmp / f"band_{chrom}_native_{args.threads[-1]}.npy")
        ok = np.isfinite(a)
        from uchrom.fea.impute_rwr import zscore_band

        za, zb = zscore_band(a, backend="numpy"), zscore_band(b, backend="native")
        agree[f"band_{chrom}"] = {"max_rel": float(np.max(np.abs(a[ok] - b[ok]) / np.abs(a[ok]))),
                                  "same_nan": bool(np.array_equal(np.isnan(a), np.isnan(b))),
                                  "z_max_abs": float(np.nanmax(np.abs(za - zb)))}
    for n in (16,):
        A = np.load(tmp / f"sums_chr19_{n}_numpy_0.npz")
        B = np.load(tmp / f"sums_chr19_{n}_native_{args.threads[-1]}.npz")
        agree[f"sums_chr19_{n}"] = {k: float(np.abs(A[k] - B[k]).max() / max(np.abs(A[k]).max(), 1e-300))
                                    for k in ("sum_z", "sum_l", "sum_d", "sum_dd")}
        agree[f"sums_chr19_{n}"]["n_out_equal"] = bool(np.array_equal(A["n_out"], B["n_out"]))
    print(json.dumps(agree, indent=1))
    hdr = (f"{'what':5s} {'chrom':6s} {'cells':>5s} {'backend':7s} {'thr':>4s} {'seconds':>9s} {'z s':>7s} "
           f"{'bg s':>7s} {'rss GB':>7s}")
    print(hdr)
    for r in rows:
        print(f"{r['what']:5s} {r['chrom']:6s} {r.get('n_cells', 1):5d} {r['backend']:7s} {r['threads']:4d} "
              f"{r['seconds']:9.3f} {r.get('zscore_s', float('nan')):7.3f} {r.get('local_background_s', float('nan')):7.3f} "
              f"{r['peak_rss_gb']:7.2f}")
    C.write_json({"rows": rows, "agreement": agree, "window_bins": w, "load": C.load_avg()},
                 args.out / "impute_speed.json")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("mode", choices=["all", "one"])
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--threads", type=int, nargs="+", default=[1, 4, 16, 32])
    ap.add_argument("--what", choices=["band", "sums"])
    ap.add_argument("--chrom", default="chr19")
    ap.add_argument("--n-cells", type=int, default=16)
    ap.add_argument("--backend", default="native")
    ap.add_argument("--window", type=int, default=0)
    args = ap.parse_args()
    if args.mode == "one":
        args.threads = args.threads[0]
        args.tmp = args.out / "arrays"
        one(args)
    else:
        run_all(args)


if __name__ == "__main__":
    main()
