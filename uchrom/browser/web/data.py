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
        idx = np.nonzero(mask)[0]
        order = np.lexsort((a["start"][idx], a["trace_code"][idx], a["chrom_rank"][idx]))
        return idx[order]

    def geometry(self, flt: GeometryFilter) -> bytes:
        return encode_geometry(self, self.select(flt), flt.max_points)


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
