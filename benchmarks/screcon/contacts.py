"""Single-cell contact tables: read, write back in the same format, bin onto particles.

Standalone (numpy only) so it runs in the Sherlock ``venv-main`` without U-Chrom.

Formats
-------
* **GEO / Stevens et al. 2017** (GSE80280 ``*_contact_pairs.txt.gz``): whitespace
  table ``chr_A pos_A chr_B pos_B`` (optional ``#`` header line).
* **.pairs** (4DN): ``readID chr1 pos1 chr2 pos2 [strand1 strand2 ...]`` with ``#``
  header lines.

:func:`read_contacts` keeps every raw data line, so :func:`write_contacts` can write
any subset of rows (e.g. a training / held-out split) byte-identical to the input
lines, header included: any reconstruction method that reads the input reads the
split unchanged.

Particle convention
-------------------
Models are stored as ``.npz`` with ``chrom`` (N,), ``pos`` (N,) and ``coords``
(M, N, 3).  ``pos`` follows the NucDynamics 2017 convention: particle *k* covers the
genomic interval ``(pos_k - size, pos_k]``.  :func:`particle_index` maps genomic
positions to particle indices under this convention (``-1`` = not covered).
"""

from __future__ import annotations

import gzip
import re
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

# Chromosome sizes (UCSC) used when a method needs chromosome lengths (Si-C, hickit).
MM10 = {"chr1": 195471971, "chr2": 182113224, "chr3": 160039680, "chr4": 156508116, "chr5": 151834684,
        "chr6": 149736546, "chr7": 145441459, "chr8": 129401213, "chr9": 124595110, "chr10": 130694993,
        "chr11": 122082543, "chr12": 120129022, "chr13": 120421639, "chr14": 124902244, "chr15": 104043685,
        "chr16": 98207768, "chr17": 94987271, "chr18": 90702639, "chr19": 61431566, "chrX": 171031299,
        "chrY": 91744698}
HG38 = {"chr1": 248956422, "chr2": 242193529, "chr3": 198295559, "chr4": 190214555, "chr5": 181538259,
        "chr6": 170805979, "chr7": 159345973, "chr8": 145138636, "chr9": 138394717, "chr10": 133797422,
        "chr11": 135086622, "chr12": 133275309, "chr13": 114364328, "chr14": 107043718, "chr15": 101991189,
        "chr16": 90338345, "chr17": 83257441, "chr18": 80373285, "chr19": 58617616, "chr20": 64444167,
        "chr21": 46709983, "chr22": 50818468, "chrX": 156040895, "chrY": 57227415}
ASSEMBLIES = {"mm10": MM10, "hg38": HG38}


def _open(path, mode="rt"):
    path = str(path)
    return gzip.open(path, mode) if path.endswith(".gz") else open(path, mode.replace("t", ""))


def chrom_key(name: str):
    """Natural sort key: chr1 < chr2 < ... < chr10 < ... < chrX < chrY."""
    s = name[3:] if name.lower().startswith("chr") else name
    return (0, int(s), "") if s.isdigit() else (1, 0, s)


def sort_chroms(names) -> list[str]:
    return sorted(set(map(str, names)), key=chrom_key)


@dataclass
class Contacts:
    """One contact (read pair) per row."""

    chrom_a: np.ndarray
    pos_a: np.ndarray
    chrom_b: np.ndarray
    pos_b: np.ndarray
    fmt: str = "geo"                  # "geo" | "pairs"
    header: list[str] = field(default_factory=list)
    lines: list[str] | None = None    # raw data lines (without newline), same order as the arrays

    def __len__(self) -> int:
        return len(self.pos_a)

    def subset(self, idx) -> "Contacts":
        idx = np.asarray(idx)
        lines = None if self.lines is None else [self.lines[i] for i in (np.flatnonzero(idx) if idx.dtype == bool else idx)]
        return Contacts(self.chrom_a[idx], self.pos_a[idx], self.chrom_b[idx], self.pos_b[idx], self.fmt,
                        list(self.header), lines)

    @property
    def chroms(self) -> list[str]:
        return sort_chroms(np.concatenate([self.chrom_a, self.chrom_b]))


def read_contacts(path) -> Contacts:
    """Read a GEO (``chr_A pos_A chr_B pos_B``) or ``.pairs`` table, keeping the raw lines."""
    header, lines, ca, pa, cb, pb = [], [], [], [], [], []
    fmt = None
    with _open(path) as fh:
        for line in fh:
            line = line.rstrip("\n").rstrip("\r")
            if not line.strip():
                continue
            if line.startswith("#"):
                header.append(line)
                continue
            r = line.split()
            if fmt is None:
                fmt = "geo" if (re.fullmatch(r"-?\d+", r[1]) and not re.fullmatch(r"-?\d+", r[2])) else "pairs"
            if fmt == "geo":
                c1, p1, c2, p2 = r[0], r[1], r[2], r[3]
            else:
                c1, p1, c2, p2 = r[1], r[2], r[3], r[4]
            ca.append(c1); pa.append(int(p1)); cb.append(c2); pb.append(int(p2))
            lines.append(line)
    return Contacts(np.array(ca, dtype=object), np.array(pa, np.int64), np.array(cb, dtype=object),
                    np.array(pb, np.int64), fmt or "geo", header, lines)


def write_contacts(path, contacts: Contacts, idx=None) -> int:
    """Write (a subset of) ``contacts`` in its input format; returns the number of rows."""
    c = contacts if idx is None else contacts.subset(idx)
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with _open(path, "wt") as fh:
        for h in c.header:
            fh.write(h + "\n")
        if c.lines is not None:
            for line in c.lines:
                fh.write(line + "\n")
        else:
            for row in zip(c.chrom_a, c.pos_a, c.chrom_b, c.pos_b):
                if c.fmt == "pairs":
                    fh.write(".\t%s\t%d\t%s\t%d\t.\t.\n" % row)
                else:
                    fh.write("%s\t%d\t%s\t%d\n" % row)
    return len(c)


def write_geo(path, chrom_a, pos_a, chrom_b, pos_b, header: bool = True) -> int:
    """Write a GEO-style table (``chr_A pos_A chr_B pos_B``, tab separated)."""
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with _open(path, "wt") as fh:
        if header:
            fh.write("#chr_A\tpos_A\tchr_B\tpos_B\n")
        for row in zip(chrom_a, pos_a, chrom_b, pos_b):
            fh.write("%s\t%d\t%s\t%d\n" % row)
    return len(pos_a)


def write_pairs(path, contacts: Contacts, chrom_sizes: dict[str, int] | None = None) -> int:
    """Write a 4DN ``.pairs`` file (strands unknown: ``.``) with ``#chromosome`` lines (hickit needs them)."""
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with _open(path, "wt") as fh:
        fh.write("## pairs format v1.0\n")
        for c in contacts.chroms:
            if chrom_sizes and c in chrom_sizes:
                fh.write(f"#chromosome: {c} {int(chrom_sizes[c])}\n")
        fh.write("#columns: readID chr1 pos1 chr2 pos2 strand1 strand2\n")
        for k, row in enumerate(zip(contacts.chrom_a, contacts.pos_a, contacts.chrom_b, contacts.pos_b)):
            fh.write("r%d\t%s\t%d\t%s\t%d\t.\t.\n" % ((k,) + row))
    return len(contacts)


def chrom_sizes_for(contacts: Contacts, assembly: str | None = None, pad: int = 0) -> dict[str, int]:
    """Chromosome lengths: the assembly's where known, never shorter than the largest contact position + 1."""
    ref = ASSEMBLIES.get(assembly or "", {})
    out = {}
    for c in contacts.chroms:
        m = max(contacts.pos_a[contacts.chrom_a == c].max(initial=0), contacts.pos_b[contacts.chrom_b == c].max(initial=0))
        out[c] = max(int(ref.get(c, 0)), int(m) + 1 + pad)
    return out


# --------------------------------------------------------------------------- particles

def load_models(path):
    """``.npz`` model file -> (chrom (N,) str, pos (N,) int64, coords (M, N, 3) float)."""
    z = np.load(path, allow_pickle=True)
    X = np.asarray(z["coords"], float)
    if X.ndim == 2:
        X = X[None]
    return z["chrom"].astype(str), z["pos"].astype(np.int64), X


def particle_size(chrom, pos) -> int:
    """Median spacing of consecutive particles on the same chromosome."""
    chrom = np.asarray(chrom)
    d = np.diff(pos)[chrom[1:] == chrom[:-1]]
    d = d[d > 0]
    return int(np.median(d)) if len(d) else 0


class ParticleIndex:
    """Map (chrom, genomic position) -> particle index; particle k covers (pos_k - size, pos_k]."""

    def __init__(self, chrom, pos, size: int | None = None):
        chrom = np.asarray(chrom).astype(str)
        pos = np.asarray(pos, np.int64)
        self.size = int(size or particle_size(chrom, pos))
        self._idx = {}
        for c in np.unique(chrom):
            sel = np.flatnonzero(chrom == c)
            order = sel[np.argsort(pos[sel], kind="stable")]
            self._idx[c] = (pos[order], order)

    def __call__(self, chroms, positions) -> np.ndarray:
        chroms = np.asarray(chroms).astype(str)
        positions = np.asarray(positions, np.int64)
        out = np.full(len(positions), -1, np.int64)
        for c, (pp, order) in self._idx.items():
            sel = np.flatnonzero(chroms == c)
            if not len(sel):
                continue
            p = positions[sel]
            k = np.searchsorted(pp, p, side="left")
            ok = k < len(pp)
            kk = np.where(ok, k, 0)
            ok &= (pp[kk] - self.size < p) & (p <= pp[kk])
            out[sel[ok]] = order[kk[ok]]
        return out


def particle_index(chrom, pos, size=None) -> ParticleIndex:
    return ParticleIndex(chrom, pos, size)


def bin_contacts(contacts: Contacts, chrom, pos, size=None):
    """Particle indices (i, j) of every contact end (``-1`` = not covered by a particle)."""
    pidx = ParticleIndex(chrom, pos, size)
    return pidx(contacts.chrom_a, contacts.pos_a), pidx(contacts.chrom_b, contacts.pos_b)


def contact_pairs(i, j, chrom=None, min_sep: int = 2):
    """Unique particle pairs (i < j) with counts, dropping uncovered ends and, when ``chrom``
    is given, cis pairs closer than ``min_sep`` particles (NucDynamics excludes |i-j| < 2)."""
    i = np.asarray(i); j = np.asarray(j)
    ok = (i >= 0) & (j >= 0) & (i != j)
    a, b = np.minimum(i[ok], j[ok]), np.maximum(i[ok], j[ok])
    if chrom is not None:
        chrom = np.asarray(chrom)
        keep = (chrom[a] != chrom[b]) | (b - a >= min_sep)
        a, b = a[keep], b[keep]
    if not len(a):
        return np.zeros((0, 2), np.int64), np.zeros(0, np.int64)
    pairs, counts = np.unique(np.stack([a, b], 1), axis=0, return_counts=True)
    return pairs, counts


# --------------------------------------------------------------------------- genomic grid

class Grid:
    """A regular genomic bin grid (bin k of a chromosome = [k*res, (k+1)*res)) over given spans.

    Global bin id = offset[chrom] + (pos // res - first_bin[chrom]).
    """

    def __init__(self, spans: dict[str, tuple[int, int]], res: int):
        self.res = int(res)
        self.chroms = sort_chroms(spans)
        self.first, self.nbins, self.offset = {}, {}, {}
        off = 0
        for c in self.chroms:
            lo, hi = spans[c]
            f, l = int(lo) // self.res, int(hi) // self.res
            self.first[c], self.nbins[c], self.offset[c] = f, l - f + 1, off
            off += l - f + 1
        self.n = off
        self.chrom = np.concatenate([np.full(self.nbins[c], c, dtype=object) for c in self.chroms]).astype(str) \
            if self.chroms else np.zeros(0, str)
        self.bin = np.concatenate([np.arange(self.first[c], self.first[c] + self.nbins[c]) for c in self.chroms]) \
            if self.chroms else np.zeros(0, np.int64)

    @classmethod
    def from_contacts(cls, contacts: Contacts, res: int) -> "Grid":
        spans = {}
        for c in contacts.chroms:
            p = np.concatenate([contacts.pos_a[contacts.chrom_a == c], contacts.pos_b[contacts.chrom_b == c]])
            spans[c] = (int(p.min()), int(p.max()))
        return cls(spans, res)

    def index(self, chroms, positions) -> np.ndarray:
        chroms = np.asarray(chroms).astype(str)
        positions = np.asarray(positions, np.int64)
        out = np.full(len(positions), -1, np.int64)
        for c in self.chroms:
            sel = np.flatnonzero(chroms == c)
            if not len(sel):
                continue
            k = positions[sel] // self.res - self.first[c]
            ok = (k >= 0) & (k < self.nbins[c])
            out[sel[ok]] = self.offset[c] + k[ok]
        return out

    @property
    def mid(self) -> np.ndarray:
        """Genomic midpoint of every bin."""
        return self.bin * self.res + self.res // 2

    def to_dict(self) -> dict:
        return {"res": self.res, "chroms": self.chroms,
                "spans": {c: [self.first[c] * self.res, (self.first[c] + self.nbins[c]) * self.res - 1] for c in self.chroms}}

    @classmethod
    def from_dict(cls, d) -> "Grid":
        return cls({c: tuple(v) for c, v in d["spans"].items()}, d["res"])
