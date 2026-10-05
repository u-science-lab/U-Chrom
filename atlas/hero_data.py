"""Data of the atlas page's hero animation (atlas/site/hero.js): a tissue section, a field of view, nuclei.

Three scales, all real data, line art:

* section: an adult mouse cerebellum section by spatial Hi-C (Chen, Guo et al. 2026; atlas store
  ``chen2026_cerebellum_adult_20um``, section Cere_HiC_R1): the tissue outline and the granular layer (spots of
  the GL_* domains) as smoothed contours, the Purkinje layer (PL_*) as a dashed one;
* field: one field of view of another adult mouse cerebellum by DNA seqFISH+ (Takei et al. 2025; FOV 0 of
  replicate 1): every nucleus at its measured position and size (from the nuclear volume), with its cell type;
* nuclei: a Purkinje and a granule cell of that field, the traced loci in 3-D (um), drawn per chromosome copy
  in genomic order as fibre pieces (broken where neighbouring loci are > 1.3 um or > 2 Mb apart; 2 neighbours
  averaged into one point), and its H3K27ac immunofluorescence (points holding one of the cell's top 8 % loci).

The zoom from section to field is illustrative (two specimens); field and nuclei are the same cells.  The field
is turned so that its granular layer lies on the side the section's granular layer lies at the zoom point.

    python atlas/hero_data.py        # -> atlas/site/hero.json
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
CHEN = ROOT / "example-data" / "spatial_hic_chen2026" / "cerebellum_adult_20um.chromdata.zarr"
TAKEI = ROOT / "example-data" / "takei2025_cerebellum" / "takei2025_cerebellum_rep1.chromdata.zarr"
OUT = ROOT / "atlas" / "site" / "hero.json"
SECTION = "Cere_HiC_R1"
SPOT_UM = 20.0            # Chen 20 um spots
FOV = "0"
PX_UM = 0.103             # seqFISH+ xy pixel
UP = 8                    # contour upsampling of the spot grid
MERGE = 2                 # neighbouring traced loci averaged into one drawn point (line art)
MAX_STEP_UM = 1.3         # the fibre is broken where neighbouring traced loci are farther apart than this ...
MAX_GAP_BP = 2_000_000    # ... or farther apart in the genome


def _simplify(pts: np.ndarray, tol: float) -> np.ndarray:
    """Douglas-Peucker."""
    if len(pts) < 3:
        return pts
    a, b = pts[0], pts[-1]
    ab = b - a
    n = np.hypot(*ab)
    v = pts - a
    d = (np.abs(ab[0] * v[:, 1] - ab[1] * v[:, 0]) / n) if n > 0 else np.hypot(v[:, 0], v[:, 1])
    i = int(np.argmax(d))
    if d[i] <= tol:
        return np.array([a, b])
    return np.vstack([_simplify(pts[:i + 1], tol)[:-1], _simplify(pts[i:], tol)])


def contours(mask: np.ndarray, sigma: float, tol: float):
    """Smoothed contours (in spot units, x / y) of a boolean grid."""
    import contourpy
    from scipy.ndimage import gaussian_filter, zoom

    big = zoom(mask.astype(float), UP, order=1)
    pad = UP * 2
    sm = gaussian_filter(np.pad(big, pad), sigma * UP)
    out = []
    for line in contourpy.contour_generator(z=sm).lines(0.5):
        line = _simplify(np.asarray(line), tol * UP)
        if len(line) < 4:
            continue
        out.append((line - pad) / UP - 0.5 + 0.5 / UP)        # columns are x, y already
    return out


def section():
    from uchrom import ChromData

    cd = ChromData.read(str(CHEN), backed=True)
    c = cd.cells
    sec = c[c["section"].astype(str) == SECTION]
    pos = cd.cell_positions().loc[sec.index]
    x = np.round(pos["x"].to_numpy()).astype(int)
    y = np.round(pos["y"].to_numpy()).astype(int)
    x -= x.min()
    y -= y.min()
    w, h = x.max() + 1, y.max() + 1
    ty = sec["cell_type"].astype(str).to_numpy()
    grid = np.zeros((h, w), dtype=object)
    grid[:] = ""
    grid[y, x] = ty
    tissue = grid != ""
    gl = np.vectorize(lambda s: s.startswith("GL"))(grid)
    pl = np.vectorize(lambda s: s.startswith("PL"))(grid)
    out = {"outline": contours(tissue, 1.2, 0.35), "granular": contours(gl, 1.0, 0.3),
           "purkinje": contours(pl, 0.9, 0.3)}
    # zoom point: a Purkinje-layer spot with molecular and granular layer around it in equal parts
    from scipy.ndimage import uniform_filter
    k = 7
    fg = uniform_filter(gl.astype(float), k)
    fm = uniform_filter(np.vectorize(lambda s: s.startswith("ML"))(grid).astype(float), k)
    inside = uniform_filter(tissue.astype(float), 15) > 0.97            # well inside the tissue
    score = np.where(pl & tissue & inside, 1 - np.abs(fg - fm) - np.abs(fg + fm - 0.75), -9)
    cy, cx = np.unravel_index(int(np.argmax(score)), score.shape)
    # direction (section frame, y down) from the molecular to the granular layer near the zoom point
    yy, xx = np.mgrid[0:h, 0:w]
    near = (xx - cx) ** 2 + (yy - cy) ** 2 <= 8 ** 2
    mlm = near & np.vectorize(lambda s: s.startswith("ML"))(grid)
    glm = near & gl
    d = np.array([xx[glm].mean() - xx[mlm].mean(), yy[glm].mean() - yy[mlm].mean()])
    d /= np.linalg.norm(d)
    s = float(max(w, h))
    norm = lambda pts: [[round(float(px) / s, 4), round(float(py) / s, 4)] for px, py in pts]   # noqa: E731
    return {
        "size_um": round(s * SPOT_UM), "w": round(w / s, 4), "h": round(h / s, 4),
        "outline": [norm(c) for c in out["outline"]], "granular": [norm(c) for c in out["granular"]],
        "purkinje": [norm(c) for c in out["purkinje"] if len(c) > 6],
        "zoom": [round(cx / s, 4), round(cy / s, 4)], "granular_dir": [round(float(d[0]), 4), round(float(d[1]), 4)],
    }


def field_and_nuclei():
    from uchrom import ChromData

    cd = ChromData.read(str(TAKEI), backed=True)
    c = cd.cells.copy()
    c = c[c.index.str.split("_").str[1] == FOV]
    x, y = c["x_centroid"].to_numpy() * PX_UM, c["y_centroid"].to_numpy() * PX_UM
    r = (3 * c["nuc_volume_um3"].to_numpy() / (4 * np.pi)) ** (1 / 3)
    size = 2048 * PX_UM
    types = ["Granule", "Purkinje", "Bergmann", "MLI1", "MLI2+PLI", "Other"]
    t = c["cell_type"].astype(str).map({k: i for i, k in enumerate(types)}).fillna(5).astype(int).to_numpy()
    cells = [[round(float(a), 2), round(float(b), 2), round(float(rr), 2), int(tt)] for a, b, rr, tt in zip(x, y, r, t)]
    field = {"size_um": round(size, 1), "types": types, "cells": cells}

    # one Purkinje and one granule cell: many loci, close to the field's middle
    picks = []
    for kind in ("Purkinje", "Granule"):
        sub = c[c["cell_type"].astype(str) == kind]
        best = None
        for cid in sub.index:
            off = abs(sub.at[cid, "x_centroid"] * PX_UM - size / 2) + abs(sub.at[cid, "y_centroid"] * PX_UM - size * 0.55)
            n = cd.get_cell(cid, columns="coords").n_spots if best is None or off < best[2] + 60 else 0
            score = n - 8 * off
            if best is None or score > best[1]:
                best = (cid, score, off)
        picks.append((kind, best[0]))
    nuclei = []
    for kind, cid in picks:
        one = cd.get_cell(cid, tracks=["H3K27ac"])
        s = one.spots_with_loci()
        xyz = np.asarray(one.coords, dtype=float)
        ok = np.isfinite(xyz).all(1)
        s, xyz = s[ok].reset_index(drop=True), xyz[ok]
        xyz = xyz - xyz.mean(0)
        k27 = one.spot_tracks["H3K27ac"].to_numpy(dtype=float)[ok] if "H3K27ac" in one.spot_tracks else np.zeros(len(s))
        thr = np.nanpercentile(k27, 92)
        traces = []
        for tid, g in s.groupby(s["trace_id"].astype(str), sort=False):
            g = g.sort_values("start")
            idx = g.index.to_numpy()
            if len(idx) < 12:
                continue
            # break the fibre where neighbouring traced loci are far apart in space or in the genome, then
            # average MERGE neighbours within each piece
            step = np.linalg.norm(np.diff(xyz[idx], axis=0), axis=1)
            gap = np.diff(g["start"].to_numpy())
            cut = np.flatnonzero((step > MAX_STEP_UM) | (gap > MAX_GAP_BP)) + 1
            pts, marks, breaks = [], [], []
            for piece in np.split(np.arange(len(idx)), cut):
                n = len(piece) // MERGE * MERGE
                if n < MERGE * 3:
                    continue
                sel = idx[piece[:n]]
                m = xyz[sel].reshape(-1, MERGE, 3).mean(1)
                breaks.append(len(pts))
                marks.extend((len(pts) + np.flatnonzero((k27[sel] >= thr).reshape(-1, MERGE).any(1))).tolist())
                pts.extend(np.round(m * 100).astype(int).tolist())       # 0.01 um
            if len(pts) < 6:
                continue
            traces.append({"chrom": str(g["chrom"].iloc[0]), "p": np.asarray(pts).ravel().tolist(),
                           "b": breaks, "k27": marks})
        rr = float(c.at[cid, "nuc_volume_um3"])
        nuclei.append({"cell": cid, "type": kind, "x": round(float(c.at[cid, "x_centroid"] * PX_UM), 2),
                       "y": round(float(c.at[cid, "y_centroid"] * PX_UM), 2),
                       "r": round((3 * rr / (4 * np.pi)) ** (1 / 3), 2), "n_loci": int(len(s)), "n_points": int(sum(len(t["p"]) // 3 for t in traces)),
                       "traces": traces})
    return field, nuclei


def main() -> None:
    sec = section()
    field, nuclei = field_and_nuclei()
    data = {"section": sec, "field": field, "nuclei": nuclei,
            "source": {"section": "Chen, Guo et al. 2026 (spatial Hi-C, adult mouse cerebellum, " + SECTION + ")",
                       "field": "Takei et al. 2025 (DNA seqFISH+, adult mouse cerebellum, replicate 1, FOV " + FOV + ")"}}
    OUT.write_text(json.dumps(data, separators=(",", ":")))
    print(f"wrote {OUT} ({OUT.stat().st_size / 1e3:.0f} kB): section {sec['size_um']} um, "
          f"{len(field['cells'])} nuclei in the field, " + ", ".join(f"{n['type']} {n['cell']} {n['n_loci']} loci "
                                                                       f"{len(n['traces'])} traces" for n in nuclei))


if __name__ == "__main__":
    main()
