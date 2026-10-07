"""Distance-based statistics of chromatin traces: population distance maps, contact frequency, radius of
gyration and the distance matrix of one trace.

Every function takes a ``ChromData`` (in memory or backed) and the chromosome to use (``chrom=``; may be
left out when the data have one chromosome), optionally restricted to some traces / cells
(``trace_ids=``, ``cells=``)::

    dm = distance_map(cd, "chr2")                        # exact median map, streams a backed store
    freq, bins, n = contact_frequency(cd, 0.18, chrom="chr2")
    rg = radius_of_gyration(cd, chrom="chr2")            # one value per trace
    d, loci = trace_distance_matrix(cd, "2_45_2_1")     # one trace on every locus of its chromosome

:func:`mean_distance_matrix`, :func:`contact_frequency` and :func:`radius_of_gyration` also take the flat
table ``chrom, start, end, x, y, z, trace_id`` that ``ChromData.to_dataframe()`` produces (the 1.x form,
kept).  The dense helper :func:`_bin_coord_cube` pivots such a table into a ``(n_traces, n_bins, 3)``
array with NaN for missing spots, which makes every statistic a NaN-aware reduction;
:func:`distance_map` and the ``ChromData`` form of :func:`contact_frequency` never build it.
"""

from __future__ import annotations

from typing import Iterable, Optional, Tuple

import numpy as np
import pandas as pd


def _is_chromdata(x) -> bool:
    return hasattr(x, "spots") and hasattr(x, "bins") and hasattr(x, "coords")


def _select(cd, trace_ids, cells):
    from uchrom.convention import select_spots

    return select_spots(cd, trace_ids=trace_ids, cells=cells)


def _one_chrom(cd, chrom, what: str) -> str:
    """``chrom``, or the only chromosome with spots."""
    if chrom is not None:
        return str(chrom)
    from uchrom.convention import resolve_chroms

    chroms = resolve_chroms(cd, None)
    if len(chroms) != 1:
        shown = ", ".join(chroms[:6]) + (", ..." if len(chroms) > 6 else "")
        raise ValueError(f"{what}: the data have {len(chroms)} chromosomes ({shown}); pass chrom=")
    return chroms[0]


def _filter_table(df: pd.DataFrame, trace_ids, cells) -> pd.DataFrame:
    if trace_ids is not None:
        df = df[df["trace_id"].astype(str).isin({str(t) for t in trace_ids})]
    if cells is not None:
        if "cell_id" not in df.columns:
            raise KeyError("cells= given but the table has no 'cell_id' column")
        df = df[df["cell_id"].astype(str).isin({str(c) for c in cells})]
    return df


def _chrom_table(data, chrom, trace_ids, cells, what: str) -> Tuple[pd.DataFrame, Optional[str]]:
    """The flat table of one chromosome: from a ``ChromData`` (``to_dataframe`` of the selected spots of
    ``chrom``) or a table (rows of the selected traces / cells)."""
    if not _is_chromdata(data):
        return _filter_table(data, trace_ids, cells), chrom
    work = _select(data, trace_ids, cells)
    chrom = _one_chrom(work, chrom, what)
    return work.get_chrom(chrom, columns="coords").to_dataframe(), chrom


def _bin_coord_cube(df: pd.DataFrame, chrom=None):
    """Pivot a flat spots+coords table into a per-trace coordinate cube.

    Returns
    -------
    cube : ndarray, shape (n_traces, n_bins, 3)
        Coordinates with NaN where a trace is missing a bin.
    bin_ids : list of tuples
        ``(start, end)`` for each bin, sorted by ``start``.
    trace_ids : list
        Trace identifiers in cube axis-0 order.
    """
    required = {"chrom", "start", "end", "x", "y", "z", "trace_id"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"DataFrame missing columns: {missing}")

    if chrom is not None:
        df = df[df["chrom"].astype(str) == str(chrom)]
    if df.empty:
        raise ValueError("No rows after filtering; cannot compute cube.")

    # Coerce start/end to int so dict-key lookups don't fall over float.
    df = df.assign(
        start=df["start"].astype(np.int64),
        end=df["end"].astype(np.int64),
    )

    bins = (
        df[["start", "end"]]
        .drop_duplicates()
        .sort_values("start", kind="mergesort")
        .reset_index(drop=True)
    )
    bin_ids = [(int(s), int(e)) for s, e in zip(bins["start"], bins["end"])]
    bin_to_idx = {k: i for i, k in enumerate(bin_ids)}
    n_bins = len(bin_ids)

    trace_ids = list(df["trace_id"].unique())
    tid_to_idx = {t: i for i, t in enumerate(trace_ids)}
    n_traces = len(trace_ids)

    cube = np.full((n_traces, n_bins, 3), np.nan, dtype=np.float64)
    ti = np.asarray(
        [tid_to_idx[t] for t in df["trace_id"]], dtype=np.int64
    )
    bi = np.asarray(
        [bin_to_idx[(int(s), int(e))] for s, e in zip(df["start"], df["end"])],
        dtype=np.int64,
    )
    cube[ti, bi, 0] = df["x"].to_numpy()
    cube[ti, bi, 1] = df["y"].to_numpy()
    cube[ti, bi, 2] = df["z"].to_numpy()
    return cube, bin_ids, trace_ids


def _pairwise_distance_per_trace(cube: np.ndarray) -> np.ndarray:
    """Return a (n_traces, n_bins, n_bins) Euclidean distance tensor.

    Missing spots propagate as NaN distances.
    """
    diff = cube[:, :, None, :] - cube[:, None, :, :]
    return np.sqrt(np.sum(diff ** 2, axis=-1))


def mean_distance_matrix(
    data,
    chrom=None,
    reduce: str = "median",
    *,
    trace_ids: Optional[Iterable] = None,
    cells: Optional[Iterable] = None,
):
    """Population median / mean pairwise distance matrix — the dense reference of :func:`distance_map`.

    For each pair of genomic bins ``(i, j)``, the distance is computed per trace and then reduced across
    traces with ``np.nanmedian`` (the Bintu 2018 convention) or ``np.nanmean``.  The whole
    ``(n_traces, n_bins, n_bins)`` tensor is built, so this is for a locus of a few hundred bins;
    :func:`distance_map` gives the same matrix without it.

    Parameters
    ----------
    data : ChromData or DataFrame
        A ``ChromData``, or the flat table ``chrom, start, end, x, y, z, trace_id`` (``to_dataframe()``).
    chrom : str, optional
        The chromosome; with a ``ChromData`` it may be left out when the data have one.  A table without
        ``chrom`` is used whole.
    reduce : ``"median"`` (default) or ``"mean"``
    trace_ids, cells : optional
        Use only these traces / cells.

    Returns
    -------
    matrix : ndarray (n_bins, n_bins)
        Rows / columns = the observed bins sorted by start; a trace observing a bin twice keeps its last
        spot (merge them first with :func:`uchrom.im.merge_duplicate_spots`).
    bin_ids : list of (start, end)
    n_traces : int
    """
    df, chrom = _chrom_table(data, chrom, trace_ids, cells, "mean_distance_matrix")
    cube, bin_ids, trace_ids = _bin_coord_cube(df, chrom=chrom)
    dist = _pairwise_distance_per_trace(cube)
    if reduce == "mean":
        agg = np.nanmean(dist, axis=0)
    else:
        agg = np.nanmedian(dist, axis=0)
    return agg, bin_ids, len(trace_ids)


class DistanceMap(dict):
    """Result of :func:`distance_map` (a dict with attribute access):
    ``matrix`` (n_bins × n_bins), ``count`` (traces observing each pair;
    the diagonal counts the traces observing the bin), ``bins`` (``bin_id``,
    ``chrom``, ``start``, ``end`` of the rows), ``n_traces``, ``stat``,
    ``streaming``, ``n_passes`` (reads of the chromosome's traces),
    ``n_bands`` and ``duplicates``.  :meth:`coarsen` pools it into blocks."""

    __getattr__ = dict.__getitem__

    def coarsen(self, k: int, stat: str = "median", *, diagonal: bool = False) -> "DistanceMap":
        """The map pooled into blocks of ``k`` × ``k`` rows (e.g. 20 × 25-kb bins = 500 kb), for display or
        to gather the sparse pairs of a large locus panel.

        Parameters
        ----------
        k : int
            Rows per block; the last block holds the rest (``n_bins % k`` rows) when ``k`` does not divide
            the number of rows.  The rows are the map's own (observed) bins, in order — gaps between bins
            are not filled in.
        stat : ``"median"`` (default) or ``"mean"``
            How the finite values of a block are combined (NaN when it has none).
        diagonal : bool
            Include the self-distances (0) of the original diagonal; by default they are left out, so the
            blocks on the diagonal hold the distances between the different bins of the block.

        Returns
        -------
        DistanceMap
            ``matrix`` and ``count`` (pair observations pooled into each block: the sum of the original
            ``count`` over the block's entries, both triangles) of the blocks, ``bins`` (``chrom``, ``start`` of the first
            bin, ``end`` of the last, ``n_bins``), ``block_size`` = ``k``, and the other fields of this map.
        """
        import warnings

        k = int(k)
        if k < 1:
            raise ValueError("k must be >= 1")
        if stat not in ("median", "mean"):
            raise ValueError("stat must be 'median' or 'mean'")
        mat = np.asarray(self["matrix"], dtype=np.float64)
        cnt = np.asarray(self["count"], dtype=np.int64)
        n = len(mat)
        nb = -(-n // k)
        A = np.full((nb * k, nb * k), np.nan)
        A[:n, :n] = mat
        C = np.zeros((nb * k, nb * k), dtype=np.int64)
        C[:n, :n] = cnt
        if not diagonal:
            A[np.arange(n), np.arange(n)] = np.nan
            C[np.arange(n), np.arange(n)] = 0
        blocks = A.reshape(nb, k, nb, k).transpose(0, 2, 1, 3).reshape(nb, nb, k * k)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)        # all-NaN blocks
            pooled = np.nanmedian(blocks, axis=2) if stat == "median" else np.nanmean(blocks, axis=2)
        count = C.reshape(nb, k, nb, k).sum(axis=(1, 3))
        b = self["bins"].reset_index(drop=True)
        block = np.arange(len(b)) // k
        bins = (b.groupby(block, sort=True)
                 .agg(chrom=("chrom", "first"), start=("start", "first"), end=("end", "last"),
                      n_bins=("start", "size"))
                 .reset_index(drop=True))
        out = DistanceMap(self)
        out.update(matrix=pooled, count=count, bins=bins, block_size=k, block_stat=stat)
        return out


def distance_map(cd, chrom=None, stat: str = "median", *, trace_ids: Optional[Iterable] = None,
                 cells: Optional[Iterable] = None, duplicates: str = "last", streaming=None, batch="auto",
                 memory_budget=None, observed: bool = True) -> DistanceMap:
    """Population median / mean 3-D distance of every bin pair of one
    chromosome — exact, in memory or streaming over the traces.

    Same definition as :func:`mean_distance_matrix` (per trace, the
    Euclidean distance of its two spots; NaN / missing spots skipped; a
    trace observing a bin twice keeps its last spot, unless ``duplicates``
    says otherwise), but without the dense ``(n_traces, n_bins, n_bins)``
    tensor, so it runs on genome-wide data:

    * ``stat="mean"`` accumulates per-pair sums and counts in trace order
      (``np.add.at``) — the additions the dense ``np.nanmean`` makes, in the
      same order, so the result is bitwise identical (``float64``); memory
      ``O(n_bins²)``.
    * ``stat="median"`` is an **exact** median (the mean of the two middle
      values for an even count, as ``np.nanmedian``).  An exact median needs
      all values of a pair at once, so the observations are gathered for one
      *row band* of the matrix at a time — the rows ``i`` whose pairs
      ``(i, j > i)`` fit ``memory_budget`` (``BYTES_PER_OBS`` bytes each) —
      and reduced with a grouped median (pandas).  A band costs one pass over
      the chromosome's traces; memory is the band plus the ``n_bins²``
      output, independent of the number of traces.  No approximation.

    Parameters
    ----------
    cd : ChromData, in memory or backed
    chrom : str, optional
        The chromosome; may be left out when the data have one.
    stat : ``"median"`` or ``"mean"``
    trace_ids, cells : optional
        Use only these traces / cells (read in memory first).
    duplicates : ``"last"`` (default), ``"first"``, ``"mean"`` or ``"median"``
        The spot a trace keeps at a bin it observed more than once (sister chromatids, a stray spot):
        its last or first one, or the per-axis mean / median of them (NaN values skipped) — exactly
        the coordinates :func:`uchrom.im.merge_duplicate_spots` (``how=``) gives, so
        ``distance_map(cd, c, duplicates="mean")`` equals ``distance_map(merge_duplicate_spots(cd), c)``.
    streaming : bool, optional
        Read the traces in batches (``iter_traces(chrom=..., columns="coords")``) and band the
        median; default ``True`` for a backed object.  ``False`` gathers every observation at once
        (the in-memory baseline).
    batch : int or "auto"
        Traces per batch, or ``"auto"`` (from the memory budget).
    memory_budget : default :data:`uchrom.settings.memory_budget`
    observed : rows / columns = the chromosome's observed bins sorted by
        start (the :func:`mean_distance_matrix` convention), or every bin of
        the chromosome in ``cd.bins``

    Returns
    -------
    DistanceMap
    """
    from uchrom.utils.memory import release_memory

    from ._pairs import BYTES_PER_OBS, MAX_BLOCK_PAIRS, ChromPairs, check_duplicates, pair_distance

    if stat not in ("median", "mean"):
        raise ValueError("stat must be 'median' or 'mean'")
    check_duplicates(duplicates)
    cd = _select(cd, trace_ids, cells)
    chrom = _one_chrom(cd, chrom, "distance_map")
    P = ChromPairs(cd, chrom, streaming=streaming, batch=batch, observed=observed,
                   memory_budget=memory_budget, duplicates=duplicates)
    P.prepare()
    B = P.n_bins
    passes = 1
    idx_dtype = np.int32 if B * B < 2 ** 31 else np.int64
    count = np.zeros(B * B, dtype=np.int32)
    out = np.full(B * B, np.nan)
    if stat == "mean":
        total = np.zeros(B * B, dtype=np.float64)
        for i, j, ci, cj in P.pairs():
            idx = i * B + j
            np.add.at(total, idx, pair_distance(ci, cj))
            np.add.at(count, idx, 1)
        passes += 1
        n_bands = 1
        with np.errstate(invalid="ignore", divide="ignore"):
            np.divide(total, count, out=out, where=count > 0)
        del total
    else:
        # the n_bins² outputs, a block of pairs, a batch of traces
        fixed = B * B * 12 + MAX_BLOCK_PAIRS * 100 + int(0.1 * P.memory_budget)
        bands = P.bands(BYTES_PER_OBS, fixed_bytes=fixed)
        n_bands = len(bands)
        for lo, hi in bands:
            n_obs = int(P.row_counts[lo:hi].sum())
            if not n_obs:
                continue
            idx = np.empty(n_obs, dtype=idx_dtype)
            d = np.empty(n_obs, dtype=np.float64)
            pos = 0
            for i, j, ci, cj in P.pairs(lo, hi):
                m = len(i)
                idx[pos:pos + m] = i * B + j
                d[pos:pos + m] = pair_distance(ci, cj)
                pos += m
            passes += 1
            if pos != n_obs:  # pragma: no cover - the two passes must agree
                raise RuntimeError(f"pair count changed between passes ({pos} != {n_obs})")
            g = pd.Series(d, copy=False).groupby(idx, sort=True)
            med = g.median()
            del d
            keys = med.index.to_numpy()
            out[keys] = med.to_numpy()
            count[keys] = g.size().to_numpy()
            del g, med, idx, keys
            release_memory()
    mat = out.reshape(B, B)
    cnt = count.reshape(B, B)
    for i in range(B - 1):                 # mirror the upper triangle, in place
        mat[i + 1:, i] = mat[i, i + 1:]
        cnt[i + 1:, i] = cnt[i, i + 1:]
    diag = np.arange(B)
    cnt[diag, diag] = P.bin_counts
    mat[diag, diag] = np.where(P.bin_counts > 0, 0.0, np.nan)
    return DistanceMap(matrix=mat, count=cnt, bins=P.bin_table(), n_traces=int(P.n_traces),
                       stat=stat, streaming=P.streaming, n_passes=passes, n_bands=n_bands,
                       chrom=str(chrom), duplicates=duplicates)


def contact_frequency(
    data,
    threshold: float,
    chrom=None,
    *,
    trace_ids: Optional[Iterable] = None,
    cells: Optional[Iterable] = None,
    duplicates: str = "last",
    streaming=None,
    batch="auto",
    memory_budget=None,
):
    """Fraction of traces where a pair of bins are within ``threshold``.

    NaN distances (missing spots) are excluded from both numerator and
    denominator — each bin pair's frequency is over the set of traces
    that have both endpoints detected.

    Parameters
    ----------
    data : ChromData or DataFrame
        A ``ChromData`` (in memory or backed: the traces are streamed as by :func:`distance_map`, so no
        ``(n_traces, n_bins, n_bins)`` tensor is built), or the flat table ``chrom, start, end, x, y, z,
        trace_id`` (``to_dataframe()``; the dense computation).  Both give the same matrix.
    threshold : float
        Distance threshold in the unit of the coordinates.
    chrom : str, optional
        The chromosome; with a ``ChromData`` it may be left out when the data have one.
    trace_ids, cells : optional
        Use only these traces / cells.
    duplicates : ``"last"`` (default), ``"first"``, ``"mean"`` or ``"median"``
        With a ``ChromData``: the spot a trace keeps at a bin it observed twice (see :func:`distance_map`).
        The table form keeps the last.
    streaming, batch, memory_budget
        With a ``ChromData``: as for :func:`distance_map`.

    Returns
    -------
    frequency : ndarray (n_bins, n_bins) in [0, 1], NaN where no
        trace had both endpoints detected; rows = the observed bins sorted by start.
    bin_ids : list of (start, end)
    n_traces : int
    """
    if not _is_chromdata(data):
        if duplicates != "last":
            raise ValueError("duplicates= needs a ChromData; the table form keeps the last spot of a bin")
        df = _filter_table(data, trace_ids, cells)
        cube, bin_ids, trace_ids = _bin_coord_cube(df, chrom=chrom)
        dist = _pairwise_distance_per_trace(cube)
        valid = ~np.isnan(dist)
        contact = np.where(valid, dist < threshold, False)
        n_contacts = contact.sum(axis=0)
        n_valid = valid.sum(axis=0)
        with np.errstate(divide="ignore", invalid="ignore"):
            freq = np.where(n_valid > 0, n_contacts / n_valid, np.nan)
        return freq, bin_ids, len(trace_ids)

    from ._pairs import ChromPairs, pair_distance

    cd = _select(data, trace_ids, cells)
    chrom = _one_chrom(cd, chrom, "contact_frequency")
    P = ChromPairs(cd, chrom, streaming=streaming, batch=batch, observed=True,
                   memory_budget=memory_budget, duplicates=duplicates)
    P.prepare()
    B = P.n_bins
    n_valid = np.zeros(B * B, dtype=np.int64)
    n_contacts = np.zeros(B * B, dtype=np.int64)
    for i, j, ci, cj in P.pairs():
        idx = i * B + j
        n_valid += np.bincount(idx, minlength=B * B)
        n_contacts += np.bincount(idx[pair_distance(ci, cj) < threshold], minlength=B * B)
    n_valid = n_valid.reshape(B, B)
    n_contacts = n_contacts.reshape(B, B)
    iu = np.triu_indices(B, 1)
    n_valid.T[iu] = n_valid[iu]                    # mirror the upper triangle
    n_contacts.T[iu] = n_contacts[iu]
    diag = np.arange(B)
    n_valid[diag, diag] = P.bin_counts             # a detected spot is at distance 0 of itself
    n_contacts[diag, diag] = P.bin_counts if 0.0 < threshold else 0
    with np.errstate(divide="ignore", invalid="ignore"):
        freq = np.where(n_valid > 0, n_contacts / n_valid, np.nan)
    return freq, P.bin_intervals(), int(P.n_traces)


def _rg_of_table(df: pd.DataFrame) -> pd.Series:
    rgs = {}
    for tid, sdf in df.groupby("trace_id", observed=True):
        pos = sdf[["x", "y", "z"]].to_numpy()
        if pos.shape[0] < 2:
            rgs[tid] = np.nan
            continue
        centroid = pos.mean(axis=0)
        rgs[tid] = float(np.sqrt(np.mean(np.sum((pos - centroid) ** 2, axis=1))))
    return pd.Series(rgs, name="rg", dtype=np.float64).sort_index()


def radius_of_gyration(data, chrom=None, *, trace_ids: Optional[Iterable] = None,
                       cells: Optional[Iterable] = None) -> pd.Series:
    """Per-trace radius of gyration.

    ``Rg = sqrt(mean over spots of ||r - centroid||²)`` over every spot of the trace (a locus detected
    twice counts twice).  Traces with fewer than 2 spots get NaN.

    Parameters
    ----------
    data : ChromData or DataFrame
        A ``ChromData`` — spots with a non-finite coordinate (undetected loci) are left out, and a trace
        without a detected spot is not listed — or the flat table ``chrom, start, end, x, y, z, trace_id``
        (``to_dataframe()``; every row is used, so a NaN coordinate makes the trace's Rg NaN: drop such
        rows first).
    chrom : str, optional
        Only the traces of this chromosome (default: all).
    trace_ids, cells : optional
        Use only these traces / cells.

    Returns
    -------
    Series
        ``rg`` per trace, indexed by ``trace_id`` (sorted), in the unit of the coordinates.
    """
    if not _is_chromdata(data):
        df = _filter_table(data, trace_ids, cells)
        if chrom is not None:
            df = df[df["chrom"].astype(str) == str(chrom)]
        return _rg_of_table(df)
    cd = _select(data, trace_ids, cells)
    if chrom is not None:
        cd = cd.get_chrom(str(chrom), columns="coords")
    xyz = np.asarray(cd.coords, dtype=np.float64)
    ok = np.isfinite(xyz).all(axis=1)
    df = pd.DataFrame(xyz[ok], columns=["x", "y", "z"])
    df["trace_id"] = cd.spots["trace_id"].iloc[np.flatnonzero(ok)].reset_index(drop=True)
    return _rg_of_table(df)


def _chrom_loci(cd, chrom: str) -> pd.DataFrame:
    """The loci of ``chrom`` in ``cd.bins``, sorted by start: ``bin_id, chrom, start, end``."""
    bins = cd.bins
    loci = bins[bins["chrom"].astype(str) == str(chrom)].sort_values("start", kind="mergesort")
    if loci.empty:
        raise KeyError(f"no loci on {chrom!r} in cd.bins")
    out = loci[["chrom", "start", "end"]].astype({"chrom": str}).reset_index(names="bin_id")
    return out.astype({"start": np.int64, "end": np.int64})


def trace_distance_matrix(cd, trace_id, chrom: Optional[str] = None, *,
                          duplicates: str = "last") -> Tuple[np.ndarray, pd.DataFrame]:
    """The pairwise 3-D distances of one trace over every locus of its chromosome.

    Unlike ``cd.compute_distances(trace_id=...)`` (the trace's own spots), the rows are the loci of the
    chromosome in ``cd.bins``, so matrices of different traces — and the population map of
    :func:`distance_map` with ``observed=False`` — share one axis.

    Parameters
    ----------
    cd : ChromData
    trace_id
        The trace (``"12"`` finds an integer id 12 and the reverse).
    chrom : str, optional
        Its chromosome, needed only when the trace spans several.
    duplicates : ``"last"`` (default), ``"first"``, ``"mean"`` or ``"median"``
        The spot kept at a locus the trace observed more than once (as for :func:`distance_map`).

    Returns
    -------
    matrix : ndarray (n_loci, n_loci)
        NaN for loci the trace did not detect.
    loci : DataFrame
        ``bin_id, chrom, start, end`` of the rows (the chromosome's loci sorted by start).
    """
    from ._pairs import check_duplicates

    check_duplicates(duplicates)
    t = cd.get_trace(trace_id)
    if t.n_spots == 0:                      # "12" for an integer id 12, or the reverse
        col = cd.spots["trace_id"]
        ids = col.cat.categories if hasattr(col, "cat") else pd.unique(col)
        same = [c for c in ids if str(c) == str(trace_id)]
        if same:
            t = cd.get_trace(same[0])
    if t.n_spots == 0:
        raise KeyError(f"trace {trace_id!r} has no spots")
    chroms = pd.unique(t.spots_with_loci()["chrom"].astype(str))
    if chrom is None:
        if len(chroms) != 1:
            raise ValueError(f"trace {trace_id!r} spans {list(chroms)}; pass chrom=")
        chrom = str(chroms[0])
    loci = _chrom_loci(cd, chrom)
    row = pd.Series(np.arange(len(loci)), index=loci["bin_id"].to_numpy())
    rows = row.reindex(t.spots["bin_id"].to_numpy()).to_numpy()
    ok = np.isfinite(rows)
    r = rows[ok].astype(np.int64)
    c = np.asarray(t.coords, dtype=np.float64)[ok]
    xyz = np.full((len(loci), 3), np.nan)
    if duplicates == "last":
        xyz[r] = c
    elif duplicates == "first":
        xyz[r[::-1]] = c[::-1]
    else:
        from uchrom.im.spots import _group_reduce

        uniq, inv = np.unique(r, return_inverse=True)
        xyz[uniq] = _group_reduce(c, inv, len(uniq), duplicates)
    return np.linalg.norm(xyz[:, None] - xyz[None], axis=-1), loci


__all__ = [
    "DistanceMap",
    "distance_map",
    "mean_distance_matrix",
    "contact_frequency",
    "radius_of_gyration",
    "trace_distance_matrix",
]
