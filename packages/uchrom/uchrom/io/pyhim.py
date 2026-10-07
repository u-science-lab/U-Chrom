"""PyHiM chromatin-trace tables (Astropy ECSV): the writer, counterpart of
:meth:`chromdata.ChromData.from_pyhim_trace`."""

from __future__ import annotations

from pathlib import Path
from typing import Mapping, Optional, Sequence, Union

import numpy as np
import pandas as pd

#: PyHiM's trace-table columns, in its order
PYHIM_COLUMNS = ("Spot_ID", "Trace_ID", "x", "y", "z", "Chrom", "Chrom_Start", "Chrom_End", "ROI #", "Mask_id",
                 "Barcode #", "label")

#: unit -> (multiply, divide) to get micron (nm: x / 1000, the same floats as dividing by hand)
_TO_MICRON = {"nm": (1.0, 1000.0), "nanometer": (1.0, 1000.0), "um": (1.0, 1.0), "micron": (1.0, 1.0),
              "µm": (1.0, 1.0), "micrometer": (1.0, 1.0), "mm": (1000.0, 1.0)}


def _ints_or_str(values: pd.Series) -> np.ndarray:
    s = values.astype(str)
    try:
        as_int = s.astype(np.int64)
    except (TypeError, ValueError):
        return s.to_numpy()
    return as_int.to_numpy() if (as_int.astype(str) == s).all() else s.to_numpy()


def write_pyhim_trace(
    cd,
    path,
    *,
    comments: Union[None, Sequence[str], Mapping[str, object]] = None,
    loci: bool = True,
    overwrite: bool = True,
) -> Path:
    """Write a ``ChromData`` as a PyHiM chromatin-trace table (Astropy ECSV; needs ``astropy``).

    PyHiM (Devos et al. 2024, *Genome Biology*) writes one row per spot with the columns
    ``Spot_ID, Trace_ID, x, y, z, Chrom, Chrom_Start, Chrom_End, ROI #, Mask_id, Barcode #, label`` and
    ``key=value`` strings in ``meta['comments']``; :meth:`ChromData.from_pyhim_trace` reads it back.

    Column mapping (the inverse of the reader's):

    - ``x, y, z``: ``coords`` in µm (PyHiM's unit), converted from ``uns['xyz_unit']`` (nm, µm);
    - ``Chrom, Chrom_Start, Chrom_End``: the spot loci (``loci=False`` leaves them empty / 0, as PyHiM
      writes them without a barcode -> genome map; read such a file with ``barcode_dict=``);
    - ``Trace_ID``: ``trace_id``; ``Mask_id``: ``cell_id`` (integers when every id is one; 0 without cells);
    - ``Barcode #``: spot column ``barcode``, else the locus number within its chromosome (1 = the first
      bin of the chromosome in ``bins``);
    - ``Spot_ID``: spot column ``spot_id``, else ``"<trace_id>_<barcode>"``;
    - ``ROI #``: spot column ``roi_id``, else 0; ``label``: spot column ``label``, else ``"None"``.

    Spots with NaN coordinates are written as NaN rows.

    Parameters
    ----------
    cd : ChromData
    path : path of the ``.ecsv`` file
    comments : list of str or dict, optional
        More ``meta['comments']`` (``"key=value"`` strings, or a dict); ``xyz_unit=micron`` and
        ``genome_assembly=`` (from ``uns``) come first.
    loci : bool
        Write the genomic columns (default) or leave them empty.
    overwrite : bool
        Replace an existing file.

    Returns
    -------
    Path of the written file.
    """
    try:
        from astropy.table import Table
    except ImportError as e:                      # pragma: no cover - optional dependency
        raise ImportError("write_pyhim_trace needs astropy (pip install astropy, or u-chrom[im])") from e

    unit = str(cd.uns.get("xyz_unit", "micron")).strip().lower()
    if unit not in _TO_MICRON:
        raise ValueError(f"cannot convert xyz_unit {unit!r} to micron; set cd.uns['xyz_unit']")
    sp = cd.spots_with_loci()
    n = len(sp)
    if "barcode" in sp.columns:
        barcode = sp["barcode"].to_numpy()
    else:
        bins = cd.bins
        rank = bins.groupby("chrom", observed=True)["start"].rank(method="first").astype(np.int64).to_numpy()
        barcode = rank[sp["bin_id"].to_numpy()]
    trace = sp["trace_id"].astype(str)
    if "spot_id" in sp.columns:
        spot_id = sp["spot_id"].astype(str).to_numpy()
    else:
        spot_id = (trace + "_" + pd.Series(barcode, index=sp.index).astype(str)).to_numpy()
    mul, div = _TO_MICRON[unit]
    xyz = np.asarray(cd.coords, dtype=np.float64)
    xyz = xyz * mul if mul != 1.0 else xyz / div
    table = pd.DataFrame({
        "Spot_ID": spot_id,
        "Trace_ID": trace.to_numpy(),
        "x": xyz[:, 0], "y": xyz[:, 1], "z": xyz[:, 2],
        "Chrom": sp["chrom"].astype(str).to_numpy() if loci else np.full(n, "", dtype=object),
        "Chrom_Start": sp["start"].to_numpy(dtype=np.int64) if loci else np.zeros(n, np.int64),
        "Chrom_End": sp["end"].to_numpy(dtype=np.int64) if loci else np.zeros(n, np.int64),
        "ROI #": sp["roi_id"].to_numpy() if "roi_id" in sp.columns else np.zeros(n, np.int64),
        "Mask_id": _ints_or_str(sp["cell_id"]) if "cell_id" in sp.columns else np.zeros(n, np.int64),
        "Barcode #": np.asarray(barcode),
        "label": sp["label"].astype(str).to_numpy() if "label" in sp.columns else np.full(n, "None", dtype=object),
    })
    meta = ["xyz_unit=micron"]
    if cd.uns.get("genome_assembly"):
        meta.append(f"genome_assembly={cd.uns['genome_assembly']}")
    if isinstance(comments, Mapping):
        meta += [f"{k}={v}" for k, v in comments.items()]
    elif comments:
        meta += [str(c) for c in comments]
    out = Table.from_pandas(table)
    out.meta["comments"] = meta
    path = Path(path)
    out.write(path, format="ascii.ecsv", overwrite=overwrite)
    return path


__all__ = ["write_pyhim_trace", "PYHIM_COLUMNS"]
