"""Supplementary Figure S1 — the Fig. 2 supplement, on one mm grid (170 mm wide).

Every panel is drawn from the JSONs in ``results/`` (written by ``benchmarks/fig2/*.py``):

  row 1  a  one trace, across formats                         (c_access.json)
         b  one chromosome, across formats                    (c_access.json)
         c  RNA UMAP: three Leiden clusters computed in ChromData (f_crossmodal.json)
  row 2  d  pseudo-bulk contact maps of two clusters, summed from the linked
            per-cell .scool, and the identity with per-type maps binned from the contact pairs
            (f_crossmodal.json, e_query.json)
         e  log2 ratio of the two maps (f_crossmodal.json window_log2_ratio)
  row 3  f  pseudo-bulk query time vs cells aggregated        (e_contacts.json)
         g  on-disk size, linked vs copied contacts           (e_query.json)
         h  import time, link vs copy                         (e_query.json)
         i  query time per cell type, first vs cached         (e_query.json)

The legend is ``figS_fig2_legend.md`` (written by hand; keep it in sync with the numbers).

    python paper/fig2/make_figS_fig2.py      # -> figS_fig2.pdf / .png
"""

from __future__ import annotations

import sys
from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.lines import Line2D
from matplotlib.colors import LinearSegmentedColormap, LogNorm
from matplotlib.patches import Patch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import make_fig2 as F  # noqa: E402

W, H = 170.0, 177.0
TICK = 6.5                       # tick-label size (pt)

ROLE_COL = {"neuronal": F.INDIGO, "oligodendrocyte": F.ORANGE, "astrocyte": F.TEAL}
ROLES = ["neuronal", "oligodendrocyte", "astrocyte"]
NAMES = {"neuronal": "neurons", "oligodendrocyte": "oligodendrocytes", "astrocyte": "astrocytes"}
OTHER = "#d9dce1"

# rows (mm from the top): panel letter at y, axes from y + AX_DY
AX_DY = 11.0
ROW1, ROW1_H = 1.0, 35.0
ROW2, ROW2_H = 58.0, 40.0
ROW3, ROW3_H = 122.0, 34.0


def style():
    mpl.rcParams.update({"xtick.labelsize": TICK, "ytick.labelsize": TICK, "axes.labelsize": 7,
                         "lines.linewidth": 1.0})


def _time(v):
    if v >= 1:
        return f"{v:g} s"
    if v >= 1e-3:
        return f"{v * 1e3:.3g} ms"
    return f"{v * 1e6:.3g} µs"


def _count(v):
    if v >= 1e6:
        return f"{v / 1e6:g}M"
    if v >= 1e4:
        return f"{v / 1e3:g}k"
    return f"{v:,.0f}"


def ticks(ax, axis, values, kind):
    """Decade ticks labelled directly (no exponents): kind = 'time' (ms / s), 'count' (10k, 1M), 'plain'."""
    f = {"time": _time, "count": _count, "plain": lambda v: f"{v:g}"}[kind]
    a = ax.xaxis if axis == "x" else ax.yaxis
    a.set_major_locator(mpl.ticker.FixedLocator(values))
    a.set_major_formatter(mpl.ticker.FuncFormatter(lambda v, _: f(v)))
    a.set_minor_formatter(mpl.ticker.NullFormatter())


def head(fig, x0, y0, letter, title, sub=None):
    F.label(fig, x0, y0, letter)
    F.title(fig, x0 + 5, y0 + 0.4, title)
    if sub:
        fig.text((x0 + 5) / W, 1 - (y0 + 4.6) / H, sub, fontsize=6, color=F.GREY, va="top", linespacing=1.05)


# --------------------------------------------------------------------------- row 1

def by_format(fig, x0, y0, letter, key, title, sub, acc):
    """One query across formats: open / load the file, then the query (c_access.json)."""
    head(fig, x0, y0, letter, title, sub)
    ax = F.ax_at(fig, x0 + 13, y0 + AX_DY, 24, ROW1_H)
    items = []
    for series, lab, col, _ in F.BASELINES:
        if series in acc["base"]:
            b = acc["base"][series]
            F.points(ax, b["n"], b[key], col, lw=1.1)
            items.append((b["n"][-1], b[key][-1], lab, col))
    ours = acc["open"] + acc[key]
    F.points(ax, acc["n"], ours, F.INDIGO, rep=acc["rep"], lw=1.3)
    items.append((acc["n"][-1], ours[-1], "chromdata.zarr" + (",\nall tracks" if key == "chrom" else ""), F.INDIGO))
    if key == "chrom":
        oc = acc["open"] + acc["chrom_coords"]
        F.points(ax, acc["n"], oc, F.INDIGO, ls=(0, (2.5, 1.2)), rep=acc["rep"], lw=1.0)
        items.append((acc["n"][-1], oc[-1], "chromdata.zarr,\ncoords only", F.INDIGO))
    F.loglog(ax)
    ax.set_xlabel("spots"); ax.set_ylabel("time")
    F.decades(ax, 1e4, 1e8)
    ticks(ax, "x", [1e4, 1e6, 1e8], "count")
    top = 100 if key == "chrom" else 30
    ax.set_ylim(1e-2, top)
    F.decades(ax, 1e-2, top, axis="y")
    ticks(ax, "y", [1e-2, 1e-1, 1e0, 1e1] + ([1e2] if key == "chrom" else []), "time")
    if key == "chrom":      # the chromdata.zarr lines cross the baselines' ends: list those top left
        base = [it for it in items if not it[2].startswith("chromdata")]
        for i, (_, _, lab, col) in enumerate(base):
            ax.text(0.04, 0.99 - 0.085 * i, lab, transform=ax.transAxes, fontsize=6, color=col, va="top")
        items = [it for it in items if it[2].startswith("chromdata")]
    F.direct_labels(ax, items, min_gap_mm=2.4)


def umap(fig, x0, y0, fx):
    groups = fx["groups"]
    head(fig, x0, y0, "c", "RNA clusters",
         f"{fx['clustering']['n_clusters']} Leiden clusters on the RNA PCA; others grey")
    ax = F.ax_at(fig, x0 + 4, y0 + AX_DY, 50, ROW1_H)
    um = fx["umap"]
    xs, ys, cl = np.asarray(um["x"]), np.asarray(um["y"]), np.asarray(um["cluster"])
    ax.scatter(xs, ys, s=0.5, color=OTHER, lw=0, rasterized=True)
    for r in ROLES:
        m = cl == groups[r]["cluster"]
        ax.scatter(xs[m], ys[m], s=0.7, color=ROLE_COL[r], lw=0, rasterized=True)
    ax.set_xticks([]); ax.set_yticks([])
    for sp in ax.spines.values():
        sp.set_visible(False)
    ax.set_xlabel("RNA UMAP 1", labelpad=1); ax.set_ylabel("RNA UMAP 2", labelpad=1)
    # direct labels, placed in empty space beside each cluster
    place = {"neuronal": (0.99, 0.60, "right", "bottom"), "oligodendrocyte": (0.07, 0.31, "left", "top"),
             "astrocyte": (0.07, 0.62, "left", "bottom")}
    for r in ROLES:
        g = groups[r]
        px, py, ha, va = place[r]
        ax.text(px, py, f"{NAMES[r]}\ncluster {g['cluster']}, n = {g['n_cells']:,}", transform=ax.transAxes,
                fontsize=6, color=ROLE_COL[r], ha=ha, va=va, linespacing=1.05)
    return ax


# --------------------------------------------------------------------------- row 2

def maps(fig, x0, y0, fx, q):
    groups = fx["groups"]
    w = groups["neuronal"]["window"]
    head(fig, x0, y0, "d", "Pseudo-bulk contact maps",
         f"{w['chrom']}:{w['start'] // 10**6}–{w['end'] // 10**6} Mb, 1 Mb bins, summed from the linked "
         "per-cell .scool")
    cmap = LinearSegmentedColormap.from_list("wt", ["#ffffff", "#b9d9f0", F.INDIGO, "#101d33"])
    pair = ["neuronal", "oligodendrocyte"]
    mats = [np.asarray(groups[r]["window"]["matrix"], float) / groups[r]["total_cis_contacts"] * 1e6 for r in pair]
    pos = np.concatenate([m[m > 0] for m in mats])
    norm = LogNorm(vmin=np.percentile(pos, 5), vmax=np.percentile(pos, 99.5))
    side = ROW2_H - 4.0
    top = y0 + AX_DY + 4.0
    for k, (r, mat) in enumerate(zip(pair, mats)):
        mx = F.ax_at(fig, x0 + 4 + k * (side + 5), top, side, side)
        mx.imshow(mat, cmap=cmap, norm=norm, interpolation="nearest")
        n = mat.shape[0]
        mx.set_xticks([-0.5, n - 0.5], [f"{w['start'] // 10**6}", f"{w['end'] // 10**6} Mb"])
        mx.set_yticks([])
        mx.tick_params(axis="x", length=1.5, pad=1)
        mx.get_xticklabels()[0].set_ha("left"); mx.get_xticklabels()[1].set_ha("right")
        for sp in mx.spines.values():
            sp.set_visible(True)
            sp.set_linewidth(0.6)
            sp.set_color(ROLE_COL[r])
        mx.set_title(f"{NAMES[r]} (cluster {groups[r]['cluster']})", fontsize=6.5, color=ROLE_COL[r], pad=2)
    cx = x0 + 4 + 2 * side + 5 + 2.5
    cax = F.ax_at(fig, cx, top + 2, 1.6, side - 4)
    cb = fig.colorbar(mpl.cm.ScalarMappable(norm=norm, cmap=cmap), cax=cax)
    cb.outline.set_linewidth(0.4)
    cb.ax.tick_params(labelsize=TICK, width=0.4, length=1.5, pad=1)
    lo, hi = np.ceil(np.log10(norm.vmin)), np.floor(np.log10(norm.vmax))
    ticks(cb.ax, "y", [10.0 ** k for k in range(int(lo), int(hi) + 1)], "plain")
    fig.text((cx - 1) / W, 1 - (top - 1.2) / H, "contacts per\nmillion cis", fontsize=6, color=F.GREY,
             va="bottom", ha="left", linespacing=1.05)
    fig.text((x0 + 4) / W, 1 - (top + side + 5.2) / H,
             f"Identical to per-type maps binned from the contact pairs, {q['n_identical']}/{q['n_types']} cell types; "
             f"max |Δ| = {q['max_abs_diff']:g} over {q['n_pixels'] / 1e6:.1f} M pixels",
             fontsize=6, color=F.INK, va="top")


def ratio(fig, x0, y0, fx):
    """log2(oligodendrocytes / neurons) of the two pseudo-bulk maps in d (same window)."""
    rr = fx["window_log2_ratio"]
    w = fx["groups"]["neuronal"]["window"]
    num, den = rr["numerator"], rr["denominator"]
    head(fig, x0, y0, "e", "Difference between the groups",
         f"log2({NAMES[num]} / {NAMES[den]}), same window")
    mat = np.asarray(rr["matrix"], float)
    lim = float(np.nanpercentile(np.abs(mat[np.isfinite(mat)]), 98))
    norm = mpl.colors.TwoSlopeNorm(vmin=-lim, vcenter=0.0, vmax=lim)
    cmap = LinearSegmentedColormap.from_list("div", [ROLE_COL[den], "#ffffff", ROLE_COL[num]])
    side = ROW2_H - 4.0
    top = y0 + AX_DY + 4.0
    mx = F.ax_at(fig, x0 + 4, top, side, side)
    mx.imshow(mat, cmap=cmap, norm=norm, interpolation="nearest")
    n = mat.shape[0]
    mx.set_xticks([-0.5, n - 0.5], [f"{w['start'] // 10**6}", f"{w['end'] // 10**6} Mb"])
    mx.set_yticks([])
    mx.tick_params(axis="x", length=1.5, pad=1)
    mx.get_xticklabels()[0].set_ha("left"); mx.get_xticklabels()[1].set_ha("right")
    for sp in mx.spines.values():
        sp.set_visible(True)
        sp.set_linewidth(0.6)
        sp.set_color(F.GREY)
    mx.set_title(f"{NAMES[num]} vs {NAMES[den]}", fontsize=6.5, color=F.INK, pad=2)
    cx = x0 + 4 + side + 2.5
    cax = F.ax_at(fig, cx, top + 2, 1.6, side - 4)
    cb = fig.colorbar(mpl.cm.ScalarMappable(norm=norm, cmap=cmap), cax=cax)
    cb.outline.set_linewidth(0.4)
    cb.ax.tick_params(labelsize=TICK, width=0.4, length=1.5, pad=1)
    t = np.floor(lim * 2) / 2
    cb.set_ticks([-t, 0, t], labels=[f"{-t:g}".replace("-", "−"), "0", f"+{t:g}"])
    fig.text((cx - 1) / W, 1 - (top + 1.0) / H, f"higher in\n{NAMES[num]}", fontsize=6, color=ROLE_COL[num],
             va="bottom", ha="left", linespacing=1.05)
    fig.text((cx - 1) / W, 1 - (top + side - 1.0) / H, f"higher in\n{NAMES[den]}", fontsize=6, color=ROLE_COL[den],
             va="top", ha="left", linespacing=1.05)


# --------------------------------------------------------------------------- row 3

def query_speed(fig, x0, y0, e, q):
    """Linked .scool query speed: per cell type (all chromosomes) | one chromosome vs cells aggregated."""
    per = q["identity"]["per_type"]
    n_chr = len(q["identity"]["scope"].split("(")[1].split(")")[0].split(","))
    head(fig, x0, y0, "g", "Linked contacts are fast to query",
         "pseudo-bulk summed from the linked per-cell .scool")
    n = np.array([p["n_cells"] for p in per]); o = np.argsort(n)
    first = np.array([p["first_query_s_total"] for p in per])
    cached = np.array([p["cached_query_s_median"] for p in per]) * n_chr
    c = np.array([p["n_cells"] for p in e])
    cold = np.array([p["cold_s"]["median"] for p in e])
    cc = np.array([p["cached_s"]["median"] for p in e])
    panels = [(n[o], first[o], cached[o], f"each cell type, all {n_chr} chromosomes", "cells of the type"),
              (c, cold, cc, "chr1, random groups of cells", "cells aggregated")]
    aw = 25.0
    for k, (xs, f_, c_, sub, xl) in enumerate(panels):
        ax = F.ax_at(fig, x0 + 13 + k * (aw + 8), y0 + AX_DY, aw, ROW3_H)
        ax.plot(xs, f_, color=F.TEAL, marker="o", ms=2.0, lw=1.1)
        ax.plot(xs, c_, color=F.TEAL, ls="--", marker="o", ms=2.0, mfc="white", lw=1.0)
        F.loglog(ax)
        ax.set_xlabel(xl)
        if k == 0:
            ax.set_ylabel("time")
        ax.set_xlim(xs.min() / 1.6, xs.max() * 1.6)
        ticks(ax, "x", [v for v in (1e2, 1e3) if xs.min() / 1.6 < v < xs.max() * 1.6], "count")
        ax.set_ylim(1e-5, 30)
        ticks(ax, "y", [1e-4, 1e-2, 1e0], "time")
        ax.set_title(sub, fontsize=6, color=F.INK, pad=2)
        if k == 1:                      # legend in the empty upper-left corner of the right sub-plot
            hs = [Line2D([], [], color=F.TEAL, marker="o", ms=2.4, lw=1.1),
                  Line2D([], [], color=F.TEAL, ls="--", marker="o", ms=2.4, mfc="white", lw=1.0)]
            ax.legend(hs, ["first query", "cached (LRU)"], loc="upper left",
                      frameon=False, fontsize=6, handlelength=2.0, handletextpad=0.4, labelspacing=0.3,
                      borderaxespad=0.2)


def sizes(fig, x0, y0, imp):
    mb_ = 1 / 2**20
    lk, cp = imp["link"]["store_bytes"] * mb_, imp["copy"]["store_bytes"] * mb_
    head(fig, x0, y0, "h", "Linking saves storage",
         f"ChromData store: {lk:.0f} MB linked vs {cp:.0f} MB copied;\nthe .scool itself is kept either way")
    ax = F.ax_at(fig, x0 + 10, y0 + AX_DY, 38, ROW3_H)
    mb = 1 / 2**20
    scool = imp["link"]["scool_bytes"] * mb
    store = {"linked": imp["link"]["store_bytes"] * mb, "copied": imp["copy"]["store_bytes"] * mb}
    x = np.array([0, 1, 2.5, 3.5])
    own = [store["linked"], store["copied"], store["linked"], store["copied"]]
    ext = [0, 0, scool, scool]
    ax.bar(x, own, width=0.7, color=[F.TEAL, F.LGREY] * 2, edgecolor=[F.TEAL, F.GREY] * 2, lw=0.5)
    ax.bar(x, ext, bottom=own, width=0.7, color="white", edgecolor=F.TEAL, hatch="////", lw=0.5)
    for xi, o, ex in zip(x, own, ext):
        ax.text(xi, o + ex + 6, f"{o + ex:.0f}", ha="center", va="bottom", fontsize=6, color=F.INK)
    ax.set_xticks(x, ["linked", "copied", "linked", "copied"])
    ax.tick_params(axis="x", length=0, pad=1.5)
    ax.set_ylabel("size (MB)")
    ax.set_xlim(-0.55, 4.05)
    ax.set_ylim(0, max(o + e for o, e in zip(own, ext)) * 1.18)
    ax.set_yticks([0, 100, 200, 300])
    for xc, t in ((0.5, "store alone"), (3.0, "total, .scool kept")):
        ax.text(xc, -0.12, t, transform=ax.get_xaxis_transform(), ha="center", va="top", fontsize=6, color=F.GREY)
    ax.legend([Patch(fc="white", ec=F.TEAL, hatch="////", lw=0.5)], [".scool"], frameon=False,
              loc="upper left", handlelength=1.3, handletextpad=0.4, borderaxespad=0.1, fontsize=6)


def import_time(fig, x0, y0, imp):
    head(fig, x0, y0, "f", "Linking is fast to set up",
         "link: record path + cell map\ncopy: write all pixels into the store")
    ax = F.ax_at(fig, x0 + 12, y0 + AX_DY, 15, ROW3_H)
    t = [imp["link"]["seconds"], imp["copy"]["seconds"]]
    med = np.array([v["median"] for v in t])
    err = np.array([[v["median"] - v["min"] for v in t], [v["max"] - v["median"] for v in t]])
    ax.bar([0, 1], med, width=0.65, color=[F.TEAL, F.LGREY], edgecolor=[F.TEAL, F.GREY], lw=0.5, yerr=err,
           error_kw=dict(lw=0.6, capsize=1.5, capthick=0.6, ecolor=F.INK))
    for i, v in enumerate(med):
        ax.text(i, v * 1.35, f"{v:.2f} s" if v < 1 else f"{v:.1f} s", ha="center", va="bottom", fontsize=6)
    ax.set_yscale("log")
    ax.set_ylim(0.1, 100)
    ticks(ax, "y", [0.1, 1, 10, 100], "time")
    ax.set_xlim(-0.6, 1.6)
    ax.set_xticks([0, 1], ["link", "copy"])
    ax.tick_params(axis="x", length=0, pad=1.5)
    ax.set_ylabel("time")
    n_px = imp["copy"].get("n_pixels") or 0
    ax.text(0.5, -0.12, f"copy: {n_px / 1e6:.0f} M pixels", transform=ax.transAxes, ha="center", va="top",
            fontsize=6, color=F.GREY)


# --------------------------------------------------------------------------- figure

def main() -> None:
    style()
    F.W, F.H = W, H                      # the helpers of make_fig2 place in mm on this canvas
    acc = F.access()
    fx = F._load("f_crossmodal")
    q = F._load("e_query")
    e = F._load("e_contacts")["aggregation"]["points"]
    fig = plt.figure(figsize=(W * F.MM, H * F.MM))

    by_format(fig, 0, ROW1, "a", "trace", "One trace, across formats", "open or load, then get one trace", acc)
    by_format(fig, 56, ROW1, "b", "chrom", "One chromosome, across formats",
              "open or load, then get one chromosome", acc)
    umap(fig, 114, ROW1, fx)

    maps(fig, 0, ROW2, fx, q["identity"])
    ratio(fig, 104, ROW2, fx)

    import_time(fig, 0, ROW3, q["import"])
    query_speed(fig, 43, ROW3, e, q)
    sizes(fig, 118, ROW3, q["import"])

    for ext in ("pdf", "png"):
        fig.savefig(HERE / f"figS_fig2.{ext}", dpi=300)
    print(HERE / "figS_fig2.pdf", f"{W:.0f} x {H:.0f} mm")


if __name__ == "__main__":
    main()
