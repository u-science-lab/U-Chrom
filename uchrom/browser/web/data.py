"""Dataset registry and geometry encoding for the web browser.

Framework-free: everything here works on :class:`~uchrom.core.ChromData`
and plain numpy, so it is testable without FastAPI.  The HTTP layer in
:mod:`uchrom.browser.web.server` is a thin wrapper.  See ``API.md`` for the
wire format.
"""

from __future__ import annotations

import json
import re
import struct
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

import numpy as np
import pandas as pd

from uchrom.core import ChromData

DEFAULT_MAX_POINTS = 5_000_000


def natural_chrom_key(name: str):
    """Sort key: chr1 < chr2 < chr10 < chrX < chrY < chrM < others."""
    s = re.sub(r"^chr", "", str(name), flags=re.IGNORECASE)
    if s.isdigit():
        return (0, int(s), "")
    special = {"X": 1, "Y": 2, "M": 3, "MT": 3}
    if s.upper() in special:
        return (1, special[s.upper()], "")
    return (2, 0, str(name))


def natural_key(text: str):
    """Sort "cell_2" before "cell_10" (digit runs compare numerically)."""
    return [(0, int(t), "") if t.isdigit() else (1, 0, t)
            for t in re.split(r"(\d+)", str(text)) if t]


def load_chromdata(path: Path) -> ChromData:
    """Load a ``.h5cd`` or a reconstruction CSV (chrom, start, end, x, y, z)."""
    if path.suffix == ".h5cd":
        return ChromData.read(path)
    df = pd.read_csv(path, index_col=0)
    return ChromData.from_dataframe(df)


@dataclass
class GeometryFilter:
    """Layer filter; every field is optional and they combine with AND."""

    chroms: Optional[List[str]] = None
    region: Optional[Dict[str, Any]] = None  # {"chrom", "start", "end"}
    trace_ids: Optional[List[str]] = None
    cell_ids: Optional[List[str]] = None
    max_points: int = DEFAULT_MAX_POINTS

    def __post_init__(self):
        if self.region is not None:
            missing = {"chrom", "start", "end"} - set(self.region)
            if missing:
                raise ValueError(f"region is missing {sorted(missing)}")
            if int(self.region["end"]) <= int(self.region["start"]):
                raise ValueError("region end must be greater than start")
        if self.max_points <= 0:
            raise ValueError("max_points must be positive")


@dataclass
class Dataset:
    id: str
    name: str
    path: Optional[str]
    cd: ChromData
    _cache: Dict[str, Any] = field(default_factory=dict, repr=False)

    # ------------------------------------------------------------------
    # Cached per-spot arrays
    # ------------------------------------------------------------------

    def _arrays(self) -> Dict[str, Any]:
        if "arrays" not in self._cache:
            spots = self.cd.spots
            chrom = spots["chrom"].astype(str).to_numpy()
            trace = spots["trace_id"].astype(str).to_numpy()
            cell = (
                spots["cell_id"].astype(str).to_numpy()
                if "cell_id" in spots.columns else None
            )
            chrom_names = sorted(pd.unique(chrom), key=natural_chrom_key)
            chrom_rank = {c: i for i, c in enumerate(chrom_names)}
            self._cache["arrays"] = {
                "chrom": chrom,
                "chrom_rank": np.array([chrom_rank[c] for c in chrom], dtype=np.int64)
                if len(chrom) else np.zeros(0, dtype=np.int64),
                "chrom_names": chrom_names,
                "trace": trace,
                "trace_code": pd.factorize(trace, sort=True)[0],
                "cell": cell,
                "start": spots["start"].to_numpy(dtype=np.int64),
                "end": spots["end"].to_numpy(dtype=np.int64),
            }
        return self._cache["arrays"]

    # ------------------------------------------------------------------
    # Summaries
    # ------------------------------------------------------------------

    def chrom_table(self) -> List[Dict[str, Any]]:
        if "chroms" not in self._cache:
            a = self._arrays()
            df = pd.DataFrame({
                "chrom": a["chrom"], "start": a["start"], "end": a["end"],
                "trace": a["trace"],
            })
            g = df.groupby("chrom", sort=False)
            table = g.agg(start=("start", "min"), end=("end", "max"),
                          n_spots=("start", "size"), n_traces=("trace", "nunique"))
            self._cache["chroms"] = [
                {"name": c, "start": int(table.at[c, "start"]),
                 "end": int(table.at[c, "end"]),
                 "n_spots": int(table.at[c, "n_spots"]),
                 "n_traces": int(table.at[c, "n_traces"])}
                for c in a["chrom_names"]
            ]
        return self._cache["chroms"]

    def summary(self) -> Dict[str, Any]:
        chroms = self.chrom_table()
        unit = self.cd.uns.get("xyz_unit") if isinstance(self.cd.uns, dict) else None
        return {
            "id": self.id,
            "name": self.name,
            "path": self.path,
            "n_spots": int(self.cd.n_spots),
            "n_traces": int(self.cd.n_traces),
            "n_cells": int(self.cd.n_cells),
            "xyz_unit": None if unit is None else str(unit),
            "trace_mode": bool(self.cd.n_traces > len(chroms)),
            "chroms": chroms,
            "cell_fields": self.cell_fields(),
            "embeddings": self.embeddings(),
            "point_sets": self.point_sets(),
        }

    def traces(self, chrom: Optional[str] = None, offset: int = 0,
               limit: int = 500) -> Dict[str, Any]:
        if "traces" not in self._cache:
            a = self._arrays()
            df = pd.DataFrame({
                "trace_id": a["trace"], "chrom": a["chrom"],
                "start": a["start"], "end": a["end"],
            })
            if a["cell"] is not None:
                df["cell_id"] = a["cell"]
            agg = {"n_spots": ("start", "size"), "start": ("start", "min"),
                   "end": ("end", "max")}
            if a["cell"] is not None:
                agg["cell_id"] = ("cell_id", "first")
            t = df.groupby(["trace_id", "chrom"], sort=False).agg(**agg).reset_index()
            t["_rank"] = t["chrom"].map(natural_chrom_key)
            t = t.sort_values(["_rank", "trace_id"], kind="stable").drop(columns="_rank")
            if "cell_id" not in t.columns:
                t["cell_id"] = None
            self._cache["traces"] = t.reset_index(drop=True)
        t = self._cache["traces"]
        if chrom is not None:
            t = t[t["chrom"] == chrom]
        page = t.iloc[offset: offset + limit]
        rows = [
            {"trace_id": str(r.trace_id), "chrom": str(r.chrom),
             "cell_id": None if r.cell_id is None or pd.isna(r.cell_id) else str(r.cell_id),
             "n_spots": int(r.n_spots), "start": int(r.start), "end": int(r.end)}
            for r in page.itertuples(index=False)
        ]
        return {"total": int(len(t)), "traces": rows}

    def cells(self, offset: int = 0, limit: int = 500) -> Dict[str, Any]:
        """Cell table in natural id order (empty when there is no cell_id)."""
        if "cells" not in self._cache:
            a = self._arrays()
            if a["cell"] is None:
                self._cache["cells"] = []
            else:
                df = pd.DataFrame({"cell_id": a["cell"], "trace": a["trace"],
                                   "chrom": a["chrom"], "start": a["start"]})
                g = df.groupby("cell_id", sort=False).agg(
                    n_spots=("start", "size"), n_traces=("trace", "nunique"),
                    n_chroms=("chrom", "nunique"))
                self._cache["cells"] = [
                    {"cell_id": str(c), "n_spots": int(g.at[c, "n_spots"]),
                     "n_traces": int(g.at[c, "n_traces"]),
                     "n_chroms": int(g.at[c, "n_chroms"])}
                    for c in sorted(g.index, key=natural_key)
                ]
        rows = self._cache["cells"]
        return {"total": len(rows), "cells": rows[offset: offset + limit]}

    # ------------------------------------------------------------------
    # Multi-omics: cell fields and point sets
    # ------------------------------------------------------------------

    def _cells_table(self) -> pd.DataFrame:
        """``cd.cells`` indexed by string cell_id (empty if unavailable)."""
        if "cells_table" not in self._cache:
            cells = self.cd.cells
            if len(cells) == 0:
                table = pd.DataFrame()
            else:
                if "cell_id" in cells.columns:
                    cells = cells.set_index("cell_id")
                table = cells.copy()
                table.index = table.index.astype(str)
            self._cache["cells_table"] = table
        return self._cache["cells_table"]

    def cell_fields(self) -> List[Dict[str, Any]]:
        """Numeric ``cd.cells`` columns, for colouring cells."""
        if "cell_fields" not in self._cache:
            table = self._cells_table()
            out = []
            for col in table.columns:
                if not pd.api.types.is_numeric_dtype(table[col]) or pd.api.types.is_bool_dtype(table[col]):
                    continue
                vals = table[col].to_numpy(dtype=np.float64)
                valid = vals[np.isfinite(vals)]
                if not len(valid):
                    continue
                group, _, label = str(col).partition(".")
                if not label:
                    group, label = "cell", str(col)
                out.append({"name": str(col), "group": group, "label": label,
                            "min": float(valid.min()), "max": float(valid.max()),
                            "n_valid": int(len(valid))})
            self._cache["cell_fields"] = out
        return self._cache["cell_fields"]

    def cell_values(self, field: str) -> Dict[str, Any]:
        table = self._cells_table()
        if field not in {f["name"] for f in self.cell_fields()}:
            raise KeyError(field)
        vals = table[field].to_numpy(dtype=np.float64)
        return {"field": field, "cell_ids": [str(c) for c in table.index],
                "values": [None if not np.isfinite(v) else _num(v) for v in vals]}

    def cell_info(self, cell_id: str) -> Dict[str, Any]:
        table = self._cells_table()
        if str(cell_id) not in table.index:
            raise KeyError(cell_id)
        row = table.loc[str(cell_id)]
        fields = {}
        for col, val in row.items():
            if isinstance(val, (float, np.floating)) and not np.isfinite(val):
                fields[str(col)] = None
            elif isinstance(val, (int, float, np.integer, np.floating)):
                fields[str(col)] = _num(val)
            else:
                fields[str(col)] = str(val)
        return {"cell_id": str(cell_id), "fields": fields}

    def embeddings(self) -> List[Dict[str, Any]]:
        """cellm arrays usable as ≥2-D cell embeddings (rows = cd.cells)."""
        n = len(self._cells_table())
        meta = self.cd.uns.get("embeddings") if isinstance(self.cd.uns, dict) else None
        meta = meta if isinstance(meta, dict) else {}
        out = []
        for key, arr in self.cd.cellm.items():
            if np.ndim(arr) != 2 or np.shape(arr)[1] < 2 or not n or np.shape(arr)[0] != n:
                continue
            m = meta.get(key) if isinstance(meta.get(key), dict) else {}
            out.append({"key": str(key), "method": m.get("method"), "source": m.get("source"),
                        "label": str(m.get("label") or key), "n_dims": int(np.shape(arr)[1])})
        return out

    def embedding(self, key: str, dims=(0, 1)) -> Dict[str, Any]:
        info = next((e for e in self.embeddings() if e["key"] == key), None)
        if info is None:
            raise KeyError(key)
        a, b = (int(d) for d in dims)
        if not (0 <= a < info["n_dims"] and 0 <= b < info["n_dims"]):
            raise ValueError(f"dims must be in [0, {info['n_dims']})")
        arr = np.asarray(self.cd.cellm[key], dtype=np.float64)
        meta = (self.cd.uns.get("embeddings") or {}).get(key) or {}
        prefix = str(meta.get("axis_prefix") or info["label"].split()[-1])
        fin = lambda v: [None if not np.isfinite(x) else float(x) for x in v]  # noqa: E731
        return {"key": key, "label": info["label"],
                "cell_ids": [str(c) for c in self._cells_table().index],
                "x": fin(arr[:, a]), "y": fin(arr[:, b]),
                "axis_labels": [f"{prefix}{a + 1}", f"{prefix}{b + 1}"]}

    def point_sets(self) -> List[Dict[str, Any]]:
        if "point_sets" not in self._cache:
            out = []
            for name, df in self.cd.points.items():
                label_field = next((c for c in ("gene", "label", "name") if c in df.columns), None)
                labels = []
                if label_field is not None:
                    counts = df[label_field].astype(str).value_counts()
                    labels = [{"value": str(k), "count": int(v)} for k, v in counts.items()]
                skip = {"x", "y", "z", "cell_id", "spot_id", label_field}
                value_fields = [str(c) for c in df.columns
                                if c not in skip and pd.api.types.is_numeric_dtype(df[c])
                                and not str(c).endswith("_id")]
                out.append({"name": str(name), "n_points": int(len(df)),
                            "label_field": label_field, "labels": labels,
                            "value_fields": value_fields})
            self._cache["point_sets"] = out
        return self._cache["point_sets"]

    def points(self, name: str, cell_ids: Optional[List[str]] = None,
               labels: Optional[List[str]] = None) -> Dict[str, Any]:
        if name not in self.cd.points:
            raise KeyError(name)
        info = next(p for p in self.point_sets() if p["name"] == name)
        df = self.cd.points[name]
        mask = np.ones(len(df), dtype=bool)
        if cell_ids is not None and "cell_id" in df.columns:
            mask &= df["cell_id"].astype(str).isin([str(c) for c in cell_ids]).to_numpy()
        if labels is not None and info["label_field"] is not None:
            mask &= df[info["label_field"]].astype(str).isin([str(v) for v in labels]).to_numpy()
        sel = df[mask]
        pos = sel[["x", "y", "z"]].to_numpy(dtype=np.float64)
        cells = (sel["cell_id"].astype(str).tolist() if "cell_id" in sel.columns
                 else [None] * len(sel))
        lab = (sel[info["label_field"]].astype(str).tolist() if info["label_field"] is not None
               else [None] * len(sel))
        values = {f: [None if not np.isfinite(v) else _num(v)
                      for v in sel[f].to_numpy(dtype=np.float64)]
                  for f in info["value_fields"]}
        return {"n": int(len(sel)),
                "positions": [None if not np.isfinite(v) else float(v) for v in pos.ravel()],
                "cell_ids": cells, "labels": lab, "values": values}

    # ------------------------------------------------------------------
    # Geometry
    # ------------------------------------------------------------------

    def select(self, flt: GeometryFilter) -> np.ndarray:
        """Indices of spots matching ``flt``, sorted by chrom, trace, start."""
        a = self._arrays()
        mask = np.ones(len(a["chrom"]), dtype=bool)
        if flt.chroms is not None:
            mask &= np.isin(a["chrom"], [str(c) for c in flt.chroms])
        if flt.region is not None:
            r = flt.region
            mask &= (a["chrom"] == str(r["chrom"]))
            mask &= (a["end"] > int(r["start"])) & (a["start"] < int(r["end"]))
        if flt.trace_ids is not None:
            mask &= np.isin(a["trace"], [str(t) for t in flt.trace_ids])
        if flt.cell_ids is not None:
            if a["cell"] is None:
                mask[:] = False
            else:
                mask &= np.isin(a["cell"], [str(c) for c in flt.cell_ids])
        idx = np.nonzero(mask)[0]
        order = np.lexsort((a["start"][idx], a["trace_code"][idx], a["chrom_rank"][idx]))
        return idx[order]

    def geometry(self, flt: GeometryFilter) -> bytes:
        return encode_geometry(self, self.select(flt), flt.max_points)


def _num(v) -> Any:
    """JSON-friendly number: ints stay ints."""
    f = float(v)
    return int(f) if f.is_integer() and abs(f) < 2**53 else f


def _segment_bounds(dataset: Dataset, idx: np.ndarray):
    """Split sorted spot indices into polyline segments.

    Returns ``(kept_idx, offsets)``: spots with non-finite coords are dropped
    and break the run, as does a change of trace or chromosome.
    """
    a = dataset._arrays()
    if len(idx) == 0:
        return idx, np.zeros(1, dtype=np.int64)
    coords = dataset.cd.coords[idx]
    finite = np.isfinite(coords).all(axis=1)
    key_change = np.ones(len(idx), dtype=bool)
    key_change[1:] = (
        (a["trace_code"][idx][1:] != a["trace_code"][idx][:-1])
        | (a["chrom_rank"][idx][1:] != a["chrom_rank"][idx][:-1])
    )
    prev_missing = np.zeros(len(idx), dtype=bool)
    prev_missing[1:] = ~finite[:-1]
    seg_id = np.cumsum(key_change | prev_missing)[finite]
    kept = idx[finite]
    if len(kept) == 0:
        return kept, np.zeros(1, dtype=np.int64)
    starts = np.flatnonzero(np.r_[True, seg_id[1:] != seg_id[:-1]])
    offsets = np.r_[starts, len(kept)].astype(np.int64)
    return kept, offsets


def encode_geometry(dataset: Dataset, idx: np.ndarray,
                    max_points: int = DEFAULT_MAX_POINTS) -> bytes:
    """Encode the selected spots in the binary layout documented in API.md."""
    a = dataset._arrays()
    kept, offsets = _segment_bounds(dataset, idx)
    total = len(kept)
    truncated = total > max_points
    if truncated:
        n_fit = int(np.searchsorted(offsets[1:], max_points, side="right"))
        if n_fit == 0:  # first segment alone exceeds the cap: cut it
            offsets = np.array([0, max_points], dtype=np.int64)
        else:
            offsets = offsets[: n_fit + 1]
        kept = kept[: offsets[-1]]

    positions = dataset.cd.coords[kept].astype(np.float32)
    starts = a["start"][kept].astype(np.uint32)

    segments = []
    for i in range(len(offsets) - 1):
        lo, hi = int(offsets[i]), int(offsets[i + 1])
        first = kept[lo]
        cell = a["cell"][first] if a["cell"] is not None else None
        segments.append({
            "trace_id": str(a["trace"][first]),
            "chrom": str(a["chrom"][first]),
            "cell_id": None if cell is None else str(cell),
            "n_points": hi - lo,
            "start": int(a["start"][kept[lo:hi]].min()),
            "end": int(a["end"][kept[lo:hi]].max()),
        })

    bbox = None
    if len(positions):
        bbox = {"min": positions.min(axis=0).tolist(),
                "max": positions.max(axis=0).tolist()}
    header = {
        "n_points": int(len(kept)),
        "n_segments": len(segments),
        "total_points": int(total),
        "truncated": bool(truncated),
        "segments": segments,
        "bbox": bbox,
        "chrom_extent": {c["name"]: [c["start"], c["end"]]
                         for c in dataset.chrom_table()},
    }
    head = json.dumps(header, separators=(",", ":")).encode("utf-8")
    head += b" " * (-len(head) % 4)
    return b"".join([
        struct.pack("<I", len(head)),
        head,
        positions.astype("<f4").tobytes(),
        starts.astype("<u4").tobytes(),
        offsets.astype("<u4").tobytes(),
    ])


def decode_geometry(buf: bytes) -> Dict[str, Any]:
    """Inverse of :func:`encode_geometry` (used by tests and notebooks)."""
    (h,) = struct.unpack_from("<I", buf, 0)
    header = json.loads(buf[4: 4 + h].decode("utf-8"))
    n, s = header["n_points"], header["n_segments"]
    pos = 4 + h
    positions = np.frombuffer(buf, dtype="<f4", count=3 * n, offset=pos).reshape(n, 3)
    pos += 12 * n
    starts = np.frombuffer(buf, dtype="<u4", count=n, offset=pos)
    pos += 4 * n
    offsets = np.frombuffer(buf, dtype="<u4", count=s + 1, offset=pos)
    return {"header": header, "positions": positions, "starts": starts,
            "offsets": offsets}


class DatasetStore:
    """Thread-safe registry of loaded datasets."""

    def __init__(self):
        self._lock = threading.Lock()
        self._datasets: Dict[str, Dataset] = {}
        self._next = 1

    def add(self, cd: ChromData, name: str, path: Optional[str] = None) -> Dataset:
        with self._lock:
            ds = Dataset(id=f"d{self._next}", name=name, path=path, cd=cd)
            self._next += 1
            self._datasets[ds.id] = ds
        return ds

    def load(self, path) -> Dataset:
        p = Path(path).expanduser().resolve()
        if not p.is_file():
            raise FileNotFoundError(f"no such file: {p}")
        return self.add(load_chromdata(p), name=p.stem, path=str(p))

    def get(self, dataset_id: str) -> Dataset:
        try:
            return self._datasets[dataset_id]
        except KeyError:
            raise KeyError(dataset_id) from None

    def remove(self, dataset_id: str) -> None:
        with self._lock:
            self._datasets.pop(dataset_id, None)

    def list(self) -> Sequence[Dataset]:
        return list(self._datasets.values())
