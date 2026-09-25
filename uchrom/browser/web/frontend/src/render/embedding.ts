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
