"""Contact readers (NCC as used by NucDynamics, and simple pair tables)."""

from __future__ import annotations

import gzip
from typing import Dict

import numpy as np


def _open(path: str):
    return gzip.open(path, "rt") if str(path).endswith((".gz", ".gzip")) else open(path)


def read_ncc(path: str) -> Dict[str, np.ndarray]:
    """Read an NCC file (NucProcess output) the way NucDynamics does.

    Contact position = fragment start on the + strand, fragment end on the -
    strand; a new ambiguity group starts at each row whose ambiguity code has
    an integer part > 0; rows whose code ends in ``.0`` are inactive.
    Returns arrays ``chrom_a, pos_a, chrom_b, pos_b, ambiguity, active``.
    """
    ca, pa, cb, pb, amb, act = [], [], [], [], [], []
    group = 0
    with _open(path) as fh:
        for line in fh:
            if line.startswith("#"):
                continue
            row = line.split()
            if len(row) < 13:
                continue
            code = row[12]
            if "." not in code:
                raise ValueError("old NCC format (ambiguity code without '.') is not supported")
            if int(float(code)) > 0:
                group += 1
            ca.append(row[0])
            pa.append(int(row[1] if row[5] == "+" else row[2]))
            cb.append(row[6])
            pb.append(int(row[7] if row[11] == "+" else row[8]))
            amb.append(group)
            act.append(not code.endswith(".0"))
    return {
        "chrom_a": np.array(ca, dtype=object),
        "pos_a": np.array(pa, dtype=np.int64),
        "chrom_b": np.array(cb, dtype=object),
        "pos_b": np.array(pb, dtype=np.int64),
        "ambiguity": np.array(amb, dtype=np.int64),
        "active": np.array(act, dtype=bool),
    }


def read_contact_pairs(path: str) -> Dict[str, np.ndarray]:
    """Read a whitespace table of contacts.

    Accepts the GEO contact-pair tables of Stevens et al. 2017
    (``chr_A pos_A chr_B pos_B``) and 4DN-style ``.pairs`` files
    (``readID chr1 pos1 chr2 pos2 ...``).  Every contact is unambiguous.
    """
    ca, pa, cb, pb = [], [], [], []
    with _open(path) as fh:
        for line in fh:
            if not line.strip() or line.startswith("#"):
                continue
            row = line.split()
            if row[1].lstrip("-").isdigit() and not row[2].lstrip("-").isdigit():
                c1, p1, c2, p2 = row[0], row[1], row[2], row[3]
            else:
                c1, p1, c2, p2 = row[1], row[2], row[3], row[4]
            ca.append(c1)
            pa.append(int(p1))
            cb.append(c2)
            pb.append(int(p2))
    n = len(ca)
    return {
        "chrom_a": np.array(ca, dtype=object),
        "pos_a": np.array(pa, dtype=np.int64),
        "chrom_b": np.array(cb, dtype=object),
        "pos_b": np.array(pb, dtype=np.int64),
        "ambiguity": np.arange(1, n + 1, dtype=np.int64),
        "active": np.ones(n, dtype=bool),
    }


_PHASE_COLS = ("phase0", "phase1")
_PROB_COLS = ("phase_prob00", "phase_prob01", "phase_prob10", "phase_prob11")


def _hap(x: str) -> int:
    return -1 if x in (".", "-1", "") else int(x)


def read_phased_contacts(path: str) -> Dict[str, np.ndarray]:
    """Read phased (homolog-resolved) single-cell contacts.

    Formats:

    * hickit / 4DN ``.pairs[.gz]`` with ``phase0`` / ``phase1`` columns named in the
      ``#columns:`` header (``0``, ``1`` or ``.`` = unknown), as written by ``hickit -o``
      (``contacts.pairs.gz``); an imputed file (``hickit -u``: ``impute.pairs.gz``) also has
      ``phase_prob00 .. phase_prob11``, returned as ``phase_prob`` (n, 4) - index
      2 hap_a + hap_b.  A ``.pairs`` file without phase columns gives unknown haplotypes.
    * Dip-C ``.con[.gz]`` / ``.con.txt.gz`` (GEO): one contact per line, two tab-separated
      legs ``chrom,pos,hap`` (hap ``0`` = paternal, ``1`` = maternal, ``.`` = unknown).

    Returns ``chrom_a, pos_a, chrom_b, pos_b, ambiguity, active`` (as
    :func:`read_contact_pairs`) plus ``hap_a, hap_b`` (int8: 0, 1, -1 = unknown) and, when
    present, ``phase_prob``.
    """
    path = str(path)
    name = path[:-3] if path.endswith(".gz") else path
    is_con = name.endswith((".con", ".con.txt"))
    ca, pa, cb, pb, ha, hb, probs = [], [], [], [], [], [], []
    cols = None
    idx = None
    has_phase = has_prob = False
    with _open(path) as fh:
        for line in fh:
            if not line.strip():
                continue
            if line.startswith("#"):
                if line.startswith("#columns:"):
                    cols = line[len("#columns:"):].split()
                continue
            row = line.split()
            if is_con:
                (c1, p1, h1), (c2, p2, h2) = row[0].split(","), row[1].split(",")
                ca.append(c1)
                pa.append(int(p1))
                ha.append(_hap(h1))
                cb.append(c2)
                pb.append(int(p2))
                hb.append(_hap(h2))
                continue
            if idx is None:
                if cols is None:
                    cols = ["readID", "chr1", "pos1", "chr2", "pos2", "strand1", "strand2"][: len(row)]
                idx = {c: k for k, c in enumerate(cols)}
                for need in ("chr1", "pos1", "chr2", "pos2"):
                    if need not in idx:
                        raise ValueError(f"{path}: no {need} column in the pairs header")
                has_phase = all(c in idx for c in _PHASE_COLS)
                has_prob = all(c in idx for c in _PROB_COLS)
            ca.append(row[idx["chr1"]])
            pa.append(int(row[idx["pos1"]]))
            cb.append(row[idx["chr2"]])
            pb.append(int(row[idx["pos2"]]))
            ha.append(_hap(row[idx["phase0"]]) if has_phase else -1)
            hb.append(_hap(row[idx["phase1"]]) if has_phase else -1)
            if has_prob:
                probs.append([float(row[idx[c]]) for c in _PROB_COLS])
    n = len(ca)
    out = {
        "chrom_a": np.array(ca, dtype=object),
        "pos_a": np.array(pa, dtype=np.int64),
        "chrom_b": np.array(cb, dtype=object),
        "pos_b": np.array(pb, dtype=np.int64),
        "ambiguity": np.arange(1, n + 1, dtype=np.int64),
        "active": np.ones(n, dtype=bool),
        "hap_a": np.array(ha, dtype=np.int8),
        "hap_b": np.array(hb, dtype=np.int8),
    }
    if probs:
        out["phase_prob"] = np.array(probs, dtype=np.float64).reshape(n, 4)
    return out
