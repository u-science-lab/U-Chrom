"""Supplementary Fig. S2 — imaged distances recover Hi-C (geometry -> contacts).

Contact frequency from chromatin tracing (distance < 200 nm among traces with both
segments) vs Hi-C of the same cell type; DIMES (Shi & Thirumalai 2023) alongside.
Data as in ``make_fig3.py`` (``results/fig3_panels.npz``, ``results/b_dimes.json``).

  a  IMR90 chr21:28-30 Mb, Hi-C (upper) | imaging (lower)
  b  median distance vs Hi-C contacts per segment pair
  c  cell-type specificity: O/E correlation, imaging x Hi-C
  d  across datasets: U-Chrom direct contact frequency vs DIMES

    python paper/fig3/make_figS_fig3.py      # -> figS_fig3.pdf / .png
"""

from __future__ import annotations

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import LinearSegmentedColormap

import make_fig3 as F
from make_fig3 import HERE, INK, MM, ORANGE, OTHER, PURPLE, TEAL, ax_at, label, load_results, sub

W, H = 170.0, 66.0
F.W, F.H = W, H          # the shared mm helpers read the page size from make_fig3


def head_(fig, x, y, letter, name, note=None):
    label(fig, x, y, letter)
    sub(fig, x + 5, y + 0.8, name, note)


def main() -> None:
    d = load_results()
    fig = plt.figure(figsize=(W * MM, H * MM))
    y = 2
    # a: split map
    head_(fig, 0, y, "a", "IMR90 chr21:28–30 Mb", "Hi-C (upper) | imaging (lower)")
    hic, img, med = d["maps"]

    def z(a):
        lo, hi = np.nanpercentile(a, 2), np.nanpercentile(a, 99.5)
        return (a - lo) / (hi - lo)

    mm = np.triu(z(np.log10(hic + 1)), 1) + np.tril(z(np.log10(img + 1e-3)), -1) + np.eye(len(hic))
    ax = ax_at(fig, 3, y + 11, 34, 34)
    ax.imshow(np.clip(mm, 0, 1), cmap=LinearSegmentedColormap.from_list("t", ["#ffffff", TEAL, "#12433d"]),
              interpolation="nearest")
    ax.set_xticks([]); ax.set_yticks([])
    ax.text(0.97, 0.93, "Hi-C", transform=ax.transAxes, ha="right", fontsize=6, color=INK)
    ax.text(0.03, 0.04, "imaging", transform=ax.transAxes, fontsize=6, color=INK)
    # b: distance vs contacts
    head_(fig, 42, y, "b", "Distance vs contacts", "per segment pair")
    iu = np.triu_indices(len(hic), 1)
    ok = np.isfinite(med[iu]) & (hic[iu] > 0)
    x_, y_ = np.log10(hic[iu][ok]), med[iu][ok] / 1000
    ax = ax_at(fig, 54, y + 11, 26, 32)
    ax.scatter(x_, y_, s=1.2, color=ORANGE, lw=0, alpha=0.5)
    ax.set_xlabel("log10 Hi-C contacts"); ax.set_ylabel("median distance (µm)")
    r = np.corrcoef(x_, np.log10(y_))[0, 1]
    ax.text(0.96, 0.95, f"r = {r:.2f}", transform=ax.transAxes, fontsize=6, ha="right", va="top")
    # c: cell-type specificity
    head_(fig, 86, y, "c", "Cell-type specificity", "O/E correlation")
    ax = ax_at(fig, 98, y + 13, 24, 24)
    oe = d["oe"]
    ax.imshow(oe, cmap=LinearSegmentedColormap.from_list("p", ["#ffffff", PURPLE]), vmin=0, vmax=1)
    for (r_, c_), v in np.ndenumerate(oe):
        ax.text(c_, r_, f"{v:.2f}", ha="center", va="center", fontsize=6.5, color="white" if v > 0.6 else INK)
    ax.set_xticks([0, 1], ["IMR90", "K562"]); ax.set_yticks([0, 1], ["IMR90", "K562"])
    ax.set_xlabel("Hi-C"); ax.set_ylabel("imaging")
    for sp in ax.spines.values():
        sp.set_visible(False)
    # d: across datasets, U-Chrom vs DIMES
    head_(fig, 126, y, "d", "Across datasets", "log–log r vs Hi-C")
    ax = ax_at(fig, 148, y + 11, 20, 32)
    names = [n for n, *_ in d["datasets"]]
    yy = np.arange(len(names))[::-1]
    ax.barh(yy + 0.18, [v for _, v, _ in d["datasets"]], color=ORANGE, height=0.34, label="U-Chrom (direct)")
    ax.barh(yy - 0.18, [v for *_, v in d["datasets"]], color=OTHER, height=0.34, label="DIMES")
    ax.set_yticks(yy, names, fontsize=5.5); ax.set_xlim(0.5, 1.0); ax.set_xlabel("r")
    ax.legend(frameon=False, fontsize=5.5, loc="upper left", bbox_to_anchor=(-1.05, -0.3), ncol=2,
              handlelength=1, columnspacing=0.8)
    for ext in ("pdf", "png"):
        fig.savefig(HERE / f"figS_fig3.{ext}", dpi=300)
    print(HERE / "figS_fig3.pdf")


if __name__ == "__main__":
    main()
