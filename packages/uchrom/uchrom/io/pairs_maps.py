"""Contact pairs binned into contact maps: one cell's pairs file -> pixels, many cells -> one ``.scool``.

Inputs are the per-cell contact lists of single-cell Hi-C pipelines:

* 4DN / hickit ``.pairs[.gz]`` (``readID chr1 pos1 chr2 pos2 strand1 strand2 [phase0 phase1 phase_prob..]``;
  the columns are named by the ``#columns:`` header);
* Dip-C ``.con[.gz]`` (two tab-separated legs ``chrom,pos,hap`` per line).

Each line is one contact and is counted once: phase columns (haplotypes of the legs, imputed phase
probabilities) are ignored, so a map of a diploid cell is the sum over its two homologs.  Positions are
1-based (as in the pairs and SAM formats); a contact falls into the bin ``(pos - 1) // resolution`` of its
chromosome.  Chromosome names match with or without a ``chr`` prefix; contacts on chromosomes outside the
given sizes (chrY, chrM, unplaced contigs) or beyond a chromosome's end are dropped and counted::

    sizes = {"chr1": 248956422, ...}
    stats = pairs_to_scool({"cell_035": "cell_035.impute.pairs.gz", ...}, "cells_5kb.scool",
                           chromsizes=sizes, resolution=5000, assembly="hg38")
"""

from __future__ import annotations

import gzip
import io
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Callable, Dict, Iterator, Optional, Tuple, Union

import numpy as np
import pandas as pd

__all__ = ["genome_bins", "iter_pairs", "bin_pairs", "pairs_to_scool", "pairs_chromsizes", "tar_member"]

#: lines read per chunk of a pairs file
CHUNK_LINES = 2_000_000

PathOrOpener = Union[str, os.PathLike, Callable[[], io.IOBase]]


def genome_bins(chromsizes: Mapping, resolution: int) -> pd.DataFrame:
    """Fixed-size bins ``chrom, start, end`` of every chromosome (the last bin ends at the chromosome end)."""
    res = int(resolution)
    parts = []
    for c, size in chromsizes.items():
        starts = np.arange(0, int(size), res, dtype=np.int64)
        parts.append(pd.DataFrame({"chrom": str(c), "start": starts, "end": np.minimum(starts + res, int(size))}))
    return pd.concat(parts, ignore_index=True)


def _text(src: PathOrOpener):
    """A text handle on a path (gzip by suffix) or on what ``src()`` opens (gzip detected by magic bytes)."""
    if callable(src):
        raw = src()
        head = raw.peek(2)[:2] if hasattr(raw, "peek") else b""
        if not head:
            raw = io.BufferedReader(raw)
            head = raw.peek(2)[:2]
        return io.TextIOWrapper(gzip.GzipFile(fileobj=raw) if head == b"\x1f\x8b" else raw)
    path = str(src)
    return gzip.open(path, "rt") if path.endswith(".gz") else open(path)


def _columns(fh) -> Tuple[Optional[list], int]:
    """(``#columns:`` names or None, number of header lines) of a pairs file."""
    names, n = None, 0
    for line in fh:
        if not line.startswith("#"):
            break
        n += 1
        if line.startswith("#columns:"):
            names = line.split()[1:]
    return names, n


def pairs_chromsizes(src: PathOrOpener) -> Dict[str, int]:
    """The chromosome sizes a pairs file declares (``#chromsize:`` / ``#chromosome:`` header lines), in order."""
    out: Dict[str, int] = {}
    with _text(src) as fh:
        for line in fh:
            if not line.startswith("#"):
                break
            if line.startswith(("#chromsize:", "#chromosome:")):
                _, name, size = line.split()[:3]
                out[name] = int(size)
    return out


def tar_member(tarball: Union[str, os.PathLike], member: str) -> Callable[[], io.IOBase]:
    """An opener (for :func:`bin_pairs` / :func:`pairs_to_scool`) of a file inside a tarball, read in place:
    the member (e.g. a cell's ``.pairs.gz``) is read into memory, nothing is extracted to disk."""
    import tarfile

    def opener():
        with tarfile.open(str(tarball), "r:*") as tf:
            return io.BufferedReader(io.BytesIO(tf.extractfile(member).read()))

    return opener


def _is_con(name: str) -> bool:
    name = name[:-3] if name.endswith(".gz") else name
    return name.endswith((".con", ".con.txt"))


def iter_pairs(src: PathOrOpener, *, name: Optional[str] = None,
               chunk_lines: int = CHUNK_LINES) -> Iterator[pd.DataFrame]:
    """The contacts of a pairs / ``.con`` file as chunks ``chrom1, pos1, chrom2, pos2`` (chromosomes as
    categoricals, 1-based positions).

    ``src`` is a path or a callable opening a binary stream (e.g. a member of a tarball); ``name`` is the file
    name that tells a ``.con`` from a ``.pairs`` when ``src`` is a callable.
    """
    label = name or (str(src) if not callable(src) else "")
    if _is_con(label):
        with _text(src) as fh:
            # "c1,p1,h1<TAB>c2,p2,h2": split on commas -> c1 | p1 | "h1<TAB>c2" | p2 | h2
            reader = pd.read_csv(fh, sep=",", header=None, comment="#", usecols=[0, 1, 2, 3],
                                 names=["chrom1", "pos1", "h1c2", "pos2"],
                                 dtype={"chrom1": "category", "pos1": np.int64, "h1c2": str, "pos2": np.int64},
                                 chunksize=chunk_lines)
            for chunk in reader:
                c2 = chunk["h1c2"].str.split("\t", n=1).str[1]
                yield pd.DataFrame({"chrom1": chunk["chrom1"], "pos1": chunk["pos1"],
                                    "chrom2": c2.astype("category"), "pos2": chunk["pos2"]})
        return
    with _text(src) as fh:
        names, _ = _columns(fh)
    names = names or ["readID", "chr1", "pos1", "chr2", "pos2"]
    try:
        cols = [names.index(c) for c in ("chr1", "pos1", "chr2", "pos2")]
    except ValueError:
        raise ValueError(f"{label}: no chr1 / pos1 / chr2 / pos2 columns in {names}") from None
    with _text(src) as fh:
        reader = pd.read_csv(fh, sep="\t", header=None, comment="#", usecols=cols,
                             dtype={cols[0]: "category", cols[1]: np.int64, cols[2]: "category", cols[3]: np.int64},
                             chunksize=chunk_lines)
        for chunk in reader:
            chunk = chunk[cols]
            chunk.columns = ["chrom1", "pos1", "chrom2", "pos2"]
            yield chunk


def _chrom_codes(cat: pd.Series, lookup: Dict[str, int]) -> np.ndarray:
    """Index into the chromosome list of every value of a categorical column (-1: not a kept chromosome)."""
    cats = cat.cat.categories.astype(str)
    table = np.array([lookup.get(c, lookup.get(_strip(c), -1)) for c in cats] + [-1], np.int64)
    codes = cat.cat.codes.to_numpy().astype(np.int64)
    return table[codes]                                   # code -1 (NaN) -> the trailing -1


def _strip(name: str) -> str:
    return name[3:] if name.lower().startswith("chr") else name


def bin_pairs(src: PathOrOpener, chromsizes: Mapping, resolution: int, *, name: Optional[str] = None,
              chunk_lines: int = CHUNK_LINES) -> Tuple[pd.DataFrame, Dict[str, int]]:
    """One cell's contacts summed into the genome-wide bins of :func:`genome_bins` (upper triangle).

    Returns
    -------
    pixels : DataFrame
        ``bin1_id, bin2_id, count`` sorted by (bin1, bin2), ``bin1_id <= bin2_id``.
    stats : dict
        ``n_lines`` (contacts in the file), ``n_contacts`` (binned), ``n_cis``, ``n_trans``, ``n_dropped``
        (other chromosomes / beyond an end), ``n_pixels``.
    """
    res = int(resolution)
    names = [str(c) for c in chromsizes]
    sizes = np.array([int(chromsizes[c]) for c in chromsizes], np.int64)
    nb = -(-sizes // res)
    offset = np.r_[0, np.cumsum(nb)[:-1]].astype(np.int64)
    width = int(nb.sum())
    lookup = {c: i for i, c in enumerate(names)}
    lookup.update({_strip(c): i for i, c in enumerate(names)})
    keys, n_lines, n_drop = [], 0, 0
    for chunk in iter_pairs(src, name=name, chunk_lines=chunk_lines):
        n_lines += len(chunk)
        c1 = _chrom_codes(chunk["chrom1"], lookup)
        c2 = _chrom_codes(chunk["chrom2"], lookup)
        p1 = chunk["pos1"].to_numpy(np.int64) - 1
        p2 = chunk["pos2"].to_numpy(np.int64) - 1
        ok = (c1 >= 0) & (c2 >= 0)
        ok[ok] &= (p1[ok] >= 0) & (p2[ok] >= 0) & (p1[ok] < sizes[c1[ok]]) & (p2[ok] < sizes[c2[ok]])
        n_drop += int((~ok).sum())
        g1 = offset[c1[ok]] + p1[ok] // res
        g2 = offset[c2[ok]] + p2[ok] // res
        keys.append(np.minimum(g1, g2) * width + np.maximum(g1, g2))
    k = np.concatenate(keys) if keys else np.zeros(0, np.int64)
    uk, cnt = np.unique(k, return_counts=True)
    b1, b2 = uk // width, uk % width
    chrom_of = np.repeat(np.arange(len(names)), nb)
    cis = chrom_of[b1] == chrom_of[b2]
    px = pd.DataFrame({"bin1_id": b1, "bin2_id": b2, "count": cnt.astype(np.int64)})
    stats = {"n_lines": int(n_lines), "n_contacts": int(cnt.sum()), "n_cis": int(cnt[cis].sum()),
             "n_trans": int(cnt[~cis].sum()), "n_dropped": int(n_drop), "n_pixels": int(len(px))}
    return px, stats


class _LazyCells(Mapping):
    """``{cell: pixels}`` computed when cooler asks for a cell (one cell in memory at a time)."""

    def __init__(self, sources: Mapping, chromsizes: Mapping, resolution: int, verbose: bool):
        self.sources = dict(sources)
        self.chromsizes, self.resolution, self.verbose = chromsizes, resolution, verbose
        self.stats: Dict[str, dict] = {}

    def __getitem__(self, cell):
        src = self.sources[cell]
        name = src[1] if isinstance(src, tuple) else None
        opener = src[0] if isinstance(src, tuple) else src
        px, st = bin_pairs(opener, self.chromsizes, self.resolution, name=name)
        self.stats[cell] = st
        if self.verbose:
            print(f"[scool] {cell}: {st['n_contacts']:,} contacts, {st['n_pixels']:,} pixels", flush=True)
        return px

    def __iter__(self):
        return iter(self.sources)

    def __len__(self):
        return len(self.sources)


def pairs_to_scool(cells: Mapping, out: Union[str, os.PathLike], *, chromsizes: Mapping, resolution: int,
                   assembly: Optional[str] = None, metadata: Optional[dict] = None,
                   verbose: bool = False) -> pd.DataFrame:
    """Bin the contacts of every cell into one ``.scool`` (cooler's single-cell format, shared bins).

    Parameters
    ----------
    cells
        ``{cell name: source}``; a source is a path of a ``.pairs[.gz]`` / ``.con[.gz]`` file or a tuple
        ``(opener, file name)`` where ``opener()`` returns a binary stream (e.g. a tarball member).
    out
        The ``.scool`` to write (atomically: written next to it, then renamed).
    chromsizes
        ``{chromosome: length}`` in genome order: the bins (:func:`genome_bins`) and the kept chromosomes.
    resolution
        Bin size (bp).
    assembly, metadata
        Recorded in the file.

    Returns
    -------
    DataFrame indexed by cell: ``n_lines, n_contacts, n_cis, n_trans, n_dropped, n_pixels`` (see
    :func:`bin_pairs`).
    """
    import cooler

    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_name(f".{out.name}.{os.getpid()}.part")
    lazy = _LazyCells(cells, chromsizes, int(resolution), verbose)
    try:
        cooler.create_scool(str(tmp), genome_bins(chromsizes, resolution), lazy, ordered=True,
                            assembly=assembly, metadata=metadata or {}, dtypes={"count": np.int32})
        os.replace(tmp, out)
    finally:
        if tmp.exists():
            tmp.unlink()
    stats = pd.DataFrame.from_dict(lazy.stats, orient="index")
    stats.index.name = "cell"
    return stats.reindex(list(cells))
