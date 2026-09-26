"""Write ``.h5cd`` files in the format-1.x layout (the writer that 2.0 dropped).

Used to test that 1.x files are read / upgraded transparently.  The layout
follows ``uchrom.core.cdata`` as of format 1.4: spots store
``chrom/start/end`` (categoricals as byte strings), ``tracks/`` is
spot-aligned, results are typed entries with provenance attrs.
"""
from __future__ import annotations

import h5py
import numpy as np
import pandas as pd

from uchrom.core.cdata import _write_results, _write_uns
from uchrom.core.results import ResultsStore


def _write_df_v1(f, name, df):
    grp = f.create_group(name)
    if df is None or (len(df) == 0 and len(df.columns) == 0):
        return
    grp.attrs["_n_rows"] = len(df)
    grp.attrs["_columns"] = [str(c) for c in df.columns]
    if len(df) == 0:
        grp.attrs["_empty"] = True
        return
    for col in df.columns:
        s = df[col]
        if hasattr(s.dtype, "categories") or s.dtype == object:
            grp.create_dataset(str(col), data=s.astype(str).to_numpy().astype("S"))
        else:
            grp.create_dataset(str(col), data=s.to_numpy())
    idx = df.index
    if not (isinstance(idx, pd.RangeIndex) and idx.start == 0 and idx.step == 1 and idx.name is None):
        vals = idx.to_numpy()
        if vals.dtype == object or vals.dtype.kind in "US":
            vals = np.array([str(x) for x in vals]).astype("S")
        grp.create_dataset("_index", data=vals)
        grp.attrs["_index_name"] = idx.name or ""


def write_v1(path, coords, spots, *, tracks=None, cells=None, traces=None, layers=None,
             cellm=None, results=None, uns=None, points=None, version="1.4"):
    with h5py.File(path, "w") as f:
        f.attrs["uchrom_format_version"] = version
        f.attrs["uchrom_version"] = "0.2.0"
        f.create_dataset("coords", data=np.asarray(coords, dtype=np.float64))
        _write_df_v1(f, "spots", spots)
        _write_df_v1(f, "cells", cells)
        _write_df_v1(f, "tracks", tracks)
        _write_df_v1(f, "traces", traces)
        for grp_name, d in (("layers", layers), ("cellm", cellm)):
            g = f.create_group(grp_name)
            for k, v in (d or {}).items():
                g.create_dataset(k, data=np.asarray(v))
        _write_results(f, "results", ResultsStore.coerce(results or {}))
        _write_uns(f, "uns", uns or {})
        if points:
            g = f.create_group("points")
            for k, v in points.items():
                _write_df_v1(g, k, v)
    return path
