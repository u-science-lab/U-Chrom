"""Imaging truth populations for the bulk deconvolution benchmark.

* ``su2020_genome`` - Su et al. 2020 (Cell 182:1641) IMR90 genome-scale DNA-MERFISH, Zenodo
  3928890 ``genomic-scale.tsv``: 1,041 loci of 100 kb (~3 Mb spacing) on chr1-22 and chrX,
  1,787 cells from 3 experiments (431 / 917 / 439), **both homologs resolved by the
  experiment** (``homolog number`` 1 / 2), per-spot distance to the nuclear lamina, hg38,
  16 % of positions missing.  -> Population (1787, 2, 1041, 3) + lamina (1787, 2, 1041).
  The genomic coordinates are used as given (``chr1:2950000-3050000`` -> start 2,950,000,
  end 3,050,000; 100 kb loci).
* ``su2020_chr21`` - Su 2020 chr21, 651 x 50 kb, one trace per imaged chromosome copy
  (``chromosome21.tsv``; reader ``benchmarks/screcon/truth.read_su2020``); copies are not
  paired into cells in the file, so each copy is one single-chromosome structure
  (Population (n_copies, 1, 651, 3)); ``min_detect`` keeps well-detected copies.
* ``takei2021_1mb`` - Takei et al. 2021 (Nature 590:344) mESC DNA seqFISH+ 1 Mb, 4DN
  4DNFIFLJGGNR: 2,460 loci, 201 cells; homologs are **not** resolved in the table and are
  separated by the screcon heuristic (``truth.split_homologs``, constrained 2-means; median
  97.8 % of spots on the right homolog on the 25 kb control).  A (cell, chromosome) keeps both
  copies when accepted (separation >= ``min_sep`` = 1 Rg, detection of *each* copy >=
  ``min_detect`` = 0.4), else both are NaN; chrX / chrY (E14 is male) are single copy (copy 0).
  Flagged ``homolog_assignment = heuristic`` in ``meta``.  Acceptance: 3,262 of 3,819 diploid
  (cell, chromosome) pairs, 43 % of positions missing (with ``min_detect=0.6``, screcon's
  per-copy threshold: 2,084 accepted, 59 % missing).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

import _common  # noqa: F401  (sys.path for screcon)
from contacts import sort_chroms
from population import Population
from truth import _loci_table, dedupe_single_copy, read_fofct, read_su2020, split_homologs


def _chrom_key(chrom) -> np.ndarray:
    order = {c: i for i, c in enumerate(sort_chroms(pd.unique(np.asarray(chrom))))}
    return np.array([order[c] for c in chrom])


def su2020_genome(path, experiments=None) -> Population:
    df = pd.read_csv(path, sep="\t")
    df.columns = ["z", "x", "y", "g", "hom", "cell", "exp", "lam"]
    if experiments is not None:
        df = df[df.exp.isin(list(experiments))]
    g = df.g.drop_duplicates()
    parts = g.str.extract(r"^(chr[^:]+):(\d+)-(\d+)$")
    loci = pd.DataFrame({"g": g.to_numpy(), "chrom": parts[0].to_numpy(), "start": parts[1].astype(np.int64).to_numpy(),
                         "end": parts[2].astype(np.int64).to_numpy()})
    loci["_k"] = _chrom_key(loci.chrom)
    loci = loci.sort_values(["_k", "start"]).reset_index(drop=True)
    li = pd.Series(np.arange(len(loci)), index=loci.g)
    cells = df[["exp", "cell"]].drop_duplicates().sort_values(["exp", "cell"]).reset_index(drop=True)
    ci = {(e, c): k for k, (e, c) in enumerate(zip(cells.exp, cells.cell))}
    S, L = len(cells), len(loci)
    X = np.full((S, 2, L, 3), np.nan, np.float32)
    lam = np.full((S, 2, L), np.nan, np.float32)
    s = np.array([ci[k] for k in zip(df.exp, df.cell)])
    h = df.hom.to_numpy() - 1
    l = li[df.g.to_numpy()].to_numpy()
    X[s, h, l] = df[["x", "y", "z"]].to_numpy(np.float32)
    lam[s, h, l] = df.lam.to_numpy(np.float32)
    meta = {"dataset": "su2020_genome", "source": str(path), "unit": "nm", "assembly": "hg38",
            "n_cells": S, "cells_per_experiment": cells.groupby("exp").size().to_dict(),
            "homolog_assignment": "experimental (homolog number column)",
            "cell_ids": [f"e{e}_c{c}" for e, c in zip(cells.exp, cells.cell)],
            "missing_fraction": float(np.isnan(X[..., 0]).mean())}
    return Population(loci.chrom.to_numpy(), loci.start.to_numpy(), loci.end.to_numpy(), X, lam, meta)


def su2020_chr21(path, min_detect: float = 0.0) -> Population:
    loci, X = read_su2020(path)
    det = np.isfinite(X).all(2).mean(1)
    keep = det >= min_detect
    meta = {"dataset": "su2020_chr21", "source": str(path), "unit": "nm", "assembly": "hg38",
            "n_copies_total": int(len(X)), "min_detect": min_detect, "n_structures": int(keep.sum()),
            "note": "one chromosome copy per structure (copies are not paired into cells in the file)"}
    return Population(loci.chrom.to_numpy(), loci.start.to_numpy(), loci.end.to_numpy(), X[keep][:, None], meta=meta)


def takei2021_1mb(path, min_sep: float = 1.0, min_detect: float = 0.4, single_copy=("chrX", "chrY")) -> Population:
    df = read_fofct(path)
    loci = _loci_table(df)
    key = {(c, s): i for i, (c, s) in enumerate(zip(loci.Chrom, loci.Chrom_Start))}
    df["li"] = [key[k] for k in zip(df.Chrom, df.Chrom_Start)]
    nloc = loci.groupby("Chrom").size().to_dict()
    cells = sorted(df.Cell_ID.unique(), key=str)
    ci = {c: k for k, c in enumerate(cells)}
    L = len(loci)
    X = np.full((len(cells), 2, L, 3), np.nan, np.float32)
    stats = {"accepted": 0, "rejected": 0, "single_copy": 0}
    for (cell, chrom), d in df.groupby(["Cell_ID", "Chrom"]):
        xyz = d[["X", "Y", "Z"]].to_numpy()
        li = d.li.to_numpy()
        k = ci[cell]
        if chrom in single_copy:
            lab = dedupe_single_copy(xyz, li)
            X[k, 0, li[lab == 0]] = xyz[lab == 0]
            stats["single_copy"] += 1
            continue
        lab, sep = split_homologs(xyz, li)
        det = [(lab == c).sum() / nloc[chrom] for c in (0, 1)]
        if sep >= min_sep and min(det) >= min_detect:
            for c in (0, 1):
                X[k, c, li[lab == c]] = xyz[lab == c]
            stats["accepted"] += 1
        else:
            stats["rejected"] += 1
    meta = {"dataset": "takei2021_1mb", "source": str(path), "unit": "nm", "assembly": "mm10",
            "n_cells": len(cells), "cell_ids": [str(c) for c in cells],
            "homolog_assignment": "heuristic constrained 2-means (benchmarks/screcon/truth.split_homologs)",
            "min_sep": min_sep, "min_detect": min_detect, "single_copy": list(single_copy), "chromosomes": stats,
            "missing_fraction": float(np.isnan(X[..., 0]).mean())}
    return Population(loci.Chrom.to_numpy(), loci.Chrom_Start.to_numpy(), loci.Chrom_End.to_numpy(), X, meta=meta)


DATASETS = {
    "su2020_genome": ("su2020_imr90/genomic-scale.tsv", su2020_genome),
    "su2020_chr21": ("su2020_imr90/chromosome21.tsv", su2020_chr21),
    "takei2021_1mb": ("4DNFIFLJGGNR.csv", takei2021_1mb),
}


def load_dataset(name: str, path=None, **kw) -> Population:
    from _common import example_data
    rel, fn = DATASETS[name]
    return fn(Path(path) if path else example_data() / rel, **kw)
