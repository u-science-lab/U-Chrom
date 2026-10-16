/** Pure helpers for the 2-D embedding scatter (no DOM). */

export interface Plot {
  /** data → pixel */
  sx: (x: number) => number
  sy: (y: number) => number
  bounds: { x0: number; x1: number; y0: number; y1: number }
}

/**
 * Fit positions into a `w × h` box keeping their aspect (one scale for both
 * axes, centred) — for cell positions in a tissue, and for embeddings (UMAP,
 * t-SNE and PCA coordinates are on one scale: stretching an axis to fill a
 * tall or wide view would distort the clusters).  `extent` [x0, x1, y0, y1]
 * (an image) is fitted when given, else the points' bounds; `yDown`: y grows
 * downwards (image pixels).
 */
export function fitPlotEqual(
  xs: (number | null)[],
  ys: (number | null)[],
  w: number,
  h: number,
  pad: number,
  opts: { yDown?: boolean; extent?: [number, number, number, number] | null } = {},
): Plot {
  let [x0, x1, y0, y1] = opts.extent ?? [Infinity, -Infinity, Infinity, -Infinity]
  if (!opts.extent) {
    for (let i = 0; i < xs.length; i++) {
      const x = xs[i]
      const y = ys[i]
      if (x === null || y === null || !Number.isFinite(x) || !Number.isFinite(y)) continue
      x0 = Math.min(x0, x)
      x1 = Math.max(x1, x)
      y0 = Math.min(y0, y)
      y1 = Math.max(y1, y)
    }
  }
  if (!Number.isFinite(x0)) [x0, x1, y0, y1] = [0, 1, 0, 1]
  if (x1 === x0) [x0, x1] = [x0 - 0.5, x1 + 0.5]
  if (y1 === y0) [y0, y1] = [y0 - 0.5, y1 + 0.5]
  const iw = Math.max(1, w - 2 * pad)
  const ih = Math.max(1, h - 2 * pad)
  const k = Math.min(iw / (x1 - x0), ih / (y1 - y0))
  const ox = pad + (iw - k * (x1 - x0)) / 2
  const oy = pad + (ih - k * (y1 - y0)) / 2
  return {
    sx: (x) => ox + (x - x0) * k,
    sy: opts.yDown ? (y) => oy + (y - y0) * k : (y) => oy + (y1 - y) * k,
    bounds: { x0, x1, y0, y1 },
  }
}

/** Pixel positions of every point (NaN for missing values). */
export function project(xs: (number | null)[], ys: (number | null)[], plot: Plot): Float32Array {
  const out = new Float32Array(2 * xs.length)
  for (let i = 0; i < xs.length; i++) {
    const x = xs[i]
    const y = ys[i]
    const ok = x !== null && y !== null && Number.isFinite(x) && Number.isFinite(y)
    out[2 * i] = ok ? plot.sx(x!) : NaN
    out[2 * i + 1] = ok ? plot.sy(y!) : NaN
  }
  return out
}

/** Index of the point nearest to (mx, my) within `radius` px, or -1.  Linear scan: fine for ~10k points. */
export function nearestPoint(px: Float32Array, mx: number, my: number, radius: number): number {
  let best = -1
  let bestD = radius * radius
  for (let i = 0; i < px.length / 2; i++) {
    const dx = px[2 * i] - mx
    const dy = px[2 * i + 1] - my
    const d = dx * dx + dy * dy
    if (d <= bestD) {
      bestD = d
      best = i
    }
  }
  return best
}

// ---- zoom / pan -------------------------------------------------------------

/** Screen transform of an embedding plot: x' = tx + k·x (same for y). */
export interface View2D {
  k: number
  tx: number
  ty: number
}
export const IDENTITY_VIEW: View2D = { k: 1, tx: 0, ty: 0 }
export const MAX_ZOOM = 200

export function isIdentity(v: View2D): boolean {
  return v.k === 1 && v.tx === 0 && v.ty === 0
}

/**
 * Zoom by `factor` keeping the screen point (cx, cy) fixed; k is clamped to [minK, MAX_ZOOM].  With the
 * default minK = 1, k = 1 is the full view; a smaller minK lets a view zoom out beyond its fit (e.g. to
 * see a tissue image around the measured spots).
 */
export function zoomAt(v: View2D, cx: number, cy: number, factor: number, minK = 1): View2D {
  const k = Math.min(MAX_ZOOM, Math.max(minK, v.k * factor))
  if (k === 1 && minK >= 1) return IDENTITY_VIEW
  const f = k / v.k
  return { k, tx: cx - (cx - v.tx) * f, ty: cy - (cy - v.ty) * f }
}

export function panBy(v: View2D, dx: number, dy: number): View2D {
  return { k: v.k, tx: v.tx + dx, ty: v.ty + dy }
}

/** Apply a view to projected points ([x0, y0, x1, y1, …]); NaN (missing) stays NaN; identity returns the input. */
export function applyView(px: Float32Array, v: View2D): Float32Array {
  if (isIdentity(v)) return px
  const out = new Float32Array(px.length)
  for (let i = 0; i < px.length; i += 2) {
    out[i] = v.tx + v.k * px[i]
    out[i + 1] = v.ty + v.k * px[i + 1]
  }
  return out
}

/**
 * Typical spacing of points (spots of a spatial array): the median distance
 * of a point to its nearest neighbour, over an evenly spaced sample of at
 * most `maxSample` points; null for fewer than two points.  Robust to grids
 * whose coordinates are not exact (pixel positions of an imaged array).
 */
export function gridSpacing(xs: (number | null)[], ys: (number | null)[], maxSample = 1500): number | null {
  const px: number[] = []
  const py: number[] = []
  for (let i = 0; i < xs.length; i++) {
    const x = xs[i]
    const y = ys[i]
    if (x !== null && y !== null && Number.isFinite(x) && Number.isFinite(y)) {
      px.push(x)
      py.push(y)
    }
  }
  const n = px.length
  if (n < 2) return null
  const step = Math.max(1, Math.floor(n / maxSample))
  const d: number[] = []
  for (let i = 0; i < n; i += step) {
    let best = Infinity
    for (let j = 0; j < n; j++) {
      if (j === i) continue
      const dx = px[i] - px[j]
      const dy = py[i] - py[j]
      const e = dx * dx + dy * dy
      if (e > 0 && e < best) best = e
    }
    if (Number.isFinite(best)) d.push(Math.sqrt(best))
  }
  if (!d.length) return null
  d.sort((a, b) => a - b)
  return d[Math.floor(d.length / 2)]
}
