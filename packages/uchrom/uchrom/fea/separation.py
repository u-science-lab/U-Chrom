"""Per-cell proximity by genomic separation, from contacts or from 3-D coordinates: one question asked of sequencing
and imaging data alike.

Single-cell Hi-C counts how often two loci touch; chromatin tracing measures how far apart they are.  Both change
with the genomic separation of the two loci, and how they change differs between cell types (the share of short-
over long-range contacts: Nagano et al. 2017, Nature 547:61; Tan et al. 2021, Cell 184:741).
:func:`separation_profile` computes for every cell the same summary from either kind of data:

* **contacts** — the per-cell maps linked to the object (a ``.scool``, or maps embedded in an atlas store, also over
  HTTP): the cis contacts whose two bins lie a separation apart;
* **coordinates** — the spots of the cell's traces: the 3-D distance of every pair of spots of one trace (one
  chromosome copy) whose loci lie a separation apart, reduced per cell to the median (or mean) and, with
  ``threshold``, to the share of pairs closer than it.

The separation is that of the bin or locus midpoints in both, so the contacts of a 1-Mb map at offset ``k`` are at
``k`` Mb, as are two loci imaged ``k`` Mb apart.  ``short`` and ``long`` (half-open ranges, bp) give the summary::

    log2_short_long = log2((n_short + pseudocount) / (n_long + pseudocount))     contacts
    log2_short_long = log2(d_long / d_short)                                     coordinates

both higher when the short range is relatively closer (more contacts, shorter distances).  Only differences
within a dataset (between cell types, conditions) are meant to be compared, never values across assays.
``edges`` adds the whole profile per cell: contacts per separation bin (the cell's contact-decay curve) or the
distance per separation bin (its distance scaling)::

    t = separation_profile(cd)                                   # per-cell maps or traces, whichever cd holds
    t.groupby(cd.cells["cell_type"])["log2_short_long"].median()
    separation_profile(cd, params=SeparationParams(edges=np.arange(0.5, 100.5) * 1e6))
    cd.cellm["separation.profile"]                               # cells x 100 separation bins
"""

from __future__ import annotations

import warnings
from dataclasses import asdict, dataclass
from typing import List, Optional, Sequence, Tuple, Union

import numpy as np
import pandas as pd

from ..convention import UNSET

__all__ = ["SeparationParams", "separation_profile"]


@dataclass
class SeparationParams:
    """Ranges and reductions of :func:`separation_profile`.

    Attributes
    ----------
    short, long
        Half-open separation ranges ``[lo, hi)`` (bp, midpoint to midpoint) of the summary.  The defaults take
        map offset 1 (1 Mb) and offsets 19-53 of a 1-Mb map, and loci 1-2 Mb and 19-54 Mb apart.
    edges
        Separation bin edges (bp, increasing; bins ``[edges[k], edges[k + 1])``) of the profile stored per cell;
        ``None``: no profile.
    chroms
        The chromosomes used (default: every chromosome but those in ``exclude``).
    exclude
        Left out when ``chroms`` is not given (matched without the ``chr`` prefix, any case): the sex
        chromosomes, whose copy number differs between cells and sexes, and the mitochondrial genome.
    stat
        ``"median"`` (default) or ``"mean"`` distance of a cell's pairs in a range (coordinates).
    threshold
        Coordinates: also the share of a cell's pairs in a range closer than this distance (the units of the
        coordinates), ``f_short`` / ``f_long``.
    pseudocount
        Added to both counts of the contact ratio (cells without contacts in a range keep a finite ratio).
    duplicates
        Coordinates: the spot a trace keeps at a bin it observed more than once (``"last"``, ``"first"``,
        ``"mean"``, ``"median"``; as :func:`uchrom.fea.distance_map`).
    """

    short: Tuple[float, float] = (1.0e6, 2.0e6)
    long: Tuple[float, float] = (1.9e7, 5.4e7)
    edges: Optional[Sequence[float]] = None
    chroms: Optional[Sequence[str]] = None
    exclude: Sequence[str] = ("chrX", "chrY", "chrM")
    stat: str = "median"
    threshold: Optional[float] = None
    pseudocount: float = 0.5
    duplicates: str = "last"


# ----------------------------------------------------------------------------------------------------------
# ranges
# ----------------------------------------------------------------------------------------------------------

class _Layer:
    """Disjoint separation ranges ``[lo[k], hi[k])`` sorted by ``lo``; ``assign`` gives each separation its range
    (or -1)."""

    def __init__(self, name: str, lo, hi):
        self.name = name
        self.lo = np.asarray(lo, np.float64)
        self.hi = np.asarray(hi, np.float64)

    def __len__(self) -> int:
        return len(self.lo)

    def assign(self, sep: np.ndarray) -> np.ndarray:
        k = np.searchsorted(self.lo, sep, side="right") - 1
        ok = k >= 0
        ok[ok] = sep[ok] < self.hi[k[ok]]
        return np.where(ok, k, -1)


def _layers(p: SeparationParams) -> List[_Layer]:
    out = []
    for name in ("short", "long"):
        lo, hi = (float(v) for v in getattr(p, name))
        if not 0 <= lo < hi:
            raise ValueError(f"params.{name} = ({lo:g}, {hi:g}): need 0 <= lo < hi")
        out.append(_Layer(name, [lo], [hi]))
    if p.edges is not None:
        e = np.asarray(p.edges, np.float64)
        if e.ndim != 1 or len(e) < 2 or not np.all(np.diff(e) > 0) or e[0] < 0:
            raise ValueError("params.edges: at least two increasing separations >= 0")
        out.append(_Layer("profile", e[:-1], e[1:]))
    return out


def _label(lo: float, hi: float) -> str:
    def f(v):
        return f"{v / 1e6:g}M" if v >= 1e6 else f"{v / 1e3:g}k" if v >= 1e3 else f"{v:g}"
    return f"{f(lo)}_{f(hi)}"


def _norm(c) -> str:
    s = str(c).lower()
    return s[3:] if s.startswith("chr") else s


def _keep_chroms(names: Sequence[str], p: SeparationParams) -> np.ndarray:
    if p.chroms is not None:
        want = {str(c) for c in p.chroms}
        return np.array([str(c) in want for c in names], bool)
    drop = {_norm(c) for c in p.exclude}
    return np.array([_norm(c) not in drop for c in names], bool)


# ----------------------------------------------------------------------------------------------------------
# contacts
# ----------------------------------------------------------------------------------------------------------

def _per_cell_map_keys(cd) -> List[str]:
    from chromdata.cdata import _linked_records

    return list(_linked_records(cd.uns.get("linked_scool"))) if hasattr(cd, "uns") else []


def _from_contacts(cd, keys: Sequence[str], units: pd.Index, layers: List[_Layer], p: SeparationParams,
                   workers: int, max_pixels: int, warn_missing: bool = True):
    """Per unit: cis contacts (all, between different bins) and contacts per range of every layer."""
    from .pseudobulk_maps import _Grid, _prefetch, _source_of

    n = len(units)
    sums = [np.zeros(n * len(L)) for L in layers]
    n_cis = np.zeros(n)
    n_apart = np.zeros(n)
    measured = np.zeros(n, bool)
    sources = []
    max_hi = max(float(L.hi.max()) for L in layers)
    for key in keys:
        source, desc, _ = _source_of(cd, key, max_pixels)
        base = int(source.base)
        row = units.get_indexer(pd.Index([str(c) for c in source.cells]))
        idx = np.flatnonzero(row >= 0)
        if warn_missing and len(idx) < len(row) and len(units):
            warnings.warn(f"{key!r}: {len(row) - len(idx)} of {len(row)} cells with maps are not in cd.cells and "
                          "are left out", stacklevel=3)
        if not len(idx):
            continue
        measured[row[idx]] = True
        keep = _keep_chroms(source.chroms, p)
        # offsets of the map -> range of each layer (separation = offset * bin size, midpoint to midpoint)
        n_off = int(np.ceil(max_hi / base)) + 1
        seps = np.arange(n_off, dtype=np.float64) * base
        lookup = [L.assign(seps) for L in layers]

        def add(cell, off, cnt):
            u = row[cell]
            n_cis[:] += np.bincount(u, weights=cnt, minlength=n)
            apart = off > 0
            n_apart[:] += np.bincount(u[apart], weights=cnt[apart], minlength=n)
            near = off < n_off
            u, off, cnt = u[near], off[near], cnt[near]
            for L, lk, acc in zip(layers, lookup, sums):
                k = lk[off]
                m = k >= 0
                acc += np.bincount(u[m] * len(L) + k[m], weights=cnt[m], minlength=len(acc))

        if source.sequential:                           # embedded maps: one cis partition at a time
            tasks = (t for t in source.tasks(False, idx) if keep[t[0]])
            for _p, cell, b1, b2, c in _prefetch(source.read, tasks, int(workers)):
                add(cell, np.abs(b2.astype(np.int64) - b1.astype(np.int64)), c.astype(np.float64))
        else:                                           # a .scool: genome-wide bins, cell by cell
            chrom_of = _Grid(source.chroms, source.sizes, base, base).chrom_of_fine
            for cell, b1, b2, c in source.iter_cells(idx):
                c1 = chrom_of[b1]
                m = (c1 == chrom_of[b2]) & keep[c1]
                add(cell[m], np.abs(b2[m] - b1[m]), c[m].astype(np.float64))
        sources.append({**desc, "resolution": base, "n_cells": int(len(idx)),
                        "chroms": [c for c, k in zip(source.chroms, keep) if k]})
    return sums, n_cis, n_apart, measured, sources


# ----------------------------------------------------------------------------------------------------------
# coordinates
# ----------------------------------------------------------------------------------------------------------

def _from_coords(work, units: pd.Index, by_cell: bool, layers: List[_Layer], p: SeparationParams, batch):
    """Per unit: traces, spots and, per range of every layer, the pairs and their distance statistics."""
    from chromdata.bins import BIN_ID

    from ._pairs import MAX_BLOCK_PAIRS, _drop_rows, _pair_rows, _remaining, check_duplicates, \
        grouped_order_stats, pair_distance, reduce_duplicates

    check_duplicates(p.duplicates)
    if p.stat not in ("median", "mean"):
        raise ValueError("params.stat must be 'median' or 'mean'")
    bins = work.bins
    size = int(np.max(bins.index.to_numpy())) + 1 if len(bins) else 0
    mid = np.full(size, np.nan)
    mid[bins.index.to_numpy()] = (bins["start"].to_numpy(np.float64) + bins["end"].to_numpy(np.float64)) / 2.0
    chrom_col = bins["chrom"].astype("category")
    chrom_code = np.full(size, -1, np.int64)
    chrom_code[bins.index.to_numpy()] = chrom_col.cat.codes.to_numpy()
    keep_code = _keep_chroms([str(c) for c in chrom_col.cat.categories], p)
    used_chroms = [str(c) for c, k in zip(chrom_col.cat.categories, keep_code) if k]

    n = len(units)
    count = [np.zeros(n * len(L), np.int64) for L in layers]
    value = [np.full(n * len(L), np.nan) for L in layers]
    close = [np.zeros(n * len(L)) for L in layers] if p.threshold is not None else None
    n_traces = np.zeros(n, np.int64)
    n_spots = np.zeros(n, np.int64)

    if by_cell:
        chunks = work.iter_cells(batch, columns="coords")
    else:                                               # traces only: one chunk (a trace id may span runs)
        chunks = work.iter_traces(max(1, int(work.n_traces)), columns="coords")
    for chunk in chunks:
        s = chunk.spots
        if not len(s):
            continue
        bid = s[BIN_ID].to_numpy().astype(np.int64)
        xyz = np.asarray(chunk.coords, np.float64)
        tr = s["trace_id"]
        tr = tr if isinstance(tr.dtype, pd.CategoricalDtype) else tr.astype("category")
        trace = tr.cat.codes.to_numpy().astype(np.int64)
        if by_cell:
            ce = s["cell_id"]
            ce = ce if isinstance(ce.dtype, pd.CategoricalDtype) else ce.astype("category")
            cell = ce.cat.codes.to_numpy().astype(np.int64)
            unit = units.get_indexer(pd.Index([str(c) for c in ce.cat.categories]))[cell]
        else:
            cell = np.zeros(len(s), np.int64)
            unit = units.get_indexer(pd.Index([str(c) for c in tr.cat.categories]))[trace]
        chrom = chrom_code[bid]
        new_run = np.r_[True, (trace[1:] != trace[:-1]) | (cell[1:] != cell[:-1]) | (chrom[1:] != chrom[:-1])]
        keep = keep_code[chrom] & (unit >= 0)
        if not keep.all():
            run_id = np.cumsum(new_run)
            r = run_id[keep]
            new_run = np.r_[True, r[1:] != r[:-1]] if len(r) else np.zeros(0, bool)
            bid, xyz, unit = bid[keep], xyz[keep], unit[keep]
        if not len(bid):
            continue
        run_unit = unit[new_run]                        # one unit per run (a run is one trace of one cell)
        bid, xyz, new_run = reduce_duplicates(bid, xyz, new_run, p.duplicates)
        run_of = np.cumsum(new_run) - 1
        ok = np.isfinite(xyz).all(axis=1)
        runs = np.r_[np.flatnonzero(new_run), len(bid)].astype(np.int64)
        bid, runs = _drop_rows(bid, runs, ok)
        xyz, unit = xyz[ok], run_unit[run_of[ok]]
        m = len(bid)
        if not m:
            continue
        n_traces += np.bincount(unit[runs[:-1]], minlength=n)
        n_spots += np.bincount(unit, minlength=n)
        rem = _remaining(runs, m)
        csum = np.cumsum(rem)
        total = int(csum[-1])
        if not total:
            continue
        cuts = np.searchsorted(csum, np.arange(MAX_BLOCK_PAIRS, total, MAX_BLOCK_PAIRS), side="left")
        bounds = np.unique(np.r_[0, cuts + 1, m])
        keys = [[] for _ in layers]
        vals = [[] for _ in layers]
        for r0, r1 in zip(bounds[:-1], bounds[1:]):
            a, b = _pair_rows(rem, int(r0), int(r1))
            if not len(a):
                continue
            sep = np.abs(mid[bid[b]] - mid[bid[a]])
            d = pair_distance(xyz[a], xyz[b])
            u = unit[a]
            for i, L in enumerate(layers):
                k = L.assign(sep)
                sel = k >= 0
                keys[i].append(u[sel] * len(L) + k[sel])
                vals[i].append(d[sel])
        # the chunk holds whole units, so its keys are final
        for i in range(len(layers)):
            if not keys[i]:
                continue
            kk = np.concatenate(keys[i])
            vv = np.concatenate(vals[i])
            if not len(kk):
                continue
            if p.stat == "median":
                gk, cnt, lo, hi, _ = grouped_order_stats(kk, vv)
                value[i][gk] = (lo + hi) / 2.0              # the mean of the middle two, as np.median
                count[i][gk] += cnt
            else:
                c = np.bincount(kk, minlength=len(count[i]))
                s_ = np.bincount(kk, weights=vv, minlength=len(count[i]))
                hit = c > 0
                value[i][hit] = s_[hit] / c[hit]
                count[i] += c
            if close is not None:
                close[i] += np.bincount(kk, weights=(vv < p.threshold).astype(np.float64), minlength=len(close[i]))
    return count, value, close, n_traces, n_spots, used_chroms


# ----------------------------------------------------------------------------------------------------------
# the function
# ----------------------------------------------------------------------------------------------------------

def _choose_source(cd, source: str, contacts) -> str:
    if source not in ("auto", "contacts", "coords"):
        raise ValueError("source must be 'auto', 'contacts' or 'coords'")
    if source != "auto":
        return source
    if contacts is not None:
        return "contacts"
    maps = _per_cell_map_keys(cd)
    coords = int(getattr(cd, "n_spots", 0)) > 0
    if maps and coords and "cell_id" in cd.spots.columns:
        raise ValueError("cd holds both per-cell contact maps and per-cell coordinates: pass source='contacts' "
                         "or source='coords'")
    if maps:
        return "contacts"
    if coords:
        return "coords"
    raise ValueError("cd has neither per-cell contact maps (cd.link_scool) nor coordinates")


def separation_profile(cd, *, source: str = "auto", contacts: Union[None, str, Sequence[str]] = None,
                       cells: Optional[Sequence] = None, params: Optional[SeparationParams] = None,
                       batch: Union[int, str] = 256, workers: int = 4, max_pixels: int = 2_000_000,
                       key_added=UNSET, copy: bool = False):
    """Per-cell proximity at short and long genomic separations (and optionally the whole profile), from the
    per-cell contact maps or from the traced coordinates of a ``ChromData``.

    Parameters
    ----------
    cd
        A ``ChromData``, in memory or backed: with per-cell maps linked (``cd.link_scool``; a local ``.scool``
        or maps embedded in the store, also an atlas store over HTTP), or with spots (one trace per chromosome
        copy; ``cell_id`` groups them into cells, without it every trace is a unit).
    source
        ``"contacts"``, ``"coords"`` or ``"auto"`` (the one ``cd`` holds; both: an error).
    contacts
        Keys of the linked per-cell maps (default: all of them, e.g. the two sections of a spatial Hi-C store),
        or a ``.scool`` path whose cell names are the cell ids.
    cells
        Only these cells (default all; traces without cells: these trace ids).
    params
        :class:`SeparationParams`.
    batch
        Coordinates: cells read at a time (``iter_cells``; ``"auto"`` from the memory budget).
    workers, max_pixels
        Contacts: reads of embedded maps in flight and pixels per read (:func:`uchrom.fea.pseudobulk`).
    key_added
        Prefix of the ``cd.cells`` columns written (default ``"separation"``; None: nothing stored), e.g.
        ``separation.log2_short_long``; the table is also ``cd.results[key_added]``, the profile (with
        ``edges``) ``cd.cellm["<key_added>.profile"]`` (cells x separation bins; coordinates also
        ``"<key_added>.n_pairs"``), with the bins in the result's parameters.
    copy
        Store on a copy of ``cd`` and return it.

    Returns
    -------
    DataFrame
        Indexed by cell id (trace id for traces without cells), one row per cell used (NaN for a cell without
        maps or spots).  Contacts: ``n_cis`` (cis contacts of the chromosomes used, also within a bin),
        ``n_apart`` (between different bins), ``n_short``, ``n_long``, ``log2_short_long``.  Coordinates:
        ``n_traces``, ``n_spots`` (finite), ``d_short``, ``d_long`` (median or mean distance),
        ``n_pairs_short``, ``n_pairs_long``, ``f_short`` / ``f_long`` (with ``threshold``),
        ``log2_short_long``.  Without a stored key the profile is ``out.attrs["profile"]``.
    """
    from ..convention import store_and_return

    p = params or SeparationParams()
    layers = _layers(p)
    kind = _choose_source(cd, source, contacts)

    by_cell = kind == "contacts" or "cell_id" in cd.spots.columns
    axis = pd.Index([str(c) for c in cd._cell_ids_axis()], name="cell_id") if len(cd.cells) else None
    work = cd
    if kind == "coords" and cells is not None and by_cell:
        work = cd.get_cells(cells, columns="coords")
    if by_cell:
        if axis is not None:
            units = axis
        elif kind == "coords":
            units = pd.Index(sorted({str(c) for c in pd.unique(work.spots["cell_id"].astype(str))}), name="cell_id")
        else:
            from .pseudobulk_maps import _source_of

            keys = [contacts] if isinstance(contacts, str) else list(contacts or _per_cell_map_keys(cd))
            ids = []
            for k in keys:
                ids += [str(c) for c in _source_of(cd, k, max_pixels)[0].cells]
            units = pd.Index(list(dict.fromkeys(ids)), name="cell_id")
    else:
        units = pd.Index([str(t) for t in pd.unique(cd.spots["trace_id"].astype(str))], name="trace_id")
    if cells is not None:
        want = pd.Index([str(c) for c in cells])
        units = units[units.isin(want)]
        if not len(units):
            raise ValueError("cells: none of them is in cd")
    n = len(units)

    out = pd.DataFrame(index=units)
    if kind == "contacts":
        keys = [contacts] if isinstance(contacts, str) else list(contacts or _per_cell_map_keys(cd))
        if not keys:
            raise ValueError("no per-cell contact maps linked to cd (cd.link_scool)")
        sums, n_cis, n_apart, measured, sources = _from_contacts(cd, keys, units, layers, p, workers, max_pixels,
                                                                     warn_missing=cells is None)
        nan = np.where(measured, 1.0, np.nan)
        out["n_cis"] = n_cis * nan
        out["n_apart"] = n_apart * nan
        out["n_short"] = sums[0] * nan
        out["n_long"] = sums[1] * nan
        out["log2_short_long"] = np.log2((out["n_short"] + p.pseudocount) / (out["n_long"] + p.pseudocount))
        profile = sums[2].reshape(n, -1) * nan[:, None] if len(layers) > 2 else None
        pairs = None
        inputs = {"source": "contacts", "per_cell_maps": sources, "n_cells": int(measured.sum())}
    else:
        count, value, close, n_traces, n_spots, used = _from_coords(work, units, by_cell, layers, p, batch)
        out["n_traces"] = n_traces
        out["n_spots"] = n_spots
        for i, name in enumerate(("short", "long")):
            out[f"d_{name}"] = value[i]
            out[f"n_pairs_{name}"] = count[i]
            if close is not None:
                with np.errstate(invalid="ignore", divide="ignore"):
                    out[f"f_{name}"] = np.where(count[i] > 0, close[i] / np.maximum(count[i], 1), np.nan)
        with np.errstate(invalid="ignore", divide="ignore"):
            out["log2_short_long"] = np.log2(out["d_long"] / out["d_short"])
        profile = value[2].reshape(n, -1) if len(layers) > 2 else None
        pairs = count[2].reshape(n, -1) if len(layers) > 2 else None
        inputs = {"source": "coords", "chroms": used, "n_spots": int(n_spots.sum()), "n_traces": int(n_traces.sum()),
                  "units": "cells" if by_cell else "traces", "coordinate_unit": cd.uns.get("xyz_unit")}

    edges = None if p.edges is None else [float(v) for v in p.edges]
    if key_added is UNSET:
        key_added = "separation"
    if key_added is None:
        if profile is not None:                     # (attrs only here: a stored table must stay JSON-clean)
            labels = [_label(a, b) for a, b in zip(edges[:-1], edges[1:])]
            out.attrs["profile"] = pd.DataFrame(profile, index=units, columns=labels)
            if pairs is not None:
                out.attrs["n_pairs"] = pd.DataFrame(pairs, index=units, columns=labels)
        return out

    target = cd.copy() if copy else cd
    stored = {**asdict(p), "short": list(p.short), "long": list(p.long), "edges": edges,
              "chroms": None if p.chroms is None else [str(c) for c in p.chroms], "exclude": list(p.exclude)}
    if by_cell and len(target.cells):
        axis_t = pd.Index([str(c) for c in target._cell_ids_axis()])
        pos = axis_t.get_indexer(out.index)
        cells_df = target.cells.copy()
        for col in out.columns:
            v = np.full(len(cells_df), np.nan)
            v[pos[pos >= 0]] = out[col].to_numpy(np.float64)[pos >= 0]
            cells_df[f"{key_added}.{col}"] = v
        target.cells = cells_df
        for name, arr in (("profile", profile), ("n_pairs", pairs)):
            if arr is None:
                continue
            full = np.full((len(axis_t), arr.shape[1]), np.nan)
            full[pos[pos >= 0]] = arr[pos >= 0]
            target.cellm[f"{key_added}.{name}"] = full
    store_and_return(target, out.reset_index(), key_added=key_added, copy=False, kind="table",
                     function="uchrom.fea.separation_profile", params=stored, inputs=inputs)
    return target if copy else out
