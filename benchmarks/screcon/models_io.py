"""Model file converters -> the common ``.npz`` (``chrom``, ``pos``, ``coords`` (M, N, 3)).

``pos`` follows the NucDynamics 2017 convention: particle k covers (pos_k - size, pos_k].

* :func:`read_nucdyn_pdb` - PDB written by original NucDynamics ``export_pdb_coords``
  (also the GEO GSE80280 models).  Chain letters are assigned in the export's
  chromosome sort order (``chr`` stripped, numbers zero-padded, then string sort:
  chr1..chr19, then chrX for mouse), so the mapping is rebuilt from the chromosome
  names of the input table rather than hard-coded; the last column is the particle
  sequence position (2017 convention).
* :func:`read_sic_pdb` - Si-C ``genome.pdb`` (``cavity2pdb_chain.c``): one ``ATOM`` line
  per bead in the order of ``assignall<res>.dat`` (chromosome 1..n, bin 0..len/res),
  chain letter ``'a' + chromosome index`` (column 20), residue number = bin index + 1
  restarting per chromosome (columns 21-26), x/y/z in columns 31-54.  Si-C bin k covers [k res, (k+1) res), so the
  2017-convention ``pos`` is (k+1) res (a read exactly at a multiple of res falls one
  bead off - probability 1/res).  Beads without any contact (assign = -1) are linear
  interpolations made by ``smooth_contract_multichr.c``; they are flagged in
  ``interpolated``.
* :func:`read_3dg` - hickit / Dip-C ``.3dg`` (``chrom start x y z``); beads may be merged
  (variable length) - every bead covers [start_k, start_{k+1}); :func:`resample_3dg`
  puts them on a regular grid (a grid bin gets the bead covering its midpoint).
"""

from __future__ import annotations

import gzip
from pathlib import Path

import numpy as np

from contacts import chrom_key, sort_chroms


def _open(path):
    return gzip.open(path, "rt") if str(path).endswith(".gz") else open(path)


def nucdyn_chain_map(chroms) -> dict[str, str]:
    """Chain letter -> chromosome, as ``export_pdb_coords`` (nuc_dynamics master) assigns them."""
    keys = []
    for c in chroms:
        k = c[3:] if c[:3] == "chr" else c
        if k.isdigit():
            k = "%03d" % int(k)
        keys.append((k, c))
    keys.sort()
    return {chr(ord("a") + i): c for i, (_, c) in enumerate(keys)}


def read_nucdyn_pdb(path, chroms=None):
    """Extended NucDynamics PDB -> (chrom, pos, coords (M, N, 3)).  ``chroms``: the chromosome
    names of the input contacts (default: mouse chr1..19 + chrX, the GEO models)."""
    if chroms is None:
        chroms = [f"chr{i}" for i in range(1, 20)] + ["chrX"]
    cmap = nucdyn_chain_map(chroms)
    models, rows, keys = [], [], None
    with _open(path) as fh:
        for line in fh:
            if line.startswith("MODEL"):
                rows = []
            elif line.startswith("HETATM"):
                rows.append((cmap.get(line[21], line[21]), int(line.split()[-1]),
                             float(line[30:38]), float(line[38:46]), float(line[46:54])))
            elif line.startswith("ENDMDL"):
                k = [(r[0], r[1]) for r in rows]
                if keys is None:
                    keys = k
                if k != keys:
                    raise ValueError("models have different particles")
                models.append(np.array([r[2:] for r in rows]))
    chrom = np.array([k[0] for k in keys])
    pos = np.array([k[1] for k in keys], np.int64)
    return chrom, pos, np.stack(models)


def read_sic_pdb(path, chroms: list[str], res_bp: int):
    """Si-C ``genome.pdb`` -> (chrom, pos [2017 convention], coords (N, 3)).
    ``chroms``: chromosome names in Si-C's numbering order (index 0 = chain 'a')."""
    ch, rid, xyz = [], [], []
    with _open(path) as fh:
        for line in fh:
            if not line.startswith("ATOM"):
                continue
            ch.append(line[19]); rid.append(int(line[20:26]))
            xyz.append((float(line[30:38]), float(line[38:46]), float(line[46:54])))
    chrom = np.array([chroms[ord(c) - ord("a")] for c in ch])
    pos = np.array(rid, np.int64) * int(res_bp)
    return chrom, pos, np.array(xyz)


def read_3dg(path):
    """hickit ``.3dg`` -> (chrom, start, coords (N, 3))."""
    ch, st, xyz = [], [], []
    with _open(path) as fh:
        for line in fh:
            if line.startswith("#") or not line.strip():
                continue
            f = line.split()
            ch.append(f[0]); st.append(int(f[1])); xyz.append((float(f[2]), float(f[3]), float(f[4])))
    return np.array(ch), np.array(st, np.int64), np.array(xyz)


def resample_3dg(chrom, start, xyz, res: int, spans: dict | None = None):
    """Beads [start_k, start_{k+1}) -> regular grid of ``res`` (2017 ``pos`` = bin end).
    The grid runs from the first bead's bin to the last bead's bin of each chromosome,
    clipped to ``spans[chrom] = (lo, hi)`` (e.g. the span of the input contacts: hickit's
    first bead starts at 0 and absorbs the contact-free chromosome start)."""
    out_c, out_p, out_x = [], [], []
    for c in sort_chroms(chrom):
        sel = np.flatnonzero(chrom == c)
        o = sel[np.argsort(start[sel], kind="stable")]
        s = start[o]
        k0, k1 = s[0] // res, s[-1] // res
        if spans and c in spans:
            k0, k1 = max(k0, spans[c][0] // res), min(k1, spans[c][1] // res)
        bins = np.arange(k0, k1 + 1)
        mid = bins * res + res // 2
        j = np.clip(np.searchsorted(s, mid, side="right") - 1, 0, len(s) - 1)
        out_c.append(np.full(len(bins), c, dtype=object)); out_p.append((bins + 1) * res); out_x.append(xyz[o[j]])
    return np.concatenate(out_c).astype(str), np.concatenate(out_p).astype(np.int64), np.concatenate(out_x)


def save_npz(path, chrom, pos, coords, **extra) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    coords = np.asarray(coords, float)
    if coords.ndim == 2:
        coords = coords[None]
    np.savez_compressed(path, chrom=np.asarray(chrom).astype(str), pos=np.asarray(pos, np.int64), coords=coords,
                        **extra)


def common_particles(sets):
    """Intersect particle sets [(chrom, pos, X), ...] -> list with only the shared particles, same order."""
    keys = None
    for chrom, pos, _ in sets:
        k = set(zip(chrom.tolist(), pos.tolist()))
        keys = k if keys is None else keys & k
    order = sorted(keys, key=lambda t: (chrom_key(t[0]), t[1]))
    out = []
    for chrom, pos, X in sets:
        idx = {k: i for i, k in enumerate(zip(chrom.tolist(), pos.tolist()))}
        ii = np.array([idx[k] for k in order], np.int64)
        out.append((chrom[ii], pos[ii], X[..., ii, :]))
    return out
