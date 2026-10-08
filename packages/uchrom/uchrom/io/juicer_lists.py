"""Loop and domain lists of Juicer (HiCCUPS, Arrowhead): the published calls of Rao et al. 2014 and the
output of ``juicer_tools hiccups`` / ``arrowhead``, as U-Chrom's pair and domain tables.

The lists are tab-separated with a header line (``chr1 x1 x2 chr2 y1 y2 color ...``; Juicer's newer
``.bedpe`` files start it with ``#`` and add a ``# juicer_tools version`` line); chromosome names often lack
the ``chr`` prefix (GEO GSE63525).  The tables read here go straight into :func:`uchrom.strc.loop.match_loops`,
:func:`uchrom.strc.tad.compare_boundaries` and :func:`uchrom.fea.pileup`.

References
----------
Rao, S. S. P. et al. (2014) A 3D map of the human genome at kilobase resolution reveals principles of
chromatin looping. *Cell* 159:1665-1680.  Durand, N. C. et al. (2016) Juicer provides a one-click system for
analyzing loop-resolution Hi-C experiments. *Cell Syst.* 3:95-98.
"""

from __future__ import annotations

import gzip
import os
from typing import Optional, Sequence, Union

import pandas as pd

__all__ = ["read_juicer_loops", "read_juicer_domains"]

PathLike = Union[str, os.PathLike]


def _read(path: PathLike, sheet: Optional[str] = None) -> pd.DataFrame:
    if str(path).lower().endswith((".xlsx", ".xls")):           # a sheet of a workbook (supplementary data)
        if sheet is None:
            raise ValueError(f"{path}: a workbook — give sheet=")
        table = pd.read_excel(path, sheet_name=sheet, dtype={"chr1": str, "chr2": str})   # needs openpyxl
        table.columns = [str(c).lstrip("#") for c in table.columns]
    else:
        opener = gzip.open if str(path).endswith(".gz") else open
        with opener(path, "rt") as fh:
            header = fh.readline().rstrip("\n").lstrip("#").split("\t")
            table = pd.read_csv(fh, sep="\t", header=None, names=header, comment="#",
                                dtype={header[0]: str, header[3]: str})
    missing = {"chr1", "x1", "x2", "chr2", "y1", "y2"} - set(table.columns)
    if missing:
        raise ValueError(f"{path}: not a Juicer list (no column(s) {sorted(missing)})")
    return table


def _chrom_names(names: pd.Series, prefix: Optional[str]) -> pd.Series:
    names = names.astype(str)
    if prefix:
        names = names.where(names.str.startswith(prefix), prefix + names)
    return names


def _keep(table: pd.DataFrame, column: str, chrom, prefix: Optional[str]) -> pd.DataFrame:
    if chrom is None:
        return table
    wanted = {chrom} if isinstance(chrom, str) else set(map(str, chrom))
    wanted = set(_chrom_names(pd.Series(sorted(wanted)), prefix))
    return table[table[column].isin(wanted)]


def read_juicer_loops(path: PathLike, *, chrom: Union[None, str, Sequence[str]] = None,
                      chrom_prefix: Optional[str] = "chr", sheet: Optional[str] = None) -> pd.DataFrame:
    """A Juicer loop list (HiCCUPS; e.g. GEO GSE63525 ``*_HiCCUPS_looplist.txt.gz``) as a pair table.

    Parameters
    ----------
    path
        The list (``.txt`` / ``.bedpe``, optionally gzipped), or a workbook (``.xlsx``, e.g. a paper's
        supplementary data; needs ``openpyxl``) with ``sheet``.
    chrom
        Only the loops on these chromosomes (names with or without the prefix).
    chrom_prefix
        Added to chromosome names that lack it (``"21"`` → ``"chr21"``, the names of UCSC-style maps);
        ``None`` keeps the names of the file.

    Returns
    -------
    DataFrame
        ``chrom1, start1, end1, chrom2, start2, end2`` (the two anchors, bp) followed by the list's other
        columns as they are (HiCCUPS: ``color, o`` — observed —, the four local expecteds ``e_bl, e_donut,
        e_h, e_v`` and their FDRs, ``num_collapsed``, ``centroid1, centroid2, radius``), sorted by position.
    """
    t = _read(path, sheet)
    t = t.rename(columns={"chr1": "chrom1", "x1": "start1", "x2": "end1", "chr2": "chrom2", "y1": "start2",
                          "y2": "end2"})
    t["chrom1"] = _chrom_names(t["chrom1"], chrom_prefix)
    t["chrom2"] = _chrom_names(t["chrom2"], chrom_prefix)
    t = _keep(t, "chrom1", chrom, chrom_prefix)
    t = t.astype({c: "int64" for c in ("start1", "end1", "start2", "end2")})
    return t.sort_values(["chrom1", "start1", "start2"], kind="mergesort").reset_index(drop=True)


def read_juicer_domains(path: PathLike, *, chrom: Union[None, str, Sequence[str]] = None,
                        chrom_prefix: Optional[str] = "chr", sheet: Optional[str] = None) -> pd.DataFrame:
    """A Juicer domain list (Arrowhead; e.g. GEO GSE63525 ``*_Arrowhead_domainlist.txt.gz``) as a domain
    table.

    Parameters
    ----------
    path
        The list (optionally gzipped), or a workbook (``.xlsx``) with ``sheet``.
    chrom
        Only the domains on these chromosomes (names with or without the prefix).
    chrom_prefix
        Added to chromosome names that lack it; ``None`` keeps the names of the file.

    Returns
    -------
    DataFrame
        ``chrom, start, end`` followed by the list's other columns as they are (Arrowhead: ``color`` and the
        scores ``f1`` … ``f5``), sorted by position; domains may nest.
    """
    t = _read(path, sheet)
    t = t.rename(columns={"chr1": "chrom", "x1": "start", "x2": "end"}).drop(columns=["chr2", "y1", "y2"])
    t["chrom"] = _chrom_names(t["chrom"], chrom_prefix)
    t = _keep(t, "chrom", chrom, chrom_prefix)
    t = t.astype({"start": "int64", "end": "int64"})
    return t.sort_values(["chrom", "start", "end"], kind="mergesort").reset_index(drop=True)
