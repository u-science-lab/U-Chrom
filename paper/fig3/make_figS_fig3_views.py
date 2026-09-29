"""Supplementary figure — Stevens 2017 Cell 1 from four viewpoints: published vs U-Chrom.

Pane captures of the U-Chrom web browser (``renders/views/<model>_v<k>.png``; one model
each, 100 kb, superposed on the published model, coloured by chromosome, the same camera
for both rows, with an axes glyph per view showing its rotation relative to view 1; views 2-3 rotate ~90 deg about the vertical axis each, view 4 tilts view 3
~90 deg about the horizontal axis).  Crops from ``renders/views/*_crop.png``.

  rows: published (GEO GSE80280) / U-Chrom native engine (GPU); columns: views 1-4

    python paper/fig3/make_figS_fig3_views.py      # -> figS_fig3_views.pdf / .png
"""

from __future__ import annotations

import matplotlib.pyplot as plt
import numpy as np

import make_fig3 as F
from make_fig3 import GREY, HERE, INK, MM, ax_at, rot, triad

W, H = 170.0, 103.0
F.W, F.H = W, H


def main() -> None:
    fig = plt.figure(figsize=(W * MM, H * MM))
    # rotation of each view relative to view 1 (trackball drags in the browser, ~90 deg each)
    views = ((np.eye(3), "view 1 (reference)"), (rot("y", 90), "view 2: +90° about vertical"),
             (rot("y", 180), "view 3: +180° about vertical"),
             (rot("x", 90) @ rot("y", 180), "view 4: view 3, +90° about horizontal"))
    rows = (("published", "Published (GEO)"), ("uchrom", "U-Chrom"))
    fig.text(2 / W, 1 - 2 / H, "Stevens 2017 Cell 1, 100 kb; coloured by chromosome; the same camera in both rows; "
             "axes glyphs: the structure's x / y / z after each rotation (approximate)", fontsize=6, color=GREY,
             va="top")
    for r, (name, title) in enumerate(rows):
        y = 8 + r * 50
        fig.text(4 / W, 1 - (y + 5 + 19) / H, title, rotation=90, ha="center", va="center", fontsize=7.5,
                 fontweight="bold", color=INK)
        for v, (R, note) in enumerate(views):
            ax = ax_at(fig, 9 + v * 40, y + 5, 38, 38)
            ax.imshow(plt.imread(HERE / "renders" / "views" / f"{name}_v{v + 1}_crop.png"))
            ax.axis("off")
            if r == 0:
                ax.set_title(note, fontsize=6, color=GREY, pad=1)
    for v, (R, _) in enumerate(views):          # axes glyphs between the two rows, left-aligned with the images
        triad(fig, 9 + v * 40, 8 + 43 + 0.5, 12, R)
    for ext in ("pdf", "png"):
        fig.savefig(HERE / f"figS_fig3_views.{ext}", dpi=300)
    print(HERE / "figS_fig3_views.pdf")


if __name__ == "__main__":
    main()
