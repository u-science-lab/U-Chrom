"""SnapFISH / SnapFISH-IMPUTE chromatin-tracing tables.

SnapFISH (Lee et al. 2023, *Nat Commun* 14:4873) and SnapFISH-IMPUTE (Yu et al.,
github.com/hyuyu104/SnapFISH-IMPUTE) read multiplexed DNA-FISH traces as two tab-separated tables:

* a **coordinate table**, one row per (imaging region, haploid, locus): ``region`` (SnapFISH: ``chr``),
  ``haploid`` (SnapFISH: ``cell_id``; a trace, unique within its region), ``pos`` (the locus number,
  from 1), ``x, y, z`` in nm — a locus that was not detected is a row with empty ``x, y, z``;
* an **annotation table**, one row per (region, locus): ``region`` (``chr``), ``pos``, ``start``, ``end``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Mapping, Optional, Union

import numpy as np
import pandas as pd

_REGION = ("region", "chr", "chrom")
_TRACE = ("haploid", "cell_id", "trace_id")


def _table(x, sep) -> pd.DataFrame:
    if isinstance(x, pd.DataFrame):
        return x.copy()
    return pd.read_csv(Path(x), sep=sep, dtype={c: str for c in _REGION + _TRACE})


def _pick(df: pd.DataFrame, names, what: str) -> str:
    for n in names:
        if n in df.columns:
            return n
    raise ValueError(f"the {what} has none of the columns {list(names)}; it has {list(df.columns)}")


def read_snapfish(
    coor,
    ann,
    *,
    chrom: Union[None, str, Mapping[str, str]] = None,
    region_name: str = "region",
    cell_id: Union[bool, Callable[[str], str]] = False,
    keep_missing: bool = True,
    xyz_unit: str = "nm",
    genome_assembly: Optional[str] = None,
    sep: str = "\t",
):
    """Read a SnapFISH / SnapFISH-IMPUTE coordinate table and its locus annotation into a ``ChromData``.

    Parameters
    ----------
    coor : path or DataFrame
        Coordinate table: ``region`` (or ``chr``), ``haploid`` (or ``cell_id``), ``pos``, ``x``, ``y``,
        ``z``; undetected loci are rows with NaN coordinates (SnapFISH-IMPUTE's ``*_coor_wnan.txt``).
    ann : path or DataFrame
        Locus annotation: ``region`` (or ``chr``), ``pos``, ``start``, ``end``.  Its loci become the locus
        axis ``bins`` (the whole probe panel, also loci without any detection).
    chrom : str or dict, optional
        ``None`` (default): each region is a chromosome of its own, named as the region (SnapFISH's view).
        A chromosome name: every region is a copy (allele) of that chromosome — e.g. the 129 and CAST
        alleles of mouse chr3 — and the region is kept as the spot column ``region_name``; a dict maps
        region -> chromosome the same way.
    region_name : str
        The spot (and trace) column that holds the region when ``chrom`` is given (e.g. ``"allele"``).
    cell_id : bool or callable
        ``False``: no cells.  ``True``: the haploid ids are cell ids (one trace per cell and region, as
        when the regions are the two alleles of a locus); a callable maps a haploid id to its cell id.
    keep_missing : bool
        Keep the undetected loci as NaN rows (default) or drop them (absent rows).
    xyz_unit, genome_assembly : str
        Recorded in ``uns`` (SnapFISH coordinates are in nm; the tables name no assembly).
    sep : str
        Column separator of the files.

    Returns
    -------
    ChromData
        One trace per (haploid, region), ``trace_id = "<haploid>_<region>"``; spot columns ``pos`` (and
        ``region_name``); ``traces`` with the region, chromosome, cell, number of loci and of detected loci;
        ``cells`` (in the order of the table) when ``cell_id`` is given.  Rows keep the table's order.

    Examples
    --------
    >>> cd = read_snapfish("mESC_Sox2_coor_wnan.txt", "mESC_Sox2_ann.txt",
    ...                    chrom="chr3", region_name="allele", cell_id=True, genome_assembly="mm10")
    """
    from chromdata import ChromData

    coor, ann = _table(coor, sep), _table(ann, sep)
    rc, tc = _pick(coor, _REGION, "coordinate table"), _pick(coor, _TRACE, "coordinate table")
    ra = _pick(ann, _REGION, "annotation table")
    for need, df, what in ((("pos", "x", "y", "z"), coor, "coordinate table"),
                           (("pos", "start", "end"), ann, "annotation table")):
        miss = [c for c in need if c not in df.columns]
        if miss:
            raise ValueError(f"the {what} misses the columns {miss}")
    t = pd.DataFrame({"region": coor[rc].astype(str).to_numpy(), "haploid": coor[tc].astype(str).to_numpy(),
                      "pos": coor["pos"].to_numpy(), "x": coor["x"].to_numpy(dtype=np.float64),
                      "y": coor["y"].to_numpy(dtype=np.float64), "z": coor["z"].to_numpy(dtype=np.float64)})
    ann = pd.DataFrame({"region": ann[ra].astype(str).to_numpy(), "pos": ann["pos"].to_numpy(),
                        "start": ann["start"].to_numpy(dtype=np.int64), "end": ann["end"].to_numpy(dtype=np.int64)})
    if ann.duplicated(["region", "pos"]).any():
        raise ValueError("the annotation table repeats a (region, pos)")

    if chrom is None:
        to_chrom = {r: r for r in ann["region"].unique()}
    elif isinstance(chrom, str):
        to_chrom = {r: chrom for r in ann["region"].unique()}
    else:
        to_chrom = {str(k): str(v) for k, v in chrom.items()}
    unknown = sorted(set(ann["region"]) - set(to_chrom))
    if unknown:
        raise ValueError(f"chrom= does not map the regions {unknown}")
    ann["chrom"] = ann["region"].map(to_chrom)

    t = t.merge(ann, on=["region", "pos"], how="left", validate="many_to_one")
    if t["start"].isna().any():
        bad = t.loc[t["start"].isna(), ["region", "pos"]].drop_duplicates().head(3).to_dict("records")
        raise ValueError(f"loci of the coordinate table missing from the annotation table, e.g. {bad}")
    t["trace_id"] = t["haploid"] + "_" + t["region"]
    if cell_id:
        f = (lambda h: h) if cell_id is True else cell_id
        t["cell_id"] = t["haploid"].map({h: str(f(h)) for h in pd.unique(t["haploid"])})
    t["detected"] = t[["x", "y", "z"]].notna().all(axis=1)

    # one row per trace: its cell, region, chromosome, panel loci and detected loci
    agg = {"region": ("region", "first"), "chrom": ("chrom", "first"), "n_loci": ("detected", "size"),
           "n_detected": ("detected", "sum")}
    if cell_id:
        agg = {"cell_id": ("cell_id", "first"), **agg}
    traces = t.groupby("trace_id", sort=False).agg(**agg)
    traces["n_detected"] = traces["n_detected"].astype(np.int64)
    traces = (traces.drop(columns="region") if chrom is None
              else traces.rename(columns={"region": region_name}))
    if not keep_missing:
        t = t[t["detected"].to_numpy()].reset_index(drop=True)
        traces = traces[traces["n_detected"] > 0]

    bins = (ann[["chrom", "start", "end"]].drop_duplicates()
            .sort_values(["chrom", "start", "end"], kind="mergesort").reset_index(drop=True))
    spots = pd.DataFrame({"chrom": t["chrom"].to_numpy(), "start": t["start"].astype(np.int64).to_numpy(),
                          "end": t["end"].astype(np.int64).to_numpy(), "trace_id": t["trace_id"].to_numpy()})
    cells = None
    if cell_id:
        spots["cell_id"] = t["cell_id"].to_numpy()
        cells = pd.DataFrame(index=pd.Index(pd.unique(spots["cell_id"]), name="cell_id"))
    if chrom is not None:
        spots[region_name] = t["region"].to_numpy()
    spots["pos"] = t["pos"].astype(np.int64).to_numpy()

    uns = {"xyz_unit": xyz_unit, "source": "SnapFISH coordinate + annotation tables"}
    if genome_assembly:
        uns["genome_assembly"] = genome_assembly
    return ChromData(t[["x", "y", "z"]].to_numpy(dtype=np.float64), spots, bins=bins, cells=cells,
                     traces=traces, uns=uns)


__all__ = ["read_snapfish"]
