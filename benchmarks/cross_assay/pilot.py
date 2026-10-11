"""Cross-assay pilot (Step 0 of Analysis A): does one cell-type contrast of contact decay point the same way in every
single-cell / spatial Hi-C dataset of the mouse cortex and in DNA seqFISH+ imaging?

The contrast is excitatory neurons (ExN) against mature oligodendrocytes (Oligo), with inhibitory neurons (InN),
astrocytes (Astro), OPCs and microglia (Micro) for the class ranking.  It is coarse on purpose and uses only data
that are already at hand (no read pairs refetched):

* sequencing: from the per-cell 1-Mb maps of the atlas stores, the cis contacts one bin apart (map offset 1:
  separations 0-2 Mb, mean 1 Mb) over those 19-53 bins apart (separations 18-54 Mb), pooled over the autosomes,
  ``log2((short + 0.5) / (long + 0.5))`` per cell;
* imaging (and Dip-C 3-D structures on the same loci): per cell, the median 3-D distance of locus pairs 19-53 Mb
  apart over that of pairs 1-2 Mb apart, ``log2(d_long / d_short)`` (higher = short range relatively more compact,
  the direction of the contact ratio).

Only contrasts within a dataset are compared (direction, size, class ranking), never absolute values.

Stages (``--stages``; each writes per-cell tables into ``--work``, ``analyze`` reads them):

* ``seq``      atlas stores (per-cell 1-Mb maps over HTTP) -> ``offsets_<dataset>.npz`` (cells x map offset 0-199,
               199 = 199 or more; autosomes pooled) and ``cells_<dataset>.parquet``;
* ``tan``      Tan 2021 Dip-C ``contacts.pairs`` (510 cells) -> the same offsets at 1 Mb and counts at exact
               separations;
* ``guo``      Guo 2026 spatial Hi-C-RNA brain: the stored contact-distance histograms (``ContactStats``) -> the ratio
               over the histogram bins closest to 1-2 / 19-53 Mb, and Guo et al.'s short / long ratio
               (``ContactFeatureParams.guo2026``);
* ``imaging``  structure sets of ``benchmarks/screcon/matched_data.py`` (``--sets``: Takei 2021 brain with the
               authors' DBSCAN homologs, with the k-means split, Tan 2021 Dip-C models) -> per-cell distances;
* ``analyze``  class medians, ExN - Oligo (bootstrap CI, Cliff's delta, adjusted for depth, at thinned depth,
               without cycling cells), class rankings, sign agreement, Kendall's W -> ``--results``.

    python benchmarks/cross_assay/pilot.py --work DIR --results benchmarks/cross_assay/results \
        --stages seq tan guo imaging analyze --tan-dir $UCHROM_DATA/tan2021_cortex/cells --sets DIR
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import warnings
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from _record import save  # noqa: E402

RES = 1_000_000
MAX_OFF = 200                     # offset histogram columns 0..199 (199: 199 bins or more)
SHORT_OFF = (1, 1)                # map offsets (inclusive) of the short range: separations 0-2 Mb
LONG_OFF = (19, 53)               # separations 18-54 Mb
MITO_OFF = (2, 12)                # Nagano et al. 2017's mitotic band 2-12 Mb, coarsely
SHORT_BP = (1.0e6, 2.0e6)         # imaging / exact separations
LONG_BP = (19.0e6, 53.0e6)
UNIT_BP = (0.75e6, 1.25e6)        # the 1-Mb unit of benchmarks/screcon/matched.py
AUTOSOMES = [f"chr{k}" for k in range(1, 20)]
CLASSES = ["ExN", "InN", "Astro", "Oligo", "OPC", "Micro"]
CORE = ["ExN", "InN", "Astro", "Oligo"]
MIN_GE1 = 500                     # per-cell analyses: cells with at least this many cis contacts >= 1 bin apart
GUO_MIN_CONTACTS = 50_000         # spot QC of benchmarks/spatial_variable

# Harmonised classes: label -> class; labels not listed (other regions, vascular, unknown) are left out.
_IT = "ExN"
DATASETS = {
    "hires_brain": {
        "assay": "scHi-C + RNA (HiRES)", "modality": "scHi-C", "column": "cell_type", "mitotic": "frac_mitotic",
        "classes": {"Ex1": "ExN", "Ex2": "ExN", "Ex3": "ExN", "In1": "InN", "In2": "InN", "Ast": "Astro",
                    "Oli": "Oligo"}},
    "gageseq_mouse_cortex": {
        "assay": "scHi-C + RNA (GAGE-seq)", "modality": "scHi-C", "column": "cell_type",
        "classes": {**{k: "ExN" for k in ("L2/3 IT CTX a", "L2/3 IT CTX b", "L2/3 IT CTX c", "L2/3 IT RSP",
                                          "L2 IT RvPP", "L4 IT CTX", "L4/5 IT CTX", "L5 IT CTX", "L5 IT RSP",
                                          "L6 IT CTX", "L6 CT CTX a", "L6 CT CTX b", "L5/6 NP CTX", "L5 PT CTX",
                                          "L6b CTX")},
                    **{k: "InN" for k in ("Pvalb a", "Pvalb b", "Sst a", "Sst b", "Vip", "Lamp5", "Sncg",
                                          "Meis2")},
                    "Astro": "Astro", "ODC": "Oligo", "OPC": "OPC", "Micro": "Micro"}},
    "droplet_hic_mouse_cortex": {
        "assay": "Droplet Hi-C", "modality": "scHi-C", "column": "cell_type",
        "classes": {**{k: "ExN" for k in ("ITL23GL", "ITL45GL", "ITL5GL", "ITL6GL", "CTGL", "PTGL", "NPGL",
                                          "CLAGL")},
                    **{k: "InN" for k in ("PVGA", "SSTGA", "VIPGA")},
                    "ASC": "Astro", "OGC": "Oligo", "OPC": "OPC", "MGL": "Micro"}},
    "paired_hic_mouse_cortex": {
        "assay": "Paired Hi-C (+ RNA)", "modality": "scHi-C", "column": "cell_type", "pooled_only": True,
        "classes": {**{k: "ExN" for k in ("ITL23GL", "ITL5GL", "ETL5GL", "ITL6GL", "CTGL", "PTGL", "NPGL",
                                          "CLAGL")},
                    **{k: "InN" for k in ("PVGA", "VIPGA")},
                    "ASC": "Astro", "OGC": "Oligo", "OPC": "OPC", "MGL": "Micro"}},
    "dschic_aging_cortex": {
        "assay": "dscHi-C (3, 12, 23 months)", "modality": "scHi-C", "column": "cell_type",
        "mitotic": "frac_mitotic_band", "strata": "age",
        "classes": {"Excitatory neurons": "ExN", "Inhibitory interneurons": "InN", "Astrocytes": "Astro",
                    "Oligodendrocytes": "Oligo", "Oligodendrocyte precursor cells": "OPC",
                    "Microglial cells": "Micro"}},
    "schicar_mouse_cortex": {
        "assay": "scHiCAR (RNA + ATAC + Hi-C)", "modality": "scHi-C", "column": "cell_type",
        "classes": {**{k: "ExN" for k in ("L23IT.1", "L23IT.2", "L23IT.3", "L45IT", "L5IT", "L6IT", "L6CT", "PT",
                                          "L56NP", "CLA")},
                    **{k: "InN" for k in ("Pvalb", "Sst", "Vip", "Lamp5")},
                    "Astro": "Astro", "Oligo": "Oligo", "OPC": "OPC", "MGL": "Micro"}},
    "hicrna_mouse_brain": {
        "assay": "spatial Hi-C-RNA (Guo 2026), spots by dominant type", "modality": "spatial Hi-C",
        "column": "cell_type", "strata": "section", "min_contacts": ("hic_contacts", GUO_MIN_CONTACTS),
        "classes": {**{k: "ExN" for k in ("L2_3 IT", "L4", "L5 IT", "L5 PT", "L6 IT", "L6 CT", "NP", "L6b")},
                    **{k: "InN" for k in ("Pvalb", "Sst", "Vip", "Lamp5", "Sncg", "Meis2")},
                    "Astro": "Astro", "Oligo": "Oligo"}},
}
# the authors' CellCharter domains of brain section r1 (names of benchmarks/spatial_variable)
GUO_DOMAINS = {"0": "cortex", "2": "cortex", "7": "white matter", "4": "CA3", "11": "CA1", "10": "DG",
               "5": "choroid plexus"}
TAN = {"assay": "Dip-C (Tan 2021)", "modality": "scHi-C",
       "classes": {"Cortical L2–5 Pyramidal Cell": "ExN", "Cortical L6 Pyramidal Cell": "ExN",
                   "Interneuron": "InN", "Adult Astrocyte": "Astro", "Mature Oligodendrocyte": "Oligo",
                   "Oligodendrocyte Progenitor": "OPC", "Microglia Etc.": "Micro"}}
TAKEI = {"Excitatory": "ExN", "Pvalb": "InN", "Vip": "InN", "Ndnf": "InN", "Sst": "InN", "Astrocyte": "Astro",
         "Microglia": "Micro", "Oligodendrocyte": "Oligo"}
SETS = {"takei2021_brain_labels": ("DNA seqFISH+ (Takei 2021), authors' DBSCAN homologs", "imaging"),
        "takei2021_brain_kmeans": ("DNA seqFISH+ (Takei 2021), k-means homolog split", "imaging"),
        "tan2021_dipc_rep1": ("Dip-C 3-D models (Tan 2021, replicate 1)", "3-D models from contacts")}


# ------------------------------------------------------------------------------------------------- sequencing

def _pandas_compat() -> bool:
    """The atlas stores record pandas >= 2.3 string dtypes (``na_value``); with an older pandas (the Sherlock env has
    2.2) read those columns as a plain ``StringDtype`` instead.  Only spot columns derived from keys are affected,
    and none is used here.  Returns whether the shim was applied."""
    try:
        pd.StringDtype(na_value=np.nan)
        return False
    except TypeError:
        import chromdata.zarrcd as zc

        zc.string_dtype_of = lambda meta: pd.StringDtype(storage=meta["storage"])
        return True


def per_cell_offsets(e, chroms, workers: int = 4, step: int = 1 << 22):
    """(cells x MAX_OFF) cis contacts by map offset |bin2 - bin1| of one embedded per-cell map, ``chroms`` pooled."""
    r = e.resolutions[0]
    if r != RES:
        raise ValueError(f"{e.name}: per-cell maps at {r} bp, not {RES}")
    n = len(e.cells)
    grp = e.g[f"r{r}"]
    parts = [c for c in chroms if f"cis/{c}" in grp]

    def one(c):
        pix = e.g[f"r{r}/cis/{c}/pix"]
        off = e.g[f"r{r}/cis/{c}/cell_offset"][:].astype(np.int64)
        h = np.zeros(n * MAX_OFF, np.float64)
        total = int(pix.shape[1])
        for s in range(0, total, step):
            t = min(s + step, total)
            blk = np.asarray(pix[:, s:t])
            d = np.abs(blk[1].astype(np.int64) - blk[0].astype(np.int64))
            np.minimum(d, MAX_OFF - 1, out=d)
            cell = np.searchsorted(off, np.arange(s, t), side="right") - 1
            h += np.bincount(cell * MAX_OFF + d, weights=blk[2].astype(np.float64), minlength=n * MAX_OFF)
        return h

    H = np.zeros(n * MAX_OFF, np.float64)
    with ThreadPoolExecutor(workers) as ex:
        for h in ex.map(one, parts):
            H += h
    return H.reshape(n, MAX_OFF).astype(np.int64), parts


def offset_columns(H: np.ndarray) -> pd.DataFrame:
    return pd.DataFrame({"n_cis": H.sum(1), "n_ge1": H[:, 1:].sum(1),
                         "n_short": H[:, SHORT_OFF[0]:SHORT_OFF[1] + 1].sum(1),
                         "n_long": H[:, LONG_OFF[0]:LONG_OFF[1] + 1].sum(1),
                         "n_mito": H[:, MITO_OFF[0]:MITO_OFF[1] + 1].sum(1)})


def stage_seq(work: Path, names, workers: int) -> dict:
    import uchrom.datasets as ds
    from chromdata.embedded import open_all

    log = {"pandas_string_dtype_shim": _pandas_compat()}
    for name in names:
        t0 = time.perf_counter()
        spec = DATASETS[name]
        cd = ds.load(name)
        store = str(cd._links_from())
        maps = {k: e for k, e in open_all(store).items() if e.kind == "per_cell"}
        Hs, ids, used = [], [], {}
        for k in sorted(maps):
            H, parts = per_cell_offsets(maps[k], AUTOSOMES, workers)
            Hs.append(H)
            ids += [str(c) for c in maps[k].cells]
            used[k] = parts
        H = np.concatenate(Hs)
        np.savez_compressed(work / f"offsets_{name}.npz", H=H, cells=np.asarray(ids))
        cells = cd.cells.copy()
        cells.index = cells.index.astype(str)
        keep = [c for c in [spec["column"], spec.get("mitotic"), spec.get("strata"), "n_contacts", "hic_contacts",
                            "cell_type_confidence", "cluster_cellcharter", "library"] if c and c in cells]
        tab = cells.reindex(ids)[keep].copy()
        for c in tab.columns:
            if isinstance(tab[c].dtype, pd.CategoricalDtype):
                tab[c] = tab[c].astype(str)
        tab.index.name = "cell_id"
        oc = offset_columns(H)
        oc.index = tab.index
        tab = pd.concat([tab, oc], axis=1)
        tab.to_parquet(work / f"cells_{name}.parquet")
        log[name] = {"store": store, "maps": sorted(maps), "n_cells": len(ids),
                     "n_cells_in_cd_cells": int(cells.index.isin(ids).sum()), "chromosomes": used,
                     "cis_contacts_median": float(np.median(oc.n_cis)), "wall_s": round(time.perf_counter() - t0, 1)}
        print(f"[seq] {name}: {len(ids):,} cells, median cis {np.median(oc.n_cis):,.0f}, "
              f"{log[name]['wall_s']} s", flush=True)
    return log


def _tan_cell(path: str):
    df = pd.read_csv(path, sep="\t", comment="#", header=None, usecols=[1, 2, 3, 4],
                     names=["c1", "p1", "c2", "p2"], dtype={"c1": str, "c2": str, "p1": np.int64, "p2": np.int64})
    n_all = len(df)
    cis = (df.c1 == df.c2) & df.c1.isin(AUTOSOMES)
    p1, p2 = df.p1[cis].to_numpy(), df.p2[cis].to_numpy()
    h = np.bincount(np.minimum(np.abs(p2 // RES - p1 // RES), MAX_OFF - 1), minlength=MAX_OFF)
    dist = np.abs(p2 - p1)
    exact = {"exact_ge1mb": int((dist >= 1e6).sum()),
             "exact_short": int(((dist >= SHORT_BP[0]) & (dist < SHORT_BP[1])).sum()),
             "exact_long": int(((dist >= LONG_BP[0]) & (dist <= LONG_BP[1])).sum()),
             "n_pairs_all": int(n_all)}
    return h, exact


def stage_tan(work: Path, tan_dir: Path, cells_tsv: Path, workers: int, limit=None) -> dict:
    t0 = time.perf_counter()
    meta = pd.read_csv(cells_tsv, sep="\t")
    if limit:
        meta = meta.head(limit)
    paths = [str(tan_dir / n / f"{n}.contacts.pairs.txt.gz") for n in meta["name"]]
    ok = [Path(p).exists() for p in paths]
    meta, paths = meta[ok], [p for p, k in zip(paths, ok) if k]
    with ProcessPoolExecutor(workers) as ex:
        out = list(ex.map(_tan_cell, paths, chunksize=4))
    H = np.stack([h for h, _ in out])
    tab = pd.DataFrame([x for _, x in out], index=pd.Index(meta["name"].astype(str), name="cell_id"))
    tab.insert(0, "cell_type", meta["cell_type"].to_numpy())
    tab.insert(1, "age", meta["age"].to_numpy())
    oc = offset_columns(H)
    oc.index = tab.index
    tab = pd.concat([tab, oc], axis=1)
    np.savez_compressed(work / "offsets_tan2021_cortex.npz", H=H, cells=np.asarray(tab.index))
    tab.to_parquet(work / "cells_tan2021_cortex.parquet")
    log = {"n_cells": len(tab), "missing_pairs_files": int((~np.asarray(ok)).sum()),
           "cis_contacts_median": float(np.median(oc.n_cis)), "wall_s": round(time.perf_counter() - t0, 1)}
    print(f"[tan] {log}", flush=True)
    return log


def _bins_between(edges: np.ndarray, lo: float, hi: float):
    """Histogram columns (column k: edges[k-1] <= d < edges[k]) between the edges closest to lo and hi."""
    a = int(np.argmin(np.abs(np.log(edges / lo))))
    b = int(np.argmin(np.abs(np.log(edges / hi))))
    return list(range(a + 1, b + 1)), (float(edges[a]), float(edges[b]))


def stage_guo(work: Path) -> dict:
    import uchrom.datasets as ds
    from uchrom.fea.contact_stats import ContactFeatureParams, contact_features

    t0 = time.perf_counter()
    shim = _pandas_compat()
    cd = ds.load("hicrna_mouse_brain")
    rec = cd.uns["contact_stats"]["contacts"]
    edges = np.asarray(rec["edges"], float)
    chroms = list(rec["chroms"])
    dist = np.asarray(cd.cellm["contacts.distance"])
    if dist.ndim == 3:
        sel = [i for i, c in enumerate(chroms) if c in AUTOSOMES]
        dist_a = dist[:, sel].sum(1)
        pooled_over = "autosomes"
    else:
        dist_a = dist
        pooled_over = "all chromosomes of the histograms (stored pooled)"
    cs, ce = _bins_between(edges, *SHORT_BP)
    cl, cle = _bins_between(edges, *LONG_BP)
    cge, _ = _bins_between(edges, 1.0e6, edges[-1])
    ids = pd.Index([str(c) for c in cd._cell_ids_axis()], name="cell_id")
    tab = pd.DataFrame({"hist_short": dist_a[:, cs].sum(1), "hist_long": dist_a[:, cl].sum(1),
                        "hist_ge1mb": dist_a[:, cge[0]:].sum(1)}, index=ids)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        f = contact_features(cd, key="contacts", params=ContactFeatureParams.guo2026(), key_added=None)
    f.index = f.index.astype(str)
    tab["guo_short_long_ratio"] = f["short_long_ratio"].reindex(ids).to_numpy()
    tab["guo_frac_short"] = f["frac_short"].reindex(ids).to_numpy()
    tab["guo_frac_long"] = f["frac_long"].reindex(ids).to_numpy()
    tab.to_parquet(work / "guo_stats.parquet")
    log = {"distance_shape": list(dist.shape), "pooled_over": pooled_over,
           "short_columns": cs, "short_edges_bp": ce, "long_columns": cl, "long_edges_bp": cle,
           "ge1mb_from_edge_bp": float(edges[cge[0] - 1]), "guo_params": "ContactFeatureParams.guo2026()",
           "pandas_string_dtype_shim": shim,
           "wall_s": round(time.perf_counter() - t0, 1)}
    print(f"[guo] {log}", flush=True)
    return log


# ------------------------------------------------------------------------------------------------- imaging

def _pairs(chrom, mid, lo, hi):
    I, J = [], []
    for c in AUTOSOMES:
        idx = np.flatnonzero(chrom == c)
        if len(idx) < 2:
            continue
        i, j = np.triu_indices(len(idx), 1)
        sep = np.abs(mid[idx[j]] - mid[idx[i]])
        k = (sep >= lo) & (sep <= hi)
        I.append(idx[i[k]])
        J.append(idx[j[k]])
    return np.concatenate(I), np.concatenate(J)


def imaging_metrics(X: np.ndarray, chrom: np.ndarray, start: np.ndarray, end: np.ndarray, chunk: int = 64):
    """Per cell: medians of the 3-D distances at short / long separations (pooled over copies and autosomes), the
    1-Mb unit, and the pairs closer than a threshold (the cell's unit; the median unit of the set)."""
    mid = (start + end) / 2.0
    Is, Js = _pairs(chrom, mid, *SHORT_BP)
    Il, Jl = _pairs(chrom, mid, *LONG_BP)
    Iu, Ju = _pairs(chrom, mid, *UNIT_BP)

    def dist(Xc, I, J):
        return np.linalg.norm(Xc[:, :, I] - Xc[:, :, J], axis=-1).reshape(len(Xc), -1)

    n = len(X)
    unit = np.full(n, np.nan)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        for a in range(0, n, chunk):
            unit[a:a + chunk] = np.nanmedian(dist(X[a:a + chunk], Iu, Ju), 1)
        scale = float(np.nanmedian(unit))
        rows = []
        for a in range(0, n, chunk):
            Xc = X[a:a + chunk]
            ds_, dl = dist(Xc, Is, Js), dist(Xc, Il, Jl)
            u = unit[a:a + chunk, None]
            r = {"d_short": np.nanmedian(ds_, 1), "d_long": np.nanmedian(dl, 1),
                 "n_short": np.isfinite(ds_).sum(1), "n_long": np.isfinite(dl).sum(1),
                 "n_loci": np.isfinite(Xc[..., 0]).sum((1, 2)), "unit": unit[a:a + chunk]}
            for f in (0.5, 1.0, 2.0):
                r[f"k_short_u{f:g}"] = (ds_ < f * u).sum(1)
                r[f"k_long_u{f:g}"] = (dl < f * u).sum(1)
                r[f"k_short_s{f:g}"] = (ds_ < f * scale).sum(1)
                r[f"k_long_s{f:g}"] = (dl < f * scale).sum(1)
            rows.append(pd.DataFrame(r))
    tab = pd.concat(rows, ignore_index=True)
    return tab, {"n_pairs_short": int(len(Is)), "n_pairs_long": int(len(Il)), "n_pairs_unit": int(len(Iu)),
                 "median_unit": scale}


def stage_imaging(work: Path, sets_dir: Path) -> dict:
    sys.path.insert(0, str(HERE.parent / "screcon"))
    from matched_data import load_set

    log = {}
    for name in SETS:
        p = sets_dir / f"{name}.npz"
        if not p.exists():
            log[name] = "missing"
            continue
        t0 = time.perf_counter()
        s = load_set(p)
        tab, info = imaging_metrics(s["X"], s["chrom"], s["start"], s["end"])
        cells = pd.DataFrame(s["cells"])
        tab.index = pd.Index(cells["cell_id"].astype(str), name="cell_id")
        tab.insert(0, "cell_type", cells["cell_type"].astype(str).to_numpy())
        tab.to_parquet(work / f"imaging_{name}.parquet")
        log[name] = {**info, "n_cells": len(tab), "set_meta": s["meta"], "wall_s": round(time.perf_counter() - t0, 1)}
        print(f"[imaging] {name}: {log[name]}", flush=True)
    return log


# ------------------------------------------------------------------------------------------------- statistics

def _boot_median_diff(x, y, rng, n_boot):
    out = np.empty(n_boot)
    for k in range(n_boot):
        out[k] = np.median(rng.choice(x, len(x))) - np.median(rng.choice(y, len(y)))
    return out


def contrast(x, y, rng, n_boot=2000) -> dict:
    from scipy.stats import mannwhitneyu

    x, y = np.asarray(x, float), np.asarray(y, float)
    x, y = x[np.isfinite(x)], y[np.isfinite(y)]
    if len(x) < 3 or len(y) < 3:
        return {"n_a": len(x), "n_b": len(y)}
    b = _boot_median_diff(x, y, rng, n_boot)
    mw = mannwhitneyu(x, y, alternative="two-sided")
    return {"n_a": len(x), "n_b": len(y), "median_a": float(np.median(x)), "median_b": float(np.median(y)),
            "diff": float(np.median(x) - np.median(y)), "ci95": [float(np.quantile(b, .025)), float(np.quantile(b, .975))],
            "cliffs_delta": float(2 * mw.statistic / (len(x) * len(y)) - 1), "mannwhitney_p": float(mw.pvalue)}


def ancova(t: pd.DataFrame, value: str, depth: str, a: str, b: str, rng, n_boot=1000) -> dict:
    """value ~ class (one coefficient per class) + depth: coefficient of a minus that of b, bootstrap over cells
    within each class."""
    t = t[np.isfinite(t[value]) & np.isfinite(t[depth])]
    cls = sorted(t["cls"].unique())
    if a not in cls or b not in cls:
        return {}
    groups = [np.flatnonzero(t["cls"].to_numpy() == c) for c in cls]
    Z = np.column_stack([(t["cls"].to_numpy() == c).astype(float) for c in cls] +
                        [t[depth].to_numpy() - t[depth].mean()])
    yv = t[value].to_numpy()
    ia, ib = cls.index(a), cls.index(b)

    def fit(rows):
        beta = np.linalg.lstsq(Z[rows], yv[rows], rcond=None)[0]
        return beta[ia] - beta[ib], beta[-1]

    est, slope = fit(np.arange(len(t)))
    boots = np.array([fit(np.concatenate([rng.choice(g, len(g)) for g in groups]))[0] for _ in range(n_boot)])
    return {"diff": float(est), "ci95": [float(np.quantile(boots, .025)), float(np.quantile(boots, .975))],
            "depth_slope": float(slope), "classes_in_model": cls}


def kendall_w(M: pd.DataFrame) -> dict:
    """Kendall's W of the class ranks (rows: datasets, columns: classes; no missing values)."""
    from scipy.stats import chi2

    M = M.dropna(axis=0)
    m, n = M.shape
    if m < 2 or n < 2:
        return {"n_datasets": m, "n_classes": n}
    R = M.rank(axis=1).to_numpy()
    S = ((R.sum(0) - R.sum(0).mean()) ** 2).sum()
    W = 12 * S / (m ** 2 * (n ** 3 - n))
    x2 = m * (n - 1) * W
    return {"W": float(W), "n_datasets": m, "n_classes": n, "chi2": float(x2), "p": float(chi2.sf(x2, n - 1)),
            "datasets": list(M.index), "classes": list(M.columns),
            "mean_rank": {c: float(v) for c, v in zip(M.columns, R.mean(0))}}


def _ratio(short, long):
    return np.log2((np.asarray(short, float) + 0.5) / (np.asarray(long, float) + 0.5))


def pooled_ratio(t, rng, n_boot=2000) -> dict:
    """Per class log2(sum short / sum long), bootstrap over cells; ExN - Oligo with CI."""
    out, boots = {}, {}
    for c, g in t.groupby("cls"):
        s, l = g["n_short"].to_numpy(float), g["n_long"].to_numpy(float)
        out[c] = float(np.log2(s.sum() / l.sum()))
        idx = rng.integers(0, len(g), (n_boot, len(g))) if len(g) * n_boot <= 5e7 else None
        if idx is not None:
            boots[c] = np.log2(s[idx].sum(1) / l[idx].sum(1))
        else:
            boots[c] = np.array([np.log2(s[k].sum() / l[k].sum())
                                 for k in (rng.integers(0, len(g), len(g)) for _ in range(n_boot))])
    res = {"by_class": out}
    if "ExN" in boots and "Oligo" in boots:
        d = boots["ExN"] - boots["Oligo"]
        res["exn_minus_oligo"] = {"diff": out["ExN"] - out["Oligo"],
                                  "ci95": [float(np.quantile(d, .025)), float(np.quantile(d, .975))]}
    return res


def thinned(t, rng, q=0.2) -> pd.DataFrame:
    """Binomial thinning of the short / long counts to the q-quantile of contacts >= 1 bin apart."""
    target = float(np.quantile(t["n_ge1"], q))
    t = t[t["n_ge1"] >= target].copy()
    p = target / t["n_ge1"].to_numpy(float)
    t["ratio_thin"] = _ratio(rng.binomial(t["n_short"].to_numpy(np.int64), p),
                             rng.binomial(t["n_long"].to_numpy(np.int64), p))
    t.attrs["target"] = target
    return t


def summarize(t: pd.DataFrame, value: str, rng, *, depth=None, a="ExN", b="Oligo", n_boot=2000) -> dict:
    g = t.groupby("cls")[value]
    med = g.median().reindex([c for c in CLASSES + ["cortex", "white matter", "CA1", "CA3", "DG", "choroid plexus"]
                              if c in g.groups])
    res = {"n_by_class": {c: int(v) for c, v in g.size().items()},
           "median_by_class": {c: float(v) for c, v in med.items()},
           "ranking_high_to_low": list(med.sort_values(ascending=False).index)}
    if a in g.groups and b in g.groups:
        res["contrast"] = {"a": a, "b": b, **contrast(t.loc[t.cls == a, value], t.loc[t.cls == b, value], rng, n_boot)}
        if depth is not None:
            res["contrast_depth_adjusted"] = ancova(t, value, depth, a, b, rng)
    return res


def _seq_table(work: Path, name: str):
    t = pd.read_parquet(work / f"cells_{name}.parquet")
    spec = DATASETS[name] if name in DATASETS else TAN
    col = spec.get("column", "cell_type")
    t["cls"] = t[col].astype(str).map(spec["classes"])
    if spec.get("min_contacts"):
        c, v = spec["min_contacts"]
        t = t[t[c] >= v]
    t["ratio"] = _ratio(t["n_short"], t["n_long"])
    t["frac_short"] = t["n_short"] / t["n_ge1"]
    t["frac_long"] = t["n_long"] / t["n_ge1"]
    t["log10_cis"] = np.log10(t["n_cis"].clip(lower=1))
    t["mito_proxy"] = t["n_mito"] / t["n_ge1"]
    return t


def analyze_seq(t: pd.DataFrame, spec: dict, rng, n_boot: int) -> dict:
    lab = t[t["cls"].notna()]
    res = {"assay": spec["assay"], "modality": spec["modality"], "n_cells_total": int(len(t)),
           "n_cells_labelled": int(len(lab)),
           "cis_contacts_median": float(lab["n_cis"].median()), "ge1_contacts_median": float(lab["n_ge1"].median()),
           "pooled": pooled_ratio(lab, rng, n_boot)}
    if spec.get("pooled_only"):
        res["note"] = "per-cell ratios not used (too few contacts per cell): pooled by class only"
        res["median_ge1_by_class"] = {c: float(v) for c, v in lab.groupby("cls")["n_ge1"].median().items()}
        return res
    pc = lab[lab["n_ge1"] >= MIN_GE1]
    res["n_cells_used"] = int(len(pc))
    res["ratio"] = summarize(pc, "ratio", rng, depth="log10_cis", n_boot=n_boot)
    res["frac_short"] = summarize(pc, "frac_short", rng, n_boot=500)
    res["frac_long"] = summarize(pc, "frac_long", rng, n_boot=500)
    th = thinned(pc, rng)
    res["ratio_thinned"] = {"target_ge1": th.attrs["target"], **summarize(th, "ratio_thin", rng, n_boot=n_boot)}
    for col, label in ((spec.get("mitotic"), "published"), ("mito_proxy", "proxy_offsets_2_12")):
        if col and col in pc:
            cut = float(np.nanquantile(pc[col], 0.9))
            sub = pc[pc[col] <= cut]
            r = summarize(sub, "ratio", rng, n_boot=n_boot)
            ex = pc[pc[col] > cut]
            res[f"without_top_decile_mitotic_{label}"] = {
                "column": col, "cut": cut, "n_removed": int(len(ex)),
                "removed_by_class": {c: int(v) for c, v in ex.groupby("cls").size().items()},
                "contrast": r.get("contrast"), "median_by_class": r["median_by_class"]}
    if spec.get("strata") and spec["strata"] in pc:
        res["by_stratum"] = {str(k): summarize(g, "ratio", rng, n_boot=500).get("contrast")
                             for k, g in pc.groupby(spec["strata"])}
    return res


def stage_analyze(work: Path, results: Path, seed: int, n_boot: int, logs: dict) -> dict:
    rng = np.random.default_rng(seed)
    out = {"definitions": {
        "seq_ratio": f"log2((short + 0.5) / (long + 0.5)) per cell, short = cis contacts at 1-Mb map offset "
                     f"{SHORT_OFF[0]} (separations 0-2 Mb), long = offsets {LONG_OFF[0]}-{LONG_OFF[1]} "
                     f"(separations 18-54 Mb), autosomes pooled; cells with >= {MIN_GE1} cis contacts at offsets >= 1",
        "seq_frac": "short / long as fractions of the cis contacts at offsets >= 1 (>= 1 Mb, coarsely)",
        "imaging_dist_ratio": "log2(median d(19-53 Mb pairs) / median d(1-2 Mb pairs)) per cell, copies and autosomes "
                              "pooled; cells with >= 10 short and >= 30 long pairs",
        "imaging_prox_ratio": "log2((k_s + 0.5) / (n_s + 1)) - log2((k_l + 0.5) / (n_l + 1)), k = pairs closer than "
                              "r; r = the cell's 1-Mb unit (u1) or the set's median unit (s1)",
        "contrast": "ExN minus Oligo: difference of medians, bootstrap 95% CI over cells (2,000), Cliff's delta, "
                    "Mann-Whitney P (cells as independent)",
        "depth_adjusted": "OLS value ~ class + log10 depth (cis contacts; imaging: detected locus copies), "
                          "ExN - Oligo coefficient, bootstrap CI",
        "thinned": "short / long counts thinned binomially to the 20th percentile of contacts at offsets >= 1",
        "classes": {k: v["classes"] for k, v in DATASETS.items()} | {"tan2021_cortex": TAN["classes"],
                                                                     "takei2021_brain": TAKEI,
                                                                     "hicrna_mouse_brain_domains_r1": GUO_DOMAINS}},
        "stage_logs": logs, "datasets": {}}
    D = out["datasets"]
    for name, spec in DATASETS.items():
        if (work / f"cells_{name}.parquet").exists():
            t = _seq_table(work, name)
            D[name] = analyze_seq(t, spec, rng, n_boot)
            print(f"[analyze] {name}", flush=True)
    if (work / "cells_tan2021_cortex.parquet").exists():
        t = _seq_table(work, "tan2021_cortex")
        D["tan2021_cortex"] = analyze_seq(t, TAN, rng, n_boot)
        t["ratio_exact"] = _ratio(t["exact_short"], t["exact_long"])
        lab = t[t.cls.notna() & (t.n_ge1 >= MIN_GE1)]
        D["tan2021_cortex"]["ratio_exact_separations"] = summarize(lab, "ratio_exact", rng, n_boot=n_boot)
    # Guo brain: domains of r1 and the histogram-based checks
    if (work / "cells_hicrna_mouse_brain.parquet").exists():
        t = _seq_table(work, "hicrna_mouse_brain")
        r1 = t[(t["section"] == "mouse_brain_r1") & (t["n_ge1"] >= MIN_GE1)].copy()
        r1["cls"] = r1["cluster_cellcharter"].astype(str).str.replace(r"\.0$", "", regex=True).map(GUO_DOMAINS)
        r1 = r1[r1.cls.notna()]
        D["hicrna_mouse_brain_domains_r1"] = {
            "assay": "spatial Hi-C-RNA (Guo 2026), section r1 by the authors' domains", "modality": "spatial Hi-C",
            "ratio": summarize(r1, "ratio", rng, depth="log10_cis", a="cortex", b="white matter", n_boot=n_boot)}
        if (work / "guo_stats.parquet").exists():
            g = pd.read_parquet(work / "guo_stats.parquet")
            t = t.join(g, how="left")
            t["hist_ratio"] = _ratio(t["hist_short"], t["hist_long"])
            pc = t[t.cls.notna() & (t.n_ge1 >= MIN_GE1)]
            from scipy.stats import spearmanr
            chk = {"spearman_map_vs_hist_ratio": float(spearmanr(pc["ratio"], pc["hist_ratio"]).statistic),
                   "spearman_map_vs_guo_ratio": float(spearmanr(pc["ratio"], pc["guo_short_long_ratio"],
                                                                nan_policy="omit").statistic),
                   "hist_ratio": summarize(pc, "hist_ratio", rng, depth="log10_cis", n_boot=n_boot),
                   "guo_short_long_ratio_log2": summarize(pc.assign(g2=np.log2(pc["guo_short_long_ratio"])), "g2",
                                                          rng, depth="log10_cis", n_boot=n_boot)}
            r1 = r1.join(g, how="left")
            r1["hist_ratio"] = _ratio(r1["hist_short"], r1["hist_long"])
            r1["g2"] = np.log2(r1["guo_short_long_ratio"])
            chk["domains_r1_hist_ratio"] = summarize(r1, "hist_ratio", rng, a="cortex", b="white matter", n_boot=n_boot)
            chk["domains_r1_guo_ratio_log2"] = summarize(r1, "g2", rng, a="cortex", b="white matter", n_boot=n_boot)
            D["hicrna_mouse_brain"]["checks_contact_stats"] = chk
    # imaging
    for name, (assay, modality) in SETS.items():
        p = work / f"imaging_{name}.parquet"
        if not p.exists():
            continue
        t = pd.read_parquet(p)
        cmap = TAKEI if name.startswith("takei") else TAN["classes"]
        t["cls"] = t["cell_type"].map(cmap)
        t["dist_ratio"] = np.log2(t["d_long"] / t["d_short"])
        for f in ("u1", "s1", "u0.5", "u2"):
            ks, kl = f"k_short_{f}", f"k_long_{f}"
            t[f"prox_ratio_{f}"] = (np.log2((t[ks] + 0.5) / (t["n_short"] + 1))
                                    - np.log2((t[kl] + 0.5) / (t["n_long"] + 1)))
        t["log10_loci"] = np.log10(t["n_loci"].clip(lower=1))
        lab = t[t.cls.notna()]
        use = lab[(lab.n_short >= 10) & (lab.n_long >= 30)]
        res = {"assay": assay, "modality": modality, "n_cells_labelled": int(len(lab)), "n_cells_used": int(len(use)),
               "short_pairs_per_cell_median": float(use.n_short.median()),
               "long_pairs_per_cell_median": float(use.n_long.median()),
               "detected_locus_copies_median": float(use.n_loci.median()),
               "dist_ratio": summarize(use, "dist_ratio", rng, depth="log10_loci", n_boot=n_boot),
               "prox_ratio_u1": summarize(use, "prox_ratio_u1", rng, depth="log10_loci", n_boot=n_boot),
               "prox_ratio_s1": summarize(use, "prox_ratio_s1", rng, depth="log10_loci", n_boot=n_boot),
               "prox_ratio_u0.5": summarize(use, "prox_ratio_u0.5", rng, n_boot=500),
               "prox_ratio_u2": summarize(use, "prox_ratio_u2", rng, n_boot=500),
               "d_short_median_by_class": {c: float(v) for c, v in use.groupby("cls")["d_short"].median().items()},
               "d_long_median_by_class": {c: float(v) for c, v in use.groupby("cls")["d_long"].median().items()},
               "unit_median_by_class": {c: float(v) for c, v in use.groupby("cls")["unit"].median().items()}}
        D[name] = res
        print(f"[analyze] {name}", flush=True)
    # across datasets
    rows, signs = {}, {}
    for name, r in D.items():
        if "pooled" in r and "ratio" not in r:                       # pooled only
            rows[name] = r["pooled"]["by_class"]
            e = r["pooled"].get("exn_minus_oligo")
        elif "ratio" in r and name != "hicrna_mouse_brain_domains_r1":
            rows[name] = r["ratio"]["median_by_class"]
            e = r["ratio"].get("contrast")
        elif "dist_ratio" in r:
            rows[name] = r["dist_ratio"]["median_by_class"]
            e = r["dist_ratio"].get("contrast")
        else:
            e = r["ratio"].get("contrast") if "ratio" in r else None
        if e and "diff" in e:
            signs[name] = {"diff": e["diff"], "ci95": e["ci95"], "positive": e["diff"] > 0,
                           "ci_excludes_0": bool(e["ci95"][0] > 0 or e["ci95"][1] < 0),
                           "modality": r.get("modality")}
    M = pd.DataFrame(rows).T
    seq_names = [n for n in M.index if D[n].get("modality") in ("scHi-C", "spatial Hi-C")]
    img_names = [n for n in M.index if n.startswith("takei")]
    across = {"exn_minus_oligo": signs,
              "kendall_w": {
                  "sequencing_core4": kendall_w(M.loc[seq_names, CORE]),
                  "sequencing_6": kendall_w(M.loc[seq_names, [c for c in CLASSES if c in M]]),
                  "sequencing_plus_imaging_labels_core4": kendall_w(
                      M.loc[seq_names + [n for n in img_names if n.endswith("labels")], CORE])},
              "class_medians": {n: {c: (None if pd.isna(v) else float(v)) for c, v in M.loc[n].items()}
                                for n in M.index}}
    out["across"] = across
    path = save(results / "pilot.json", out, script="benchmarks/cross_assay/pilot.py",
                datasets=list(DATASETS) + ["tan2021_cortex", "takei2021_brain"],
                params={"seed": seed, "n_boot": n_boot, "short_offsets": SHORT_OFF, "long_offsets": LONG_OFF,
                        "short_bp": SHORT_BP, "long_bp": LONG_BP, "min_ge1": MIN_GE1})
    (results / "pilot.md").write_text(markdown(out))
    print(markdown(out))
    return {"results": str(path)}


def markdown(out: dict) -> str:
    D = out["datasets"]
    lines = ["| dataset | modality | metric | " + " | ".join(CLASSES) + " | ExN - Oligo [95% CI] | Cliff | depth-adj. |",
             "|---|---|---|" + "---|" * len(CLASSES) + "---|---|---|"]
    for name, r in D.items():
        if "dist_ratio" in r:
            m, metric = r["dist_ratio"], "dist ratio"
        elif "ratio" in r:
            m, metric = r["ratio"], "contact ratio"
        else:
            m, metric = None, "pooled ratio"
        if m is None:
            med = r["pooled"]["by_class"]
            e = r["pooled"].get("exn_minus_oligo", {})
            cliff, adj = "", ""
        else:
            med = m["median_by_class"]
            e = m.get("contrast", {})
            cliff = f"{e['cliffs_delta']:+.2f}" if "cliffs_delta" in e else ""
            a = m.get("contrast_depth_adjusted", {})
            adj = f"{a['diff']:+.3f} [{a['ci95'][0]:+.3f}, {a['ci95'][1]:+.3f}]" if a else ""
        if name.endswith("domains_r1"):
            cells = [f"cortex {med.get('cortex', float('nan')):.3f}", f"WM {med.get('white matter', float('nan')):.3f}"]
            cells += [""] * (len(CLASSES) - 2)
        else:
            cells = [f"{med[c]:.3f}" if c in med else "" for c in CLASSES]
        ci = f"{e['diff']:+.3f} [{e['ci95'][0]:+.3f}, {e['ci95'][1]:+.3f}]" if "diff" in e else ""
        lines.append(f"| {name} | {r.get('modality', '')} | {metric} | " + " | ".join(cells) + f" | {ci} | {cliff} | {adj} |")
    w = out["across"]["kendall_w"]
    lines.append("")
    for k, v in w.items():
        if "W" in v:
            lines.append(f"- Kendall's W {k}: {v['W']:.2f} ({v['n_datasets']} datasets x {v['n_classes']} classes, "
                         f"P = {v['p']:.2g}); mean ranks {json.dumps({c: round(x, 2) for c, x in v['mean_rank'].items()})}")
    return "\n".join(lines) + "\n"


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--work", type=Path, required=True)
    ap.add_argument("--results", type=Path, default=HERE / "results")
    ap.add_argument("--stages", nargs="+", default=["seq", "tan", "guo", "imaging", "analyze"])
    ap.add_argument("--datasets", nargs="+", default=list(DATASETS))
    ap.add_argument("--tan-dir", type=Path)
    ap.add_argument("--tan-cells", type=Path, default=HERE.parent / "screcon" / "data" / "tan2021_adult_cortex_cells.tsv")
    ap.add_argument("--tan-limit", type=int)
    ap.add_argument("--sets", type=Path)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--boot", type=int, default=2000)
    a = ap.parse_args()
    a.work.mkdir(parents=True, exist_ok=True)
    logf = a.work / "stage_logs.json"
    logs = json.loads(logf.read_text()) if logf.exists() else {}
    for st in a.stages:
        if st == "seq":
            logs.setdefault("seq", {}).update(stage_seq(a.work, a.datasets, a.workers))
        elif st == "tan":
            logs["tan"] = stage_tan(a.work, a.tan_dir, a.tan_cells, a.workers, a.tan_limit)
        elif st == "guo":
            logs["guo"] = stage_guo(a.work)
        elif st == "imaging":
            logs["imaging"] = stage_imaging(a.work, a.sets)
        elif st == "analyze":
            stage_analyze(a.work, a.results, a.seed, a.boot, logs)
        logf.write_text(json.dumps(logs, indent=1, default=str) + "\n")


if __name__ == "__main__":
    main()
