"""Contact maps embedded in a ``.chromdata.zarr`` store (additive part of format 2.3).

A linked ``.scool`` / ``.mcool`` stays outside the store; for an atlas on object storage the maps
can instead be *embedded*: ``embedded/contacts/<name>/`` holds the pixels as Zarr arrays laid out
for range reads (partitioned by chromosome like the coordinates; sharded, so one S3 object holds
many small chunks and a read fetches only the chunks it needs).  Stores without the group, and
older readers, are unaffected.  Layout (``spec.md``, "Embedded contacts")::

    embedded/contacts/<name>/        attrs: uchrom_contacts = {key, kind, label, source, resolutions, ...}
    ├── cells                        string array, per_cell only
    └── r<resolution>/               one per resolution (per_cell: one)
        ├── bins/{chrom,start,end[,weight]}    chrom = code into attrs.chroms
        ├── cis/<chrom>/pix          (3, n) bin1, bin2 (chromosome-local), count; upper triangle
        ├── cis/<chrom>/cell_offset  per_cell: (n_cells + 1) pixel offsets of each cell (sorted by cell, bin1, bin2)
        ├── cis/<chrom>/bin1_offset  bulk: (n_bins_chrom + 1) offsets of each bin1 row
        └── trans/{pix, cell_offset | bin1_offset}   bin ids are genome-wide; bulk: coarse resolutions only

``kind`` is ``per_cell`` (from a ``.scool``) or ``bulk`` (from a ``.mcool`` / ``.cool``).
"""

from __future__ import annotations

import os
import re
import shutil
import tempfile
import warnings
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Sequence, Tuple, Union

import numpy as np

PathLike = Union[str, Path]

GROUP = "embedded/contacts"
ANNDATA = "embedded/anndata"
CHUNK = 1 << 14    # pixels per chunk (the unit of a range read)
SHARD = 1 << 22    # pixels per shard (one object on S3)
ZSTD_LEVEL = 9
#: bulk maps keep trans contacts only at resolutions of at least this many bp
TRANS_MIN_RESOLUTION = 250_000
_SAFE = re.compile(r"[^A-Za-z0-9._+-]")


def safe_name(key: str) -> str:
    return _SAFE.sub("_", str(key))[:120] or "default"


def _zarr():
    import zarr

    return zarr


def as_store(store):
    """A URL becomes a read-only fsspec store (see :mod:`uchrom.core.remote`); anything else is kept."""
    from .remote import is_url, zarr_store

    return zarr_store(str(store).rstrip("/")) if is_url(store) else store


def _uint(maxval: int):
    return np.uint8 if maxval < 2**8 else np.uint16 if maxval < 2**16 else np.uint32


def _pix_array(group, name: str, arr: np.ndarray, dtype) -> None:
    """Pixels as a ``(3, n)`` array (bin1, bin2, count rows), chunked ``(3, CHUNK)`` and sharded: each
    column is contiguous inside a chunk, which compresses ~40 % better than interleaved ``(n, 3)``."""
    zarr = _zarr()
    n = len(arr)
    ch = max(1, min(CHUNK, n))
    sh = max(ch, min(SHARD, -(-n // ch) * ch))
    z = group.create_array(name, shape=(3, n), chunks=(3, ch), shards=(3, sh), dtype=dtype,
                           compressors=zarr.codecs.ZstdCodec(level=ZSTD_LEVEL))
    if n:
        z[:] = np.asarray(arr).T.astype(dtype)


def _small(group, name: str, arr: np.ndarray) -> None:
    z = group.create_array(name, shape=arr.shape, chunks=(max(1, min(len(arr), 1 << 20)),), dtype=arr.dtype)
    if len(arr):
        z[:] = arr


def _store_group(store_path: PathLike):
    zarr = _zarr()
    root = zarr.open_group(str(store_path), mode="r+")
    if "uchrom" not in root.attrs:
        raise ValueError(f"{store_path}: not a ChromData store")
    return root


def _check_uniform(bins_start: np.ndarray, bins_chrom: np.ndarray, binsize: int) -> None:
    for c in np.unique(bins_chrom):
        s = bins_start[bins_chrom == c]
        if not np.array_equal(s, np.arange(len(s), dtype=np.int64) * binsize):
            raise ValueError("embedding needs uniform bins starting at 0 on every chromosome")


def _begin(store_path: PathLike, key: str, overwrite: bool, section: str = GROUP):
    """(final dir, temp group dir) of an embedded map; the temp dir is renamed on success."""
    root_dir = Path(store_path)
    final = root_dir / section / safe_name(key)
    if final.exists() and not overwrite:
        raise FileExistsError(f"{key!r} is already embedded in {store_path} (overwrite=True replaces it)")
    root = _store_group(store_path)
    root.require_group(section)
    tmp = Path(tempfile.mkdtemp(prefix=final.name + ".partial-", dir=final.parent))
    return final, tmp


def _commit(final: Path, tmp: Path, consolidate: bool = True) -> None:
    zarr = _zarr()
    if final.exists():
        shutil.rmtree(final)
    os.replace(tmp, final)
    store = str(final.parents[2])
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")   # "consolidated metadata is not part of the v3 spec"
        if consolidate:
            zarr.consolidate_metadata(store, path=f"{GROUP}/{final.name}")
    consolidate_sections(store)


def consolidate_sections(store_path: PathLike) -> None:
    """Consolidate the metadata of ``embedded/contacts`` and ``embedded/anndata`` (all children in
    one document): a remote reader lists the embedded objects without listing the bucket."""
    zarr = _zarr()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        for section in (GROUP, ANNDATA):
            if (Path(store_path) / section).is_dir():
                zarr.consolidate_metadata(str(store_path), path=section)


# ======================================================================
# per-cell maps (.scool)
# ======================================================================

def embed_scool(store_path: PathLike, key: str, scool: PathLike, *, label: Optional[str] = None,
                overwrite: bool = False, cells: Optional[Sequence[str]] = None) -> Dict[str, Any]:
    """Embed the per-cell maps of a ``.scool`` into the store; returns a summary.

    ``cells``: embed only these cell names (default all).  Memory stays at one block of cells plus
    one chromosome partition: pixels are staged in temporary files per partition."""
    import h5py

    zarr = _zarr()
    final, tmp = _begin(store_path, key, overwrite)
    stage = None
    try:
        with h5py.File(scool, "r") as f:
            names = list(f["cells"]) if cells is None else [c for c in cells if c in f["cells"]]
            chrom = np.asarray(f["bins/chrom"][:]).astype(np.int64)
            start = np.asarray(f["bins/start"][:]).astype(np.int64)
            end = np.asarray(f["bins/end"][:]).astype(np.int64)
            chroms = [str(c) for c in np.asarray(f["chroms/name"][:]).astype(str)]
            binsize = int(np.median(end - start))
            _check_uniform(start, chrom, binsize)
            first = np.array([int(np.flatnonzero(chrom == c)[0]) if (chrom == c).any() else 0
                              for c in range(len(chroms))], np.int64)
            n_c, n_cells = len(chroms), len(names)
            nbins = len(chrom)
            counts = np.zeros((n_c + 1, n_cells), np.int64)       # last row: trans
            stage = Path(tempfile.mkdtemp(prefix=final.name + ".partial-stage-", dir=final.parent))
            fh = [open(stage / f"{p}.bin", "wb") for p in range(n_c + 1)]
            cmax = 0
            for i, nm in enumerate(names):
                px = f["cells"][nm]["pixels"]
                a = px["bin1_id"][:].astype(np.int64)
                b = px["bin2_id"][:].astype(np.int64)
                k = px["count"][:].astype(np.int64)
                if len(k):
                    cmax = max(cmax, int(k.max()))
                ca, cb = chrom[a], chrom[b]
                same = ca == cb
                for c in np.unique(ca[same]):
                    m = same & (ca == c)
                    fh[c].write(np.column_stack([a[m] - first[c], b[m] - first[c], k[m]]).astype(np.uint32).tobytes())
                    counts[c, i] = int(m.sum())
                m = ~same
                if m.any():
                    fh[n_c].write(np.column_stack([a[m], b[m], k[m]]).astype(np.uint32).tobytes())
                    counts[n_c, i] = int(m.sum())
            for h in fh:
                h.close()
        dt = np.dtype(np.uint16 if max(cmax, nbins) < 2**16 else np.uint32)
        root = zarr.open_group(str(tmp), mode="w", zarr_format=3)
        g = root.create_group(f"r{binsize}")
        bg = g.create_group("bins")
        _small(bg, "chrom", chrom.astype(np.uint8 if n_c < 256 else np.uint16))
        _small(bg, "start", start.astype(np.int64 if start.max() >= 2**31 else np.int32))
        _small(bg, "end", end.astype(np.int64 if end.max() >= 2**31 else np.int32))
        root.create_array("cells", data=np.asarray(names, dtype=str))
        npix = {}
        for p in range(n_c + 1):
            data = np.fromfile(stage / f"{p}.bin", dtype=np.uint32).reshape(-1, 3)
            os.remove(stage / f"{p}.bin")
            if len(data) == 0:
                continue
            part = g.create_group("trans" if p == n_c else f"cis/{chroms[p]}")
            _pix_array(part, "pix", data, dt)
            off = np.zeros(n_cells + 1, np.int64)
            off[1:] = np.cumsum(counts[p])
            _small(part, "cell_offset", off)
            npix["trans" if p == n_c else chroms[p]] = int(len(data))
        meta = {"key": key, "kind": "per_cell", "label": label or key, "source": Path(scool).name,
                "resolutions": [binsize], "chroms": chroms, "chrom_first_bin": {str(binsize): first.tolist()},
                "n_cells": n_cells, "n_pixels": npix, "count_max": cmax}
        root.attrs["uchrom_contacts"] = meta
        _commit(final, tmp)
        return meta
    except BaseException:
        shutil.rmtree(tmp, ignore_errors=True)
        raise
    finally:
        if stage is not None:
            shutil.rmtree(stage, ignore_errors=True)


# ======================================================================
# bulk maps (.mcool / .cool)
# ======================================================================

def _pixels(px, s0: int, s1: int, step: int) -> np.ndarray:
    """Pixel rows ``[s0, s1)`` of a cooler pixel table as an int64 (n, 3) array."""
    blocks = [px[s:min(s1, s + step)][["bin1_id", "bin2_id", "count"]].to_numpy(np.int64)
              for s in range(s0, s1, step)]
    return np.concatenate(blocks) if blocks else np.zeros((0, 3), np.int64)


def embed_cool(store_path: PathLike, key: str, cool: PathLike, *, label: Optional[str] = None,
               overwrite: bool = False, resolutions: Optional[Sequence[int]] = None,
               trans_min_resolution: int = TRANS_MIN_RESOLUTION) -> Dict[str, Any]:
    """Embed a ``.mcool`` (every resolution, or ``resolutions``) or a single-resolution ``.cool``."""
    import cooler

    zarr = _zarr()
    cool = str(cool)
    uris = cooler.fileops.list_coolers(cool)
    if any("/resolutions/" in u for u in uris):
        res_uri = {int(u.rsplit("/", 1)[-1]): f"{cool}::{u}" for u in uris if "/resolutions/" in u}
    else:
        res_uri = {int(cooler.Cooler(cool).binsize): cool}
    if resolutions is not None:
        res_uri = {r: u for r, u in res_uri.items() if r in set(int(x) for x in resolutions)}
    if not res_uri:
        raise ValueError("no resolution to embed")
    final, tmp = _begin(store_path, key, overwrite)
    try:
        root = zarr.open_group(str(tmp), mode="w", zarr_format=3)
        chroms, first, weights, npix = None, {}, False, {}
        for res in sorted(res_uri):
            clr = cooler.Cooler(res_uri[res])
            bins = clr.bins()[:]
            cnames = [str(c) for c in clr.chromnames]
            chrom = np.asarray(bins["chrom"].cat.codes if hasattr(bins["chrom"], "cat") else
                               bins["chrom"].map({c: i for i, c in enumerate(cnames)}), np.int64)
            start = bins["start"].to_numpy(np.int64)
            end = bins["end"].to_numpy(np.int64)
            _check_uniform(start, chrom, res)
            fb = np.array([int(np.flatnonzero(chrom == c)[0]) for c in range(len(cnames))], np.int64)
            chroms = cnames
            first[str(res)] = fb.tolist()
            g = root.create_group(f"r{res}")
            bg = g.create_group("bins")
            _small(bg, "chrom", chrom.astype(np.uint8 if len(cnames) < 256 else np.uint16))
            _small(bg, "start", start.astype(np.int64 if start.max() >= 2**31 else np.int32))
            _small(bg, "end", end.astype(np.int64 if end.max() >= 2**31 else np.int32))
            if "weight" in bins.columns:
                _small(bg, "weight", bins["weight"].to_numpy(np.float64))
                weights = True
            nb = len(bins)
            px = clr.pixels()
            n_pix = len(px)
            step = 20_000_000
            with clr.open("r") as h5:
                bin1_off = np.asarray(h5["indexes/bin1_offset"][:], np.int64)
            for c, cname in enumerate(cnames):
                lo, hi = clr.extent(cname)
                if hi <= lo:
                    continue
                d = _pixels(px, int(bin1_off[lo]), int(bin1_off[hi]), step)
                cpart = d[d[:, 1] < hi]
                cpart = np.column_stack([cpart[:, 0] - lo, cpart[:, 1] - lo, cpart[:, 2]])
                off = np.zeros(hi - lo + 1, np.int64)
                np.add.at(off, cpart[:, 0] + 1, 1)
                off = np.cumsum(off)
                part = g.create_group(f"cis/{cname}")
                cm = int(cpart[:, 2].max()) if len(cpart) else 0
                _pix_array(part, "pix", cpart, np.uint32 if cm >= 2**16 else np.uint16)
                _small(part, "bin1_offset", off)
                npix[f"r{res}/{cname}"] = int(len(cpart))
            if res >= trans_min_resolution:
                tr = _pixels(px, 0, n_pix, step)
                tr = tr[chrom[tr[:, 0]] != chrom[tr[:, 1]]]
                off = np.zeros(nb + 1, np.int64)
                np.add.at(off, tr[:, 0] + 1, 1)
                off = np.cumsum(off)
                part = g.create_group("trans")
                cm = int(tr[:, 2].max()) if len(tr) else 0
                _pix_array(part, "pix", tr, np.uint32 if (cm >= 2**16 or nb >= 2**16) else np.uint16)
                _small(part, "bin1_offset", off)
                npix[f"r{res}/trans"] = int(len(tr))
        meta = {"key": key, "kind": "bulk", "label": label or key, "source": Path(cool.split("::")[0]).name,
                "resolutions": sorted(res_uri), "chroms": chroms, "chrom_first_bin": first,
                "has_weights": weights, "trans_min_resolution": int(trans_min_resolution), "n_pixels": npix}
        root.attrs["uchrom_contacts"] = meta
        _commit(final, tmp)
        return meta
    except BaseException:
        shutil.rmtree(tmp, ignore_errors=True)
        raise


# ======================================================================
# reading
# ======================================================================

class EmbeddedContacts:
    """Read access to one embedded map (``store`` may be a path, URL or zarr store)."""

    def __init__(self, store, name: str):
        zarr = _zarr()
        self.name = name
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            self.g = zarr.open_group(as_store(store), path=f"{GROUP}/{name}", mode="r", use_consolidated=True)
        self.meta = dict(self.g.attrs["uchrom_contacts"])
        self.kind: str = self.meta["kind"]
        self.key: str = self.meta["key"]
        self.label: str = self.meta.get("label", self.key)
        self.resolutions: List[int] = [int(r) for r in self.meta["resolutions"]]
        self.chroms: List[str] = list(self.meta["chroms"])
        self._cache: Dict[Any, Any] = {}

    # -- tables -------------------------------------------------------

    def bins(self, resolution: Optional[int] = None):
        import pandas as pd

        r = self._res(resolution)
        if ("bins", r) not in self._cache:
            b = self.g[f"r{r}/bins"]
            df = pd.DataFrame({"chrom": np.asarray(self.chroms, dtype=object)[b["chrom"][:].astype(np.int64)],
                               "start": b["start"][:].astype(np.int64), "end": b["end"][:].astype(np.int64)})
            if "weight" in b:
                df["weight"] = b["weight"][:].astype(np.float64)
            self._cache[("bins", r)] = df
        return self._cache[("bins", r)]

    def chromsizes(self, resolution: Optional[int] = None) -> Dict[str, int]:
        b = self.bins(resolution)
        return {str(c): int(e) for c, e in b.groupby("chrom", sort=False)["end"].max().items()}

    @property
    def cells(self) -> List[str]:
        if "cells" not in self._cache:
            self._cache["cells"] = [str(c) for c in self.g["cells"][:]] if self.kind == "per_cell" else []
        return self._cache["cells"]

    def _res(self, resolution: Optional[int]) -> int:
        r = int(resolution) if resolution else self.resolutions[0]
        if r not in self.resolutions:
            raise ValueError(f"resolution must be one of {self.resolutions}")
        return r

    def first_bin(self, chrom: str, resolution: Optional[int] = None) -> int:
        """Genome-wide index of the first bin of ``chrom`` at a resolution."""
        return int(self.meta["chrom_first_bin"][str(self._res(resolution))][self.chroms.index(chrom)])

    def _offsets(self, r: int, part: str, name: str) -> np.ndarray:
        k = (r, part, name)
        if k not in self._cache:
            self._cache[k] = self.g[f"r{r}/{part}/{name}"][:].astype(np.int64)
        return self._cache[k]

    def has_trans(self, resolution: Optional[int] = None) -> bool:
        return "trans" in self.g[f"r{self._res(resolution)}"]

    # -- pixels -------------------------------------------------------

    def cell_pixels(self, part: str, cell_idx: Sequence[int], resolution: Optional[int] = None) -> np.ndarray:
        """Pixels (n, 3) of the cells ``cell_idx`` in a partition (``cis/<chrom>`` or ``trans``);
        neighbouring cells are read as one range."""
        r = self._res(resolution)
        if f"{part}" not in self.g[f"r{r}"]:
            return np.zeros((0, 3), np.int64)
        off = self._offsets(r, part, "cell_offset")
        pix = self.g[f"r{r}/{part}/pix"]
        idx = np.unique(np.asarray(cell_idx, np.int64))
        lo, hi = off[idx], off[idx + 1]
        keep = hi > lo
        lo, hi = lo[keep], hi[keep]
        if len(lo) == 0:
            return np.zeros((0, 3), np.int64)
        # coalesce ranges whose gap is smaller than a chunk (one read instead of many)
        out, i = [], 0
        while i < len(lo):
            j = i
            while j + 1 < len(lo) and lo[j + 1] - hi[j] <= CHUNK:
                j += 1
            block = pix[:, int(lo[i]):int(hi[j])].T.astype(np.int64)
            if j == i:
                out.append(block)
            else:
                out.extend(block[int(l - lo[i]):int(h - lo[i])] for l, h in zip(lo[i:j + 1], hi[i:j + 1]))
            i = j + 1
        return np.concatenate(out)

    def region_pixels(self, chrom: str, lo_bin: int, hi_bin: int, resolution: Optional[int] = None) -> np.ndarray:
        """Bulk: cis pixels whose bin1 lies in chromosome-local bins ``[lo_bin, hi_bin)``."""
        r = self._res(resolution)
        part = f"cis/{chrom}"
        off = self._offsets(r, part, "bin1_offset")
        s0, s1 = int(off[lo_bin]), int(off[hi_bin])
        return self.g[f"r{r}/{part}/pix"][:, s0:s1].T.astype(np.int64)

    def iter_pixels(self, resolution: Optional[int] = None, cell_idx: Optional[Sequence[int]] = None,
                    trans: bool = True) -> Iterator[Tuple[np.ndarray, np.ndarray, np.ndarray]]:
        """All pixels as genome-wide ``(bin1, bin2, count)`` blocks (per_cell: of ``cell_idx``)."""
        r = self._res(resolution)
        for c in self.chroms:
            part = f"cis/{c}"
            if part not in self.g[f"r{r}"]:
                continue
            if self.kind == "per_cell":
                d = self.cell_pixels(part, cell_idx if cell_idx is not None else range(len(self.cells)), r)
            else:
                d = self.g[f"r{r}/{part}/pix"][:].T.astype(np.int64)
            f0 = self.first_bin(c, r)
            if len(d):
                yield d[:, 0] + f0, d[:, 1] + f0, d[:, 2]
        if trans and "trans" in self.g[f"r{r}"]:
            if self.kind == "per_cell":
                d = self.cell_pixels("trans", cell_idx if cell_idx is not None else range(len(self.cells)), r)
            else:
                d = self.g[f"r{r}/trans/pix"][:].T.astype(np.int64)
            if len(d):
                yield d[:, 0], d[:, 1], d[:, 2]


def list_embedded(store) -> Dict[str, str]:
    """``{key: group name}`` of the embedded contact maps of a store ({} if none)."""
    zarr = _zarr()
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            grp = zarr.open_group(as_store(store), path=GROUP, mode="r", use_consolidated=True)
    except (FileNotFoundError, KeyError, zarr.errors.GroupNotFoundError if hasattr(zarr.errors, "GroupNotFoundError") else KeyError):
        return {}
    out = {}
    for name, sub in grp.groups():
        if ".partial-" in name:
            continue
        meta = sub.attrs.get("uchrom_contacts")
        if meta:
            out[str(meta["key"])] = name
    return out


# ======================================================================
# AnnData (cell x gene / cell x bin matrices)
# ======================================================================

def embed_anndata(store_path: PathLike, key: str, h5ad: PathLike, *, family: str = "linked_anndata",
                  label: Optional[str] = None, overwrite: bool = False,
                  chunks: Optional[Tuple[int, int]] = None) -> Dict[str, Any]:
    """Embed an ``.h5ad`` as an AnnData Zarr group (``embedded/anndata/<key>``).

    ``family`` is the ``uns`` record family it replaces (``linked_anndata`` or ``linked_bin_matrices``).
    A dense ``X`` is chunked ``chunks`` (default ``(1024, 256)``: a chromosome of every cell is a few
    chunks); a sparse ``X`` keeps anndata's layout."""
    import anndata as ad

    zarr = _zarr()
    final, tmp = _begin(store_path, key, overwrite, ANNDATA)
    try:
        adata = ad.read_h5ad(h5ad)
        dense = not hasattr(adata.X, "indptr")
        shutil.rmtree(tmp)
        kw = {"chunks": chunks or (min(adata.n_obs, 1024), min(adata.n_vars, 256))} if dense else {}
        adata.write_zarr(str(tmp), **kw)
        meta = {"key": key, "family": family, "label": label or key, "source": Path(h5ad).name,
                "n_obs": int(adata.n_obs), "n_vars": int(adata.n_vars), "dense": bool(dense)}
        g = zarr.open_group(str(tmp), mode="r+")
        g.attrs["uchrom_anndata"] = meta
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            zarr.consolidate_metadata(str(tmp))
        _commit(final, tmp, consolidate=False)
        return meta
    except BaseException:
        shutil.rmtree(tmp, ignore_errors=True)
        raise


def list_embedded_anndata(store, family: Optional[str] = None) -> Dict[str, str]:
    """``{key: group name}`` of the embedded AnnData groups (of one ``family``)."""
    zarr = _zarr()
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            grp = zarr.open_group(as_store(store), path=ANNDATA, mode="r", use_consolidated=True)
    except Exception:
        return {}
    out = {}
    for name, sub in grp.groups():
        meta = sub.attrs.get("uchrom_anndata")
        if meta and (family is None or meta.get("family") == family) and ".partial-" not in name:
            out[str(meta["key"])] = name
    return out


def read_embedded_anndata(store, name: str):
    """The embedded AnnData as an in-memory ``AnnData``."""
    import anndata as ad

    zarr = _zarr()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        grp = zarr.open_group(as_store(store), path=f"{ANNDATA}/{name}", mode="r")
        return ad.read_zarr(grp)


# ======================================================================
# whole store
# ======================================================================

def _records(uns: Dict[str, Any], family: str) -> Dict[str, dict]:
    raw = (uns or {}).get(family)
    if not isinstance(raw, dict):
        return {}
    if "path" in raw:
        return {"default": raw}
    return {str(k): v for k, v in raw.items() if isinstance(v, dict) and v.get("path")}


def embed_links(store_path: PathLike, *, overwrite: bool = False, keys: Optional[Sequence[str]] = None,
                trans_min_resolution: int = TRANS_MIN_RESOLUTION, verbose: bool = True) -> Dict[str, Any]:
    """Embed every linked ``.cool`` / ``.mcool`` / ``.scool`` / ``.h5ad`` of a store (records of
    ``linked_cool``, ``linked_scool``, ``linked_bin_matrices``, ``linked_anndata``) into the store.

    The link records stay, so the store still reads on a machine that has the files; a reader that
    finds an embedded copy uses it.  Returns ``{key: summary}``."""
    from .cdata import ChromData

    cd = ChromData.read(str(store_path), backed=True)
    done: Dict[str, Any] = {}
    todo = [(fam, k, r) for fam in ("linked_cool", "linked_scool", "linked_bin_matrices", "linked_anndata")
            for k, r in _records(cd.uns, fam).items() if keys is None or k in set(keys)]
    for fam, key, rec in todo:
        path = cd.resolve_link_path(rec["path"])
        if not path.exists():
            if verbose:
                print(f"[embed] {fam}/{key}: {path} not found, skipped")
            continue
        if verbose:
            print(f"[embed] {fam}/{key}: {path.name}", flush=True)
        label = rec.get("label")
        if fam == "linked_scool":
            done[key] = embed_scool(store_path, key, path, label=label, overwrite=overwrite)
        elif fam == "linked_cool":
            done[key] = embed_cool(store_path, key, path, label=label, overwrite=overwrite,
                                   trans_min_resolution=trans_min_resolution)
        else:
            done[key] = embed_anndata(store_path, key, path, family=fam, label=label, overwrite=overwrite)
    consolidate_sections(store_path)
    return done


if __name__ == "__main__":     # python -m uchrom.core.embedded STORE [--overwrite] [--keys a b ...] [--reconsolidate]
    import argparse

    ap = argparse.ArgumentParser(description="Embed the linked contact maps / h5ad files into a .chromdata.zarr store")
    ap.add_argument("store")
    ap.add_argument("--overwrite", action="store_true")
    ap.add_argument("--keys", nargs="*")
    ap.add_argument("--trans-min-resolution", type=int, default=TRANS_MIN_RESOLUTION)
    ap.add_argument("--reconsolidate", action="store_true", help="only rebuild the metadata index of the embedded groups")
    a = ap.parse_args()
    if a.reconsolidate:
        consolidate_sections(a.store)
        raise SystemExit(0)
    embed_links(a.store, overwrite=a.overwrite, keys=a.keys, trans_min_resolution=a.trans_min_resolution)
