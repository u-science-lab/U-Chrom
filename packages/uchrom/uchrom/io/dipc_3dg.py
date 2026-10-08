"""Single-cell 3-D genome structures in the ``.3dg`` text layout of Dip-C and hickit, as ``ChromData``.

A ``.3dg`` file is one structure of one cell: a tab-separated line per particle, ``chromosome  position  x
y  z`` (hickit adds a sixth column), ``#`` lines are comments.  The two programs differ in how a diploid
cell's homologs are named and in what the position of a particle means:

* **Dip-C** (Tan et al. 2018, *Science* 361:924; its NucDynamics-based ``nuc_dynamics`` + ``dip-c clean3``):
  homologs as ``1(pat)`` / ``1(mat)``, chromosomes without ``chr``; a particle at position ``p`` holds the
  contacts in ``(p - size, p]`` (the NucDynamics convention, Stevens et al. 2017, *Nature* 544:59).  Checked
  on Tan 2018 GM12878 cell 1: the contacts of its ``impute3.round4.con`` file (both legs on one homolog, more
  than 100 kb apart) are 1.5 particle radii apart (median) when each leg is given the particle at the next
  multiple of 20 kb, 2.6 with the previous multiple; and phase ``0`` of that file is ``(pat)``.
* **hickit** (Li Heng; used by Tan 2021, Wu 2025, HiRES): ``#chromosome: 1a 249250621`` header lines,
  homologs as ``1a`` / ``1b`` (the phase-0 / phase-1 haplotypes of the phased variants: paternal / maternal
  for the GM12878 data), a particle at ``p`` holds ``[p, p + size)`` (the same check on the hickit pairs and
  20 kb structure of that cell: 0.079 vs 0.131 by the next multiple).  hickit puts a particle at position 0
  of a chromosome when the first bins have no contacts (it stands for that stretch); it is read as the bin
  ``[0, size)``.

:func:`read_3dg_structure` reads one file into a table of particles with their genomic interval;
:func:`read_3dg_cells` makes a ``ChromData`` of several cells (one trace per cell, chromosome and homolog),
with more runs of the same cells (Dip-C's replicate structures) as ``layers`` aligned to the particles of
the main run; :func:`replicate_deviation` measures how far those runs are from the main one after
superposition (Tan et al. 2018 judged the structures by this RMSD).
"""

from __future__ import annotations

import gzip
import io
import os
import re
from pathlib import Path
from typing import Dict, Mapping, Optional, Sequence, Tuple, Union

import numpy as np
import pandas as pd

PathLike = Union[str, os.PathLike]

_DIPC_NAME = re.compile(r"^(?P<chrom>[^()\s]+)\((?P<hap>[^()\s]+)\)$")


def _read_text(path: PathLike) -> str:
    path = str(path)
    if path.endswith(".gz"):
        with gzip.open(path, "rt") as fh:
            return fh.read()
    with open(path) as fh:
        return fh.read()


def _layout(text: str, names: np.ndarray) -> Tuple[str, Dict[str, Tuple[str, Optional[str]]]]:
    """``(format, {file name: (chromosome, homolog or None)})``; format ``"dipc"``, ``"hickit"`` or ``"plain"``."""
    uniq = list(pd.unique(names))
    if all(_DIPC_NAME.match(n) for n in uniq):
        return "dipc", {n: (_DIPC_NAME.match(n)["chrom"], _DIPC_NAME.match(n)["hap"]) for n in uniq}
    declared = re.findall(r"^#chromosome:\s*(\S+)", text, flags=re.M)
    if declared:
        listed = set(declared) | set(uniq)
        out = {}
        for n in uniq:
            stem, last = n[:-1], n[-1:]
            other = {"a": "b", "b": "a"}.get(last)
            out[n] = (stem, last) if other is not None and stem and stem + other in listed else (n, None)
        return "hickit", out
    return "plain", {n: (n, None) for n in uniq}


def _mode_spacing(positions: np.ndarray, groups: np.ndarray) -> int:
    order = np.lexsort((positions, groups))
    p, g = positions[order], groups[order]
    d = np.diff(p)[g[1:] == g[:-1]]
    d = d[d > 0]
    if not len(d):
        raise ValueError("cannot infer the particle size (no two particles on one chromosome copy); "
                         "give particle_size=")
    values, counts = np.unique(d, return_counts=True)
    return int(values[np.argmax(counts)])


def read_3dg_structure(path: PathLike, *, particle_size: Optional[int] = None, particle_position: str = "auto",
                       hap_names: Sequence[str] = ("pat", "mat"), chr_prefix: Union[str, bool] = "auto"
                       ) -> pd.DataFrame:
    """One single-cell structure in the ``.3dg`` layout (Dip-C or hickit) as a table of particles.

    Parameters
    ----------
    path
        A ``.3dg`` file, plain or gzipped (Dip-C ``*.3dg.txt.gz`` / hickit ``*.3dg.gz``).
    particle_size
        Bin size of the particles (bp).  ``None``: the most common distance between consecutive particles of
        a chromosome copy (20 kb for the Tan 2018 structures).
    particle_position
        What a particle's position is: ``"end"`` (it holds ``(p - size, p]``: Dip-C / NucDynamics),
        ``"start"`` (``[p, p + size)``: hickit), ``"mid"`` (``[p - size/2, p + size/2)``) or ``"auto"`` (by the
        layout: Dip-C names → ``"end"``, hickit or plain names → ``"start"``; see the module docstring).
    hap_names
        Names of hickit's ``a`` / ``b`` homologs (default ``("pat", "mat")``, as Dip-C names them; ``a`` is
        the phase-0 haplotype of the phased variants).  Dip-C names are kept as written.
    chr_prefix
        Prefix ``chr`` to chromosome names without it (``"auto"`` / ``True``; ``False``: keep the names).

    Returns
    -------
    DataFrame
        One row per particle in file order: ``chrom``, ``start``, ``end`` (the particle's interval, bp,
        ``start`` clipped at 0), ``homolog`` (``None`` for a chromosome without homolog suffix), ``position``
        (as in the file), ``x``, ``y``, ``z`` (the file's unit: particle radii for Dip-C, hickit's own
        scale).  With ``particle_position="end"`` a particle at position 0 (it would hold ``(-size, 0]``, i.e.
        nothing: Dip-C starts some chains there) is left out.  ``attrs`` holds ``format``,
        ``particle_size``, ``particle_position`` and ``n_dropped_before_start``.
    """
    text = _read_text(path)
    table = pd.read_csv(io.StringIO(text), sep=r"\s+", comment="#", header=None, dtype={0: str})
    if table.shape[1] < 5:
        raise ValueError(f"{path}: a .3dg line has at least 5 columns (chromosome, position, x, y, z)")
    names = table[0].astype(str).to_numpy()
    fmt, parsed = _layout(text, names)
    chrom = np.array([parsed[n][0] for n in names], dtype=object)
    hap = np.array([parsed[n][1] for n in names], dtype=object)
    if fmt == "hickit":
        letters = {"a": hap_names[0], "b": hap_names[1]}
        hap = np.array([letters.get(h) if h is not None else None for h in hap], dtype=object)
    if chr_prefix in ("auto", True):
        chrom = np.array([c if c.lower().startswith("chr") else f"chr{c}" for c in chrom], dtype=object)
    position = table[1].to_numpy(np.int64)
    size = int(particle_size) if particle_size is not None else _mode_spacing(position, names)
    if particle_position == "auto":
        particle_position = "end" if fmt == "dipc" else "start"
    if particle_position == "end":
        start = position - size
    elif particle_position == "start":
        start = position.copy()
    elif particle_position == "mid":
        start = position - size // 2
    else:
        raise ValueError("particle_position must be 'auto', 'start', 'end' or 'mid'")
    # an "end" particle at position 0 would hold (-size, 0]: no contacts (NucDynamics starts a chain at
    # the multiple of the size below its first contact); it is left out
    keep = start >= 0 if particle_position == "end" else np.ones(len(start), bool)
    start = np.maximum(start, 0)
    out = pd.DataFrame({"chrom": chrom.astype(str), "start": start, "end": start + size,
                        "homolog": hap, "position": position,
                        "x": table[2].to_numpy(np.float64), "y": table[3].to_numpy(np.float64),
                        "z": table[4].to_numpy(np.float64)})
    out = out[keep].reset_index(drop=True)
    out.attrs.update(format=fmt, particle_size=size, particle_position=particle_position,
                     n_dropped_before_start=int((~keep).sum()))
    return out


def _trace_name(cell: str, chrom: str, hap) -> str:
    return f"{cell}_{chrom}" if hap is None or (isinstance(hap, float) and np.isnan(hap)) else f"{cell}_{chrom}_{hap}"


def _chrom_key(c: str):
    s = c[3:] if c.lower().startswith("chr") else c
    return (0, int(s), "") if s.isdigit() else (1, 0, s)


def read_3dg_cells(files: Mapping[str, PathLike], *, layers: Optional[Mapping[str, Mapping[str, PathLike]]] = None,
                   cells: Optional[pd.DataFrame] = None, uns: Optional[dict] = None, **read_kw):
    """Several cells' ``.3dg`` structures as one ``ChromData``: a trace per cell, chromosome and homolog.

    Parameters
    ----------
    files
        ``{cell id: .3dg path}`` (the main structure of each cell).
    layers
        More runs of the same cells, ``{layer name: {cell id: path}}`` (e.g. Dip-C's ``rep1`` / ``rep2``):
        stored as ``cd.layers[name]`` on the particles of the main run — NaN where a run lacks a particle;
        particles only in a layer run are left out (counted in ``uns["structures"]["layers"]``).  Each run
        has its own frame (no superposition here; see :func:`replicate_deviation`).
    cells
        Cell metadata indexed by cell id (default: just the ids of ``files``).
    uns
        Extra ``uns`` entries.
    **read_kw
        For :func:`read_3dg_structure` (``particle_size``, ``particle_position``, ``hap_names``, ...).

    Returns
    -------
    ChromData
        ``spots``: ``chrom, start, end, trace_id, cell_id`` sorted by cell, chromosome (genome order),
        homolog and position; trace ids ``<cell>_<chrom>_<homolog>`` (``<cell>_<chrom>`` without homolog);
        ``traces`` (index trace id): ``cell_id, chrom, homolog, n_particles``; ``cells`` gains
        ``n_particles`` and ``n_traces``; ``uns["structures"]``: format, particle size and position
        convention (``particle_position``: the meaning of the file positions; the loci are the particles'
        intervals), per-layer counts; ``uns["xyz_unit"]``.
    """
    from chromdata import ChromData

    parts, meta = [], None
    for cell, path in files.items():
        t = read_3dg_structure(path, **read_kw)
        if meta is None:
            meta = dict(t.attrs)
        elif (t.attrs["particle_size"], t.attrs["format"]) != (meta["particle_size"], meta["format"]):
            raise ValueError(f"{path}: {t.attrs['format']} particles of {t.attrs['particle_size']} bp, the first "
                             f"file has {meta['format']} particles of {meta['particle_size']} bp")
        parts.append(t.assign(cell_id=str(cell)))
    if not parts:
        raise ValueError("no structure files")
    df = pd.concat(parts, ignore_index=True)
    hap = df["homolog"].astype(object)
    df["trace_id"] = [_trace_name(c, ch, h) for c, ch, h in zip(df["cell_id"], df["chrom"], hap)]
    cell_order = {c: i for i, c in enumerate(map(str, files))}
    chrom_rank = {c: i for i, c in enumerate(sorted(df["chrom"].unique(), key=_chrom_key))}
    hap_rank = {h: i for i, h in enumerate(pd.unique(hap.fillna("")))}
    order = np.lexsort((df["start"].to_numpy(), hap.fillna("").map(hap_rank).to_numpy(),
                        df["chrom"].map(chrom_rank).to_numpy(), df["cell_id"].map(cell_order).to_numpy()))
    df = df.iloc[order].reset_index(drop=True)
    if df.duplicated(["trace_id", "start"]).any():
        raise ValueError("two particles of one chromosome copy at the same position")

    key = pd.MultiIndex.from_arrays([df["trace_id"], df["start"]])
    layer_arrays, layer_info = {}, {}
    for name, runs in (layers or {}).items():
        arr = np.full((len(df), 3), np.nan)
        n_in, n_extra = 0, 0
        for cell, path in runs.items():
            if str(cell) not in cell_order:
                raise KeyError(f"layer {name!r}: cell {cell!r} has no main structure")
            t = read_3dg_structure(path, **read_kw)
            if t.attrs["particle_size"] != meta["particle_size"]:
                raise ValueError(f"{path}: particles of {t.attrs['particle_size']} bp, the main run has "
                                 f"{meta['particle_size']} bp")
            tid = [_trace_name(str(cell), ch, h) for ch, h in zip(t["chrom"], t["homolog"].astype(object))]
            rows = key.get_indexer(pd.MultiIndex.from_arrays([tid, t["start"]]))
            ok = rows >= 0
            arr[rows[ok]] = t.loc[ok, ["x", "y", "z"]].to_numpy()
            n_in += int(ok.sum())
            n_extra += int((~ok).sum())
        layer_arrays[name] = arr
        layer_info[name] = {"cells": [str(c) for c in runs], "particles_on_main": n_in,
                            "particles_not_in_main_run": n_extra,
                            "main_particles_missing": int(np.isnan(arr[:, 0]).sum())}

    tr = (df.groupby("trace_id", sort=False)
          .agg(cell_id=("cell_id", "first"), chrom=("chrom", "first"), homolog=("homolog", "first"),
               n_particles=("start", "size")))
    tr.index.name = "trace_id"
    if cells is None:
        cells = pd.DataFrame(index=pd.Index([str(c) for c in files], name="cell_id"))
    cells = cells.copy()
    cells["n_particles"] = df.groupby("cell_id").size().reindex(cells.index).fillna(0).astype(np.int64)
    cells["n_traces"] = tr.groupby("cell_id").size().reindex(cells.index).fillna(0).astype(np.int64)
    info = {"format": meta["format"], "particle_size": int(meta["particle_size"]),
            "particle_position": meta["particle_position"],
            "loci": "each particle's genomic interval (see particle_position)", "layers": layer_info}
    unit = "particle radius" if meta["format"] == "dipc" else "hickit units"
    spots = df[["chrom", "start", "end", "trace_id", "cell_id"]].assign(      # bins in genome order
        chrom=pd.Categorical(df["chrom"], categories=sorted(chrom_rank, key=chrom_rank.get)))
    return ChromData(df[["x", "y", "z"]].to_numpy(), spots, cells=cells, traces=tr, layers=layer_arrays,
                     uns={"xyz_unit": unit, "structures": info, **(uns or {})})


def _superpose(mov: np.ndarray, ref: np.ndarray, reflection: bool) -> np.ndarray:
    """``mov`` superposed onto ``ref`` (optimal rotation [+ reflection] and translation; Kabsch 1976) over the
    rows finite in both; rows of ``mov`` with NaN stay NaN."""
    ok = np.isfinite(mov).all(1) & np.isfinite(ref).all(1)
    a, b = mov[ok], ref[ok]
    ca, cb = a.mean(0), b.mean(0)
    u, _, vt = np.linalg.svd((a - ca).T @ (b - cb))
    best = None
    for d in ((1.0, -1.0) if reflection else (float(np.sign(np.linalg.det(u @ vt))) or 1.0,)):
        rot = u @ np.diag([1.0, 1.0, d]) @ vt
        err = float((((a - ca) @ rot - (b - cb)) ** 2).sum())
        if best is None or err < best[0]:
            best = (err, rot)
    return (mov - ca) @ best[1] + cb


def replicate_deviation(cd, layers: Sequence[str] = ("rep1", "rep2"), *, reflection: bool = True
                        ) -> Tuple[pd.DataFrame, np.ndarray]:
    """How far other runs of the same cells (``cd.layers``) are from ``cd.coords``, after superposition.

    Each layer is superposed on the main structure cell by cell (one rigid motion for all of a cell's
    particles, all homologs; mirror images allowed with ``reflection``, since contacts do not fix the
    handedness) and the deviations of the particles measured — the replicate RMSD by which Tan et al. 2018
    (*Science* 361:924) judged their Dip-C structures.

    Parameters
    ----------
    cd
        Structures with the runs as layers (:func:`read_3dg_cells`).
    layers
        Layer names.
    reflection
        Allow an improper rotation.

    Returns
    -------
    per_cell : DataFrame
        Indexed by cell: ``rmsd_<layer>`` (RMSD over the particles of both), ``median_dev_<layer>`` (median
        particle deviation) for every layer, and ``mirrored_<layer>`` (the mirror image fitted better).
    per_spot : ndarray (n_spots,)
        Root mean square over the layers of each particle's deviation (NaN without any layer value).
    """
    xyz = np.asarray(cd.coords, dtype=np.float64)
    cell_of = cd.spots["cell_id"].astype(str).to_numpy()
    sq = np.zeros(len(xyz))
    n = np.zeros(len(xyz))
    rows = []
    for cell in pd.unique(cell_of):
        idx = np.flatnonzero(cell_of == cell)
        rec = {"cell_id": cell}
        for name in layers:
            lay = np.asarray(cd.layers[name], dtype=np.float64)[idx]
            if not np.isfinite(lay).all(1).any():
                rec.update({f"rmsd_{name}": np.nan, f"median_dev_{name}": np.nan, f"mirrored_{name}": False})
                continue
            fitted = _superpose(lay, xyz[idx], reflection)
            proper = _superpose(lay, xyz[idx], False)
            dev = np.linalg.norm(fitted - xyz[idx], axis=1)
            dev_proper = np.linalg.norm(proper - xyz[idx], axis=1)
            ok = np.isfinite(dev)
            rec[f"rmsd_{name}"] = float(np.sqrt(np.mean(dev[ok] ** 2)))
            rec[f"median_dev_{name}"] = float(np.median(dev[ok]))
            rec[f"mirrored_{name}"] = bool(np.mean(dev[ok] ** 2) < np.mean(dev_proper[ok] ** 2) - 1e-12)
            sq[idx[ok]] += dev[ok] ** 2
            n[idx[ok]] += 1
        rows.append(rec)
    with np.errstate(invalid="ignore", divide="ignore"):
        per_spot = np.where(n > 0, np.sqrt(sq / np.maximum(n, 1)), np.nan)
    return pd.DataFrame(rows).set_index("cell_id"), per_spot


__all__ = ["read_3dg_cells", "read_3dg_structure", "replicate_deviation"]
