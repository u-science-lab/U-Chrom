"""Cross-assay analysis (Analysis A, Steps 1-2): one cell-type contrast of short- over long-range proximity in every
single-cell / spatial Hi-C dataset of the mouse cortex and in two imaging datasets, each computed by one library
call, :func:`uchrom.fea.separation_profile`, on the dataset's ``ChromData``.

The question and the statistics are those of the pilot (``pilot.py``, Step 0, whose functions are reused): excitatory
neurons (ExN) against mature oligodendrocytes (Oligo), the class ranking with InN, Astro, OPC and Micro, Kendall's W
across datasets.  What changes:

* every per-cell value comes from ``separation_profile`` (contacts: the per-cell maps linked to the store, 1-Mb
  map offset 1 over offsets 19-53; coordinates: the median 3-D distance of locus pairs 19-54 Mb over 1-2 Mb apart,
  pairs within one chromosome copy, autosomes) — the pilot's own readers are kept only to check it (``check``);
* Tan et al. 2021's contact pairs are binned into a ``.scool`` (``uchrom.io.pairs_to_scool``) and read the same way;
* Liu et al. 2025's DNA-MERFISH of the mouse MOp (11,045 traced cells, Allen subclasses; ``liu2025_mop``, built by
  ``apps/atlas/recipes/build_liu2025_mop.py``) is added: the imaging dataset with separate Oligo and OPC classes.

Stages (``--stages``; tables go to ``--work``, ``analyze`` reads them):

* ``seq``      atlas stores -> ``cells_<dataset>.parquet`` (labels, ``n_cis``, ``n_ge1``, ``n_short``, ``n_long``,
               ``n_mito``) and ``profile_<dataset>.npz`` (contacts per 1-Mb offset 0-199);
* ``tan``      Tan 2021 pairs -> ``.scool`` at 1 Mb -> the same tables;
* ``imaging``  the Liu 2025 store and the pilot's structure sets (Takei 2021 with the authors' homologs and with the
               k-means split, Tan 2021 Dip-C models; ``--sets``) -> ``imaging_<set>.parquet`` (+ profile);
* ``check``    against the pilot's tables (``--pilot-work``): equal counts per cell, and the imaging medians with
               the pilot's closed ranges;
* ``analyze``  -> ``--results``/cross_assay.json and .md;
* ``figure``   -> the inputs of the Extended Data figure (``--figdata``, default the paper's
               ``manuscripts/nmeth-bc/figures/results``).

    python benchmarks/cross_assay/cross_assay.py --work DIR --stages seq tan imaging check analyze \
        --tan-dir $UCHROM_DATA/tan2021_cortex/cells --sets DIR --liu $UCHROM_DATA/liu2025_mop/liu2025_mop.chromdata.zarr \
        --pilot-work DIR
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))
import pilot as P  # noqa: E402
from _record import save  # noqa: E402

RES = P.RES
EDGES = np.r_[0.0, np.arange(0.5, P.MAX_OFF + 0.5)] * RES     # profile bin k = map offset k (k Mb apart)
MITO_COLS = slice(P.MITO_OFF[0], P.MITO_OFF[1] + 1)            # offsets 2-12
MIN_SHORT_PAIRS, MIN_LONG_PAIRS = 10, 30                       # imaging cells used (as in the pilot)
IMAGING = {"liu2025_mop": ("DNA-MERFISH (Liu 2025, MOp)", "imaging"),
           "takei2021_brain_labels": P.SETS["takei2021_brain_labels"],
           "takei2021_brain_kmeans": P.SETS["takei2021_brain_kmeans"],
           "tan2021_dipc_rep1": P.SETS["tan2021_dipc_rep1"]}
LIU_GLIA = {"Astro": "Astro", "Oligo": "Oligo", "OPC": "OPC", "Micro": "Micro"}
LIU_CLASS = {"Gluta": "ExN", "GABA": "InN"}


def params(**kw):
    from uchrom.fea import SeparationParams

    return SeparationParams(edges=EDGES, **kw)


def liu_classes(cells: pd.DataFrame) -> pd.Series:
    """Liu 2025: the glial subclasses by name, neurons by class (Gluta -> ExN, GABA -> InN); the rest left out."""
    sub = cells["cluster_subclass"].astype(str).map(LIU_GLIA)
    cls = cells["cluster_class"].astype(str).map(LIU_CLASS)
    return sub.fillna(cls)


def _cells_table(cd, ids, spec_cols) -> pd.DataFrame:
    cells = cd.cells.copy()
    cells.index = cells.index.astype(str)
    keep = [c for c in spec_cols if c and c in cells]
    tab = cells.reindex(ids)[keep].copy()
    for c in tab.columns:
        if isinstance(tab[c].dtype, pd.CategoricalDtype):
            tab[c] = tab[c].astype(str)
    tab.index.name = "cell_id"
    return tab


def _contact_tables(work: Path, name: str, cd, t: pd.DataFrame, spec_cols) -> dict:
    prof = t.attrs["profile"].to_numpy()
    ok = t["n_cis"].notna().to_numpy()
    t, prof = t[ok], prof[ok]
    tab = _cells_table(cd, t.index, spec_cols)
    tab["n_cis"] = t["n_cis"].to_numpy(np.int64)
    tab["n_ge1"] = t["n_apart"].to_numpy(np.int64)
    tab["n_short"] = t["n_short"].to_numpy(np.int64)
    tab["n_long"] = t["n_long"].to_numpy(np.int64)
    tab["n_mito"] = prof[:, MITO_COLS].sum(1).astype(np.int64)
    tab.to_parquet(work / f"cells_{name}.parquet")
    np.savez_compressed(work / f"profile_{name}.npz", profile=prof.astype(np.float32), cells=np.asarray(t.index),
                        edges=EDGES)
    return {"n_cells": int(len(tab)), "cis_contacts_median": float(tab["n_cis"].median())}


# ------------------------------------------------------------------------------------------------- stages

def stage_seq(work: Path, names, workers: int) -> dict:
    import uchrom.datasets as ds
    from uchrom.fea import separation_profile

    log = {"pandas_string_dtype_shim": P._pandas_compat()}
    for name in names:
        t0 = time.perf_counter()
        spec = P.DATASETS[name]
        cd = ds.load(name)
        t = separation_profile(cd, source="contacts", params=params(), workers=workers, key_added=None)
        cols = [spec["column"], spec.get("mitotic"), spec.get("strata"), "n_contacts", "hic_contacts",
                "cluster_cellcharter", "library"]
        log[name] = {**_contact_tables(work, name, cd, t, cols), "maps": list(cd.uns["linked_scool"]),
                     "wall_s": round(time.perf_counter() - t0, 1)}
        print(f"[seq] {name}: {log[name]}", flush=True)
    return log


def stage_tan(work: Path, tan_dir: Path, cells_tsv: Path) -> dict:
    from chromdata import ChromData
    from uchrom.fea import separation_profile
    from uchrom.io.pairs_maps import pairs_chromsizes, pairs_to_scool

    t0 = time.perf_counter()
    meta = pd.read_csv(cells_tsv, sep="\t")
    paths = {n: tan_dir / n / f"{n}.contacts.pairs.txt.gz" for n in meta["name"]}
    paths = {n: str(p) for n, p in paths.items() if p.exists()}
    meta = meta[meta["name"].isin(list(paths))]
    scool = work / "tan2021_cortex_1mb.scool"
    sizes = pairs_chromsizes(next(iter(paths.values())))
    if not scool.exists():
        stats = pairs_to_scool(paths, scool, chromsizes=sizes, resolution=RES, assembly="mm10")
        stats.to_parquet(work / "tan2021_cortex_scool_stats.parquet")
    cells = pd.DataFrame({"cell_type": meta["cell_type"].to_numpy(), "age": meta["age"].to_numpy()},
                         index=pd.Index(meta["name"].astype(str), name="cell_id"))
    no_spots = pd.DataFrame({"chrom": pd.Series(dtype=str), "start": pd.Series(dtype=np.int64),
                             "end": pd.Series(dtype=np.int64), "trace_id": pd.Series(dtype=str),
                             "cell_id": pd.Series(dtype=str)})
    cd = ChromData(np.zeros((0, 3)), no_spots, cells=cells, uns={"genome_assembly": "mm10"})
    cd.link_scool(str(scool), key="per_cell", cell_name="cell_id", genome_assembly="mm10", bin_size=RES)
    t = separation_profile(cd, source="contacts", params=params(), key_added=None)
    log = {**_contact_tables(work, "tan2021_cortex", cd, t, ["cell_type", "age"]), "scool": str(scool),
           "n_chroms": len(sizes), "missing_pairs_files": int(len(meta) - len(paths)),
           "wall_s": round(time.perf_counter() - t0, 1)}
    print(f"[tan] {log}", flush=True)
    return log


def set_to_chromdata(s: dict, cell_type_col: str = "cell_type"):
    """A structure set of benchmarks/screcon/matched_data.py (X: cells x copies x loci x 3, NaN = missing) as a
    ChromData: one trace per (cell, copy, chromosome)."""
    from chromdata import ChromData

    X = s["X"]
    n, H, L, _ = X.shape
    chrom = np.asarray(s["chrom"]).astype(str)
    codes, names = pd.factorize(chrom)
    ci, hi, li = np.nonzero(np.isfinite(X[..., 0]))
    cells = pd.DataFrame(s["cells"])
    ids = cells["cell_id"].astype(str).to_numpy()
    spots = pd.DataFrame({"chrom": chrom[li], "start": np.asarray(s["start"])[li].astype(np.int64),
                          "end": np.asarray(s["end"])[li].astype(np.int64),
                          "trace_id": (ci.astype(np.int64) * H + hi) * len(names) + codes[li],
                          "cell_id": ids[ci]})
    table = pd.DataFrame({"cell_type": cells[cell_type_col].astype(str).to_numpy()},
                         index=pd.Index(ids, name="cell_id"))
    return ChromData(X[ci, hi, li].astype(np.float64), spots, cells=table)


def _imaging_table(work: Path, name: str, t: pd.DataFrame, cell_type: pd.Series, extra: dict) -> dict:
    prof = t.attrs["profile"]
    tab = t.copy()
    tab.insert(0, "cell_type", cell_type.reindex(tab.index).astype(str).to_numpy())
    tab.attrs = {}
    tab.to_parquet(work / f"imaging_{name}.parquet")
    np.savez_compressed(work / f"imaging_profile_{name}.npz", profile=prof.to_numpy(np.float32),
                        n_pairs=t.attrs["n_pairs"].to_numpy(np.int32), cells=np.asarray(t.index), edges=EDGES)
    used = tab[(tab.n_pairs_short >= MIN_SHORT_PAIRS) & (tab.n_pairs_long >= MIN_LONG_PAIRS)]
    return {**extra, "n_cells": int(len(tab)), "n_cells_with_pairs": int(len(used)),
            "short_pairs_median": float(used.n_pairs_short.median()),
            "long_pairs_median": float(used.n_pairs_long.median())}


def stage_imaging(work: Path, sets_dir, liu) -> dict:
    from chromdata import ChromData
    from uchrom.fea import separation_profile

    sys.path.insert(0, str(HERE.parent / "screcon"))
    from matched_data import load_set

    log = {}
    if liu:
        t0 = time.perf_counter()
        cd = ChromData.read(str(liu), backed=True)
        t = separation_profile(cd, source="coords", params=params(), key_added=None)
        cells = cd.cells.copy()
        cells.index = cells.index.astype(str)
        label = cells["cluster_subclass"].astype(str) + " | " + cells["cluster_class"].astype(str)
        log["liu2025_mop"] = _imaging_table(work, "liu2025_mop", t, label, {
            "store": str(liu), "n_spots": int(cd.n_spots), "n_traces": int(cd.n_traces),
            "coordinate_unit": cd.uns.get("xyz_unit"),
            "subclass_counts": {k: int(v) for k, v in cells["cluster_subclass"].astype(str).value_counts().items()},
            "class_counts": {k: int(v) for k, v in cells["cluster_class"].astype(str).value_counts().items()},
            "wall_s": round(time.perf_counter() - t0, 1)})
        print(f"[imaging] liu2025_mop: {log['liu2025_mop']['n_cells_with_pairs']} cells, "
              f"{log['liu2025_mop']['wall_s']} s", flush=True)
    for name in [k for k in IMAGING if k != "liu2025_mop"]:
        p = Path(sets_dir) / f"{name}.npz" if sets_dir else None
        if p is None or not p.exists():
            log[name] = "missing"
            continue
        t0 = time.perf_counter()
        s = load_set(p)
        cd = set_to_chromdata(s)
        t = separation_profile(cd, source="coords", params=params(), key_added=None)
        ct = cd.cells["cell_type"]
        ct.index = ct.index.astype(str)
        log[name] = _imaging_table(work, name, t, ct, {"set": str(p), "set_meta": s["meta"],
                                                      "wall_s": round(time.perf_counter() - t0, 1)})
        print(f"[imaging] {name}: {log[name]}", flush=True)
    return log


def stage_check(work: Path, pilot_work: Path, sets_dir) -> dict:
    """The library against the pilot's own readers: counts per cell (contacts), medians with the pilot's closed
    ranges (imaging; float32 distances in the pilot, float64 here)."""
    from uchrom.fea import SeparationParams, separation_profile

    out = {}
    for name in list(P.DATASETS) + ["tan2021_cortex"]:
        a, b = pilot_work / f"cells_{name}.parquet", work / f"cells_{name}.parquet"
        if not (a.exists() and b.exists()):
            continue
        a, b = pd.read_parquet(a), pd.read_parquet(b)
        common = a.index.intersection(b.index)
        r = {"n_pilot": int(len(a)), "n_library": int(len(b)), "n_common": int(len(common))}
        for col in ("n_cis", "n_ge1", "n_short", "n_long", "n_mito"):
            x, y = a.loc[common, col].to_numpy(np.int64), b.loc[common, col].to_numpy(np.int64)
            r[col] = {"share_equal": float(np.mean(x == y)), "max_abs_diff": int(np.abs(x - y).max(initial=0)),
                      "sum_pilot": int(x.sum()), "sum_library": int(y.sum())}
        out[name] = r
        print(f"[check] {name}: {json.dumps(r)}", flush=True)
    if sets_dir:
        sys.path.insert(0, str(HERE.parent / "screcon"))
        from matched_data import load_set

        closed = SeparationParams(short=(P.SHORT_BP[0], np.nextafter(P.SHORT_BP[1], np.inf)),
                                  long=(P.LONG_BP[0], np.nextafter(P.LONG_BP[1], np.inf)))
        for name in ("takei2021_brain_labels", "takei2021_brain_kmeans", "tan2021_dipc_rep1"):
            p, ref = Path(sets_dir) / f"{name}.npz", pilot_work / f"imaging_{name}.parquet"
            if not (p.exists() and ref.exists()):
                continue
            t = separation_profile(set_to_chromdata(load_set(p)), source="coords", params=closed, key_added=None)
            a = pd.read_parquet(ref)
            t = t.reindex(a.index.astype(str))
            r = {"n_cells": int(len(a))}
            for lib, pil in (("n_pairs_short", "n_short"), ("n_pairs_long", "n_long")):
                r[lib] = {"share_equal": float(np.mean(t[lib].to_numpy() == a[pil].to_numpy()))}
            for col in ("d_short", "d_long"):
                x, y = a[col].to_numpy(np.float64), t[col].to_numpy(np.float64)
                both = np.isfinite(x) & np.isfinite(y)
                r[col] = {"same_nan": bool(np.array_equal(np.isfinite(x), np.isfinite(y))),
                          "max_rel_diff": float(np.max(np.abs(x[both] - y[both]) / np.abs(x[both]), initial=0))}
            out[f"imaging_{name}"] = r
            print(f"[check] {name}: {json.dumps(r)}", flush=True)
    (work / "check.json").write_text(json.dumps(out, indent=1) + "\n")
    return out


# ------------------------------------------------------------------------------------------------- statistics

def _imaging_frame(work: Path, name: str):
    t = pd.read_parquet(work / f"imaging_{name}.parquet")
    if name == "liu2025_mop":
        parts = t["cell_type"].str.split(" | ", n=1, regex=False, expand=True)
        t["cls"] = liu_classes(pd.DataFrame({"cluster_subclass": parts[0], "cluster_class": parts[1]}, index=t.index))
    else:
        t["cls"] = t["cell_type"].map(P.TAKEI if name.startswith("takei") else P.TAN["classes"])
    t["dist_ratio"] = t["log2_short_long"]
    t["log10_spots"] = np.log10(t["n_spots"].clip(lower=1))
    lab = t[t.cls.notna()]
    return lab, lab[(lab.n_pairs_short >= MIN_SHORT_PAIRS) & (lab.n_pairs_long >= MIN_LONG_PAIRS)]


def stage_analyze(work: Path, results: Path, seed: int, n_boot: int, logs: dict) -> dict:
    rng = np.random.default_rng(seed)
    D = {}
    for name, spec in list(P.DATASETS.items()) + [("tan2021_cortex", P.TAN)]:
        if not (work / f"cells_{name}.parquet").exists():
            continue
        t = P._seq_table(work, name)
        D[name] = P.analyze_seq(t, spec, rng, n_boot)
        if "ratio" in D[name]:
            pc = t[t.cls.notna() & (t.n_ge1 >= P.MIN_GE1)]
            D[name]["astro_minus_oligo"] = P.contrast(pc.loc[pc.cls == "Astro", "ratio"],
                                                      pc.loc[pc.cls == "Oligo", "ratio"], rng, n_boot)
        print(f"[analyze] {name}", flush=True)
    if (work / "cells_hicrna_mouse_brain.parquet").exists():
        t = P._seq_table(work, "hicrna_mouse_brain")
        r1 = t[(t["section"] == "mouse_brain_r1") & (t["n_ge1"] >= P.MIN_GE1)].copy()
        r1["cls"] = r1["cluster_cellcharter"].astype(str).str.replace(r"\.0$", "", regex=True).map(P.GUO_DOMAINS)
        r1 = r1[r1.cls.notna()]
        D["hicrna_mouse_brain_domains_r1"] = {
            "assay": "spatial Hi-C-RNA (Guo 2026), section r1 by the authors' domains", "modality": "spatial Hi-C",
            "ratio": P.summarize(r1, "ratio", rng, depth="log10_cis", a="cortex", b="white matter", n_boot=n_boot)}
    for name, (assay, modality) in IMAGING.items():
        if not (work / f"imaging_{name}.parquet").exists():
            continue
        lab, use = _imaging_frame(work, name)
        D[name] = {"assay": assay, "modality": modality, "n_cells_labelled": int(len(lab)),
                   "n_cells_used": int(len(use)),
                   "short_pairs_per_cell_median": float(use.n_pairs_short.median()),
                   "long_pairs_per_cell_median": float(use.n_pairs_long.median()),
                   "spots_per_cell_median": float(use.n_spots.median()),
                   "dist_ratio": P.summarize(use, "dist_ratio", rng, depth="log10_spots", n_boot=n_boot),
                   "astro_minus_oligo": P.contrast(use.loc[use.cls == "Astro", "dist_ratio"],
                                                   use.loc[use.cls == "Oligo", "dist_ratio"], rng, n_boot),
                   "d_short_median_by_class": {c: float(v) for c, v in use.groupby("cls")["d_short"].median().items()},
                   "d_long_median_by_class": {c: float(v) for c, v in use.groupby("cls")["d_long"].median().items()}}
        print(f"[analyze] {name}", flush=True)
    rows, signs = {}, {}
    for name, r in D.items():
        if "pooled" in r and "ratio" not in r:
            rows[name], e = r["pooled"]["by_class"], r["pooled"].get("exn_minus_oligo")
        elif "ratio" in r and name != "hicrna_mouse_brain_domains_r1":
            rows[name], e = r["ratio"]["median_by_class"], r["ratio"].get("contrast")
        elif "dist_ratio" in r:
            rows[name], e = r["dist_ratio"]["median_by_class"], r["dist_ratio"].get("contrast")
        else:
            e = r["ratio"].get("contrast")
        if e and "diff" in e:
            signs[name] = {"diff": e["diff"], "ci95": e["ci95"], "positive": e["diff"] > 0,
                           "ci_excludes_0": bool(e["ci95"][0] > 0 or e["ci95"][1] < 0), "modality": r.get("modality")}
    M = pd.DataFrame(rows).T
    seq = [n for n in M.index if D[n].get("modality") in ("scHi-C", "spatial Hi-C")]
    six = [c for c in P.CLASSES if c in M]
    W = {"sequencing_core4": P.kendall_w(M.loc[seq, P.CORE]),
         "sequencing_6": P.kendall_w(M.loc[seq, six])}
    if "liu2025_mop" in M.index:
        W["sequencing_plus_liu_core4"] = P.kendall_w(M.loc[seq + ["liu2025_mop"], P.CORE])
        W["sequencing_plus_liu_6"] = P.kendall_w(M.loc[seq + ["liu2025_mop"], six])
        img = ["liu2025_mop"] + [n for n in ("takei2021_brain_labels",) if n in M.index]
        W["sequencing_plus_imaging_core4"] = P.kendall_w(M.loc[seq + img, P.CORE])
    out = {"definitions": {
        "function": "uchrom.fea.separation_profile (SeparationParams defaults: short [1, 2) Mb, long [19, 54) Mb "
                    "midpoint to midpoint, chrX / chrY / chrM left out; profile edges = 1-Mb offsets 0-199)",
        "seq_ratio": "log2((n_short + 0.5) / (n_long + 0.5)) per cell (map offset 1 over offsets 19-53); cells with "
                     f">= {P.MIN_GE1} cis contacts between different bins",
        "imaging_dist_ratio": "log2(median d of pairs 19-54 Mb apart / median d of pairs 1-2 Mb apart) per cell, "
                              f"pairs within a chromosome copy; cells with >= {MIN_SHORT_PAIRS} short and "
                              f">= {MIN_LONG_PAIRS} long pairs",
        "contrast": "difference of medians, bootstrap 95% CI over cells, Cliff's delta, Mann-Whitney P (cells as "
                    "independent)",
        "depth_adjusted": "OLS value ~ class + log10 depth (cis contacts; imaging: spots), bootstrap CI",
        "classes": {k: v["classes"] for k, v in P.DATASETS.items()} | {
            "tan2021_cortex": P.TAN["classes"], "takei2021_brain": P.TAKEI,
            "liu2025_mop": {"cluster_subclass": LIU_GLIA, "cluster_class (other subclasses)": LIU_CLASS},
            "hicrna_mouse_brain_domains_r1": P.GUO_DOMAINS}},
        "stage_logs": logs, "datasets": D,
        "across": {"exn_minus_oligo": signs, "kendall_w": W,
                   "class_medians": {n: {c: (None if pd.isna(v) else float(v)) for c, v in M.loc[n].items()}
                                     for n in M.index}}}
    path = save(results / "cross_assay.json", out, script="benchmarks/cross_assay/cross_assay.py",
                datasets=list(P.DATASETS) + ["tan2021_cortex", "takei2021_brain", "liu2025_mop"],
                params={"seed": seed, "n_boot": n_boot, "min_ge1": P.MIN_GE1, "min_short_pairs": MIN_SHORT_PAIRS,
                        "min_long_pairs": MIN_LONG_PAIRS, "edges_mb": [EDGES[0] / RES, EDGES[-1] / RES]})
    md = P.markdown(out)
    am = ["", "| dataset | Astro - Oligo [95% CI] | Cliff |", "|---|---|---|"]
    for name, r in D.items():
        e = r.get("astro_minus_oligo", {})
        if "diff" in e:
            am.append(f"| {name} | {e['diff']:+.3f} [{e['ci95'][0]:+.3f}, {e['ci95'][1]:+.3f}] | "
                      f"{e['cliffs_delta']:+.2f} |")
    (results / "cross_assay.md").write_text(md + "\n".join(am) + "\n")
    print(md + "\n".join(am), flush=True)
    return {"results": str(path)}


# ------------------------------------------------------------------------------------------------- figure inputs

#: the rows of the Extended Data figure: (dataset, label, group)
FIG_ROWS = [("hires_brain", "HiRES", "sequencing"), ("gageseq_mouse_cortex", "GAGE-seq", "sequencing"),
            ("droplet_hic_mouse_cortex", "Droplet Hi-C", "sequencing"),
            ("paired_hic_mouse_cortex", "Paired Hi-C", "sequencing"),
            ("dschic_aging_cortex", "dscHi-C", "sequencing"), ("schicar_mouse_cortex", "scHiCAR", "sequencing"),
            ("tan2021_cortex", "Dip-C", "sequencing"), ("hicrna_mouse_brain", "Spatial Hi-C-RNA", "sequencing"),
            ("liu2025_mop", "DNA-MERFISH", "imaging"), ("takei2021_brain_labels", "DNA seqFISH+", "imaging"),
            ("takei2021_brain_kmeans", "DNA seqFISH+, k-means copies", "imaging"),
            ("tan2021_dipc_rep1", "Dip-C 3D models", "models")]
FIG_PROFILE_MAX = 60                                           # separations shown, Mb


def _cliff(x, y) -> float:
    from scipy.stats import mannwhitneyu

    return float(2 * mannwhitneyu(x, y).statistic / (len(x) * len(y)) - 1)


def _cliff_ci(x, y, rng, n_boot: int) -> dict:
    x, y = np.asarray(x, float), np.asarray(y, float)
    x, y = x[np.isfinite(x)], y[np.isfinite(y)]
    if len(x) < 3 or len(y) < 3:
        return {}
    b = [_cliff(rng.choice(x, len(x)), rng.choice(y, len(y))) for _ in range(n_boot)]
    return {"cliffs_delta": _cliff(x, y), "ci95": [float(np.quantile(b, .025)), float(np.quantile(b, .975))],
            "n_a": int(len(x)), "n_b": int(len(y))}


def _per_cell(work: Path, name: str) -> pd.DataFrame:
    """(cls, value) of the cells each dataset's statistics use."""
    if name in IMAGING:
        _, use = _imaging_frame(work, name)
        return use[["cls", "dist_ratio"]].rename(columns={"dist_ratio": "value"})
    t = P._seq_table(work, name)
    pc = t[t.cls.notna() & (t.n_ge1 >= P.MIN_GE1)]
    return pc[["cls", "ratio"]].rename(columns={"ratio": "value"})


def _figdata() -> Path:
    from _paper import paper_root

    root = paper_root()
    if root is None:
        raise SystemExit("u-chrom-paper not found: pass --figdata (or set UCHROM_PAPER)")
    return root / "manuscripts" / "nmeth-bc" / "figures" / "results"


def stage_figure(work: Path, results: Path, figdata: Path, seed: int, n_boot: int) -> dict:
    """Inputs of the Extended Data figure (u-chrom-paper manuscripts/nmeth-bc/figures/make_ed_cross_assay.py):
    ``cross_assay_figure.json`` (per dataset: class medians, n, ExN - Oligo and Astro - Oligo with Cliff's delta and
    its bootstrap CI), ``cross_assay_cells.parquet`` (per-cell values of GAGE-seq, Liu 2025, Takei 2021) and
    ``cross_assay_profiles.parquet`` (class medians of the per-cell profiles, GAGE-seq and Liu 2025)."""
    rng = np.random.default_rng(seed)
    figdata.mkdir(parents=True, exist_ok=True)
    R = json.loads((results / "cross_assay.json").read_text())["results"]
    D, med = R["datasets"], R["across"]["class_medians"]
    rows = []
    for name, label, group in FIG_ROWS:
        if name not in D:
            continue
        r = D[name]
        row = {"dataset": name, "label": label, "group": group, "assay": r.get("assay"),
               "medians": {c: v for c, v in med.get(name, {}).items() if v is not None}}
        if "ratio" in r:
            row["n_by_class"], row["metric"] = r["ratio"]["n_by_class"], "contacts"
            row["exn_minus_oligo_diff"] = r["ratio"]["contrast"]
        elif "dist_ratio" in r:
            row["n_by_class"], row["metric"] = r["dist_ratio"]["n_by_class"], "distances"
            row["exn_minus_oligo_diff"] = r["dist_ratio"]["contrast"]
        else:
            row["metric"], row["pooled_only"] = "contacts, pooled by class", True
            row["exn_minus_oligo_diff"] = r["pooled"]["exn_minus_oligo"]
        if not row.get("pooled_only"):
            f = _per_cell(work, name)
            for a, b in (("ExN", "Oligo"), ("Astro", "Oligo")):
                row[f"{a.lower()}_minus_{b.lower()}"] = _cliff_ci(f.loc[f.cls == a, "value"],
                                                                 f.loc[f.cls == b, "value"], rng, n_boot)
        rows.append(row)
        print(f"[figure] {name}", flush=True)
    # Liu 2025's OPCs pooled with its oligodendrocytes (a lineage class, as Takei 2021's may be): Astro against it
    f = _per_cell(work, "liu2025_mop")
    lineage = f[f.cls.isin(["Oligo", "OPC"])]
    astro = f.loc[f.cls == "Astro", "value"]
    lin = {"n_oligo": int((lineage.cls == "Oligo").sum()), "n_opc": int((lineage.cls == "OPC").sum()),
           "opc_share": float((lineage.cls == "OPC").mean()), "median_astro": float(astro.median()),
           "median_oligo_lineage": float(lineage["value"].median()),
           "astro_minus_lineage": _cliff_ci(astro, lineage["value"], rng, n_boot)}
    cells = []
    for name in ("gageseq_mouse_cortex", "liu2025_mop", "takei2021_brain_labels"):
        f = _per_cell(work, name)
        cells.append(f.assign(dataset=name).reset_index())
    pd.concat(cells, ignore_index=True).to_parquet(figdata / "cross_assay_cells.parquet")
    prof = []
    k = np.arange(1, FIG_PROFILE_MAX + 1)
    g = P._seq_table(work, "gageseq_mouse_cortex")
    z = np.load(work / "profile_gageseq_mouse_cortex.npz", allow_pickle=True)
    pr = pd.DataFrame(z["profile"][:, k], index=pd.Index(z["cells"].astype(str)))
    use = g[g.cls.notna() & (g.n_ge1 >= P.MIN_GE1)]
    share = pr.loc[use.index].div(use["n_ge1"].astype(float), axis=0)
    for c, sub in share.groupby(use["cls"]):
        prof.append(pd.DataFrame({"dataset": "gageseq_mouse_cortex", "cls": c, "separation_mb": k,
                                  "value": sub.median().to_numpy(), "n_cells": len(sub)}))
    _, use = _imaging_frame(work, "liu2025_mop")
    z = np.load(work / "imaging_profile_liu2025_mop.npz", allow_pickle=True)
    pr = pd.DataFrame(z["profile"][:, k], index=pd.Index(z["cells"].astype(str))).loc[use.index]
    for c, sub in pr.groupby(use["cls"]):
        prof.append(pd.DataFrame({"dataset": "liu2025_mop", "cls": c, "separation_mb": k,
                                  "value": sub.median(skipna=True).to_numpy(), "n_cells": len(sub)}))
    pd.concat(prof, ignore_index=True).to_parquet(figdata / "cross_assay_profiles.parquet")
    out = {"rows": rows, "kendall_w": R["across"]["kendall_w"], "liu_lineage_pooled": lin,
           "definitions": {"value": R["definitions"]["seq_ratio"] + "; imaging: " + R["definitions"]["imaging_dist_ratio"],
                           "cliff": f"Cliff's delta (2U / (n_a n_b) - 1), bootstrap 95% CI over cells ({n_boot})",
                           "profiles": "GAGE-seq: per cell, the contacts at each 1-Mb map offset over its contacts "
                                       "between different bins, class median; Liu 2025: per cell, the median distance "
                                       "(um) of locus pairs [k - 0.5, k + 0.5) Mb apart, class median"}}
    path = save(figdata / "cross_assay_figure.json", out, script="benchmarks/cross_assay/cross_assay.py",
                datasets=[r["dataset"] for r in rows], params={"seed": seed, "n_boot": n_boot,
                                                                "profile_max_mb": FIG_PROFILE_MAX})
    return {"figdata": str(figdata), "json": str(path)}


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--work", type=Path, required=True)
    ap.add_argument("--results", type=Path, default=HERE / "results")
    ap.add_argument("--stages", nargs="+", default=["seq", "tan", "imaging", "check", "analyze"])
    ap.add_argument("--datasets", nargs="+", default=list(P.DATASETS))
    ap.add_argument("--tan-dir", type=Path)
    ap.add_argument("--tan-cells", type=Path, default=HERE.parent / "screcon" / "data" / "tan2021_adult_cortex_cells.tsv")
    ap.add_argument("--sets", type=Path)
    ap.add_argument("--liu", type=Path)
    ap.add_argument("--pilot-work", type=Path)
    ap.add_argument("--figdata", type=Path, help="figure inputs (default: <u-chrom-paper>/manuscripts/nmeth-bc/"
                                                   "figures/results)")
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
            logs["tan"] = stage_tan(a.work, a.tan_dir, a.tan_cells)
        elif st == "imaging":
            logs["imaging"] = stage_imaging(a.work, a.sets, a.liu)
        elif st == "check":
            logs["check"] = stage_check(a.work, a.pilot_work, a.sets)
        elif st == "analyze":
            stage_analyze(a.work, a.results, a.seed, a.boot, logs)
        elif st == "figure":
            stage_figure(a.work, a.results, a.figdata or _figdata(), a.seed, min(a.boot, 1000))
        logf.write_text(json.dumps(logs, indent=1, default=str) + "\n")


if __name__ == "__main__":
    main()
