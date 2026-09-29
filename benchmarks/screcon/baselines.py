"""Structure-free baselines (anchor the scale of every test).

* ``random_polymer``: an ensemble of random-walk chains, one per chromosome, on the
  regular grid of ``--res`` spanning each chromosome's contacts (or given spans).  Steps
  are Gaussian with unit RMS length (so the bead unit is ~1); chromosome start points are
  uniform in a sphere whose radius makes the chains overlap about as much as
  chromosome territories do (R = n_particles^(1/3) bead units).  It knows nothing
  about the contacts except which chromosome regions exist, so in the held-out test its
  cis AUC is 0.5 in expectation (separation-matched negatives) and its trans AUC ~0.5.

    python benchmarks/screcon/baselines.py random_polymer --contacts train.txt.gz --res 100000 \\
        --n-models 10 --seed 1 --out RUN/random_polymer.npz
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from contacts import Grid, read_contacts  # noqa: E402
from models_io import save_npz  # noqa: E402


def random_polymer(grid: Grid, n_models: int = 10, seed: int = 0, confine: bool = True) -> np.ndarray:
    """(M, N, 3) random-walk ensembles on ``grid`` (2017 pos = bin end)."""
    rng = np.random.default_rng(seed)
    N = grid.n
    R = max(N, 1) ** (1 / 3)
    X = np.zeros((n_models, N, 3))
    for m in range(n_models):
        for c in grid.chroms:
            o, nb = grid.offset[c], grid.nbins[c]
            steps = rng.normal(size=(nb, 3)) / np.sqrt(3)
            steps[0] = 0
            chain = np.cumsum(steps, 0)
            chain -= chain.mean(0)
            v = rng.normal(size=3)
            start = v / np.linalg.norm(v) * R * rng.random() ** (1 / 3) if confine else 0
            X[m, o:o + nb] = chain + start
    return X


def cmd_random_polymer(args) -> None:
    c = read_contacts(args.contacts)
    grid = Grid.from_contacts(c, args.res)
    X = random_polymer(grid, args.n_models, args.seed)
    save_npz(args.out, grid.chrom, (grid.bin + 1) * grid.res, X)
    print(f"random polymer: {X.shape} -> {args.out}")


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("random_polymer")
    r.add_argument("--contacts", required=True)
    r.add_argument("--res", type=int, default=100_000)
    r.add_argument("--n-models", type=int, default=10)
    r.add_argument("--seed", type=int, default=1)
    r.add_argument("--out", required=True)
    r.set_defaults(fn=cmd_random_polymer)
    args = ap.parse_args(argv)
    args.fn(args)


if __name__ == "__main__":
    main()
