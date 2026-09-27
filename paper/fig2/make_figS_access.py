"""Supplementary panels — one trace and one chromosome, across formats.

Complements Fig. 2d (one cell): open (backed chromdata.zarr), load (FOF-CT, AnnData) or
lazy-open (SpatialData) the file, then get one trace / one chromosome; chromdata.zarr
``get_chrom`` with all per-spot tracks (solid) and coordinates only (dashed).  Data:
``results/c_access.json``.  The panel function is ``make_figS_formats.by_format``.

    python paper/fig2/make_figS_access.py      # -> figS_access.pdf / .png
"""

from __future__ import annotations

import matplotlib.pyplot as plt

import make_fig2 as F
import make_figS_formats as SF

W, H = 170.0, 60.0


def main(fig=None):
    F.W, F.H = W, H                  # helpers of make_fig2 place in mm on this canvas
    SF.W, SF.H = W, H                # by_format reads these for its titles
    standalone = fig is None
    fig = fig if fig is not None else plt.figure(figsize=(W * F.MM, H * F.MM))
    SF.by_format(fig, 1, 2, "a", "trace", "One trace, across formats", "open or load the file, then get one trace")
    SF.by_format(fig, 86, 2, "b", "chrom", "One chromosome, across formats",
                 "open or load the file, then get one chromosome")
    if standalone:
        for ext in ("pdf", "png"):
            fig.savefig(F.HERE / f"figS_access.{ext}", dpi=300)
        print(F.HERE / "figS_access.pdf")
    return fig


if __name__ == "__main__":
    main()
