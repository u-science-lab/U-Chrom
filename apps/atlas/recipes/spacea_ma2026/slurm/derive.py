"""A SpaceA store (build_store.py) -> the same store with what the analyses and the web browser read.

1. ``clusters["spacea_filtered"]``: the authors' cluster filter (``uchrom.fea.filter_clusters``: size 2-1,000,
   chromosomes > 15 % of the cluster, cis share >= 20 %; checked against their filter_sprite.py cluster by
   cluster); the raw ``clusters["spacea"]`` stay.
2. Contact maps of the filtered clusters (fragment pairs, integers), next to the store and embedded in it
   (``chromdata.embedded``): per spot at 1 Mb (``<store>_1mb.scool``, linked ``per_spot``) and pooled
   (``<store>_pooled.mcool``, 100 kb - 2 Mb, ICE-balanced, linked ``pooled``).  Unweighted pairs give the large
   clusters more weight than the authors' 2/n: the pooled map decays more slowly with distance than theirs.
3. Per-spot counts of the filtered clusters (``filtered_n_clusters``, ``filtered_n_pairs``, ``filtered_n_cis``) in
   ``cells``; a scHiCluster embedding of the per-spot maps (``cellm["hic_pca"]``, ``["hic_umap"]``) and its Leiden
   clusters (``cells["hic_leiden"]``; spatially weak: neighbouring spots share a label at 0.44 vs 0.28 shuffled).

Usage::

    python derive.py STORE.chromdata.zarr [--threads 8]
"""

from __future__ import annotations

import argparse
from pathlib import Path


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("store", type=Path)
    ap.add_argument("--threads", type=int, default=8)
    args = ap.parse_args()

    from chromdata import ChromData
    from chromdata.embedded import embed_links
    from uchrom.datasets._load_snaphic import MM10
    from uchrom.emb import cluster_cells, embed_contacts
    from uchrom.fea.cluster_maps import clusters_to_mcool, clusters_to_scool, filter_clusters

    store = args.store
    stem = store.name.removesuffix(".chromdata.zarr")
    cd = ChromData.read(store)
    cd.cells = cd.cells.drop(columns=[c for c in ("lig", "y") if c in cd.cells])   # stores built before: = centroids
    t = filter_clusters(cd, "spacea")
    print(t, flush=True)
    st = clusters_to_scool(cd, "spacea_filtered", store.with_name(f"{stem}_1mb.scool"), chromsizes=MM10,
                           resolution=1_000_000, max_size=None, link_key="per_spot",
                           label="Per spot (1 Mb, fragment pairs of the filtered clusters)")
    for c in ("n_clusters", "n_pairs", "n_cis"):
        cd.cells[f"filtered_{c}"] = st[c].reindex(cd.cells.index.astype(str)).to_numpy()
    print(st.describe().T[["mean", "50%", "max"]], flush=True)
    clusters_to_mcool(cd, "spacea_filtered", store.with_name(f"{stem}_pooled.mcool"), chromsizes=MM10,
                      resolutions=[100_000, 200_000, 500_000, 1_000_000, 2_000_000], max_size=None,
                      link_key="pooled", label="All spots (fragment pairs of the filtered clusters)",
                      n_threads=args.threads)
    # the linked file names are relative to the store's folder
    for kind in ("linked_scool", "linked_cool"):
        for rec in cd.uns[kind].values():
            rec["path"] = Path(rec["path"]).name
    embed_contacts(cd, contacts="per_spot", key_added="hic", methods=("pca", "umap"), n_threads=args.threads)
    cluster_cells(cd, use="hic_pca", resolution=0.5, key_added="hic_leiden")
    print(cd.cells["hic_leiden"].value_counts().to_dict(), flush=True)
    cd.write(store)
    embed_links(str(store))
    print("embedded", flush=True)


if __name__ == "__main__":
    main()
