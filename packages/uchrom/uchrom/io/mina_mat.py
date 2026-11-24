"""Chromatin traces of the Siyuan Wang lab's MATLAB analysis (MINA / DNA-MERFISH / sequential tracing).

The lab's pipeline saves its traces as MATLAB structs (``.mat``, version 7.3 = HDF5; Cheng et al. 2026, *Science*
393:eadw4243, Zenodo 19959235).  Two layouts:

* **one element per cell** (``ChrFOV`` / ``ChrFOVNew``; genome-wide DNA-MERFISH): ``CellID`` (the cell's label in its
  field of view), ``FOVid``, ``TraceNum`` and ``Traces``, a cell array with one entry per chromosome (``ChrID`` 1..23,
  X = 23): empty, one trace (a struct) or several (a struct array, one per imaged copy), each with ``r`` (1 =
  locus detected), ``x``, ``y``, ``z`` (µm, the field of view's frame; 0 when not detected) over the chromosome's
  loci; optional per-cell fields (``seurat_midgroup``, ``CellType``, ``CellLableAssign``);
* **one element per trace** (``ChrAll``; sequential tracing of one region): ``CellID``, ``FOV``, ``r``, ``x``,
  ``y``, ``z`` over the region's loci and per-trace fields (``CellLableAssign``, ``CellLableValues``, ``rg``,
  ``Center``).

The files hold no genomic coordinates: the caller gives the loci (``loci``).  Undetected loci are left out.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Sequence

import numpy as np
import pandas as pd

__all__ = ["read_mina_mat", "mat_struct"]


def _value(f, obj):
    """A MATLAB v7.3 value: char -> str, numeric -> ndarray (MATLAB's shape), cell -> list, struct -> dict
    (a struct array -> list of dicts), empty -> None."""
    import h5py

    if isinstance(obj, h5py.Reference):
        obj = f[obj]
    cls = obj.attrs.get("MATLAB_class", b"")
    cls = cls.decode() if isinstance(cls, bytes) else str(cls)
    if isinstance(obj, h5py.Group):
        return mat_struct(f, obj)
    if obj.attrs.get("MATLAB_empty", 0):
        return None
    data = obj[()]
    if obj.dtype == h5py.ref_dtype:
        return [_value(f, r) for r in np.asarray(data).ravel(order="F")]
    if cls == "char":
        return "".join(map(chr, np.asarray(data).ravel(order="F")))
    return np.asarray(data).T


def mat_struct(f, group):
    """A MATLAB struct (an HDF5 group): a dict for a single struct, a list of dicts for a struct array (its fields
    are datasets of references without a MATLAB class)."""
    import h5py

    keys = [k for k in group.keys()]
    if not keys:
        return {}
    first = group[keys[0]]
    array = (isinstance(first, h5py.Dataset) and first.dtype == h5py.ref_dtype
             and "MATLAB_class" not in first.attrs)
    if not array:
        return {k: _value(f, group[k]) for k in keys}
    refs = {k: np.asarray(group[k][()]).ravel(order="F") for k in keys}
    n = len(refs[keys[0]])
    return [{k: _value(f, refs[k][i]) for k in keys} for i in range(n)]


def _scalar(v):
    if v is None:
        return np.nan
    if isinstance(v, str):
        return v
    a = np.asarray(v).ravel()
    return a[0].item() if a.size == 1 else (np.nan if a.size == 0 else a)


def _detected(t: dict, n_loci: int, where: str):
    r = np.asarray(t["r"], float).ravel()
    xyz = np.stack([np.asarray(t[c], float).ravel() for c in ("x", "y", "z")], axis=1)
    if len(r) != n_loci or len(xyz) != n_loci:
        raise ValueError(f"{where}: {len(r)} loci in the trace, {n_loci} in the locus table")
    keep = np.flatnonzero((r == 1) & np.isfinite(xyz).all(1) & (xyz != 0).any(1))
    return keep, xyz[keep]


def read_mina_mat(
    paths,
    loci: pd.DataFrame,
    *,
    cell_prefix: str = "",
    cell_fields: Sequence[str] = ("seurat_midgroup", "CellType", "CellLableAssign"),
    trace_fields: Sequence[str] = ("CellLableAssign", "rg"),
    replicates_by_fov_order: bool = False,
    genome_assembly: str = "hg38",
    source: Optional[str] = None,
):
    """Read Wang-lab MATLAB traces (module docstring) into a ``ChromData`` (coordinates in µm).

    Parameters
    ----------
    paths : path or list of paths
        ``.mat`` files of one layout (one ``ChrFOV*`` / ``ChrAll`` struct each); a list is read in order and
        concatenated (e.g. the 64 per-FOV files of one tonsil section).
    loci : DataFrame or list of DataFrames
        ``chrom``, ``start``, ``end`` of the loci in the order of the traces' ``r`` / ``x`` vectors.  For the
        per-cell layout also ``chrom_id`` (the ``Traces`` entry, 1-based): the rows of one ``chrom_id`` in
        locus order.  A list gives each file its own loci (e.g. two regions traced in the same cells).
    cell_prefix : str
        Put before every cell id: ``"<prefix><FOV>_<CellID>"``.  Traces are ``"<cell>_<chrom>_<k>"`` (per-cell
        layout, k = copy) or ``"<prefix>t<n>"`` (per-trace layout, n = element).
    cell_fields, trace_fields : names
        Scalar fields copied to ``cells`` (per-cell layout) or ``traces`` (per-trace layout) when present
        (``seurat_midgroup`` -> ``cell_type``; others keep their names).  ``CellLableValues`` and ``Center`` of the
        per-trace layout go to ``traces`` as ``label_value_<i>`` / ``center_x`` / ``center_y``.
    replicates_by_fov_order : bool
        Per-trace layout: the file concatenates experiments whose fields of view are each numbered from 0 (the
        lab's merged ``ChrAll`` of two replicates); a new experiment starts wherever the FOV number decreases.  The
        cells become ``"<prefix>r<rep>_<FOV>_<CellID>"`` with ``cells["replicate"]`` (1, 2, ...).

    Returns
    -------
    ChromData
        ``cells``: ``fov``, ``cell_label`` (the file's ``CellID``), ``n_traces``, the fields; ``traces``:
        ``cell_id``, ``chrom`` (per-cell layout: ``copy``), the fields; ``uns``: ``genome_assembly``,
        ``xyz_unit`` = ``micron``.
    """
    import h5py
    from chromdata import ChromData
    from chromdata.bins import bins_from_loci

    paths = [Path(p) for p in ([paths] if isinstance(paths, (str, Path)) else paths)]
    per_path = isinstance(loci, (list, tuple))
    tables = [t.reset_index(drop=True) for t in (loci if per_path else [loci] * len(paths))]
    if len(tables) != len(paths):
        raise ValueError(f"{len(tables)} locus tables for {len(paths)} files")
    allloci = pd.concat(tables, ignore_index=True)[["chrom", "start", "end"]]
    bins, all_bin = bins_from_loci(allloci)
    offsets = np.cumsum([0] + [len(t) for t in tables])
    coords, spot_bin, spot_trace, trace_rows, cell_rows = [], [], [], [], {}
    for pi, path in enumerate(paths):
        loci, locus_bin = tables[pi], all_bin[offsets[pi]:offsets[pi + 1]]
        per_cell = "chrom_id" in loci.columns
        if per_cell:
            by_chrom = {int(c): np.flatnonzero(loci["chrom_id"].to_numpy() == c) for c in loci["chrom_id"].unique()}
        rep, last_fov = 1, None                          # experiments are numbered within each file
        with h5py.File(path, "r") as f:
            names = [k for k in f.keys() if not k.startswith("#")]
            if len(names) != 1:
                raise ValueError(f"{path.name}: expected one struct, found {names}")
            elems = mat_struct(f, f[names[0]])
            elems = [elems] if isinstance(elems, dict) else elems
            for n, e in enumerate(elems):
                fov = int(_scalar(e.get("FOVid", e.get("FOV"))))
                if replicates_by_fov_order and not per_cell:
                    if last_fov is not None and fov < last_fov:
                        rep += 1
                    last_fov = fov
                    cell = f"{cell_prefix}r{rep}_{fov}_{int(_scalar(e['CellID']))}"
                else:
                    cell = f"{cell_prefix}{fov}_{int(_scalar(e['CellID']))}"
                if per_cell:
                    row = cell_rows.setdefault(cell, {"cell_id": cell, "fov": fov,
                                                      "cell_label": int(_scalar(e["CellID"])), "n_traces": 0})
                    for k in cell_fields:
                        if k in e:
                            row["cell_type" if k == "seurat_midgroup" else k] = _scalar(e[k])
                    for ci, entry in enumerate(e["Traces"] or [], start=1):
                        if entry is None:
                            continue
                        idx = by_chrom.get(ci)
                        if idx is None:
                            raise ValueError(f"{path.name}: chromosome entry {ci} has no loci in the table")
                        for k, t in enumerate([entry] if isinstance(entry, dict) else entry, start=1):
                            keep, xyz = _detected(t, len(idx), f"{path.name} cell {cell} chromosome {ci}")
                            if not len(keep):
                                continue
                            chrom = str(loci.loc[idx[0], "chrom"])
                            tid = f"{cell}_{chrom}_{k}"
                            trace_rows.append({"trace_id": tid, "cell_id": cell, "chrom": chrom, "copy": k})
                            coords.append(xyz)
                            spot_bin.append(locus_bin[idx[keep]])
                            spot_trace.append(np.full(len(keep), len(trace_rows) - 1))
                            row["n_traces"] += 1
                else:
                    crow = cell_rows.setdefault(cell, {"cell_id": cell, "fov": fov,
                                                       "cell_label": int(_scalar(e["CellID"])), "n_traces": 0})
                    if replicates_by_fov_order:
                        crow["replicate"] = rep
                    keep, xyz = _detected(e, len(loci), f"{path.name} element {n}")
                    if not len(keep):
                        continue
                    tid = f"{cell_prefix}t{len(trace_rows)}"
                    row = {"trace_id": tid, "cell_id": cell, "chrom": str(loci.loc[keep[0], "chrom"])}
                    for k in trace_fields:
                        if k in e:
                            row[k] = _scalar(e[k])
                    vals = e.get("CellLableValues")
                    if vals is not None:
                        for i, v in enumerate(np.asarray(vals, float).ravel(), start=1):
                            row[f"label_value_{i}"] = v
                    if e.get("Center") is not None:
                        c = np.asarray(e["Center"], float).ravel()
                        row["center_x"], row["center_y"] = c[0], c[1]
                    trace_rows.append(row)
                    cell_rows[cell]["n_traces"] += 1
                    coords.append(xyz)
                    spot_bin.append(locus_bin[keep])
                    spot_trace.append(np.full(len(keep), len(trace_rows) - 1))
    traces = pd.DataFrame(trace_rows).set_index("trace_id")
    cells = pd.DataFrame(list(cell_rows.values())).set_index("cell_id")
    tidx = np.concatenate(spot_trace) if spot_trace else np.zeros(0, int)
    spots = pd.DataFrame({"trace_id": traces.index.to_numpy()[tidx],
                          "cell_id": traces["cell_id"].to_numpy()[tidx],
                          "bin_id": np.concatenate(spot_bin) if spot_bin else np.zeros(0, int)})
    xyz = np.concatenate(coords) if coords else np.zeros((0, 3))
    return ChromData(coords=xyz, spots=spots, bins=bins, cells=cells, traces=traces,
                     uns={"genome_assembly": genome_assembly, "xyz_unit": "micron",
                          "source": source or ", ".join(p.name for p in paths[:3])})
