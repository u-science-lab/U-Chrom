"""scA/B on Tan et al. 2021 (Cell 184:741) adult cortex Dip-C: does it recover the paper's structure types?

    .venv/bin/python benchmarks/sc_structures/scab_tan2021.py [--out DIR] [--depths 100000 50000 20000 10000]

Data: the 510 adult cortex cells of the registered ``tan2021_cortex`` entry (P56 / P309 / P347, >= 100 k contacts,
cell types from ``tan2021_adult_cortex_cells.tsv``: the paper's "structure types", which the authors obtained by
hierarchical clustering of the first 20 PCs of the scA/B matrix of 3,646 cells), only their ``contacts.pairs``
(hickit, 2.0 GB for the 510 cells; fetched file by file from the registered URLs), binned at 1 Mb into one
``.scool`` (``uchrom.io.pairs_to_scool``, mm10, every contact once: both homologs, as Dip-C ``color2 -H``).

1. ``single_cell_compartments`` with the defaults (Dip-C: all contacts, ranks per cell; CpG frequency of
   ``mm10_genome``), the autosomes (Tan 2021: "2,410 1-Mb bins across the mouse autosome"); also the
   scHiCluster form (cis, no normalisation).
2. Separation of the paper's cell types (types with >= 5 cells; "Unknown" left out): the first 20 PCs of the
   matrix (bins with a value in >= 90 % of the cells, missing values -> the bin's mean), kNN accuracy (5-fold,
   k = 10), kNN purity, ARI / NMI of Ward clusters (the paper's hierarchical clustering) and of k-means, with
   as many clusters as types.  Next to scHiCluster embeddings of the same maps (``uchrom.emb.embed_contacts``).
3. Depth: every cell binomially thinned to 100 k / 50 k / 20 k / 10 k contacts (Tan 2021: structure typing
   "relatively unchanged when contacts were down-sampled to 100 k per cell (or only moderately degrades at
   50 k per cell)"), the same metrics.
4. Run time / peak memory of ``single_cell_compartments`` on the 510 cells (best of 3) and the load.

Results: a table on stdout and ``scab_tan2021.json`` in ``--out``.
"""

from __future__ import annotations

import argparse
import gzip
import json
import sys
import tempfile
import time
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from scab_common import PeakRSS, cpg_track, fill_columns, load_average, pcs, separation, thin_scool  # noqa: E402

HERE = Path(__file__).resolve().parent
CELLS_TSV = HERE.parents[1] / "packages/uchrom/uchrom/datasets/tan2021_adult_cortex_cells.tsv"
RES = 1_000_000
AUTOSOMES = [f"chr{k}" for k in range(1, 20)]


def fetch_contacts(names):
    from uchrom.datasets import _entry, _files, data_dir
    from uchrom.datasets._fetch import download

    want = {f"{n}.contacts.pairs.txt.gz" for n in names}
    out = {}
    for rel, url in _files(_entry("tan2021_cortex")):
        name = rel.rsplit("/", 1)[-1]
        if name in want:
            out[name.split(".")[0]] = download(url, data_dir() / rel, verbose=False)
    return out


def make_cd(scool: Path, cells: pd.DataFrame):
    from chromdata import ChromData

    no_spots = pd.DataFrame({"chrom": pd.Series(dtype=str), "start": pd.Series(dtype=np.int64),
                             "end": pd.Series(dtype=np.int64), "trace_id": pd.Series(dtype=str),
                             "cell_id": pd.Series(dtype=str)})
    cd = ChromData(np.zeros((0, 3)), no_spots, cells=cells.copy(), uns={"genome_assembly": "mm10"})
    cd.link_scool(str(scool), key="per_cell", cell_name="cell_id", genome_assembly="mm10", bin_size=RES)
    return cd


def scab_metrics(cd, track, labels_mask, params=None, key="scab", min_finite=0.9):
    from uchrom.strc.comp.single_cell import ScABParams, single_cell_compartments

    frame = single_cell_compartments(cd, track=track, chrom=AUTOSOMES, params=params or ScABParams(), key_added=key)
    x = fill_columns(cd.cellm[key][labels_mask], min_finite=min_finite)
    return frame, x


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--out", type=Path, default=Path(tempfile.gettempdir()) / "uchrom_scab_tan2021")
    ap.add_argument("--depths", type=int, nargs="*", default=[100_000, 50_000, 20_000, 10_000])
    ap.add_argument("--min-type", type=int, default=5)
    a = ap.parse_args()
    from uchrom.emb import embed_contacts
    from uchrom.io.pairs_maps import pairs_to_scool
    from uchrom.strc.comp.single_cell import ScABParams, single_cell_compartments

    a.out.mkdir(parents=True, exist_ok=True)
    print(f"load: {load_average()}")
    cells = pd.read_csv(CELLS_TSV, sep="\t").rename(columns={"name": "cell_id"}).set_index("cell_id")
    pairs = fetch_contacts(list(cells.index))
    header = [line.split()[1:] for line in gzip.open(next(iter(pairs.values())), "rt")
              if line.startswith("#chromosome")]
    sizes = {c: int(n) for c, n in header}
    scool = a.out / "tan2021_cortex_1Mb.scool"
    if not scool.exists():
        t0 = time.perf_counter()
        stats = pairs_to_scool({n: pairs[n] for n in cells.index}, scool, chromsizes=sizes, resolution=RES,
                               assembly="mm10")
        stats.to_csv(a.out / "tan2021_cortex_1Mb.stats.csv")
        print(f"binned {len(cells)} cells at 1 Mb in {time.perf_counter() - t0:.0f} s")
    stats = pd.read_csv(a.out / "tan2021_cortex_1Mb.stats.csv", index_col=0)
    cells = cells.join(stats[["n_contacts", "n_cis", "n_trans"]])
    print(f"{len(cells)} cells, contacts per cell median {cells['n_contacts'].median():,.0f} "
          f"(range {cells['n_contacts'].min():,} - {cells['n_contacts'].max():,})")
    track = cpg_track("mm10", sizes, RES, a.out / "cache")

    counts = cells["cell_type"].value_counts()
    types = [t for t, n in counts.items() if n >= a.min_type and t != "Unknown"]
    mask = cells["cell_type"].isin(types).to_numpy()
    y = cells["cell_type"].to_numpy()[mask]
    print(f"types scored ({len(types)}, {mask.sum()} cells): " + ", ".join(f"{t} ({counts[t]})" for t in types))
    res = {"n_cells": int(len(cells)), "types": {t: int(counts[t]) for t in types}, "load_start": load_average(),
           "contacts_per_cell": cells["n_contacts"].describe().to_dict()}

    # --- 1 + 4: the scA/B matrix, timing ---------------------------------------------------------------------
    cd = make_cd(scool, cells)
    times, peak = [], 0
    for _ in range(3):
        with PeakRSS() as mem:
            t0 = time.perf_counter()
            single_cell_compartments(cd, track=track, chrom=AUTOSOMES, key_added="scab")
            times.append(time.perf_counter() - t0)
        peak = max(peak, mem.peak - mem.base)
    rec = cd.results.record("scab")
    res["runtime"] = {"best_of_3_s": min(times), "runs_s": times, "peak_rss_increase_gb": peak / 1e9,
                      "stages_s": rec.inputs["seconds"], "load": load_average()}
    print(f"single_cell_compartments, 510 cells, 1 Mb: best of 3 {min(times):.2f} s ({times}), "
          f"+{peak / 1e9:.2f} GB; stages {rec.inputs['seconds']}")
    table = cd.results["scab"]
    m = cd.cellm["scab"]
    res["matrix"] = {"bins": int(m.shape[1]), "bins_finite_in_90pct_cells": int((np.isfinite(m).mean(0) >= .9).sum()),
                     "bins_per_cell_median": float(np.isfinite(m).sum(1).mean()),
                     "track_vs_mean_scab_r": float(np.corrcoef(table["track"].fillna(table["track"].mean()),
                                                               table["mean"].fillna(0.5))[0, 1])}

    rows = []

    def score(name, x, depth="all"):
        out = separation(pcs(x, 20), y)
        out.update({"features": name, "depth": depth})
        rows.append(out)
        print(f"  {name:<36s} depth {depth:>7}: kNN acc {out.get('knn_accuracy', float('nan')):.3f} "
              f"(balanced {out.get('knn_balanced_accuracy', float('nan')):.3f}), purity {out['knn_purity']:.3f}, "
              f"Ward ARI {out.get('ward_ARI', float('nan')):.3f}, k-means ARI {out['kmeans_ARI']:.3f}", flush=True)
        return out

    print("\nseparation of the paper's structure types (first 20 PCs):")
    score("scA/B Dip-C (all, rank)", fill_columns(m[mask], 0.9))
    _, x = scab_metrics(cd, track, mask, ScABParams(contacts="cis", normalize="none"), key="scab_cis")
    score("scA/B scHiCluster (cis, raw)", x)
    _, x = scab_metrics(cd, track, mask, ScABParams(contacts="all", normalize="zscore"), key="scab_z")
    score("scA/B (all, z-score)", x)
    _, x = scab_metrics(cd, track, mask, ScABParams(contacts="trans"), key="scab_trans")
    score("scA/B (trans only, rank)", x)

    t0 = time.perf_counter()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        embed_contacts(cd, methods=("pca",), n_pcs=20, chroms=AUTOSOMES, key_added="hic")
    t_hic = time.perf_counter() - t0
    out = separation(cd.cellm["hic_pca"][mask], y)
    out.update({"features": "scHiCluster embed_contacts (cis, 1 Mb)", "depth": "all", "seconds": t_hic})
    rows.append(out)
    print(f"  {'scHiCluster embed_contacts':<36s} depth     all: kNN acc {out['knn_accuracy']:.3f} "
          f"(balanced {out['knn_balanced_accuracy']:.3f}), purity {out['knn_purity']:.3f}, "
          f"Ward ARI {out['ward_ARI']:.3f}, k-means ARI {out['kmeans_ARI']:.3f} ({t_hic:.0f} s)")

    # --- 3: depth ---------------------------------------------------------------------------------------------
    for depth in a.depths:
        thin = a.out / f"thin_{depth}.scool"
        kept = thin_scool(str(scool), thin, depth, seed=1)
        sub = cells.loc[kept.index]
        cdt = make_cd(thin, sub)
        single_cell_compartments(cdt, track=track, chrom=AUTOSOMES, key_added="scab")
        mk = sub["cell_type"].isin(types).to_numpy()
        yy = sub["cell_type"].to_numpy()[mk]
        o = separation(pcs(fill_columns(cdt.cellm["scab"][mk], 0.9), 20), yy)
        o.update({"features": "scA/B Dip-C (all, rank)", "depth": depth})
        rows.append(o)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            embed_contacts(cdt, methods=("pca",), n_pcs=20, chroms=AUTOSOMES, key_added="hic")
        o2 = separation(cdt.cellm["hic_pca"][mk], yy)
        o2.update({"features": "scHiCluster embed_contacts (cis, 1 Mb)", "depth": depth})
        rows.append(o2)
        print(f"  depth {depth:>7,}: {mk.sum()} cells; scA/B kNN acc {o['knn_accuracy']:.3f} Ward ARI "
              f"{o['ward_ARI']:.3f} | scHiCluster kNN acc {o2['knn_accuracy']:.3f} Ward ARI {o2['ward_ARI']:.3f}",
              flush=True)

    tab = pd.DataFrame(rows)
    cols = ["features", "depth", "n_cells", "knn_accuracy", "knn_balanced_accuracy", "knn_purity", "ward_ARI",
            "ward_NMI", "kmeans_ARI", "kmeans_NMI"]
    print()
    print(tab[cols].to_string(index=False, float_format=lambda v: f"{v:.3f}"))
    res["separation"] = json.loads(tab.to_json(orient="records"))
    res["load_end"] = load_average()
    out = a.out / "scab_tan2021.json"
    out.write_text(json.dumps(res, indent=1, default=float))
    print(f"\n-> {out}")


if __name__ == "__main__":
    main()
