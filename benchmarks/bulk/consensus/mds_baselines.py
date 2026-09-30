"""Consensus-structure baselines on the SAME balanced input as the method (same bins, same KR
balancing and coverage filter: ``uchrom.recon.bulk.consensus`` loader).

* ``mds_full``   U-Chrom PyTorch MDS (``uchrom.recon.bulk.mds.run_mds``, full mode = one MDS of the
                 whole matrix, alpha = 4, miniMDS-style decay prior w = 0.05) on the genome-wide
                 matrix (cis + trans) when it has <= --max-full bins; otherwise not run.
* ``mds_chrom``  the same, one MDS per chromosome (cis only; chromosomes placed independently).
* ``minimds``    miniMDS (Rieber & Mahony 2017, github.com/seqcode/miniMDS @ 9915d21) FULL mode
                 (no partitioning), one run per chromosome (miniMDS models one chromosome per call),
                 defaults (alpha 4, w 0.05); needs ``--minimds-dir`` (a clone) and runs with this Python.
HIPPS mean distances (``<r_ij> = p_ij^-1/4``) and IGM population mean distances are distance-matrix
models evaluated on the imaging loci directly by ``score.py`` (``--hipps``, ``--igm``).

    python benchmarks/bulk/consensus/mds_baselines.py --cell imr90 --resolution 250000 \
        --methods mds_full mds_chrom minimds --minimds-dir $BASE/minimds --out-dir RUNS/consensus/base/imr90_250kb
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

import _bc  # noqa: F401
from _bc import hic_source, peak_rss_gb, save_model_npz, write_json


def balanced_genome(src_path: str, res: int, chroms, params):
    """Balanced symmetric dense matrix (NaN rows = masked) + bins, the method's genome-mode loader."""
    from uchrom.recon.bulk.consensus._contacts import CoolerSource, resolve_chroms
    from uchrom.recon.bulk.consensus._restraints import load_stage

    src = CoolerSource(src_path)
    ch = resolve_chroms(src.chrom_names, chroms, params.exclude_chroms)
    px = load_stage(src, res, ch, "genome", 10 ** 9, params)
    n = len(px.bins)
    M = np.zeros((n, n))
    M[px.i, px.j] = px.b
    M[px.j, px.i] = px.b
    M[~px.valid] = 0
    M[:, ~px.valid] = 0
    return M, px.bins.reset_index(drop=True), px.valid, ch


def run_uchrom_mds(M: np.ndarray, device: str) -> tuple[np.ndarray, np.ndarray]:
    import torch
    from uchrom.recon.bulk.mds import run_mds

    c, mask = run_mds(torch.from_numpy(M.copy()), alpha=4.0, device=device)
    X = np.full((len(M), 3), np.nan)
    X[mask] = np.asarray(c)
    return X, mask


def write_bed(M: np.ndarray, bins: pd.DataFrame, path: Path) -> None:
    iu = np.triu_indices(len(M), 1)
    v = M[iu]
    k = v > 0
    c = bins["chrom"].to_numpy()
    s = bins["start"].to_numpy()
    e = bins["end"].to_numpy()
    with open(path, "w") as fh:
        for i, j, x in zip(iu[0][k], iu[1][k], v[k]):
            fh.write(f"{c[i]}\t{s[i]}\t{e[i]}\t{c[j]}\t{s[j]}\t{e[j]}\t{x:.10g}\n")


def load_minimds(path: Path, n: int, res: int) -> np.ndarray:
    with open(path) as fh:
        fh.readline()
        r = float(fh.readline())
        start = int(fh.readline())
        arr = np.loadtxt(fh, ndmin=2)
    X = np.full((n, 3), np.nan)
    if len(arr):
        X[int(start // r) + arr[:, 0].astype(int)] = arr[:, 1:4]
    return X


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cell", choices=sorted(_bc.CELLS))
    ap.add_argument("--source", default=None)
    ap.add_argument("--resolution", type=int, required=True)
    ap.add_argument("--chroms", nargs="*", default=None)
    ap.add_argument("--methods", nargs="+", default=["mds_full", "mds_chrom", "minimds"])
    ap.add_argument("--max-full", type=int, default=15000)
    ap.add_argument("--minimds-dir", default=None)
    ap.add_argument("--device", default="auto")
    ap.add_argument("--out-dir", required=True)
    a = ap.parse_args(argv)
    from uchrom.recon.bulk.consensus import ConsensusParams

    out = Path(a.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    src = a.source or hic_source(a.cell)
    p = ConsensusParams()
    t0 = time.time()
    M, bins, valid, chroms = balanced_genome(src, a.resolution, a.chroms, p)
    log = {"source": src, "resolution": a.resolution, "chroms": chroms, "n_bins": len(bins),
           "n_valid": int(valid.sum()), "seconds_load": time.time() - t0, "methods": {}}
    print(f"input: {len(bins)} bins ({int(valid.sum())} valid), {len(chroms)} chromosomes, {time.time() - t0:.0f} s", flush=True)
    chrom = bins["chrom"].astype(str).to_numpy()
    for m in a.methods:
        t = time.time()
        info = {}
        if m == "mds_full":
            if int(valid.sum()) > a.max_full:
                log["methods"][m] = {"skipped": f"{int(valid.sum())} bins > --max-full {a.max_full}"}
                continue
            X, _ = run_uchrom_mds(M, a.device)
        elif m == "mds_chrom":
            X = np.full((len(bins), 3), np.nan)
            for c in chroms:
                k = np.flatnonzero(chrom == c)
                X[k], _ = run_uchrom_mds(M[np.ix_(k, k)], a.device)
        elif m == "minimds":
            if not a.minimds_dir:
                log["methods"][m] = {"skipped": "no --minimds-dir"}
                continue
            X = np.full((len(bins), 3), np.nan)
            tmp = out / "minimds_tmp"
            tmp.mkdir(exist_ok=True)
            fails = {}
            for c in chroms:
                k = np.flatnonzero(chrom == c)
                bed, tsv = tmp / f"{c}.bed", tmp / f"{c}.tsv"
                write_bed(M[np.ix_(k, k)], bins.iloc[k], bed)
                r = subprocess.run([sys.executable, str(Path(a.minimds_dir) / "minimds.py"), "-o", str(tsv), str(bed)],
                                   capture_output=True, text=True)
                if r.returncode != 0:
                    fails[c] = r.stderr[-500:]
                    continue
                X[k] = load_minimds(tsv, len(k), a.resolution)
            info["failed_chroms"] = fails
        else:
            raise SystemExit(f"unknown method {m}")
        secs = time.time() - t
        info.update(seconds=secs, n_placed=int(np.isfinite(X).all(1).sum()))
        log["methods"][m] = info
        save_model_npz(out / f"{m}.npz", bins, X, {"model": m, "resolution": a.resolution, **info})
        print(f"{m}: {info['n_placed']} bins placed, {secs:.0f} s", flush=True)
    log["peak_rss_gb"] = peak_rss_gb()
    write_json(out / "baselines.json", log)


if __name__ == "__main__":
    main()
