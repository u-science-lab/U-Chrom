"""Supplementary figure — linked vs copied contacts (scHiCAR MOp, 5,313 cells, 1 Mb .scool).

a  on-disk size: the ChromData store alone, linked (the store records the
   path) vs copied (every cell's pixels written into the store as Parquet);
   and the user's total footprint, where the community .scool is kept either
   way (linked = .scool + store, copied = .scool + store with the copy)
b  import time: linking (record path + cell map, write the store) vs copying
   all pixels into the store (fresh process, median of 3; whiskers min/max)
c  query cost per cell type: whole-genome cis pseudo-bulk (all chromosomes)
   through the index, first query vs the same query again (LRU cache)

Data: ``results/e_query.json`` (``benchmarks/fig2/e_contacts_query.py``).

    python paper/fig2/make_figS_contacts.py      # -> figS_contacts.pdf / .png
"""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np

HERE = Path(__file__).resolve().parent
MM = 1 / 25.4
W, H = 170.0, 58.0
TEAL, GREY, LGREY, INK = "#2a9d8f", "#8a8f98", "#c9ccd1", "#2b2f36"

mpl.rcParams.update({
    "pdf.fonttype": 42, "font.family": "sans-serif", "font.sans-serif": ["Arial"],
    "font.size": 7, "axes.titlesize": 7, "axes.labelsize": 7,
    "xtick.labelsize": 6, "ytick.labelsize": 6, "legend.fontsize": 6,
    "axes.linewidth": 0.5, "xtick.major.width": 0.5, "ytick.major.width": 0.5,
    "xtick.major.size": 2, "ytick.major.size": 2, "xtick.minor.size": 1, "ytick.minor.size": 1,
    "axes.spines.top": False, "axes.spines.right": False, "lines.linewidth": 1.0,
})


def ax_at(fig, x, y, w, h):
    return fig.add_axes([x / W, 1 - (y + h) / H, w / W, h / H])


def label(fig, x, y, s, t):
    fig.text(x / W, 1 - y / H, s, fontsize=10, fontweight="bold", va="top")
    fig.text((x + 5) / W, 1 - (y + 0.4) / H, t, fontsize=8.5, fontweight="bold", va="top")


def main():
    q = json.loads((HERE / "results" / "e_query.json").read_text())
    imp = q["import"]
    gb = 1 / 2**30
    fig = plt.figure(figsize=(W * MM, H * MM))

    # a: sizes
    label(fig, 2, 2, "a", "On-disk size")
    ax = ax_at(fig, 14, 11, 44, 34)
    scool = imp["link"]["scool_bytes"] * gb
    store = {"linked": imp["link"]["store_bytes"] * gb, "copied": imp["copy"]["store_bytes"] * gb}
    x = np.array([0, 1, 2.6, 3.6])
    own = [store["linked"], store["copied"], store["linked"], store["copied"]]
    ext = [0, 0, scool, scool]
    cols = [TEAL, LGREY, TEAL, LGREY]
    ax.bar(x, own, width=0.7, color=cols, edgecolor=[TEAL, GREY, TEAL, GREY], lw=0.5)
    ax.bar(x, ext, bottom=own, width=0.7, color="white", edgecolor=TEAL, hatch="////", lw=0.5)
    for xi, o, e in zip(x, own, ext):
        ax.text(xi, o + e + 0.01, f"{(o + e) * 1024:.0f} MB", ha="center", va="bottom", fontsize=6, color=INK)
    ax.set_xticks(x, ["linked", "copied", "linked", "copied"])
    ax.set_ylabel("size (GB)")
    ymax = max(o + e for o, e in zip(own, ext))
    ax.set_ylim(0, ymax * 1.25)
    ax.text(0.5, -0.30, "store alone", transform=ax.get_xaxis_transform(), ha="center", fontsize=6, color=GREY)
    ax.text(3.1, -0.30, "user total (.scool kept)", transform=ax.get_xaxis_transform(), ha="center", fontsize=6,
            color=GREY)
    from matplotlib.patches import Patch
    ax.legend([Patch(fc="white", ec=TEAL, hatch="////", lw=0.5)], [".scool (5,313 cells)"], frameon=False,
              loc="upper left", handlelength=1.4)

    # b: import time
    label(fig, 62, 2, "b", "Import time")
    ax = ax_at(fig, 74, 11, 26, 34)
    t = [imp["link"]["seconds"], imp["copy"]["seconds"]]
    med = np.array([v["median"] for v in t])
    err = np.array([[v["median"] - v["min"] for v in t], [v["max"] - v["median"] for v in t]])
    ax.bar([0, 1], med, width=0.6, color=[TEAL, LGREY], edgecolor=[TEAL, GREY], lw=0.5, yerr=err,
           error_kw=dict(lw=0.6, capsize=1.5, capthick=0.6, ecolor=INK))
    for i, v in enumerate(med):
        ax.text(i, v * 1.25, f"{v:.2f} s" if v < 10 else f"{v:.0f} s", ha="center", va="bottom", fontsize=6)
    ax.set_yscale("log")
    ax.set_ylim(med.min() / 3, med.max() * 6)
    ax.set_xticks([0, 1], ["link", "copy"])
    ax.set_ylabel("time (s)")
    n_px = imp["copy"].get("n_pixels") or 0
    ax.text(0.5, -0.30, f"copy = {n_px / 1e6:.0f} M pixels", transform=ax.transAxes, ha="center", fontsize=6,
            color=GREY)

    # c: per-type query, first vs cached
    label(fig, 106, 2, "c", "Query per cell type")
    ax = ax_at(fig, 120, 11, 44, 34)
    per = q["identity"]["per_type"]
    n = np.array([p["n_cells"] for p in per])
    first = np.array([p["first_query_s_total"] for p in per])
    n_chr = len(q["identity"]["scope"].split("(")[1].split(")")[0].split(","))
    cached = np.array([p["cached_query_s_median"] for p in per]) * n_chr
    o = np.argsort(n)
    ax.plot(n[o], first[o], color=TEAL, marker="o", ms=2.2, label="first query")
    ax.plot(n[o], cached[o], color=TEAL, ls="--", marker="o", ms=2.2, mfc="white", label="cached")
    ax.set_xscale("log"); ax.set_yscale("log")
    ax.set_xlabel("cells of the type"); ax.set_ylabel(f"time, all {n_chr} chromosomes (s)")
    ax.legend(frameon=False, loc="center right", handlelength=1.6)
    for ext in ("pdf", "png"):
        fig.savefig(HERE / f"figS_contacts.{ext}", dpi=300)
    print(HERE / "figS_contacts.pdf")


if __name__ == "__main__":
    main()
