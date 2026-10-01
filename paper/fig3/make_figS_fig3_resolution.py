"""Supplementary figure — single-cell structures at 100 kb, 10 kb and 1 kb on one GPU.

Stevens 2017 Cell 1, U-Chrom native engine (GPU, one H100), 10 models, full 2017 schedule
extended to the target resolution; model 1 rendered with the U-Chrom web browser
(``build_render_hires.py``: the 10 kb / 1 kb models brought onto the 100 kb model by a
similarity transform; ``renders/hires/*_crop.png``).  Wall times from
``results/a_nucdyn_native_runs.json`` (100 kb) and ``results/a_nucdyn_gpu_<res>_cell1.json``.

  a  whole genome at each resolution
  b  chr1:30-35 Mb at each resolution (same camera per row)
  c  particles and wall time per resolution

    python paper/fig3/make_figS_fig3_resolution.py      # -> figS_fig3_resolution.pdf / .png
"""

from __future__ import annotations

import json

import matplotlib.pyplot as plt
import numpy as np

import make_fig3 as F
from make_fig3 import GREY, HERE, INK, MM, OURS, RES, ax_at, label, sub

W, H = 170.0, 102.0
F.W, F.H = W, H
RESOLUTIONS = (("100kb", "100 kb"), ("10kb", "10 kb"), ("1kb", "1 kb"))


def particles(tag: str) -> int:
    return int(np.load(HERE / "renders" / "hires" / f"cell1_{tag}_model1.npz")["coords"].shape[0])


def wall_minutes(tag: str) -> float:
    if tag == "100kb":
        runs = json.loads((RES / "a_nucdyn_native_runs.json").read_text())["gpu"]
        return [r for r in runs if r["cell"] == 1][0]["wall_seconds"] / 60
    return json.loads((RES / f"a_nucdyn_gpu_{tag}_cell1.json").read_text())["wall_seconds"] / 60


def main() -> None:
    fig = plt.figure(figsize=(W * MM, H * MM))
    label(fig, 0, 2, "a")
    sub(fig, 5, 2.8, "Whole genome", "Stevens 2017 Cell 1, model 1 of 10, coloured by chromosome")
    label(fig, 0, 56, "b")
    sub(fig, 5, 56.8, "chr1:30–35 Mb", "same model, zoomed")
    for k, (tag, name) in enumerate(RESOLUTIONS):
        ax = ax_at(fig, 6 + k * 40, 14, 36, 36)
        ax.imshow(plt.imread(HERE / "renders" / "hires" / f"genome_{tag}_crop.png")); ax.axis("off")
        ax.set_title(name, fontsize=7, color=INK, pad=1)
        bx = ax_at(fig, 8 + k * 40, 66, 32, 32)
        bx.imshow(plt.imread(HERE / "renders" / "hires" / f"chr1_30_35M_{tag}_crop.png")); bx.axis("off")
    label(fig, 126, 2, "c")
    sub(fig, 131, 2.8, "Cost on one GPU", "10 models, full schedule")
    n = [particles(t) for t, _ in RESOLUTIONS]
    t = [wall_minutes(t) for t, _ in RESOLUTIONS]
    ax = ax_at(fig, 138, 14, 28, 30)
    ax.plot(n, t, color=OURS, marker="o", ms=3)
    for k, (ni, ti, (_, name)) in enumerate(zip(n, t, RESOLUTIONS)):
        ax.annotate(f"{name}\n{ti:.1f} min" if ti < 10 else f"{name}\n{ti:.0f} min", (ni, ti),
                    textcoords="offset points", xytext=(4, -9) if k == 0 else (-3, 5), fontsize=5.3,
                    ha="left" if k == 0 else "right")
    ax.set_xscale("log"); ax.set_yscale("log")
    ax.set_xlabel("particles per model"); ax.set_ylabel("wall time (min)")
    ax.set_xlim(1.5e4, 5e6); ax.set_ylim(0.3, 60)
    ax.set_yticks([0.5, 1, 5, 10, 50], ["0.5", "1", "5", "10", "50"]); ax.minorticks_off()
    rows = [f"{nm}: {ni:,} particles, {ti:.1f} min" for (_, nm), ni, ti in zip(RESOLUTIONS, n, t)]
    fig.text(131 / W, 1 - 56 / H, "NVIDIA H100, one GPU\n" + "\n".join(rows), fontsize=5.5, color=GREY,
             va="top", linespacing=1.3)
    for ext in ("pdf", "png"):
        fig.savefig(HERE / f"figS_fig3_resolution.{ext}", dpi=300)
    print(HERE / "figS_fig3_resolution.pdf")


if __name__ == "__main__":
    main()
