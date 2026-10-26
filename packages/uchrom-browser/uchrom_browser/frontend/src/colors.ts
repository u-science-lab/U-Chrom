import type { CellField, CellValue, ColorMode, Geometry } from './types'

export type RGB = [number, number, number]

/** matplotlib tab20 */
export const TAB20 = [
  '#1f77b4', '#aec7e8', '#ff7f0e', '#ffbb78', '#2ca02c', '#98df8a', '#d62728', '#ff9896',
  '#9467bd', '#c5b0d5', '#8c564b', '#c49c94', '#e377c2', '#f7b6d2', '#7f7f7f', '#c7c7c7',
  '#bcbd22', '#dbdb8d', '#17becf', '#9edae5',
]

/** Distinct, bright-on-dark palette for chromosomes (stable per name). */
const CHROM_PALETTE = [
  '#e6194b', '#3cb44b', '#ffe119', '#4363d8', '#f58231', '#911eb4', '#46f0f0', '#f032e6',
  '#bcf60c', '#fabebe', '#008080', '#e6beff', '#9a6324', '#fffac8', '#800000', '#aaffc3',
  '#808000', '#ffd8b1', '#6b8cff', '#ff6f91', '#00c2a8', '#c9a0ff', '#ffa600', '#7fdbff',
]

export function hexToRgb(hex: string): RGB {
  let h = hex.trim().replace(/^#/, '')
  if (h.length === 3) h = h.split('').map((c) => c + c).join('')
  if (!/^[0-9a-fA-F]{6}$/.test(h)) throw new Error(`bad colour "${hex}"`)
  const n = parseInt(h, 16)
  return [((n >> 16) & 255) / 255, ((n >> 8) & 255) / 255, (n & 255) / 255]
}

/** Natural rank of common chromosome names; unknown names fall back to a hash. */
function chromRank(name: string): number {
  const base = name.replace(/^chr/i, '')
  if (/^\d+$/.test(base)) return parseInt(base, 10) - 1
  // chr1–22 take palette slots 0–21, so X/Y get the two remaining slots.
  const special: Record<string, number> = { x: 22, y: 23, m: 24, mt: 24 }
  const k = base.toLowerCase()
  if (k in special) return special[k]
  let h = 2166136261
  for (let i = 0; i < name.length; i++) {
    h ^= name.charCodeAt(i)
    h = Math.imul(h, 16777619)
  }
  return (h >>> 0) + 1000
}

export function chromColor(name: string): string {
  return CHROM_PALETTE[chromRank(name) % CHROM_PALETTE.length]
}

/**
 * Colour of the i-th cell: hues spaced by the golden angle, so cells with
 * neighbouring indices always differ clearly even with hundreds of cells.
 */
export function cellColor(index: number): RGB {
  const h = (index * 0.618033988749895) % 1
  return hsv(h, 0.8, 1)
}

/** matplotlib viridis, 9 stops (0, 1/8, …, 1). */
const VIRIDIS: RGB[] = [
  [0.267, 0.005, 0.329],
  [0.279, 0.175, 0.483],
  [0.23, 0.322, 0.546],
  [0.173, 0.449, 0.558],
  [0.128, 0.567, 0.551],
  [0.153, 0.681, 0.504],
  [0.361, 0.786, 0.388],
  [0.668, 0.862, 0.196],
  [0.993, 0.906, 0.144],
]

/** Sequential colormap for t ∈ [0, 1] (clamped). */
export function viridis(t: number): RGB {
  const c = Math.min(1, Math.max(0, Number.isFinite(t) ? t : 0)) * (VIRIDIS.length - 1)
  const i = Math.min(VIRIDIS.length - 2, Math.floor(c))
  const f = c - i
  const a = VIRIDIS[i]
  const b = VIRIDIS[i + 1]
  return [a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f, a[2] + (b[2] - a[2]) * f]
}

export const MISSING_RGB: RGB = [0.45, 0.45, 0.45]

/**
 * Colour range for a numeric field: [min, 99th percentile] of the finite
 * values, so a few outliers don't wash the map out.  Degenerate → [v, v+1].
 */
export function fieldRange(values: Iterable<CellValue | undefined>): [number, number] {
  const v: number[] = []
  for (const x of values) if (typeof x === 'number' && Number.isFinite(x)) v.push(x)
  if (!v.length) return [0, 1]
  v.sort((a, b) => a - b)
  const lo = v[0]
  const hi = v[Math.min(v.length - 1, Math.floor(0.99 * (v.length - 1) + 1e-9))]
  return hi > lo ? [lo, hi] : [lo, lo + 1]
}

/**
 * Whether a numeric field reads better on a log scale: non-negative values (counts) skewed to the right
 * (skewness > 1) that log1p of the offset from the minimum makes more symmetric.
 */
export function skewedField(values: Iterable<CellValue | undefined>): boolean {
  const v: number[] = []
  for (const x of values) if (typeof x === 'number' && Number.isFinite(x)) v.push(x)
  if (v.length < 3) return false
  let lo = Infinity
  for (const x of v) lo = Math.min(lo, x)
  if (lo < 0) return false
  const skew = (xs: number[]) => {
    const m = xs.reduce((a, b) => a + b, 0) / xs.length
    let s2 = 0
    let s3 = 0
    for (const x of xs) (s2 += (x - m) ** 2, s3 += (x - m) ** 3)
    s2 /= xs.length
    return s2 > 0 ? s3 / xs.length / s2 ** 1.5 : 0
  }
  const s = skew(v)
  return s > 1 && Math.abs(skew(v.map((x) => Math.log1p(x - lo)))) < s
}

/** viridis over `range` (log1p of the offset from its start when `log`), grey for missing values. */
export function fieldColor(value: CellValue | undefined, range: [number, number], log = false): RGB {
  if (typeof value !== 'number' || !Number.isFinite(value)) return MISSING_RGB
  return viridis(log ? Math.log1p(Math.max(0, value - range[0])) / Math.log1p(range[1] - range[0]) : (value - range[0]) / (range[1] - range[0]))
}

/** Colour of a hidden category (legend toggled off): darker than missing. */
export const HIDDEN_RGB: RGB = [0.24, 0.24, 0.26]

/** Colour of the i-th category of a field (legend order); past 24, a hashed colour. */
export function categoryColor(index: number, value: string): RGB {
  return index < 24 ? categoricalColor(index) : labelColor(value)
}

/**
 * Category → legend index for a categorical cell field (−1 = hidden by the
 * legend).  Values the field's list doesn't know are appended in order of
 * appearance so they still get a colour.
 */
export function categoryIndex(field: CellField, hidden: readonly string[] = [], values?: Iterable<CellValue | undefined>): Map<string, number> {
  const off = new Set(hidden)
  const order = (field.categories ?? []).map((c) => c.value)
  if (values) {
    const known = new Set(order)
    for (const v of values) if (typeof v === 'string' && !known.has(v)) (known.add(v), order.push(v))
  }
  return new Map(order.map((v, i) => [v, off.has(v) ? -1 : i]))
}

/** Colour of one cell value: categorical when `categories` is given, else viridis. */
export function cellValueColor(value: CellValue | undefined, opts: Pick<ColorOptions, 'categories' | 'fieldRange' | 'fieldLog' | 'cellValues'>): RGB {
  if (opts.categories) {
    if (value === null || value === undefined) return MISSING_RGB
    const i = opts.categories.get(String(value))
    return i === undefined ? MISSING_RGB : i < 0 ? HIDDEN_RGB : categoryColor(i, String(value))
  }
  return fieldColor(value, opts.fieldRange ?? fieldRange(opts.cellValues?.values() ?? []), opts.fieldLog ?? false)
}

/** Stable colour per categorical label (e.g. gene): hashed golden-angle hue. */
/**
 * i-th categorical colour: 12 hues × {vivid, light}; consecutive indices
 * jump 7/12 of the colour wheel so neighbours in a legend never look alike.
 */
export function categoricalColor(index: number): RGB {
  const i = ((index % 24) + 24) % 24
  const hue = ((i % 12) * 7) % 12
  return i < 12 ? hsv(hue / 12, 0.78, 1) : hsv(hue / 12, 0.4, 1)
}

/**
 * Colour per label for a point set: labels in `order` (the set's labels by
 * count — fixed for a dataset) get distinct categorical colours; anything
 * beyond 24 labels, or unknown, falls back to the hash colour.
 */
export function labelColorMap(order: readonly string[]): (label: string) => RGB {
  const idx = new Map(order.map((l, i) => [l, i]))
  return (label) => {
    const i = idx.get(label)
    return i !== undefined && i < 24 ? categoricalColor(i) : labelColor(label)
  }
}

export function labelColor(label: string): RGB {
  let h = 2166136261
  for (let i = 0; i < label.length; i++) {
    h ^= label.charCodeAt(i)
    h = Math.imul(h, 16777619)
  }
  const hue = (((h >>> 0) % 997) * 0.618033988749895) % 1
  return hsv(hue, 0.7, 1)
}

/**
 * sRGB → linear, in place.  three.js treats vertex colours as linear and
 * encodes the output as sRGB, so palette colours must be linearised first
 * or the 3-D view comes out washed out next to the (CSS) legends.
 */
export function srgbToLinear(rgb: Float32Array): Float32Array {
  for (let i = 0; i < rgb.length; i++) {
    const c = rgb[i]
    rgb[i] = c <= 0.04045 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4)
  }
  return rgb
}

export const rgbCss = (c: RGB) => `rgb(${Math.round(c[0] * 255)}, ${Math.round(c[1] * 255)}, ${Math.round(c[2] * 255)})`

/** HSV → RGB, all in [0, 1]. */
function hsv(h: number, s: number, v: number): RGB {
  const i = Math.floor(h * 6)
  const f = h * 6 - i
  const p = v * (1 - s)
  const q = v * (1 - f * s)
  const t = v * (1 - (1 - f) * s)
  switch (((i % 6) + 6) % 6) {
    case 0: return [v, t, p]
    case 1: return [q, v, p]
    case 2: return [p, v, t]
    case 3: return [p, q, v]
    case 4: return [t, p, v]
    default: return [v, p, q]
  }
}

/** Rainbow along the polymer: t=0 violet/blue → t=1 red (like matplotlib "rainbow"). */
export function rainbow(t: number): RGB {
  const c = Math.min(1, Math.max(0, t))
  return hsv((1 - c) * 0.75, 0.85, 1)
}

/**
 * Per-vertex RGB colours (length 3·N) for a geometry.
 *
 * - rainbow: several chromosomes (or `chromColors`) → one colour per chromosome; a single
 *   chromosome → hue along genomic position, scaled by the dataset-wide
 *   `chrom_extent` so a sub-region keeps its parent's colours.
 * - trace: tab20 by order of first appearance of each trace_id.
 * - custom: one colour.
 */
export interface ColorOptions {
  /** colour by chromosome even if only one is present (see rainbow) */
  chromColors?: boolean
  /** stable index per cell id for 'cell' mode (e.g. the dataset's cell list) */
  cellIndex?: ReadonlyMap<string, number>
  /** per-cell values + colour range for 'field' mode */
  cellValues?: ReadonlyMap<string, CellValue>
  fieldRange?: [number, number]
  /** numeric field on a log scale (see skewedField) */
  fieldLog?: boolean
  /** categorical field: category → legend index (−1 hidden); see categoryIndex */
  categories?: ReadonlyMap<string, number>
}

/** Neutral dot colour for modes that are not about cells (chrom, trace, …). */
export const NEUTRAL_RGB: RGB = [0.72, 0.74, 0.78]

/**
 * Colour of one whole cell under the overview colouring — the same colour
 * its chromatin gets in the 3-D view ('cell' / 'field'); other modes have
 * no per-cell colour and give NEUTRAL_RGB ('custom' uses the custom colour).
 */
export function cellRgb(cellId: string, mode: ColorMode, custom: string, opts: ColorOptions = {}): RGB {
  if (mode === 'cell') {
    const i = opts.cellIndex?.get(cellId)
    return i === undefined ? [0.6, 0.6, 0.6] : cellColor(i)
  }
  if (mode === 'field') return cellValueColor(opts.cellValues?.get(cellId), opts)
  if (mode === 'custom') return hexToRgb(custom)
  return NEUTRAL_RGB
}

export function vertexColors(geom: Geometry, mode: ColorMode, custom: string, opts: ColorOptions = {}): Float32Array {
  const chromColors = opts.chromColors ?? false
  const { header, starts, offsets } = geom
  const n = header.n_points
  const out = new Float32Array(3 * n)
  const fill = (from: number, to: number, rgb: RGB) => {
    for (let i = from; i < to; i++) {
      out[3 * i] = rgb[0]
      out[3 * i + 1] = rgb[1]
      out[3 * i + 2] = rgb[2]
    }
  }
  if (mode === 'custom') {
    fill(0, n, hexToRgb(custom))
    return out
  }
  if (mode === 'field') {
    const vals = opts.cellValues ?? new Map<string, CellValue>()
    const o = { ...opts, fieldRange: opts.fieldRange ?? fieldRange(vals.values()), fieldLog: opts.fieldLog ?? skewedField(vals.values()) }
    const memo = new Map<string, RGB>()
    header.segments.forEach((seg, s) => {
      if (seg.cell_id === null) return fill(offsets[s], offsets[s + 1], MISSING_RGB)
      let c = memo.get(seg.cell_id)
      if (!c) memo.set(seg.cell_id, (c = cellValueColor(vals.get(seg.cell_id), o)))
      fill(offsets[s], offsets[s + 1], c)
    })
    return out
  }
  if (mode === 'cell') {
    const order = new Map<string, number>(opts.cellIndex ?? [])
    const grey: RGB = [0.6, 0.6, 0.6]
    header.segments.forEach((seg, s) => {
      if (seg.cell_id === null) return fill(offsets[s], offsets[s + 1], grey)
      if (!order.has(seg.cell_id)) order.set(seg.cell_id, order.size)
      fill(offsets[s], offsets[s + 1], cellColor(order.get(seg.cell_id)!))
    })
    return out
  }
  if (mode === 'trace') {
    const order = new Map<string, number>()
    header.segments.forEach((seg, s) => {
      if (!order.has(seg.trace_id)) order.set(seg.trace_id, order.size)
      fill(offsets[s], offsets[s + 1], hexToRgb(TAB20[order.get(seg.trace_id)! % TAB20.length]))
    })
    return out
  }
  const chroms = new Set(header.segments.map((s) => s.chrom))
  // `chromColors`: the layer spans several chromosomes even if the display
  // filter left one, so keep the legend's per-chromosome colours.
  if (chroms.size > 1 || chromColors) {
    header.segments.forEach((seg, s) => fill(offsets[s], offsets[s + 1], hexToRgb(chromColor(seg.chrom))))
    return out
  }
  header.segments.forEach((seg, s) => {
    const ext = header.chrom_extent[seg.chrom] ?? [seg.start, seg.end]
    const span = Math.max(1, ext[1] - ext[0])
    for (let i = offsets[s]; i < offsets[s + 1]; i++) {
      const rgb = rainbow((starts[i] - ext[0]) / span)
      out[3 * i] = rgb[0]
      out[3 * i + 1] = rgb[1]
      out[3 * i + 2] = rgb[2]
    }
  })
  return out
}
