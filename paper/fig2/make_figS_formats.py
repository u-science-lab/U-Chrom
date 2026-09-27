"""Supplementary figure — ChromData format versions and the flat Parquet reference.

a, b  File size and full-read time vs n_spots (Takei 2025 whole-cell subsets,
      62 spot tracks; ``results/b_storage.json``): flat Parquet (pyarrow
      defaults; the storage engine under chromdata.zarr, i.e. the lower bound
      without hierarchy, index or metadata), chromdata.zarr 2.2 / 2.1 / 2.0,
      2.0 with float32 coordinates, h5cd 2.0 and 1.x.
c     Backed ``get_chrom`` vs n_spots for the three chromdata.zarr layouts
      (``results/c_access.json``): all columns (solid) and coordinates only
      (dashed; 2.1 and 2.2 only).
d     Backed ``get_cell`` for the same layouts.

    python paper/fig2/make_figS_formats.py   # -> figS_formats.pdf / .png
"""

from __future__ import annotations

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.lines import Line2D

import make_fig2 as F

W, H = 170.0, 70.0
LAYOUT_COL = {"2.0": "#b8c4d9", "2.1": F.LINDIGO, "2.2": F.INDIGO}


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
    for ext in ("pdf", "png"):
        fig.savefig(F.HERE / f"figS_formats.{ext}", dpi=300)
    print(F.HERE / "figS_formats.pdf")


if __name__ == "__main__":
    main()
