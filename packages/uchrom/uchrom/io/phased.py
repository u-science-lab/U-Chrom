"""Phased (homolog-resolved) single-cell Hi-C contacts.

Two formats are read into one table — ``chrom1, pos1, hap1, chrom2, pos2, hap2`` (hap: 0, 1
or -1 = unknown) plus ``phase_prob00 .. phase_prob11`` when the input has them:

* hickit / 4DN ``.pairs[.gz]`` (Tan et al. 2018 Dip-C pipeline, ``hickit -o``): the columns
  are named by the ``#columns:`` header; ``phase0`` / ``phase1`` hold ``0``, ``1`` or ``.``.
  ``hickit -u`` (imputation) adds ``phase_prob00 .. phase_prob11`` (probability of each
  (hap1, hap2) combination).
* Dip-C ``.con[.gz]`` (GEO GSE117876 ``*.con.txt.gz``): one contact per line, two tab-separated
  legs ``chrom,pos,hap``; hap ``0`` = paternal, ``1`` = maternal, ``.`` = unknown
  (``dip-c`` ``classes.Haplotypes``).

The table is the input of :func:`uchrom.recon.sc.reconstruct_ember` /
:func:`uchrom.recon.sc.nucdyn.reconstruct_nucdyn` for diploid reconstruction.
"""

from __future__ import annotations

import gzip
from pathlib import Path

import numpy as np
import pandas as pd

__all__ = ["read_phased_pairs", "write_phased_pairs", "pairs_header_columns"]

_PROB = ["phase_prob00", "phase_prob01", "phase_prob10", "phase_prob11"]


def _open(path):
    path = str(path)
    return gzip.open(path, "rt") if path.endswith(".gz") else open(path)


def pairs_header_columns(path):
    """Column names of a ``.pairs`` file from its ``#columns:`` header (None if absent)."""
    with _open(path) as fh:
        for line in fh:
            if not line.startswith("#"):
                return None
            if line.startswith("#columns:"):
                return line.split()[1:]
    return None


def _haps(s: pd.Series) -> np.ndarray:
    s = s.astype(str).replace({".": "-1"})
    return pd.to_numeric(s, errors="coerce").fillna(-1).to_numpy().astype(np.int8)


def read_phased_pairs(path) -> pd.DataFrame:
    """Read phased contacts (hickit ``.pairs`` or Dip-C ``.con``) into a DataFrame with
    ``chrom1, pos1, hap1, chrom2, pos2, hap2`` (+ ``phase_prob00 .. phase_prob11`` when
    present).  Haplotypes are int8: 0, 1, -1 = unknown.  A ``.pairs`` file without phase
    columns gives -1 everywhere."""
    path = str(path)
    name = path[:-3] if path.endswith(".gz") else path
    if name.endswith((".con", ".con.txt")):
        raw = pd.read_csv(path, sep="\t", header=None, names=["a", "b"], dtype=str, comment="#")
        a = raw["a"].str.split(",", expand=True)
        b = raw["b"].str.split(",", expand=True)
        return pd.DataFrame({
            "chrom1": a[0].astype(str), "pos1": a[1].astype(np.int64), "hap1": _haps(a[2]),
            "chrom2": b[0].astype(str), "pos2": b[1].astype(np.int64), "hap2": _haps(b[2]),
        })
    cols = pairs_header_columns(path)
    df = pd.read_csv(path, sep="\t", header=None, comment="#", dtype=str)
    if cols is None:
        cols = ["readID", "chr1", "pos1", "chr2", "pos2", "strand1", "strand2"][: df.shape[1]]
    if len(cols) != df.shape[1]:
        raise ValueError(f"{path}: {df.shape[1]} columns, header names {len(cols)}")
    df.columns = cols
    out = pd.DataFrame({
        "chrom1": df["chr1"].astype(str), "pos1": df["pos1"].astype(np.int64),
        "hap1": _haps(df["phase0"]) if "phase0" in df else np.full(len(df), -1, np.int8),
        "chrom2": df["chr2"].astype(str), "pos2": df["pos2"].astype(np.int64),
        "hap2": _haps(df["phase1"]) if "phase1" in df else np.full(len(df), -1, np.int8),
    })
    if all(c in df for c in _PROB):
        for c in _PROB:
            out[c] = df[c].astype(np.float64)
    return out


def write_phased_pairs(df: pd.DataFrame, path, chrom_sizes=None) -> None:
    """Write a phased table as a hickit-readable ``.pairs`` (``readID chr1 pos1 chr2 pos2
    strand1 strand2 phase0 phase1``; strands ``.``; ``#chromsize:`` lines from
    ``chrom_sizes``)."""
    lines = ["## pairs format v1.0", "#sorted: none", "#shape: upper triangle"]
    for c, n in (chrom_sizes or {}).items():
        lines.append(f"#chromsize: {c} {int(n)}")
    lines.append("#columns: readID chr1 pos1 chr2 pos2 strand1 strand2 phase0 phase1")
    h = lambda x: np.where(np.asarray(x) >= 0, np.asarray(x).astype(str), ".")  # noqa: E731
    body = pd.DataFrame({"r": [f"r{k}" for k in range(len(df))], "c1": df["chrom1"], "p1": df["pos1"],
                         "c2": df["chrom2"], "p2": df["pos2"], "s1": ".", "s2": ".",
                         "h1": h(df["hap1"]), "h2": h(df["hap2"])})
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    opener = gzip.open if str(path).endswith(".gz") else open
    with opener(path, "wt") as fh:
        fh.write("\n".join(lines) + "\n")
        body.to_csv(fh, sep="\t", header=False, index=False)
