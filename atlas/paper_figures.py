"""Panels of the U-Chrom paper figures for the atlas' U-Chrom page (atlas/site/uchrom.html).

Renders figures/fig1/fig1_final.pdf and figures/fig2/fig2.pdf of the u-chrom-paper repository at 600 dpi (pdftoppm), crops the panels below and
writes them as WebP to atlas/site/paper/.  Rerun after a figure changes:

    python atlas/paper_figures.py
"""

from __future__ import annotations

import subprocess
import tempfile
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "atlas" / "site" / "paper"
sys.path.insert(0, str(ROOT / "benchmarks"))
from _paper import paper_root  # noqa: E402  (u-chrom-paper: $UCHROM_PAPER or next to the main checkout)

PAPER = paper_root() or ROOT / "paper"         # before the move: this repository's paper/ folder
SOURCES = {"fig1": PAPER / "figures" / "fig1" / "fig1_final.pdf", "fig2": PAPER / "figures" / "fig2" / "fig2.pdf"}
if not SOURCES["fig1"].exists():                # the layout before the move
    SOURCES = {"fig1": ROOT / "paper" / "fig1" / "fig1_final.pdf", "fig2": ROOT / "paper" / "fig2" / "fig2.pdf"}
#: panel -> (figure, x0, y0, x1, y1 in pixels of the 2007-px-wide 300-dpi page, width written); titles left out
PANELS = {
    "fig1c": ("fig1", 0, 1270, 2007, 2202, 2400),     # ecosystem: interfaces, methods, formats
    "fig2a": ("fig2", 0, 60, 2007, 1030, 2400),       # tables joined by keys + the .chromdata.zarr layout
    "fig2b": ("fig2", 0, 1140, 1150, 1672, 1600),     # what each format can represent
    "fig2c": ("fig2", 1180, 1140, 2007, 1672, 1100),  # storage and full reads
    "fig2de": ("fig2", 0, 1742, 2007, 2289, 2400),    # access speed, memory
}
PAGE_WIDTH = 2007


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        pages = {}
        for name, pdf in SOURCES.items():
            subprocess.run(["pdftoppm", "-r", "600", "-png", "-singlefile", str(pdf), f"{tmp}/{name}"], check=True)
            pages[name] = Image.open(f"{tmp}/{name}.png").convert("RGB")
        for panel, (fig, x0, y0, x1, y1, width) in PANELS.items():
            page = pages[fig]
            k = page.width / PAGE_WIDTH
            im = page.crop((int(x0 * k), int(y0 * k), int(x1 * k), int(y1 * k)))
            if im.width > width:
                im = im.resize((width, round(im.height * width / im.width)), Image.LANCZOS)
            im.save(OUT / f"{panel}.webp", quality=92, method=6)
            print(f"{panel}: {im.size[0]} x {im.size[1]}")


if __name__ == "__main__":
    main()
