"""Supplementary figure — groups from one modality, structure from another (scHiCAR mouse MOp).

Moved out of Fig. 2 (it was panel f).  Drawn from ``results/f_crossmodal.json``
(``benchmarks/fig2/f_crossmodal.py``), ``e_query.json`` and ``e_contacts.json``.

a  RNA UMAP: Leiden clusters computed in ChromData on the RNA PCA
   (``uchrom.emb.cluster_cells``), three contrasting clusters coloured
b  their pseudo-bulk contact maps, summed from the linked per-cell ``.scool``
   through the shared index (``Dataset.contacts(group=…)``), and the
   correctness check against the published per-type ``.cool``
c  contact probability vs distance, P(s), per group, with slopes
d  time to sum the pseudo-bulk of chr1 vs cells aggregated (first query, cached)

    python paper/fig2/make_figS_crossmodal.py   # -> figS_crossmodal.pdf / .png
"""

from __future__ import annotations

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import LinearSegmentedColormap, LogNorm
from matplotlib.lines import Line2D

import make_fig2 as F

W, H = 170.0, 128.0
ROLE_COL = {"neuronal": F.INDIGO, "oligodendrocyte": F.ORANGE, "astrocyte": F.TEAL}
ROLES = ["neuronal", "oligodendrocyte", "astrocyte"]
NAMES = {"neuronal": "neurons", "oligodendrocyte": "oligodendrocytes", "astrocyte": "astrocytes"}


def main() -> None:
    F.W, F.H = W, H
    fx = F._load("f_crossmodal")
    q = F._load("e_query")["identity"]
    e = F._load("e_contacts")["aggregation"]["points"]
    groups = fx["groups"]
    fig = plt.figure(figsize=(W * F.MM, H * F.MM))
    fig.text(1 / W, 1 - 1 / H, "Groups from one modality, structure from another", fontsize=8.5,
             fontweight="bold", va="top")
    fig.text(1 / W, 1 - 5.2 / H, f"scHiCAR mouse primary motor cortex ({fx['dataset']['n_cells']:,} cells): RNA "
             "clusters → pseudo-bulk Hi-C from the linked per-cell .scool", fontsize=6, color=F.GREY, va="top")

    # a: UMAP of the RNA embedding
    y1 = 12.0
    F.label(fig, 1, y1, "a")
    F.title(fig, 6, y1 + 0.4, "RNA clusters",
            f"{fx['clustering']['n_clusters']} Leiden clusters on the RNA PCA")
    ax = F.ax_at(fig, 4, y1 + 11, 38, 38)
    um = fx["umap"]
    xs, ys, cl = np.asarray(um["x"]), np.asarray(um["y"]), np.asarray(um["cluster"])
    ax.scatter(xs, ys, s=0.6, color="#d9dce1", lw=0, rasterized=True)
    for r in ROLES:
        m = cl == groups[r]["cluster"]
        ax.scatter(xs[m], ys[m], s=0.8, color=ROLE_COL[r], lw=0, rasterized=True)
    ax.set_xticks([]); ax.set_yticks([])
    for sp in ax.spines.values():
        sp.set_visible(False)
    ax.set_xlabel("RNA UMAP 1", labelpad=1); ax.set_ylabel("RNA UMAP 2", labelpad=1)
    hs, labs = [], []
    for r in ROLES:
        g = groups[r]
        hs.append(Line2D([], [], ls="", marker="o", ms=3.0, color=ROLE_COL[r]))
        labs.append(f"cluster {g['cluster']}: {NAMES[r]} (n = {g['n_cells']:,})")
    hs.append(Line2D([], [], ls="", marker="o", ms=3.0, color="#d9dce1"))
    labs.append("other clusters")
    F.legend(fig, hs, labs, 4, y1 + 55, handlelength=0.7, handletextpad=0.4, labelspacing=0.3)

    # b: two pseudo-bulk maps of the same window (each normalised to its cis total)
    x2 = 52.0
    F.label(fig, x2, y1, "b")
    w = groups["neuronal"]["window"]
    F.title(fig, x2 + 5, y1 + 0.4, "Pseudo-bulk contact maps",
            f"{w['chrom']}:{w['start'] // 10**6}–{w['end'] // 10**6} Mb, 1 Mb bins, pseudo-bulk of each cluster")
    cmap = LinearSegmentedColormap.from_list("wt", ["#ffffff", "#b9d9f0", F.INDIGO, "#101d33"])
    pair = ["neuronal", "oligodendrocyte"]
    mats = [np.asarray(groups[r]["window"]["matrix"], float) / groups[r]["total_cis_contacts"] * 1e6 for r in pair]
    pos = np.concatenate([m[m > 0] for m in mats])
    norm = LogNorm(vmin=np.percentile(pos, 5), vmax=np.percentile(pos, 99.5))
    for k, (r, mat) in enumerate(zip(pair, mats)):
        mx = F.ax_at(fig, x2 + 4 + k * 38, y1 + 14, 33, 33)
        mx.imshow(mat, cmap=cmap, norm=norm, interpolation="nearest")
        mx.set_xticks([]); mx.set_yticks([])
        for sp in mx.spines.values():
            sp.set_linewidth(0.6)
            sp.set_color(ROLE_COL[r])
        mx.set_title(f"{NAMES[r]} (cluster {groups[r]['cluster']})", fontsize=6.5, color=ROLE_COL[r], pad=2)
    cax = F.ax_at(fig, x2 + 80, y1 + 15, 1.5, 28)
    cb = fig.colorbar(mpl.cm.ScalarMappable(norm=norm, cmap=cmap), cax=cax)
    cb.outline.set_linewidth(0.4)
    cb.ax.tick_params(labelsize=6, width=0.4, length=1.5, pad=1)
    fig.text((x2 + 90) / W, 1 - (y1 + 15) / H, "contacts\nper million\ncis contacts", fontsize=6, color=F.GREY,
             va="top", linespacing=1.1)
    fig.text((x2 + 4) / W, 1 - (y1 + 51) / H,
             f"Pseudo-bulk from the per-cell .scool equals the published per-type .cool for "
             f"{q['n_identical']}/{q['n_types']} cell types\n(max |Δ| = {q['max_abs_diff']:g} over "
             f"{q['n_pixels'] / 1e6:.1f} M pixels, all chromosomes)", fontsize=6, color=F.INK, va="top",
             linespacing=1.2)

    # c: P(s) per group
    y2 = 80.0
    F.label(fig, 1, y2, "c")
    F.title(fig, 6, y2 + 0.4, "Contact probability vs distance", "all chromosomes, per group")
    px = F.ax_at(fig, 13, y2 + 11, 40, 26)
    for r in ROLES:
        g = groups[r]
        s, p = np.asarray(g["ps_s_mb"], float), np.asarray(g["ps"], float)
        px.plot(s, p, color=ROLE_COL[r], lw=1.0)
    F.loglog(px)
    px.set_xlabel("distance s (Mb)"); px.set_ylabel("P(s)")
    px.set_xticks([1, 10]); px.set_xticklabels(["1", "10"])
    px.yaxis.set_minor_formatter(mpl.ticker.NullFormatter())
    fig.text(58 / W, 1 - (y2 + 12) / H, "slope, 2–30 Mb", fontsize=6, color=F.GREY, va="top")
    for i, r in enumerate(ROLES):
        fig.text(58 / W, 1 - (y2 + 15.5 + 3.2 * i) / H, f"{groups[r]['ps_slope']:.2f}  {NAMES[r]}",
                 fontsize=6, color=ROLE_COL[r], va="top")

    # d: pseudo-bulk time vs cells (e_contacts.json)
    x4 = 100.0
    F.label(fig, x4, y2, "d")
    F.title(fig, x4 + 5, y2 + 0.4, "Pseudo-bulk query time", "chr1, summed from the linked .scool")
    tx = F.ax_at(fig, x4 + 13, y2 + 11, 40, 26)
    c = np.array([p["n_cells"] for p in e])
    cold = np.array([p["cold_s"]["median"] for p in e])
    cached = np.array([p["cached_s"]["median"] for p in e])
    tx.plot(c, cold, color=F.TEAL, marker="o", ms=2.2, lw=1.0)
    tx.plot(c, cached, color=F.TEAL, ls="--", marker="o", ms=2.2, mfc="white", lw=1.0)
    F.loglog(tx)
    tx.set_xlabel("cells aggregated"); tx.set_ylabel("time (s)")
    F.decades(tx, c.min(), c.max())
    tx.set_yticks([1e-4, 1e-2, 1e0])
    tx.yaxis.set_minor_formatter(mpl.ticker.NullFormatter())
    tx.set_ylim(cached.min() / 3, cold.max() * 6)
    tx.text(c[-1], cold[-1] * 2.0, "first query", fontsize=6, color=F.TEAL, va="bottom", ha="right")
    tx.text(c[0], cached[0] * 3.5, "cached", fontsize=6, color=F.TEAL, va="bottom")
    for ext in ("pdf", "png"):
        fig.savefig(F.HERE / f"figS_crossmodal.{ext}", dpi=300)
    print(F.HERE / "figS_crossmodal.pdf")


if __name__ == "__main__":
    main()
