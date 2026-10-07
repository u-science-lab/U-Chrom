"""Run the reference Mustache (``mustache-hic`` 1.3.3) kernels on pixels dumped by ``mustache_validate.py``.

Runs in the validation venv that has ``mustache-hic`` installed (never imported by uchrom)::

    $CTENV/bin/python mustache_reference_blocks.py pixels.npz out.npz

``pixels.npz`` holds the balanced pixels the reference reads from a ``.cool`` (``x``, ``y``, ``v``: bins and
values, ``|x - y| <= D``, ``v > 0``) and ``res``, ``D``, ``pt``, ``st``, ``sigma0``, ``octaves``.  The
script applies the reference's ``normalize_sparse`` and its block loop (``regulator`` / ``process_block``,
without the worker processes) and writes the normalised values ``z``, every block's raw calls
(``block_calls``: block, x, y, fdr, scale — before the overlap mask) and the final calls (``calls``: x, y,
fdr, scale — what the command line writes).
"""

import sys

import numpy as np
from mustache import mustache as M


def main(src, dst):
    f = np.load(src)
    x, y, v = f["x"].astype(np.int64), f["y"].astype(np.int64), f["v"].astype(np.float64).copy()
    res, D = int(f["res"]), int(f["D"])
    pt, st = float(f["pt"]), float(f["st"])
    octave_values = [float(f["sigma0"]) * (2 ** i) for i in range(int(f["octaves"]))]
    chrom = "chrN"

    n = max(x.max(), y.max()) + 1
    pval_weights = M.normalize_sparse(x, y, v, res, D)              # v normalised in place
    chunk = max(2 * D, 2000)
    overlap = D
    if n <= chunk:
        start, end = [0], [n]
    else:
        start, end = [0], [chunk]
        while end[-1] < n:
            start.append(end[-1] - overlap)
            end.append(start[-1] + chunk)
        end[-1] = n
        start[-1] = end[-1] - chunk
    block_calls, calls = [], []
    for b in range(len(start)):
        idx = (x >= start[b]) & (x < end[b]) & (y >= start[b]) & (y < end[b])
        cc = np.zeros((chunk, chunk))
        cc[x[idx] - start[b], y[idx] - start[b]] = v[idx]
        if b == 0:
            mask = -1
        elif b == len(start) - 1:
            mask = end[b - 1] - start[b]
        else:
            mask = overlap
        loops = M.mustache(cc, chrom, chrom, res, pval_weights, start[b], end[b], mask, D, octave_values, st, pt)
        for lp in loops:
            block_calls.append([b, lp[0], lp[1], lp[2], lp[3]])
            if lp[0] >= start[b] + mask or lp[1] >= start[b] + mask:
                calls.append([lp[0], lp[1], lp[2], lp[3]])
    np.savez(dst, z=v, starts=np.array(start), ends=np.array(end), chunk=chunk,
             block_calls=np.array(block_calls, dtype=np.float64).reshape(-1, 5),
             calls=np.array(calls, dtype=np.float64).reshape(-1, 4))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
