"""``cd``-level Directionality-Index TAD caller on linked Hi-C contacts.

Wraps the matrix-level kernel :func:`uchrom.strc.tad.di.get_domains`
(Dixon et al. 2012) in the ChromData calling convention.  The contact
matrix comes from a ``.cool`` / ``.mcool`` linked with
:meth:`ChromData.link_cool` (``cd.uns['linked_cool'][contacts]``) or
from a path, read with :func:`uchrom.fea.open_map` /
:func:`uchrom.fea.contact_matrix`.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

import pandas as pd

from uchrom.convention import merge_tables, resolve_chroms, store_and_return


@dataclass(frozen=True)
class DICallerParams:
    """Knobs of :func:`call_tads_di` (defaults = :func:`get_domains`)."""

    window: int = 50                # DI window, in bins
    smoothing_param: float = 0.1    # moving-average window, fraction of n_bins
    min_size_frac: float = 0.05     # minimum TAD size, fraction of n_bins


_DI_COLUMNS = ("chrom", "start", "end", "start_bin", "end_bin")


def _empty_di() -> pd.DataFrame:
    return pd.DataFrame({
        "chrom": pd.Series(dtype=str),
        "start": pd.Series(dtype="int64"),
        "end": pd.Series(dtype="int64"),
        "start_bin": pd.Series(dtype="int64"),
        "end_bin": pd.Series(dtype="int64"),
    })


def _contacts_label(contacts, path: str) -> str:
    """Provenance of ``contacts=``: the key of a linked map, or the path of a map given as a path."""
    return path if path == str(Path(str(contacts)).expanduser()) else str(contacts)


def call_tads_di(
    cd,
    *,
    contacts="default",
    resolution: Optional[int] = None,
    balance: bool = True,
    chrom=None,
    params: Optional[DICallerParams] = None,
    device: str = "auto",
    key_added: Optional[str] = "tads.di",
    copy: bool = False,
):
    """Directionality-index TADs on a linked Hi-C contact matrix.

    Parameters
    ----------
    cd : ChromData
        Holds the link (``cd.link_cool(path, key=...)``) and receives the
        result.
    contacts : str
        Key of ``cd.uns['linked_cool']`` (default ``"default"``) or a path
        to a ``.cool`` / ``.mcool``.
    resolution : int, optional
        Required for ``.mcool``; checked against a ``.cool``'s bin size.
    balance : bool
        Use the cooler ``weight`` column (falls back to raw counts, with
        a warning, when the file is not balanced).
    chrom : str, sequence of str, or None
        ``None`` → the chromosomes of ``cd.spots`` that the cooler has,
        or every cooler chromosome when ``cd`` has no spots on any of
        them (e.g. Hi-C-only data).
    params : DICallerParams, optional
    key_added : str or None
        ``cd.results`` key (default ``"tads.di"``); ``None`` does not store.
    copy : bool
        ``True`` → return a new ChromData holding the result.

    Returns
    -------
    DataFrame (``copy=False``) or ChromData (``copy=True``)
        ``chrom, start, end, start_bin, end_bin`` — bin indices are
        per-chromosome, ``end_bin`` exclusive, exactly as returned by
        :func:`get_domains`.  (The kernel's last domain stops one bin
        short of the chromosome end; this is kept as is.)
    """
    import torch

    from uchrom.fea.maps import contact_matrix, map_path, open_map

    from .di import get_domains

    if copy and key_added is None:
        raise ValueError("call_tads_di(): copy=True needs a key_added")
    params = params or DICallerParams()
    path = map_path(cd, contacts, resolution=resolution)
    clr = open_map(path, resolution=resolution)

    if chrom is None:
        wanted = resolve_chroms(cd, None) if len(cd.spots) else []
        chroms = [c for c in wanted if c in clr.chromnames] or list(clr.chromnames)
    else:
        chroms = resolve_chroms(cd, chrom)

    frames: List[pd.DataFrame] = []
    for c in chroms:
        bins, mat = contact_matrix(clr, chrom=c, balance=balance)
        domains = get_domains(
            torch.as_tensor(mat, dtype=torch.float64),
            smoothing_param=params.smoothing_param,
            min_size_frac=params.min_size_frac,
            window=params.window,
            device=device,
        )
        rows = []
        for s, e in domains:
            s, e = int(s), int(e)
            if e <= s:
                continue
            rows.append({
                "chrom": c,
                "start": int(bins["start"].iat[s]),
                "end": int(bins["end"].iat[e - 1]),
                "start_bin": s,
                "end_bin": e,
            })
        frames.append(pd.DataFrame(rows, columns=list(_DI_COLUMNS)))
    table = merge_tables(frames, _empty_di())
    inputs = {
        "contacts": _contacts_label(contacts, path),
        "contacts_path": str(path),
        "resolution": int(clr.binsize) if clr.binsize else None,
        "balance": bool(balance),
        "chrom": list(chroms),
    }
    return store_and_return(
        cd, table, key_added=key_added, copy=copy, kind="intervals", interval_kind="domain",
        function="uchrom.strc.tad.call_tads_di", params=params, inputs=inputs,
    )


__all__ = ["DICallerParams", "call_tads_di"]
