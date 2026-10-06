"""Figure 2f — groups from one modality, structure from another (scHiCAR MOp).

Everything is real data (``example-data/schicar_mop/``): the scHiCAR mouse
brain store (``schicar_mop.h5cd``: 5,313 cells, RNA / ATAC / Hi-C
embeddings in ``cellm``) and its linked per-cell 1 Mb contact maps
(``contacts_cells_1Mb.scool``).

1. **Groups from RNA.**  Leiden clusters computed in ChromData on the RNA
   PCA (``uchrom.emb.cluster_cells(cd, use="rna_pca")``, stored in
   ``cd.cells``) — not the published labels.  Clusters are identified by
   their top RNA marker genes (``uchrom.emb.marker_features``; mean
   ``log1p`` difference vs the other cells); the published label
   composition of each cluster is recorded for transparency only.  Three
   contrasting clusters are chosen by marker genes: an oligodendrocyte
   cluster (highest mean ``log1p`` of Mobp / Plp1 / Mog / Opalin), a
   neuronal cluster (the largest cluster without glial / vascular markers)
   and an astrocyte cluster (Gja1 / Aqp4-like: highest Slc1a3 / Gja1 /
   Gpc5 / Atp1a2).
2. **Structure from Hi-C.**  Each cluster's pseudo-bulk contact map, summed
   from the linked per-cell ``.scool`` through the library path the web
   browser uses — ``Dataset.register_group(cells)`` then
   ``Dataset.contacts(key, chrom, group=...)`` → ``Dataset._pseudobulk`` —
   for every chromosome (1 Mb).  A window of one chromosome is stored for
   the maps (each group normalised to its total cis contacts).
3. **Readout.**  Contact probability vs genomic distance, P(s): per group,
   the sum over chromosomes of the counts at diagonal offset d divided by
   the number of bin pairs at that offset, normalised to sum 1 over
   d = 1 … d_max; the slope is the least-squares fit of log10 P vs log10 s
   over s = 2–30 Mb.
4. The timing (pseudo-bulk time vs cells aggregated, first query vs cached)
   is ``e_contacts.json``; the identity against the published per-type
   ``.cool`` files is ``e_query.json`` — both reused.

    python benchmarks/fig2/f_crossmodal.py [--resolution 1.0] [--window chr2:40-90Mb]

Writes ``u-chrom-paper/manuscripts/full/figures/fig2/results/f_crossmodal.json``.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _common as C  # noqa: E402

SCHICAR = C.DATA / "schicar_mop" / "schicar_mop.h5cd"
OLIGO = ("Mobp", "Plp1", "Mog", "Opalin")
ASTRO = ("Slc1a3", "Gja1", "Gpc5", "Atp1a2")
GLIA_VASC = OLIGO + ASTRO + ("Pdgfra", "Cspg4", "Csf1r", "P2ry12", "Cx3cr1", "Flt1", "Cldn5", "Rgs5", "Pdgfrb",
                             "Ptprc", "Vtn")
FIT = (2, 30)          # Mb, P(s) slope range
D_MAX = 60             # Mb, P(s) curve stored up to here


def _score(cells, genes):
    cols = [f"rna.{g}" for g in genes if f"rna.{g}" in cells.columns]
    return np.log1p(cells[cols].to_numpy(dtype=float)).mean(axis=1) if cols else np.zeros(len(cells))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--resolution", type=float, default=1.0)
    ap.add_argument("--n-neighbors", type=int, default=15)
    ap.add_argument("--window", default="chr2:40-90Mb")
    args = ap.parse_args()

    import pandas as pd

    from uchrom import ChromData
    from uchrom.browser.web.data import Dataset, decode_matrix
    from uchrom.emb import cluster_cells, marker_features

    cd = ChromData.read(SCHICAR)
    t0 = time.perf_counter()
    lab = cluster_cells(cd, use="rna_pca", n_neighbors=args.n_neighbors, resolution=args.resolution,
                        key_added="leiden_rna")
    t_cluster = time.perf_counter() - t0
    cells = cd.cells
    markers = marker_features(cd, "leiden_rna", prefix="rna.", n_top=6)
    clusters = []
    for k in lab.cat.categories:
        m = (lab == k).to_numpy()
        comp = cells.loc[m, "cell_type"].astype(str).value_counts()
        clusters.append({"cluster": str(k), "n_cells": int(m.sum()), "markers": markers[str(k)],
                         "oligo_score": float(_score(cells[m], OLIGO).mean()),
                         "astro_score": float(_score(cells[m], ASTRO).mean()),
                         "glia_vasc_score": float(_score(cells[m], GLIA_VASC).mean()),
                         "published_labels": {str(a): int(b) for a, b in comp.head(4).items()},
                         "published_top_fraction": float(comp.iloc[0] / m.sum())})
    df = pd.DataFrame(clusters)
    oligo = df.sort_values("oligo_score", ascending=False).iloc[0]["cluster"]
    astro = df[df.cluster != oligo].sort_values("astro_score", ascending=False).iloc[0]["cluster"]
    glia_cut = df["glia_vasc_score"].median()
    neur = df[(df.cluster != oligo) & (df.cluster != astro) & (df.glia_vasc_score <= glia_cut)] \
        .sort_values("n_cells", ascending=False).iloc[0]["cluster"]
    chosen = {"neuronal": neur, "oligodendrocyte": oligo, "astrocyte": astro}
    print({r: (c, markers[c], int((lab == c).sum())) for r, c in chosen.items()}, flush=True)

    ds = Dataset(id="schicar", name="schicar", path=str(SCHICAR), cd=cd)
    key = next(m["key"] for m in ds.contact_maps() if m["kind"] == "scool")
    import cooler
    scool = cd.resolve_link_path(cd.uns["linked_scool"]["per_cell"]["path"])
    first = cooler.Cooler(f"{scool}::{cooler.fileops.list_scool_cells(str(scool))[0]}")
    chroms = [c for c in first.chromnames if c not in ("chrY", "chrM")]
    wchrom, wrange = args.window.split(":")
    w0, w1 = (int(float(x.rstrip("Mb")) * 1e6) for x in wrange.split("-"))
    groups = {}
    for role, cl in chosen.items():
        ids = [str(c) for c in cells.index[(lab == cl).to_numpy()]]
        gid = ds.register_group(ids)["id"]
        diag = np.zeros(D_MAX + 1)
        npairs = np.zeros(D_MAX + 1)
        total_cis = 0.0
        window = None
        t_all = time.perf_counter()
        for ch in chroms:
            got = decode_matrix(ds.contacts(key, ch, group=gid))
            if got["header"].get("note"):
                raise RuntimeError(f"{role} {ch}: {got['header']['note']}")
            mat = np.asarray(got["matrix"], dtype=np.float64)
            n = len(mat)
            total_cis += float(np.triu(mat).sum())
            for d in range(0, min(D_MAX, n - 1) + 1):
                diag[d] += float(np.trace(mat, offset=d))
                npairs[d] += n - d
            if ch == wchrom:
                st = np.asarray(got["header"]["bin_starts"], dtype=np.int64)
                sel = (st >= w0) & (st < w1)
                window = {"chrom": ch, "start": int(st[sel][0]), "end": int(st[sel][-1] + 1_000_000),
                          "resolution": 1_000_000, "matrix": mat[np.ix_(sel, sel)].tolist()}
        t_all = time.perf_counter() - t_all
        s = np.arange(1, D_MAX + 1)
        p = diag[1:] / np.maximum(npairs[1:], 1)
        p = p / p.sum()
        fit = (s >= FIT[0]) & (s <= FIT[1]) & (p > 0)
        slope, icept = np.polyfit(np.log10(s[fit]), np.log10(p[fit]), 1)
        groups[role] = {"cluster": str(cl), "n_cells": len(ids), "markers": markers[str(cl)],
                        "published_labels": next(c["published_labels"] for c in clusters if c["cluster"] == cl),
                        "total_cis_contacts": total_cis, "ps_s_mb": s.tolist(), "ps": p.tolist(),
                        "ps_slope": float(slope), "ps_intercept": float(icept),
                        "window": window, "pseudobulk_all_chroms_s": t_all}
        print(role, cl, len(ids), f"slope {slope:.3f}", f"cis {total_cis:.3g}", f"{t_all:.1f} s", flush=True)
    # log2 ratio of the two first groups on the window (each normalised to its cis total)
    a, b = groups["neuronal"], groups["oligodendrocyte"]
    ma = np.asarray(a["window"]["matrix"]) / a["total_cis_contacts"]
    mb = np.asarray(b["window"]["matrix"]) / b["total_cis_contacts"]
    with np.errstate(divide="ignore", invalid="ignore"):
        ratio = np.log2(mb / ma)
    umap = np.asarray(cd.cellm["rna_umap"], dtype=float)
    C.write_json("f_crossmodal", {
        "panel": "f", "machine": C.machine_info(),
        "dataset": {"name": "scHiCAR mouse brain (GSE305439)", "store": "schicar_mop/schicar_mop.h5cd",
                    "scool": "schicar_mop/contacts_cells_1Mb.scool (5,313 cells, 1 Mb)",
                    "n_cells": int(len(cells))},
        "clustering": {"function": "uchrom.emb.cluster_cells", "use": "rna_pca", "method": "leiden",
                       "n_neighbors": args.n_neighbors, "resolution": args.resolution,
                       "n_clusters": int(len(lab.cat.categories)), "seconds": t_cluster,
                       "marker_method": "uchrom.emb.marker_features (mean log1p difference, rna.* columns)"},
        "clusters": clusters,
        "chosen": chosen,
        "selection_rule": {"oligodendrocyte": f"highest mean log1p of {', '.join(OLIGO)}",
                           "astrocyte": f"highest mean log1p of {', '.join(ASTRO)} (other clusters)",
                           "neuronal": "largest remaining cluster with a glial / vascular marker score at or "
                                       "below the median"},
        "pseudobulk_function": "uchrom.browser.web.data.Dataset.contacts(key, chrom, group=...) -> "
                               "Dataset._pseudobulk (per-cell pixels summed from the .scool)",
        "chroms": chroms,
        "ps_method": f"sum over chromosomes of diagonal d / pairs at d, normalised over d = 1..{D_MAX} Mb; "
                     f"slope = least squares of log10 P vs log10 s over {FIT[0]}-{FIT[1]} Mb",
        "groups": groups,
        "window_log2_ratio": {"numerator": "oligodendrocyte", "denominator": "neuronal",
                              "matrix": np.where(np.isfinite(ratio), ratio, np.nan).tolist()},
        "umap": {"key": "rna_umap", "x": umap[:, 0].round(4).tolist(), "y": umap[:, 1].round(4).tolist(),
                 "cluster": lab.astype(str).tolist()},
        "reused": {"timing": "e_contacts.json (aggregation)", "identity": "e_query.json (identity)"},
    })
    print(C.RESULTS / "f_crossmodal.json")


if __name__ == "__main__":
    main()
