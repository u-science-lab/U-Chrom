"""ChromData stores for the high-resolution diploid renders of Fig. 3 (scMicro-C GM12878, Wu et al. 2025).

Input: EMber diploid models (``benchmarks/screcon/run_diploid.py`` ``.npz``: copy chains ``chr1(0)`` /
``chr1(1)``, hap 0 = paternal; ``pos`` = particle end).  One model (``--model``, default 0).

* ``genome``: every copy chain of one model, one trace per chain (``chr7(pat)`` / ``chr7(mat)``; chrom
  ``chr7``), coordinates centred and rotated onto the model's principal axes (x: largest extent,
  y: second; so the default camera of the browser looks along the shortest axis).
* ``--zoom chr:start-end``: the same region of one copy (``--zoom-copy``, default pat) from each
  ``--zoom-npz`` (e.g. 5 kb and the exploratory 2 kb / 1 kb runs), one store per input, each centred
  and rotated onto the principal axes of the region at the first input's resolution (the finer
  models brought onto it by a similarity transform fitted on matched positions, as
  ``build_render_hires.py``).  Units: particle radii of each run.

    python paper/fig3/build_render_scmicroc.py --npz RUN/res5000_s1.npz --name gm12878_cell035_5kb \\
        --zoom chr7:26000000-29000000 --zoom-npz RUN/res5000_s1.npz RUN/res2000_s1.npz
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
OUT = HERE / "renders" / "highres"
HAP = {0: "pat", 1: "mat"}
COPY_RE = re.compile(r"^(.*)\((\d)\)$")


def load(path: Path, model: int):
    z = np.load(path, allow_pickle=False)
    X = z["coords"]
    X = X[model] if X.ndim == 3 else X
    return z["chrom"].astype(str), z["pos"].astype(np.int64), X.astype(np.float64)


def split(names):
    base, hap = [], []
    for n in names:
        m = COPY_RE.match(n)
        base.append(m.group(1) if m else n)
        hap.append(HAP[int(m.group(2))] if m else "single")
    return np.array(base), np.array(hap)


def principal(X: np.ndarray):
    """Centre + rotation onto principal axes (x: largest variance), proper rotation; returns a function."""
    mu = X.mean(0)
    _, _, Vt = np.linalg.svd(X - mu, full_matrices=False)
    R = Vt.T
    if np.linalg.det(R) < 0:
        R[:, 2] *= -1
    return lambda Y: (Y - mu) @ R


def umeyama(src, dst):
    ms, md = src.mean(0), dst.mean(0)
    a, b = src - ms, dst - md
    U, S, Vt = np.linalg.svd(b.T @ a / len(a))
    d = np.sign(np.linalg.det(U @ Vt))                 # proper rotation only (same chirality)
    D = np.diag([1, 1, d])
    R = U @ D @ Vt
    s = (S * np.diag(D)).sum() / (a ** 2).sum(1).mean()
    return lambda X: (X - ms) @ R.T * s + md


def store(chrom, hap, pos, X, res, cell, uns, out: Path):
    from uchrom import ChromData
    spots = pd.DataFrame({"chrom": chrom, "start": pos - res, "end": pos, "cell_id": cell,
                          "trace_id": [f"{c}({h})" if h != "single" else c for c, h in zip(chrom, hap)]})
    cd = ChromData(X, spots, uns=uns)
    out.parent.mkdir(parents=True, exist_ok=True)
    cd.write(out)
    print(out, cd.coords.shape)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--npz", type=Path, required=True)
    ap.add_argument("--name", required=True)
    ap.add_argument("--model", type=int, default=0)
    ap.add_argument("--cell", default="GM12878 scMicro-C")
    ap.add_argument("--zoom")
    ap.add_argument("--zoom-copy", default="pat")
    ap.add_argument("--zoom-npz", type=Path, nargs="*", default=[])
    args = ap.parse_args()
    ch, pos, X = load(args.npz, args.model)
    base, hap = split(ch)
    res = int(np.median(np.diff(pos)[ch[1:] == ch[:-1]]))
    uns = {"genome_assembly": "hg38", "xyz_unit": "particle radius",
           "description": f"EMber (U-Chrom) diploid, {args.cell}, {res // 1000} kb, model {args.model}",
           "source": str(args.npz.name)}
    store(base, hap, pos, principal(X)(X), res, args.cell, uns, OUT / f"{args.name}.chromdata.zarr")
    if not args.zoom:
        return
    zc, lo, hi = re.match(r"^(\w+):(\d+)-(\d+)$", args.zoom).groups()
    lo, hi = int(lo), int(hi)
    first = None
    for path in args.zoom_npz:
        ch, pos, X = load(path, args.model)
        base, hap = split(ch)
        r = int(np.median(np.diff(pos)[ch[1:] == ch[:-1]]))
        sel = (base == zc) & (hap == args.zoom_copy) & (pos > lo) & (pos <= hi)
        p, Y = pos[sel], X[sel]
        if first is None:
            f = principal(Y)
            first = (p, f(Y), r)
            Y = first[1]
        else:                                          # onto the first input via its bins
            p0, Y0, r0 = first
            blk = np.searchsorted(p0, np.ceil(p / r0) * r0)
            ok = (blk < len(p0)) & (p0[np.minimum(blk, len(p0) - 1)] == np.ceil(p / r0) * r0)
            M = np.stack([np.bincount(blk[ok], weights=Y[ok, k], minlength=len(p0)) for k in range(3)], 1)
            n = np.bincount(blk[ok], minlength=len(p0))
            use = n > 0
            Y = umeyama(M[use] / n[use, None], Y0[use])(Y)
        tag = f"{r // 1000}kb" if r >= 1000 else f"{r}bp"
        store(np.full(len(p), zc), np.full(len(p), args.zoom_copy), p, Y, r, args.cell,
              {**uns, "description": f"EMber (U-Chrom) diploid, {args.zoom} ({args.zoom_copy}), {tag}",
               "source": str(path.name)},
              OUT / f"{args.name}_zoom_{zc}_{lo // 1_000_000}_{hi // 1_000_000}M_{tag}.chromdata.zarr")


if __name__ == "__main__":
    main()
