"""Population container of the bulk deconvolution benchmark.

A *population* is a set of S structures on L loci with up to P copies per locus:

* ``chrom`` (L,), ``start`` / ``end`` (L,) - loci (0-based, half-open), genome order;
* ``coords`` (S, P, L, 3) float32 in nm (or model units), NaN = missing / absent copy
  (single-copy chromosomes use copy 0 only);
* optional ``lamina`` (S, P, L) - distance to the nuclear lamina (imaging truth);
* ``meta`` JSON (dataset, units, provenance).

Copy labels are arbitrary (imaging: "homolog 1 / 2"; models: copy 0 / 1); every metric in
``metrics.py`` is invariant to relabelling copies within a structure and chromosome.

Stored as ``.npz``.  :func:`from_chromdata` converts the output of
``uchrom.recon.bulk.deconv.deconvolve(method="igm")`` (a ChromData whose cells are structures,
traces chromosome copies, spots beads pointing at haploid bins) and :func:`from_arrays` the
engine's raw ``coords (S, N, 3)`` + ``bead_bin`` / ``bead_copy``; both map loci by midpoint.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd


@dataclass
class Population:
    chrom: np.ndarray
    start: np.ndarray
    end: np.ndarray
    coords: np.ndarray                       # (S, P, L, 3)
    lamina: Optional[np.ndarray] = None      # (S, P, L)
    meta: dict = field(default_factory=dict)

    def __post_init__(self):
        self.chrom = np.asarray(self.chrom).astype(str)
        self.start = np.asarray(self.start, np.int64)
        self.end = np.asarray(self.end, np.int64)
        self.coords = np.asarray(self.coords, np.float32)
        if self.coords.ndim == 3:                      # (S, L, 3) -> one copy
            self.coords = self.coords[:, None]
        assert self.coords.shape[2] == len(self.chrom) and self.coords.shape[3] == 3, self.coords.shape

    @property
    def n_structures(self) -> int:
        return self.coords.shape[0]

    @property
    def n_copies(self) -> int:
        return self.coords.shape[1]

    @property
    def n_loci(self) -> int:
        return len(self.chrom)

    def subset(self, idx) -> "Population":
        idx = np.asarray(idx)
        return Population(self.chrom, self.start, self.end, self.coords[idx],
                          None if self.lamina is None else self.lamina[idx], dict(self.meta))

    def loci_subset(self, keep) -> "Population":
        keep = np.asarray(keep)
        return Population(self.chrom[keep], self.start[keep], self.end[keep], self.coords[:, :, keep],
                          None if self.lamina is None else self.lamina[:, :, keep], dict(self.meta))

    def scaled(self, s: float) -> "Population":
        return Population(self.chrom, self.start, self.end, self.coords * np.float32(s),
                          None if self.lamina is None else self.lamina * np.float32(s), dict(self.meta))

    def save(self, path) -> None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        kw = {} if self.lamina is None else {"lamina": self.lamina.astype(np.float32)}
        np.savez_compressed(path, chrom=self.chrom, start=self.start, end=self.end,
                            coords=self.coords.astype(np.float32), meta=json.dumps(self.meta, default=str), **kw)

    @classmethod
    def load(cls, path) -> "Population":
        z = np.load(path, allow_pickle=False)
        return cls(z["chrom"], z["start"], z["end"], z["coords"], z["lamina"] if "lamina" in z.files else None,
                   json.loads(str(z["meta"])) if "meta" in z.files else {})


def median_consecutive(pop: Population, max_structures: int = 500) -> float:
    """Median distance between consecutive loci of one chromosome copy (the length unit)."""
    X = pop.coords[:max_structures]
    same = pop.chrom[1:] == pop.chrom[:-1]
    d = np.linalg.norm(np.diff(X, axis=2), axis=-1)[..., same]
    return float(np.nanmedian(d))


def map_to_loci(chrom_b, start_b, end_b, chrom_l, start_l, end_l) -> np.ndarray:
    """Locus -> bin index containing the locus midpoint (-1 if none)."""
    chrom_b = np.asarray(chrom_b).astype(str)
    out = np.full(len(chrom_l), -1, np.int64)
    mid = (np.asarray(start_l) + np.asarray(end_l)) // 2
    for c in np.unique(chrom_l):
        sb = np.flatnonzero(chrom_b == c)
        if not len(sb):
            continue
        o = sb[np.argsort(np.asarray(start_b)[sb])]
        k = np.searchsorted(np.asarray(start_b)[o], mid[chrom_l == c], side="right") - 1
        kk = np.clip(k, 0, None)
        ok = (k >= 0) & (mid[chrom_l == c] < np.asarray(end_b)[o][kk])
        li = np.flatnonzero(chrom_l == c)
        out[li[ok]] = o[k[ok]]
    return out


def from_arrays(coords, bead_bin, bead_copy, bins: pd.DataFrame, loci: Optional[pd.DataFrame] = None,
                meta: Optional[dict] = None) -> Population:
    """Engine output (coords (S, N, 3), bead -> haploid bin, bead -> copy) -> Population on
    ``loci`` (default: the bins themselves)."""
    coords = np.asarray(coords, np.float32)
    bead_bin = np.asarray(bead_bin, np.int64)
    bead_copy = np.asarray(bead_copy, np.int64)
    P = int(bead_copy.max()) + 1
    nb = len(bins)
    X = np.full((coords.shape[0], P, nb, 3), np.nan, np.float32)
    X[:, bead_copy, bead_bin] = coords
    pop = Population(bins["chrom"].to_numpy(), bins["start"].to_numpy(), bins["end"].to_numpy(), X, meta=meta or {})
    return pop if loci is None else remap(pop, loci)


def remap(pop: Population, loci: pd.DataFrame) -> Population:
    """Population on bins -> population on ``loci`` (the bin containing each locus midpoint)."""
    idx = map_to_loci(pop.chrom, pop.start, pop.end, loci["chrom"].astype(str).to_numpy(),
                      loci["start"].to_numpy(), loci["end"].to_numpy())
    X = np.full(pop.coords.shape[:2] + (len(loci), 3), np.nan, np.float32)
    ok = idx >= 0
    X[:, :, ok] = pop.coords[:, :, idx[ok]]
    meta = dict(pop.meta, remapped_to_loci=int(len(loci)), loci_unmapped=int((~ok).sum()))
    return Population(loci["chrom"].to_numpy(), loci["start"].to_numpy(), loci["end"].to_numpy(), X, meta=meta)


def from_chromdata(cd, loci: Optional[pd.DataFrame] = None) -> Population:
    """ChromData population (cells = structures, traces = chromosome copies) -> Population.

    The copy of a trace is ``cd.traces["copy"]`` when present, else the order of the trace
    among the traces of its (cell, chromosome).  Works on backed stores (reads per cell)."""
    bins = cd.bins.reset_index()
    bins = bins.rename(columns={bins.columns[0]: "bin_id"}) if "bin_id" not in bins else bins
    pos = {b: k for k, b in enumerate(bins["bin_id"].to_numpy())}
    cells = list(cd.cells.index) if cd.cells is not None and len(cd.cells) else None
    spots = cd.spots.copy()
    spots["cell_id"] = spots["cell_id"].astype(str)
    spots["trace_id"] = spots["trace_id"].astype(str)
    if cells is None:
        cells = list(pd.unique(spots["cell_id"]))
    cells = [str(c) for c in cells]
    tcopy = None
    if cd.traces is not None and "copy" in getattr(cd.traces, "columns", []):
        tcopy = {str(k): int(v) for k, v in cd.traces["copy"].items()}
    xyz = np.asarray(cd.coords, np.float32)
    spots["_row"] = np.arange(len(spots))
    spots["_bin"] = spots["bin_id"].map(pos).to_numpy()
    spots["_chrom"] = bins["chrom"].astype(str).to_numpy()[spots["_bin"].to_numpy()]
    if tcopy is None:
        tr = spots.drop_duplicates("trace_id")[["cell_id", "_chrom", "trace_id"]]
        tr["_copy"] = tr.groupby(["cell_id", "_chrom"]).cumcount()
        tcopy = dict(zip(tr.trace_id, tr._copy))
    spots["_copy"] = spots["trace_id"].map(tcopy).to_numpy()
    P = int(spots["_copy"].max()) + 1
    ci = {c: k for k, c in enumerate(cells)}
    X = np.full((len(cells), P, len(bins), 3), np.nan, np.float32)
    s_idx = spots["cell_id"].map(ci).to_numpy()
    X[s_idx, spots["_copy"].to_numpy(), spots["_bin"].to_numpy()] = xyz[spots["_row"].to_numpy()]
    pop = Population(bins["chrom"].to_numpy(), bins["start"].to_numpy(), bins["end"].to_numpy(), X,
                     meta={"source": "ChromData", "n_cells": len(cells), **(cd.uns.get("population_model", {})
                           if isinstance(cd.uns.get("population_model"), dict) else {})})
    return pop if loci is None else remap(pop, loci)


def load_any(path, loci: Optional[pd.DataFrame] = None) -> Population:
    """``.npz`` Population, engine ``.npz`` (coords, bead_bin, bead_copy, chrom/start/end of the
    haploid bins) or a ChromData store (``.chromdata.zarr`` / ``.cdz`` / ``.h5cd``)."""
    p = str(path)
    if p.endswith(".npz"):
        z = np.load(p, allow_pickle=False)
        if "bead_bin" in z.files:
            bins = pd.DataFrame({"chrom": z["chrom"].astype(str), "start": z["start"], "end": z["end"]})
            return from_arrays(z["coords"], z["bead_bin"], z["bead_copy"], bins, loci, meta={"source": p})
        pop = Population.load(p)
        return pop if loci is None else remap(pop, loci)
    from uchrom import ChromData  # the evaluation of a ChromData needs U-Chrom
    return from_chromdata(ChromData.read(p), loci)
