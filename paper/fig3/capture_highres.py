"""Pane captures of the U-Chrom web browser for the high-resolution diploid panel of Fig. 3.

Starts ``python -m uchrom.browser --web`` on a store, opens the page in headless Chromium (Playwright,
Paper theme, default camera: screen x / y = the store's x / y, looking down -z) and saves PNGs of the
3-D view (``capture_view``, the view alone without the interface), driving the page's own controls:

* ``genome``    every copy chain coloured by chromosome (the overview "Chrom" colouring; both
                homologs of a chromosome share its colour);
* ``homologs``  the same camera, every chain light grey, the two copies of ``--highlight`` in two
                colours (subset layers made with the Subset layer / Trace tab, custom colours);
* ``zoom``      a second store (``--zoom-store``: one region, one cell per resolution) drawn as
                tubes, rainbow along the region.

Then crops the white margin (``*_crop.png``).

    python paper/fig3/capture_highres.py --store renders/highres/gm12878_cell035_5kb.chromdata.zarr \\
        --highlight chr7 --out renders/highres
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO / "benchmarks" / "fig6"))

from bench_frontend import LAUNCH, free_port, start_server  # noqa: E402

PAT, MAT, GREY = "#d1495b", "#2e6fbf", "#c9ccd1"


def crop(path: Path, pad: int = 12) -> Path:
    """Crop the white margin of a capture (square, centred) -> ``<stem>_crop.png``."""
    import matplotlib.pyplot as plt
    img = plt.imread(path)
    rgb = img[..., :3]
    ink = (rgb < 0.97).any(-1)
    ys, xs = np.nonzero(ink)
    y0, y1, x0, x1 = ys.min(), ys.max(), xs.min(), xs.max()
    side = max(y1 - y0, x1 - x0) + 2 * pad
    cy, cx = (y0 + y1) // 2, (x0 + x1) // 2
    out = np.ones((side, side, 3), dtype=rgb.dtype)
    sy0, sx0 = cy - side // 2, cx - side // 2
    for oy in range(side):
        y = sy0 + oy
        if 0 <= y < rgb.shape[0]:
            xa, xb = max(sx0, 0), min(sx0 + side, rgb.shape[1])
            out[oy, xa - sx0:xb - sx0] = rgb[y, xa:xb]
    dst = path.with_name(path.stem + "_crop.png")
    plt.imsave(dst, out)
    return dst


class Page:
    def __init__(self, page, base: str):
        import uchrom.browser as ub
        self.page, self.base = page, base
        self.ws = ub.connect(base)

    def open(self, store: Path) -> None:
        import requests
        requests.post(self.base + "/api/datasets", json={"path": str(store.resolve())}, timeout=1200).raise_for_status()
        self.page.goto(self.base + "/")
        self.page.wait_for_function("performance.getEntriesByName('uchrom:geometry-drawn').length > 0", timeout=600_000)
        self.page.wait_for_timeout(2000)

        # one 3-D view only (the page opens 3-D + matrix), fitted
        for v in self.ws.describe()["views"]:
            if v["type"] != "3d":
                self.ws.close_view(pane=v["pane"])
        self.page.wait_for_timeout(1000)
        self.reset()

    def reset(self) -> None:
        self.page.locator('button[title^="Reset view"]').first.click()
        self.page.wait_for_timeout(800)

    def _set(self, locator, value) -> None:
        """Set a React-controlled <input> (range / color) and fire its input event."""
        locator.evaluate("""(el, v) => {
            const set = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set
            set.call(el, v); el.dispatchEvent(new Event('input', {bubbles: true}))
            el.dispatchEvent(new Event('change', {bubbles: true}))}""", str(value))

    def select_layer(self, name: str) -> None:
        self.page.locator("ul.layer-list li", has=self.page.locator("span.name", has_text=name)).last.click()
        self.page.wait_for_timeout(300)

    def show_layer(self, name: str) -> None:
        row = self.page.locator("ul.layer-list li", has=self.page.locator("span.name", has_text=name)).first
        eye = row.locator("button.eye")
        if "on" not in (eye.get_attribute("class") or ""):
            eye.click()
            self.page.wait_for_timeout(1500)

    def style(self,mode=None, color_mode=None, color=None, opacity=None, line_width=None) -> None:
        """Style of the selected layer through the inspector's Style section."""
        pg = self.page
        if mode:
            pg.get_by_role("button", name=mode, exact=True).click()
        if color_mode:
            pg.get_by_role("button", name=color_mode, exact=True).last.click()
        if color:
            self._set(pg.locator('input[type="color"]').last, color)
        if opacity is not None:
            self._set(pg.locator("label:has-text('Opacity') + input[type=range]").first, opacity)
        if line_width is not None:
            self._set(pg.locator("label:has-text('Line width') + input[type=range]").first, line_width)
        pg.wait_for_timeout(800)

    def subset_traces(self, parent: str, trace_ids: str) -> None:
        """New child layer of `parent` with these traces (Subset layer > Trace tab)."""
        pg = self.page
        self.select_layer(parent)
        det = pg.locator("details.subset")
        if det.get_attribute("open") is None:
            det.locator("summary").click()
        det.get_by_role("button", name="Trace", exact=True).click()
        det.locator('input[placeholder^="id,"]').fill(trace_ids)
        det.get_by_role("button", name="Create subset").click()
        pg.wait_for_function("document.querySelectorAll('ul.layer-list li').length > 1")
        pg.wait_for_timeout(2500)

    def capture(self, path: Path) -> Path:
        self.page.wait_for_timeout(1500)
        self.ws.capture(path=str(path))
        return path


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--store", type=Path, help="whole-genome store (genome + homolog captures)")
    ap.add_argument("--zoom-store", type=Path)
    ap.add_argument("--highlight", default="chr7")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--prefix", default="")
    ap.add_argument("--size", type=int, default=1000, help="viewport side (CSS px; device scale 2)")
    ap.add_argument("--debug", action="store_true", help="also save full-page screenshots")
    args = ap.parse_args()
    from playwright.sync_api import sync_playwright

    args.out.mkdir(parents=True, exist_ok=True)
    pre = f"{args.out}/{args.prefix}"

    def session(store: Path, steps) -> None:
        port = free_port()
        proc = start_server(port)
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(**LAUNCH)
                # left panel ~410 px + inspector ~370 px: the 3-D pane is ~size x size
                page = browser.new_page(viewport={"width": args.size + 780, "height": args.size + 90},
                                        device_scale_factor=2)
                page.add_init_script("localStorage.setItem('uchrom.browser.theme', 'paper')")
                P = Page(page, f"http://127.0.0.1:{port}")
                P.open(store)
                root = store.name.split(".")[0]
                steps(P, root)
                if args.debug:
                    page.screenshot(path=str(pre) + "debug_page.png")
                browser.close()
        finally:
            proc.terminate()
            proc.wait(10)

    def genome(P: Page, root: str) -> None:
        P.select_layer(root)
        P.style(mode="line", color_mode="Rainbow", opacity=1.0, line_width=1)
        print(crop(P.capture(Path(str(pre) + "genome.png"))))
        # the same camera: every chain light grey, the two homologs of one chromosome in colour
        P.style(color_mode="Custom", color=GREY, opacity=0.08)
        for h, col in (("pat", PAT), ("mat", MAT)):
            P.subset_traces(root, f"{args.highlight}({h})")
            P.select_layer(f"{args.highlight}({h})")
            P.style(color_mode="Custom", color=col, opacity=1.0, line_width=1.5)
        P.show_layer(root)          # a new subset hides its parent; keep the grey context
        P.reset()                   # fit everything drawn = the camera of the genome capture
        print(crop(P.capture(Path(str(pre) + f"homologs_{args.highlight}.png"))))

    def zoom(P: Page, root: str) -> None:
        P.select_layer(root)
        P.style(mode="tube", color_mode="Rainbow", opacity=1.0)
        P.page.get_by_label("High quality").check()
        P.page.wait_for_timeout(1500)
        P.reset()
        print(crop(P.capture(Path(str(pre) + "zoom.png"))))

    if args.store:
        session(args.store, genome)
    if args.zoom_store:
        session(args.zoom_store, zoom)


if __name__ == "__main__":
    main()
