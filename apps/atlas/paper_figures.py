"""Panels of the U-Chrom paper figures for the atlas' U-Chrom page (apps/atlas/site/uchrom.html) and the
documentation (docs/source/start/concepts.md, docs/source/index.md).

Renders manuscripts/full/figures/fig1/fig1_final.pdf and .../fig2/fig2.pdf of the u-chrom-paper repository at
600 dpi (pdftoppm), crops the panels below and writes them as WebP to apps/atlas/site/paper/ and as PNG / JPEG
(what Sphinx's HTML builder takes) to docs/source/_static/paper/.  Rerun after a figure changes:

    python apps/atlas/paper_figures.py [--only atlas|docs]
"""

from __future__ import annotations

import argparse
import subprocess
import tempfile
import sys
from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]                                   # the repository
OUT = HERE / "site" / "paper"
sys.path.insert(0, str(ROOT / "benchmarks"))
from _paper import paper_root  # noqa: E402  (u-chrom-paper: $UCHROM_PAPER or next to the main checkout)

PAPER = paper_root() or ROOT / "paper"         # before the move: this repository's paper/ folder
FIGS = PAPER / "manuscripts" / "full" / "figures"
SOURCES = {"fig1": FIGS / "fig1" / "fig1_final.pdf", "fig2": FIGS / "fig2" / "fig2.pdf"}
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
#: the documentation: panel -> (figure, x0, y0, x1, y1, width written, format)
DOCS = ROOT / "docs" / "source" / "_static" / "paper"
DOCS_PANELS = {
    "fig1a": ("fig1", 0, 85, 1075, 1180, 1200, "jpg"),      # three facets of 3-D genome data (illustration)
    "fig1b": ("fig1", 1085, 85, 2007, 1180, 1100, "png"),   # ChromData: one shared index
    "fig1c": ("fig1", 0, 1270, 2007, 2202, 1800, "png"),    # the ecosystem
    "fig2a": ("fig2", 0, 60, 2007, 1030, 1800, "png"),      # tables joined by keys + the store layout
}
PAGE_WIDTH = 2007


def _crop(page, x0, y0, x1, y1, width):
    k = page.width / PAGE_WIDTH
    im = page.crop((int(x0 * k), int(y0 * k), int(x1 * k), int(y1 * k)))
    if im.width > width:
        im = im.resize((width, round(im.height * width / im.width)), Image.LANCZOS)
    return im


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only", choices=["atlas", "docs"], help="write one set of panels")
    args = ap.parse_args()
    with tempfile.TemporaryDirectory() as tmp:
        pages = {}
        for name, pdf in SOURCES.items():
            subprocess.run(["pdftoppm", "-r", "600", "-png", "-singlefile", str(pdf), f"{tmp}/{name}"], check=True)
            pages[name] = Image.open(f"{tmp}/{name}.png").convert("RGB")
        if args.only in (None, "atlas"):
            OUT.mkdir(parents=True, exist_ok=True)
            for panel, (fig, x0, y0, x1, y1, width) in PANELS.items():
                im = _crop(pages[fig], x0, y0, x1, y1, width)
                im.save(OUT / f"{panel}.webp", quality=92, method=6)
                print(f"{panel}: {im.size[0]} x {im.size[1]}")
        if args.only in (None, "docs"):
            DOCS.mkdir(parents=True, exist_ok=True)
            for panel, (fig, x0, y0, x1, y1, width, fmt) in DOCS_PANELS.items():
                im = _crop(pages[fig], x0, y0, x1, y1, width)
                path = DOCS / f"{panel}.{fmt}"
                if fmt == "jpg":
                    im.save(path, quality=88, optimize=True, progressive=True)
                else:
                    im.quantize(256, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE).save(path, optimize=True)
                print(f"docs {panel}: {im.size[0]} x {im.size[1]}, {path.stat().st_size / 1e3:.0f} KB")


if __name__ == "__main__":
    main()
