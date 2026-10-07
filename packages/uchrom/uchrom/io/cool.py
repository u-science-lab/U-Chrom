"""Write a locus x locus contact matrix (loci of any size and spacing) as a ``.cool`` file."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional, Union

import numpy as np
import pandas as pd

__all__ = ["write_locus_cool"]


def write_locus_cool(loci, matrix, path, *, assembly: Optional[str] = None,
                     balance: Union[bool, dict] = True) -> str:
    """Write a contact matrix over arbitrary loci (e.g. imaged loci, uneven) as a ``.cool``.

    Cooler bins tile each chromosome, so the bin of a locus runs from its start to the start of the next
    locus of the chromosome (the last one to its own end), after an **empty leading bin** from 0 to the
    first locus (left out when the first locus starts at 0).  Fetching a region then returns the loci whose
    start lies in it, and ``cd.link_cool(path, key=...)`` links the file to the ``ChromData`` of the loci.

    Parameters
    ----------
    loci : DataFrame
        ``chrom``, ``start``, ``end`` of the rows / columns of ``matrix``.  Starts must differ within a
        chromosome; the loci are sorted (chromosomes in order of first appearance, then start).
    matrix : array-like (n, n)
        Symmetric, non-negative counts; zeros and NaN are not stored.  Integer-valued matrices are stored as
        integer counts, others as float counts.
    path : str or Path
        The ``.cool`` file to write (replaced atomically).
    assembly : str, optional
        Genome assembly recorded in the file.
    balance : bool or dict
        ICE-balance the map and store the ``weight`` column (``cooler.balance_cooler`` with its defaults, or
        with the keyword arguments of a dict).

    Returns
    -------
    str
        ``path``.
    """
    import cooler

    loci = pd.DataFrame(loci)
    missing = [c for c in ("chrom", "start", "end") if c not in loci.columns]
    if missing:
        raise ValueError(f"loci needs the columns chrom, start, end (missing {missing})")
    m = np.asarray(matrix, dtype=np.float64)
    n = len(loci)
    if m.shape != (n, n):
        raise ValueError(f"matrix is {m.shape}, but there are {n} loci")
    if not np.allclose(m, m.T, equal_nan=True):
        raise ValueError("matrix must be symmetric")
    if (m < 0).any():
        raise ValueError("matrix must be non-negative (counts)")

    chrom = loci["chrom"].astype(str).to_numpy(dtype=object)
    start = loci["start"].to_numpy(np.int64)
    end = loci["end"].to_numpy(np.int64)
    if (end <= start).any():
        raise ValueError("loci must satisfy end > start")
    names = list(dict.fromkeys(chrom))
    rank = pd.Series(range(len(names)), index=names)[chrom].to_numpy()
    order = np.lexsort((start, rank))
    chrom, start, end, rank = chrom[order], start[order], end[order], rank[order]
    m = m[np.ix_(order, order)]
    same = rank[1:] == rank[:-1]
    if (start[1:][same] == start[:-1][same]).any():
        raise ValueError("loci of one chromosome must have different starts")

    # bins: per chromosome an empty leading bin [0, first start), then locus k -> [start_k, start_k+1)
    parts, bin_of_locus, offset = [], np.empty(n, np.int64), 0
    for r, name in enumerate(names):
        idx = np.flatnonzero(rank == r)
        s, e = start[idx], end[idx]
        lead = 1 if s[0] > 0 else 0
        parts.append(pd.DataFrame({"chrom": name, "start": np.r_[[0] * lead, s].astype(np.int64),
                                   "end": np.r_[s[:lead], s[1:], e[-1:]].astype(np.int64)}))
        bin_of_locus[idx] = offset + lead + np.arange(len(idx))
        offset += lead + len(idx)
    bins = pd.concat(parts, ignore_index=True)

    i, j = np.triu_indices(n)
    v = m[i, j]
    keep = np.isfinite(v) & (v != 0)
    integral = bool(np.all(v[keep] == np.round(v[keep])))
    pixels = pd.DataFrame({"bin1_id": bin_of_locus[i[keep]], "bin2_id": bin_of_locus[j[keep]],
                           "count": v[keep].astype(np.int64) if integral else v[keep]})

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.unlink(missing_ok=True)
    try:
        cooler.create_cooler(str(tmp), bins, pixels, ordered=True, assembly=assembly,
                             dtypes=None if integral else {"count": np.float64})
        if balance:
            cooler.balance_cooler(cooler.Cooler(str(tmp)), store=True, **(balance if isinstance(balance, dict) else {}))
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)
    return str(path)
