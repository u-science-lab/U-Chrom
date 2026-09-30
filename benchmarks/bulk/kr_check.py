"""Check U-Chrom's Knight-Ruiz balancing against Juicer's KR vectors.

For each (file, chromosome, resolution) the intra-chromosomal raw matrix is read (HTTP range
reads: ``.mcool`` through fsspec + h5py + cooler, ``.hic`` through hicstraw), balanced with
``preprocess.kr_balance`` on the bins that Juicer kept (finite, positive KR entry), and compared
with the stored vector:

* 4DN ``.mcool`` files (converted from Juicer ``.hic`` by hic2cool) carry Juicer's per-chromosome
  KR vector as ``bins/KR``; ``.hic`` files through ``hicstraw``'s ``getNormVector``.
* Juicer's vectors are *divisive* (balanced = observed / (v_i v_j)); the script tests both
  conventions (``x ~ v`` and ``x ~ 1 / v``) and reports the one that fits.
* reported: Pearson r of log weights, the max and 99th-percentile relative deviation of the
  weight ratio from its median (a pure scale factor is allowed: Juicer scales its vector so
  that the balanced matrix keeps the total count), the row-sum spread of the matrix balanced
  with Juicer's vector (Juicer's own convergence) and with ours.

Usage::

    python benchmarks/bulk/kr_check.py --out kr_check.json            # default set (range reads, ~1 min)
    python benchmarks/bulk/kr_check.py --case imr90_4dn:chr21:25000 bonev_4dn:chr19:1000000
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np
import scipy.sparse as sp

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import BONEV_4DN, RAO_IMR90_4DN, RAO_IMR90_GEO, jdump, load_preprocess  # noqa: E402

SOURCES = {"imr90_4dn": RAO_IMR90_4DN, "bonev_4dn": BONEV_4DN, "imr90_geo": RAO_IMR90_GEO}
DEFAULT = ["imr90_4dn:chr21:1000000", "imr90_4dn:chr1:1000000", "imr90_4dn:chr21:100000",
           "imr90_4dn:chr21:25000", "bonev_4dn:chr19:1000000", "bonev_4dn:chr19:100000",
           "imr90_geo:21:50000"]


def read_mcool(url: str, chrom: str, res: int):
    import cooler
    import fsspec
    import h5py
    fh = fsspec.open(url, block_size=2 ** 22, cache_type="blockcache").open() if url.startswith("http") else open(url, "rb")
    clr = cooler.Cooler(h5py.File(fh, "r")[f"resolutions/{res}"])
    px = clr.matrix(balance=False, as_pixels=True).fetch(chrom)
    b = clr.bins().fetch(chrom)
    off = int(b.index[0])
    n = len(b)
    m = sp.coo_matrix((px["count"].to_numpy(float), (px.bin1_id.to_numpy() - off, px.bin2_id.to_numpy() - off)),
                      shape=(n, n)).tocsr()
    return m, b["KR"].to_numpy(float)


def read_hic(url: str, chrom: str, res: int):
    import hicstraw
    hic = hicstraw.HiCFile(url)
    sizes = {c.name: (c.index, c.length) for c in hic.getChromosomes()}
    idx, L = sizes[chrom]
    zd = hic.getMatrixZoomData(chrom, chrom, "observed", "KR", "BP", res)
    v = np.asarray(zd.getNormVector(idx), float)
    zd0 = hic.getMatrixZoomData(chrom, chrom, "observed", "NONE", "BP", res)
    recs = zd0.getRecords(0, L, 0, L)
    x = np.fromiter((r.binX for r in recs), np.int64, len(recs)) // res
    y = np.fromiter((r.binY for r in recs), np.int64, len(recs)) // res
    c = np.fromiter((r.counts for r in recs), float, len(recs))
    n = int(np.ceil(L / res))
    m = sp.coo_matrix((c, (np.minimum(x, y), np.maximum(x, y))), shape=(n, n)).tocsr()
    return m, v[:n]


def compare(m, v, pp) -> dict:
    u = pp.canonical_upper(m)
    ok = np.isfinite(v) & (v > 0)
    w, info = pp.kr_balance(u, mask=~ok)
    both = ok & np.isfinite(w)
    A = pp.symmetrize_upper(u)
    res = {"n_bins": int(len(v)), "n_juicer_kept": int(ok.sum()), "n_ours_kept": int(np.isfinite(w).sum()),
           "kr_info": info}
    lw, lv = np.log(w[both]), np.log(v[both])
    r_mult, r_div = float(np.corrcoef(lw, lv)[0, 1]), float(np.corrcoef(lw, -lv)[0, 1])
    conv = "multiplicative" if r_mult > r_div else "divisive"
    mult = v if conv == "multiplicative" else 1.0 / v
    ratio = w[both] / mult[both]
    dev = np.abs(ratio / np.median(ratio) - 1)
    res.update({"juicer_convention": conv, "pearson_log_weights": max(r_mult, r_div),
                "max_rel_dev": float(dev.max()), "p99_rel_dev": float(np.quantile(dev, 0.99)),
                "median_rel_dev": float(np.median(dev))})
    keep = np.flatnonzero(both)
    B = A[keep][:, keep]
    for name, x in (("juicer", mult[keep]), ("ours", w[keep])):
        rs = x * (B @ x)
        res[f"rowsum_cv_{name}"] = float(np.std(rs) / np.mean(rs))
    return res


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--case", nargs="+", default=DEFAULT, help="source:chrom:resolution")
    ap.add_argument("--source", nargs="*", default=[], help="NAME=URL_OR_PATH overrides / additions")
    ap.add_argument("--out", type=Path)
    args = ap.parse_args(argv)
    src = dict(SOURCES)
    src.update(dict(s.split("=", 1) for s in args.source))
    pp = load_preprocess()
    out = {}
    for case in args.case:
        name, chrom, res = case.split(":")
        t0 = time.time()
        url = src[name]
        try:
            m, v = (read_hic if url.endswith(".hic") else read_mcool)(url, chrom, int(res))
            r = compare(m, v, pp)
        except Exception as e:  # report and go on (network, missing module)
            r = {"error": f"{type(e).__name__}: {e}"}
        r["seconds"] = time.time() - t0
        r["source"] = url
        out[case] = r
        print(case, jdump({k: v for k, v in r.items() if k not in ("kr_info", "source")}).replace("\n", " "), flush=True)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(jdump(out))


if __name__ == "__main__":
    main()
