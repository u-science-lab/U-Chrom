"""Imaging truth structures for the simulation benchmark (numpy / pandas only).

A *truth* is one cell's haploid set of chromatin traces, stored as ``.npz``:
``chrom`` (L,), ``start`` / ``end`` (L,) (0-based, half-open), ``coords`` (L, 3) in nm
(``NaN`` = not detected), ``measured`` (L,) bool, plus JSON ``meta``.

Loaders
-------
``su2020_chr21``  Su et al. 2020 IMR90 chr21, 651 x 50 kb loci, one trace per imaged
    chromosome copy (Zenodo 3928890 ``chromosome21.tsv``).  Copies with detection
    >= ``min_detect`` are eligible; ``n`` of them are drawn with a seed.
``takei2021_25kb`` Takei et al. 2021 mESC DNA seqFISH+ 25 kb (4DN 4DNFIHF3JCBY): 20
    regions x 60 loci, traces already resolved per homolog (``Trace_ID`` =
    fov_cell_chrom_homolog).  Haploid set = for every chromosome the better-detected
    homolog of the cell.
``takei2021_1mb`` Takei et al. 2021 mESC DNA seqFISH+ 1 Mb (4DN 4DNFIFLJGGNR): 2,460
    loci genome-wide; one trace per (cell, chromosome) holding the spots of BOTH
    homologs (not resolved in the deposited table).  Homologs are separated here by a
    constrained 2-means (spots of the same locus go to different clusters; a cluster keeps
    at most one spot per locus, the one closest to its chain neighbours).  A
    chromosome is accepted only when its two clusters are well separated
    (centroid distance >= ``min_sep`` x mean radius of gyration) and the kept copy has
    detection >= ``min_detect``; cells are ranked by the number of accepted chromosomes.
    E14 is male: chrX is single copy and is only deduplicated (one spot per locus).
    Checked on the homolog-resolved 25 kb table (both homologs merged, then split):
    median 97.8 % of spots assigned to the right homolog, 83 % of (cell, chromosome)
    traces >= 95 % correct.
    This separation is a heuristic (no ground truth for the homolog assignment) and is
    flagged in ``meta``; ``--min-sep`` trades cells for confidence.

Missing loci
------------
Scoring always uses **measured loci only** (``measured`` mask).  For the forward model
(reads need a position for every locus) missing loci are, with ``missing="interp"``
(default), placed by linear interpolation along the chain between the nearest measured
neighbours (chain ends: copy of the nearest measured locus), flagged ``measured=False``;
with ``missing="drop"`` they get no reads at all (holes in the contact map, like
unmappable regions).  Interpolated positions are never compared with a model.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from contacts import sort_chroms


# --------------------------------------------------------------------------- container

def save_truth(path, chrom, start, end, coords, measured, meta) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(path, chrom=np.asarray(chrom).astype(str), start=np.asarray(start, np.int64),
                        end=np.asarray(end, np.int64), coords=np.asarray(coords, float),
                        measured=np.asarray(measured, bool), meta=json.dumps(meta))


def load_truth(path) -> dict:
    z = np.load(path, allow_pickle=False)
    t = {k: z[k] for k in ("chrom", "start", "end", "coords", "measured")}
    t["chrom"] = t["chrom"].astype(str)
    t["meta"] = json.loads(str(z["meta"]))
    return t


def interpolate_missing(chrom, start, coords):
    """Linear interpolation of NaN rows along each chromosome by genomic midpoint; ends copy
    the nearest measured locus.  Returns (coords_filled, measured)."""
    coords = np.array(coords, float)
    measured = np.isfinite(coords).all(1)
    mid = np.asarray(start, float)
    for c in np.unique(chrom):
        sel = np.flatnonzero(chrom == c)
        m = measured[sel]
        if m.sum() == 0:
            continue
        for k in range(3):
            coords[sel, k] = np.interp(mid[sel], mid[sel][m], coords[sel[m], k])
    return coords, measured


# --------------------------------------------------------------------------- Su 2020

def read_su2020(path) -> tuple[pd.DataFrame, np.ndarray]:
    """-> loci table (chrom, start, end) and coords (n_copies, 651, 3) in nm (x, y, z)."""
    df = pd.read_csv(path, sep="\t", usecols=[0, 1, 2, 3, 4])
    df.columns = ["z", "x", "y", "g", "copy"]
    nloc = int(df.g.nunique())
    g = df.g.iloc[:nloc].str.extract(r"^(chr[^:]+):(\d+)-(\d+)$")
    loci = pd.DataFrame({"chrom": g[0], "start": g[1].astype(np.int64) - 1, "end": g[2].astype(np.int64) - 1})
    X = df[["x", "y", "z"]].to_numpy(float).reshape(-1, nloc, 3)
    return loci, X


def su2020_truths(path, n: int = 5, min_detect: float = 0.95, seed: int = 1):
    loci, X = read_su2020(path)
    det = np.isfinite(X).all(2).mean(1)
    elig = np.flatnonzero(det >= min_detect)
    rng = np.random.default_rng(seed)
    pick = np.sort(rng.choice(elig, size=min(n, len(elig)), replace=False))
    out = []
    for k in pick:
        out.append({"chrom": loci.chrom.to_numpy().astype(str), "start": loci.start.to_numpy(),
                     "end": loci.end.to_numpy(), "coords": X[k],
                     "meta": {"dataset": "su2020_chr21", "copy_index": int(k), "detection": float(det[k]),
                              "min_detect": min_detect, "n_eligible": int(len(elig)), "seed": seed,
                              "unit": "nm"}})
    pop = [X[i] for i in range(len(X)) if i not in set(pick.tolist())]
    return out, {"chrom": loci.chrom.to_numpy().astype(str), "start": loci.start.to_numpy(),
                 "end": loci.end.to_numpy(), "population": np.stack(pop)}


# --------------------------------------------------------------------------- Takei 2021

FOFCT_COLS = ["Spot_ID", "Trace_ID", "X", "Y", "Z", "Chrom", "Chrom_Start", "Chrom_End", "Cell_ID", "Extra_Cell_ROI_ID"]


def read_fofct(path) -> pd.DataFrame:
    df = pd.read_csv(path, comment="#", header=None, names=FOFCT_COLS, low_memory=False)
    df = df.dropna(subset=["Trace_ID", "X"])
    df["Chrom_Start"] = df.Chrom_Start.astype(np.int64)
    df["Chrom_End"] = df.Chrom_End.astype(np.int64)
    for k in ("X", "Y", "Z"):
        df[k] = df[k].astype(float) * 1000.0          # micron -> nm
    return df


def _loci_table(df):
    loci = df[["Chrom", "Chrom_Start", "Chrom_End"]].drop_duplicates()
    loci = loci.assign(_k=loci.Chrom.map({c: i for i, c in enumerate(sort_chroms(loci.Chrom))}))
    loci = loci.sort_values(["_k", "Chrom_Start"]).reset_index(drop=True)
    return loci


def takei25kb_truths(path, n: int = 5, min_detect: float = 0.8, seed: int = 1):
    df = read_fofct(path)
    loci = _loci_table(df)
    key = {(c, s): i for i, (c, s) in enumerate(zip(loci.Chrom, loci.Chrom_Start))}
    df["li"] = [key[k] for k in zip(df.Chrom, df.Chrom_Start)]
    L = len(loci)
    per_cell = {}
    for cell, dc in df.groupby("Cell_ID"):
        coords = np.full((L, 3), np.nan)
        info = {}
        for chrom, dch in dc.groupby("Chrom"):
            best = None
            for tid, dt in dch.groupby("Trace_ID"):
                dt = dt.drop_duplicates("li")
                if best is None or len(dt) > len(best[1]):
                    best = (tid, dt)
            coords[best[1].li.to_numpy()] = best[1][["X", "Y", "Z"]].to_numpy()
            info[chrom] = str(best[0])
        per_cell[cell] = (coords, info)
    det = {c: np.isfinite(v[0]).all(1).mean() for c, v in per_cell.items()}
    elig = sorted([c for c, d in det.items() if d >= min_detect], key=str)
    rng = np.random.default_rng(seed)
    pick = list(rng.choice(elig, size=min(n, len(elig)), replace=False)) if elig else []
    out = [{"chrom": loci.Chrom.to_numpy().astype(str), "start": loci.Chrom_Start.to_numpy(),
            "end": loci.Chrom_End.to_numpy(), "coords": per_cell[c][0],
            "meta": {"dataset": "takei2021_25kb", "cell": str(c), "detection": float(det[c]),
                     "traces": per_cell[c][1], "min_detect": min_detect, "n_eligible": len(elig),
                     "seed": seed, "unit": "nm"}} for c in pick]
    pop = np.stack([v[0] for c, v in per_cell.items() if c not in set(pick)])
    return out, {"chrom": loci.Chrom.to_numpy().astype(str), "start": loci.Chrom_Start.to_numpy(),
                 "end": loci.Chrom_End.to_numpy(), "population": pop}


def dedupe_single_copy(xyz: np.ndarray, li: np.ndarray) -> np.ndarray:
    """Single-copy chromosome (chrX of a male line): keep one spot per locus, the one closest
    to the median of the spots at loci within +-2.  Returns labels in {0, -1}."""
    lab = np.zeros(len(xyz), int)
    for l in np.unique(li):
        cand = np.flatnonzero(li == l)
        if len(cand) < 2:
            continue
        nb = np.flatnonzero((np.abs(li - l) <= 2) & (li != l))
        ref = np.median(xyz[nb], 0) if len(nb) else np.median(xyz, 0)
        keep = cand[np.argmin(np.linalg.norm(xyz[cand] - ref, axis=1))]
        lab[cand[cand != keep]] = -1
    return lab


def split_homologs(xyz: np.ndarray, li: np.ndarray, n_iter: int = 30, seed: int = 0):
    """Constrained 2-means of one (cell, chromosome) spot cloud.

    ``xyz`` (S, 3) spots, ``li`` (S,) locus index.  Spots of one locus are assigned to
    different clusters when there are two or more; afterwards each cluster keeps at most
    one spot per locus (closest to the cluster's spots at neighbouring loci).
    Returns (labels (S,) in {0, 1, -1 = discarded}, separation ratio).
    """
    S = len(xyz)
    if S < 4:
        return np.zeros(S, int), 0.0
    D = np.linalg.norm(xyz[:, None] - xyz[None], axis=2)
    a, b = np.unravel_index(np.argmax(D), D.shape)
    cen = np.stack([xyz[a], xyz[b]])
    lab = np.zeros(S, int)
    groups = pd.Series(np.arange(S)).groupby(li).apply(list).tolist()
    for _ in range(n_iter):
        d0 = np.linalg.norm(xyz - cen[0], axis=1)
        d1 = np.linalg.norm(xyz - cen[1], axis=1)
        new = (d1 < d0).astype(int)
        for g in groups:
            if len(g) >= 2:                      # the spot preferring cluster 0 most goes to 0, the next to 1
                pref = d0[g] - d1[g]
                o = np.argsort(pref)
                new[g[o[0]]] = 0
                new[g[o[-1]]] = 1
        if (new == lab).all() and _ > 0:
            break
        lab = new
        for k in (0, 1):
            if (lab == k).any():
                cen[k] = xyz[lab == k].mean(0)
    # one spot per locus per cluster: closest to the median of the cluster's spots at loci within +-2
    out = lab.copy()
    for k in (0, 1):
        sel = np.flatnonzero(lab == k)
        loc = li[sel]
        for l in np.unique(loc):
            cand = sel[loc == l]
            if len(cand) < 2:
                continue
            nb = sel[(np.abs(loc - l) <= 2) & (loc != l)]
            ref = np.median(xyz[nb], 0) if len(nb) else cen[k]
            keep = cand[np.argmin(np.linalg.norm(xyz[cand] - ref, axis=1))]
            out[cand[cand != keep]] = -1
    rg = [np.sqrt(((xyz[out == k] - xyz[out == k].mean(0)) ** 2).sum(1).mean()) if (out == k).sum() > 1 else np.inf
          for k in (0, 1)]
    sep = float(np.linalg.norm(xyz[out == 0].mean(0) - xyz[out == 1].mean(0)) / np.mean(rg)) \
        if (out == 0).any() and (out == 1).any() else 0.0
    return out, sep


def takei1mb_cells(path, min_sep: float = 1.0, min_detect: float = 0.6, single_copy=("chrX", "chrY")):
    """Per cell: haploid coords (L, 3) from the homolog split, accepted chromosomes, stats.
    ``single_copy``: chromosomes present once (E14 is male: X and Y) - not split, deduplicated."""
    df = read_fofct(path)
    loci = _loci_table(df)
    key = {(c, s): i for i, (c, s) in enumerate(zip(loci.Chrom, loci.Chrom_Start))}
    df["li"] = [key[k] for k in zip(df.Chrom, df.Chrom_Start)]
    L = len(loci)
    nloc_chrom = loci.groupby("Chrom").size().to_dict()
    cells = {}
    for (cell, chrom), d in df.groupby(["Cell_ID", "Chrom"]):
        xyz = d[["X", "Y", "Z"]].to_numpy()
        li = d.li.to_numpy()
        if chrom in single_copy:
            lab, sep = dedupe_single_copy(xyz, li), float("inf")
        else:
            lab, sep = split_homologs(xyz, li)
        best = max((0, 1), key=lambda k: (lab == k).sum())
        sel = lab == best
        detect = sel.sum() / nloc_chrom[chrom]
        rec = cells.setdefault(cell, {"coords": np.full((L, 3), np.nan), "chroms": {}})
        ok = sep >= min_sep and detect >= min_detect
        rec["chroms"][chrom] = {"separation": sep if np.isfinite(sep) else None, "detection": float(detect),
                                "accepted": bool(ok), "single_copy": chrom in single_copy}
        if ok:
            rec["coords"][li[sel]] = xyz[sel]
    return loci, cells


def takei1mb_truths(path, n: int = 5, min_sep: float = 1.0, min_detect: float = 0.6, seed: int = 1,
                    min_chroms: int = 20, single_copy=("chrX", "chrY")):
    loci, cells = takei1mb_cells(path, min_sep, min_detect, single_copy)
    nacc = {c: sum(v["accepted"] for v in r["chroms"].values()) for c, r in cells.items()}
    best_n = max(nacc.values())
    thr = min(min_chroms, best_n)
    elig = sorted([c for c, k in nacc.items() if k >= thr], key=str)
    rng = np.random.default_rng(seed)
    pick = list(rng.choice(elig, size=min(n, len(elig)), replace=False))
    chrom = loci.Chrom.to_numpy().astype(str)
    out = []
    for c in pick:
        r = cells[c]
        acc = [ch for ch, v in r["chroms"].items() if v["accepted"]]
        keep = np.isin(chrom, acc)
        out.append({"chrom": chrom[keep], "start": loci.Chrom_Start.to_numpy()[keep],
                    "end": loci.Chrom_End.to_numpy()[keep], "coords": r["coords"][keep],
                    "meta": {"dataset": "takei2021_1mb", "cell": str(c), "n_chroms_accepted": len(acc),
                             "chroms": r["chroms"], "min_sep": min_sep, "min_detect": min_detect,
                             "homolog_assignment": "heuristic constrained 2-means (truth.split_homologs)",
                             "n_eligible": len(elig), "min_chroms_required": thr, "seed": seed, "unit": "nm"}})
    pop = np.stack([r["coords"] for c, r in cells.items() if c not in set(pick)])
    stats = {"n_cells": len(cells), "accepted_per_cell": np.bincount(list(nacc.values())).tolist()}
    return out, {"chrom": chrom, "start": loci.Chrom_Start.to_numpy(), "end": loci.Chrom_End.to_numpy(),
                 "population": pop, "stats": stats}
