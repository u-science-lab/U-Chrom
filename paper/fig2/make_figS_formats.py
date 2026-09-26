"""Supplementary figure — ChromData on-disk format versions.

File size and full-read time vs n_spots for the ChromData containers only:
h5cd 1.x, h5cd 2.0 (HDF5, deprecated for writing), chromdata.zarr 2.0 and
chromdata.zarr 2.0 with float32 coordinates.  Same data and protocol as
Fig. 2b (``results/b_storage.json``, written by ``benchmarks/fig2/b_storage.py``).

    python paper/fig2/make_figS_formats.py   # -> figS_formats.pdf / .png
"""

from __future__ import annotations

import matplotlib.pyplot as plt

import make_fig2 as F

SERIES = ["h5cd 1.x", "h5cd 2.0", "chromdata.zarr 2.0", "chromdata.zarr 2.0 (float32 coords)"]
W, H = 120.0, 58.0


def main() -> None:
    st = F.load_results()["storage"]
    fig = plt.figure(figsize=(W * F.MM, H * F.MM))
    axes = [fig.add_axes([(12 + j * 58) / W, 1 - 40 / H, 40 / W, 34 / H]) for j in range(2)]
    for ax, (key, ylab) in zip(axes, [("size_mb", "file size (MB)"), ("read_s", "full read into memory (s)")]):
        for f in SERIES:
            if f not in st:
                continue
            ax.plot(st[f]["n"], st[f][key], **{"ms": 2.5, **F.FORMATS[f]}, label=F.FORMAT_LABEL[f])
        F.loglog(ax)
        ax.set_xlabel("spots"); ax.set_ylabel(ylab)
        ax.set_xticks([1e4, 1e5, 1e6, 1e7])
    h, l = axes[0].get_legend_handles_labels()
    fig.legend(h, l, loc="upper left", bbox_to_anchor=(10 / W, 1 - 48 / H), ncol=4, frameon=False,
               handlelength=2.2, handletextpad=0.4, columnspacing=1.0)
    fig.text(1 / W, 1 - 1 / H, "ChromData format versions (Takei 2025, whole-cell subsets)", fontsize=8.5,
             fontweight="bold", va="top")
    for ext in ("pdf", "png"):
        fig.savefig(F.HERE / f"figS_formats.{ext}", dpi=300)
    print(F.HERE / "figS_formats.pdf")


if __name__ == "__main__":
    main()
