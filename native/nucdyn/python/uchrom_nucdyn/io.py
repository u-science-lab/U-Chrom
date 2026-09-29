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
