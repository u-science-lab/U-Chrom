"""Contact maps linked to a ``ChromData``: read one as a matrix, rebin it onto other bins, observed / expected.

A bulk (or pseudo-bulk) Hi-C map stays in its ``.cool`` / ``.mcool`` file and is *linked* to the
``ChromData`` (``cd.link_cool(path, key=...)``; ``uchrom.datasets.load`` does this for the Hi-C datasets).
The functions here take the ``ChromData`` and the key of the map (``contacts=``; ``None`` = the only linked
map, or the path of a ``.cool`` / ``.mcool``), or a path::

    hic = ds.load("rao2014_imr90_chr21")                  # the 5 kb map, linked as "bulk"
    rebin_map(hic, "bulk", resolution=100_000)             # -> linked as "bulk_100kb" (ICE-balanced)
    thin_map(hic, "bulk", fraction=0.05)                   # -> "bulk_5pct": the map at 5 % of its depth
    bins, M = contact_matrix(hic, "bulk_100kb", chrom="chr21")
    oe = observed_over_expected(M)
"""

from __future__ import annotations

import os
import tempfile
import warnings
from pathlib import Path
from typing import Optional, Sequence, Tuple, Union

import numpy as np
import pandas as pd

__all__ = ["map_path", "open_map", "contact_matrix", "rebin_map", "thin_map", "observed_over_expected"]

#: default of ``rebin_map(key_added=...)``: ``"<contacts>_<resolution>"`` (e.g. ``"bulk_100kb"``)
AUTO = "auto"

_SCRATCH: dict = {}


def _is_chromdata(x) -> bool:
    return hasattr(x, "uns") and hasattr(x, "spots") and hasattr(x, "link_cool")


def _is_cooler(x) -> bool:
    return hasattr(x, "matrix") and hasattr(x, "chromnames") and hasattr(x, "pixels")


def _resolution_label(res: int, sep: str = "") -> str:
    res = int(res)
    if res % 1_000_000 == 0:
        return f"{res // 1_000_000}{sep}Mb"
    if res % 1000 == 0:
        return f"{res // 1000}{sep}kb"
    return f"{res}{sep}bp"


def _map_key(cd, contacts: Optional[str]) -> str:
    """The key of a linked ``.cool`` / ``.mcool``: ``contacts``, or the only one linked."""
    from chromdata.cdata import _linked_records

    records = _linked_records(cd.uns.get("linked_cool"))
    if contacts is None:
        if len(records) == 1:
            return next(iter(records))
        if "default" in records:
            return "default"
        raise KeyError(f"{len(records)} contact maps are linked ({sorted(records)}); pass contacts=<key>"
                       if records else "no contact map is linked (cd.link_cool(path, key=...))")
    if contacts not in records:
        raise KeyError(f"contacts={contacts!r} is not a linked map; linked: {sorted(records)}")
    return contacts


def _given_path(x) -> Optional[str]:
    """``x`` as the path of an existing file (``~`` expanded; a ``file::/group`` URI as is), else ``None``."""
    if x is None:
        return None
    text = str(x)
    if "::" in text:
        return text if Path(text.split("::", 1)[0]).expanduser().exists() else None
    path = Path(text).expanduser()
    return str(path) if path.exists() else None


def _is_linked(cd, contacts) -> bool:
    from chromdata.cdata import _linked_records

    return contacts is None or str(contacts) in _linked_records(cd.uns.get("linked_cool"))


def map_path(cd, contacts: Optional[str] = None, *, resolution: Optional[int] = None) -> str:
    """Path of a contact map: the file linked to ``cd`` under ``contacts`` (``None``: the only linked map;
    an embedded copy is exported once — only the level ``resolution`` when given —, see
    :meth:`chromdata.ChromData.linked_cool_path`), or ``contacts`` itself when it is not a linked key but the
    path of a ``.cool`` / ``.mcool`` — or ``cd`` itself when it is such a path."""
    if not _is_chromdata(cd):
        path = _given_path(cd)
        if path is None:
            raise FileNotFoundError(f"{cd}: no such contact map")
        return path
    if not _is_linked(cd, contacts):
        path = _given_path(contacts)
        if path is not None:
            return path
    return cd.linked_cool_path(_map_key(cd, contacts), resolution=resolution)


def open_map(cd, contacts: Optional[str] = None, *, resolution: Optional[int] = None):
    """A contact map as a ``cooler.Cooler``.

    Parameters
    ----------
    cd
        A ``ChromData`` with the map linked (``cd.link_cool``), or the path of a ``.cool`` / ``.mcool``.
    contacts
        Key of the linked map (``None``: the only one) or the path of a map.
    resolution
        The level of an ``.mcool`` (required when it has several); checked against a ``.cool``.

    Returns
    -------
    cooler.Cooler
    """
    return _open(map_path(cd, contacts, resolution=resolution), resolution)


def _map_record(cd, contacts: Optional[str]) -> dict:
    if not _is_chromdata(cd):
        return {"path": str(cd)}
    if not _is_linked(cd, contacts) and _given_path(contacts) is not None:
        return {"path": _given_path(contacts)}
    from chromdata.cdata import _linked_records

    key = _map_key(cd, contacts)
    return {"key": key, **_linked_records(cd.uns.get("linked_cool"))[key]}


def _open(path: str, resolution: Optional[int]):
    """A ``cooler.Cooler``: a ``.cool`` (checked against ``resolution``) or the level of an ``.mcool``."""
    import cooler

    if "::" not in path and (path.endswith(".mcool") or cooler.fileops.is_multires_file(path)):
        levels = sorted(int(r.rsplit("/", 1)[-1]) for r in cooler.fileops.list_coolers(path))
        if resolution is None:
            if len(levels) > 1:
                raise ValueError(f"{path} has resolutions {levels}; pass resolution=")
            resolution = levels[0]
        if int(resolution) not in levels:
            raise ValueError(f"{path} has no level at {resolution} bp ({levels}); rebin_map() makes one")
        return cooler.Cooler(f"{path}::/resolutions/{int(resolution)}")
    clr = cooler.Cooler(path)
    if resolution is not None and clr.binsize is not None and int(resolution) != int(clr.binsize):
        raise ValueError(f"{path} is at {clr.binsize} bp, not {resolution}; rebin_map() makes a map at "
                         f"another resolution")
    return clr


def contact_matrix(cd, contacts: Optional[str] = None, *, chrom: str, resolution: Optional[int] = None,
                   balance: bool = True) -> Tuple[pd.DataFrame, np.ndarray]:
    """The contact matrix of one chromosome from a linked map.

    Parameters
    ----------
    cd
        A ``ChromData`` with the map linked (``cd.link_cool``), the path of a ``.cool`` / ``.mcool``, or a
        ``cooler.Cooler`` (:func:`open_map`; ``resolution`` is then ignored).
    contacts
        Key of the linked map (``None``: the only one) or the path of a map.
    chrom
        Chromosome (as named in the map).
    resolution
        The level of an ``.mcool`` (required when it has several); checked against a ``.cool``.
    balance
        Balanced values (the cooler ``weight`` column; raw counts with a warning when the map has none).

    Returns
    -------
    bins : DataFrame
        ``chrom``, ``start``, ``end`` of the rows (index 0..n-1).
    matrix : ndarray (n, n)
        float64; masked (NaN) entries of a balanced map are 0.
    """
    clr = cd if _is_cooler(cd) else open_map(cd, contacts, resolution=resolution)
    if chrom not in clr.chromnames:
        raise ValueError(f"{chrom!r} is not in the map ({list(clr.chromnames)[:10]})")
    bins = clr.bins().fetch(chrom)
    use = bool(balance)
    if use and "weight" not in bins.columns:
        warnings.warn(f"{clr.uri}: not balanced (no 'weight' column); using raw counts", stacklevel=2)
        use = False
    mat = np.asarray(clr.matrix(balance=use).fetch(chrom), dtype=np.float64)
    mat[~np.isfinite(mat)] = 0.0
    out = bins[["chrom", "start", "end"]].reset_index(drop=True)
    out["chrom"] = out["chrom"].astype(str)
    return out, mat


def _scratch_dir() -> Path:
    d = _SCRATCH.get("maps")
    if d is None:
        import atexit
        import shutil

        d = Path(tempfile.mkdtemp(prefix="uchrom-maps-"))
        atexit.register(shutil.rmtree, d, True)
        _SCRATCH["maps"] = d
    return d


#: maps with at most this many pixels are balanced in memory (:func:`uchrom.fea.ice`, ~60 B per pixel), larger
#: ones too when ``uchrom.settings.memory_budget`` holds them; otherwise by cooler's out-of-core balancing (the
#: same weights, but the file is re-read every iteration: hours for a genome-wide 25-kb map)
ICE_IN_MEMORY_MAX = 50_000_000
ICE_BYTES_PER_PIXEL = 60


def _balance_cool(path: Path) -> None:
    """ICE-balance a ``.cool`` in place with ``cooler balance`` defaults (the ``weight`` column + its stats)."""
    import cooler
    import h5py

    clr = cooler.Cooler(str(path))
    nnz = int(clr.info["nnz"])
    if nnz > ICE_IN_MEMORY_MAX:
        from chromdata.settings import settings

        if nnz * ICE_BYTES_PER_PIXEL > settings.memory_budget:
            cooler.balance_cooler(clr, store=True)
            return
    from .pseudobulk_maps import ice

    with h5py.File(path, "r+") as h5:
        px = h5["pixels"]
        weight, stats = ice(px["bin1_id"][:], px["bin2_id"][:], px["count"][:], h5["indexes/chrom_offset"][:])
        h5["bins"].create_dataset("weight", data=weight, compression="gzip", compression_opts=6)
        h5["bins/weight"].attrs.update(stats)


def _rebin_cool(clr, out: Path, resolution: int, anchor: int, chroms: Sequence[str], balance: bool) -> Path:
    """Sum the pixels of ``clr`` into bins of ``resolution`` whose edges fall on ``anchor`` (snapped down
    to the map's own grid) + k * ``resolution`` (and the chromosome ends); ICE-balance (``cooler balance``
    defaults) when ``balance``."""
    import cooler

    base = clr.binsize
    if base is None:
        raise ValueError(f"{clr.uri}: variable-size bins cannot be rebinned")
    sizes = clr.chromsizes
    phase = (int(anchor) // base * base) % int(resolution)
    fine = clr.bins()[["chrom", "start", "end"]][:]
    f2c = np.full(len(fine), -1, dtype=np.int64)
    parts, offset = [], 0
    for c in chroms:
        length = int(sizes[c])
        edges = np.unique(np.r_[0, np.arange(phase, length, int(resolution)), length])
        parts.append(pd.DataFrame({"chrom": c, "start": edges[:-1], "end": edges[1:]}))
        lo, hi = clr.extent(c)
        starts = fine["start"].to_numpy()[lo:hi]
        f2c[lo:hi] = offset + np.searchsorted(edges, starts, side="right") - 1
        offset += len(edges) - 1
    bins = pd.concat(parts, ignore_index=True)

    def chunks():
        for c in chroms:                                    # pixels with bin1 on c: coarse bin1 on c too
            px = clr.pixels().fetch(c)
            b1 = f2c[px["bin1_id"].to_numpy()]
            b2 = f2c[px["bin2_id"].to_numpy()]
            ok = (b1 >= 0) & (b2 >= 0)
            if not ok.any():
                continue
            yield (pd.DataFrame({"bin1_id": np.minimum(b1, b2)[ok], "bin2_id": np.maximum(b1, b2)[ok],
                                 "count": px["count"].to_numpy()[ok]})
                   .groupby(["bin1_id", "bin2_id"], as_index=False)["count"].sum())

    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_name(f".{out.name}.{os.getpid()}.part")
    meta = {"rebinned_from": str(clr.uri), "resolution": int(resolution), "anchor": int(anchor),
            "balance": "ICE (cooler balance defaults)" if balance else "none"}
    cooler.create_cooler(str(tmp), bins, chunks(), ordered=True, assembly=clr.info.get("genome-assembly"),
                         metadata=meta)
    if balance:
        _balance_cool(tmp)
    os.replace(tmp, out)
    return out


def rebin_map(cd, contacts: Optional[str] = None, *, resolution: int, anchor: int = 0,
              chrom: Union[None, str, Sequence[str]] = None, balance: bool = True,
              out: Union[None, str, os.PathLike] = None, key_added: Optional[str] = AUTO, copy: bool = False):
    """A linked contact map summed into coarser bins, written as a ``.cool`` and linked to ``cd``.

    The bins of the new map have edges at ``anchor + k * resolution`` (``anchor`` snapped down to the map's
    own grid) and at the chromosome ends — ``anchor=0`` coarsens the map as ``cooler coarsen`` does; another
    anchor puts the edges on the grid of other data, e.g. the first segment of a chromatin tracing experiment,
    so that every imaged segment falls into exactly one bin.  The counts of the original bins are summed
    into the bin that holds their start; the new map is ICE-balanced (``cooler balance`` defaults) unless
    ``balance=False``.

    Parameters
    ----------
    cd
        ``ChromData`` with the map linked, or a path (then nothing is linked and the path is returned).
    contacts
        Key of the linked map (``None``: the only one).  An ``.mcool`` is read at its finest level.
    resolution
        Bin size of the new map (bp), a multiple of the map's own.
    anchor
        A position that is a bin edge of the new map.
    chrom
        Chromosome(s) to keep (default: all of the map).
    balance
        ICE-balance the new map (``weight`` column).
    out
        Where to write it (default: a scratch directory removed at exit).
    key_added
        Key under which the new map is linked (``cd.link_cool``; default ``"<contacts>_<resolution>"``, e.g.
        ``"bulk_100kb"``; ``None``: not linked).
    copy
        ``True``: link it to a copy of ``cd`` and return that.

    Returns
    -------
    The path of the new map (``copy=False``), or the copy of ``cd`` with the map linked.
    """
    import cooler

    resolution = int(resolution)
    path = map_path(cd, contacts)
    if "::" not in path and (path.endswith(".mcool") or cooler.fileops.is_multires_file(path)):
        levels = sorted(int(r.rsplit("/", 1)[-1]) for r in cooler.fileops.list_coolers(path))
        usable = [r for r in levels if resolution % r == 0]
        if not usable:
            raise ValueError(f"{path}: no level divides {resolution} bp ({levels})")
        clr = cooler.Cooler(f"{path}::/resolutions/{max(usable)}")
    else:
        clr = cooler.Cooler(path)
    if clr.binsize and resolution % int(clr.binsize):
        raise ValueError(f"resolution {resolution} is not a multiple of the map's {clr.binsize} bp")
    chroms = list(clr.chromnames) if chrom is None else ([chrom] if isinstance(chrom, str) else list(chrom))
    missing = sorted(set(chroms) - set(clr.chromnames))
    if missing:
        raise ValueError(f"not in the map: {missing}")
    key = _map_record(cd, contacts).get("key") or Path(path.split("::", 1)[0]).stem
    if key_added == AUTO:
        key_added = f"{key}_{_resolution_label(resolution)}"
    if out is None:
        out = _scratch_dir() / f"{key_added or key}{'' if anchor == 0 else f'_at{anchor}'}.cool"
    if copy and (key_added is None or not _is_chromdata(cd)):
        raise ValueError("rebin_map(copy=True) links the new map to a copy of a ChromData: pass one and a key_added")
    out = _rebin_cool(clr, Path(out), resolution, anchor, chroms, balance)
    if not _is_chromdata(cd) or key_added is None:
        return str(out)
    target = cd.copy() if copy else cd
    record = _map_record(cd, contacts)
    target.link_cool(str(Path(out).resolve()), key=key_added,
                     label=f"{record.get('label') or key}, rebinned to {_resolution_label(resolution, ' ')}"
                           + (" (ICE-balanced)" if balance else " (raw)"),
                     genome_assembly=record.get("genome_assembly") or clr.info.get("genome-assembly"),
                     bin_size=resolution, anchor=int(anchor), rebinned_from=key, balanced=bool(balance))
    return target if copy else str(out)


def rebin_scool(cd, contacts: str = "per_cell", *, resolution: int, out: Union[str, os.PathLike],
                key_added: Optional[str] = AUTO):
    """The linked per-cell maps (``.scool``) summed into coarser bins, written as a new ``.scool`` and linked.

    Single-cell maps are kept at a fine resolution (5-10 kb) to be looked at; an embedding of the cells by their
    maps (:func:`uchrom.emb.embed_contacts`) wants them at about 1 Mb.  The counts of each cell's bins are summed
    into the bin of the new grid (edges at multiples of ``resolution`` and at the chromosome ends) that holds their
    start; raw counts, no balancing (as the per-cell maps).

    Parameters
    ----------
    cd
        ``ChromData`` with the per-cell maps linked (``cd.link_scool``) or embedded.
    contacts
        Key of the linked maps.
    resolution
        Bin size of the new maps (bp), a multiple of the maps' own.
    out
        Where to write the ``.scool`` (it is linked by this path; give one next to the store for a relative link).
    key_added
        Key of the new maps (default ``"<contacts>_<resolution>"``, e.g. ``"per_cell_1mb"``; ``None``: not linked).

    Returns
    -------
    The path of the new ``.scool``.
    """
    import cooler

    resolution = int(resolution)
    record = (cd.uns.get("linked_scool") or {}).get(contacts)
    if record is None:
        raise KeyError(f"no per-cell maps linked under {contacts!r}")
    path = str(cd.linked_scool_path(contacts))
    cells = list(cooler.fileops.list_scool_cells(path))
    first = cooler.Cooler(f"{path}::{cells[0]}")
    if first.binsize and resolution % int(first.binsize):
        raise ValueError(f"resolution {resolution} is not a multiple of the maps' {first.binsize} bp")
    sizes = first.chromsizes
    starts = [np.arange(0, int(n), resolution, dtype=np.int64) for n in sizes]
    coarse = pd.DataFrame({"chrom": np.repeat(sizes.index.to_numpy(), [len(s) for s in starts]),
                           "start": np.concatenate(starts)})
    coarse["end"] = np.minimum(coarse["start"] + resolution, coarse["chrom"].map(sizes).to_numpy())
    offset = dict(zip(sizes.index, np.r_[0, np.cumsum([len(s) for s in starts])[:-1]]))
    fine = first.bins()[["chrom", "start"]][:]
    to_coarse = (fine["chrom"].astype(str).map(offset).to_numpy(np.int64)
                 + fine["start"].to_numpy(np.int64) // resolution)
    maps = {}
    for name in cells:
        px = cooler.Cooler(f"{path}::{name}").pixels()[:]
        b1, b2 = to_coarse[px["bin1_id"].to_numpy()], to_coarse[px["bin2_id"].to_numpy()]
        lo, hi = np.minimum(b1, b2), np.maximum(b1, b2)
        summed = (pd.DataFrame({"bin1_id": lo, "bin2_id": hi, "count": px["count"].to_numpy()})
                  .groupby(["bin1_id", "bin2_id"], sort=True, as_index=False)["count"].sum())
        maps[name.rsplit("/", 1)[-1]] = summed
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    cooler.create_scool(str(out), coarse, maps, ordered=True, symmetric_upper=True,
                        dtypes={"count": np.int32}, mode="w")
    if key_added == AUTO:
        key_added = f"{contacts}_{_resolution_label(resolution)}"
    if key_added is not None:
        src = cd._links_from()                      # next to the store: a relative link, moved with it
        here = not isinstance(src, str) and src is not None and out.resolve().parent == Path(src).resolve().parent
        cd.link_scool(out.name if here else str(out.resolve()), key=key_added, cell_name=record.get("cell_name", "cell_id"),
                      genome_assembly=record.get("genome_assembly"), bin_size=resolution,
                      label=f"{record.get('label') or contacts}, rebinned to {_resolution_label(resolution, ' ')}",
                      rebinned_from=contacts)
    return str(out)


#: pixels thinned per chunk by :func:`thin_map`
THIN_CHUNK = 5_000_000


def thin_map(cd, contacts: Optional[str] = None, *, fraction: Optional[float] = None,
             n_contacts: Optional[int] = None, seed: int = 0, resolution: Optional[int] = None,
             balance: bool = True, out: Union[None, str, os.PathLike] = None,
             key_added: Optional[str] = AUTO, copy: bool = False):
    """A linked contact map at a lower sequencing depth: every contact of the raw counts kept with probability
    ``fraction`` (binomial thinning), written as a ``.cool`` and linked to ``cd``.

    Cell-type pseudo-bulks often hold 1-20 % of the contacts of a bulk map; thinning the bulk map to their
    depth shows what a caller still finds there (e.g. loops are no longer called below ~5 %, while the pileup
    of known loops still scores them).  Thinning keeps the bins and the counting statistics of a shallower
    experiment of the same library (Poisson counts stay Poisson).

    Parameters
    ----------
    cd
        ``ChromData`` with the map linked, or a path (then nothing is linked and the path is returned).
    contacts
        Key of the linked map (``None``: the only one).
    fraction, n_contacts
        The share of the contacts to keep, or their expected number (one of the two).
    seed
        Seed of the random draws (the same seed gives the same map).
    resolution
        The level of an ``.mcool`` (required when it has several).
    balance
        ICE-balance the thinned map (``weight`` column; ``cooler balance`` defaults).
    out
        Where to write it (default: a scratch directory removed at exit).
    key_added
        Key under which the new map is linked (default ``"<contacts>_<percent>pct"``, e.g. ``"bulk_5pct"``;
        ``None``: not linked).
    copy
        ``True``: link it to a copy of ``cd`` and return that.

    Returns
    -------
    The path of the new map (``copy=False``), or the copy of ``cd`` with the map linked.
    """
    import cooler

    if (fraction is None) == (n_contacts is None):
        raise ValueError("thin_map needs exactly one of fraction= and n_contacts=")
    path = map_path(cd, contacts, resolution=resolution)
    clr = _open(path, resolution)
    total = clr.info.get("sum")
    if total is None or n_contacts is not None:
        total = sum(int(c.sum()) for c in _pixel_chunks(clr, "count"))
    p = float(n_contacts) / total if n_contacts is not None else float(fraction)
    if not 0 < p <= 1:
        raise ValueError(f"fraction {p:g} is not in (0, 1] (the map has {total:,} contacts)")
    key = _map_record(cd, contacts).get("key") or Path(path.split("::", 1)[0]).stem
    label = f"{100 * p:.3g}pct"
    if key_added == AUTO:
        key_added = f"{key}_{label}"
    if copy and (key_added is None or not _is_chromdata(cd)):
        raise ValueError("thin_map(copy=True) links the new map to a copy of a ChromData: pass one and a key_added")
    out = Path(out) if out is not None else _scratch_dir() / f"{key_added or f'{key}_{label}'}.cool"
    out.parent.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(seed)

    def chunks():
        for s in range(0, int(clr.info["nnz"]), THIN_CHUNK):
            px = clr.pixels()[s: s + THIN_CHUNK]
            kept = rng.binomial(px["count"].to_numpy(np.int64), p)
            yield px.assign(count=kept)[kept > 0]

    tmp = out.with_name(f".{out.name}.{os.getpid()}.part")
    meta = {"thinned_from": str(clr.uri), "fraction": p, "seed": int(seed),
            "balance": "ICE (cooler balance defaults)" if balance else "none"}
    try:
        cooler.create_cooler(str(tmp), clr.bins()[:][["chrom", "start", "end"]], chunks(), ordered=True,
                             assembly=clr.info.get("genome-assembly"), metadata=meta)
        if balance:
            _balance_cool(tmp)
        os.replace(tmp, out)
    finally:
        if tmp.exists():
            tmp.unlink()
    if not _is_chromdata(cd) or key_added is None:
        return str(out)
    target = cd.copy() if copy else cd
    record = _map_record(cd, contacts)
    target.link_cool(str(out.resolve()), key=key_added,
                     label=f"{record.get('label') or key}, thinned to {100 * p:.3g} %"
                           + (" (ICE-balanced)" if balance else " (raw)"),
                     genome_assembly=record.get("genome_assembly") or clr.info.get("genome-assembly"),
                     bin_size=clr.binsize, thinned_from=key, fraction=p, seed=int(seed), balanced=bool(balance))
    return target if copy else str(out)


def _pixel_chunks(clr, column: str):
    for s in range(0, int(clr.info["nnz"]), THIN_CHUNK):
        yield clr.pixels()[s: s + THIN_CHUNK][column].to_numpy()


def observed_over_expected(matrix, *, positions=None) -> np.ndarray:
    """Every entry of a contact (or distance) matrix divided by the mean at its genomic separation.

    The expected value of a separation is the mean of its positive, finite entries; entries that are not
    positive (or NaN) and the diagonal are NaN in the result.

    Parameters
    ----------
    matrix
        Square, symmetric (n, n).
    positions
        Genomic position of every row (e.g. bin starts).  Default: the rows are equally spaced, so the
        separation is the diagonal; with gaps (bins left out), entries are grouped by their separation
        ``|positions[i] - positions[j]|`` instead.

    Returns
    -------
    ndarray (n, n), symmetric.
    """
    A = np.asarray(matrix, dtype=np.float64)
    n = len(A)
    if A.shape != (n, n):
        raise ValueError(f"a square matrix, not {A.shape}")
    out = np.full((n, n), np.nan)
    pos = None if positions is None else np.asarray(positions, dtype=np.float64)
    if pos is not None and len(pos) != n:
        raise ValueError(f"{len(pos)} positions for {n} rows")
    steps = np.diff(pos) if pos is not None else None
    if pos is None or n < 3 or np.all(steps == steps[0]):
        for k in range(1, n):                       # equally spaced: a diagonal is a separation
            i = np.arange(n - k)
            v = A[i, i + k]
            ok = v > 0
            if ok.any():
                out[i, i + k] = out[i + k, i] = np.where(ok, v / v[ok].mean(), np.nan)
        return out
    iu, ju = np.triu_indices(n, 1)
    v = A[iu, ju]
    ok = v > 0
    sep = np.abs(pos[ju] - pos[iu])
    keys, inv = np.unique(sep, return_inverse=True)
    total = np.bincount(inv, weights=np.where(ok, v, 0.0), minlength=len(keys))
    count = np.bincount(inv, weights=ok.astype(np.float64), minlength=len(keys))
    with np.errstate(invalid="ignore", divide="ignore"):
        expected = total / count
        oe = np.where(ok, v / expected[inv], np.nan)
    out[iu, ju] = oe
    out[ju, iu] = oe
    return out
