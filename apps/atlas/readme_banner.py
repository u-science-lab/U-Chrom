"""The README banner: the atlas hero (apps/atlas/site/hero.js) as a still, wide line drawing in SVG.

A tissue section on a slide seen at an angle and, lifted from it, three cells with their 3-D genomes -- the same
data as the atlas page's hero (``site/hero.json``, written by ``hero_data.py``: an adult mouse cerebellum section by
spatial Hi-C, Chen, Guo et al. 2026, and single-cell 3-D genome structures of adult mouse brain cells, HiRES, Liu et
al. 2023; the cells are placed on the section for the diagram only).  Drawn as a card
on the atlas page's paper colour, so it reads the same on light and dark pages; standard library only.

    python apps/atlas/readme_banner.py        # -> docs/source/_static/banner.svg
"""

from __future__ import annotations

import json
import math
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
HERO = HERE / "site" / "hero.json"
OUT = ROOT / "docs" / "source" / "_static"

W, H = 1600, 600
# the slide (as hero.js: an oblique view, far edge up and to the right)
SHEAR, FLAT, PAD = 0.42, 0.46, 0.08
SLIDE_W = 880                     # width of the sheared slide on the banner
SLIDE_CX, SLIDE_CY = 1090, 445    # where the tissue's centre lands
NUC_R = 96                        # nucleus radius
NUC_Y = 158                       # nuclei centres
SPIN, TILT = 0.9, 0.3             # view of each genome (hero.js still: spin 0.9 with reduced motion)

# the atlas page's light colours (apps/atlas/site/style.css); the card has its own paper background
THEME = {"paper": "#fbfaf7", "rule": "#e5e1d8", "ink": "#1c1d21", "muted": "#73767d", "hl": ["#2a9d8f", "#34568b", "#e07a3f"]}
SERIF = "Newsreader, Georgia, 'Times New Roman', serif"
SANS = "Inter, -apple-system, 'Segoe UI', Helvetica, Arial, sans-serif"


def f(v: float) -> str:
    return f"{v:.1f}".rstrip("0").rstrip(".")


def layout(t: dict):
    sw, sh = t["w"] + 2 * PAD, t["h"] + 2 * PAD
    S = SLIDE_W / (sw + SHEAR * sh)

    def P(x: float, y: float) -> tuple[float, float]:
        u, v = x - t["w"] / 2, y - t["h"] / 2
        return SLIDE_CX + S * (u - SHEAR * v), SLIDE_CY + S * FLAT * v

    return S, P


def poly(pts, close=False) -> str:
    d = "M" + "L".join(f"{f(x)} {f(y)}" for x, y in pts)
    return d + ("Z" if close else "")


def tangents(c1, r1, c2, r2):
    """Outer tangents of the flattened ring (c1, r1) on the slide and the nucleus circle (c2, r2), as hero.js."""
    dx, dy = c2[0] - c1[0], c2[1] - c1[1]
    L = math.hypot(dx, dy)
    vx, vy = dx / L, dy / L
    c = (r1 - r2) / L
    s = math.sqrt(max(0.0, 1 - c * c))
    out = []
    for sg in (1, -1):
        nx, ny = vx * c - sg * vy * s, vy * c + sg * vx * s
        out.append(((c1[0] + r1 * nx, c1[1] + r1 * ny * FLAT), (c2[0] + r2 * nx, c2[1] + r2 * ny)))
    return out


def chromatin(cell: dict, cx: float, cy: float, r: float):
    """One cell's chromosome copies as smooth lines (quadratic through midpoints): far / near grey, 3 copies in colour."""
    k = 0.92 * r
    cs, sn, ct, st = math.cos(SPIN), math.sin(SPIN), math.cos(TILT), math.sin(TILT)
    far, near = [], []
    hf, hn = [[], [], []], [[], [], []]
    for cp in cell["copies"]:
        p = cp["p"]
        n = len(p) // 3
        if n < 3:
            continue
        X, Y, D = [], [], []
        for i in range(n):
            x0, y0, z0 = p[3 * i] / 1000, p[3 * i + 1] / 1000, p[3 * i + 2] / 1000
            x, z = cs * x0 + sn * z0, -sn * x0 + cs * z0
            y = ct * y0 - st * z
            D.append(st * y0 + ct * z)
            X.append(cx + x * k)
            Y.append(cy + y * k)
        mx0, my0 = X[0], Y[0]
        for j in range(1, n - 1):
            mx, my = (X[j] + X[j + 1]) / 2, (Y[j] + Y[j + 1]) / 2
            hl = cp["hl"]
            seg = f"M{f(mx0)} {f(my0)}Q{f(X[j])} {f(Y[j])} {f(mx)} {f(my)}"
            (hn[hl] if D[j] >= 0 else hf[hl]).append(seg) if hl >= 0 else (near if D[j] >= 0 else far).append(seg)
            mx0, my0 = mx, my
    return "".join(far), "".join(near), ["".join(s) for s in hf], ["".join(s) for s in hn]


def banner(d: dict) -> str:
    th = THEME
    ink, muted, hl = th["ink"], th["muted"], th["hl"]
    t = d["tissue"]
    S, P = layout(t)
    out: list[str] = []
    a = out.append
    a(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" role="img" '
      f'aria-label="U-Chrom: a tissue section and, lifted from it, three cells with their 3-D genomes">')
    a("<title>U-Chrom — the 3-D genome, cell by cell</title>")
    a(f'<rect x="1" y="1" width="{W - 2}" height="{H - 2}" rx="18" fill="{th["paper"]}" stroke="{th["rule"]}" stroke-width="2"/>')
    a('<g fill="none" stroke-linejoin="round" stroke-linecap="round">')

    # ---- the slide and the tissue -------------------------------------------------------------------------------
    slide = [P(*p) for p in [(-PAD, -PAD), (t["w"] + PAD, -PAD), (t["w"] + PAD, t["h"] + PAD), (-PAD, t["h"] + PAD)]]
    a(f'<path d="{poly(slide, True)}" stroke="{ink}" stroke-opacity="0.8" stroke-width="1.4"/>')
    a(f'<path d="{"".join(poly([P(*q) for q in l]) for l in t["outline"])}" stroke="{ink}" stroke-opacity="0.75" stroke-width="1.1"/>')
    a(f'<path d="{"".join(poly([P(*q) for q in l]) for l in t["granular"])}" stroke="{ink}" stroke-opacity="0.4" stroke-width="0.8"/>')
    r = 1.6
    dots = t["dots"]
    stip = "".join(f"M{f(x - r / 2)} {f(y - r / 2)}h{f(r)}v{f(r)}h{f(-r)}z"
                   for x, y in (P(dots[i] / 1e4, dots[i + 1] / 1e4) for i in range(0, len(dots), 2)))
    a(f'<path d="{stip}" fill="{ink}" fill-opacity="0.55" stroke="none"/>')
    sr = t["soma_r"] * S
    som = "".join(f"M{f(x - sr)} {f(y)}a{f(sr)} {f(sr * FLAT)} 0 1 0 {f(2 * sr)} 0a{f(sr)} {f(sr * FLAT)} 0 1 0 {f(-2 * sr)} 0"
                  for x, y in (P(*p) for p in t["somata"]))
    a(f'<path d="{som}" stroke="{ink}" stroke-opacity="0.55" stroke-width="0.8"/>')
    a("</g>")

    # ---- three cells lifted from the section ------------------------------------------------------------------------
    picks = [P(*p) for p in t["picks"]]
    order = sorted(range(len(picks)), key=lambda i: picks[i][0])          # nuclei left -> right, cones do not cross
    xs = [SLIDE_CX - 330, SLIDE_CX, SLIDE_CX + 330]
    rc = 14
    for slot, i in enumerate(order):
        cell, pk = d["cells"][i], picks[i]
        nx, ny = xs[slot], NUC_Y
        tg = tangents(pk, rc, (nx, ny), NUC_R)
        if tg[0][1][0] > tg[1][1][0]:
            tg.reverse()
        L, R = tg
        a1, a2 = math.atan2(L[1][1] - ny, L[1][0] - nx), math.atan2(R[1][1] - ny, R[1][0] - nx)
        large = 1 if ((a1 - a2) % (2 * math.pi)) > math.pi else 0
        a(f'<path d="M{f(L[0][0])} {f(L[0][1])}L{f(L[1][0])} {f(L[1][1])}A{NUC_R} {NUC_R} 0 {large} 0 {f(R[1][0])} {f(R[1][1])}'
          f'L{f(R[0][0])} {f(R[0][1])}Z" fill="{ink}" fill-opacity="0.035"/>')
        a(f'<g fill="none" stroke="{ink}" stroke-linecap="round">')
        for l in tg:
            a(f'<path d="M{f(l[0][0])} {f(l[0][1])}L{f(l[1][0])} {f(l[1][1])}" stroke-opacity="0.9" stroke-width="1.4"/>')
        a(f'<ellipse cx="{f(pk[0])}" cy="{f(pk[1])}" rx="{rc}" ry="{f(rc * FLAT)}" stroke-opacity="0.95" stroke-width="1.6"/>')
        a("</g>")
        far, near, hf, hn = chromatin(cell, nx, ny, NUC_R - 2)
        cid = f"nuc{slot}"
        a(f'<clipPath id="{cid}"><circle cx="{f(nx)}" cy="{f(ny)}" r="{NUC_R - 2}"/></clipPath>')
        a(f'<g clip-path="url(#{cid})" fill="none" stroke-linecap="round" stroke-linejoin="round">')
        a(f'<path d="{far}" stroke="{ink}" stroke-opacity="0.07" stroke-width="0.7"/>')
        a(f'<path d="{near}" stroke="{ink}" stroke-opacity="0.17" stroke-width="0.7"/>')
        for h in range(3):
            a(f'<path d="{hf[h]}" stroke="{hl[h]}" stroke-opacity="0.5" stroke-width="1.6"/>')
            a(f'<path d="{hn[h]}" stroke="{hl[h]}" stroke-opacity="0.95" stroke-width="2.2"/>')
        a("</g>")
        a(f'<circle cx="{f(nx)}" cy="{f(ny)}" r="{NUC_R}" fill="none" stroke="{ink}" stroke-opacity="0.95" stroke-width="1.8"/>')
        a(f'<text x="{f(nx)}" y="{f(ny - NUC_R - 14)}" text-anchor="middle" font-family="{SERIF}" '
          f'font-style="italic" font-size="27" fill="{ink}" fill-opacity="0.9">{cell["type"]}</text>')
    a(f'<text x="{f(slide[3][0] - 14)}" y="{f(slide[3][1] - 4)}" text-anchor="end" font-family="{SANS}" font-size="20" fill="{muted}">tissue section</text>')

    # ---- the wordmark -------------------------------------------------------------------------------------------------
    a(f'<text x="60" y="262" font-family="{SERIF}" font-size="118" font-weight="500" letter-spacing="-2" fill="{ink}">U-Chrom</text>')
    a(f'<text x="66" y="328" font-family="{SERIF}" font-style="italic" font-size="40" fill="{ink}" fill-opacity="0.9">'
      f'the 3-D genome, cell by cell</text>')
    a(f'<text x="68" y="384" font-family="{SANS}" font-size="25" fill="{muted}">sequencing · imaging · one data model</text>')
    a("</svg>")
    return "\n".join(out)


def main() -> None:
    d = json.loads(HERO.read_text())
    p = OUT / "banner.svg"
    p.write_text(banner(d))
    print(f"{p.relative_to(ROOT)}: {p.stat().st_size / 1024:.0f} KB")


if __name__ == "__main__":
    main()
