"""Loop calls against a reference list, and against the 3-D distances of the traces."""

from __future__ import annotations

from typing import Optional, Union

import numpy as np
import pandas as pd


def _chrom_column(table: pd.DataFrame) -> Optional[str]:
    for c in ("chrom1", "chrom"):
        if c in table.columns:
            return c
    return None


def match_loops(reference: pd.DataFrame, calls: pd.DataFrame, *, tol: int = 25_000) -> pd.Series:
    """Which loops of ``reference`` were called: both anchors of a call within ``tol`` bp of theirs.

    Parameters
    ----------
    reference, calls : DataFrame
        BEDPE-like loop tables with ``start1`` and ``start2`` (anchor starts, bp).  When both have a
        chromosome column (``chrom1`` or ``chrom``) a match must also be on the same chromosome.
    tol : int
        Largest distance between anchor starts, bp (default one 25-kb bin).

    Returns
    -------
    Series of bool, indexed like ``reference``.

    Examples
    --------
    >>> ref = pd.DataFrame({"start1": [50_300_000], "start2": [50_525_000]})
    >>> match_loops(ref, cd.intervals["loops.axiswise_f"])          # doctest: +SKIP
    """
    for t, name in ((reference, "reference"), (calls, "calls")):
        missing = {"start1", "start2"} - set(t.columns)
        if missing:
            raise KeyError(f"{name} has no column(s) {sorted(missing)}")
    rc, cc = _chrom_column(reference), _chrom_column(calls)
    c1 = np.asarray(calls["start1"], dtype=np.int64)
    c2 = np.asarray(calls["start2"], dtype=np.int64)
    cchrom = calls[cc].astype(str).to_numpy() if rc and cc else None
    found = []
    for k, (a, b) in enumerate(zip(np.asarray(reference["start1"], dtype=np.int64),
                                   np.asarray(reference["start2"], dtype=np.int64))):
        hit = (np.abs(c1 - a) <= tol) & (np.abs(c2 - b) <= tol)
        if cchrom is not None:
            hit &= cchrom == str(reference[rc].iloc[k])
        found.append(bool(hit.any()))
    return pd.Series(found, index=reference.index, name="found", dtype=bool)


def score_loops(
    cd,
    loops: Union[str, pd.DataFrame] = "loops.axiswise_f",
    *,
    chrom=None,
    trace_ids=None,
    cells=None,
) -> pd.DataFrame:
    """How much closer the two anchors of each loop are than other locus pairs at the same genomic separation.

    For each loop, the 3-D distance of its two anchor loci in every trace that detected both, against the
    distances of every other pair of loci of the chromosome exactly as far apart (same start-to-start
    separation), pooled over the traces.  A loop called from imaging should have ``ratio`` < 1.

    Parameters
    ----------
    cd : ChromData
        The traces (in memory or backed; one chromosome is read at a time).
    loops : str or DataFrame
        A key of ``cd.results`` / ``cd.intervals`` (default ``"loops.axiswise_f"``) or a loop table with
        ``chrom1`` (or ``chrom``), ``start1``, ``start2``; anchors are matched to loci by their start.
    chrom : str or sequence of str, optional
        Score only the loops on these chromosomes.
    trace_ids, cells : sequence, optional
        Use only these traces / cells.

    Returns
    -------
    DataFrame
        The loop table with ``n_traces`` (traces that detected both anchors), ``anchor_distance`` (their
        median distance), ``n_background`` (distances of the other pairs), ``background_distance`` (their
        median) and ``ratio`` (= anchor / background).  Distances in the unit of ``cd.coords``.
    """
    from uchrom.convention import select_spots

    from .._traces import coord_cube

    table = cd.results[loops] if isinstance(loops, str) else loops
    table = pd.DataFrame(table).reset_index(drop=True)
    cc = _chrom_column(table)
    if cc is None:
        raise KeyError("loops need a chrom1 (or chrom) column")
    if chrom is not None:
        keep = {chrom} if isinstance(chrom, str) else set(map(str, chrom))
        table = table[table[cc].astype(str).isin(keep)].reset_index(drop=True)
    work = select_spots(cd, trace_ids=trace_ids, cells=cells)
    cols = {k: np.full(len(table), np.nan) for k in
            ("n_traces", "anchor_distance", "n_background", "background_distance")}
    for c, rows in table.groupby(table[cc].astype(str), sort=False).groups.items():
        cube, loci, _ = coord_cube(work, c)
        starts = loci["start"].to_numpy()
        index = {int(s): k for k, s in enumerate(starts)}
        for r in rows:
            s1, s2 = int(table.at[r, "start1"]), int(table.at[r, "start2"])
            if s1 not in index or s2 not in index:
                raise KeyError(f"loop {c}:{s1}-{s2}: an anchor start is not a locus start of {c}")
            i, j = index[s1], index[s2]
            d = np.linalg.norm(cube[:, i] - cube[:, j], axis=1)
            d = d[np.isfinite(d)]
            sep = s2 - s1
            others = [(index[int(s)], index[int(s) + sep]) for s in starts
                      if int(s) + sep in index and int(s) != s1]
            bg = (np.concatenate([np.linalg.norm(cube[:, a] - cube[:, b], axis=1) for a, b in others])
                  if others else np.zeros(0))
            bg = bg[np.isfinite(bg)]
            cols["n_traces"][r] = len(d)
            cols["anchor_distance"][r] = np.median(d) if len(d) else np.nan
            cols["n_background"][r] = len(bg)
            cols["background_distance"][r] = np.median(bg) if len(bg) else np.nan
    out = table.assign(**cols)
    out["ratio"] = out["anchor_distance"] / out["background_distance"]
    return out.astype({"n_traces": np.int64, "n_background": np.int64})


__all__ = ["match_loops", "score_loops"]
