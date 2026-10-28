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
  value: 'count' | 'balanced' | 'distance' | 'contact_frequency' | 'log2_ratio' | string
  unit?: string | null
  n_traces?: number | null
  /** group-scoped matrices: the group, its cells used, contacts summed (pseudo-bulk) */
  group?: string | null
  n_cells?: number | null
  n_contacts?: number | null
  /** log2 ratio maps (value 'log2_ratio'): the reference group and the smoothing */
  ratio_to?: string | null
  smooth?: number | null
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
  if (value === 'log2_ratio') return 'ratio'
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

/**
 * Imaged loci drawn as tiles that meet: a locus of a distance map (25-100 kb probes 1-3 Mb apart in genome-wide
 * tracing) is widened to the next locus when the gap to it is no more than 3× the spacing to the previous one, so
 * a sparse map is not a few dots on white; a gap that is much wider than the local spacing (two imaged regions far
 * apart) stays empty.  The last locus takes the spacing before it.  Maps of contiguous bins are unchanged.
 */
export function tileLoci(starts: readonly number[], ends: readonly number[]): number[] {
  const n = starts.length
  const out = ends.slice()
  for (let i = 0; i < n; i++) {
    const prev = i > 0 ? starts[i] - starts[i - 1] : n > 1 ? starts[1] - starts[0] : 0
    if (i < n - 1) {
      const next = starts[i + 1] - starts[i]
      if (out[i] < starts[i + 1] && next <= 3 * prev) out[i] = starts[i + 1]
    } else if (n > 1 && out[i] - starts[i] < prev) {
      out[i] = starts[i] + prev
    }
  }
  return out
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

/**
 * The Matrix pane's view (HiGlass square mode): the heatmap fills a w × h pane at one bp per
 * px on both axes — x is the shared locus, y is centred on the locus centre plus `yOff` (the
 * pane's own vertical pan).
 */
export function matrixViewport(locus: { start: number; end: number }, w: number, h: number, yOff = 0) {
  const bpPerPx = (locus.end - locus.start) / Math.max(1, w)
  const yCenter = (locus.start + locus.end) / 2 + yOff
  return { xStart: locus.start, xEnd: locus.end, yStart: yCenter - (h / 2) * bpPerPx, yEnd: yCenter + (h / 2) * bpPerPx, bpPerPx }
}

/**
 * Zoom the square view by `factor` (< 1 zooms in) keeping the locus under pane point (mx, my)
 * in place: the new x window (for `setLocus`, before clamping) and the new vertical offset.
 */
export function zoomMatrixView(locus: { start: number; end: number }, w: number, h: number, yOff: number, factor: number, mx: number, my: number) {
  const v = matrixViewport(locus, w, h, yOff)
  const bx = v.xStart + mx * v.bpPerPx
  const by = v.yStart + my * v.bpPerPx
  const bpp = v.bpPerPx * factor
  const start = bx - mx * bpp
  const end = start + w * bpp
  const yCenter = by - my * bpp + (h / 2) * bpp
  return { start, end, yOff: yCenter - (start + end) / 2 }
}
