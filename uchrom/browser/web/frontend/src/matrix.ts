/**
 * Binary matrix payload (API.md "Binary matrix payload") and heatmap colour
 * scales for contact / distance matrices.  Pure — no DOM.
 */

import { viridis, type RGB } from './colors'

export interface MatrixHeader {
  chrom: string
  start: number
  end: number
  n_rows: number
  n_cols: number
  bin_starts: number[]
  bin_ends: number[]
  resolution?: number | null
  value: 'count' | 'balanced' | 'distance' | 'contact_frequency' | string
  unit?: string | null
  n_traces?: number | null
  note?: string | null
}

export interface MatrixData {
  header: MatrixHeader
  /** row-major n_rows × n_cols, NaN = missing */
  data: Float32Array
}

/** uint32 H | H bytes JSON header (space padded) | float32[n_rows·n_cols]. */
export function decodeMatrix(buf: ArrayBuffer): MatrixData {
  if (buf.byteLength < 4) throw new Error('matrix payload too short')
  const h = new DataView(buf).getUint32(0, true)
  if (h % 4 !== 0) throw new Error(`header length ${h} is not a multiple of 4`)
  if (4 + h > buf.byteLength) throw new Error('matrix header overruns the payload')
  const header = JSON.parse(new TextDecoder().decode(new Uint8Array(buf, 4, h))) as MatrixHeader
  const n = header.n_rows * header.n_cols
  const expected = 4 + h + 4 * n
  if (buf.byteLength !== expected) throw new Error(`matrix payload is ${buf.byteLength} bytes, expected ${expected}`)
  return { header, data: new Float32Array(buf, 4 + h, n) }
}

/** Kind of colour scale a matrix needs. */
export type MatrixScale = 'contacts' | 'distance' | 'frequency'

export function scaleFor(value: string): MatrixScale {
  if (value === 'distance') return 'distance'
  if (value === 'contact_frequency') return 'frequency'
  return 'contacts'
}

/** Quantile of the finite values (q ∈ [0, 1]); NaN when there are none. */
export function quantile(values: ArrayLike<number>, q: number, transform?: (v: number) => number): number {
  const v: number[] = []
  for (let i = 0; i < values.length; i++) {
    const x = transform ? transform(values[i]) : values[i]
    if (Number.isFinite(x)) v.push(x)
  }
  if (!v.length) return NaN
  v.sort((a, b) => a - b)
  return v[Math.min(v.length - 1, Math.max(0, Math.round(q * (v.length - 1))))]
}

/**
 * Colour range of a matrix.  Contacts: [0, p99 of log1p(count)] (log
 * scale, zeros stay white).  Distances: [p1, p99].  Frequencies: [0, max].
 */
export function matrixRange(data: ArrayLike<number>, scale: MatrixScale): [number, number] {
  if (scale === 'contacts') {
    const hi = quantile(data, 0.99, (v) => (v > 0 ? Math.log1p(v) : NaN))
    return [0, Number.isFinite(hi) && hi > 0 ? hi : 1]
  }
  if (scale === 'frequency') {
    const hi = quantile(data, 1)
    return [0, Number.isFinite(hi) && hi > 0 ? hi : 1]
  }
  const lo = quantile(data, 0.01)
  const hi = quantile(data, 0.99)
  if (!Number.isFinite(lo)) return [0, 1]
  return hi > lo ? [lo, hi] : [lo, lo + 1]
}

/** "fall"-like ramp for contacts: white → yellow → orange → red → dark red. */
const FALL: RGB[] = [
  [1, 1, 1],
  [1, 0.96, 0.62],
  [1, 0.72, 0.3],
  [0.94, 0.33, 0.13],
  [0.7, 0.05, 0.08],
  [0.3, 0, 0.03],
]

export function fall(t: number): RGB {
  const c = Math.min(1, Math.max(0, Number.isFinite(t) ? t : 0)) * (FALL.length - 1)
  const i = Math.min(FALL.length - 2, Math.floor(c))
  const f = c - i
  const a = FALL[i]
  const b = FALL[i + 1]
  return [a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f, a[2] + (b[2] - a[2]) * f]
}

export const MATRIX_MISSING: RGB = [0.38, 0.38, 0.4]

/** Colour of one matrix value under `scale` / `range` (NaN → grey). */
export function matrixColor(v: number, scale: MatrixScale, range: [number, number]): RGB {
  if (!Number.isFinite(v)) return MATRIX_MISSING
  const [lo, hi] = range
  if (scale === 'contacts') return fall((v > 0 ? Math.log1p(v) : 0) / (hi || 1))
  const t = (v - lo) / (hi - lo || 1)
  // distances: near = bright (reversed viridis); frequencies: high = bright
  return scale === 'distance' ? viridis(1 - t) : viridis(t)
}

/** RGBA pixels (n_cols × n_rows, one pixel per bin) for an ImageData. */
export function matrixPixels(m: MatrixData, scale: MatrixScale, range: [number, number]): Uint8ClampedArray {
  const { n_rows, n_cols } = m.header
  const px = new Uint8ClampedArray(4 * n_rows * n_cols)
  for (let i = 0; i < n_rows * n_cols; i++) {
    const c = matrixColor(m.data[i], scale, range)
    px[4 * i] = c[0] * 255
    px[4 * i + 1] = c[1] * 255
    px[4 * i + 2] = c[2] * 255
    px[4 * i + 3] = 255
  }
  return px
}

/** Bin index containing genomic position `pos` (binary search on bin starts), or -1. */
export function binAt(starts: readonly number[], ends: readonly number[], pos: number): number {
  let lo = 0
  let hi = starts.length - 1
  if (hi < 0 || pos < starts[0] || pos >= ends[hi]) return -1
  while (lo < hi) {
    const mid = (lo + hi + 1) >> 1
    if (starts[mid] <= pos) lo = mid
    else hi = mid - 1
  }
  return pos < ends[lo] ? lo : -1
}
