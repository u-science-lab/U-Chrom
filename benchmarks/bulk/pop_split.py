"""Cell split of the EMber-pop benchmark (``PREREG_POP.md`` section 2), fixed before any run.

Every imaged cell of a truth dataset is assigned to exactly one set:

* ``su2020_genome`` (1,787 cells): cells in the order of ``truths.su2020_genome`` (experiment,
  cell), permuted by ``numpy.random.default_rng(20261007)``; positions 0-446 ``dev_bulk``,
  447-893 ``dev_truth``, 894-1340 ``test_bulk``, 1341-1786 ``test_truth``.
* ``takei2021_1mb`` (201 cells, held back entirely): cells in the order of
  ``truths.takei2021_1mb``, permuted by the same generator seed; positions 0-99 ``test_bulk``,
  100-200 ``test_truth``.

``*_bulk`` cells make the simulated population Hi-C, ``*_truth`` cells are the held-out truth
population the reconstructions are compared with.  Output: ``data/pop_split.tsv``
(``dataset``, ``cell_id``, ``set``)::

    python benchmarks/bulk/pop_split.py --out benchmarks/bulk/data/pop_split.tsv
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _common  # noqa: E402,F401
from truths import load_dataset  # noqa: E402

SEED = 20261007


def split_ids(ids: list[str], sizes: list[tuple[str, int]]) -> pd.DataFrame:
    perm = np.random.default_rng(SEED).permutation(len(ids))
    out, k = [], 0
    for name, n in sizes:
        out += [(ids[p], name) for p in perm[k:k + n]]
        k += n
    assert k == len(ids), (k, len(ids))
    return pd.DataFrame(out, columns=["cell_id", "set"])


def load_split(path=None) -> pd.DataFrame:
    return pd.read_csv(path or Path(__file__).resolve().parent / "data" / "pop_split.tsv", sep="\t", dtype=str)


def cells_of(dataset: str, sets, path=None) -> list[str]:
    sp = load_split(path)
    sets = [sets] if isinstance(sets, str) else list(sets)
    return sp[(sp.dataset == dataset) & sp.set.isin(sets)].cell_id.tolist()


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)
    frames = []
    su = load_dataset("su2020_genome").meta["cell_ids"]
    assert len(su) == 1787
    frames.append(split_ids(su, [("dev_bulk", 447), ("dev_truth", 447), ("test_bulk", 447), ("test_truth", 446)])
                  .assign(dataset="su2020_genome"))
    tk = load_dataset("takei2021_1mb").meta["cell_ids"]
    assert len(tk) == 201
    frames.append(split_ids(tk, [("test_bulk", 100), ("test_truth", 101)]).assign(dataset="takei2021_1mb"))
    df = pd.concat(frames)[["dataset", "cell_id", "set"]]
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(args.out, sep="\t", index=False)
    print(df.groupby(["dataset", "set"]).size().to_string())


if __name__ == "__main__":
    main()
