"""Compact per-panel arrays for Fig. 3 from the real data (run once; small output).

Writes ``results/fig3_panels.npz``:

* ``hic_map`` / ``img_map`` / ``med_dist``: IMR90 chr21:28-30 Mb, 65 x 30 kb segments;
  Rao 2014 IMR90 raw Hi-C counts (5 kb summed into the segments) and the contact
  frequency of Bintu et al. 2018 traces (distance < 200 nm among traces with both
  segments), median distance per pair (nm) -- the same definitions as
  ``benchmarks/fig3/b_first_look.py``.
* ``nd_pub_d`` / ``nd_ours_d``: Stevens et al. 2017 Cell 1, 20,000 random
  intra-chromosomal particle pairs, distance (particle radii) in published model 1
  (GEO) and in native-engine GPU model 1 (Sherlock run, full schedule).

    python paper/fig3/prepare_fig3.py --data example-data --nd-run <dir with native_gpu_full/cell1.npz>
"""

from __future__ import annotations

import argparse
import gzip
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "benchmarks" / "fig3"))
from b_first_look import SEG, hic_segments, load_bintu  # noqa: E402

CHAINS = {chr(ord("a") + i): f"chr{i + 1}" for i in range(19)} | {"t": "chrX"}


def read_pdb(path: Path):
    """First model of a GEO extended PDB -> chrom, pos, coords (N, 3)."""
    rows = []
    with gzip.open(path, "rt") as fh:
        for line in fh:
            if line.startswith("HETATM"):
                rows.append((CHAINS.get(line[21], line[21]), int(line.split()[-1]),
                             float(line[30:38]), float(line[38:46]), float(line[46:54])))
            elif line.startswith("ENDMDL"):
                break
    return (np.array([r[0] for r in rows]), np.array([r[1] for r in rows], np.int64),
            np.array([r[2:] for r in rows]))


def bintu_maps(data: Path, radius_nm: float = 200.0):
    df = load_bintu(data / "bintu2018" / "IMR90_chr21-28-30Mb.csv", 29_372_390)
    segs = np.sort(df["seg"].unique())
    starts = 29_372_390 + (segs - 1) * SEG
    n = len(segs)
    traces = df["trace_id"].unique()
    X = np.full((len(traces), n, 3), np.nan)
    ti = {t: i for i, t in enumerate(traces)}
    si = {s: i for i, s in enumerate(segs)}
    X[df["trace_id"].map(ti).to_numpy(), df["seg"].map(si).to_numpy()] = df[["x", "y", "z"]].to_numpy()
    D = np.linalg.norm(X[:, :, None, :] - X[:, None, :, :], axis=-1)       # traces x n x n (nm)
    ok = np.isfinite(D)
    img = np.where(ok, D < radius_nm, False).sum(0) / np.maximum(ok.sum(0), 1)
    med = np.nanmedian(D, axis=0)
    hic = hic_segments(data / "rao2014_imr90" / "IMR90_chr21_5kb_hg19.cool", "chr21", starts, SEG)
    return hic, img, med


def nd_pairs(data: Path, run: Path, n: int = 20_000, seed: int = 0):
    ch_p, pos_p, Xp = read_pdb(data / "stevens2017_mesc" / "GSM2219497_Cell_1_genome_structure_model.pdb.gz")
    z = np.load(run / "native_gpu_full" / "cell1.npz")
    key = {(c, p): i for i, (c, p) in enumerate(zip(z["chrom"], z["pos"]))}
    ib = np.array([key.get((c, p), -1) for c, p in zip(ch_p, pos_p)])
    keep = ib >= 0
    ch, Xp, Xo = ch_p[keep], Xp[keep], z["coords"][0][ib[keep]]
    rng = np.random.default_rng(seed)
    i = rng.integers(0, len(ch), n)                       # partner on the same chromosome
    lo = np.searchsorted(ch, ch[i], "left") if np.all(ch[:-1] <= ch[1:]) else None
    if lo is None:
        order = np.argsort(ch, kind="stable")
        ch, Xp, Xo = ch[order], Xp[order], Xo[order]
        i = rng.integers(0, len(ch), n)
        lo = np.searchsorted(ch, ch[i], "left")
    hi = np.searchsorted(ch, ch[i], "right")
    j = lo + (rng.random(n) * (hi - lo)).astype(int)
    m = i != j
    i, j = i[m], j[m]
    return np.linalg.norm(Xp[i] - Xp[j], axis=1), np.linalg.norm(Xo[i] - Xo[j], axis=1)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", type=Path, default=ROOT / "example-data")
    ap.add_argument("--nd-run", type=Path, required=True)
    ap.add_argument("--out", type=Path, default=HERE / "results" / "fig3_panels.npz")
    args = ap.parse_args()
    hic, img, med = bintu_maps(args.data)
    pub_d, ours_d = nd_pairs(args.data, args.nd_run)
    np.savez_compressed(args.out, hic_map=hic, img_map=img, med_dist=med, nd_pub_d=pub_d, nd_ours_d=ours_d)
    print(args.out, hic.shape, f"nd pairs {len(pub_d)}, r = {np.corrcoef(pub_d, ours_d)[0, 1]:.3f}")


if __name__ == "__main__":
    main()
