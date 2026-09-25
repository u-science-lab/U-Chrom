"""Export the U-Chrom and ChromData logos as standalone vector files (PDF + SVG + PNG)."""
import matplotlib.pyplot as plt

import make_fig1 as f

OUT = f.HERE / "logos"


def export(name, w, h, draw):
    f.W, f.H = w, h
    fig = plt.figure(figsize=(w * f.MM, h * f.MM))
    cv = f.Canvas(fig)
    draw(cv)
    OUT.mkdir(exist_ok=True)
    for ext in ("pdf", "svg"):
        fig.savefig(OUT / f"{name}.{ext}", transparent=True)
    fig.savefig(OUT / f"{name}.png", dpi=600, transparent=True)
    plt.close(fig)


export("uchrom_logo", 62, 14, lambda cv: f.uchrom_logo(cv, 2, 2, 10))
export("uchrom_mark", 12, 14, lambda cv: f.uchrom_mark(cv, 2, 1.5, 11))
export("chromdata_logo", 58, 14, lambda cv: (f.chromdata_mark(cv, 2, 1.5, 11),
                                             cv.text(15, 7.3, "ChromData", size=21, weight="bold", color=f.CORE)))
export("chromdata_mark", 14, 14, lambda cv: f.chromdata_mark(cv, 1.5, 1.5, 11))
print(sorted(p.name for p in OUT.iterdir()))
