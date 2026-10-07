"""Domain boundaries on the loci of a ``ChromData``, and how two boundary sets agree.

A domain table (ArcFISH TADs, directionality-index TADs on a linked Hi-C map, FISHnet single-allele
domains) gives positions in bp; the loci of ``cd.bins`` — or the bins of a contact map linked to it
(``contacts=``) — give the common axis.  A **boundary** is the first
locus of a domain or the first locus after it, leaving out the outer edges of the domain set (the start
of the first domain and the end of the last one, per chromosome and per trace).  On loci with gaps
between them (e.g. 50-kb loci every 50-100 kb) the end of a domain and the start of the next one map to the
same locus, so a boundary is counted once.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Dict, Optional, Union

import numpy as np
import pandas as pd

from .._traces import chrom_loci

Domains = Union[str, pd.DataFrame]


def _on_loci(cd, contacts: Optional[str], resolution: Optional[int]):
    """``cd``, or — with ``contacts`` — a view of it whose loci are the bins of that linked map."""
    if contacts is None:
        return cd
    from uchrom.fea.maps import open_map

    bins = open_map(cd, contacts, resolution=resolution).bins()[:][["chrom", "start", "end"]]
    return SimpleNamespace(bins=bins, results=getattr(cd, "results", {}))


def _domains(cd, domains: Domains, level: Optional[int]) -> pd.DataFrame:
    table = cd.results[domains] if isinstance(domains, str) else domains
    table = pd.DataFrame(table)
    missing = {"chrom", "start", "end"} - set(table.columns)
    if missing:
        raise KeyError(f"a domain table needs the column(s) {sorted(missing)}")
    if "level" in table.columns:
        lvl = int(table["level"].min()) if level is None else int(level)
        table = table[table["level"] == lvl]
    elif level is not None:
        raise KeyError("level= given but the domain table has no 'level' column")
    return table


def tad_boundaries(cd, domains: Domains = "tads.arcfish", *, level: Optional[int] = None,
                   contacts: Optional[str] = None, resolution: Optional[int] = None) -> pd.DataFrame:
    """The boundaries of a domain table, as loci of ``cd``.

    Parameters
    ----------
    cd : ChromData
        Its ``bins`` are the loci the boundaries are placed on (or the bins of ``contacts``).
    domains : str or DataFrame
        A key of ``cd.results`` (default ``"tads.arcfish"``) or a table with ``chrom, start, end``; with a
        ``trace_id`` column (FISHnet), boundaries per trace.
    level : int, optional
        For hierarchical tables (a ``level`` column): the level to use; default the finest (level 1).
    contacts, resolution : optional
        Key of a contact map linked to ``cd`` (and the level of an ``.mcool``): its bins are the loci — for a
        ``ChromData`` that holds only Hi-C maps (``bin_id`` is then the map's bin index).

    Returns
    -------
    DataFrame
        One row per boundary: ``chrom``, [``trace_id``], ``bin_index`` (the locus after the boundary, counted
        within the chromosome from 0), ``bin_id`` (``cd.bins`` index) and ``start`` (its start, bp).
    """
    cd = _on_loci(cd, contacts, resolution)
    table = _domains(cd, domains, level)
    per_trace = "trace_id" in table.columns
    rows = []
    for chrom, g in table.groupby(table["chrom"].astype(str), sort=False):
        loci = chrom_loci(cd, chrom)
        starts = loci["start"].to_numpy()
        groups = g.groupby(g["trace_id"].astype(str), sort=False) if per_trace else [(None, g)]
        for trace, d in groups:
            d = d.sort_values("start", kind="mergesort")
            a = np.searchsorted(starts, d["start"].to_numpy(np.int64), side="left")
            b = np.searchsorted(starts, d["end"].to_numpy(np.int64), side="left")
            edges = sorted((set(a[1:].tolist()) | set(b[:-1].tolist())) - {0, len(starts)})
            for k in edges:
                row = {"chrom": chrom, "bin_index": int(k), "bin_id": loci["bin_id"].iat[k],
                       "start": int(starts[k])}
                if per_trace:
                    row["trace_id"] = trace
                rows.append(row)
    cols = ["chrom"] + (["trace_id"] if per_trace else []) + ["bin_index", "bin_id", "start"]
    out = pd.DataFrame(rows, columns=cols)
    return out.astype({"bin_index": np.int64, "start": np.int64})


def compare_boundaries(cd, query: Domains, reference: Domains, *, tol: int = 1,
                       level: Optional[int] = None, contacts: Optional[str] = None,
                       resolution: Optional[int] = None) -> Dict[str, float]:
    """How often the boundaries of ``query`` fall within ``tol`` loci of a boundary of ``reference``,
    against what random loci would give.

    Parameters
    ----------
    cd : ChromData
        Its ``bins`` are the loci both tables are placed on (:func:`tad_boundaries`).
    query, reference : str or DataFrame
        Population domain tables (keys of ``cd.results`` or tables), e.g. DI TADs on Hi-C and ArcFISH TADs
        on the imaging of the same loci, or insulation TADs and a published domain list.
    tol : int
        Largest distance in loci (default 1: the same or a neighbouring locus).
    level : int, optional
        Level of hierarchical tables (default the finest).
    contacts, resolution : optional
        Place the boundaries on the bins of this linked contact map instead of ``cd.bins``
        (:func:`tad_boundaries`); ``tol`` then counts map bins.

    Returns
    -------
    dict
        ``n_query``, ``n_reference`` (boundaries), ``fraction_near`` (of the query boundaries within ``tol``
        loci of a reference boundary on the same chromosome), ``chance`` (the same fraction for every locus
        of the chromosomes with query boundaries) and ``enrichment`` (= fraction_near / chance).
    """
    def within(idx, ref):
        return np.min(np.abs(np.asarray(idx)[:, None] - ref[None, :]), axis=1) <= tol

    cd = _on_loci(cd, contacts, resolution)
    q = tad_boundaries(cd, query, level=level)
    r = tad_boundaries(cd, reference, level=level)
    near, chance_hits, n_loci = [], 0, 0
    for chrom, g in q.groupby("chrom", sort=False):
        ref = r.loc[r["chrom"] == chrom, "bin_index"].to_numpy()
        n = len(chrom_loci(cd, chrom))
        n_loci += n
        if len(ref) == 0:
            near += [False] * len(g)
            continue
        near += within(g["bin_index"].to_numpy(), ref).tolist()
        chance_hits += int(within(np.arange(n), ref).sum())
    fraction = float(np.mean(near)) if near else float("nan")
    chance = chance_hits / n_loci if n_loci else float("nan")
    return {"n_query": int(len(q)), "n_reference": int(len(r)), "fraction_near": fraction,
            "chance": float(chance), "enrichment": fraction / chance if chance else float("nan")}


def boundary_frequency(cd, domains: Domains = "tads.fishnet") -> pd.DataFrame:
    """Per locus, the fraction of traces (alleles) with a domain boundary there — single-allele domain
    tables such as FISHnet's.

    Parameters
    ----------
    cd : ChromData
    domains : str or DataFrame
        A key of ``cd.results`` (default ``"tads.fishnet"``) or a table with ``chrom, trace_id, start, end``.

    Returns
    -------
    DataFrame
        One row per locus of the chromosomes in the table: ``bin_id, chrom, start, end, bin_index``,
        ``n_traces`` (traces with domains on the chromosome) and ``frequency``.
    """
    table = _domains(cd, domains, None)
    if "trace_id" not in table.columns:
        raise KeyError("boundary_frequency() needs per-trace domains (a trace_id column)")
    b = tad_boundaries(cd, table)
    parts = []
    for chrom, g in table.groupby(table["chrom"].astype(str), sort=False):
        loci = chrom_loci(cd, chrom)
        n_traces = g["trace_id"].astype(str).nunique()
        hits = np.bincount(b.loc[b["chrom"] == chrom, "bin_index"].to_numpy(np.int64), minlength=len(loci))
        parts.append(loci.assign(bin_index=np.arange(len(loci)), n_traces=n_traces,
                                 frequency=hits / n_traces))
    return pd.concat(parts, ignore_index=True)


__all__ = ["boundary_frequency", "compare_boundaries", "tad_boundaries"]
