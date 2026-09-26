"""Shared plumbing for the ChromData analysis calling convention.

Every ``cd``-level analysis function follows (see
``docs/source/guide/chromdata_2_0_design.md``, section 3)::

    def call_x(cd, *, chrom=None, trace_ids=None, cells=None,
               params=None, device="auto", key_added="<what>.<method>",
               copy=False) -> DataFrame | ChromData

* ``chrom=None`` runs every chromosome and merges the per-chromosome
  outputs into **one** table under **one** key.
* ``key_added`` is the ``cd.results`` key (``None`` = do not store).
* ``copy=False`` returns the primary table; ``copy=True`` returns a new
  ``ChromData`` holding the result and leaves ``cd`` untouched.

The helpers here implement the parts every caller shares, including the
deprecation path for the 1.x keywords (positional ``chrom``, ``store=``,
``result_key=``).
"""

from __future__ import annotations

import warnings
from typing import Any, Iterable, List, Mapping, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

#: Sentinel for "argument not passed" (lets us detect deprecated keywords).
UNSET: Any = type("_Unset", (), {"__repr__": lambda self: "UNSET", "__bool__": lambda self: False})()


def parse_legacy_call(
    func_name: str,
    args: Tuple[Any, ...],
    *,
    chrom: Any,
    key_added: Any,
    store: Any,
    result_key: Any,
    default_key: str,
    legacy_key: Optional[str],
    copy: bool = False,
    stacklevel: int = 3,
) -> Tuple[Any, Optional[str], bool]:
    """Map 1.x arguments onto the convention.

    Returns ``(chrom, key_added, legacy)``.  ``legacy`` is True when any
    deprecated form was used — the caller then keeps the 1.x default key
    (``legacy_key``, e.g. ``"tads"``) so old code that reads
    ``cd.results["tads"]`` keeps working.
    """
    legacy = False
    if args:
        if len(args) > 1:
            raise TypeError(
                f"{func_name}() takes 1 positional argument (cd) plus an optional "
                f"deprecated positional chrom; got {1 + len(args)}"
            )
        if chrom is not None:
            raise TypeError(f"{func_name}() got chrom both positionally and as a keyword")
        chrom = args[0]
        legacy = True
        warnings.warn(
            f"{func_name}(cd, chrom, ...) is deprecated; pass chrom=... as a "
            f"keyword (chrom=None runs every chromosome).",
            DeprecationWarning,
            stacklevel=stacklevel,
        )
    if result_key is not UNSET:
        if key_added is not UNSET:
            raise TypeError(f"{func_name}(): pass key_added=, not both key_added= and result_key=")
        warnings.warn(
            f"{func_name}(result_key=...) is deprecated; use key_added=...",
            DeprecationWarning,
            stacklevel=stacklevel,
        )
        key_added = result_key
        legacy = True
    if store is not UNSET:
        warnings.warn(
            f"{func_name}(store=...) is deprecated; use key_added=None to skip "
            f"storing the result.",
            DeprecationWarning,
            stacklevel=stacklevel,
        )
        legacy = True
        if not store:
            key_added = None
    if key_added is UNSET:
        key_added = legacy_key if (legacy and legacy_key) else default_key
    if copy and key_added is None:
        raise ValueError(f"{func_name}(): copy=True needs a key_added to store the result under")
    return chrom, key_added, legacy


def resolve_chroms(cd, chrom: Optional[Any]) -> List[str]:
    """``chrom=None`` → chromosomes that actually have spots, in category
    order; a string → ``[chrom]``; a sequence → ``list(chrom)``."""
    if chrom is None and getattr(cd, "backed", False):
        # from index/ (no per-spot read): partitions / runs carry the chromosome
        idx = cd._index
        names = [str(c) for c in cd.bins["chrom"].cat.categories]
        codes = np.asarray(idx["partition_chrom"] if getattr(cd, "partitioned", False)
                           else idx["chrom_trace"])
        if (codes >= 0).all():
            present = set(int(c) for c in np.unique(codes))
            return [n for i, n in enumerate(names) if i in present]
    if chrom is None:
        col = cd.spots["chrom"]
        present = set(map(str, pd.unique(col.astype(str))))
        order = list(col.cat.categories) if hasattr(col, "cat") else list(pd.unique(col))
        return [str(c) for c in order if str(c) in present]
    if isinstance(chrom, (str, bytes)) or np.isscalar(chrom):
        return [str(chrom)]
    return [str(c) for c in chrom]


def select_spots(cd, *, trace_ids: Optional[Iterable] = None, cells: Optional[Iterable] = None):
    """Subset ``cd`` to the given traces / cells (``cd`` itself if neither)."""
    if trace_ids is None and cells is None:
        return cd
    mask = np.ones(cd.n_spots, dtype=bool)
    if trace_ids is not None:
        keep = {str(t) for t in trace_ids}
        mask &= cd.spots["trace_id"].astype(str).isin(keep).to_numpy()
    if cells is not None:
        if "cell_id" not in cd.spots.columns:
            raise KeyError("cells= given but spots has no 'cell_id' column")
        keep = {str(c) for c in cells}
        mask &= cd.spots["cell_id"].astype(str).isin(keep).to_numpy()
    if not mask.any():
        raise ValueError("trace_ids / cells selection matches no spots")
    return cd[mask]


def merge_tables(frames: Sequence[pd.DataFrame], empty: pd.DataFrame) -> pd.DataFrame:
    """Merge per-chromosome outputs into one table.

    Empty frames are skipped; a single non-empty frame is returned as is
    (so a one-chromosome call is identical to the 1.x per-chromosome
    output); no rows at all → ``empty``.
    """
    rows = [f for f in frames if f is not None and not f.empty]
    if not rows:
        return empty
    if len(rows) == 1:
        return rows[0]
    return pd.concat(rows, ignore_index=True)


def selection_inputs(cd, chroms: Sequence[str], trace_ids, cells) -> dict:
    """The ``inputs`` provenance block shared by the tracing callers."""
    inputs = {
        "chrom": list(chroms),
        "coords": "coords",
        "n_spots": int(cd.n_spots),
        "n_traces": int(cd.n_traces),
    }
    if trace_ids is not None:
        inputs["trace_ids"] = [str(t) for t in trace_ids]
    if cells is not None:
        inputs["cells"] = [str(c) for c in cells]
    return inputs


def store_and_return(
    cd,
    table: pd.DataFrame,
    *,
    key_added: Optional[str],
    copy: bool,
    kind: str,
    function: str,
    params: Any,
    inputs: Mapping[str, Any],
    extra: Sequence[Tuple[str, Any, str]] = (),
    interval_kind: Optional[str] = None,
    intervals: Sequence[Tuple[str, pd.DataFrame, str]] = (),
    bin_tracks: Optional[Mapping[str, pd.DataFrame]] = None,
):
    """Store ``table`` (and ``extra`` ``(key, value, kind)`` records) with
    provenance, then return per the convention.

    ``kind="intervals"`` tables are also exposed as ``cd.intervals[key_added]``
    (the same object, typed ``interval_kind``).  ``intervals`` adds more
    ``(key, table, interval_kind)`` interval tables (e.g. compartment
    segments) and ``bin_tracks`` maps a track name to a frame with
    ``chrom, start, end, value`` that is written to ``cd.bin_tracks``.
    """
    target = cd.copy() if copy else cd
    if key_added is not None:
        if kind == "intervals" and hasattr(target, "intervals"):
            table = target.intervals.add(key_added, table, kind=interval_kind,
                                         source_result=key_added)
        target.results.set(key_added, table, kind=kind, function=function,
                           params=params, inputs=inputs)
        for key, value, extra_kind in extra:
            target.results.set(key, value, kind=extra_kind, function=function,
                               params=params, inputs=inputs)
        for key, value, ikind in intervals:
            target.intervals.add(key, value, kind=ikind, source_result=key_added)
        for name, frame in (bin_tracks or {}).items():
            _set_bin_track(target, name, frame)
    return target if copy else table


def _set_bin_track(cd, name: str, frame: pd.DataFrame) -> None:
    """Write ``frame["value"]`` onto ``cd.bin_tracks[name]`` by exact locus."""
    from uchrom.core.bins import map_loci_to_bins

    ids = map_loci_to_bins(frame, cd.bins)
    values = np.full(cd.n_bins, np.nan)
    ok = ids >= 0
    values[ids[ok]] = frame["value"].to_numpy(dtype=float)[ok]
    bt = cd.bin_tracks.copy()
    bt[name] = values
    cd.bin_tracks = bt


__all__ = [
    "UNSET",
    "merge_tables",
    "parse_legacy_call",
    "resolve_chroms",
    "select_spots",
    "selection_inputs",
    "store_and_return",
]
