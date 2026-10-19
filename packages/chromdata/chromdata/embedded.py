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

import functools

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
#: pixels per block when a group of cells (or a big map) is summed: bounds the memory of a request
BLOCK_PIXELS = 1_000_000
#: bulk maps keep trans contacts only at resolutions of at least this many bp
TRANS_MIN_RESOLUTION = 250_000
_SAFE = re.compile(r"[^A-Za-z0-9._+-]")


def safe_name(key: str) -> str:
    return _SAFE.sub("_", str(key))[:120] or "default"


def _zarr():
    import zarr

    return zarr


def as_store(store):
    """A URL becomes a read-only fsspec store (see :mod:`chromdata.remote`), a ``.cdz`` file a read-only zip
    store (the same tree in one zip); anything else is kept."""
    from .remote import is_url, zarr_store

    if is_url(store):
        return zarr_store(str(store).rstrip("/"))
    if isinstance(store, (str, Path)) and str(store).lower().endswith(".cdz") and Path(store).is_file():
        p = Path(store).resolve()
        return _zip_store(str(p), p.stat().st_mtime_ns)
    return store


@functools.lru_cache(maxsize=16)
def _zip_store(path: str, mtime_ns: int):
    """One read-only ZipStore per ``.cdz`` (and version of it): the zip's directory is read once."""
    zarr = _zarr()
    return zarr.storage.ZipStore(path, mode="r")


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
    # writes must not trust the consolidated metadata (it predates the groups added here)
    root = zarr.open_group(str(store_path), mode="r+", zarr_format=3, use_consolidated=False)
    if "uchrom" not in root.attrs:
        raise ValueError(f"{store_path}: not a ChromData store")
    return root


def _chromsizes(chrom: np.ndarray, end: np.ndarray, names: Sequence[str]) -> Dict[str, int]:
    """Chromosome lengths (end of the last bin) from a bin table: kept in the attrs so that describing a map
    reads no array."""
    return {str(names[c]): int(end[chrom == c].max()) for c in np.unique(chrom)}


SUM = "sum"    # pixels of the map summed over every cell, per partition: the "all spots" view without reading each cell


def _sum_pixels(data: np.ndarray, width: int) -> np.ndarray:
    """(n, 3) pixels (bin1, bin2, count) summed over duplicates of (bin1, bin2): the total over all cells."""
    key = data[:, 0].astype(np.int64) * width + data[:, 1].astype(np.int64)
    uk, inv = np.unique(key, return_inverse=True)
    tot = np.bincount(inv, weights=data[:, 2].astype(np.float64), minlength=len(uk))
    return np.column_stack([uk // width, uk % width, tot]).astype(np.int64)


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


def upgrade_store(store_path: PathLike) -> Dict[str, Any]:
    """Make an already embedded store cheap to open over HTTP (no data is rewritten): put the chromosome lengths
    into the attrs of every contact map that lacks them, then rebuild the consolidated metadata of the embedded
    sections and of the store root (one request instead of one per array).  Returns what changed."""
    zarr = _zarr()
    done = {"chromsizes": [], "root_consolidated": False}
    for key, name in list_embedded(str(store_path)).items():
        e = EmbeddedContacts(str(store_path), name)
        if e.meta.get("chromsizes"):
            continue
        meta = dict(e.meta)
        meta["chromsizes"] = e.chromsizes()
        g = zarr.open_group(str(store_path), path=f"{GROUP}/{name}", mode="r+", zarr_format=3, use_consolidated=False)
        g.attrs["uchrom_contacts"] = meta
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            zarr.consolidate_metadata(str(store_path), path=f"{GROUP}/{name}")
        done["chromsizes"].append(key)
    done["sum"] = []
    for key, name in list_embedded(str(store_path)).items():
        e = EmbeddedContacts(str(store_path), name)
        if e.kind == "per_cell" and not e.has_sum():
            add_sums(store_path, name)
            done["sum"].append(key)
    done["var"] = []
    for key, (g, meta) in open_anndata_groups(str(store_path), "linked_bin_matrices").items():
        if g.attrs.get("uchrom_var"):
            continue
        v = bin_matrix_var(g)
        gw = zarr.open_group(str(store_path), path=f"{ANNDATA}/{safe_name(key)}", mode="r+", zarr_format=3, use_consolidated=False)
        gw.attrs["uchrom_var"] = {"bin_id": v["bin_id"].astype(int).tolist(),
                                  "resolution": (v["resolution"].astype(int).tolist() if "resolution" in v else [0] * len(v))}
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            zarr.consolidate_metadata(str(store_path), path=f"{ANNDATA}/{safe_name(key)}")
        done["var"].append(key)
    consolidate_sections(store_path)
    consolidate_root(store_path)
    done["root_consolidated"] = True
    return done


def add_sums(store_path: PathLike, name: str, *, max_dense: int = 20_000) -> None:
    """Add the all-cells sums to a per-cell map embedded without them: one pass over every cell's pixels in blocks
    (memory = one dense matrix per partition), no data is rewritten."""
    zarr = _zarr()
    e = EmbeddedContacts(str(store_path), name)
    r = e.resolutions[0]
    idx = range(len(e.cells))
    nb = len(e.bins(r))
    gw = zarr.open_group(str(store_path), path=f"{GROUP}/{name}/r{r}", mode="r+", zarr_format=3, use_consolidated=False)
    parts = [(f"cis/{c}", int(e.chromsizes()[c] // r) + 1) for c in e.chroms if f"cis/{c}" in e.g[f"r{r}"]]
    parts.append(("trans", nb))
    for part, width in parts:
        if part not in e.g[f"r{r}"]:
            continue
        if width <= max_dense:                                   # dense accumulator, block by block
            acc = np.zeros(width * width, np.float64)
            for d in e.cell_pixel_blocks(part, idx, r):
                acc += np.bincount(d[:, 0] * width + d[:, 1], weights=d[:, 2], minlength=width * width)
            nz = np.flatnonzero(acc)
            data = np.column_stack([nz // width, nz % width, acc[nz]]).astype(np.int64)
        else:                                                    # too wide: sum the blocks' partial sums
            data = np.zeros((0, 3), np.int64)
            for d in e.cell_pixel_blocks(part, idx, r):
                data = _sum_pixels(np.concatenate([data, _sum_pixels(d, width)]), width)
        _pix_array(gw[part], SUM, data, np.uint32)
    meta = dict(e.meta)
    meta["has_sum"] = True
    gm = zarr.open_group(str(store_path), path=f"{GROUP}/{name}", mode="r+", zarr_format=3, use_consolidated=False)
    gm.attrs["uchrom_contacts"] = meta
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        zarr.consolidate_metadata(str(store_path), path=f"{GROUP}/{name}")


def consolidate_root(store_path: PathLike) -> None:
    """Consolidate the metadata of the whole store (all arrays in the root ``zarr.json``): opening a store over
    HTTP then needs one request for all array metadata instead of one per array."""
    zarr = _zarr()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        zarr.consolidate_metadata(str(store_path))


def consolidate_sections(store_path: PathLike) -> None:
    """Consolidate the metadata of ``embedded/contacts`` and ``embedded/anndata`` (all children in
    one document): a remote reader lists the embedded objects without listing the bucket."""
    zarr = _zarr()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        for section in (GROUP, ANNDATA, IMAGES):
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
            _pix_array(part, SUM, _sum_pixels(data, nbins), np.uint32)     # every cell added: the "all spots" map
            off = np.zeros(n_cells + 1, np.int64)
            off[1:] = np.cumsum(counts[p])
            _small(part, "cell_offset", off)
            npix["trans" if p == n_c else chroms[p]] = int(len(data))
        meta = {"key": key, "kind": "per_cell", "label": label or key, "source": Path(scool).name,
                "resolutions": [binsize], "chroms": chroms, "chrom_first_bin": {str(binsize): first.tolist()},
                "n_cells": n_cells, "n_pixels": npix, "count_max": cmax,
                "chromsizes": _chromsizes(chrom, end, chroms), "has_sum": True}
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
        chroms, first, weights, npix, chromsizes = None, {}, False, {}, None
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
            if chromsizes is None:
                chromsizes = _chromsizes(chrom, end, cnames)
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
                "has_weights": weights, "trans_min_resolution": int(trans_min_resolution), "n_pixels": npix,
                "chromsizes": chromsizes}
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

    def __init__(self, store, name: str, group=None):
        zarr = _zarr()
        self.name = name
        if group is not None:        # a child of the consolidated ``embedded/contacts`` group: no request
            self.g = group
        else:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                self.g = zarr.open_group(as_store(store), path=f"{GROUP}/{name}", mode="r", use_consolidated=True, zarr_format=3)
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
        if self.meta.get("chromsizes"):
            return {str(c): int(n) for c, n in self.meta["chromsizes"].items()}
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

    def cell_pixel_blocks(self, part: str, cell_idx: Sequence[int], resolution: Optional[int] = None,
                          max_pixels: int = BLOCK_PIXELS) -> Iterator[np.ndarray]:
        """Pixels (n, 3) of the cells ``cell_idx`` in a partition (``cis/<chrom>`` or ``trans``), in blocks of at
        most about ``max_pixels`` (a bigger cell is a block of its own): memory stays bounded however many cells.
        Neighbouring cells are read as one range."""
        r = self._res(resolution)
        if part not in self.g[f"r{r}"]:
            return
        off = self._offsets(r, part, "cell_offset")
        pix = self.g[f"r{r}/{part}/pix"]
        idx = np.unique(np.asarray(cell_idx, np.int64))
        lo, hi = off[idx], off[idx + 1]
        keep = hi > lo
        lo, hi = lo[keep], hi[keep]
        if len(lo) == 0:
            return
        # batches of cells whose pixels add up to about max_pixels
        cum = np.cumsum(hi - lo)
        start = 0
        while start < len(lo):
            base = cum[start - 1] if start else 0
            end = int(np.searchsorted(cum, base + max_pixels, side="right"))
            end = max(end, start + 1)
            yield self._read_ranges(pix, lo[start:end], hi[start:end])
            start = end

    @staticmethod
    def _read_ranges(pix, lo: np.ndarray, hi: np.ndarray) -> np.ndarray:
        """Rows lo[k]:hi[k] of the pixel array; ranges whose gap is under a chunk are fetched as one read."""
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

    def cell_pixels(self, part: str, cell_idx: Sequence[int], resolution: Optional[int] = None) -> np.ndarray:
        """All pixels (n, 3) of the cells ``cell_idx`` in a partition; for many cells use :meth:`cell_pixel_blocks`."""
        blocks = list(self.cell_pixel_blocks(part, cell_idx, resolution, max_pixels=1 << 62))
        return np.concatenate(blocks) if blocks else np.zeros((0, 3), np.int64)

    def has_sum(self, resolution: Optional[int] = None) -> bool:
        """Whether the map carries the precomputed all-cells sums (a per-cell map embedded recently, or upgraded)."""
        r = self._res(resolution)
        parts = [f"cis/{c}" for c in self.chroms if f"cis/{c}" in self.g[f"r{r}"]]
        return self.kind == "per_cell" and bool(parts) and all(SUM in self.g[f"r{r}/{p}"] for p in parts)

    def sum_pixels(self, part: str, resolution: Optional[int] = None) -> np.ndarray:
        """(n, 3) pixels of a partition summed over every cell (partition-local bin ids for ``cis/``)."""
        r = self._res(resolution)
        if part not in self.g[f"r{r}"]:
            return np.zeros((0, 3), np.int64)
        return self.g[f"r{r}/{part}/{SUM}"][:].T.astype(np.int64)

    def iter_sum_pixels(self, resolution: Optional[int] = None):
        """:meth:`iter_pixels` of all cells at once, from the precomputed sums."""
        r = self._res(resolution)
        for c in self.chroms:
            part = f"cis/{c}"
            if part in self.g[f"r{r}"]:
                d = self.sum_pixels(part, r)
                f0 = self.first_bin(c, r)
                if len(d):
                    yield d[:, 0] + f0, d[:, 1] + f0, d[:, 2]
        if "trans" in self.g[f"r{r}"]:
            d = self.sum_pixels("trans", r)
            if len(d):
                yield d[:, 0], d[:, 1], d[:, 2]

    def region_pixels(self, chrom: str, lo_bin: int, hi_bin: int, resolution: Optional[int] = None) -> np.ndarray:
        """Bulk: cis pixels whose bin1 lies in chromosome-local bins ``[lo_bin, hi_bin)``."""
        r = self._res(resolution)
        part = f"cis/{chrom}"
        off = self._offsets(r, part, "bin1_offset")
        s0, s1 = int(off[lo_bin]), int(off[hi_bin])
        return self.g[f"r{r}/{part}/pix"][:, s0:s1].T.astype(np.int64)

    def iter_pixels(self, resolution: Optional[int] = None, cell_idx: Optional[Sequence[int]] = None,
                    trans: bool = True, max_pixels: int = BLOCK_PIXELS) -> Iterator[Tuple[np.ndarray, np.ndarray, np.ndarray]]:
        """All pixels as genome-wide ``(bin1, bin2, count)`` blocks of about ``max_pixels`` (per_cell: of ``cell_idx``)."""
        r = self._res(resolution)
        cells = cell_idx if cell_idx is not None else range(len(self.cells))
        parts = [(f"cis/{c}", self.first_bin(c, r)) for c in self.chroms if f"cis/{c}" in self.g[f"r{r}"]]
        if trans and "trans" in self.g[f"r{r}"]:
            parts.append(("trans", 0))
        for part, f0 in parts:
            if self.kind == "per_cell":
                blocks = self.cell_pixel_blocks(part, cells, r, max_pixels)
            else:
                arr = self.g[f"r{r}/{part}/pix"]
                blocks = (arr[:, s:s + max_pixels].T.astype(np.int64) for s in range(0, arr.shape[1], max_pixels))
            for d in blocks:
                if len(d):
                    yield d[:, 0] + f0, d[:, 1] + f0, d[:, 2]


def _open_section(store, section: str):
    zarr = _zarr()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return zarr.open_group(as_store(store), path=section, mode="r", use_consolidated=True, zarr_format=3)


def open_all(store) -> Dict[str, "EmbeddedContacts"]:
    """Every embedded contact map of a store, from one request (the consolidated metadata of the section holds
    all the maps); the arrays are read when a map is used."""
    try:
        grp = _open_section(store, GROUP)
    except Exception:
        return {}
    out = {}
    for name, sub in grp.groups():
        if ".partial-" not in name and sub.attrs.get("uchrom_contacts"):
            e = EmbeddedContacts(store, name, group=sub)
            out[e.key] = e
    return out


def open_anndata_groups(store, family: Optional[str] = None) -> Dict[str, Tuple[Any, Dict[str, Any]]]:
    """``{key: (zarr group, attrs)}`` of the embedded AnnData groups (of one ``family``) from one request."""
    try:
        grp = _open_section(store, ANNDATA)
    except Exception:
        return {}
    return {str(sub.attrs["uchrom_anndata"]["key"]): (sub, dict(sub.attrs["uchrom_anndata"]))
            for name, sub in grp.groups()
            if ".partial-" not in name and "uchrom_anndata" in sub.attrs
            and (family is None or sub.attrs["uchrom_anndata"].get("family") == family)}


def bin_matrix_var(group) -> Any:
    """The ``bin_id`` / ``resolution`` columns of an embedded cell x bin matrix: from the attrs (``uchrom_var``)
    when present, else read from the ``var`` table (one request per column)."""
    import pandas as pd

    v = group.attrs.get("uchrom_var")
    if v:
        return pd.DataFrame({"bin_id": np.asarray(v["bin_id"], np.int64), "resolution": np.asarray(v["resolution"], np.int64)})
    import anndata as ad

    return ad.io.read_elem(group["var"])


def list_embedded(store) -> Dict[str, str]:
    """``{key: group name}`` of the embedded contact maps of a store ({} if none)."""
    zarr = _zarr()
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            grp = zarr.open_group(as_store(store), path=GROUP, mode="r", use_consolidated=True, zarr_format=3)
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
        with ad.settings.override(zarr_write_format=3):     # anndata < 0.13 writes Zarr v2 by default
            adata.write_zarr(str(tmp), **kw)
        meta = {"key": key, "family": family, "label": label or key, "source": Path(h5ad).name,
                "n_obs": int(adata.n_obs), "n_vars": int(adata.n_vars), "dense": bool(dense)}
        g = zarr.open_group(str(tmp), mode="r+")
        g.attrs["uchrom_anndata"] = meta
        if "bin_id" in adata.var:      # a cell x bin matrix: its column table in the attrs (read with the metadata)
            g.attrs["uchrom_var"] = {"bin_id": adata.var["bin_id"].astype(int).tolist(),
                                     "resolution": (adata.var["resolution"].astype(int).tolist() if "resolution" in adata.var
                                                    else [0] * adata.n_vars)}
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
            grp = zarr.open_group(as_store(store), path=ANNDATA, mode="r", use_consolidated=True, zarr_format=3)
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
        grp = zarr.open_group(as_store(store), path=f"{ANNDATA}/{name}", mode="r", zarr_format=3)
        return ad.read_zarr(grp)


# ======================================================================
# images (section / FOV pictures of ``uns['linked_images']``)
# ======================================================================

IMAGES = "embedded/images"
_MEDIA = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".tif": "image/tiff",
          ".tiff": "image/tiff", ".webp": "image/webp", ".gif": "image/gif"}


def embed_image(store_path: PathLike, key: str, image: PathLike, *, overwrite: bool = False) -> Dict[str, Any]:
    """Embed an image file as a byte array (``embedded/images/<key>``); served unchanged."""
    zarr = _zarr()
    image = Path(image)
    final, tmp = _begin(store_path, key, overwrite, IMAGES)
    try:
        raw = np.frombuffer(image.read_bytes(), dtype=np.uint8)
        root = zarr.open_group(str(tmp), mode="w", zarr_format=3)
        z = root.create_array("data", shape=raw.shape, chunks=(max(1, min(len(raw), 1 << 20)),), dtype=np.uint8,
                              compressors=None)
        z[:] = raw
        meta = {"key": key, "source": image.name, "media_type": _MEDIA.get(image.suffix.lower(), "application/octet-stream"),
                "bytes": int(len(raw))}
        root.attrs["uchrom_image"] = meta
        _commit(final, tmp, consolidate=False)
        return meta
    except BaseException:
        shutil.rmtree(tmp, ignore_errors=True)
        raise


def list_embedded_images(store) -> Dict[str, str]:
    zarr = _zarr()
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            grp = zarr.open_group(as_store(store), path=IMAGES, mode="r", use_consolidated=True, zarr_format=3)
    except Exception:
        return {}
    return {str(sub.attrs["uchrom_image"]["key"]): name for name, sub in grp.groups()
            if ".partial-" not in name and "uchrom_image" in sub.attrs}


def read_embedded_image(store, name: str) -> Tuple[bytes, str]:
    """(file bytes, media type) of an embedded image."""
    zarr = _zarr()
    g = zarr.open_group(as_store(store), path=f"{IMAGES}/{name}", mode="r", zarr_format=3)
    return g["data"][:].tobytes(), str(g.attrs["uchrom_image"]["media_type"])


# ======================================================================
# export back to cooler files (interoperability; Python code that needs a cooler)
# ======================================================================

def _open(store, key: str) -> "EmbeddedContacts":
    names = list_embedded(store)
    if key not in names:
        raise KeyError(f"no embedded contact map {key!r} (have {sorted(names)})")
    return EmbeddedContacts(store, names[key])


def _pixel_frame(e: "EmbeddedContacts", r: int, cell_idx=None):
    import pandas as pd

    blocks = list(e.iter_pixels(r, cell_idx))
    if not blocks:
        return pd.DataFrame({"bin1_id": np.zeros(0, np.int64), "bin2_id": np.zeros(0, np.int64),
                             "count": np.zeros(0, np.int64)})
    d = np.concatenate([np.column_stack(b) for b in blocks])
    d = d[np.lexsort((d[:, 1], d[:, 0]))]
    return pd.DataFrame({"bin1_id": d[:, 0], "bin2_id": d[:, 1], "count": d[:, 2]})


def _bins_frame(e: "EmbeddedContacts", r: int):
    b = e.bins(r)
    return b[["chrom", "start", "end"] + (["weight"] if "weight" in b else [])]


def export_cool(store, key: str, out: PathLike, *, resolution: Optional[int] = None,
                cell: Optional[str] = None) -> Path:
    """Write one resolution of a bulk map (or one cell of a per-cell map) as a ``.cool``.
    A bulk map embedded without trans contacts at this resolution exports its cis pixels only."""
    import cooler

    e = _open(store, key)
    r = e._res(resolution)
    idx = None
    if e.kind == "per_cell":
        if cell is None:
            raise ValueError("a per-cell map needs cell=<name> (or use export_scool)")
        idx = [e.cells.index(str(cell))]
    cooler.create_cooler(str(out), _bins_frame(e, r), _pixel_frame(e, r, idx), ordered=True,
                         columns=["count"], dtypes={"count": "int32"}, ensure_sorted=False)
    return Path(out)


def export_mcool(store, key: str, out: PathLike, *, resolutions: Optional[Sequence[int]] = None) -> Path:
    """Write a bulk map as a ``.mcool``: every embedded resolution, or only ``resolutions`` (the fine levels of
    a genome-wide map are by far the largest).  Written to a temporary file and renamed, so an interrupted
    export leaves no partial file."""
    import cooler

    e = _open(store, key)
    if e.kind != "bulk":
        raise ValueError(f"{key!r} is a per-cell map: use export_scool")
    levels = list(e.resolutions) if resolutions is None else [int(r) for r in resolutions]
    missing = [r for r in levels if r not in e.resolutions]
    if missing:
        raise ValueError(f"{key!r} has no embedded level at {missing} bp ({list(e.resolutions)})")
    out = Path(out)
    tmp = out.with_name(f".{out.name}.{os.getpid()}.part")
    tmp.unlink(missing_ok=True)
    try:
        for r in levels:
            cooler.create_cooler(f"{tmp}::/resolutions/{r}", _bins_frame(e, r), _pixel_frame(e, r), ordered=True,
                                 columns=["count"], dtypes={"count": "int32"}, mode="a")
        os.replace(tmp, out)
    finally:
        tmp.unlink(missing_ok=True)
    return out


def export_scool(store, key: str, out: PathLike, *, cells: Optional[Sequence[str]] = None,
                 trans: bool = True) -> Path:
    """Write a per-cell map (all cells or ``cells``) as a ``.scool``; the cells are built in memory.
    Each partition is read once for all the cells (few large reads, also over HTTP); ``trans=False`` leaves
    out the contacts between chromosomes."""
    import cooler
    import pandas as pd

    e = _open(store, key)
    if e.kind != "per_cell":
        raise ValueError(f"{key!r} is a bulk map: use export_cool / export_mcool")
    r = e.resolutions[0]
    names = [str(c) for c in cells] if cells is not None else list(e.cells)
    pos = {c: i for i, c in enumerate(e.cells)}
    missing = [c for c in names if c not in pos]
    if missing:
        raise KeyError(f"cells not in {key!r}: {missing[:5]}")
    order = np.unique([pos[c] for c in names]).astype(np.int64)
    got: Dict[int, list] = {int(i): [] for i in order}
    parts = [(f"cis/{c}", e.first_bin(c, r)) for c in e.chroms if f"cis/{c}" in e.g[f"r{r}"]]
    if trans and "trans" in e.g[f"r{r}"]:
        parts.append(("trans", 0))
    for part, f0 in parts:
        off = e._offsets(r, part, "cell_offset")
        n = off[order + 1] - off[order]
        cell_of, n = order[n > 0], n[n > 0]
        k = 0
        for d in e.cell_pixel_blocks(part, order, r):     # whole cells, in cell order
            s = 0
            while s < len(d):
                got[int(cell_of[k])].append(d[s:s + n[k]] + (f0, f0, 0))
                s += int(n[k])
                k += 1
    maps = {}
    for c in names:
        blocks = got[pos[c]]
        d = np.concatenate(blocks) if blocks else np.zeros((0, 3), np.int64)
        d = d[np.lexsort((d[:, 1], d[:, 0]))]
        maps[c] = pd.DataFrame({"bin1_id": d[:, 0], "bin2_id": d[:, 1], "count": d[:, 2]})
    cooler.create_scool(str(out), _bins_frame(e, r), maps, ordered=True)
    return Path(out)


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
    finds an embedded copy uses it.  Keys that are already embedded are skipped unless ``overwrite``.
    Returns ``{key: summary}`` of what was embedded."""
    from .cdata import ChromData

    cd = ChromData.read(str(store_path), backed=True)
    done: Dict[str, Any] = {}
    todo = [(fam, k, r) for fam in ("linked_cool", "linked_scool", "linked_bin_matrices", "linked_anndata", "linked_images")
            for k, r in _records(cd.uns, fam).items() if keys is None or k in set(keys)]
    for fam, key, rec in todo:
        path = cd.resolve_link_path(rec["path"])
        if not path.exists():
            if verbose:
                print(f"[embed] {fam}/{key}: {path} not found, skipped")
            continue
        section = {"linked_cool": GROUP, "linked_scool": GROUP, "linked_images": IMAGES}.get(fam, ANNDATA)
        if not overwrite and (Path(store_path) / section / safe_name(key)).exists():
            if verbose:
                print(f"[embed] {fam}/{key}: already embedded, skipped (overwrite=True replaces it)")
            continue
        if verbose:
            print(f"[embed] {fam}/{key}: {path.name}", flush=True)
        label = rec.get("label")
        if fam == "linked_scool":
            done[key] = embed_scool(store_path, key, path, label=label, overwrite=overwrite)
        elif fam == "linked_cool":
            done[key] = embed_cool(store_path, key, path, label=label, overwrite=overwrite,
                                   trans_min_resolution=trans_min_resolution)
        elif fam == "linked_images":
            done[key] = embed_image(store_path, key, path, overwrite=overwrite)
        else:
            done[key] = embed_anndata(store_path, key, path, family=fam, label=label, overwrite=overwrite)
    consolidate_sections(store_path)
    return done


def embed_reachable(cd, store_path: PathLike, *, verbose: bool = False) -> Dict[str, Any]:
    """Embed into ``store_path`` (a store just written from ``cd``) the linked contact maps and AnnData that
    ``cd`` can reach — its linked files, or the embedded copies of the store it was read from (an atlas
    store, also for a subset or a copy of it) — limited to ``cd``'s cells where the data are per cell.
    ``ChromData.write(path, embed=True)`` calls it.  Returns ``{key: summary}``; a link that cannot be
    reached is left as it is (with a warning)."""
    import tempfile

    ids = [str(c) for c in cd.cells.index] if len(cd.cells) else None
    origin = cd._links_from()
    done: Dict[str, Any] = {}
    for key, rec in _records(cd.uns, "linked_scool").items():
        try:
            path = cd.linked_scool_path(key, cells=ids)
        except FileNotFoundError as exc:
            warnings.warn(f"embed: {exc}", stacklevel=3)
            continue
        import cooler

        have = {c.rsplit("/", 1)[-1] for c in cooler.fileops.list_scool_cells(path)}
        keep = [c for c in ids if c in have] if ids is not None else None
        done[key] = embed_scool(store_path, key, path, label=rec.get("label"), overwrite=True, cells=keep)
    for key, rec in _records(cd.uns, "linked_cool").items():
        try:
            path = cd.linked_cool_path(key)
        except FileNotFoundError as exc:
            warnings.warn(f"embed: {exc}", stacklevel=3)
            continue
        done[key] = embed_cool(store_path, key, path, label=rec.get("label"), overwrite=True)
    for fam in ("linked_anndata", "linked_bin_matrices"):
        for key, rec in _records(cd.uns, fam).items():
            path = cd.resolve_link_path(rec["path"]) if rec.get("path") else None
            if path is not None and path.exists():
                import anndata as ad

                adata = ad.read_h5ad(path)
            else:
                found = list_embedded_anndata(str(origin), fam) if origin is not None else {}
                if key not in found:
                    warnings.warn(f"embed: {fam} {key!r} is neither a file nor embedded in the origin store",
                                  stacklevel=3)
                    continue
                adata = read_embedded_anndata(str(origin), found[key])
            if fam == "linked_anndata" and ids is not None and set(ids) <= set(map(str, adata.obs_names)):
                adata = adata[ids].copy()                     # this object's cells, in its order
            with tempfile.TemporaryDirectory() as tmp:
                h5ad = Path(tmp) / f"{safe_name(key)}.h5ad"
                adata.write_h5ad(h5ad)
                done[f"{fam}/{key}"] = embed_anndata(store_path, key, h5ad, family=fam, label=rec.get("label"),
                                                     overwrite=True)
    if done:
        consolidate_sections(store_path)
    if verbose:
        print("[embed]", ", ".join(done) or "nothing to embed")
    return done


if __name__ == "__main__":     # python -m chromdata.embedded STORE [--overwrite] [--keys a b ...] [--reconsolidate]
    import argparse

    ap = argparse.ArgumentParser(description="Embed the linked contact maps / h5ad files into a .chromdata.zarr store")
    ap.add_argument("store")
    ap.add_argument("--overwrite", action="store_true")
    ap.add_argument("--keys", nargs="*")
    ap.add_argument("--trans-min-resolution", type=int, default=TRANS_MIN_RESOLUTION)
    ap.add_argument("--reconsolidate", action="store_true", help="only rebuild the metadata index of the embedded groups")
    ap.add_argument("--upgrade", action="store_true",
                    help="make an embedded store cheap to open over HTTP (chromsizes in the attrs, consolidated root metadata)")
    a = ap.parse_args()
    if a.upgrade:
        print(upgrade_store(a.store))
        raise SystemExit(0)
    if a.reconsolidate:
        consolidate_sections(a.store)
        raise SystemExit(0)
    embed_links(a.store, overwrite=a.overwrite, keys=a.keys, trans_min_resolution=a.trans_min_resolution)
