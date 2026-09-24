"""Agreement of per-modality cell embeddings with cell type (real data).

For every embedding in ``cd.uns["embeddings"]`` of the example datasets
(``build_takei2025_fov0.py`` / ``build_schicar_mop.py`` outputs):

* kNN label purity — fraction of each cell's k nearest neighbours with the
  same ``cell_type`` (chance = mean over 20 label permutations);
* silhouette of ``cell_type`` (Euclidean);

on the 2-D embedding (t-SNE / UMAP / published) and on the linear space
(PCA / LSI, all kept components).  Cross-modality: ARI between Leiden
clusters (scanpy, kNN k=15 on the linear space, resolution 1) of each pair
of modalities and of each modality with ``cell_type``.

Usage::

    python benchmarks/omics_embeddings.py [--takei PATH] [--schicar PATH]
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parents[1] / "example-data"


def knn_purity(x: np.ndarray, y: np.ndarray, k: int) -> float:
    from sklearn.neighbors import NearestNeighbors

    idx = NearestNeighbors(n_neighbors=k + 1).fit(x).kneighbors(x, return_distance=False)[:, 1:]
    return float((y[idx] == y[:, None]).mean())


def evaluate(cd, k: int, name: str) -> pd.DataFrame:
    from sklearn.metrics import silhouette_score

    y = cd.cells["cell_type"].astype(str).to_numpy()
    rng = np.random.default_rng(0)
    meta = cd.uns.get("embeddings") or {}
    rows = []
    for key, arr in cd.cellm.items():
        x = np.asarray(arr, dtype=np.float64)
        if x.ndim != 2 or x.shape[0] != len(y):
            continue
        m = meta.get(key, {})
        chance = np.mean([knn_purity(x, rng.permutation(y), k) for _ in range(20)])
        rows.append({"dataset": name, "key": key, "modality": m.get("modality", "Published"),
                     "space": f"{x.shape[1]}-D" + (" (linear)" if m.get("method") in ("pca", "lsi") else ""),
                     "n_cells": len(y), f"knn{k}": knn_purity(x, y, k), "chance": chance,
                     "silhouette": float(silhouette_score(x, y))})
    return pd.DataFrame(rows)


def leiden_ari(cd, keys: dict, resolution: float = 1.0) -> pd.DataFrame:
    import anndata as ad
    import scanpy as sc
    from sklearn.metrics import adjusted_rand_score

    y = cd.cells["cell_type"].astype(str).to_numpy()
    labels = {"cell_type": y}
    for mod, key in keys.items():
        a = ad.AnnData(np.zeros((len(y), 1)), obsm={"X": np.asarray(cd.cellm[key], dtype=np.float64)})
        sc.pp.neighbors(a, use_rep="X", n_neighbors=15, random_state=0)
        sc.tl.leiden(a, resolution=resolution, random_state=0, flavor="igraph", n_iterations=2,
                     directed=False)
        labels[mod] = a.obs["leiden"].to_numpy()
        print(f"  Leiden on {key}: {len(set(labels[mod]))} clusters")
    names = list(labels)
    return pd.DataFrame([[adjusted_rand_score(labels[a], labels[b]) for b in names] for a in names],
                        index=names, columns=names)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--takei", default=HERE / "takei2025_fov0" / "takei2025_fov0.h5cd", type=Path)
    ap.add_argument("--schicar", default=HERE / "schicar_mop" / "schicar_mop.h5cd", type=Path)
    args = ap.parse_args()

    from uchrom import ChromData

    pd.set_option("display.width", 200)
    tables = []
    if args.takei.exists():
        cd = ChromData.read(args.takei)
        tables.append(evaluate(cd, 5, "Takei2025 FOV0"))
    if args.schicar.exists():
        cd = ChromData.read(args.schicar)
        tables.append(evaluate(cd, 10, "scHiCAR MOp"))
        keys = {m: k for m, k in (("RNA", "rna_pca"), ("ATAC", "atac_lsi"), ("Hi-C", "hic_pca"))
                if k in cd.cellm}
        print("scHiCAR Leiden ARI (linear spaces):")
        print(leiden_ari(cd, keys).round(3).to_string())
    print(pd.concat(tables).round(3).to_string(index=False))


if __name__ == "__main__":
    main()
