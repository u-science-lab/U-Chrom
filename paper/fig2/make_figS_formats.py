"""Supplementary figure — format versions, access by layout and by format, round trips.

a, b  File size and full-read time vs n_spots (Takei 2025 whole-cell subsets,
      62 spot tracks; ``results/b_storage.json``): flat Parquet (pyarrow
      defaults; the storage engine under chromdata.zarr, i.e. the lower bound
      without hierarchy, index or metadata), chromdata.zarr 2.2 / 2.1 / 2.0,
      2.0 with float32 coordinates, h5cd 2.0 and 1.x.
c     Backed ``get_chrom`` vs n_spots for the three chromdata.zarr layouts
      (``results/c_access.json``): all columns (solid) and coordinates only
      (dashed; 2.1 and 2.2 only).
d     Backed ``get_cell`` for the same layouts.
e     Interoperability: what survives export → import (``results/f_roundtrip.json``;
      the round-trip evidence behind Fig. 2b).
f, g  One trace and one chromosome, across formats (``results/c_access.json``):
      open (backed chromdata.zarr) or load (FOF-CT, AnnData) or lazy-open
      (SpatialData) the file, then the query; complements Fig. 2d (one cell).

    python paper/fig2/make_figS_formats.py   # -> figS_formats.pdf / .png
"""

from __future__ import annotations

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.lines import Line2D

import make_fig2 as F

W, H = 170.0, 132.0
LAYOUT_COL = {"2.0": "#b8c4d9", "2.1": F.LINDIGO, "2.2": F.INDIGO}
STATUS_VAL = {"preserved": 1.0, "partial": 0.5, "lost": -1.0, "na": 0.0, "untested": 0.0}


def roundtrip(fig, x0, y0):
    """Round-trip dot matrix (f_roundtrip.json)."""
    F.label(fig, x0, y0, "e")
    F.title(fig, x0 + 5, y0 + 0.4, "Round trips")
    fig.text((x0 + 5) / W, 1 - (y0 + 4.6) / H, "what survives export → import", fontsize=6, color=F.GREY,
             va="top")
    f = F._load("f_roundtrip")
    rows, cols = list(f["rows"]), list(f["cols"])
    v = np.array([[STATUS_VAL[f["cells"][r][c]["status"]] for c in cols] for r in rows])
    direction = {"PDB": "export only", ".3dg": "import only"}
    rh = 4.4
    ax = F.ax_at(fig, x0 + 21, y0 + 22, 25, rh * len(rows))
    for i in range(v.shape[0]):
        for j in range(v.shape[1]):
            val = float(v[i, j])
            if val < 0:
                ax.plot(j + 0.5, i + 0.5, marker="x", ms=4, color=F.RED, mew=0.8)
                continue
            fill = {1.0: "full", 0.5: "left", 0.0: "none"}[val]
            col = F.INDIGO if val else F.LGREY
            ax.plot(j + 0.5, i + 0.5, marker="o", ms=5.0, fillstyle=fill, color=col, mec=col, mew=0.6,
                    markerfacecoloralt="white")
    ax.set_xlim(0, v.shape[1]); ax.set_ylim(v.shape[0], 0)
    ax.set_xticks(np.arange(v.shape[1]) + 0.5, cols, rotation=50, ha="left", rotation_mode="anchor")
    ax.xaxis.tick_top(); ax.tick_params(length=0, pad=1.5)
    ax.set_yticks(np.arange(v.shape[0]) + 0.5, rows)
    for s in ax.spines.values():
        s.set_visible(False)
    for i, r in enumerate(rows):
        if r in direction:
            ax.annotate(direction[r], (0, i + 0.5), xytext=(-2.5, -5.4), textcoords="offset points", ha="right",
                        va="center", fontsize=6, color=F.GREY, annotation_clip=False)
    hs = [Line2D([], [], marker="o", ls="", ms=4.6, fillstyle=fs, color=c, mec=c, mew=0.6,
                 markerfacecoloralt="white") for fs, c in (("full", F.INDIGO), ("left", F.INDIGO), ("none", F.LGREY))]
    labs = ["preserved", "partial, or not representable in that format", "not applicable"]
    if (v < 0).any():
        hs.append(Line2D([], [], marker="x", ls="", ms=4, color=F.RED, mew=0.8))
        labs.append("lost")
    F.legend(fig, hs, labs, x0 + 2.5, y0 + 22 + rh * len(rows) + 3.0, handlelength=1.0, labelspacing=0.35)


def by_format(fig, x0, y0, letter, key, title, sub):
    """One query across formats: open / load the file, then the query (c_access.json)."""
    F.label(fig, x0, y0, letter)
    F.title(fig, x0 + 5, y0 + 0.4, title)
    fig.text((x0 + 5) / W, 1 - (y0 + 4.6) / H, sub, fontsize=6, color=F.GREY, va="top")
    a = F.access()
    ax = F.ax_at(fig, x0 + 10, y0 + 12, 28, 38)
    items = []
    for series, lab, col, _ in F.BASELINES:
        if series in a["base"]:
            b = a["base"][series]
            F.points(ax, b["n"], b[key], col, lw=1.1)
            items.append((b["n"][-1], b[key][-1], lab, col))
    ours = a["open"] + a[key]
    F.points(ax, a["n"], ours, F.INDIGO, rep=a["rep"], lw=1.3)
    items.append((a["n"][-1], ours[-1], "chromdata.zarr" + (",\nall tracks" if key == "chrom" else ""), F.INDIGO))
    if key == "chrom":
        oc = a["open"] + a["chrom_coords"]
        F.points(ax, a["n"], oc, F.INDIGO, ls=(0, (2.5, 1.2)), rep=a["rep"], lw=1.0)
        items.append((a["n"][-1], oc[-1], "chromdata.zarr,\ncoords only", F.INDIGO))
    F.loglog(ax)
    ax.set_xlabel("spots"); ax.set_ylabel("time (s)")
    F.decades(ax, 1e4, 1e8)
    ax.set_xticks([1e4, 1e6, 1e8])
    top = 100 if key == "chrom" else 30
    ax.set_ylim(1e-2, top)
    F.decades(ax, 1e-2, top, axis="y")
    if key == "chrom":      # the chromdata.zarr line crosses the baselines' ends: list those top left
        base = [it for it in items if not it[2].startswith("chromdata")]
        for i, (_, _, lab, col) in enumerate(base):
            ax.text(0.04, 0.98 - 0.075 * i, lab, transform=ax.transAxes, fontsize=6, color=col, va="top")
        items = [it for it in items if it[2].startswith("chromdata")]
    F.direct_labels(ax, items, min_gap_mm=2.4)


def main() -> None:
    F.W, F.H = W, H          # the helpers of make_fig2 place in mm on this canvas
    st = F.storage(list(F.SUPP_FORMATS))
    c = F._load("c_access")["series"]
    fig = plt.figure(figsize=(W * F.MM, H * F.MM))
    axes = [F.ax_at(fig, 10 + j * 42, 13, 30, 30) for j in range(4)]
    for k, (ax, (key, ylab)) in enumerate(zip(axes[:2], [("size_mb", "file size (MB)"),
                                                        ("read_s", "full read into memory (s)")])):
        for f in reversed(list(F.SUPP_FORMATS)):
            if f not in st:
                continue
            sty = {kk: v for kk, v in F.SUPP_FORMATS[f].items() if kk != "label"}
            ax.plot(st[f]["n"], st[f][key], **{"ms": 2.3, **sty})
        F.loglog(ax)
        ax.set_xlabel("spots"); ax.set_ylabel(ylab)
        F.decades(ax, 1e4, 1e7)
    for ax, lvl, ylab in ((axes[2], "chrom", "get_chrom, backed (s)"), (axes[3], "cell", "get_cell, backed (s)")):
        for v in ("2.0", "2.1", "2.2"):
            name = f"chromdata.zarr {v} (backed, from disk)"
            if name not in c:
                continue
            pts = c[name]["points"]
            n = F._arr(pts, lambda p: float(p["n_spots"]))
            rep = F._arr(pts, lambda p: bool(p["replicated"]))
            F.points(ax, n, F._arr(pts, lambda p: p[lvl]["latency_s"]["median"]), LAYOUT_COL[v], rep=rep)
            if all(f"{lvl}_coords" in p for p in pts):
                F.points(ax, n, F._arr(pts, lambda p: p[f"{lvl}_coords"]["latency_s"]["median"]), LAYOUT_COL[v],
                         ls=(0, (2.5, 1.2)), rep=rep, lw=0.9)
        F.loglog(ax)
        ax.set_xlabel("spots"); ax.set_ylabel(ylab)
        F.decades(ax, 1e4, 1e8)
    for i, (x, t) in enumerate([(1, "a"), (43, "b"), (85, "c"), (127, "d")]):
        F.label(fig, x, 6.5, t)
    fig.text(1 / W, 1 - 1 / H, "Format versions and the flat Parquet reference", fontsize=8, fontweight="bold",
             va="top")
    fig.text(85 / W, 1 - 1 / H, "Backed access by layout", fontsize=8, fontweight="bold", va="top")
    hs = [Line2D([], [], **{"ms": 2.6, **{k: v for k, v in F.SUPP_FORMATS[f].items() if k != "label"}})
          for f in F.SUPP_FORMATS]
    F.legend(fig, hs, [F.SUPP_FORMATS[f]["label"] for f in F.SUPP_FORMATS], 3, 52, ncol=2, handlelength=2.2)
    h2 = [Line2D([], [], color=LAYOUT_COL[v], lw=1.2) for v in LAYOUT_COL]
    l2 = [f"chromdata.zarr {v}" for v in LAYOUT_COL]
    h2 += [Line2D([], [], color=F.INK, lw=1.2), Line2D([], [], color=F.INK, lw=0.9, ls=(0, (2.5, 1.2))),
           Line2D([], [], ls="", marker="o", ms=3.2, mfc="white", mec=F.INK, mew=0.8)]
    l2 += ["all columns", "coordinates only", "replicated cells (1e8)"]
    F.legend(fig, h2, l2, 88, 52, ncol=2, handlelength=2.0)
    # row 2: round trips, and one trace / one chromosome across formats
    y2 = 66.0
    roundtrip(fig, 1, y2)
    by_format(fig, 62, y2, "f", "trace", "One trace, across formats", "open or load the file, then get one trace")
    by_format(fig, 115, y2, "g", "chrom", "One chromosome, across formats",
              "open or load the file, then get one chromosome")
    for ext in ("pdf", "png"):
        fig.savefig(F.HERE / f"figS_formats.{ext}", dpi=300)
    print(F.HERE / "figS_formats.pdf")


if __name__ == "__main__":
    main()
