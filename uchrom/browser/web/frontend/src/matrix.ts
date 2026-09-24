/**
 * Binary matrix payload (API.md "Binary matrix payload") and heatmap colour
 * scales for contact / distance matrices.  Pure — no DOM.
 */

import type { RGB } from './colors'
import { scaleColor, type ColorScale, type MatrixKind } from './colormaps'

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
  /** group-scoped matrices: the group, its cells used, contacts summed (pseudo-bulk) */
  group?: string | null
  n_cells?: number | null
  n_contacts?: number | null
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

/** Kind of values a matrix holds (decides the default colour scale). */
export type MatrixScale = MatrixKind

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

/** RGBA pixels (n_cols × n_rows, one pixel per bin) under a colour scale; missing values get `missing`. */
export function matrixPixels(m: MatrixData, s: ColorScale, range: [number, number], missing: RGB): Uint8ClampedArray {
  const { n_rows, n_cols } = m.header
  const px = new Uint8ClampedArray(4 * n_rows * n_cols)
  for (let i = 0; i < n_rows * n_cols; i++) {
    const c = scaleColor(m.data[i], s, range, missing)
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
