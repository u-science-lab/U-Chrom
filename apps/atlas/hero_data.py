"""Data of the atlas page's hero animation (apps/atlas/site/hero.js): a tissue section on a slide and, lifted from it,
the nucleus of one cell with its 3-D genome.  A diagram, in line art:

* tissue: drawn after an adult mouse cerebellum section by spatial Hi-C (Chen, Guo et al. 2026; atlas store
  ``chen2026_cerebellum_adult_20um``, section Cere_HiC_R1): the tissue outline and the granular layer (spots of the
  GL_* domains) as smoothed contours, nuclei stippled at the density of each layer (dense granular layer, sparse
  molecular layer, a row of large Purkinje somata) -- the stipple is drawn, not measured;
* cells: real single-cell 3-D genome structures of adult mouse brain cells (HiRES, Liu et al. 2023; atlas store
  ``hires_brain``, the authors' diploid structures): the best-resolved (lowest ``rmsd_20k``) excitatory neuron,
  astrocyte and oligodendrocyte, coarse-grained to 2 Mb, every chromosome copy as one line; three neighbouring
  copies of three chromosomes are drawn in colour.  The cells are placed on the section for the diagram only.

    python apps/atlas/hero_data.py        # -> apps/atlas/site/hero.json
"""

from __future__ import annotations

from uchrom.datasets import data_dir
import json
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]                                   # the repository
CHEN = data_dir() / "spatial_hic_chen2026" / "cerebellum_adult_20um.chromdata.zarr"
HIRES = data_dir() / "hires2023" / "hires_brain.chromdata.zarr"
OUT = HERE / "site" / "hero.json"
SECTION = "Cere_HiC_R1"
UP = 8                    # contour upsampling of the spot grid
COARSE = 10               # 200 kb particles averaged into one drawn point (2 Mb)
CELLS = (("Ex1", "Excitatory neuron", "granular"), ("Ast", "Astrocyte", "purkinje"),
         ("Oli", "Oligodendrocyte", "granular"))
# stippled nuclei: minimum distance between two dots (spot units) in each layer
SPACING = {"GL": 0.7, "PL": 0.95, "ML": 1.7}
SEED = 7


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


def _smooth_grid(mask: np.ndarray, sigma: float):
    from scipy.ndimage import gaussian_filter, zoom

    big = zoom(mask.astype(float), UP, order=1)
    pad = UP * 2
    return gaussian_filter(np.pad(big, pad), sigma * UP), pad


def contours(mask: np.ndarray, sigma: float, tol: float):
    """Smoothed contours (in spot units, x / y) of a boolean grid."""
    import contourpy

    sm, pad = _smooth_grid(mask, sigma)
    out = []
    for line in contourpy.contour_generator(z=sm).lines(0.5):
        line = _simplify(np.asarray(line), tol * UP)
        if len(line) < 4:
            continue
        out.append((line - pad) / UP - 0.5 + 0.5 / UP)        # columns are x, y already
    return out


def _inside(sm, pad, pts):
    """Values of an upsampled smoothed grid at points in spot units."""
    ix = np.clip(np.round((pts[:, 0] + 0.5 - 0.5 / UP) * UP + pad).astype(int), 0, sm.shape[1] - 1)
    iy = np.clip(np.round((pts[:, 1] + 0.5 - 0.5 / UP) * UP + pad).astype(int), 0, sm.shape[0] - 1)
    return sm[iy, ix]


def stipple(layers: dict[str, np.ndarray], tissue: np.ndarray, rng) -> tuple[np.ndarray, np.ndarray]:
    """Blue-noise dots (spot units) with a minimum distance per layer; also the Purkinje somata."""
    h, w = tissue.shape
    sm_t, pad = _smooth_grid(tissue, 1.2)
    field = {k: _smooth_grid(m, 0.6)[0] for k, m in layers.items()}
    cand = rng.uniform([0, 0], [w, h], size=(int(w * h * 8), 2)) - 0.5
    keep = _inside(sm_t, pad, cand) > 0.5
    cand = cand[keep]
    # the layer of a candidate: the one with the largest smoothed value; its spacing
    vals = np.stack([_inside(field[k], pad, cand) for k in layers])
    which = np.argmax(vals, 0)
    spacing = np.array([SPACING[k] for k in layers])[which]
    spacing[vals.max(0) < 0.25] = SPACING["ML"]                 # tissue outside the three layers: sparse
    spacing *= rng.uniform(0.9, 1.25, len(spacing))
    cell = 0.3
    grid: dict[tuple[int, int], list[int]] = {}
    acc = []
    for i, (p, r) in enumerate(zip(cand, spacing)):
        gx, gy = int(p[0] // cell), int(p[1] // cell)
        k = int(np.ceil(r / cell))
        ok = True
        for dx in range(-k, k + 1):
            for dy in range(-k, k + 1):
                for j in grid.get((gx + dx, gy + dy), ()):
                    if (cand[j, 0] - p[0]) ** 2 + (cand[j, 1] - p[1]) ** 2 < r * r:
                        ok = False
                        break
                if not ok:
                    break
            if not ok:
                break
        if ok:
            grid.setdefault((gx, gy), []).append(i)
            acc.append(i)
    dots = cand[acc]
    # Purkinje somata: along the Purkinje layer, about 2.4 spots (50 um) apart
    pl = cand[(which == list(layers).index("PL")) & (_inside(field["PL"], pad, cand) > 0.55)]
    soma = []
    for p in pl[rng.permutation(len(pl))]:
        if all((p[0] - q[0]) ** 2 + (p[1] - q[1]) ** 2 > 2.4 ** 2 for q in soma):
            soma.append(p)
    return dots, np.array(soma)


def section(rng):
    from scipy.ndimage import uniform_filter

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
    grid = np.full((h, w), "", dtype=object)
    grid[y, x] = sec["cell_type"].astype(str).to_numpy()
    tissue = grid != ""
    layer = {k: np.vectorize(lambda s, k=k: s.startswith(k))(grid) for k in ("GL", "PL", "ML")}
    dots, soma = stipple(layer, tissue, rng)
    # where the cells are lifted from: well inside the tissue, in their layer, spread across the section
    inside = uniform_filter(tissue.astype(float), 9) > 0.95
    picks = []
    for _, _, where in CELLS:
        m = uniform_filter(layer["GL" if where == "granular" else "PL"].astype(float), 3) > 0.6
        yy, xx = np.nonzero(m & inside)
        best = None
        for _ in range(4000):
            i = rng.integers(len(xx))
            p = np.array([xx[i], yy[i]], dtype=float)
            # far from the section's rim and from the other picks, near the middle in y
            d = min([np.hypot(*(p - q)) for q in picks] + [w])
            score = min(d, 0.3 * w) - 0.6 * abs(p[1] - h * 0.5) - 0.6 * abs(p[0] - w * 0.5)
            if best is None or score > best[0]:
                best = (score, p)
        picks.append(best[1])
    s = float(max(w, h))
    norm = lambda pts: [[round(float(px) / s, 4), round(float(py) / s, 4)] for px, py in pts]   # noqa: E731
    return {
        "w": round(w / s, 4), "h": round(h / s, 4),
        "outline": [norm(c) for c in contours(tissue, 1.2, 0.35)],
        "granular": [norm(c) for c in contours(layer["GL"], 1.0, 0.3)],
        "dots": np.round(dots / s * 1e4).astype(int).ravel().tolist(),          # 1e-4 section units
        "somata": norm(soma), "soma_r": round(0.45 / s, 4), "picks": norm(picks),
    }


def cells():
    from uchrom import ChromData

    cd = ChromData.read(str(HIRES), backed=True)
    meta = cd.cells
    out = []
    for kind, label, _ in CELLS:
        cid = meta[meta["cell_type"].astype(str) == kind]["rmsd_20k"].idxmin()
        one = cd.get_cell(cid, columns="coords")
        s = one.spots_with_loci()
        xyz = np.asarray(one.coords, dtype=float)
        ok = np.isfinite(xyz).all(1)
        s, xyz = s[ok].reset_index(drop=True), xyz[ok]
        xyz -= xyz.mean(0)
        scale = np.percentile(np.linalg.norm(xyz, axis=1), 97)
        xyz /= scale
        copies = []
        for tid, g in s.groupby(s["trace_id"].astype(str), sort=False):
            g = g.sort_values("start")
            idx = g.index.to_numpy()
            n = len(idx) // COARSE * COARSE
            if n < COARSE * 6:
                continue
            p = xyz[idx[:n]].reshape(-1, COARSE, 3).mean(1)
            chrom = str(g["chrom"].iloc[0])
            copies.append({"chrom": chrom, "copy": tid.rsplit("_", 1)[-1], "p": p})
        # three copies of three different chromosomes in colour: large, compact ones whose territories touch, near
        # the middle
        cen = {i: c["p"].mean(0) for i, c in enumerate(copies)}
        size = {i: len(c["p"]) for i, c in enumerate(copies)}
        rg = {i: float(np.sqrt(((c["p"] - cen[i]) ** 2).sum(1).mean())) for i, c in enumerate(copies)}
        best = None
        big = [i for i in cen if size[i] >= 60 and copies[i]["chrom"] not in ("chrX", "chrY")]
        for a in big:
            for b in big:
                for c in big:
                    if not (a < b < c) or len({copies[a]["chrom"], copies[b]["chrom"], copies[c]["chrom"]}) < 3:
                        continue
                    pts = np.array([cen[a], cen[b], cen[c]])
                    spread = max(np.linalg.norm(pts[i] - pts[j]) for i in range(3) for j in range(i + 1, 3))
                    score = (-spread - 0.8 * np.linalg.norm(pts.mean(0)) + 0.008 * (size[a] + size[b] + size[c])
                             - 1.5 * (rg[a] + rg[b] + rg[c]))                   # compact territories
                    if best is None or score > best[0]:
                        best = (score, (a, b, c))
        hl = {i: k for k, i in enumerate(best[1])}
        out.append({
            "cell": str(cid), "type": label, "cell_type": kind,
            "copies": [{"chrom": c["chrom"], "copy": c["copy"], "hl": hl.get(i, -1),
                        "p": np.round(c["p"] * 1000).astype(int).ravel().tolist()} for i, c in enumerate(copies)],
        })
        print(f"{label}: {cid}, {len(copies)} copies, colour: " + ", ".join(
            f"{copies[i]['chrom']} {copies[i]['copy']}" for i in best[1]))
    return out


def main() -> None:
    rng = np.random.default_rng(SEED)
    data = {"tissue": section(rng), "cells": cells(),
            "source": {"tissue": "drawn after Chen, Guo et al. 2026 (spatial Hi-C, adult mouse cerebellum, " + SECTION + ")",
                       "cells": "HiRES, Liu et al. 2023 (single-cell Hi-C + RNA, adult mouse brain), the authors' 3-D structures"}}
    OUT.write_text(json.dumps(data, separators=(",", ":")))
    t = data["tissue"]
    print(f"wrote {OUT} ({OUT.stat().st_size / 1e3:.0f} kB): {len(t['dots']) // 2} dots, {len(t['somata'])} somata, "
          f"{len(data['cells'])} cells")


if __name__ == "__main__":
    main()
