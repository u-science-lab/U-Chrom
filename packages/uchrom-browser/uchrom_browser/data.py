"""Dataset registry and geometry encoding for the web browser.

Framework-free: everything here works on :class:`~chromdata.ChromData`
and plain numpy, so it is testable without FastAPI.  The HTTP layer in
:mod:`uchrom_browser.server` is a thin wrapper.  See ``API.md`` for the
wire format.
"""

from __future__ import annotations

import hashlib
import json
import re
import struct
import threading
import warnings
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from chromdata import ChromData

DEFAULT_MAX_POINTS = 5_000_000
#: a backed store with more spots than this is never read whole by the browser: summaries come from its index,
#: geometry / statistics / distance maps from a sample of its cells or traces (format 2.2 stores)
LARGE_SPOTS = 2_000_000
#: spots read for a statistic (radius of gyration, P(s)) of a large store
STATS_MAX_SPOTS = 2_000_000
#: reserved group reference: every cell (e.g. the all-cell pseudo-bulk of a per-cell map)
ALL_CELLS = "all"


def _fmt_bp(n: int) -> str:
    """A bin size as "500 kb", "1 Mb", "50 bp"."""
    for unit, f in (("Mb", 1_000_000), ("kb", 1_000)):
        if n >= f and n % f == 0:
            return f"{n // f} {unit}"
    return f"{n} bp"


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


_EMB_METHODS = ("umap", "tsne", "pca", "lsi")


def _method_from_key(key: str) -> Optional[str]:
    """'atac_umap' → 'umap' (for cellm arrays without uns['embeddings'] metadata)."""
    low = key.lower()
    return next((m for m in _EMB_METHODS if low == m or low.endswith("_" + m)), None)


def _modality(key: str, meta: Dict[str, Any]) -> str:
    """Display modality of an embedding ("RNA", "Histone/IF", "ATAC", "Hi-C",
    "Published", …): the recorded one, else from its source / key prefix."""
    if meta.get("modality"):
        return str(meta["modality"])
    from chromdata.conventions import MODALITY_LABELS

    source = str(meta.get("source") or "")
    if source in MODALITY_LABELS:
        return MODALITY_LABELS[source]
    prefix = key.split("_", 1)[0].lower() if "_" in key else ""
    if prefix in MODALITY_LABELS:
        return MODALITY_LABELS[prefix]
    if prefix in ("paper", "published") or "metadata" in source.lower():
        return "Published"
    return "Other"


def load_chromdata(path: Path) -> ChromData:
    """Open a ChromData store or a reconstruction CSV (chrom, start, end, x, y, z).

    ``.chromdata.zarr`` / ``.cdz`` stores open **backed**: only the small
    tables and the ``index/`` offsets are read, and the spots of a cell /
    trace / chromosome are read when a view needs them.  A legacy ``.h5cd``
    raises a ``ValueError`` that names the conversion command.
    """
    from chromdata.zarrcd import container_kind

    kind = container_kind(path)
    if kind is not None:  # zarr / cdz; "h5cd" raises (convert with python -m uchrom.io.upgrade)
        return ChromData.read(path, backed=True)
    df = pd.read_csv(path, index_col=0)
    return ChromData.from_dataframe(df)


class _LazyNames:
    """Cell names of an embedded cell x bin matrix: read (one request) when first needed; ``len`` is known."""

    def __init__(self, load, n: int):
        self._load, self._n, self._v = load, n, None

    def __len__(self) -> int:
        return self._n

    def values(self):
        if self._v is None:
            self._v = self._load()
        return self._v


class _LazyRows(dict):
    """``{cell id: row}`` of a :class:`_LazyNames`, built on first lookup; ``len`` without reading anything."""

    def __init__(self, names: _LazyNames):
        super().__init__()
        self._names, self._built = names, False

    def _build(self) -> None:
        if not self._built:
            self.update({str(c): i for i, c in enumerate(self._names.values())})
            self._built = True

    def __len__(self) -> int:
        return len(self._names)

    def __getitem__(self, k):
        self._build()
        return super().__getitem__(k)

    def __contains__(self, k) -> bool:
        self._build()
        return super().__contains__(k)

    def get(self, k, default=None):
        self._build()
        return super().get(k, default)


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
    _groups: Dict[str, Dict[str, Any]] = field(default_factory=dict, repr=False)

    # ------------------------------------------------------------------
    # Cached per-spot arrays
    # ------------------------------------------------------------------

    def _arrays(self) -> Dict[str, Any]:
        if "arrays" not in self._cache:
            spots = self.cd.spots
            bins = self.cd.bins
            bin_id = spots["bin_id"].to_numpy(dtype=np.int64)
            chrom = bins["chrom"].astype(str).to_numpy()[bin_id]
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
                "start": bins["start"].to_numpy(dtype=np.int64)[bin_id],
                "end": bins["end"].to_numpy(dtype=np.int64)[bin_id],
                "bin_id": bin_id,
            }
        return self._cache["arrays"]

    def _coords(self) -> np.ndarray:
        """All spot coordinates as one in-memory array.

        On a backed store ``cd.coords[idx]`` with an index array reads row by
        row (2.7 s for 1.15e7 spots, twice per geometry request), while the
        full slice ``cd.coords[:]`` is one fast read (0.04 s); geometry indexes
        this cached array instead."""
        if not self.backed:
            return self.cd.coords
        if "coords" not in self._cache:
            self._cache["coords"] = np.asarray(self.cd.coords[:])
        return self._cache["coords"]

    # ------------------------------------------------------------------
    # Backed stores: summaries from the index, geometry from row ranges
    # ------------------------------------------------------------------

    @property
    def backed(self) -> bool:
        return bool(getattr(self.cd, "backed", False))

    def _segments(self) -> pd.DataFrame:
        """Backed only: one row per (cell, trace, chromosome) run of the
        stored spots — from ``index/`` plus the ``bin_id`` column, with no
        per-spot strings.  Columns: ``trace``, ``cell`` (str / None),
        ``chrom``, ``n_spots``, ``start`` (min), ``end`` (max)."""
        if "segments" not in self._cache and self._index_segments():
            # from the coordinate index alone (one run per chromosome copy): the per-spot bin ids of a large
            # store are never read; start / end are the chromosome's extent on the locus axis
            r = self._runs()
            ext = self._chrom_extent()
            names = np.asarray(self.cd.bins["chrom"].cat.categories.astype(str))
            chrom = names[r["chrom"].to_numpy()]
            trace_cats = np.asarray(self.cd._categories("trace_id")).astype(str)
            df = pd.DataFrame({"trace": trace_cats[r["trace"].to_numpy()], "chrom": chrom,
                               "n_spots": (r["hi"] - r["lo"]).to_numpy(np.int64),
                               "start": ext.loc[chrom, "start"].to_numpy(np.int64),
                               "end": ext.loc[chrom, "end"].to_numpy(np.int64)})
            if self.cd._has_cell_id():
                cell_cats = np.asarray(self.cd._categories("cell_id")).astype(str)
                df["cell"] = cell_cats[r["cell"].to_numpy()]
            else:
                df["cell"] = None
            self._cache["segments"] = df
        if "segments" not in self._cache:
            cd = self.cd
            idx = cd._index
            off = np.asarray(idx["trace_offsets"], dtype=np.int64)
            n_seg = len(off) - 1
            bins = cd.bins
            chrom_codes = np.asarray(bins["chrom"].cat.codes, dtype=np.int64)
            chrom_names = np.asarray(bins["chrom"].cat.categories.astype(str))
            b_start = bins["start"].to_numpy(dtype=np.int64)
            b_end = bins["end"].to_numpy(dtype=np.int64)
            bin_id = cd.spots["bin_id"].to_numpy(dtype=np.int64)
            seg_of_row = np.repeat(np.arange(n_seg), np.diff(off))
            rc = chrom_codes[bin_id] if len(bin_id) else np.zeros(0, dtype=np.int64)
            key = seg_of_row * max(1, len(chrom_names)) + rc
            new = np.r_[True, key[1:] != key[:-1]] if len(key) else np.zeros(0, dtype=bool)
            starts = np.flatnonzero(new)
            run_seg = seg_of_row[starts]
            trace_cats = np.asarray(cd._categories("trace_id")).astype(str)
            tcode = np.asarray(idx["trace_codes"], dtype=np.int64)[run_seg]
            df = pd.DataFrame({
                "trace": np.where(tcode >= 0, trace_cats[np.maximum(tcode, 0)], "nan"),
                "chrom": chrom_names[rc[starts]] if len(starts) else np.zeros(0, dtype=str),
                "n_spots": np.diff(np.r_[starts, len(key)]).astype(np.int64),
                "start": np.minimum.reduceat(b_start[bin_id], starts) if len(starts) else np.zeros(0, np.int64),
                "end": np.maximum.reduceat(b_end[bin_id], starts) if len(starts) else np.zeros(0, np.int64),
            })
            if cd._has_cell_id():
                cell_cats = np.asarray(cd._categories("cell_id")).astype(str)
                ccode = np.asarray(idx["trace_cells"], dtype=np.int64)[run_seg]
                df["cell"] = np.where(ccode >= 0, cell_cats[np.maximum(ccode, 0)], None)
            else:
                df["cell"] = None
            self._cache["segments"] = df
        return self._cache["segments"]

    def _subset(self, flt: "GeometryFilter") -> Optional[ChromData]:
        """Backed only: an in-memory ChromData holding every spot that can
        match ``flt`` (whole cells / traces / chromosome runs), or ``None``
        when the filter does not narrow the data.  Geometry needs only the
        coordinates and the key columns, so only those are read
        (``columns="coords"``: no spot tracks, extra spot columns or
        layers)."""
        cd = self.cd
        idx = cd._index
        if flt.cell_ids is not None:
            if not cd._has_cell_id():
                return cd[np.zeros(0, dtype=np.int64)]
            cats = pd.Index(np.asarray(cd._categories("cell_id")).astype(str))
            codes = cats.get_indexer([str(c) for c in flt.cell_ids])
            mask = np.isin(np.asarray(idx["cell_codes"]), codes[codes >= 0])
            return cd._build(ranges=cd._segment_ranges(mask, idx["cell_offsets"]), columns="coords")
        if flt.trace_ids is not None:
            cats = pd.Index(np.asarray(cd._categories("trace_id")).astype(str))
            codes = cats.get_indexer([str(t) for t in flt.trace_ids])
            mask = np.isin(np.asarray(idx["trace_codes"]), codes[codes >= 0])
            return cd._build(ranges=cd._segment_ranges(mask, idx["trace_offsets"]), columns="coords")
        chroms = list(flt.chroms or []) + ([flt.region["chrom"]] if flt.region is not None else [])
        if chroms:
            names = np.asarray(cd.bins["chrom"].cat.categories.astype(str))
            codes = np.flatnonzero(np.isin(names, [str(c) for c in chroms]))
            # format 2.2: the coordinate projection (one partition per chromosome)
            return cd._chroms_subset(codes, columns="coords")
        return None

    # ------------------------------------------------------------------
    # Large backed stores: read a sample, never the whole store
    # ------------------------------------------------------------------

    def _large(self) -> bool:
        """Decided once per dataset (so its paths stay consistent)."""
        if "large" not in self._cache:
            cd = self.cd
            self._cache["large"] = bool(self.backed and getattr(cd, "_v22", False) and int(cd.n_spots) > LARGE_SPOTS
                                        and (np.asarray(cd._cidx["chrom_trace"]) >= 0).all())
        return self._cache["large"]

    def _index_segments(self) -> bool:
        """Summaries from the coordinate index alone: a large store, or any store read over HTTP (where reading
        every spot's bin id costs seconds); every run must be one chromosome copy."""
        if "index_segments" not in self._cache:
            from chromdata.remote import is_url

            cd = self.cd
            self._cache["index_segments"] = bool(
                self.backed and getattr(cd, "_v22", False) and (self._large() or (self.path and is_url(self.path)))
                and (np.asarray(cd._cidx["chrom_trace"]) >= 0).all())
        return self._cache["index_segments"]

    def _runs(self) -> pd.DataFrame:
        """The coordinate table's runs (chromosome > cell > trace; one per chromosome copy): row range and the
        chromosome / cell / trace codes (cached)."""
        if "runs" not in self._cache:
            c = self.cd._cidx
            off = np.asarray(c["trace_offsets"], dtype=np.int64)
            self._cache["runs"] = pd.DataFrame({
                "lo": off[:-1], "hi": off[1:], "chrom": np.asarray(c["chrom_trace"], dtype=np.int64),
                "cell": np.asarray(c["trace_cells"], dtype=np.int64), "trace": np.asarray(c["trace_codes"], dtype=np.int64)})
        return self._cache["runs"]

    def _chrom_extent(self) -> pd.DataFrame:
        b = self.cd.bins
        return b.assign(chrom=b["chrom"].astype(str)).groupby("chrom").agg(start=("start", "min"), end=("end", "max"))

    def _run_mask(self, chroms=None, cell_ids=None, trace_ids=None) -> np.ndarray:
        r, cd = self._runs(), self.cd
        mask = np.ones(len(r), dtype=bool)
        if chroms:
            names = np.asarray(cd.bins["chrom"].cat.categories.astype(str))
            mask &= np.isin(r["chrom"].to_numpy(), np.flatnonzero(np.isin(names, [str(c) for c in chroms])))
        if cell_ids is not None:
            cats = pd.Index(np.asarray(cd._categories("cell_id")).astype(str)) if cd._has_cell_id() else pd.Index([])
            codes = cats.get_indexer([str(c) for c in cell_ids])
            mask &= np.isin(r["cell"].to_numpy(), codes[codes >= 0])
        if trace_ids is not None:
            cats = pd.Index(np.asarray(cd._categories("trace_id")).astype(str))
            codes = cats.get_indexer([str(t) for t in trace_ids])
            mask &= np.isin(r["trace"].to_numpy(), codes[codes >= 0])
        return mask

    def _sample(self, mask: np.ndarray, max_spots: int, *, unit: str = "cell", max_units: Optional[int] = None,
                block: int = 8):
        """Runs of ``mask`` for a sample: whole cells (or single traces, ``unit="trace"``) in a fixed random order
        until ``max_spots`` (or ``max_units``) is reached.  The order shuffles blocks of ``block`` neighbouring
        units: neighbours share row groups, so a sample is a few reads per partition, not one per unit (over
        HTTP, ten times fewer requests).  Returns ``(row ranges, units used, units matching, spots used, spots
        matching)``."""
        r = self._runs()[mask]
        n_all = int((r["hi"] - r["lo"]).sum())
        if not self.cd._has_cell_id():
            unit = "trace"
        key = r["cell"].to_numpy() if unit == "cell" else np.arange(len(r))
        units = np.unique(key)
        nb = -(-len(units) // block) if len(units) else 0
        blocks = np.random.default_rng(0).permutation(nb)
        order = np.concatenate([units[b * block:(b + 1) * block] for b in blocks]) if nb else units
        size = pd.Series((r["hi"] - r["lo"]).to_numpy(), index=key).groupby(level=0).sum().reindex(order).to_numpy()
        n = int(np.searchsorted(np.cumsum(size), max_spots, side="right"))
        n = max(1, n) if len(order) else 0
        if max_units is not None:
            n = min(n, int(max_units))
        keep = np.isin(key, order[:n])
        sel = r[keep].sort_values("lo")
        lo, hi = sel["lo"].to_numpy(), sel["hi"].to_numpy()
        brk = np.r_[True, lo[1:] != hi[:-1]] if len(lo) else np.zeros(0, dtype=bool)
        ranges = list(zip(lo[brk].tolist(), hi[np.r_[brk[1:], True]].tolist())) if len(lo) else []
        return ranges, n, len(units), int((sel["hi"] - sel["lo"]).sum()), n_all

    def _part(self, ranges) -> "Dataset":
        """An in-memory Dataset of coordinate-table row ranges (coordinates + keys only)."""
        sub = self.cd._build22(crd=ranges, columns="coords")
        return Dataset(id=self.id, name=self.name, path=self.path, cd=sub)

    def _scope_cells(self, cell_id=None, group=None) -> Optional[List[str]]:
        _one_scope(cell_id, group)
        if cell_id is not None:
            return [str(cell_id)]
        if group is not None:
            return [str(c) for c in self.group_cells(group)]
        return None

    # ------------------------------------------------------------------
    # Summaries
    # ------------------------------------------------------------------

    def chrom_table(self) -> List[Dict[str, Any]]:
        if "chroms" not in self._cache and self.cd.n_spots == 0:
            # no spots (spatial Hi-C, scHi-C): the locus axis still names the chromosomes, for the
            # genome views of contact maps and cell x bin matrices
            b = self.cd.bins
            table = (b.assign(chrom=b["chrom"].astype(str)).groupby("chrom").agg(start=("start", "min"), end=("end", "max"))
                     if len(b) else pd.DataFrame(columns=["start", "end"]))
            self._cache["chroms"] = [
                {"name": c, "start": int(table.at[c, "start"]), "end": int(table.at[c, "end"]),
                 "n_spots": 0, "n_traces": 0}
                for c in sorted(table.index, key=natural_chrom_key)
            ]
        if "chroms" not in self._cache and self.backed:
            seg = self._segments()
            g = seg.groupby("chrom", sort=False)
            table = g.agg(start=("start", "min"), end=("end", "max"),
                          n_spots=("n_spots", "sum"), n_traces=("trace", "nunique"))
            self._cache["chroms"] = [
                {"name": c, "start": int(table.at[c, "start"]), "end": int(table.at[c, "end"]),
                 "n_spots": int(table.at[c, "n_spots"]), "n_traces": int(table.at[c, "n_traces"])}
                for c in sorted(table.index, key=natural_chrom_key)
            ]
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
            "n_bins": int(self.cd.n_bins),
            "n_traces": int(self.cd.n_traces),
            "n_cells": int(self.cd.n_cells),
            "xyz_unit": None if unit is None else str(unit),
            "trace_mode": bool(self.cd.n_traces > len(chroms)),
            "chroms": chroms,
            "genome": self.genome_layout(),
            "has_coords": bool(self.cd.n_spots > 0),
            "tracks": self.track_names(),
            "contact_maps": self.contact_maps(),
            "intervals": self.interval_tables(),
            "clusters": self.cluster_tables(),
            "cell_fields": self.cell_fields(),
            "embeddings": self.embeddings(),
            "point_sets": self.point_sets(),
            "spatial": self.spatial(),
            "cells_overlap": self.cells_overlap(),
        }

    def cells_overlap(self, n: int = 12) -> bool:
        """Whether the cells' 3-D structures share one frame — each model centred on the origin (Dip-C, NucDynamics),
        so that a view of all cells stacks them: the centres of up to ``n`` cells spread over the list lie closer to
        each other (median) than half a cell's radius (median distance of its spots to its centre)."""
        if "cells_overlap" in self._cache:
            return self._cache["cells_overlap"]
        out = False
        try:
            has_cells = self.cd._has_cell_id() if self.backed else "cell_id" in self.cd.spots.columns
            if self.cd.n_spots and self.cd.n_cells > 1 and has_cells:
                cats = (list(self.cd._categories("cell_id")) if self.backed
                        else list(self.cd.spots["cell_id"].astype("category").cat.categories))
                pick = [cats[i] for i in np.unique(np.linspace(0, len(cats) - 1, min(n, len(cats))).astype(int))]
                centres, radii = [], []
                for cell in pick:
                    xyz = np.asarray(self.cd.get_cell(cell, columns="coords").coords, dtype=float)
                    xyz = xyz[np.isfinite(xyz).all(1)]
                    if len(xyz) < 3:
                        continue
                    c = xyz.mean(0)
                    centres.append(c)
                    radii.append(float(np.median(np.linalg.norm(xyz - c, axis=1))))
                if len(centres) >= 2:
                    cen = np.asarray(centres)
                    d = np.linalg.norm(cen[:, None] - cen[None], axis=-1)[np.triu_indices(len(cen), 1)]
                    out = bool(np.median(d) < 0.5 * np.median(radii))
        except Exception:                       # a store this cannot read: the default view as before
            out = False
        self._cache["cells_overlap"] = out
        return out

    def traces(self, chrom: Optional[str] = None, offset: int = 0,
               limit: int = 500) -> Dict[str, Any]:
        if "traces" not in self._cache and self.backed:
            seg = self._segments().rename(columns={"trace": "trace_id", "cell": "cell_id"})
            agg = {"n_spots": ("n_spots", "sum"), "start": ("start", "min"),
                   "end": ("end", "max"), "cell_id": ("cell_id", "first")}
            t = seg.groupby(["trace_id", "chrom"], sort=False).agg(**agg).reset_index()
            t["_rank"] = t["chrom"].map(natural_chrom_key)
            t = t.sort_values(["_rank", "trace_id"], kind="stable").drop(columns="_rank")
            self._cache["traces"] = t.reset_index(drop=True)
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
        if "cells" not in self._cache and self.backed and self.cd.n_spots and self.cd._has_cell_id():
            seg = self._segments()
            g = seg.groupby("cell", sort=False).agg(
                n_spots=("n_spots", "sum"), n_traces=("trace", "nunique"),
                n_chroms=("chrom", "nunique"))
            self._cache["cells"] = [
                {"cell_id": str(c), "n_spots": int(g.at[c, "n_spots"]),
                 "n_traces": int(g.at[c, "n_traces"]), "n_chroms": int(g.at[c, "n_chroms"])}
                for c in sorted(g.index, key=natural_key)
            ]
        if "cells" not in self._cache:
            a = {"cell": None} if self.backed else self._arrays()
            if a["cell"] is None or len(a["cell"]) == 0:
                # no 3-D spots (e.g. scHi-C / RNA only): list cd.cells
                table = self._cells_table()
                self._cache["cells"] = [
                    {"cell_id": str(c), "n_spots": 0, "n_traces": 0, "n_chroms": 0}
                    for c in sorted(table.index, key=natural_key)
                ]
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
        """``cd.cells`` columns for colouring cells: numeric ones (with range)
        and low-cardinality categorical ones such as ``cell_type``."""
        if "cell_fields" not in self._cache:
            table = self._cells_table()
            out = []
            for col in table.columns:
                series = table[col]
                if not pd.api.types.is_numeric_dtype(series) or pd.api.types.is_bool_dtype(series):
                    values = series.dropna().astype(str)
                    counts = values.value_counts()
                    # ids / barcodes are unique per cell: not a useful colouring
                    if len(counts) < 2 or len(counts) > 60 or len(counts) > 0.5 * max(len(values), 1):
                        continue
                    group, _, label = str(col).partition(".")
                    if not label:
                        group, label = "cell", str(col)
                    out.append({"name": str(col), "group": group, "label": label, "kind": "category",
                                "categories": [{"value": str(k), "count": int(v)}
                                               for k, v in sorted(counts.items(), key=lambda kv: natural_key(kv[0]))],
                                "n_valid": int(len(values))})
                    continue
                vals = table[col].to_numpy(dtype=np.float64)
                valid = vals[np.isfinite(vals)]
                if not len(valid):
                    continue
                group, _, label = str(col).partition(".")
                if not label:
                    group, label = "cell", str(col)
                out.append({"name": str(col), "group": group, "label": label, "kind": "numeric",
                            "min": float(valid.min()), "max": float(valid.max()),
                            "n_valid": int(len(valid))})
            self._cache["cell_fields"] = out
        return self._cache["cell_fields"]

    def cell_values(self, field: str) -> Dict[str, Any]:
        table = self._cells_table()
        info = next((f for f in self.cell_fields() if f["name"] == field), None)
        if info is None:
            raise KeyError(field)
        if info["kind"] == "category":
            return {"field": field, "kind": "category", "cell_ids": [str(c) for c in table.index],
                    "values": [None if pd.isna(v) else str(v) for v in table[field]]}
        vals = table[field].to_numpy(dtype=np.float64)
        return {"field": field, "kind": "numeric", "cell_ids": [str(c) for c in table.index],
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

    # ------------------------------------------------------------------
    # Cell groups: a category of a cell field, or a registered cell list
    # ------------------------------------------------------------------

    def known_cells(self) -> set:
        """Cell ids of this dataset (the cells table and the spots)."""
        if "known_cells" not in self._cache:
            known = set(self._cells_table().index)
            if self.backed:
                if self.cd.n_spots and self.cd._has_cell_id():
                    known.update(self._segments()["cell"].dropna().unique())
            else:
                a = self._arrays()
                if a["cell"] is not None:
                    known.update(pd.unique(a["cell"]))
            self._cache["known_cells"] = known
        return self._cache["known_cells"]

    def register_group(self, cells: Sequence[str], name: Optional[str] = None) -> Dict[str, Any]:
        """Register a cell list (e.g. a lasso selection) under a stable id.

        The id hashes the sorted known cells, so registering the same cells
        again (another tab, a reload) gives the same id.  Unknown ids are
        dropped; none known → LookupError.
        """
        wanted = {str(c) for c in cells}
        kept = sorted(wanted & self.known_cells(), key=natural_key)
        if not kept:
            raise LookupError("none of these cells are in the dataset")
        gid = "g" + hashlib.sha1("\n".join(kept).encode("utf-8")).hexdigest()[:12]
        rec = self._groups.setdefault(gid, {"id": gid, "cells": kept})
        if name:
            rec["name"] = str(name)
        return {"id": gid, "name": rec.get("name"), "n_cells": len(kept),
                "n_unknown": len(wanted) - len(kept)}

    def groups(self) -> List[Dict[str, Any]]:
        return [{"id": g["id"], "name": g.get("name"), "n_cells": len(g["cells"])}
                for g in self._groups.values()]

    def group_cells(self, group: str) -> List[str]:
        """Cells of a group reference: ``all``, ``field:<column>=<value>`` or a registered id.

        Unknown field / id → KeyError; a group with no cells → LookupError.
        """
        group = str(group)
        if group == ALL_CELLS:
            cells = sorted(self.known_cells(), key=natural_key)
            if not cells:
                raise LookupError("this dataset has no cell ids")
            return cells
        if group.startswith("field:"):
            field, sep, value = group[len("field:"):].partition("=")
            table = self._cells_table()
            if not sep or field not in table.columns:
                raise KeyError(f"group {group!r}: no cell field {field!r}")
            col = table[field]
            cells = [str(c) for c, v in zip(table.index, col) if not pd.isna(v) and str(v) == value]
            if not cells:
                raise LookupError(f"group {group!r} has no cells")
            return cells
        rec = self._groups.get(group)
        if rec is None:
            raise KeyError(f"unknown group {group!r} (register it with POST groups)")
        return rec["cells"]

    def group_info(self, group: str) -> Dict[str, Any]:
        cells = self.group_cells(group)
        name = (self._groups[group].get("name") if group in self._groups
                else "all cells" if group == ALL_CELLS else group.partition("=")[2])
        return {"group": group, "name": name, "n_cells": len(cells), "cells": cells}

    def _group_spot_mask(self, group: str) -> np.ndarray:
        """Spots of the group's cells (cached; a few groups at a time)."""
        cache = self._cache.setdefault("group_masks", {})
        if group not in cache:
            a = self._arrays()
            cells = self.group_cells(group)
            mask = (np.zeros(len(a["chrom"]), dtype=bool) if a["cell"] is None
                    else np.isin(a["cell"], np.array(cells, dtype=object).astype(str)))
            if len(cache) >= 16:
                cache.pop(next(iter(cache)))
            cache[group] = mask
        return cache[group]

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
            method = m.get("method") or _method_from_key(str(key))
            out.append({"key": str(key), "method": method, "source": m.get("source"),
                        "modality": _modality(str(key), m),
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

    # ---- cell positions (uns['cell_spatial']) and section images (uns['linked_images']) ----

    def _images(self) -> Dict[str, Dict[str, Any]]:
        recs = self.cd.uns.get("linked_images") if isinstance(self.cd.uns, dict) else None
        embedded = self._embedded_images()
        return {str(k): v for k, v in (recs or {}).items()
                if isinstance(v, dict) and v.get("path") and (str(k) in embedded or self.resolve(v["path"]).exists())}

    def _embedded_images(self) -> Dict[str, str]:
        """``{image key: group name}`` of the images embedded in the store."""
        if "embedded_images" not in self._cache:
            from chromdata.embedded import list_embedded_images

            loc = self._store_location()
            self._cache["embedded_images"] = list_embedded_images(loc) if loc else {}
        return self._cache["embedded_images"]

    def image_bytes(self, name: str) -> Optional[Tuple[bytes, str]]:
        """(bytes, media type) of an image embedded in the store, else None (a file: :meth:`image_path`)."""
        group = self._embedded_images().get(name)
        if group is None:
            return None
        from chromdata.embedded import read_embedded_image

        return read_embedded_image(self._store_location(), group)

    def spatial(self) -> List[Dict[str, Any]]:
        """Cell-position sets: key, unit, y direction, regions (sections / FOVs) with cell counts
        and the image of each region, if any.  Sets with images first."""
        if "spatial" in self._cache:
            return self._cache["spatial"]
        recs = self.cd.uns.get("cell_spatial") if isinstance(self.cd.uns, dict) else None
        images = self._images()
        out = []
        for key, rec in (recs or {}).items():
            if not isinstance(rec, dict):
                continue
            try:
                pos = self.cd.cell_positions(str(key))
            except Exception:  # noqa: BLE001 - a malformed record is skipped, not fatal
                continue
            ok = pos[["x", "y"]].notna().all(axis=1)
            reg = pos["region"].astype(str) if "region" in pos else pd.Series("all", index=pos.index)
            counts = reg[ok].value_counts()
            imgs = {r["region"]: name for name, r in images.items() if r.get("positions") == key and "region" in r}
            regions = [{"name": r, "n_cells": int(counts[r]), "image": imgs.get(r)}
                       for r in sorted(counts.index, key=natural_chrom_key)]
            unit = rec.get("unit")
            y_axis = rec.get("y_axis") or ("down" if unit in ("px", "pixel", "spot") else "up")
            in_coords = rec.get("in_coords_frame")
            if not isinstance(in_coords, bool):
                in_coords = self._positions_in_coords(pos[ok])
            out.append({"key": str(key), "unit": unit, "frame": rec.get("frame"), "y_axis": y_axis,
                        "status": rec.get("status"), "source": rec.get("source"),
                        "regions": regions, "n_images": sum(1 for r in regions if r["image"]),
                        "in_coords_frame": bool(in_coords)})
        out.sort(key=lambda d: -d["n_images"])
        self._cache["spatial"] = out
        return out

    def _positions_in_coords(self, pos: pd.DataFrame, n: int = 12) -> bool:
        """Whether cell positions are the cells' places in the 3-D coordinates (a Spatial view then repeats the 3-D
        one): for up to ``n`` cells, the position lies within a cell's radius of the centre of its spots (x, y)."""
        try:
            if not (self.cd.n_spots and len(pos)):
                return False
            has_cells = self.cd._has_cell_id() if self.backed else "cell_id" in self.cd.spots.columns
            if not has_cells:
                return False
            cats = (list(self.cd._categories("cell_id")) if self.backed
                    else list(self.cd.spots["cell_id"].astype("category").cat.categories))
            by_name = {str(c): c for c in cats}
            names = [c for c in pos.index.astype(str) if c in by_name]
            if not names:
                return False
            pick = [names[i] for i in np.unique(np.linspace(0, len(names) - 1, min(n, len(names))).astype(int))]
            near = []
            for name in pick:
                xyz = np.asarray(self.cd.get_cell(by_name[name], columns="coords").coords, dtype=float)
                xyz = xyz[np.isfinite(xyz).all(1)]
                if len(xyz) < 3:
                    continue
                c = xyz.mean(0)
                radius = float(np.median(np.linalg.norm(xyz - c, axis=1))) or 1.0
                p = pos.loc[pos.index.astype(str) == name, ["x", "y"]].to_numpy(float)[0]
                near.append(float(np.linalg.norm(p - c[:2])) < 2 * radius)
            return bool(near) and float(np.mean(near)) >= 0.75
        except Exception:                       # unreadable: treat the positions as their own frame
            return False

    def spatial_points(self, key: str, region: Optional[str] = None) -> Dict[str, Any]:
        info = next((s for s in self.spatial() if s["key"] == key), None)
        if info is None:
            raise KeyError(key)
        pos = self.cd.cell_positions(key)
        ok = pos[["x", "y"]].notna().all(axis=1).to_numpy().copy()
        if region is not None:
            if "region" not in pos:
                raise KeyError(region)
            ok &= (pos["region"].astype(str) == str(region)).to_numpy()
        sub = pos[ok]

        def image_of(r: Optional[dict]) -> Optional[dict]:
            if not r or not r["image"]:
                return None
            rec = self._images()[r["image"]]
            return {"name": r["image"], "extent": [float(v) for v in rec.get("extent", [])], "kind": rec.get("kind")}

        out = {"key": key, "region": region, "unit": info["unit"], "y_axis": info["y_axis"],
               "cell_ids": [str(c) for c in sub.index],
               "x": sub["x"].astype(float).tolist(), "y": sub["y"].astype(float).tolist()}
        if region is not None:
            out["image"] = image_of(next((x for x in info["regions"] if x["name"] == region), None))
        else:
            # every region at once: the region of each cell and the image of each region, so a client can
            # switch sections (e.g. to follow the focused cell) without another request
            out["image"] = None
            out["regions"] = sub["region"].astype(str).tolist() if "region" in sub else None
            out["images"] = {x["name"]: image_of(x) for x in info["regions"] if x["image"]}
        return out

    def image_path(self, name: str) -> Path:
        rec = self._images().get(name)
        if rec is None:
            raise KeyError(name)
        return self.resolve(rec["path"])

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
    # Genome-coordinate views: tracks, intervals, contacts, distances, stats
    # ------------------------------------------------------------------

    def _store_location(self) -> Optional[str]:
        """The store as a URL, a local directory or a ``.cdz`` file (what the embedded readers open), else None
        (CSV, PDB ...)."""
        from chromdata.remote import is_url

        if not self.path:
            return None
        if is_url(self.path):
            return str(self.path)
        p = Path(self.path)
        return str(p) if p.is_dir() or (p.is_file() and p.name.lower().endswith(".cdz")) else None

    def resolve(self, path: str) -> Path:
        """Linked file path; relative paths are relative to the dataset's
        directory (where the .chromdata.zarr / .cdz lives)."""
        from chromdata.remote import is_url

        p = Path(path).expanduser()
        if not p.is_absolute() and self.path and not is_url(self.path):
            p = Path(self.path).parent / p
        return p

    def track_names(self) -> List[Dict[str, Any]]:
        """Numeric tracks: ``level`` is ``"bin"`` (``cd.bin_tracks``, one
        value per locus), ``"spot"`` (``cd.spot_tracks``, per spot) or
        ``"cell_bin"`` (a linked cell x bin matrix, one track per resolution,
        averaged over the cells in scope).  ``grid`` names the bins a track
        is reported on: tracks of one grid can be requested together."""
        out = []
        for level, table in (("bin", self.cd.bin_tracks), ("spot", self.cd.spot_tracks)):
            dtypes = table.dtypes      # (a backed table reads no data for this)
            out += [{"name": str(c), "level": level, "grid": "spots"} for c in table.columns
                    if pd.api.types.is_numeric_dtype(dtypes[c])]
        for name, t in self._cell_bin_tracks().items():
            out.append({"name": name, "level": "cell_bin", "grid": name, "label": t["label"],
                        "resolution": t["resolution"], "n_cells": t["n_cells"]})
        return out

    # ---- cell x bin matrices (uns['linked_bin_matrices']: linked AnnData, var bin_id -> bins) ----

    def _cell_bin_tracks(self) -> Dict[str, Dict[str, Any]]:
        """``<key>@<res>kb`` -> {key, resolution, label, n_cells}; the files are opened lazily."""
        if "cell_bin" in self._cache:
            return self._cache["cell_bin"]
        recs = self.cd.uns.get("linked_bin_matrices") if isinstance(self.cd.uns, dict) else None
        out: Dict[str, Dict[str, Any]] = {}
        embedded = self._embedded_bin_matrices()
        items = {str(k): v for k, v in (recs or {}).items() if isinstance(v, dict) and k not in embedded}
        items.update({k: {"label": a["label"], "path": None} for k, (_, a) in embedded.items()})
        for key, rec in items.items():
            if rec.get("path") is None:
                if key not in embedded:
                    continue
            elif not self.resolve(rec["path"]).exists():
                continue
            m = self._bin_matrix(str(key))
            label = str(rec.get("label") or key)
            for res in sorted(m["var"]["resolution"].unique(), reverse=True):
                size = _fmt_bp(int(res))
                name = f"{key}@{size.replace(' ', '')}" if res else str(key)
                out[name] = {"key": str(key), "resolution": int(res), "n_cells": len(m["rows"]),
                             "label": f"{label} {size}" if res else label}
        self._cache["cell_bin"] = out
        return out

    def _embedded_bin_matrices(self) -> Dict[str, Any]:
        """``{key: (zarr group, attrs)}`` of the cell x bin matrices embedded in the store (one request)."""
        if "embedded_bin" not in self._cache:
            from chromdata.embedded import open_anndata_groups

            loc = self._store_location()
            self._cache["embedded_bin"] = open_anndata_groups(loc, "linked_bin_matrices") if loc else {}
        return self._cache["embedded_bin"]

    def _bin_matrix(self, key: str) -> Dict[str, Any]:
        cache = self._cache.setdefault("bin_matrix", {})
        if key not in cache:
            import anndata as ad

            emb = self._embedded_bin_matrices().get(key)
            if emb is not None:      # embedded copy: X is read straight from the Zarr array
                from types import SimpleNamespace

                from chromdata.embedded import bin_matrix_var

                grp = emb[0]
                adata = SimpleNamespace(X=grp["X"], var=bin_matrix_var(grp), obs_names=_LazyNames(
                    lambda: ad.io.read_elem(grp["obs"]).index, int(emb[1]["n_obs"])))
            else:
                rec = self.cd.uns["linked_bin_matrices"][key]
                adata = ad.read_h5ad(self.resolve(rec["path"]), backed="r")
            var = adata.var
            bins = self.cd.bins
            ids = var["bin_id"].to_numpy(np.int64)
            v = pd.DataFrame({"col": np.arange(len(ids)), "chrom": bins["chrom"].astype(str).to_numpy()[ids],
                              "start": bins["start"].to_numpy()[ids], "end": bins["end"].to_numpy()[ids],
                              "resolution": (var["resolution"].to_numpy(np.int64) if "resolution" in var
                                             else np.zeros(len(ids), np.int64))})
            cache[key] = {"adata": adata, "var": v, "blocks": {},
                          "rows": _LazyRows(adata.obs_names) if isinstance(adata.obs_names, _LazyNames)
                          else {str(c): i for i, c in enumerate(adata.obs_names)}}
        return cache[key]

    def _cell_bin_values(self, name: str, chrom: str, start, end, cell_id, group, agg: str):
        t = self._cell_bin_tracks()[name]
        m = self._bin_matrix(t["key"])
        v = m["var"]
        sel = v[(v["chrom"] == str(chrom)) & (v["resolution"] == t["resolution"])].sort_values("start")
        if start is not None:
            sel = sel[sel["end"] > int(start)]
        if end is not None:
            sel = sel[sel["start"] < int(end)]
        bk = (name, str(chrom))
        if bk not in m["blocks"]:                      # one chromosome of all cells: read once
            allc = v[(v["chrom"] == str(chrom)) & (v["resolution"] == t["resolution"])]["col"].to_numpy()
            lo, hi = (int(allc.min()), int(allc.max()) + 1) if len(allc) else (0, 0)
            m["blocks"][bk] = (lo, np.asarray(m["adata"].X[:, lo:hi], dtype=np.float32))
        lo, block = m["blocks"][bk]
        rows = m["rows"]
        if cell_id is not None:
            r = [rows[str(cell_id)]] if str(cell_id) in rows else []
        elif group is not None:
            r = sorted(rows[c] for c in self.group_cells(group) if c in rows)
        else:
            r = None
        x = block[:, sel["col"].to_numpy() - lo] if r is None else block[np.asarray(r, dtype=np.int64)][:, sel["col"].to_numpy() - lo]
        n = np.isfinite(x).sum(axis=0)
        with warnings.catch_warnings():                # all-NaN bins: NaN, quietly
            warnings.simplefilter("ignore", RuntimeWarning)
            f = {"mean": np.nanmean, "median": np.nanmedian, "max": np.nanmax}[agg]
            val = f(x, axis=0) if x.shape[0] else np.full(len(sel), np.nan)
        return sel, val, n

    def _track_values(self, name: str) -> np.ndarray:
        """Spot-aligned float values of one track (bin tracks broadcast)."""
        if name in self.cd.bin_tracks.columns:
            vals = self.cd.bin_tracks[name].to_numpy(dtype=np.float64)
            return vals[self._arrays()["bin_id"]]
        return self.cd.spot_tracks[name].to_numpy(dtype=np.float64)

    def _select(self, chrom: str, start=None, end=None, cell_id=None, trace_id=None,
                group=None) -> np.ndarray:
        a = self._arrays()
        _one_scope(cell_id, group)
        mask = a["chrom"] == str(chrom)
        if start is not None:
            mask &= a["end"] > int(start)
        if end is not None:
            mask &= a["start"] < int(end)
        if cell_id is not None and a["cell"] is not None:
            mask &= a["cell"] == str(cell_id)
        if trace_id is not None:
            mask &= a["trace"] == str(trace_id)
        if group is not None:
            mask &= self._group_spot_mask(group)
        return np.flatnonzero(mask)

    def tracks(self, names: List[str], chrom: str, start=None, end=None,
               cell_id=None, agg: str = "mean", group=None) -> Dict[str, Any]:
        known = {t["name"]: t for t in self.track_names()}
        unknown = [n for n in names if n not in known]
        if unknown:
            raise KeyError(unknown[0])
        if agg not in ("mean", "median", "max"):
            raise ValueError("agg must be mean, median or max")
        if str(chrom) == GENOME:
            return self._genome_tracks(names, cell_id, agg, group)
        grids = {known[n]["grid"] for n in names}
        if len(grids) > 1:
            raise ValueError(f"tracks on different bins cannot be requested together: {sorted(grids)}")
        if names and known[names[0]]["level"] == "cell_bin":
            _one_scope(cell_id, group)
            out_vals, sel, n = {}, None, None
            for name in names:
                sel, val, n = self._cell_bin_values(name, chrom, start, end, cell_id, group, agg)
                out_vals[name] = [None if not np.isfinite(x) else float(x) for x in val]
            return {"chrom": str(chrom), "group": group,
                    "bin_starts": [int(x) for x in sel["start"]], "bin_ends": [int(x) for x in sel["end"]],
                    "n_spots": [int(x) for x in n], "values": out_vals}
        if self._index_segments():          # spot tracks of a sample of the matching cells
            mask = self._run_mask([chrom], self._scope_cells(cell_id, group))
            ranges, n_used, n_cells, used, total = self._sample(mask, STATS_MAX_SPOTS)
            sub = Dataset(id=self.id, name=self.name, path=self.path, cd=self.cd._build22(crd=ranges))
            out = sub.tracks(names, chrom, start, end, agg=agg)
            out.update(group=group, note=f"{n_used:,} of {n_cells:,} cells (random sample)" if used < total else None)
            return out
        a = self._arrays()
        idx = self._select(chrom, start, end, cell_id, group=group)
        df = pd.DataFrame({"start": a["start"][idx], "end": a["end"][idx]})
        for n in names:
            df[n] = self._track_values(n)[idx]
        g = df.groupby("start", sort=True)
        out = g[names].agg(agg) if names else pd.DataFrame(index=g.size().index)
        return {
            "chrom": str(chrom),
            "group": group,
            "bin_starts": [int(v) for v in out.index],
            "bin_ends": [int(v) for v in g["end"].max().to_numpy()],
            "n_spots": [int(v) for v in g.size().to_numpy()],
            "values": {n: [None if not np.isfinite(v) else float(v) for v in out[n].to_numpy()]
                       for n in names},
        }

    def _interval_table(self, key: str) -> Optional[pd.DataFrame]:
        """``cd.intervals[key]`` (typed) first, else a ``cd.results`` table."""
        df = self.cd.intervals.get(key)
        if df is None:
            df = self.cd.results.get(key)
        if isinstance(df, pd.DataFrame) and {"chrom", "start", "end"} <= set(df.columns):
            return df
        return None

    def interval_tables(self) -> List[Dict[str, Any]]:
        out, seen = [], set()
        for key, val in list(self.cd.intervals.items()) + list(self.cd.results.items()):
            if key in seen:
                continue
            if isinstance(val, pd.DataFrame) and {"chrom", "start", "end"} <= set(val.columns):
                kind = val.attrs.get("kind") if key in self.cd.intervals else None
                out.append({"key": str(key), "n": int(len(val)), "kind": kind})
                seen.add(key)
        return out

    def cluster_tables(self) -> List[Dict[str, Any]]:
        """The multi-way contact tables (``cd.clusters``): key, counts, per cell or bulk, assay, the table a
        filtered one was made from."""
        out = []
        for key, t in (getattr(self.cd, "clusters", None) or {}).items():
            attrs = t.attrs or {}
            out.append({"key": str(key), "n_clusters": int(t.n_clusters), "n_fragments": int(t.n_members),
                        "per_cell": t.cells is not None, "assay": attrs.get("assay"),
                        "filtered_from": attrs.get("filtered_from")})
        return out

    def clusters(self, key: str, chrom: str, start: int, end: int, cell_id: Optional[str] = None,
                 group: Optional[str] = None, min_size: int = 2, max_size: Optional[int] = None,
                 limit: int = 400) -> Dict[str, Any]:
        """The clusters with fragments in ``chrom:start-end`` (of one cell, a group's cells or all), as a cluster
        track draws them: per cluster its size (all chromosomes), fragments on this chromosome, their span and
        the fragments in the window.  Beyond ``limit`` clusters, those with the most fragments in the window are
        kept (``n_clusters`` counts them all); the rows go by span start."""
        tables = getattr(self.cd, "clusters", None) or {}
        if key not in tables:
            raise KeyError(key)
        if str(chrom) == GENOME:
            raise ValueError("clusters are drawn in a window of one chromosome")
        t = tables[key]
        cells = None
        if t.cells is not None:
            if cell_id is not None:
                cells = [cell_id]
            elif group is not None and group != ALL_CELLS:
                cells = self.group_cells(group)
        f = t.region(str(chrom), int(start), int(end), min_size=min_size, max_size=max_size, cells=cells)
        if not len(f):
            return {"key": key, "chrom": str(chrom), "start": int(start), "end": int(end), "n_clusters": 0,
                    "clusters": []}
        g = f.groupby("cluster", sort=False)
        per = g.agg(n=("start", "size"), size=("size", "first"), chrom_size=("chrom_size", "first"),
                    span_start=("span_start", "first"), span_end=("span_end", "first"))
        if "cell_id" in f:
            per["cell"] = g["cell_id"].first().astype(str)
        n_all = len(per)
        if n_all > limit:
            per = per.sort_values(["n", "span_start"], ascending=[False, True], kind="stable").head(limit)
        per = per.sort_values(["span_start", "span_end"], kind="stable")
        frags = {c: list(zip(s.tolist(), e.tolist())) for c, (s, e) in
                 ((c, (d["start"], d["end"])) for c, d in f[f["cluster"].isin(per.index)].groupby("cluster"))}
        return {
            "key": key, "chrom": str(chrom), "start": int(start), "end": int(end), "n_clusters": int(n_all),
            "clusters": [{"id": int(c), "cell": r.get("cell"), "size": int(r["size"]),
                          "chrom_size": int(r["chrom_size"]), "span": [int(r["span_start"]), int(r["span_end"])],
                          "fragments": [[int(a), int(b)] for a, b in frags[c]]}
                         for c, r in per.iterrows()],
        }

    def store_tree(self) -> Dict[str, Any]:
        """The store's on-disk structure (``.chromdata.zarr`` / ``.cdz``, local or at a URL; see
        store_tree.py); cached."""
        from chromdata.remote import is_url
        from chromdata.zarrcd import container_kind

        from .store_tree import remote_store_tree, store_tree

        if "store_tree" not in self._cache and self.path and is_url(self.path):
            self._cache["store_tree"] = remote_store_tree(str(self.path))
        if "store_tree" not in self._cache:
            p = Path(self.path) if self.path else None
            if p is None or not p.exists() or container_kind(p) not in ("zarr", "cdz"):
                raise LookupError("this dataset is not a .chromdata.zarr / .cdz store (nothing to list)")
            self._cache["store_tree"] = store_tree(p)
        return self._cache["store_tree"]

    def genome_layout(self) -> List[Dict[str, Any]]:
        """The chromosomes end to end, for the whole-genome view (``chrom="*"``): name, offset
        (bp before it) and length — the largest extent of its bins / spots and of any contact
        map, in natural order."""
        if "genome" not in self._cache:
            length: Dict[str, int] = {}
            for c in self.chrom_table():
                length[c["name"]] = max(length.get(c["name"], 0), int(c["end"]))
            for m in self.contact_maps():
                for c in m.get("chroms") or []:
                    length[c["name"]] = max(length.get(c["name"], 0), int(c["length"]))
            out, off = [], 0
            for name in sorted(length, key=natural_chrom_key):
                out.append({"name": name, "offset": off, "length": length[name]})
                off += length[name]
            self._cache["genome"] = out
        return self._cache["genome"]

    def _genome_offsets(self) -> Dict[str, int]:
        return {c["name"]: c["offset"] for c in self.genome_layout()}

    def _genome_tracks(self, names: List[str], cell_id, agg: str, group) -> Dict[str, Any]:
        """Tracks over the whole genome: each chromosome's bins in genome coordinates; beyond
        MAX_GENOME_TRACK_BINS bins, k consecutive bins of a chromosome are pooled (``agg``)."""
        layout = self.genome_layout()
        parts = []
        for c in layout:
            d = self.tracks(names, c["name"], None, None, cell_id, agg, group)
            if not d["bin_starts"]:
                continue
            f = pd.DataFrame({"chrom": c["name"], "off": c["offset"], "start": d["bin_starts"],
                              "end": d["bin_ends"], "n": d["n_spots"]})
            for n in names:
                f[n] = np.array([np.nan if v is None else v for v in d["values"][n]], dtype=np.float64)
            parts.append(f)
        if not parts:
            return {"chrom": GENOME, "group": group, "bin_starts": [], "bin_ends": [], "n_spots": [],
                    "values": {n: [] for n in names}}
        df = pd.concat(parts, ignore_index=True)
        if len(df) > MAX_GENOME_TRACK_BINS:          # k consecutive bins of a chromosome pooled
            k = int(np.ceil(len(df) / MAX_GENOME_TRACK_BINS))
            df["win"] = df.groupby("off", sort=False).cumcount() // k
            g = df.groupby(["off", "win"], sort=True)
            with warnings_ignored():
                vals = g[names].agg({"mean": "mean", "median": "median", "max": "max"}[agg]) if names else None
            first = g.agg(chrom=("chrom", "first"), start=("start", "min"), end=("end", "max"), n=("n", "sum"))
            df = first.reset_index().join(vals.reset_index(drop=True)) if names else first.reset_index()
        return {
            "chrom": GENOME, "group": group,
            "bin_starts": [int(v) for v in df["off"] + df["start"]],
            "bin_ends": [int(v) for v in df["off"] + df["end"]],
            "n_spots": [int(v) for v in df["n"]],
            "values": {n: [None if not np.isfinite(v) else float(v) for v in df[n].to_numpy()] for n in names},
        }

    def intervals(self, key: str, chrom: str, start=None, end=None) -> Dict[str, Any]:
        df = self._interval_table(key)
        if df is None:
            raise KeyError(key)
        if str(chrom) == GENOME:  # whole genome: every row, in genome coordinates
            off = df["chrom"].astype(str).map(self._genome_offsets())
            df = df[off.notna()].copy()
            off = off[off.notna()].astype(np.int64)
            df["start"] = df["start"].astype(np.int64) + off
            df["end"] = df["end"].astype(np.int64) + off
            start = end = None
            m = np.ones(len(df), dtype=bool)
        else:
            m = df["chrom"].astype(str) == str(chrom)
        if start is not None:
            m &= df["end"] > int(start)
        if end is not None:
            m &= df["start"] < int(end)
        sel = df[m]

        def cell(v):
            if isinstance(v, (float, np.floating)) and not np.isfinite(v):
                return None
            if isinstance(v, (int, float, np.integer, np.floating)):
                return _num(v)
            return str(v)

        return {"columns": [str(c) for c in sel.columns],
                "rows": [[cell(v) for v in row] for row in sel.itertuples(index=False)]}

    # -- contact maps ----------------------------------------------------

    def _link_records(self, family: str) -> Dict[str, dict]:
        raw = self.cd.uns.get(family) if isinstance(self.cd.uns, dict) else None
        if not isinstance(raw, dict):
            return {}
        if "path" in raw:
            return {"default": raw}
        return {str(k): v for k, v in raw.items() if isinstance(v, dict) and v.get("path")}

    def contact_maps(self) -> List[Dict[str, Any]]:
        if "contact_maps" not in self._cache:
            out = []
            embedded = self._embedded_maps()
            for key, e in embedded.items():
                per = e.kind == "per_cell"
                out.append({"key": key, "kind": "scool" if per else ("mcool" if len(e.resolutions) > 1 else "cool"),
                            "label": e.label, "resolutions": list(e.resolutions),
                            "chroms": [{"name": c, "length": n} for c, n in e.chromsizes().items()],
                            "per_cell": per, "n_cells": int(e.meta.get("n_cells") or 0) if per else 0,
                            "balanced": bool(e.meta.get("has_weights")), "embedded": True})
            for family in ("linked_cool", "linked_scool"):
                for key, rec in self._link_records(family).items():
                    if key in embedded:      # the embedded copy wins: it needs no external file
                        continue
                    path = self.resolve(str(rec["path"]))
                    if not path.is_file():
                        continue
                    try:
                        out.append(self._describe_contacts(key, rec, path, family))
                    except Exception as exc:  # unreadable file: skip, but say why
                        out.append({"key": key, "kind": "error", "label": str(rec.get("label") or key),
                                    "error": f"{type(exc).__name__}: {exc}", "resolutions": [],
                                    "chroms": [], "per_cell": False, "n_cells": 0})
            self._cache["contact_maps"] = out
        return self._cache["contact_maps"]

    def _describe_contacts(self, key: str, rec: dict, path: Path, family: str) -> Dict[str, Any]:
        import cooler

        cells = []
        if family == "linked_scool":
            kind, uris = "scool", []
            import h5py

            with h5py.File(path, "r") as f:  # cooler's tree walk costs minutes on a 30k-cell file
                cells = [f"/cells/{name}" for name in f["cells"]]
            self._cache[("scool_cells", str(path))] = set(cells)  # listing is slow
            first = f"{path}::{cells[0]}" if cells else str(path)
            resolutions = [int(cooler.Cooler(first).binsize or 0)]
        else:
            uris = cooler.fileops.list_coolers(str(path))
            kind = "mcool" if any("/resolutions/" in u for u in uris) else "cool"
        if kind == "mcool":
            resolutions = sorted(int(u.rsplit("/", 1)[-1]) for u in uris if "/resolutions/" in u)
            first = f"{path}::/resolutions/{resolutions[0]}"
        elif kind == "cool":
            first = str(path)
            resolutions = [int(cooler.Cooler(first).binsize or 0)]
        clr = cooler.Cooler(first)
        chroms = [{"name": str(c), "length": int(n)} for c, n in clr.chromsizes.items()]
        return {"key": key, "kind": kind, "label": str(rec.get("label") or key),
                "resolutions": resolutions, "chroms": chroms,
                "per_cell": kind == "scool", "n_cells": len(cells),
                "balanced": "weight" in clr.bins().columns}

    def contacts(self, key: str, chrom: str, start=None, end=None, resolution=None,
                 balance: bool = False, cell: Optional[str] = None, group: Optional[str] = None,
                 ratio_to: Optional[str] = None, smooth: int = 1) -> bytes:
        _one_scope(cell, group)
        if ratio_to is not None:
            return self._contacts_ratio(key, chrom, start, end, resolution, balance, cell, group, ratio_to, smooth)

        info = next((m for m in self.contact_maps() if m["key"] == key and m["kind"] != "error"), None)
        if info is None:
            raise KeyError(key)
        if info.get("embedded"):
            # no cooler here: importing it creates multiprocessing semaphores, which a sandboxed container (Cloudflare
            # Containers) does not have; embedded maps are read straight from Zarr
            return self._embedded_contacts(key, info, chrom, start, end, resolution, balance, cell, group)
        import cooler
        family = "linked_scool" if info["kind"] == "scool" else "linked_cool"
        path = self.resolve(str(self._link_records(family)[key]["path"]))
        if str(chrom) == GENOME:
            return self._genome_contacts(key, info, path, resolution, balance, cell, group)
        length = next((c["length"] for c in info["chroms"] if c["name"] == chrom), None)
        if length is None:
            raise ValueError(f"unknown chromosome {chrom!r} in contact map {key!r}")
        lo = max(0, int(start or 0))
        hi = min(length, int(end or length))
        if hi <= lo:
            raise ValueError("empty region")
        if group is not None:
            if info["kind"] != "scool":
                raise ValueError(f"contact map {key!r} is not per-cell: a group needs a per-cell (.scool) map")
            return self._pseudobulk(key, path, group, chrom, lo, hi)
        if info["kind"] == "mcool":
            res = int(resolution) if resolution else next(
                (r for r in info["resolutions"] if (hi - lo) / r <= MAX_MATRIX_BINS), info["resolutions"][-1])
            if res not in info["resolutions"]:
                raise ValueError(f"resolution must be one of {info['resolutions']}")
            uri = f"{path}::/resolutions/{res}"
        elif info["kind"] == "scool":
            if cell is None:
                raise LookupError("per-cell contact map: pass cell=<cell id> or group=<group>")
            name = f"/cells/{cell}"
            if name not in self._scool_cells(path):
                raise KeyError(f"cell {cell!r} has no map in {key!r} ({self._scool_coverage(path)})")
            uri = f"{path}::{name}"
        else:
            uri = str(path)
        clr = cooler.Cooler(uri)
        balanced = bool(balance) and "weight" in clr.bins().columns
        region = (chrom, lo, hi)
        mat = clr.matrix(balance=balanced, sparse=False).fetch(region).astype(np.float32)
        bins = clr.bins().fetch(region)
        starts, ends = bins["start"].to_numpy(np.int64), bins["end"].to_numpy(np.int64)
        mat, starts, ends, note = _pool_square(mat, starts, ends, np.nansum)
        header = {"chrom": chrom, "start": lo, "end": hi, "resolution": int(clr.binsize or 0),
                  "value": "balanced" if balanced else "count", "unit": None,
                  "cell": cell, "group": None, "note": note}
        return encode_matrix(mat, starts, ends, header)

    def _contacts_ratio(self, key: str, chrom: str, start, end, resolution, balance: bool, cell: Optional[str],
                        group: Optional[str], ratio_to: str, smooth: int) -> bytes:
        """log2 of the map of ``cell`` / ``group`` over the map of the group ``ratio_to`` (``"all"``: every cell),
        each divided by its total in the window: where the two differ beyond their depths (e.g. a group with more
        short-range and fewer long-range contacts: red near the diagonal, blue away from it).  Both maps are summed
        over ``smooth`` x ``smooth`` pixels first (odd); pixels where the reference has fewer than
        ``RATIO_MIN_COUNT`` contacts after that are NaN; half a contact is added to both."""
        if cell is None and group is None:
            raise LookupError("a ratio needs cell=<cell id> or group=<group> for its numerator")
        k = int(smooth or 1)
        if k < 1 or k % 2 == 0:
            raise ValueError("smooth must be an odd number >= 1")
        a = decode_matrix(self.contacts(key, chrom, start, end, resolution, balance, cell, group))
        b = decode_matrix(self.contacts(key, chrom, start, end, resolution, balance, None, ratio_to))
        A = np.nan_to_num(np.asarray(a["matrix"], np.float64))
        B = np.nan_to_num(np.asarray(b["matrix"], np.float64))
        if A.shape != B.shape:
            raise ValueError("the two maps have different bins")
        ta, tb = A.sum(), B.sum()
        if ta <= 0 or tb <= 0:
            raise LookupError("no contacts in the window")
        A, B = _box_sum(A, k), _box_sum(B, k)
        with np.errstate(divide="ignore", invalid="ignore"):
            ratio = np.log2(((A + 0.5) / ta) / ((B + 0.5) / tb))
        ratio[B < RATIO_MIN_COUNT] = np.nan
        h = a["header"]
        ref = "all cells" if ratio_to == ALL_CELLS else ratio_to
        note = "; ".join(x for x in (h.get("note"), f"log2 over {ref}, each over its total in the window"
                                     + (f", {k} x {k} pixels summed" if k > 1 else "")) if x)
        header = {k_: v for k_, v in h.items() if k_ not in ("n_rows", "n_cols", "bin_starts", "bin_ends")}
        header.update(value="log2_ratio", unit=None, ratio_to=ratio_to, smooth=k, note=note)
        return encode_matrix(ratio.astype(np.float32), h["bin_starts"], h["bin_ends"], header)

    def _genome_contacts(self, key: str, info: dict, path: Path, resolution, balance: bool,
                         cell: Optional[str], group: Optional[str]) -> bytes:
        """The whole genome (chromosomes in :meth:`genome_layout` order) at most MAX_MATRIX_BINS
        bins: an .mcool at its finest resolution that fits, else bins pooled k × k within each
        chromosome.  Pixels are read straight from HDF5 (per cell for a group of a .scool) and
        summed into the output bins; balanced values use the bins' weights.  Cached (LRU)."""
        import cooler
        import h5py

        cache = self._cache.setdefault("genome_contacts", {})
        ck = (key, resolution, bool(balance), cell, group)
        if ck in cache:
            cache[ck] = cache.pop(ck)
            return cache[ck]
        total = sum(c["length"] for c in self.genome_layout())
        notes, n_cells = ["whole genome"], None
        if info["kind"] == "mcool":
            res = int(resolution) if resolution else next(
                (r for r in info["resolutions"] if total / r <= MAX_MATRIX_BINS), info["resolutions"][-1])
            if res not in info["resolutions"]:
                raise ValueError(f"resolution must be one of {info['resolutions']}")
            groups = [f"resolutions/{res}"]
        elif info["kind"] == "scool":
            available = self._scool_cells(path)
            if group is not None:
                names = [c for c in self.group_cells(group) if f"/cells/{c}" in available]
                if not names:
                    raise LookupError(f"no cell of group {group!r} has a map in {key!r} ({self._scool_coverage(path)})")
                if len(names) > PSEUDOBULK_MAX_CELLS:
                    rng = np.random.default_rng(0)
                    names = sorted(rng.choice(names, PSEUDOBULK_MAX_CELLS, replace=False).tolist(), key=natural_key)
                    notes.append(f"sum over {PSEUDOBULK_MAX_CELLS} random cells of the group")
                n_cells = len(names)
            elif cell is not None:
                if f"/cells/{cell}" not in available:
                    raise KeyError(f"cell {cell!r} has no map in {key!r} ({self._scool_coverage(path)})")
                names = [str(cell)]
            else:
                raise LookupError("per-cell contact map: pass cell=<cell id> or group=<group>")
            groups = [f"cells/{c}" for c in names]
        else:
            groups = [""]
        clr = cooler.Cooler(f"{path}::/{groups[0]}")

        def blocks(weight):
            step = 5_000_000
            with h5py.File(path, "r") as f:
                for g in groups:
                    grp = f[g] if g else f
                    n_pix = grp["pixels/bin1_id"].shape[0]
                    for s0 in range(0, n_pix, step):
                        yield (grp["pixels/bin1_id"][s0: s0 + step], grp["pixels/bin2_id"][s0: s0 + step],
                               grp["pixels/count"][s0: s0 + step].astype(np.float64))

        buf = self._genome_matrix(key, clr.bins()[:], int(clr.binsize or 0), blocks, balance, cell, group, notes, n_cells)
        cache[ck] = buf
        while len(cache) > PSEUDOBULK_CACHE:
            cache.pop(next(iter(cache)))
        return buf

    def _genome_matrix(self, key: str, bins: pd.DataFrame, binsize: int, blocks, balance: bool,
                       cell: Optional[str], group: Optional[str], notes: List[str], n_cells: Optional[int]) -> bytes:
        """Sum the pixel blocks ``blocks(weight)`` -> (bin1, bin2, count) into the whole-genome grid."""
        layout = self.genome_layout()
        offsets = {c["name"]: c["offset"] for c in layout}
        rank = {c["name"]: i for i, c in enumerate(layout)}
        total = sum(c["length"] for c in layout)
        chrom = bins["chrom"].astype(str).to_numpy()
        starts = bins["start"].to_numpy(np.int64)
        ends = bins["end"].to_numpy(np.int64)
        kept = [c for c in sorted(set(chrom) & set(offsets), key=rank.get)]
        n_kept = int(np.isin(chrom, kept).sum())
        if not n_kept:
            raise LookupError(f"contact map {key!r} has no chromosome of this dataset")
        k = max(1, int(np.ceil(n_kept / MAX_MATRIX_BINS)))
        out_idx = np.full(len(bins), -1, dtype=np.int64)
        o_starts, o_ends, n_out = [], [], 0
        for c in kept:
            ix = np.flatnonzero(chrom == c)                     # bins of a chromosome are contiguous
            m = int(np.ceil(len(ix) / k))
            out_idx[ix] = n_out + np.arange(len(ix)) // k
            o_starts += [offsets[c] + int(starts[ix[i * k]]) for i in range(m)]
            o_ends += [offsets[c] + int(ends[ix[min(len(ix), (i + 1) * k) - 1]]) for i in range(m)]
            n_out += m
        if k > 1:
            notes.append(f"{k}x{k} bins pooled")
        balanced = bool(balance) and "weight" in bins.columns
        weight = bins["weight"].to_numpy(np.float64) if balanced else None
        acc = np.zeros(n_out * n_out, dtype=np.float64)
        diag = np.zeros(n_out, dtype=np.float64)
        n_contacts = 0.0
        for b1, b2, v in blocks(weight):
            v = np.asarray(v, dtype=np.float64)
            n_contacts += float(v.sum())
            if weight is not None:
                v = v * weight[b1] * weight[b2]
            o1, o2 = out_idx[b1], out_idx[b2]
            ok = (o1 >= 0) & (o2 >= 0) & np.isfinite(v)
            o1, o2, v, same = o1[ok], o2[ok], v[ok], (b1 == b2)[ok]
            acc += np.bincount(o1 * n_out + o2, weights=v, minlength=n_out * n_out)
            diag += np.bincount(o1[same], weights=v[same], minlength=n_out)
        up = acc.reshape(n_out, n_out)
        mat = (up + up.T - np.diag(diag)).astype(np.float32)   # cool stores one triangle
        if weight is not None:                                 # bins without a weight: no value
            dead = np.ones(n_out, dtype=bool)
            live = out_idx[np.isfinite(weight) & (out_idx >= 0)]
            dead[live] = False
            mat[dead, :] = np.nan
            mat[:, dead] = np.nan
        header = {"chrom": GENOME, "start": 0, "end": total, "resolution": int(binsize) * k,
                  "value": "balanced" if balanced else "count", "unit": None,
                  "cell": cell if group is None else None, "group": group, "note": "; ".join(notes)}
        if n_cells is not None:
            header.update(n_cells=n_cells, n_contacts=n_contacts)
        return encode_matrix(mat, np.asarray(o_starts, np.int64), np.asarray(o_ends, np.int64), header)

    def _embedded_maps(self) -> Dict[str, Any]:
        """Contact maps embedded in the store (``embedded/contacts``), by key (one request opens them all)."""
        if "embedded_maps" not in self._cache:
            from chromdata.embedded import open_all

            loc = self._store_location()
            self._cache["embedded_maps"] = open_all(loc) if loc is not None else {}
        return self._cache["embedded_maps"]

    def _embedded_contacts(self, key: str, info: dict, chrom: str, start, end, resolution, balance: bool,
                           cell: Optional[str], group: Optional[str]) -> bytes:
        """The embedded counterpart of the .cool / .scool paths of :meth:`contacts`: a region of one
        cell, of a group (pseudo-bulk) or of a bulk map, or the whole genome."""
        e = self._embedded_maps()[key]
        per = info["kind"] == "scool"
        token = Path(f"embedded:{key}")
        notes: List[str] = []
        idx, n_cells, use_sum = None, None, False
        if per:
            index = self._cache.setdefault(("emb_cell_index", key), {c: i for i, c in enumerate(e.cells)})
            if group is not None:
                names = [c for c in self.group_cells(group) if c in index]
                if not names:
                    raise LookupError(f"no cell of group {group!r} has a map in {key!r} ({self._scool_coverage(token)})")
                # every cell of the map: the precomputed sums answer at once (no cell is read, nothing is subsampled)
                use_sum = len(names) == len(index) and e.has_sum()
                if not use_sum and len(names) > PSEUDOBULK_MAX_CELLS:
                    rng = np.random.default_rng(0)
                    names = sorted(rng.choice(names, PSEUDOBULK_MAX_CELLS, replace=False).tolist(), key=natural_key)
                    notes.append(f"sum over {PSEUDOBULK_MAX_CELLS} random cells of the group")
                n_cells, idx = len(names), (None if use_sum else [index[c] for c in names])
            elif cell is not None:
                if str(cell) not in index:
                    raise KeyError(f"cell {cell!r} has no map in {key!r} ({self._scool_coverage(token)})")
                idx = [index[str(cell)]]
            else:
                raise LookupError("per-cell contact map: pass cell=<cell id> or group=<group>")
        elif group is not None:
            raise ValueError(f"contact map {key!r} is not per-cell: a group needs a per-cell (.scool) map")
        chroms = {c["name"]: c["length"] for c in info["chroms"]}
        if str(chrom) == GENOME:
            cache = self._cache.setdefault("genome_contacts", {})
            ck = (key, resolution, bool(balance), cell, group)
            if ck in cache:
                cache[ck] = cache.pop(ck)
                return cache[ck]
            total = sum(c["length"] for c in self.genome_layout())
            res = int(resolution) if resolution else next(
                (r for r in info["resolutions"] if total / r <= MAX_MATRIX_BINS), info["resolutions"][-1])
            if res not in info["resolutions"]:
                raise ValueError(f"resolution must be one of {info['resolutions']}")
            buf = self._genome_matrix(key, e.bins(res), res,
                                      (lambda weight: e.iter_sum_pixels(res)) if use_sum else (lambda weight: e.iter_pixels(res, idx)),
                                      balance, cell, group, ["whole genome"] + notes, n_cells)
            cache[ck] = buf
            while len(cache) > PSEUDOBULK_CACHE:
                cache.pop(next(iter(cache)))
            return buf
        length = chroms.get(chrom)
        if length is None:
            raise ValueError(f"unknown chromosome {chrom!r} in contact map {key!r}")
        lo = max(0, int(start or 0))
        hi = min(length, int(end or length))
        if hi <= lo:
            raise ValueError("empty region")
        res = int(resolution) if resolution else next(
            (r for r in info["resolutions"] if (hi - lo) / r <= MAX_MATRIX_BINS), info["resolutions"][-1])
        if res not in info["resolutions"]:
            raise ValueError(f"resolution must be one of {info['resolutions']}")
        ck = (key, group, chrom, lo, hi, res, bool(balance))
        cache = self._cache.setdefault("pseudobulk", {})
        if group is not None and ck in cache:
            cache[ck] = cache.pop(ck)
            return cache[ck]
        b0, b1 = lo // res, min(-(-length // res), -(-hi // res))
        n = b1 - b0
        acc = np.zeros(n * n, dtype=np.float64)
        if use_sum:
            blocks = [e.sum_pixels(f"cis/{chrom}", res)]
        else:
            blocks = [e.region_pixels(chrom, b0, b1, res)] if not per else e.cell_pixel_blocks(f"cis/{chrom}", idx, res)
        for d in blocks:                       # blocks of a few million pixels: memory does not grow with the group
            d = d[(d[:, 0] >= b0) & (d[:, 1] < b1)]
            acc += np.bincount((d[:, 0] - b0) * n + (d[:, 1] - b0), weights=d[:, 2], minlength=n * n)
        up = acc.reshape(n, n)
        mat = up + up.T - np.diag(np.diag(up))
        bins = e.bins(res)
        f0 = e.first_bin(chrom, res)
        rows = bins.iloc[f0 + b0: f0 + b1]
        balanced = bool(balance) and "weight" in bins.columns and not per
        if balanced:
            w = rows["weight"].to_numpy(np.float64)
            mat = mat * w[:, None] * w[None, :]
        mat = mat.astype(np.float32)
        starts, ends = rows["start"].to_numpy(np.int64), rows["end"].to_numpy(np.int64)
        mat, starts, ends, note = _pool_square(mat, starts, ends, np.nansum)
        if note:
            notes.append(note)
        header = {"chrom": chrom, "start": lo, "end": hi, "resolution": int(res),
                  "value": "balanced" if balanced else "count", "unit": None,
                  "cell": cell if group is None else None, "group": group, "note": "; ".join(notes) or None}
        if group is not None:
            header.update(n_cells=n_cells, n_contacts=float(np.triu(up).sum()))
        buf = encode_matrix(mat, starts, ends, header)
        if group is not None:
            cache[ck] = buf
            while len(cache) > PSEUDOBULK_CACHE:
                cache.pop(next(iter(cache)))
        return buf

    def _scool_cells(self, path: Path) -> set:
        """``/cells/<name>`` URIs of a .scool (listing is slow: cached)."""
        cells = self._cache.get(("scool_cells", str(path)))
        if cells is None and str(path).startswith("embedded:"):    # an embedded map: read its cell list when needed
            e = self._embedded_maps()[str(path)[len("embedded:"):]]
            cells = self._cache[("scool_cells", str(path))] = {f"/cells/{c}" for c in e.cells}
        if cells is None:
            import cooler      # only for a linked file (cooler cannot be imported in a sandboxed container)

            cells = self._cache[("scool_cells", str(path))] = set(cooler.fileops.list_scool_cells(str(path)))
        return cells

    def _scool_coverage(self, path: Path) -> str:
        """Which cells a .scool covers, for error messages (e.g. only one section of the data)."""
        names = sorted(c.rsplit("/", 1)[-1] for c in self._scool_cells(path))
        if not names:
            return "it has no cells"
        return f"it covers {len(names):,} of {len(self._cells_table()):,} cells, e.g. {names[0]!r}"

    def _pseudobulk(self, key: str, path: Path, group: str, chrom: str, lo: int, hi: int) -> bytes:
        """Sum of a group's per-cell maps over a region (raw counts).

        Reads the pixels of each cell straight from HDF5 (bin1 index slice
        per cell), which is ~100× faster than a Cooler per cell; at most
        PSEUDOBULK_MAX_CELLS cells (a random subset beyond that, noted), and
        the last PSEUDOBULK_CACHE results are kept.
        """
        import cooler
        import h5py

        cache = self._cache.setdefault("pseudobulk", {})
        ck = (key, group, chrom, lo, hi)
        if ck in cache:
            cache[ck] = cache.pop(ck)  # LRU: most recent last
            return cache[ck]
        available = self._scool_cells(path)
        names = [c for c in self.group_cells(group) if f"/cells/{c}" in available]
        if not names:
            raise LookupError(f"no cell of group {group!r} has a map in {key!r} ({self._scool_coverage(path)})")
        notes = []
        if len(names) > PSEUDOBULK_MAX_CELLS:
            rng = np.random.default_rng(0)
            names = sorted(rng.choice(names, PSEUDOBULK_MAX_CELLS, replace=False).tolist(), key=natural_key)
            notes.append(f"sum over {PSEUDOBULK_MAX_CELLS} random cells of the group")
        first = cooler.Cooler(f"{path}::/cells/{names[0]}")
        b0, b1 = first.extent((chrom, lo, hi))
        bins = first.bins()[b0:b1]
        starts, ends = bins["start"].to_numpy(np.int64), bins["end"].to_numpy(np.int64)
        n = b1 - b0
        acc = np.zeros(n * n, dtype=np.float64)
        with h5py.File(path, "r") as f:
            for c in names:
                g = f["cells"][c]
                off = g["indexes/bin1_offset"][b0: b1 + 1]
                s0, s1 = int(off[0]), int(off[-1])
                if s1 <= s0:
                    continue
                i = g["pixels/bin1_id"][s0:s1] - b0
                j = g["pixels/bin2_id"][s0:s1] - b0
                ok = j < n
                acc += np.bincount(i[ok] * n + j[ok], weights=g["pixels/count"][s0:s1][ok], minlength=n * n)
        up = acc.reshape(n, n)
        mat = (up + up.T - np.diag(np.diag(up))).astype(np.float32)  # cool stores the upper triangle
        total = float(np.triu(up).sum())
        mat, starts, ends, note = _pool_square(mat, starts, ends, np.nansum)
        if note:
            notes.append(note)
        header = {"chrom": chrom, "start": lo, "end": hi, "resolution": int(first.binsize or 0),
                  "value": "count", "unit": None, "cell": None, "group": group,
                  "n_cells": len(names), "n_contacts": total, "note": "; ".join(notes) or None}
        buf = encode_matrix(mat, starts, ends, header)
        cache[ck] = buf
        while len(cache) > PSEUDOBULK_CACHE:
            cache.pop(next(iter(cache)))
        return buf

    # -- distances --------------------------------------------------------

    def _trace_bin_positions(self, idx: np.ndarray):
        """(traces, bins, P[T, N, 3]) — per-trace coordinates on the union of
        bins of ``idx`` (duplicate spots in a bin are averaged; missing = NaN)."""
        a = self._arrays()
        coords = self._coords()[idx]
        ok = np.isfinite(coords).all(axis=1)
        idx, coords = idx[ok], coords[ok]
        starts = a["start"][idx]
        bins, bin_pos = np.unique(starts, return_inverse=True)
        ends = pd.Series(a["end"][idx]).groupby(bin_pos).max().reindex(range(len(bins))).to_numpy()
        traces, tr_pos = np.unique(a["trace"][idx], return_inverse=True)
        T, N = len(traces), len(bins)
        acc = np.zeros((T, N, 3))
        cnt = np.zeros((T, N))
        np.add.at(acc, (tr_pos, bin_pos), coords)
        np.add.at(cnt, (tr_pos, bin_pos), 1)
        with np.errstate(invalid="ignore"):
            P = acc / cnt[..., None]
        P[cnt == 0] = np.nan
        return traces, bins, ends, P

    def distance(self, chrom: str, start=None, end=None, cell_id=None, trace_id=None,
                 stat: str = "median", threshold: Optional[float] = None, group=None,
                 _header: Optional[Dict[str, Any]] = None) -> bytes:
        if stat not in ("median", "mean", "contact"):
            raise ValueError("stat must be median, mean or contact")
        if str(chrom) == GENOME:
            raise ValueError("distance matrices are per chromosome: pick a chromosome")
        if self._index_segments():
            # a random subset of the matching traces, as many as the (traces x bins x bins) budget holds, is read
            cells = self._scope_cells(cell_id, group)
            mask = self._run_mask([chrom], cells, [trace_id] if trace_id is not None else None)
            b = self.cd.bins
            on = (b["chrom"].astype(str).to_numpy() == str(chrom))
            if start is not None:
                on &= b["end"].to_numpy() > int(start)
            if end is not None:
                on &= b["start"].to_numpy() < int(end)
            n_bins = max(1, min(int(on.sum()), MAX_MATRIX_BINS))
            keep = max(1, 60_000_000 // (n_bins * n_bins))
            ranges, n, n_traces, used, total = self._sample(mask, int(self.cd.n_spots), unit="trace", max_units=keep)
            if not ranges:
                raise LookupError("no spots with coordinates in this selection")
            n_cell = len(np.unique(self._runs()[mask]["cell"]))
            note = f"statistic over {n} of {n_traces} traces (random subset)" if n < n_traces else None
            return self._part(ranges).distance(chrom, start, end, stat=stat, threshold=threshold, _header={
                "trace_id": trace_id, "cell_id": cell_id, "group": group, "n_cells_matching": n_cell,
                "note_prefix": note})
        idx = self._select(chrom, start, end, cell_id, trace_id, group=group)
        if len(idx) == 0:
            raise LookupError("no spots with coordinates in this selection")
        traces, bins, ends, P = self._trace_bin_positions(idx)
        notes = []
        # coarsen bins so the matrix fits (average positions per block)
        k = int(np.ceil(len(bins) / MAX_MATRIX_BINS))
        if k > 1:
            nb = int(np.ceil(len(bins) / k))
            with np.errstate(invalid="ignore"), warnings_ignored():
                pad = np.full((P.shape[0], nb * k - P.shape[1], 3), np.nan)
                P = np.nanmean(np.concatenate([P, pad], axis=1).reshape(P.shape[0], nb, k, 3), axis=2)
            ends = np.array([ends[min(len(ends), (i + 1) * k) - 1] for i in range(nb)])
            bins = bins[::k]
            notes.append(f"{k} bins pooled per cell")
        T, N = P.shape[:2]
        budget = 60_000_000  # floats in the (T, N, N) stack
        if T * N * N > budget:
            keep = max(1, budget // (N * N))
            sel = np.random.default_rng(0).choice(T, keep, replace=False)
            P = P[np.sort(sel)]
            notes.append(f"statistic over {keep} of {T} traces (random subset)")
        with warnings_ignored():
            if stat == "median":
                mat = _nanmedian_pairs(P)
                value = "distance"
            else:
                D = np.linalg.norm(P[:, :, None, :] - P[:, None, :, :], axis=-1)  # (T, N, N)
            if stat == "contact":
                thr = float(threshold) if threshold is not None else 0.5 * float(np.nanmedian(D))
                valid = np.isfinite(D)
                mat = np.where(valid.sum(0) > 0, (np.where(valid, D, np.inf) < thr).sum(0) / np.maximum(valid.sum(0), 1), np.nan)
                value = "contact_frequency"
                notes.append(f"threshold {thr:.3g}")
            elif stat == "mean":
                mat = np.nanmean(D, axis=0)
                value = "distance"
        unit = self.cd.uns.get("xyz_unit") if isinstance(self.cd.uns, dict) else None
        header = {"chrom": chrom, "start": int(bins[0]), "end": int(ends[-1]),
                  "resolution": int(np.median(np.diff(bins))) if len(bins) > 1 else 0,
                  "value": value, "stat": stat, "unit": None if unit is None else str(unit),
                  "n_traces": int(len(traces)), "trace_id": trace_id, "cell_id": cell_id,
                  "group": group, "n_cells": self._n_cells_of(idx),
                  "note": "; ".join(notes) or None}
        if _header:      # a sample of a large store: the request's scope, and how the sample was drawn
            extra = dict(_header)
            prefix = extra.pop("note_prefix", None)
            header.update({k: v for k, v in extra.items() if k != "n_cells_matching"})
            if prefix:
                header["note"] = "; ".join([prefix] + notes)
        return encode_matrix(mat.astype(np.float32), bins, ends, header)

    # -- statistics -------------------------------------------------------

    def _stats_spots(self, chrom=None, cell_id=None, group=None) -> np.ndarray:
        a = self._arrays()
        _one_scope(cell_id, group)
        mask = np.isfinite(self._coords()).all(axis=1)
        if chrom:
            mask &= a["chrom"] == str(chrom)
        if cell_id is not None and a["cell"] is not None:
            mask &= a["cell"] == str(cell_id)
        if group is not None:
            mask &= self._group_spot_mask(group)
        return np.flatnonzero(mask)

    def _n_cells_of(self, idx: np.ndarray) -> Optional[int]:
        a = self._arrays()
        return None if a["cell"] is None else int(len(pd.unique(a["cell"][idx])))

    def _stats_sample(self, chrom, cell_id, group):
        """Large stores: (in-memory Dataset of a random sample of the matching cells, note or None)."""
        cells = self._scope_cells(cell_id, group)
        mask = self._run_mask([chrom] if chrom else None, cells)
        ranges, n, n_cells, used, total = self._sample(mask, STATS_MAX_SPOTS)
        note = f"{n:,} of {n_cells:,} cells (random sample)" if used < total else None
        return self._part(ranges), note

    def stats_rg(self, chrom=None, cell_id=None, group=None) -> Dict[str, Any]:
        if self._index_segments():
            part, note = self._stats_sample(chrom, cell_id, group)
            out = part.stats_rg(chrom)
            out.update(group=group, note=note)
            return out
        a = self._arrays()
        idx = self._stats_spots(chrom, cell_id, group)
        df = pd.DataFrame(self._coords()[idx], columns=["x", "y", "z"])
        df["trace"] = a["trace"][idx]
        g = df.groupby("trace", sort=False)
        cen = g[["x", "y", "z"]].transform("mean")
        df["d2"] = ((df[["x", "y", "z"]] - cen) ** 2).sum(axis=1)
        rg = np.sqrt(df.groupby("trace", sort=False)["d2"].mean())
        first = pd.Series(idx).groupby(df["trace"].to_numpy(), sort=False).first().reindex(rg.index)
        unit = self.cd.uns.get("xyz_unit") if isinstance(self.cd.uns, dict) else None
        return {"trace_ids": [str(t) for t in rg.index],
                "cell_ids": [None if a["cell"] is None else str(a["cell"][i]) for i in first.to_numpy()],
                "chroms": [str(a["chrom"][i]) for i in first.to_numpy()],
                "rg": [float(v) for v in rg.to_numpy()],
                "n_spots": [int(v) for v in g.size().reindex(rg.index).to_numpy()],
                "group": group, "n_cells": self._n_cells_of(idx),
                "unit": None if unit is None else str(unit)}

    def stats_scaling(self, chrom=None, cell_id=None, n_bins: int = 24, group=None) -> Dict[str, Any]:
        if self._index_segments():
            part, note = self._stats_sample(chrom, cell_id, group)
            out = part.stats_scaling(chrom, n_bins=n_bins)
            out.update(group=group, note=note)
            return out
        a = self._arrays()
        idx = self._stats_spots(chrom, cell_id, group)
        n_cells = self._n_cells_of(idx)
        order = np.lexsort((a["start"][idx], a["trace_code"][idx]))
        idx = idx[order]
        codes = a["trace_code"][idx]
        cut = np.flatnonzero(np.r_[True, codes[1:] != codes[:-1], True])
        groups = [idx[cut[i]:cut[i + 1]] for i in range(len(cut) - 1)]
        rng = np.random.default_rng(0)
        total = sum(len(g) * (len(g) - 1) // 2 for g in groups)
        if total > 30_000_000:  # sample traces to bound memory
            frac = 30_000_000 / total
            groups = [g for g in groups if rng.random() < frac]
        seps, dists = [], []
        for g in groups:
            if len(g) < 2:
                continue
            i, j = np.triu_indices(len(g), k=1)
            mid = (a["start"][g] + a["end"][g]) / 2
            seps.append(np.abs(mid[j] - mid[i]))
            dists.append(np.linalg.norm(self._coords()[g][j] - self._coords()[g][i], axis=1))
        unit = self.cd.uns.get("xyz_unit") if isinstance(self.cd.uns, dict) else None
        if not seps:
            return {"sep_bp": [], "median": [], "q25": [], "q75": [], "n_pairs": [],
                    "group": group, "n_cells": n_cells, "unit": None if unit is None else str(unit)}
        sep, dist = np.concatenate(seps), np.concatenate(dists)
        pos = sep > 0
        sep, dist = sep[pos], dist[pos]
        edges = np.geomspace(sep.min(), sep.max() * 1.0001, n_bins + 1)
        which = np.digitize(sep, edges) - 1
        out = {"sep_bp": [], "median": [], "q25": [], "q75": [], "n_pairs": []}
        for b in range(n_bins):
            d = dist[which == b]
            if len(d) == 0:
                continue
            q = np.percentile(d, [25, 50, 75])
            out["sep_bp"].append(float(np.sqrt(edges[b] * edges[b + 1])))
            out["q25"].append(float(q[0]))
            out["median"].append(float(q[1]))
            out["q75"].append(float(q[2]))
            out["n_pairs"].append(int(len(d)))
        out["unit"] = None if unit is None else str(unit)
        out["group"], out["n_cells"] = group, n_cells
        return out

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
        # the global (chrom, trace, start) order is computed once; filtering it keeps the order, and
        # lexsort is stable, so this equals sorting the selection itself
        order = self._draw_order()
        return order[mask[order]]

    def _draw_order(self) -> np.ndarray:
        """All spot indices sorted by chrom, trace, start (cached)."""
        if "draw_order" not in self._cache:
            a = self._arrays()
            start, trace, chrom = a["start"], a["trace_code"], a["chrom_rank"]
            n_tr = int(trace.max()) + 1 if len(trace) else 1
            n_st = int(start.max()) + 1 if len(start) else 1
            if len(start) and start.min() >= 0 and (int(chrom.max()) + 1) * n_tr * n_st < 2 ** 63:
                # one packed int64 key + a stable sort: same order as the lexsort, several times faster
                key = (chrom.astype(np.int64) * n_tr + trace) * n_st + start
                self._cache["draw_order"] = np.argsort(key, kind="stable")
            else:
                self._cache["draw_order"] = np.lexsort((start, trace, chrom))
        return self._cache["draw_order"]

    def geometry(self, flt: GeometryFilter) -> bytes:
        if self._index_segments():
            # the matching runs of a sample of whole cells, about max_points spots: the view is a random set of
            # cells, never the whole store (the header keeps the matching total, truncated when sampled)
            chroms = list(flt.chroms or []) + ([flt.region["chrom"]] if flt.region is not None else [])
            mask = self._run_mask(chroms or None, flt.cell_ids, flt.trace_ids)
            ranges, n, n_cells, used, total = self._sample(mask, flt.max_points)
            part = self._part(ranges)
            return encode_geometry(part, part.select(flt), flt.max_points, chrom_extent=self.chrom_table(),
                                   total_points=total, sample={"cells": n, "of_cells": n_cells} if used < total else None)
        if self.backed:
            sub = self._subset(flt)
            if sub is not None:
                # the same selection and encoding on the spots that can
                # match, read from disk; the extent stays the dataset's
                part = Dataset(id=self.id, name=self.name, path=self.path, cd=sub)
                return encode_geometry(part, part.select(flt), flt.max_points,
                                       chrom_extent=self.chrom_table())
        return encode_geometry(self, self.select(flt), flt.max_points)


MAX_MATRIX_BINS = 1000
#: the whole-genome view: ``chrom="*"`` (tracks, contact maps, intervals in genome coordinates)
GENOME = "*"
#: whole-genome tracks: bins pooled into at most this many windows
MAX_GENOME_TRACK_BINS = 4000
#: pseudo-bulk of a group over a per-cell (.scool) map: cells summed at most
PSEUDOBULK_MAX_CELLS = 20_000
#: pseudo-bulk matrices kept per dataset (LRU)
PSEUDOBULK_CACHE = 16
#: a ratio of two maps (``contacts(..., ratio_to=)``): pixels with fewer reference contacts (after smoothing) are NaN
RATIO_MIN_COUNT = 10


def _box_sum(m: np.ndarray, k: int) -> np.ndarray:
    """Sum of each pixel's k x k neighbourhood (k odd; zeros beyond the edges)."""
    if k <= 1:
        return m
    r = k // 2
    p = np.pad(m, r)
    c = np.pad(p.cumsum(0).cumsum(1), ((1, 0), (1, 0)))
    n0, n1 = m.shape
    return c[k:k + n0, k:k + n1] - c[:n0, k:k + n1] - c[k:k + n0, :n1] + c[:n0, :n1]


def _one_scope(cell_id, group) -> None:
    if cell_id is not None and group is not None:
        raise ValueError("pass either cell_id or group, not both")


class warnings_ignored:
    """Silence numpy's all-NaN slice / empty-mean warnings in a block."""

    def __enter__(self):
        import warnings

        self._ctx = warnings.catch_warnings()
        self._ctx.__enter__()
        warnings.simplefilter("ignore", category=RuntimeWarning)
        return self

    def __exit__(self, *exc):
        return self._ctx.__exit__(*exc)


def _pool_square(mat: np.ndarray, starts: np.ndarray, ends: np.ndarray, reduce):
    """Pool a square matrix by k×k blocks so it has at most MAX_MATRIX_BINS bins."""
    n = mat.shape[0]
    k = int(np.ceil(n / MAX_MATRIX_BINS))
    if k <= 1:
        return mat, starts, ends, None
    m = int(np.ceil(n / k))
    pad = m * k - n
    padded = np.pad(mat, ((0, pad), (0, pad)), constant_values=np.nan)
    with warnings_ignored():
        pooled = reduce(padded.reshape(m, k, m, k), axis=(1, 3)).astype(np.float32)
    new_ends = np.array([ends[min(n, (i + 1) * k) - 1] for i in range(m)])
    return pooled, starts[::k], new_ends, f"{k}x{k} bins pooled"


def encode_matrix(mat: np.ndarray, starts, ends, header: Dict[str, Any]) -> bytes:
    """Binary matrix payload (API.md): uint32 H | JSON header | float32 rows."""
    mat = np.asarray(mat, dtype="<f4")
    head = {**header, "n_rows": int(mat.shape[0]), "n_cols": int(mat.shape[1]),
            "bin_starts": [int(v) for v in starts], "bin_ends": [int(v) for v in ends]}
    raw = json.dumps(head, separators=(",", ":")).encode("utf-8")
    raw += b" " * (-len(raw) % 4)
    return struct.pack("<I", len(raw)) + raw + mat.tobytes()


def decode_matrix(buf: bytes) -> Dict[str, Any]:
    (h,) = struct.unpack_from("<I", buf, 0)
    header = json.loads(buf[4: 4 + h].decode("utf-8"))
    mat = np.frombuffer(buf, dtype="<f4", count=header["n_rows"] * header["n_cols"],
                        offset=4 + h).reshape(header["n_rows"], header["n_cols"])
    return {"header": header, "matrix": mat}


def _num(v) -> Any:
    """JSON-friendly number: ints stay ints."""
    f = float(v)
    return int(f) if f.is_integer() and abs(f) < 2**53 else f


def _nanmedian_pairs(P: np.ndarray) -> np.ndarray:
    """Per bin pair, the median over traces of the 3-D distance, for positions ``P`` (T, N, 3).

    Equals ``np.nanmedian(norm(P[:, :, None] - P[:, None]), axis=0)``, computed on the upper triangle
    only and without masked arrays (NaN sorts last; the median of the n finite values is the mean of the
    two middle ones)."""
    T, N = P.shape[:2]
    iu = np.triu_indices(N)
    d = P[:, iu[0]] - P[:, iu[1]]                                  # (T, M, 3)
    v = np.sort(np.sqrt(np.einsum("tmk,tmk->tm", d, d)), axis=0)   # (T, M), NaN last
    n = np.isfinite(v).sum(axis=0)
    lo = np.clip((n - 1) // 2, 0, T - 1)
    hi = np.clip(n // 2, 0, T - 1)
    med = 0.5 * (np.take_along_axis(v, lo[None], 0)[0] + np.take_along_axis(v, hi[None], 0)[0])
    med = np.where(n > 0, med, np.nan)
    out = np.empty((N, N), dtype=med.dtype)
    out[iu] = med
    out[iu[1], iu[0]] = med
    return out


def _segment_bounds(dataset: Dataset, idx: np.ndarray):
    """Split sorted spot indices into polyline segments.

    Returns ``(kept_idx, offsets)``: spots with non-finite coords are dropped
    and break the run, as does a change of trace or chromosome.
    """
    a = dataset._arrays()
    if len(idx) == 0:
        return idx, np.zeros(1, dtype=np.int64)
    coords = dataset._coords()[idx]
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
                    max_points: int = DEFAULT_MAX_POINTS,
                    chrom_extent: Optional[List[Dict[str, Any]]] = None,
                    total_points: Optional[int] = None, sample: Optional[Dict[str, int]] = None) -> bytes:
    """Encode the selected spots in the binary layout documented in API.md.

    ``chrom_extent`` (a :meth:`Dataset.chrom_table`) overrides the
    dataset's own, for a subset of a larger dataset; ``total_points`` /
    ``sample`` describe the whole selection when ``dataset`` is a sample
    of a large store."""
    a = dataset._arrays()
    kept, offsets = _segment_bounds(dataset, idx)
    total = len(kept)
    truncated = total > max_points or sample is not None
    if truncated:
        n_fit = int(np.searchsorted(offsets[1:], max_points, side="right"))
        if n_fit == 0:  # first segment alone exceeds the cap: cut it
            offsets = np.array([0, max_points], dtype=np.int64)
        else:
            offsets = offsets[: n_fit + 1]
        kept = kept[: offsets[-1]]

    positions = dataset._coords()[kept].astype(np.float32)
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
        "total_points": int(total if total_points is None else max(total, total_points)),
        "truncated": bool(truncated),
        "sample": sample,
        "segments": segments,
        "bbox": bbox,
        "chrom_extent": {c["name"]: [c["start"], c["end"]]
                         for c in (chrom_extent if chrom_extent is not None
                                   else dataset.chrom_table())},
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
        from chromdata.remote import is_url

        if is_url(path):      # s3:// https:// ...: opened backed over fsspec
            p = str(path).rstrip("/")
            base = p.rsplit("/", 1)[-1]
            name = base[: -len(".chromdata.zarr")] if base.endswith(".chromdata.zarr") else base
            # the embedded sections' metadata (three independent requests) is read while the store itself is read
            from concurrent.futures import ThreadPoolExecutor

            from chromdata.embedded import list_embedded_images, open_all, open_anndata_groups

            with ThreadPoolExecutor(max_workers=3) as pool:
                warm = {"embedded_maps": pool.submit(open_all, p),
                        "embedded_bin": pool.submit(open_anndata_groups, p, "linked_bin_matrices"),
                        "embedded_images": pool.submit(list_embedded_images, p)}
                cd = load_chromdata(p)
            ds = self.add(cd, name=name, path=p)
            for k, f in warm.items():
                try:
                    ds._cache[k] = f.result()
                except Exception:      # not readable: found again (and reported) when first used
                    pass
            # no pre-sort here: over HTTP it reads every spot's keys; the first geometry request sorts (once)
            return ds
        p = Path(path).expanduser().resolve()
        if not p.exists():
            raise FileNotFoundError(f"no such file: {p}")
        name = p.name[: -len(".chromdata.zarr")] if p.name.endswith(".chromdata.zarr") else p.stem
        ds = self.add(load_chromdata(p), name=name, path=str(p))
        if not ds._large():
            ds._draw_order()  # sort once at open, so the first overview request does not pay for it
        return ds

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
