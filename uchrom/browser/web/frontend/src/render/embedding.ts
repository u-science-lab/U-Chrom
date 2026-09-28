/** Pure helpers for the 2-D embedding scatter (no DOM). */

export interface Plot {
  /** data → pixel */
  sx: (x: number) => number
  sy: (y: number) => number
  bounds: { x0: number; x1: number; y0: number; y1: number }
}

/**
 * Fit data into a `w × h` pixel box with `pad` px margins; each axis is
 * scaled independently (embeddings have no meaningful aspect).  y grows up.
 */
export function fitPlot(xs: (number | null)[], ys: (number | null)[], w: number, h: number, pad: number): Plot {
  let x0 = Infinity
  let x1 = -Infinity
  let y0 = Infinity
  let y1 = -Infinity
  for (let i = 0; i < xs.length; i++) {
    const x = xs[i]
    const y = ys[i]
    if (x === null || y === null || !Number.isFinite(x) || !Number.isFinite(y)) continue
    x0 = Math.min(x0, x)
    x1 = Math.max(x1, x)
    y0 = Math.min(y0, y)
    y1 = Math.max(y1, y)
  }
  if (!Number.isFinite(x0)) [x0, x1, y0, y1] = [0, 1, 0, 1]
  if (x1 === x0) [x0, x1] = [x0 - 0.5, x1 + 0.5]
  if (y1 === y0) [y0, y1] = [y0 - 0.5, y1 + 0.5]
  const iw = Math.max(1, w - 2 * pad)
  const ih = Math.max(1, h - 2 * pad)
  return {
    sx: (x) => pad + ((x - x0) / (x1 - x0)) * iw,
    sy: (y) => pad + (1 - (y - y0) / (y1 - y0)) * ih,
    bounds: { x0, x1, y0, y1 },
  }
}

/**
 * Fit positions into a `w × h` box keeping their aspect (one scale for both
 * axes, centred) — for cell positions in a tissue.  `extent` [x0, x1, y0, y1]
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

/** Zoom by `factor` keeping the screen point (cx, cy) fixed; k is clamped to [1, MAX_ZOOM], k = 1 → the full view. */
export function zoomAt(v: View2D, cx: number, cy: number, factor: number): View2D {
  const k = Math.min(MAX_ZOOM, Math.max(1, v.k * factor))
  if (k === 1) return IDENTITY_VIEW
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
 * Typical spacing of points on a grid (spots of a spatial array): the
 * smaller of the median gaps between distinct x and distinct y values, in
 * data units; null for fewer than two distinct values.
 */
export function gridSpacing(xs: (number | null)[], ys: (number | null)[]): number | null {
  const gap = (v: (number | null)[]) => {
    const u = [...new Set(v.filter((x): x is number => x !== null && Number.isFinite(x)))].sort((a, b) => a - b)
    if (u.length < 2) return null
    const d = u.slice(1).map((x, i) => x - u[i]).sort((a, b) => a - b)
    return d[Math.floor(d.length / 2)]
  }
  const gx = gap(xs)
  const gy = gap(ys)
  return gx === null ? gy : gy === null ? gx : Math.min(gx, gy)
}
