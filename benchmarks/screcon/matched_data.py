"""Inputs of the matched-modality comparison (``matched.py``): imaging and scHi-C structure sets
on one common locus axis, the Takei 2021 1 Mb loci (numpy / pandas only).

Structure set (``.npz``)
------------------------
``X`` (n_cells, H, L, 3) float32 (NaN = locus not detected / not modelled / copy rejected),
``H`` = 1 (haploid: Stevens / Nagano models, baselines) or 2 (diploid: imaging homologs, Dip-C
maternal / paternal); ``chrom`` / ``start`` / ``end`` (L,) = the locus axis; ``cells`` = JSON
list of per-cell records (``cell_id`` + metadata such as ``cell_type``); ``meta`` = JSON.

Locus axis
----------
The 2,460 Takei 2021 ~1 Mb loci (25 kb probes; 1,267 named ``chrN-#k`` in channel 1, 1,193 named
after a nearby gene in channel 2).  The raw Zenodo tables name loci only; their coordinates are
in the papers' Table S1.  ``data/takei2021_1mb_loci.csv`` was recovered without the supplement:
the 4DN FOF-CT table 4DNFIFLJGGNR (mm10 coordinates) holds exactly the 705,143 spots of the
Zenodo 3735329 replicate-1 table (201 cells), with X = x * 0.103, Y = y * 0.103, Z = z * 0.25 um;
joining on (cell, rounded X/Y/Z) matches 97 % of spots and gives every one of the 2,460 names
exactly one coordinate (``locus-map`` rebuilds it).  The brain tables (Zenodo 4708112, Table
S7) use the same names.

Loaders
-------
* ``takei-mesc``: Takei 2021 Nature, E14 mESC (Zenodo 3735329 ``DNAseqFISH+.zip``,
  ``1Mbloci-E14-replicate{1,2}``: 201 + 245 = 446 cells).
* ``takei-brain``: Takei 2021 Science, adult mouse cortex (Zenodo 4708112 Table S7; 2,762
  cells, ``cluster label`` 1-9 named by marker means of Table S5, see ``BRAIN_CLUSTERS``).
  Both: voxel -> nm (103, 103, 250); homologs separated per (cell, chromosome) with
  ``truth.split_homologs`` (constrained 2-means); a chromosome keeps both copies only when the
  clusters are >= ``min_sep`` mean Rg apart, and a copy is kept when its detection >=
  ``min_detect``; single-copy chromosomes (male chrX / chrY) are deduplicated instead.  For the
  brain the authors' DBSCAN ``labelID`` is used only as a check (agreement reported).
* ``nagano``: Nagano 2017 haploid mESC (``adj`` fend-pair tables of the schic2 archives, mm9
  GATC fends) -> GEO-style contact tables (``chr_A pos_A chr_B pos_B``) lifted to mm10
  with the UCSC chain; one line per fend pair (the count column - duplicate reads - is dropped,
  as NucDynamics and hickit de-duplicate anyway).  Cell selection is a stated rule
  (``--rule``), written to ``manifest.tsv``.
* ``models``: scHi-C model ``.npz`` files (100 kb particles, 2017 ``pos`` convention) -> a
  haploid set: every locus takes the particle covering its probe midpoint.
* ``dipc``: Tan 2021 Dip-C ``*.20k.<rep>.clean.3dg`` (dip-c format: ``chrom(mat|pat) start x y
  z``, 20 kb particles; contact-poor particles removed by ``dip-c clean3``) -> a diploid set
  (copy 0 = mat, 1 = pat), cell types from ``data/tan2021_adult_cortex_cells.tsv``.
"""

from __future__ import annotations

import argparse
import gzip
import json
import re
import sys
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from contacts import ParticleIndex, chrom_key, load_models, write_geo  # noqa: E402
from truth import dedupe_single_copy, split_homologs  # noqa: E402

HERE = Path(__file__).resolve().parent
LOCI_CSV = HERE / "data" / "takei2021_1mb_loci.csv"
TAN_CELLS = HERE / "data" / "tan2021_adult_cortex_cells.tsv"
VOXEL_NM = (103.0, 103.0, 250.0)

# Takei 2021 Science cluster labels (Table S5 / S7 ``cluster label``), named from the cluster means
# of the Table S5 markers named in the paper (Slc17a7, Pvalb, Vip, Ndnf, Sst, Mfge8, Csf1r, Olig1,
# Cldn5); sizes 155, 58, 41, 53, 152, 90, 240, 78, 1,895 match the paper's Fig. 1I legend.
BRAIN_CLUSTERS = {1: "Pvalb", 2: "Vip", 3: "Ndnf", 4: "Sst", 5: "Astrocyte", 6: "Microglia",
                  7: "Endothelial", 8: "Oligodendrocyte", 9: "Excitatory"}
# Coarse classes shared by Takei 2021 Science clusters and Tan 2021 Dip-C structure types.
BRAIN_CLASS = {"Pvalb": "Inhibitory", "Vip": "Inhibitory", "Ndnf": "Inhibitory", "Sst": "Inhibitory",
               "Astrocyte": "Astrocyte", "Microglia": "Microglia", "Endothelial": "Endothelial",
               "Oligodendrocyte": "Oligodendrocyte", "Excitatory": "Excitatory",
               "Cortical L2–5 Pyramidal Cell": "Excitatory", "Cortical L6 Pyramidal Cell": "Excitatory",
               "Interneuron": "Inhibitory", "Adult Astrocyte": "Astrocyte", "Microglia Etc.": "Microglia",
               "Mature Oligodendrocyte": "Oligodendrocyte"}


# --------------------------------------------------------------------------- structure sets

def save_set(path, X, chrom, start, end, cells: list[dict], meta: dict) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(path, X=np.asarray(X, np.float32), chrom=np.asarray(chrom).astype(str),
                        start=np.asarray(start, np.int64), end=np.asarray(end, np.int64),
                        cells=json.dumps(cells), meta=json.dumps(meta))


def load_set(path) -> dict:
    z = np.load(path, allow_pickle=False)
    return {"X": z["X"].astype(np.float32), "chrom": z["chrom"].astype(str), "start": z["start"],
            "end": z["end"], "cells": json.loads(str(z["cells"])), "meta": json.loads(str(z["meta"]))}


def subset_set(s: dict, where: dict | None = None, idx=None) -> dict:
    """Cells matching ``where`` ({field: value or list of values}) or index ``idx``."""
    if idx is None:
        keep = np.ones(len(s["cells"]), bool)
        for k, v in (where or {}).items():
            vals = set(v) if isinstance(v, (list, tuple, set)) else {v}
            keep &= np.array([str(c.get(k)) in {str(x) for x in vals} for c in s["cells"]])
        idx = np.flatnonzero(keep)
    idx = np.asarray(idx)
    return {**s, "X": s["X"][idx], "cells": [s["cells"][i] for i in idx]}


# --------------------------------------------------------------------------- locus axis

def read_loci(path=LOCI_CSV) -> pd.DataFrame:
    """2,460 loci sorted by (chromosome, start); columns name, chrom, start, end."""
    df = pd.read_csv(path)
    df = df.assign(_k=[chrom_key(c) for c in df.chrom]).sort_values(["_k", "start"]).drop(columns="_k")
    return df.reset_index(drop=True)


def build_locus_map(fofct_csv, zip_path, out=LOCI_CSV) -> pd.DataFrame:
    """Recover name -> mm10 coordinates by joining 4DNFIFLJGGNR (replicate 1, FOF-CT) with the
    Zenodo replicate-1 spots (see module docstring)."""
    cols = ["Spot_ID", "Trace_ID", "X", "Y", "Z", "Chrom", "Chrom_Start", "Chrom_End", "Cell_ID", "Extra"]
    f = pd.read_csv(fofct_csv, comment="#", header=None, names=cols, low_memory=False).dropna(subset=["X"])
    with zipfile.ZipFile(zip_path) as zf:
        z = pd.read_csv(zf.open("DNAseqFISH+/DNAseqFISH+1Mbloci-E14-replicate1.csv"))
    z["Cell_ID"] = z.fov.astype(str) + "_" + z.cellID.astype(str)
    for a, b, s in (("x", "X", .103), ("y", "Y", .103), ("z", "Z", .25)):
        z["k" + a] = np.round(z[a] * s, 3)
        f["k" + a] = np.round(f[b].astype(float), 3)
    m = z.merge(f, on=["Cell_ID", "kx", "ky", "kz"], how="inner")
    g = m.groupby("geneID")
    if (g.Chrom_Start.nunique() > 1).any():
        raise ValueError("ambiguous locus names")
    out_df = g[["Chrom", "Chrom_Start", "Chrom_End"]].first().reset_index()
    out_df.columns = ["name", "chrom", "start", "end"]
    out_df[["start", "end"]] = out_df[["start", "end"]].astype(np.int64)
    out_df = out_df.assign(_k=[chrom_key(c) for c in out_df.chrom]).sort_values(["_k", "start"]).drop(columns="_k")
    out_df.to_csv(out, index=False)
    print(f"{len(out_df)} loci from {len(m)} / {len(z)} matched spots -> {out}")
    return out_df


# --------------------------------------------------------------------------- imaging

def imaging_set_from_spots(df: pd.DataFrame, loci: pd.DataFrame, cell_meta: dict, *, min_sep=1.0,
                           min_detect=0.5, single_copy=(), label_col=None, use_labels=False):
    """Spots (columns cell, name, x, y, z in nm[, label_col]) -> (X (n, 2, L, 3), cells, stats).

    Copy slot 0 = the larger homolog cluster.  ``label_col`` (DBSCAN ids in Takei 2021 Science)
    is only compared with the split: fraction of spots whose split cluster equals the majority
    split cluster of their DBSCAN label (both clusters non-negative)."""
    li_of = {n: i for i, n in enumerate(loci.name)}
    df = df[df.name.isin(li_of)].copy()
    df["li"] = df.name.map(li_of).astype(int)
    df["chrom"] = loci.chrom.to_numpy()[df.li.to_numpy()]
    L = len(loci)
    nloc = loci.groupby("chrom").size().to_dict()
    cell_ids = sorted(df.cell.unique(), key=lambda c: (str(type(c)), c))
    cidx = {c: k for k, c in enumerate(cell_ids)}
    X = np.full((len(cell_ids), 2, L, 3), np.nan, np.float32)
    stats = {"n_chrom_copies_2": 0, "n_chrom_copies_1": 0, "n_chrom_rejected": 0, "label_agree": []}
    for (cell, chrom), d in df.groupby(["cell", "chrom"], sort=False):
        xyz = d[["x", "y", "z"]].to_numpy(float)
        li = d.li.to_numpy()
        k = cidx[cell]
        if chrom in single_copy:
            lab = dedupe_single_copy(xyz, li)
            sel = lab == 0
            if sel.sum() / nloc[chrom] >= min_detect:
                X[k, 0, li[sel]] = xyz[sel]
                stats["n_chrom_copies_1"] += 1
            else:
                stats["n_chrom_rejected"] += 1
            continue
        if use_labels:
            ll = d[label_col].to_numpy()
            ids = [v for v in np.unique(ll) if v >= 0]
            if len(ids) != 2:                     # the authors' rule: two separated homologs or none
                stats["n_chrom_rejected"] += 1
                continue
            lab = np.full(len(ll), -1)
            for h, v in enumerate(ids):
                sel = np.flatnonzero(ll == v)
                keep = dedupe_single_copy(xyz[sel], li[sel]) == 0
                lab[sel[keep]] = h
            sep = np.inf
        else:
            lab, sep = split_homologs(xyz, li)
        if label_col is not None and not use_labels:
            ll = d[label_col].to_numpy()
            ok = (lab >= 0) & (ll >= 0)
            if ok.sum() >= 10:
                agree = 0
                for v in np.unique(ll[ok]):
                    s = lab[ok][ll[ok] == v]
                    agree += max((s == 0).sum(), (s == 1).sum())
                stats["label_agree"].append(agree / ok.sum())
        if sep < min_sep:
            stats["n_chrom_rejected"] += 1
            continue
        order = sorted((0, 1), key=lambda h: -(lab == h).sum())
        kept = 0
        for slot, h in enumerate(order):
            sel = lab == h
            if sel.sum() / nloc[chrom] >= min_detect:
                X[k, slot, li[sel]] = xyz[sel]
                kept += 1
        stats[f"n_chrom_copies_{kept}" if kept else "n_chrom_rejected"] += 1
    la = stats.pop("label_agree")
    if la:
        stats["dbscan_label_agreement_median"] = float(np.median(la))
        stats["dbscan_label_agreement_n"] = len(la)
    cells = [{"cell_id": str(c), **cell_meta.get(c, {})} for c in cell_ids]
    return X, cells, stats


def load_takei_mesc(zip_path, loci: pd.DataFrame, reps=(1, 2), **kw):
    frames = []
    with zipfile.ZipFile(zip_path) as zf:
        for r in reps:
            z = pd.read_csv(zf.open(f"DNAseqFISH+/DNAseqFISH+1Mbloci-E14-replicate{r}.csv"))
            z["cell"] = f"rep{r}_" + z.fov.astype(str) + "_" + z.cellID.astype(str)
            frames.append(z)
    z = pd.concat(frames, ignore_index=True)
    df = pd.DataFrame({"cell": z.cell, "name": z.geneID, "x": z.x * VOXEL_NM[0], "y": z.y * VOXEL_NM[1],
                       "z": z.z * VOXEL_NM[2]})
    meta = {c: {"replicate": c.split("_")[0]} for c in df.cell.unique()}
    return imaging_set_from_spots(df, loci, meta, single_copy=("chrX", "chrY"), **kw)


def load_takei_brain(s7_path, loci: pd.DataFrame, use_labels=True, **kw):
    z = pd.read_csv(s7_path, low_memory=False)
    z = z[z.geneID.isin(set(loci.name))]
    df = pd.DataFrame({"cell": z.finalcellID.astype(int), "name": z.geneID, "x": z.x * VOXEL_NM[0],
                       "y": z.y * VOXEL_NM[1], "z": z.z * VOXEL_NM[2], "label": z.labelID.fillna(-1).astype(int)})
    first = z.drop_duplicates("finalcellID").set_index("finalcellID")
    meta = {int(c): {"cluster": int(r["cluster label"]), "cell_type": BRAIN_CLUSTERS[int(r["cluster label"])],
                     "cell_class": BRAIN_CLASS[BRAIN_CLUSTERS[int(r["cluster label"])]],
                     "replicate": int(r["replicateID"])} for c, r in first.iterrows()}
    return imaging_set_from_spots(df, loci, meta, single_copy=(), label_col="label", use_labels=use_labels, **kw)


# --------------------------------------------------------------------------- liftover

class Chain:
    """UCSC chain file (e.g. mm9ToMm10.over.chain.gz): map single positions, ungapped blocks only."""

    def __init__(self, path):
        blocks = {}
        with gzip.open(path, "rt") if str(path).endswith(".gz") else open(path) as fh:
            tname = qname = None
            for line in fh:
                r = line.split()
                if not r:
                    continue
                if r[0] == "chain":
                    tname, tstart, qname, qsize, qstrand, qstart = r[2], int(r[5]), r[7], int(r[8]), r[9], int(r[10])
                    t, q = tstart, qstart
                    continue
                size = int(r[0])
                blocks.setdefault(tname, []).append((t, size, qname, q, qstrand, qsize))
                if len(r) == 3:
                    t += size + int(r[1])
                    q += size + int(r[2])
        self.blocks = {}
        for c, b in blocks.items():
            b.sort()
            self.blocks[c] = (np.array([x[0] for x in b], np.int64), np.array([x[1] for x in b], np.int64),
                              np.array([x[2] for x in b], dtype=object), np.array([x[3] for x in b], np.int64),
                              np.array([x[4] == "-" for x in b]), np.array([x[5] for x in b], np.int64))

    def map(self, chroms, pos):
        """0-based positions -> (chrom (object), pos (int64, -1 = unmapped))."""
        chroms = np.asarray(chroms).astype(str)
        pos = np.asarray(pos, np.int64)
        oc = np.full(len(pos), "", dtype=object)
        op = np.full(len(pos), -1, np.int64)
        for c in np.unique(chroms):
            if c not in self.blocks:
                continue
            ts, sz, qn, qs, neg, qsize = self.blocks[c]
            sel = np.flatnonzero(chroms == c)
            k = np.searchsorted(ts, pos[sel], side="right") - 1
            ok = k >= 0
            kk = np.where(ok, k, 0)
            off = pos[sel] - ts[kk]
            ok &= (off >= 0) & (off < sz[kk])
            q = qs[kk] + off
            q = np.where(neg[kk], qsize[kk] - 1 - q, q)
            oc[sel[ok]] = qn[kk[ok]]
            op[sel[ok]] = q[ok]
        return oc, op


# --------------------------------------------------------------------------- Nagano 2017

def read_fends(path):
    """schic2 GATC.fends (tab separated, header: fend frag chr coord ...) -> {fend: (chr, coord)} arrays."""
    df = pd.read_csv(path, sep="\t", usecols=["fend", "chr", "coord"], dtype={"chr": str})
    chrom = df.chr.astype(str)
    chrom = np.where(chrom.str.startswith("chr"), chrom, "chr" + chrom)
    return df.fend.to_numpy(np.int64), chrom, df.coord.to_numpy(np.int64)


class FendTable:
    def __init__(self, path):
        f, c, p = read_fends(path)
        o = np.argsort(f)
        self.f, self.c, self.p = f[o], c[o], p[o]

    def __call__(self, fends):
        k = np.searchsorted(self.f, fends)
        k = np.clip(k, 0, len(self.f) - 1)
        ok = self.f[k] == fends
        return ok, self.c[k], self.p[k]


def nagano_cell_table(adj_path, fends: FendTable, chain: Chain | None, out, chroms=None) -> dict:
    """One ``adj`` (fend1 fend2 count) -> GEO table in mm10 (mm9 when ``chain`` is None)."""
    a = pd.read_csv(adj_path, sep="\t")
    ok1, c1, p1 = fends(a.fend1.to_numpy(np.int64))
    ok2, c2, p2 = fends(a.fend2.to_numpy(np.int64))
    ok = ok1 & ok2
    c1, p1, c2, p2 = c1[ok], p1[ok], c2[ok], p2[ok]
    n_fend = int(ok.sum())
    if chain is not None:
        c1, p1 = chain.map(c1, p1)
        c2, p2 = chain.map(c2, p2)
        ok = (p1 >= 0) & (p2 >= 0)
        c1, p1, c2, p2 = c1[ok], p1[ok] + 1, c2[ok], p2[ok] + 1      # 1-based like the GEO tables
    keep = np.ones(len(p1), bool)
    if chroms is not None:
        keep = np.isin(c1.astype(str), chroms) & np.isin(c2.astype(str), chroms)
    n = write_geo(out, c1[keep], p1[keep], c2[keep], p2[keep])
    return {"n_adj_rows": int(len(a)), "n_fend_mapped": n_fend, "n_written": int(n),
            "n_reads": int(a["count"].sum())}


def nagano_select(features_tsv, rule: str, max_cells: int | None = None, seed: int = 1) -> pd.DataFrame:
    """Rows of the GEO haploid feature table selected by ``rule`` (a pandas query), optionally a
    seeded random subset of ``max_cells``."""
    f = pd.read_csv(features_tsv, sep="\t")
    s = f.query(rule)
    if max_cells and len(s) > max_cells:
        s = s.sample(max_cells, random_state=seed).sort_index()
    return s


# --------------------------------------------------------------------------- scHi-C models

def models_to_loci(chrom, pos, X, loci: pd.DataFrame) -> np.ndarray:
    """(M, N, 3) particle models -> (M, L, 3): every locus takes the particle covering its probe
    midpoint (NaN where none)."""
    mid = ((loci.start.to_numpy() + loci.end.to_numpy()) // 2).astype(np.int64)
    pidx = ParticleIndex(chrom, pos)(loci.chrom.to_numpy().astype(str), mid)
    out = np.full((X.shape[0], len(loci), 3), np.nan, np.float32)
    ok = pidx >= 0
    out[:, ok] = X[:, pidx[ok]]
    return out


def read_dipc_3dg(path):
    """dip-c 3dg: ``chrom(hap) start x y z`` -> DataFrame chrom, hap, start, x, y, z."""
    df = pd.read_csv(path, sep="\t", header=None, names=["c", "start", "x", "y", "z"], comment="#")
    m = df.c.str.extract(r"^(?:chr)?([^()]+)\((mat|pat)\)$")
    return pd.DataFrame({"chrom": "chr" + m[0], "hap": m[1], "start": df.start.astype(np.int64),
                         "x": df.x, "y": df.y, "z": df.z})


def dipc_to_loci(df: pd.DataFrame, loci: pd.DataFrame, res: int = 20_000) -> np.ndarray:
    """(2, L, 3): copy 0 = mat, 1 = pat; locus -> the 20 kb particle containing its midpoint."""
    out = np.full((2, len(loci), 3), np.nan, np.float32)
    mid = (loci.start.to_numpy() + loci.end.to_numpy()) // 2
    key = {(c, b): i for i, (c, b) in enumerate(zip(loci.chrom, mid // res * res))}
    for h, hap in enumerate(("mat", "pat")):
        d = df[df.hap == hap]
        for c, s, x, y, z in zip(d.chrom, d.start, d.x, d.y, d.z):
            i = key.get((c, int(s) // res * res))
            if i is not None:
                out[h, i] = (x, y, z)
    return out


# --------------------------------------------------------------------------- CLI

def _write_set(args, X, cells, meta, loci):
    save_set(args.out, X, loci.chrom, loci.start, loci.end, cells, meta)
    det = np.isfinite(X[..., 0])
    print(json.dumps({"out": str(args.out), "n_cells": len(cells), "H": X.shape[1],
                      "median_loci_per_cell": float(np.median(det.sum((1, 2)))), **meta.get("stats", {})}))


def cmd_locus_map(args):
    build_locus_map(args.fofct, args.zip, args.out)


def cmd_takei_mesc(args):
    loci = read_loci()
    X, cells, stats = load_takei_mesc(args.zip, loci, min_sep=args.min_sep, min_detect=args.min_detect)
    _write_set(args, X, cells, {"dataset": "takei2021_mesc_1mb", "unit": "nm", "min_sep": args.min_sep,
                                "min_detect": args.min_detect, "stats": stats,
                                "homologs": "truth.split_homologs (heuristic); chrX/chrY single copy"}, loci)


def cmd_takei_brain(args):
    loci = read_loci()
    md = 0.2 if args.min_detect is None else args.min_detect
    X, cells, stats = load_takei_brain(args.s7, loci, use_labels=args.split == "labels", min_sep=args.min_sep,
                                       min_detect=md)
    how = ("authors' DBSCAN labelID: (cell, chromosome) kept when it has exactly two labels, one spot per "
           "locus per label" if args.split == "labels" else
           "truth.split_homologs (heuristic); DBSCAN labelID only compared")
    _write_set(args, X, cells, {"dataset": "takei2021_brain_1mb", "unit": "nm", "min_sep": args.min_sep,
                                "min_detect": md, "stats": stats, "homologs": how}, loci)


def cmd_nagano(args):
    sel = nagano_select(args.features, args.rule, args.max_cells, args.seed)
    fends = FendTable(args.fends)
    chain = Chain(args.chain) if args.chain else None
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    chroms = [f"chr{i}" for i in range(1, 20)] + ["chrX"]
    rows = []
    for _, r in sel.iterrows():
        name = r.cell_nm.replace("_", ".")
        adj = next((Path(d) / name / "adj" for d in args.adj_dirs if (Path(d) / name / "adj").exists()), None)
        if adj is None:
            print(f"missing adj for {r.cell_nm}")
            continue
        dest = out / f"{r.cell_nm}.txt.gz"
        st = nagano_cell_table(adj, fends, chain, dest, chroms)
        rows.append({"cell": r.cell_nm, "cond": r.cond, "group": r.group, "total_contacts": r.total_contacts,
                     "table": str(dest), **st})
        print(json.dumps(rows[-1]), flush=True)
    man = pd.DataFrame(rows)
    man.to_csv(out / "manifest.tsv", sep="\t", index=False)
    (out / "selection.json").write_text(json.dumps({"rule": args.rule, "max_cells": args.max_cells,
                                                     "seed": args.seed, "n_selected": len(sel),
                                                     "n_written": len(man)}, indent=1))


def cmd_models(args):
    loci = read_loci()
    man = pd.concat([pd.read_csv(m, sep="\t") for m in args.manifest], ignore_index=True)
    if "models" not in man:
        man["models"] = [str(Path(args.models_dir) / f"{c}.npz") for c in man.cell]
    man = man.drop(columns=[c for c in ("table",) if c in man])
    sets, cells = [], []
    for _, r in man.iterrows():
        p = Path(r.models)
        if not p.exists():
            print(f"missing {p}")
            continue
        chrom, pos, X = load_models(p)
        Y = models_to_loci(chrom, pos, X, loci)
        k = min(args.model, len(Y) - 1)
        sets.append(Y[k][None])
        rec = {c: (v if isinstance(v, str) else (None if pd.isna(v) else v.item() if hasattr(v, "item") else v))
               for c, v in r.items() if c != "models"}
        cells.append({"cell_id": str(rec.get("cell", p.stem)), **rec, "n_models": int(len(Y)), "model_used": int(k),
                      "frac_loci_modelled": float(np.isfinite(Y[k, :, 0]).mean())})
    X = np.stack(sets)
    _write_set(args, X, cells, {"dataset": args.label, "unit": "model", "model_index": args.model,
                                "manifest": str(args.manifest)}, loci)


def cmd_dipc(args):
    loci = read_loci()
    tab = pd.read_csv(args.cells, sep="\t")
    sets, cells = [], []
    for _, r in tab.iterrows():
        p = Path(args.dir) / r["name"] / f"{r['name']}.20k.{args.rep}.clean.3dg.txt.gz"
        if not p.exists():
            continue
        sets.append(dipc_to_loci(read_dipc_3dg(p), loci))
        cells.append({"cell_id": r["name"], "gsm": r.gsm, "age": r.age, "cross": r.cross, "cell_type": r.cell_type,
                      "cell_class": BRAIN_CLASS.get(r.cell_type, "Other")})
    _write_set(args, np.stack(sets), cells, {"dataset": "tan2021_cortex_dipc", "unit": "particle radius (dip-c)",
                                             "rep": args.rep}, loci)


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("locus-map"); p.add_argument("--fofct", required=True); p.add_argument("--zip", required=True)
    p.add_argument("--out", default=str(LOCI_CSV)); p.set_defaults(fn=cmd_locus_map)
    for name, fn in (("takei-mesc", cmd_takei_mesc), ("takei-brain", cmd_takei_brain)):
        p = sub.add_parser(name)
        if name == "takei-mesc":
            p.add_argument("--zip", required=True)
        else:
            p.add_argument("--s7", required=True)
            p.add_argument("--split", choices=["labels", "kmeans"], default="labels")
        p.add_argument("--min-sep", type=float, default=1.0)
        p.add_argument("--min-detect", type=float, default=0.5 if name == "takei-mesc" else None,
                       help="minimum detected fraction of a copy's loci (mESC 0.5, brain 0.2)")
        p.add_argument("--out", required=True)
        p.set_defaults(fn=fn)
    p = sub.add_parser("nagano")
    p.add_argument("--features", required=True); p.add_argument("--fends", required=True)
    p.add_argument("--chain"); p.add_argument("--adj-dirs", nargs="+", required=True)
    p.add_argument("--rule", required=True); p.add_argument("--max-cells", type=int)
    p.add_argument("--seed", type=int, default=1); p.add_argument("--out-dir", required=True)
    p.set_defaults(fn=cmd_nagano)
    p = sub.add_parser("models")
    p.add_argument("--manifest", nargs="+", required=True,
                   help="tsv(s) with cell metadata and a 'models' column (.npz) or a 'cell' column + --models-dir")
    p.add_argument("--models-dir")
    p.add_argument("--model", type=int, default=0); p.add_argument("--label", required=True)
    p.add_argument("--out", required=True); p.set_defaults(fn=cmd_models)
    p = sub.add_parser("dipc")
    p.add_argument("--dir", required=True); p.add_argument("--cells", default=str(TAN_CELLS))
    p.add_argument("--rep", type=int, default=1); p.add_argument("--out", required=True)
    p.set_defaults(fn=cmd_dipc)
    args = ap.parse_args(argv)
    args.fn(args)


if __name__ == "__main__":
    main()
