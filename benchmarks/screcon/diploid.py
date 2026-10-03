"""Shared helpers of the diploid (homolog-resolved) benchmarks (numpy / pandas only).

Convention: a diploid structure is stored like a haploid one (``.npz``: ``chrom``, ``pos``,
``coords``) with one *copy chain* per chromosome copy, named ``<chrom>(<h>)`` (h = 0 / 1, the
haplotype index of the phasing: 0 = paternal, 1 = maternal in Dip-C / hickit); a single-copy
chromosome (male X / Y) keeps its plain name.  The haploid scorers (``simulate.score_ensemble``,
``ParticleIndex``) then work unchanged: "cis" = within one copy chain.

Phased contact tables are hickit ``.pairs`` (``phase0`` / ``phase1``: ``0``, ``1``, ``.``).
"""

from __future__ import annotations

import gzip
import re
from pathlib import Path

import numpy as np

COPY_RE = re.compile(r"^(.*)\((\d)\)$")
PROB_COLS = ("phase_prob00", "phase_prob01", "phase_prob10", "phase_prob11")


def copy_name(chrom: str, h: int, ploidy: int = 2) -> str:
    return f"{chrom}({int(h)})" if ploidy == 2 else str(chrom)


def split_copy(name: str) -> tuple[str, int]:
    """``chr1(1)`` -> (``chr1``, 1); a plain name -> (name, 0)."""
    m = COPY_RE.match(str(name))
    return (m.group(1), int(m.group(2))) if m else (str(name), 0)


def hickit_copy(name: str, ploidy: dict | None = None) -> str:
    """hickit split-chromosome names (``1a`` / ``chr1b``: suffix a = haplotype 0, b = 1) -> copy
    names.  A name of a single-copy chromosome (``chrX`` of a male) has no suffix."""
    if ploidy is not None and ploidy.get(name, 2) == 1:
        return name
    if name and name[-1] in "ab" and (ploidy is None or name[:-1] in ploidy):
        return copy_name(name[:-1], "ab".index(name[-1]))
    return name


def _open(path, mode="rt"):
    path = str(path)
    return gzip.open(path, mode) if path.endswith(".gz") else open(path, mode.replace("t", ""))


def _hap(x: str) -> int:
    return -1 if x in (".", "", "-1") else int(x)


class Phased:
    """Phased contacts, one per row, with the raw lines (so subsets are written back unchanged)."""

    def __init__(self, chrom_a, pos_a, hap_a, chrom_b, pos_b, hap_b, header=None, lines=None, phase_prob=None):
        self.chrom_a = np.asarray(chrom_a).astype(str)
        self.pos_a = np.asarray(pos_a, np.int64)
        self.hap_a = np.asarray(hap_a, np.int8)
        self.chrom_b = np.asarray(chrom_b).astype(str)
        self.pos_b = np.asarray(pos_b, np.int64)
        self.hap_b = np.asarray(hap_b, np.int8)
        self.header = list(header or [])
        self.lines = lines
        self.phase_prob = phase_prob

    def __len__(self):
        return len(self.pos_a)

    def subset(self, idx) -> "Phased":
        idx = np.asarray(idx)
        rows = np.flatnonzero(idx) if idx.dtype == bool else idx
        return Phased(self.chrom_a[rows], self.pos_a[rows], self.hap_a[rows], self.chrom_b[rows], self.pos_b[rows],
                      self.hap_b[rows], self.header, None if self.lines is None else [self.lines[i] for i in rows],
                      None if self.phase_prob is None else self.phase_prob[rows])

    @property
    def chroms(self):
        from contacts import sort_chroms
        return sort_chroms(np.concatenate([self.chrom_a, self.chrom_b]))


def read_phased(path) -> Phased:
    """hickit ``.pairs`` (columns from ``#columns:``) or Dip-C ``.con`` -> Phased (raw lines kept)."""
    path = str(path)
    name = path[:-3] if path.endswith(".gz") else path
    con = name.endswith((".con", ".con.txt"))
    header, lines, ca, pa, ha, cb, pb, hb, probs = [], [], [], [], [], [], [], [], []
    idx = None
    with _open(path) as fh:
        for line in fh:
            line = line.rstrip("\n")
            if not line.strip():
                continue
            if line.startswith("#"):
                header.append(line)
                if line.startswith("#columns:"):
                    idx = {c: k for k, c in enumerate(line.split()[1:])}
                continue
            r = line.split()
            if con:
                (c1, p1, h1), (c2, p2, h2) = r[0].split(","), r[1].split(",")
                ca.append(c1); pa.append(int(p1)); ha.append(_hap(h1))
                cb.append(c2); pb.append(int(p2)); hb.append(_hap(h2))
            else:
                if idx is None:
                    idx = {c: k for k, c in enumerate(["readID", "chr1", "pos1", "chr2", "pos2", "strand1", "strand2"])}
                ca.append(r[idx["chr1"]]); pa.append(int(r[idx["pos1"]]))
                cb.append(r[idx["chr2"]]); pb.append(int(r[idx["pos2"]]))
                ha.append(_hap(r[idx["phase0"]]) if "phase0" in idx else -1)
                hb.append(_hap(r[idx["phase1"]]) if "phase1" in idx else -1)
                if all(c in idx for c in PROB_COLS):
                    probs.append([float(r[idx[c]]) for c in PROB_COLS])
            lines.append(line)
    return Phased(ca, pa, ha, cb, pb, hb, header, lines, np.array(probs) if probs else None)


def write_phased(path, c: Phased, chrom_sizes: dict | None = None) -> int:
    """hickit-readable phased ``.pairs`` (``#chromosome:`` lines, strands ``.``)."""
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    h = lambda x: "." if x < 0 else str(int(x))  # noqa: E731
    with _open(path, "wt") as fh:
        fh.write("## pairs format v1.0\n#shape: upper triangle\n")
        for ch in c.chroms:
            if chrom_sizes and ch in chrom_sizes:
                fh.write(f"#chromosome: {ch} {int(chrom_sizes[ch])}\n")
        fh.write("#columns: readID chr1 pos1 chr2 pos2 strand1 strand2 phase0 phase1\n")
        import pandas as pd
        hs = lambda x: np.where(x < 0, ".", x.astype(str))  # noqa: E731
        pd.DataFrame({"r": np.char.add("r", np.arange(len(c)).astype(str)), "c1": c.chrom_a, "p1": c.pos_a,
                      "c2": c.chrom_b, "p2": c.pos_b, "s1": ".", "s2": ".", "h1": hs(c.hap_a), "h2": hs(c.hap_b)}
                     ).to_csv(fh, sep="\t", header=False, index=False)
    del h
    return len(c)


def write_phased_subset(path, c: Phased, idx) -> int:
    """Rows ``idx`` of ``c`` in its input format (header and raw lines unchanged)."""
    s = c.subset(idx)
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with _open(path, "wt") as fh:
        for line in s.header:
            fh.write(line + "\n")
        for line in s.lines:
            fh.write(line + "\n")
    return len(s)


def save_models(path, chrom, pos, coords, **extra) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(path, chrom=np.asarray(chrom).astype(str), pos=np.asarray(pos, np.int64),
                        coords=np.asarray(coords, np.float32 if np.asarray(coords).size > 5e7 else float), **extra)
