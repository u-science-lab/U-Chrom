"""uchrom.spatial against the reference implementations on real data: the spot RNA counts of Guo et al. 2026's mouse
brain section r1 (atlas ``hicrna_mouse_brain``) — the kind of data SPARK-X was built for.

* SPARK-X (``uchrom.spatial.sparkx``) vs ``SPARK::sparkx`` (R, xzhoulab/SPARK @a8b4bf2): the same count matrix and
  array coordinates, all eleven kernels; statistics, per-kernel and combined p-values, BY-adjusted calls.
* Moran's I / Geary's C (``uchrom.spatial.spatial_autocorr``) vs ``esda`` (PySAL) on log1p CP10k expression, the
  8 adjacent spots (libpysal ``DistanceBand(threshold=1.5)``, row-standardised): statistics, expectations, variances
  under normality and randomisation, z-scores.

    python benchmarks/spatial_variable/validate_stats.py --out $SCRATCH/uchrom-nd/runs/sv/validate
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

R_SCRIPT = r"""
suppressMessages({library(SPARK); library(Matrix)})
args <- commandArgs(trailingOnly = TRUE)
counts <- readMM(file.path(args[1], "counts.mtx"))            # genes x spots
rownames(counts) <- readLines(file.path(args[1], "genes.txt"))
colnames(counts) <- readLines(file.path(args[1], "spots.txt"))
loc <- as.matrix(read.csv(file.path(args[1], "coords.csv"), row.names = 1))
t0 <- Sys.time()
res <- sparkx(counts, loc, numCores = as.integer(args[2]), option = "mixture", verbose = FALSE)
cat("SPARK-X (R):", format(Sys.time() - t0), "\n")
write.csv(res$stats, file.path(args[1], "r_stats.csv"))
write.csv(res$res_stest, file.path(args[1], "r_pvals.csv"))
write.csv(res$res_mtest, file.path(args[1], "r_combined.csv"))
cat("SPARK", as.character(packageVersion("SPARK")), "R", R.version.string, "\n")
"""


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, flush=True)


def main(argv=None):
    import scipy.io
    import scipy.sparse as sps

    import uchrom.datasets as ds
    from uchrom.spatial import KERNELS, SpatialGraph, sparkx, spatial_autocorr
    from _record import save

    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--out", required=True)
    ap.add_argument("--section", default="mouse_brain_r1")
    ap.add_argument("--min-detect", type=float, default=0.05, help="genes detected in at least this share of spots")
    ap.add_argument("--n-moran", type=int, default=1000, help="genes for Moran / Geary (most detected)")
    ap.add_argument("--results", default=str(HERE / "results"))
    a = ap.parse_args(argv)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    cores = int(os.environ.get("SLURM_CPUS_PER_TASK", "4"))

    cd = ds.load("hicrna_mouse_brain")
    ids = pd.Index([str(i) for i in cd._cell_ids_axis()])
    c = cd.cells.copy()
    c.index = ids
    sec = c.index[c.section == a.section]
    adata = cd.linked_adata[list(sec)]
    X = sps.csr_matrix(adata.X).astype(np.float64)
    tot = np.asarray(X.sum(1)).ravel()
    keep_spots = tot > 0
    X = X[keep_spots]
    spots = sec[keep_spots]
    det = np.asarray((X > 0).mean(0)).ravel()
    genes = np.flatnonzero(det >= a.min_detect)
    Xg = X[:, genes]
    names = adata.var_names[genes].astype(str)
    xy = c.loc[spots, ["centroid_x", "centroid_y"]].to_numpy(float)
    log(f"{a.section}: {len(spots)} spots, {len(genes)} genes detected in >= {a.min_detect:.0%}")

    # --- SPARK-X: R vs ours -------------------------------------------------------------------------------
    scipy.io.mmwrite(out / "counts.mtx", Xg.T.tocoo())
    (out / "genes.txt").write_text("\n".join(names) + "\n")
    (out / "spots.txt").write_text("\n".join(spots) + "\n")
    pd.DataFrame(xy, index=spots, columns=["x", "y"]).to_csv(out / "coords.csv")
    (out / "sparkx_ref.R").write_text(R_SCRIPT)
    t = time.time()
    subprocess.run(["Rscript", str(out / "sparkx_ref.R"), str(out), str(cores)], check=True)
    t_r = time.time() - t
    t = time.time()
    ours = sparkx(pd.DataFrame(Xg.toarray(), columns=names), xy)
    t_ours = time.time() - t
    r_stats = pd.read_csv(out / "r_stats.csv", index_col=0)
    r_p = pd.read_csv(out / "r_pvals.csv", index_col=0)
    r_c = pd.read_csv(out / "r_combined.csv", index_col=0)
    common = r_c.index.intersection(ours.index)
    sx = {"n_spots": int(len(spots)), "n_genes": int(len(common)), "seconds_r": t_r, "seconds_uchrom": t_ours,
          "cores_r": cores}
    for k in KERNELS:
        rs, os_ = r_stats.loc[common, k].to_numpy(), ours.loc[common, f"stat_{k}"].to_numpy()
        rp, op = r_p.loc[common, k].to_numpy(), ours.loc[common, f"pval_{k}"].to_numpy()
        sx[f"kernel/{k}"] = {"stat_max_rel_diff": float(np.nanmax(np.abs(os_ - rs) / np.abs(rs))),
                             "pval_max_abs_diff": float(np.nanmax(np.abs(op - rp))),
                             "pval_max_abs_diff_where_r_ge_1e-4": float(np.nanmax(np.abs(op - rp)[rp >= 1e-4]))
                             if (rp >= 1e-4).any() else None}
    rcomb, ocomb = r_c.loc[common, "combinedPval"].to_numpy(), ours.loc[common, "pval"].to_numpy()
    radj, oadj = r_c.loc[common, "adjustedPval"].to_numpy(), ours.loc[common, "padj"].to_numpy()
    lr, lo = -np.log10(np.maximum(rcomb, 1e-300)), -np.log10(np.maximum(ocomb, 1e-300))
    sig_r, sig_o = radj < 0.05, oadj < 0.05
    sx["combined"] = {"pval_max_abs_diff": float(np.max(np.abs(ocomb - rcomb))),
                      "spearman_neglog10": float(pd.Series(lr).corr(pd.Series(lo), method="spearman")),
                      "n_sig_r": int(sig_r.sum()), "n_sig_uchrom": int(sig_o.sum()),
                      "n_sig_both": int((sig_r & sig_o).sum()),
                      "n_calls_differ": int((sig_r != sig_o).sum())}
    log("SPARK-X:", sx["combined"])

    # --- Moran's I / Geary's C: esda vs ours ----------------------------------------------------------------
    import esda
    import libpysal

    top = np.argsort(-det[genes])[: a.n_moran]
    Y = np.log1p(Xg[:, top].toarray() / tot[keep_spots][:, None] * 1e4)
    gnames = names[top]
    w = libpysal.weights.DistanceBand(xy, threshold=1.5, binary=True, silence_warnings=True)
    # our graph from the same neighbours (positions as the store's), for a like-for-like comparison
    from uchrom.spatial import spatial_neighbors
    from chromdata import ChromData

    cdq = ChromData(coords=np.zeros((0, 3)), spots=pd.DataFrame({"chrom": pd.Series([], dtype=str), "start": [],
                                                                 "end": [], "trace_id": []}),
                    cells=pd.DataFrame({"cell_id": spots}))
    cdq.set_cell_positions(xy, cell_ids=list(spots), unit="spot", frame="tissue")
    g = spatial_neighbors(cdq, method="radius", radius=1.5)
    assert list(g.cell_ids) == list(spots)
    vals = pd.DataFrame(Y, index=spots, columns=gnames)
    mi = spatial_autocorr(values=vals, graph=g, alternative="two-sided")
    gc = spatial_autocorr(values=vals, graph=g, method="geary", alternative="two-sided")
    ref = {"I": [], "EI": [], "VI_norm": [], "VI_rand": [], "z_norm": [], "z_rand": [], "p_norm": [],
           "C": [], "VC_norm": [], "VC_rand": [], "zc_norm": [], "zc_rand": []}
    t = time.time()
    for j in range(Y.shape[1]):
        m = esda.Moran(Y[:, j], w, transformation="r", permutations=0)
        gg = esda.Geary(Y[:, j], w, transformation="r", permutations=0)
        ref["I"].append(m.I), ref["EI"].append(m.EI), ref["VI_norm"].append(m.VI_norm)
        ref["VI_rand"].append(m.VI_rand), ref["z_norm"].append(m.z_norm), ref["z_rand"].append(m.z_rand)
        ref["p_norm"].append(m.p_norm)
        ref["C"].append(gg.C), ref["VC_norm"].append(gg.VC_norm), ref["VC_rand"].append(gg.VC_rand)
        ref["zc_norm"].append(gg.z_norm), ref["zc_rand"].append(gg.z_rand)
    t_esda = time.time() - t
    ref = {k: np.asarray(v, float) for k, v in ref.items()}

    def rel(a_, b_):
        return float(np.nanmax(np.abs(a_ - b_) / np.maximum(np.abs(b_), 1e-300)))

    mo = {"n_genes": int(Y.shape[1]), "n_edges": int(g.adjacency.nnz // 2), "esda_edges": int(w.s0 // 2),
          "seconds_esda": t_esda,
          "I_max_rel_diff": rel(mi["I"].to_numpy(), ref["I"]),
          "VI_norm_max_rel_diff": rel(mi["var_norm"].to_numpy(), ref["VI_norm"]),
          "VI_rand_max_rel_diff": rel(mi["var_rand"].to_numpy(), ref["VI_rand"]),
          "z_rand_max_abs_diff": float(np.nanmax(np.abs(mi["z_rand"].to_numpy() - ref["z_rand"]))),
          "p_norm_two_sided_max_abs_diff": float(np.nanmax(np.abs(mi["p_norm"].to_numpy() - ref["p_norm"]))),
          "C_max_rel_diff": rel(gc["C"].to_numpy(), ref["C"]),
          "VC_norm_max_rel_diff": rel(gc["var_norm"].to_numpy(), ref["VC_norm"]),
          "VC_rand_max_rel_diff": rel(gc["var_rand"].to_numpy(), ref["VC_rand"]),
          "zc_rand_max_abs_diff": float(np.nanmax(np.abs(gc["z_rand"].to_numpy() - ref["zc_rand"])))}
    log("Moran / Geary:", mo)
    import esda as _e
    import libpysal as _l

    save(Path(a.results) / "validate_stats.json", {"sparkx_vs_R": sx, "moran_geary_vs_esda": mo},
         script=__file__, datasets=["hicrna_mouse_brain"],
         params={"section": a.section, "min_detect": a.min_detect, "n_moran": a.n_moran},
         references={"SPARK": "xzhoulab/SPARK@a8b4bf27b804 (R)", "esda": _e.__version__, "libpysal": _l.__version__})


if __name__ == "__main__":
    main()
