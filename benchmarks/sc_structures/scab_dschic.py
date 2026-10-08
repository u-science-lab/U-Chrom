"""scA/B on the dscHi-C aging cortex atlas store (32,777 cells, 1 Mb per-cell maps embedded, read over HTTP).

    .venv/bin/python benchmarks/sc_structures/scab_dschic.py [--out DIR] [--runs 3] [--subsample 500]

1. Run time / memory: ``single_cell_compartments`` on every cell (Dip-C defaults: all contacts, ranks; the CpG
   frequency of ``mm10_genome``; the autosomes), best of ``--runs``, peak resident memory, the stages from the
   provenance (read = waiting for HTTP reads, bin, sum = the kernel, normalize), the bytes the per-cell pixels
   take in the store; then the cis-only form (no trans partition read).
2. Against the cell-type pseudo-bulk compartments: ``uchrom.fea.pseudobulk(cd, "cell_type")`` (cis + trans,
   ICE) and ``call_compartments_eig`` (E1 oriented by the CpG frequency) per type; per type the mean scA/B of
   its cells vs its E1 (Pearson / Spearman over the autosomal bins), with the CpG track alone as the baseline
   (scA/B is a CpG-weighted average: how much does it add?), the partial correlation given CpG, the cross-type
   matrix r(mean scA/B of type a, E1 of type b), and r(difference of mean scA/B, difference of E1) over the pairs
   of types (the type-specific part); per cell r(scA/B, its type's E1) by contacts per cell.
3. Separation of the annotated cell types: first 20 PCs of the scA/B matrix (bins with a value in >= 90 % of
   the cells, missing -> the bin's mean) vs the store's scHiCluster PCA (``cellm["hic_pca"]``, the same
   per-cell maps; first 20 PCs): kNN accuracy (5-fold, k = 10), kNN purity, ARI / NMI of k-means; by quartile
   of contacts per cell; and on a stratified subsample (``--subsample`` cells per type) both scA/B and a fresh
   ``uchrom.emb.embed_contacts`` (scHiCluster) with Ward clusters too.

Results: tables on stdout and ``scab_dschic.json`` in ``--out``.
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
import time
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from scab_common import (PeakRSS, cpg_track, fill_columns, load_average, partial_r, pcs, pearson,  # noqa: E402
                         separation, spearman)

AUTOSOMES = [f"chr{k}" for k in range(1, 20)]


def stored_bytes(e, store: str, parts) -> int:
    """Compressed bytes of the per-cell pixel arrays of these partitions (HEAD of every shard)."""
    from concurrent.futures import ThreadPoolExecutor

    import fsspec

    fs = fsspec.filesystem("https")
    r = e.resolutions[0]
    shard = e.g[f"r{r}/cis/{e.chroms[0]}/pix"].shards[1]
    urls = []
    for part, n in e.meta["n_pixels"].items():
        name = "trans" if part == "trans" else f"cis/{part}"
        if name not in parts:
            continue
        urls += [f"{store}/embedded/contacts/{e.name}/r{r}/{name}/pix/c/0/{k}" for k in range(-(-n // shard))]
    with ThreadPoolExecutor(16) as ex:
        return int(sum(ex.map(lambda u: fs.info(u)["size"], urls)))


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--out", type=Path, default=Path(tempfile.gettempdir()) / "uchrom_scab_dschic")
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--subsample", type=int, default=500, help="cells per type for the embed_contacts comparison")
    a = ap.parse_args()
    import uchrom.datasets as ds
    from chromdata.embedded import open_all

    from uchrom.emb import embed_contacts
    from uchrom.fea.pseudobulk_maps import pseudobulk
    from uchrom.strc.comp import call_compartments_eig
    from uchrom.strc.comp.single_cell import ScABParams, single_cell_compartments

    a.out.mkdir(parents=True, exist_ok=True)
    res = {"load_start": load_average()}
    print(f"load: {res['load_start']}")
    cd = ds.load("dschic_aging_cortex")
    store = str(cd._links_from())
    e = open_all(store)["per_cell"]
    sizes = e.chromsizes()
    track = cpg_track("mm10", sizes, int(e.resolutions[0]), a.out / "cache")
    cells = cd.cells
    types = list(cells["cell_type"].value_counts().index)
    print(f"{store}: {len(cells):,} cells, {len(types)} types, contacts per cell median "
          f"{cells['n_contacts'].median():,.0f}")

    # --- 1. run time ---------------------------------------------------------------------------------------
    parts_all = [f"cis/{c}" for c in e.chroms] + ["trans"]
    rx_all = stored_bytes(e, store, parts_all)
    rx_cis = stored_bytes(e, store, parts_all[:-1])
    runs = []
    for k in range(a.runs):
        with PeakRSS() as mem:
            t0 = time.perf_counter()
            single_cell_compartments(cd, track=track, chrom=AUTOSOMES, key_added="scab", verbose=(k == 0))
            wall = time.perf_counter() - t0
        runs.append({"wall_s": wall, "peak_rss_gb": mem.peak / 1e9, "rss_increase_gb": (mem.peak - mem.base) / 1e9,
                     "stages_s": cd.results.record("scab").inputs["seconds"], "load": load_average()})
        print(f"run {k + 1}: {wall:.1f} s, +{(mem.peak - mem.base) / 1e9:.2f} GB, stages {runs[-1]['stages_s']}, "
              f"load {runs[-1]['load']}", flush=True)
    best = min(runs, key=lambda r: r["wall_s"])
    with PeakRSS() as mem:
        t0 = time.perf_counter()
        single_cell_compartments(cd, track=track, chrom=AUTOSOMES, params=ScABParams(contacts="cis"),
                                 key_added="scab_cis")
        wall_cis = time.perf_counter() - t0
    res["runtime"] = {"runs": runs, "best_wall_s": best["wall_s"], "transferred_gb_all": rx_all / 1e9,
                      "transferred_gb_cis": rx_cis / 1e9, "mb_per_s_best": rx_all / 1e6 / best["wall_s"],
                      "cis_only": {"wall_s": wall_cis, "rss_increase_gb": (mem.peak - mem.base) / 1e9,
                                   "stages_s": cd.results.record("scab_cis").inputs["seconds"]},
                      "result_matrix_mb": cd.cellm["scab"].nbytes / 1e6}
    print(f"best {best['wall_s']:.1f} s for {rx_all / 1e9:.2f} GB of per-cell pixels "
          f"({rx_all / 1e6 / best['wall_s']:.1f} MB/s); cis only {wall_cis:.1f} s ({rx_cis / 1e9:.2f} GB)")

    m = cd.cellm["scab"]
    table = cd.results["scab"]
    bins = table[["chrom", "start", "end"]].copy()
    y = cells["cell_type"].astype(str).to_numpy()

    # --- 2. vs cell-type pseudo-bulk E1 ---------------------------------------------------------------------
    t0 = time.perf_counter()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        summary = pseudobulk(cd, "cell_type", out_dir=a.out / "pseudobulk", workers=4)
    print(f"pseudobulk of {len(summary)} types in {time.perf_counter() - t0:.0f} s")
    e1 = {}
    for row in summary.itertuples():
        t = call_compartments_eig(cd, contacts=row.key, phasing=track, n_eigs=3, key_added=f"eig.{row.group}")
        t = t[t["chrom"].isin(AUTOSOMES)]
        e1[row.group] = bins.merge(t[["chrom", "start", "E1"]], on=["chrom", "start"], how="left")["E1"].to_numpy()
    cpg = bins.merge(track, on=["chrom", "start", "end"], how="left")["value"].to_numpy()
    means = {g: np.nanmean(m[y == g], axis=0) for g in types}
    per_type = []
    for g in types:
        per_type.append({"type": g, "n_cells": int((y == g).sum()),
                         "contacts_median": float(cells.loc[y == g, "n_contacts"].median()),
                         "r_scab_E1": pearson(means[g], e1[g]), "rho_scab_E1": spearman(means[g], e1[g]),
                         "r_cpg_E1": pearson(cpg, e1[g]), "r_scab_cpg": pearson(means[g], cpg),
                         "partial_r_scab_E1_given_cpg": partial_r(means[g], e1[g], cpg)})
    pt = pd.DataFrame(per_type)
    print("\nmean scA/B of each type vs the type's pseudo-bulk E1 (autosomes, 1 Mb):")
    print(pt.to_string(index=False, float_format=lambda v: f"{v:.3f}"))
    cross = pd.DataFrame({b: {g: pearson(means[g], e1[b]) for g in types} for b in types})   # rows scab, cols E1
    print("\nr(mean scA/B of row type, E1 of column type):")
    print(cross.to_string(float_format=lambda v: f"{v:.3f}"))
    pairs = []
    for i, g in enumerate(types):
        for h in types[i + 1:]:
            pairs.append({"a": g, "b": h, "r_diff_scab_diff_E1": pearson(means[g] - means[h], e1[g] - e1[h]),
                          "rho_diff": spearman(means[g] - means[h], e1[g] - e1[h])})
    pp = pd.DataFrame(pairs)
    print("\nr(scA/B difference, E1 difference) over the pairs of types: median "
          f"{pp['r_diff_scab_diff_E1'].median():.3f} (range {pp['r_diff_scab_diff_E1'].min():.3f} - "
          f"{pp['r_diff_scab_diff_E1'].max():.3f})")
    print(pp.sort_values("r_diff_scab_diff_E1").to_string(index=False, float_format=lambda v: f"{v:.3f}"))
    # per cell: r with its type's E1, by depth
    per_cell = np.full(len(y), np.nan)
    for g in types:
        rows = np.flatnonzero(y == g)
        E = e1[g]
        for r in rows:
            per_cell[r] = pearson(m[r], E)
    depth = cells["n_contacts"].to_numpy()
    q = pd.qcut(depth, 10, labels=False)
    by_depth = pd.DataFrame({"decile": np.arange(10),
                             "contacts_median": [float(np.median(depth[q == k])) for k in range(10)],
                             "r_cell_vs_type_E1_median": [float(np.nanmedian(per_cell[q == k])) for k in range(10)]})
    print("\nper cell r(scA/B, its type's E1) by decile of contacts:")
    print(by_depth.to_string(index=False, float_format=lambda v: f"{v:.3f}"))
    res["vs_pseudobulk"] = {"per_type": per_type, "cross": cross.to_dict(), "pairs": pairs,
                            "per_cell_r_median": float(np.nanmedian(per_cell)), "by_depth": by_depth.to_dict("records"),
                            "pseudobulk": json.loads(summary.drop(columns=["path"]).to_json(orient="records"))}

    # --- 3. separation --------------------------------------------------------------------------------------
    x = fill_columns(m, 0.9)
    t0 = time.perf_counter()
    pc = pcs(x, 20)
    t_pca = time.perf_counter() - t0
    hic = np.asarray(cd.cellm["hic_pca"], dtype=np.float64)[:, :20]
    rows = []
    for name, emb in (("scA/B (all, rank) PCA 20", pc), ("scHiCluster hic_pca 20 (store)", hic)):
        o = separation(emb, y)
        o.update({"features": name, "cells": "all"})
        rows.append(o)
        for k, (lo, hi) in enumerate(zip(*[np.quantile(depth, [0, .25, .5, .75])],
                                         np.quantile(depth, [.25, .5, .75, 1.0]))):
            sel = (depth >= lo) & (depth <= hi)
            o = separation(emb[sel], y[sel])
            o.update({"features": name, "cells": f"contacts Q{k + 1} ({lo:,.0f}-{hi:,.0f})"})
            rows.append(o)
    xc = fill_columns(cd.cellm["scab_cis"], 0.9)
    o = separation(pcs(xc, 20), y)
    o.update({"features": "scA/B (cis, rank) PCA 20", "cells": "all"})
    rows.append(o)
    # stratified subsample: scA/B and a fresh embed_contacts on the same cells, Ward too
    rng = np.random.default_rng(0)
    pick = np.sort(np.concatenate([rng.choice(np.flatnonzero(y == g), min(a.subsample, int((y == g).sum())),
                                              replace=False) for g in types]))
    ids = [str(c) for c in cells.index[pick]]
    t0 = time.perf_counter()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        embed_contacts(cd, cells=ids, methods=("pca",), n_pcs=20, chroms=AUTOSOMES, key_added="hicsub")
    t_hic = time.perf_counter() - t0
    for name, emb in (("scA/B (all, rank) PCA 20", pcs(fill_columns(m[pick], 0.9), 20)),
                      ("scHiCluster embed_contacts PCA 20", np.asarray(cd.cellm["hicsub_pca"])[pick])):
        o = separation(emb, y[pick])
        o.update({"features": name, "cells": f"stratified {len(pick)}"})
        rows.append(o)
    tab = pd.DataFrame(rows)
    cols = ["features", "cells", "n_cells", "knn_accuracy", "knn_balanced_accuracy", "knn_purity", "kmeans_ARI",
            "kmeans_NMI", "ward_ARI", "ward_NMI"]
    print("\nseparation of the annotated cell types:")
    print(tab[[c for c in cols if c in tab.columns]].to_string(index=False, float_format=lambda v: f"{v:.3f}"))
    res["separation"] = json.loads(tab.to_json(orient="records"))
    res["seconds"] = {"pca_scab": t_pca, "embed_contacts_subsample": t_hic}
    res["load_end"] = load_average()
    out = a.out / "scab_dschic.json"
    out.write_text(json.dumps(res, indent=1, default=float))
    print(f"\n-> {out}")


if __name__ == "__main__":
    main()
