"""A/B compartments of a Hi-C map linked to a ``ChromData``: the first principal component of the
correlation matrix of the observed / expected map (Lieberman-Aiden et al. 2009), on any bins — also on
loci of uneven size and spacing, such as the imaged loci of a tracing experiment with the Hi-C summed
into them.  The reference for compartments called from imaging (:func:`compare_compartments`).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Union

import numpy as np
import pandas as pd

from uchrom.convention import merge_tables, resolve_chroms, store_and_return

from .axes_pc import compartment_segments


@dataclass(frozen=True)
class HiCCompartmentParams:
    """Knobs of :func:`call_compartments_hic`.

    The expected count of a bin pair is the mean count of the pairs in its class of genomic separation
    (``n_distance_classes`` log-spaced classes from ``min_separation_bp`` to the largest separation, pairs
    closer than ``min_separation_bp`` in one class) — so uneven loci are handled.
    """

    n_distance_classes: int = 60
    min_separation_bp: float = 10 ** 4.5
    balance: bool = False             # True: the ICE-balanced matrix (cooler weights) instead of raw counts


def hic_compartment_pc1(counts: np.ndarray, positions, *, marker=None,
                        params: Optional[HiCCompartmentParams] = None) -> np.ndarray:
    """PC1 of the correlation matrix of the log2 observed / expected contact matrix.

    Parameters
    ----------
    counts : ndarray (n, n)
        Contact matrix of one chromosome (bins without contacts removed beforehand).
    positions : array (n,)
        Genomic position of each bin (bp; e.g. its start) — the separations of the expected counts.
    marker : array (n,), optional
        A track that is higher in A (gene density, an active mark); PC1 is oriented to correlate positively
        with it (NaN values are left out).  Without it the sign is arbitrary.
    params : HiCCompartmentParams, optional

    Returns
    -------
    ndarray (n,)
        Unit-norm PC1; ``> 0`` is A when a ``marker`` is given.
    """
    params = params or HiCCompartmentParams()
    counts = np.asarray(counts, dtype=np.float64)
    positions = np.asarray(positions, dtype=np.float64)
    sep = np.abs(positions[:, None] - positions[None, :])
    edges = np.logspace(np.log10(params.min_separation_bp), np.log10(sep.max() + 1), params.n_distance_classes)
    k = np.digitize(sep, edges)
    oe = np.full_like(counts, np.nan)
    for kk in np.unique(k):
        m = (k == kk) & (sep > 0)
        if not m.any():
            continue
        mu = counts[m].mean()
        if mu > 0:
            oe[m] = counts[m] / mu
    logoe = np.where(oe > 0, np.log2(np.where(oe > 0, oe, 1.0)), 0.0)
    with np.errstate(invalid="ignore", divide="ignore"):
        corr = np.nan_to_num(np.corrcoef(logoe))
    pc1 = np.linalg.eigh(corr)[1][:, -1]
    if marker is not None:
        marker = np.asarray(marker, dtype=np.float64)
        ok = np.isfinite(marker)
        if ok.sum() > 1 and np.corrcoef(pc1[ok], marker[ok])[0, 1] < 0:
            pc1 = -pc1
    return pc1


def _rows_at(table: pd.DataFrame, chrom: np.ndarray, pos: np.ndarray) -> np.ndarray:
    """For each ``(chrom, pos)``: the row (position in ``table``) whose ``[start, end)`` holds ``pos`` on
    that chromosome; -1 for none."""
    out = np.full(len(pos), -1, dtype=np.int64)
    tchrom = table["chrom"].astype(str).to_numpy()
    for c in np.unique(chrom):
        rows = np.flatnonzero(tchrom == c)
        if not len(rows):
            continue
        order = rows[np.argsort(table["start"].to_numpy()[rows], kind="mergesort")]
        starts = table["start"].to_numpy(np.int64)[order]
        ends = table["end"].to_numpy(np.int64)[order]
        want = np.flatnonzero(chrom == c)
        k = np.searchsorted(starts, pos[want], side="right") - 1
        ok = (k >= 0) & (pos[want] < ends[np.clip(k, 0, None)])
        out[want[ok]] = order[k[ok]]
    return out


def _loci_midpoints(bins: pd.DataFrame):
    return bins["chrom"].astype(str).to_numpy(), (bins["start"].to_numpy(np.int64) + bins["end"].to_numpy(np.int64)) // 2


def call_compartments_hic(
    cd,
    *,
    contacts="default",
    resolution: Optional[int] = None,
    chrom=None,
    orient_by: Optional[str] = None,
    params: Optional[HiCCompartmentParams] = None,
    key_added: Optional[str] = "compartments.hic_pc1",
    copy: bool = False,
):
    """A/B compartments of a Hi-C map linked to ``cd``: PC1 of the observed / expected correlation matrix.

    Parameters
    ----------
    cd : ChromData
        Holds the link (``cd.link_cool(path, key=...)``) and receives the result.
    contacts : str
        Key of ``cd.uns['linked_cool']`` (default ``"default"``) or a path to a ``.cool`` / ``.mcool``.
    resolution : int, optional
        Required for ``.mcool``.
    chrom : str, sequence of str, or None
        ``None``: the chromosomes of ``cd`` that the map has (every map chromosome when ``cd`` has no spots).
    orient_by : str, optional
        A ``cd.bin_tracks`` column that is higher in A (gene density, an active mark): PC1 is oriented to
        correlate positively with it (the track of the loci inside each Hi-C bin, averaged).  Without it the
        sign — and so which label is A — is arbitrary.
    params : HiCCompartmentParams, optional
        Distance classes of the expected counts; ``balance=True`` for the ICE-balanced matrix.
    key_added : str or None
        ``cd.results`` key (default ``"compartments.hic_pc1"``); ``None`` does not store.
    copy : bool
        ``True`` → return a new ChromData holding the result.

    Returns
    -------
    DataFrame (``copy=False``) or ChromData (``copy=True``)
        One row per Hi-C bin with contacts: ``chrom, start, end, bin_index`` (in the map, per chromosome),
        ``compartment`` (``"A"`` where ``pc1 > 0``) and ``pc1``.  When stored, also the runs of equal label
        as the ``segment`` table ``cd.intervals[key_added]`` and PC1 on the loci of ``cd`` (the Hi-C bin
        holding each locus' midpoint) as ``cd.bin_tracks[f"{key_added}.pc1"]``.
    """
    from uchrom.fea.maps import contact_matrix, map_path, open_map

    if copy and key_added is None:
        raise ValueError("call_compartments_hic(): copy=True needs a key_added")
    params = params or HiCCompartmentParams()
    path = map_path(cd, contacts)
    clr = open_map(path, resolution=resolution)
    if chrom is None:
        wanted = resolve_chroms(cd, None) if len(cd.spots) else []
        chroms = [c for c in wanted if c in clr.chromnames] or list(clr.chromnames)
    else:
        chroms = resolve_chroms(cd, chrom)
    if orient_by is not None and orient_by not in cd.bin_tracks.columns:
        raise KeyError(f"orient_by={orient_by!r} is not a column of cd.bin_tracks ({list(cd.bin_tracks.columns)})")

    frames: List[pd.DataFrame] = []
    for c in chroms:
        bins, mat = contact_matrix(clr, chrom=c, balance=params.balance)
        keep = np.flatnonzero(mat.sum(axis=1) > 0)
        hb = bins.iloc[keep].reset_index(drop=True).astype({"chrom": str})
        marker = None
        if orient_by is not None:
            lchrom, mid = _loci_midpoints(cd.bins)
            row = _rows_at(hb, lchrom, mid)
            track = cd.bin_tracks[orient_by].to_numpy(dtype=float)
            ok = row >= 0
            marker = (pd.Series(track[ok]).groupby(row[ok]).mean()
                      .reindex(np.arange(len(hb))).to_numpy(dtype=float))
        pc1 = hic_compartment_pc1(mat[np.ix_(keep, keep)], hb["start"].to_numpy(), marker=marker, params=params)
        frames.append(hb.assign(bin_index=keep.astype(np.int64), compartment=np.where(pc1 > 0, "A", "B"), pc1=pc1))
    empty = pd.DataFrame({"chrom": pd.Series(dtype=str), "start": pd.Series(dtype="int64"),
                          "end": pd.Series(dtype="int64"), "bin_index": pd.Series(dtype="int64"),
                          "compartment": pd.Series(dtype=str), "pc1": pd.Series(dtype=float)})
    table = merge_tables(frames, empty)[list(empty.columns)]
    label = path if path == str(Path(str(contacts)).expanduser()) else str(contacts)
    inputs = {"contacts": label, "contacts_path": str(path),
              "resolution": int(clr.binsize) if clr.binsize else None, "chrom": list(chroms),
              "orient_by": orient_by}
    out = store_and_return(
        cd, table, key_added=key_added, copy=copy, kind="table",
        function="uchrom.strc.comp.call_compartments_hic", params=params, inputs=inputs,
        intervals=[(key_added, compartment_segments(table, score="pc1"), "segment")] if key_added else (),
    )
    if key_added is not None:
        target = out if copy else cd
        lchrom, mid = _loci_midpoints(target.bins)
        row = _rows_at(table, lchrom, mid)
        values = np.where(row >= 0, table["pc1"].to_numpy()[np.clip(row, 0, None)], np.nan)
        bt = target.bin_tracks.copy()
        bt[f"{key_added}.pc1"] = values
        target.bin_tracks = bt
    return out


_SCORES = ("pc2", "pc1", "score")


def _per_locus(cd, call: Union[str, pd.DataFrame]):
    table = pd.DataFrame(cd.results[call] if isinstance(call, str) else call).reset_index(drop=True)
    label = "compartment" if "compartment" in table.columns else "label"
    score = next((c for c in _SCORES if c in table.columns), None)
    if label not in table.columns or score is None:
        raise KeyError(f"a compartment table needs a 'compartment' (or 'label') column and one of {_SCORES}")
    lchrom, mid = _loci_midpoints(cd.bins)
    row = _rows_at(table.astype({"chrom": str}), lchrom, mid)
    ok = row >= 0
    labels = np.where(ok, table[label].astype(str).to_numpy()[np.clip(row, 0, None)], None)
    scores = np.where(ok, table[score].to_numpy(dtype=float)[np.clip(row, 0, None)], np.nan)
    return labels, scores, ok


def compare_compartments(cd, query: Union[str, pd.DataFrame], reference: Union[str, pd.DataFrame], *,
                         chrom=None) -> Dict[str, float]:
    """How well two compartment calls agree on the loci of ``cd``.

    Parameters
    ----------
    cd : ChromData
        Its ``bins`` are the common axis: each locus takes the label and score of the bin of each call that
        holds its midpoint.
    query, reference : str or DataFrame
        Keys of ``cd.results`` or per-bin tables with ``chrom, start, end``, ``compartment`` (or ``label``)
        and a score column (``pc2``, ``pc1`` or ``score``), e.g. :func:`call_compartments_axes_pc` on the
        imaging and :func:`call_compartments_hic` on Hi-C of the same loci.
    chrom : str or sequence of str, optional
        Compare only these chromosomes.

    Returns
    -------
    dict
        ``n_bins`` (loci called by both), ``agreement`` (fraction of them with the same label) and
        ``pearson_r`` (correlation of the two scores).
    """
    lq, sq, okq = _per_locus(cd, query)
    lr, sr, okr = _per_locus(cd, reference)
    both = okq & okr
    if chrom is not None:
        keep = {chrom} if isinstance(chrom, str) else set(map(str, chrom))
        both &= cd.bins["chrom"].astype(str).isin(keep).to_numpy()
    finite = both & np.isfinite(sq) & np.isfinite(sr)
    agreement = float(np.mean(lq[both] == lr[both])) if both.any() else float("nan")
    r = float(np.corrcoef(sq[finite], sr[finite])[0, 1]) if finite.sum() > 1 else float("nan")
    return {"n_bins": int(both.sum()), "agreement": agreement, "pearson_r": r}


__all__ = ["HiCCompartmentParams", "call_compartments_hic", "compare_compartments", "hic_compartment_pc1"]
