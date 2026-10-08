"""scA/B on Kim et al. 2020 sci-Hi-C (Nat Commun 11:6386): do sparse single cells separate H1 ES from HFF?

    .venv/bin/python benchmarks/sc_structures/scab_kim2020.py [--out DIR] [--res 500000 1000000 2500000]

Data: ``ds.load("kim2020_scihic")`` — 1,931 cells (H1Esc / HFF, the labels of the Noble lab benchmark), per-cell
maps at 500 kb (hg19), 1,001 - 2.4 M contacts per cell (median ~4 k).  scA/B with the Dip-C defaults (all
contacts, ranks) and the scHiCluster form (cis, raw), CpG frequency of ``hg19_genome``, autosomes, at 500 kb and
coarser (the maps summed by ``resolution=``).  Separation of the two lines: the first 20 PCs of the matrix (every
bin with a value in any cell; missing values -> the bin's mean: in a cell with 4 k contacts most bins have none),
kNN accuracy (5-fold, k = 10), kNN purity, ARI / NMI of k-means and Ward clusters (2 clusters); by quartile of
contacts per cell; next to scHiCluster (``uchrom.emb.embed_contacts``) on the same maps.

Results: a table on stdout and ``scab_kim2020.json`` in ``--out``.
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
from scab_common import cpg_track, fill_columns, load_average, pcs, separation  # noqa: E402

AUTOSOMES = [f"chr{k}" for k in range(1, 23)]


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--out", type=Path, default=Path(tempfile.gettempdir()) / "uchrom_scab_kim2020")
    ap.add_argument("--res", type=int, nargs="*", default=[500_000, 1_000_000, 2_500_000])
    a = ap.parse_args()
    import uchrom.datasets as ds
    from uchrom.datasets._load_schic import HG19
    from uchrom.emb import embed_contacts
    from uchrom.strc.comp.single_cell import ScABParams, single_cell_compartments

    a.out.mkdir(parents=True, exist_ok=True)
    print(f"load: {load_average()}")
    cd = ds.load("kim2020_scihic")
    y = cd.cells["cell_type"].astype(str).to_numpy()
    depth = cd.cells["n_contacts"].to_numpy()
    print(f"{len(y)} cells: {pd.Series(y).value_counts().to_dict()}, contacts median {np.median(depth):,.0f}")
    quart = np.quantile(depth, [0, .25, .5, .75, 1.0])
    rows = []

    def score(name, emb, res):
        for label, sel in [("all", np.ones(len(y), bool))] + [
                (f"Q{k + 1} ({quart[k]:,.0f}-{quart[k + 1]:,.0f})", (depth >= quart[k]) & (depth <= quart[k + 1]))
                for k in range(4)]:
            o = separation(emb[sel], y[sel])
            o.update({"features": name, "resolution": res, "cells": label})
            rows.append(o)
            if label == "all":
                print(f"  {res // 1000:>5} kb {name:<30s}: kNN acc {o['knn_accuracy']:.3f}, purity "
                      f"{o['knn_purity']:.3f}, k-means ARI {o['kmeans_ARI']:.3f}, Ward ARI {o['ward_ARI']:.3f}",
                      flush=True)

    timing = {}
    for res in a.res:
        track = cpg_track("hg19", {c: HG19[c] for c in HG19}, res, a.out / "cache")
        for name, params in (("scA/B Dip-C (all, rank)", ScABParams()),
                             ("scA/B scHiCluster (cis, raw)", ScABParams(contacts="cis", normalize="none"))):
            t0 = time.perf_counter()
            single_cell_compartments(cd, track=track, resolution=res if res != 500_000 else None, chrom=AUTOSOMES,
                                     params=params, key_added="scab")
            timing[f"{name} {res}"] = time.perf_counter() - t0
            m = cd.cellm["scab"]
            finite = np.isfinite(m)
            print(f"{res // 1000} kb {name}: {timing[f'{name} {res}']:.1f} s; bins with a value per cell median "
                  f"{np.median(finite.sum(1)):.0f} of {m.shape[1]}", flush=True)
            score(name, pcs(fill_columns(m, 0.0), 20), res)
    t0 = time.perf_counter()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        embed_contacts(cd, methods=("pca",), n_pcs=20, chroms=AUTOSOMES, key_added="hic")
    timing["embed_contacts 500000"] = time.perf_counter() - t0
    score("scHiCluster embed_contacts", np.asarray(cd.cellm["hic_pca"]), 500_000)
    tab = pd.DataFrame(rows)
    cols = ["resolution", "features", "cells", "n_cells", "knn_accuracy", "knn_balanced_accuracy", "knn_purity",
            "kmeans_ARI", "ward_ARI"]
    print()
    print(tab[cols].to_string(index=False, float_format=lambda v: f"{v:.3f}"))
    out = a.out / "scab_kim2020.json"
    out.write_text(json.dumps({"rows": json.loads(tab.to_json(orient="records")), "seconds": timing,
                               "load": load_average()}, indent=1, default=float))
    print(f"\n-> {out}")


if __name__ == "__main__":
    main()
