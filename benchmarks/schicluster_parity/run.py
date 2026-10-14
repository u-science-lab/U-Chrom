"""U-Chrom's scHiCluster against the authors' code on real cells: the imputed maps, the binarised features and the
time, for every cell of a .scool and chromosomes chr1-19.

    python run.py --side authors --scool contacts_cells_1Mb.scool --out OUT [--n-cells N] [--workers 8]
    python run.py --side uchrom  --scool contacts_cells_1Mb.scool --out OUT [--n-cells N]
    python run.py --compare OUT

``authors``: the body of ``schicluster.schicluster.impute_cpu`` (PyPI 1.3.2; the cell's upper-triangle pixels in
place of its text file) in a process pool, then ``hicluster_cpu``'s binarisation (each cell's values above their
80th percentile); never imports uchrom.  ``uchrom``: ``uchrom.emb.hic.schicluster_impute`` on batches of the
cells' maps as ``scool_cell_features`` builds them, the same binarisation.  Each side writes, per chromosome, the
binarised matrix (``np.packbits``), the imputed maps of three cells, and the time.  ``--compare`` writes
``results/parity.json``: per chromosome the fraction of identical binarised entries and cells, the largest
difference of the imputed maps, the times.  The times include reading each cell's chromosome with cooler: in the
authors' process pool for theirs, one cell after the other in this script for U-Chrom's (the I/O dominates it);
the library's own path (``scool_cell_features`` reads each cell once) is timed by the agent benchmark's R4.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np

AUTOSOMES = [f"chr{i}" for i in range(1, 20)]
SAMPLE = (0, 1, 2)


def cells_and_bins(scool):
    import cooler

    names = [c.split("/")[-1] for c in cooler.fileops.list_scool_cells(scool)]
    first = cooler.Cooler(f"{scool}::/cells/{names[0]}")
    return names, first


def pixels(scool, cell, chrom):
    import cooler

    clr = cooler.Cooler(f"{scool}::/cells/{cell}")
    px = clr.matrix(balance=False, as_pixels=True, join=False).fetch(chrom)
    lo = clr.offset(chrom)
    return px["bin1_id"].to_numpy() - lo, px["bin2_id"].to_numpy() - lo, px["count"].to_numpy(float)


def _authors_one(args):
    """``impute_cpu`` of schicluster 1.3.2 with the pixels in place of ``np.loadtxt``."""
    from scipy.sparse import csr_matrix

    import schicluster.schicluster as S

    scool, cell, chrom, ngene = args
    b1, b2, v = pixels(scool, cell, chrom)
    A = csr_matrix((v, (b1, b2)), shape=(ngene, ngene)).toarray()
    A = np.log2(A + A.T + 1)
    A = S.neighbor_ave_cpu(A, 1)
    return S.random_walk_cpu(A, 0.5).reshape(-1)


def side(a):
    names, first = cells_and_bins(a.scool)
    names = names[:a.n_cells] if a.n_cells else names
    out = Path(a.out) / a.side
    out.mkdir(parents=True, exist_ok=True)
    times = {}
    for chrom in AUTOSOMES:
        n = int(first.extent(chrom)[1] - first.extent(chrom)[0])
        t0 = time.perf_counter()
        if a.side == "authors":
            assert "uchrom" not in sys.modules
            from multiprocessing import Pool

            with Pool(a.workers) as p:
                Q = np.stack(p.map(_authors_one, [(a.scool, c, chrom, n) for c in names], chunksize=16))
        else:
            from uchrom.emb.hic import schicluster_impute

            Q = np.empty((len(names), n * n))
            for s in range(0, len(names), 256):
                block = names[s:s + 256]
                m = np.zeros((len(block), n * n))
                for j, c in enumerate(block):
                    r, q, v = pixels(a.scool, c, chrom)
                    off = r != q
                    m[j] = np.bincount(np.concatenate([r * n + q, (q * n + r)[off]]),
                                       weights=np.concatenate([v, v[off]]), minlength=n * n)
                Q[s:s + len(block)] = schicluster_impute(m.reshape(-1, n, n)).reshape(len(block), -1)
        binar = Q > np.percentile(Q, 80, axis=1)[:, None]
        times[chrom] = time.perf_counter() - t0
        np.save(out / f"{chrom}_bits.npy", np.packbits(binar, axis=1))
        np.save(out / f"{chrom}_sample.npy", Q[list(SAMPLE)])
        print(a.side, chrom, n, f"{times[chrom]:.1f} s", flush=True)
    (out / "times.json").write_text(json.dumps({"times_s": times, "n_cells": len(names),
                                                "workers": a.workers if a.side == "authors" else None}))


def compare(out):
    out = Path(out)
    ta = json.loads((out / "authors" / "times.json").read_text())
    tu = json.loads((out / "uchrom" / "times.json").read_text())
    res = {"n_cells": ta["n_cells"], "per_chrom": {}, "time_authors_s": sum(ta["times_s"].values()),
           "time_uchrom_s": sum(tu["times_s"].values()), "authors_workers": ta["workers"]}
    for chrom in AUTOSOMES:
        a = np.unpackbits(np.load(out / "authors" / f"{chrom}_bits.npy"), axis=1)
        u = np.unpackbits(np.load(out / "uchrom" / f"{chrom}_bits.npy"), axis=1)
        sa, su = np.load(out / "authors" / f"{chrom}_sample.npy"), np.load(out / "uchrom" / f"{chrom}_sample.npy")
        res["per_chrom"][chrom] = {"entries_identical": float((a == u).mean()),
                                   "cells_identical": float((a == u).all(axis=1).mean()),
                                   "sample_max_abs_diff": float(np.abs(sa - su).max()),
                                   "sample_max_rel_diff": float((np.abs(sa - su) / np.maximum(np.abs(sa), 1e-300)).max()),
                                   "time_authors_s": ta["times_s"][chrom], "time_uchrom_s": tu["times_s"][chrom]}
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from _record import save

    res["time_note"] = ("both times include reading each cell's chromosome with cooler: the authors' in an 8-process "
                        "pool, U-Chrom's one cell after the other in this script")
    save(Path(__file__).resolve().parent / "results" / "parity.json", res, script=__file__,
         datasets=["schicar_mop"], params={"authors": "schicluster 1.3.2 (PyPI)", "pad": 1, "rp": 0.5, "prct": 20})
    print(json.dumps({k: v for k, v in res.items() if k != "per_chrom"}, indent=1))
    worst = min(res["per_chrom"].items(), key=lambda kv: kv[1]["entries_identical"])
    print("worst chromosome", worst)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--side", choices=("authors", "uchrom"))
    ap.add_argument("--scool")
    ap.add_argument("--out", required=True)
    ap.add_argument("--n-cells", type=int, default=0)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--compare", action="store_true")
    a = ap.parse_args()
    compare(a.out) if a.compare else side(a)


if __name__ == "__main__":
    main()
