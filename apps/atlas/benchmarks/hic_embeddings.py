"""The atlas Hi-C embeddings again, with the scHiCluster of U-Chrom b6d8873 (bit-identical to schicluster 1.3.2,
U-Chrom PR #130), and their agreement with the cell labels as apps/atlas/benchmarks/validate.py scores it.

What the atlas recipes did (apps/atlas/recipes/build_*.py, origin/main b6d8873): scool_cell_features on the per-cell
1 Mb .scool (chromosomes of the file without chrY), then embed_cells(source="hic", normalization="none") with
PCA + UMAP and 30 PCs (dscHi-C, Droplet / Paired Hi-C, GAGE-seq, HiRES), 20 PCs and the default methods (PCA,
t-SNE, UMAP; scHiCAR), PCA only with min(10, n - 1) PCs (Uni-C).  The agreement: the share of the k nearest
neighbours of a cell (k = 15 by cell type, 3 by sample; validate.py knn_agreement) with its label.  The old values
are recomputed from the stores' current cellm (written 2026-10-05 or earlier with the scHiCluster of that time).

    python apps/atlas/benchmarks/hic_embeddings.py DATA_DIR OUT_JSON ID [ID ...]

Run 2026-10-15 on tag-308 (CPU only, 24 cores; Sherlock did not schedule the setup job): results/hic_embeddings.json.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[2] / "benchmarks"))                # the repository's benchmarks/_record.py
import _record  # noqa: E402

K = 15
LABELS = ("cell_type", "sample")
#: id -> store, 1 Mb scool (under DATA_DIR), embed_cells arguments
SETS = {
    "hires_brain": ("hires2023/hires_brain.chromdata.zarr", "hires2023/hires_brain_cells_1Mb.scool", {"methods": ("pca", "umap"), "n_pcs": 30}),
    "hires_embryo": ("hires2023/hires_embryo.chromdata.zarr", "hires2023/hires_embryo_cells_1Mb.scool", {"methods": ("pca", "umap"), "n_pcs": 30}),
    "dschic_aging_cortex": ("dschic2025/dschic_aging_cortex.chromdata.zarr", "dschic2025/dschic_aging_cortex_cells_1Mb.scool", {"methods": ("pca", "umap"), "n_pcs": 30}),
    "gageseq_mouse_cortex": ("gageseq2024/gageseq_mouse_cortex.chromdata.zarr", "gageseq2024/gageseq_mouse_cortex_cells_1Mb.scool", {"methods": ("pca", "umap"), "n_pcs": 30}),
    "gageseq_human_bm_cd34": ("gageseq2024/gageseq_human_bm_cd34.chromdata.zarr", "gageseq2024/gageseq_human_bm_cd34_cells_1Mb.scool", {"methods": ("pca", "umap"), "n_pcs": 30}),
    "droplet_hic_mouse_cortex": ("droplet_hic2024/droplet_hic_mouse_cortex.chromdata.zarr", "droplet_hic2024/droplet_hic_mouse_cortex_cells_1Mb.scool", {"methods": ("pca", "umap"), "n_pcs": 30}),
    "paired_hic_mouse_cortex": ("droplet_hic2024/paired_hic_mouse_cortex.chromdata.zarr", "droplet_hic2024/paired_hic_mouse_cortex_cells_1Mb.scool", {"methods": ("pca", "umap"), "n_pcs": 30}),
    "schicar_mouse_cortex": ("schicar_mop/schicar_mop.chromdata.zarr", "schicar_mop/contacts_cells_1Mb.scool", {"n_pcs": 20}),
    "unic_human": ("unic2025/unic_human.chromdata.zarr", "unic2025/unic_human_cells_1Mb.scool", {"methods": ("pca",), "n_pcs": None}),
    "unic_mouse": ("unic2025/unic_mouse.chromdata.zarr", "unic2025/unic_mouse_cells_1Mb.scool", {"methods": ("pca",), "n_pcs": None}),
}


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def knn_agreement(x: np.ndarray, labels: np.ndarray, k: int = K) -> float:   # validate.py, unchanged
    from sklearn.neighbors import NearestNeighbors

    ok = np.isfinite(x).all(1)
    x, labels = x[ok], labels[ok]
    k = min(k, len(x) - 1)
    nn = NearestNeighbors(n_neighbors=k + 1).fit(x).kneighbors(x, return_distance=False)[:, 1:]
    return float((labels[nn] == labels[:, None]).mean())


def one(data: Path, ident: str) -> dict:
    import cooler
    from uchrom import ChromData
    from uchrom.emb import embed_cells, scool_cell_features

    store, scool, kw = SETS[ident]
    store, scool = data / store, data / scool
    cd = ChromData.read(str(store), backed=True)
    c = cd.cells
    label = next((k for k in LABELS if k in c.columns and c[k].nunique() > 1), None)
    has = c[label].notna().to_numpy()
    lab = np.array([str(v) for v in c[label][has]], dtype=object)
    k = K if label == "cell_type" else 3
    old = {key: round(knn_agreement(np.asarray(m, dtype=float)[has], lab, k), 4)
           for key, m in cd.cellm.items() if key.startswith("hic_") and np.asarray(m).ndim == 2}
    first = cooler.fileops.list_scool_cells(str(scool))[0]
    chroms = [str(x) for x in cooler.Cooler(f"{scool}::{first}").chromnames if str(x) != "chrY"]
    t0 = time.time()
    feats, _, depth = scool_cell_features(str(scool), [str(x) for x in c.index], chroms=chroms)
    t_feat = time.time() - t0
    n_missing = int((depth == 0).sum())
    log(f"{ident}: scHiCluster features {feats.shape} in {t_feat:.0f} s ({n_missing} cells without contacts in the file)")
    import pandas as pd
    # a small in-memory object with the store's cells (as the Uni-C recipe builds one): embed_cells writes its cellm
    spots = pd.DataFrame({col: pd.Series(dtype=t) for col, t in
                          [("chrom", str), ("start", np.int64), ("end", np.int64), ("trace_id", str), ("cell_id", str)]})
    mem = ChromData(np.zeros((0, 3)), spots, cells=c.copy())
    args = dict(kw)
    if args.get("n_pcs") is None:
        args["n_pcs"] = min(10, len(c) - 1)
    t0 = time.time()
    embed_cells(mem, source="hic", matrix=feats, normalization="none", **args)
    t_emb = time.time() - t0
    new = {key: round(knn_agreement(np.asarray(m, dtype=float)[has], lab, k), 4)
           for key, m in mem.cellm.items() if key.startswith("hic_")}
    log(f"{ident}: old {old} -> new {new} ({t_emb:.0f} s embedding)")
    return {"label": label, "k": k, "n": int(has.sum()), "n_cells": int(len(c)), "chroms": chroms,
            "n_features": int(feats.shape[1]), "n_cells_without_contacts": n_missing,
            "embed_cells": {k_: (list(v) if isinstance(v, tuple) else v) for k_, v in args.items()},
            "agreement_old": old, "agreement_new": new, "seconds": {"features": round(t_feat, 1), "embedding": round(t_emb, 1)}}


def main() -> None:
    data, out, ids = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3:]
    res = {}
    for ident in ids:
        res[ident] = one(data, ident)
        _record.save(out, res, script="apps/atlas/benchmarks/hic_embeddings.py (the apps/atlas recipes' embeddings + validate.py's agreement)",
                     datasets=list(res), params={"k": K, "labels": list(LABELS),
                                                 "sets": {i: [SETS[i][0], SETS[i][1]] for i in res}})
    log(f"wrote {out}")


if __name__ == "__main__":
    main()
