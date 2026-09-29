"""ChromData of Stevens 2017 Cell 1 at 100 kb, 10 kb and 1 kb (U-Chrom GPU, model 1 each) for renders.

Each resolution has its own length unit (consecutive particles ~1 apart), so the 10 kb and 1 kb
models are brought onto the 100 kb model by a similarity transform (Umeyama: rotation, mirror,
isotropic scale, translation) fitted on their 100 kb block means.  Three "cells" named by
resolution, one trace per chromosome.

    python paper/fig3/build_render_hires.py      # reads renders/hires/cell1_<res>_model1.npz
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
D = HERE / "renders" / "hires"


def load(tag):
    z = np.load(D / f"cell1_{tag}_model1.npz")
    return z["chrom"].astype(str), z["pos"].astype(np.int64), z["coords"].astype(np.float64)


def umeyama(src, dst):
    """Similarity transform (mirror allowed) mapping src (N x 3) onto dst; returns a function."""
    ms, md = src.mean(0), dst.mean(0)
    a, b = src - ms, dst - md
    U, S, Vt = np.linalg.svd(b.T @ a / len(a))
    R = U @ Vt                                  # proper or improper rotation (mirror allowed)
    s = S.sum() / (a ** 2).sum(1).mean()
    return lambda X: (X - ms) @ R.T * s + md


def main() -> None:
    from uchrom import ChromData

    cc, cp, C = load("100kb")
    key = {(c, p): i for i, (c, p) in enumerate(zip(cc, cp))}
    frames, xyz = [], []
    for tag, size in (("100kb", 100_000), ("10kb", 10_000), ("1kb", 1_000)):
        ch, pos, X = load(tag)
        if tag != "100kb":
            blk = np.array([key.get((c, int(np.ceil(p / 100_000) * 100_000)), -1) for c, p in zip(ch, pos)])
            ok = blk >= 0
            n = len(cc)
            cnt = np.bincount(blk[ok], minlength=n)
            M = np.stack([np.bincount(blk[ok], weights=X[ok, k], minlength=n) for k in range(3)], 1)
            use = cnt > 0
            M = M[use] / cnt[use, None]
            X = umeyama(M, C[use])(X)
        xyz.append(X)
        frames.append(pd.DataFrame({"chrom": ch, "start": pos - size, "end": pos, "cell_id": tag,
                                    "trace_id": [f"{tag}:{c}" for c in ch]}))
        print(tag, X.shape)
    cd = ChromData(np.vstack(xyz), pd.concat(frames, ignore_index=True),
                   uns={"genome_assembly": "mm10", "xyz_unit": "100 kb particle spacing",
                        "description": "Stevens 2017 Cell 1, U-Chrom GPU model 1 at 100 / 10 / 1 kb"})
    out = HERE / "renders" / "stevens_cell1_hires.chromdata.zarr"
    cd.write(out)
    print(out, cd)


if __name__ == "__main__":
    main()
