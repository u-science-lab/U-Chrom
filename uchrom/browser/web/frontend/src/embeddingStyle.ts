/**
 * Per-pane point style and colouring of the Embedding view (pure helpers,
 * no DOM).  A pane stores only what differs from DEFAULT_EMB_STYLE, as
 * `pane.embStyle`; `resolveEmbStyle` fills in the rest.
 */

import { cmap, isColormap, scalePos, type ColormapName } from './colormaps'
import { categoryColor, categoryIndex, hexToRgb, HIDDEN_RGB, MISSING_RGB, rgbCss, type RGB } from './colors'
import type { CellField, CellValue } from './types'

/** 'overview': the global overview colouring; 'field': a cell field of this pane; 'solid': one colour. */
export type EmbColorBy = 'overview' | 'field' | 'solid'
/** numeric range: min–max, 1–99 % quantiles, or manual lo / hi */
export type EmbRangeMode = 'auto' | 'quantile' | 'manual'
export type EmbShape = 'circle' | 'square'
/** 'auto': the theme's ring (light themes only) */
export type EmbOutline = 'auto' | 'on' | 'off'

export interface EmbStyle {
  colorBy: EmbColorBy
  /** colorBy 'field': the cell field */
  field: string | null
  /** colorBy 'solid': hex colour */
  solid: string
  /** numeric fields */
  cmap: ColormapName
  reverse: boolean
  /** null → default for the field (quantiles for genes / ATAC, else min–max) */
  range: EmbRangeMode | null
  lo: number | null
  hi: number | null
  log: boolean
  /** numeric: high values drawn last (on top) */
  highOnTop: boolean
  /** dot radius in px; null = automatic (by cell count and pane size) */
  size: number | null
  opacity: number
  shape: EmbShape
  outline: EmbOutline
  /** legend / colour-bar overlay in the pane */
  legend: boolean
  /** categorical field: categories greyed out in this pane */
  hidden: string[]
}

/** What a pane stores: only the changes from the defaults. */
export type EmbStyleSetting = Partial<EmbStyle>

export const DEFAULT_EMB_STYLE: EmbStyle = {
  colorBy: 'overview',
  field: null,
  solid: '#4c9be8',
  cmap: 'viridis',
  reverse: false,
  range: null,
  lo: null,
  hi: null,
  log: false,
  highOnTop: true,
  size: null,
  opacity: 0.95,
  shape: 'circle',
  outline: 'auto',
  legend: true,
  hidden: [],
}

export const SIZE_MIN = 0.5
export const SIZE_MAX = 10
export const OPACITY_MIN = 0.1

const HEX = /^#[0-9a-fA-F]{6}$/
const finite = (v: unknown): v is number => typeof v === 'number' && Number.isFinite(v)

/** Keep the well-formed fields of a stored style (undefined when nothing is left). */
export function parseEmbStyle(raw: unknown): EmbStyleSetting | undefined {
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return undefined
  const r = raw as Record<string, unknown>
  const o: EmbStyleSetting = {}
  if (r.colorBy === 'overview' || r.colorBy === 'field' || r.colorBy === 'solid') o.colorBy = r.colorBy
  if (typeof r.field === 'string' && r.field) o.field = r.field
  if (typeof r.solid === 'string' && HEX.test(r.solid)) o.solid = r.solid
  if (isColormap(r.cmap)) o.cmap = r.cmap
  if (typeof r.reverse === 'boolean') o.reverse = r.reverse
  if (r.range === 'auto' || r.range === 'quantile' || r.range === 'manual') o.range = r.range
  if (finite(r.lo)) o.lo = r.lo
  if (finite(r.hi)) o.hi = r.hi
  if (typeof r.log === 'boolean') o.log = r.log
  if (typeof r.highOnTop === 'boolean') o.highOnTop = r.highOnTop
  if (finite(r.size)) o.size = Math.min(SIZE_MAX, Math.max(SIZE_MIN, r.size))
  if (finite(r.opacity)) o.opacity = Math.min(1, Math.max(OPACITY_MIN, r.opacity))
  if (r.shape === 'circle' || r.shape === 'square') o.shape = r.shape
  if (r.outline === 'auto' || r.outline === 'on' || r.outline === 'off') o.outline = r.outline
  if (typeof r.legend === 'boolean') o.legend = r.legend
  if (Array.isArray(r.hidden) && r.hidden.every((h) => typeof h === 'string')) o.hidden = [...r.hidden]
  return Object.keys(o).length ? o : undefined
}

/** A stored style over the defaults (a field colouring without a field falls back to the overview). */
export function resolveEmbStyle(s: EmbStyleSetting | undefined | null): EmbStyle {
  const st: EmbStyle = { ...DEFAULT_EMB_STYLE, ...(parseEmbStyle(s) ?? {}) }
  if (st.colorBy === 'field' && !st.field) st.colorBy = 'overview'
  return st
}

const same = (a: unknown, b: unknown) => (Array.isArray(a) && Array.isArray(b) ? a.length === b.length && a.every((x, i) => x === b[i]) : a === b)

/**
 * Apply a change to a stored style; keys back at their default are dropped
 * and an all-default style is `undefined`.  Picking another field clears
 * the greyed-out categories.
 */
export function patchEmbStyle(cur: EmbStyleSetting | undefined, patch: Partial<EmbStyle>): EmbStyleSetting | undefined {
  const next: Record<string, unknown> = { ...(cur ?? {}), ...patch }
  if ('field' in patch && patch.field !== cur?.field && !('hidden' in patch)) delete next.hidden
  for (const k of Object.keys(next)) {
    const v = next[k]
    if (v === undefined || same(v, DEFAULT_EMB_STYLE[k as keyof EmbStyle])) delete next[k]
  }
  return Object.keys(next).length ? (next as EmbStyleSetting) : undefined
}

/** Default range of a field: 1–99 % quantiles for sparse per-gene data (rna.*, atac.*), else min–max. */
export function defaultRangeMode(field: string | null): EmbRangeMode {
  return field && /^(rna|atac)\./.test(field) ? 'quantile' : 'auto'
}

/** Quantile q ∈ [0, 1] of ascending `sorted` (linear interpolation); NaN when empty. */
export function quantileSorted(sorted: ArrayLike<number>, q: number): number {
  const n = sorted.length
  if (!n) return NaN
  const p = Math.min(1, Math.max(0, q)) * (n - 1)
  const i = Math.floor(p)
  const f = p - i
  return i + 1 < n ? sorted[i] + (sorted[i + 1] - sorted[i]) * f : sorted[i]
}

/** Finite numbers among `values`, ascending. */
export function sortedFinite(values: Iterable<CellValue | undefined>): Float64Array {
  const v: number[] = []
  for (const x of values) if (finite(x)) v.push(x)
  return Float64Array.from(v).sort()
}

/**
 * Automatic colour range of a numeric field: min–max ('auto'), or the 1st–99th
 * percentile ('quantile'; when that collapses — e.g. a gene expressed in
 * under 1 % of cells — the top falls back to the maximum).  Degenerate → [v, v+1].
 */
export function autoFieldRange(sorted: ArrayLike<number>, mode: 'auto' | 'quantile'): [number, number] {
  if (!sorted.length) return [0, 1]
  const min = sorted[0]
  const max = sorted[sorted.length - 1]
  let lo = min
  let hi = max
  if (mode === 'quantile') {
    lo = quantileSorted(sorted, 0.01)
    hi = quantileSorted(sorted, 0.99)
    if (!(hi > lo)) hi = max
  }
  return hi > lo ? [lo, hi] : [lo, lo + 1]
}

/** The range used: manual lo / hi where set (in 'manual' mode), else automatic. */
export function fieldScaleRange(sorted: ArrayLike<number>, st: Pick<EmbStyle, 'range' | 'lo' | 'hi' | 'field'>): [number, number] {
  const mode = st.range ?? defaultRangeMode(st.field)
  const auto = autoFieldRange(sorted, mode === 'quantile' ? 'quantile' : 'auto')
  if (mode !== 'manual') return auto
  const lo = st.lo ?? auto[0]
  const hi = st.hi ?? auto[1]
  return hi > lo ? [lo, hi] : [lo, lo + (Math.abs(lo) || 1) * 1e-6 + 1e-12]
}

/** Automatic dot radius: by cell count, growing a little with the pane. */
export function autoRadius(n: number, w: number, h: number): number {
  const grow = Math.min(2, Math.max(1, Math.min(w, h) / 340))
  return (n > 3000 ? 1.6 : n > 800 ? 2.4 : 3.4) * grow
}

export const dotRadius = (st: Pick<EmbStyle, 'size'>, n: number, w: number, h: number) => st.size ?? autoRadius(n, w, h)

/**
 * Per-dot colours (CSS strings) and draw keys of a pane colouring.  Keys
 * order the drawing (low first): missing / hidden values get −Infinity so
 * they sit underneath; numeric values keep their value when high values go
 * on top, else 0 (data order).
 */
export interface DotColors {
  css: string[]
  key: Float64Array
}

/** Numeric field: colormap over `range` (missing → grey). */
export function numericDotColors(ids: readonly string[], values: ReadonlyMap<string, CellValue> | null, st: EmbStyle, range: [number, number]): DotColors {
  const n = ids.length
  const css = new Array<string>(n)
  const key = new Float64Array(n)
  const missing = rgbCss(MISSING_RGB)
  // a small LUT: 256 levels are indistinguishable from exact colours and save 5k string builds
  const lut = Array.from({ length: 256 }, (_, i) => rgbCss(cmap(st.cmap, i / 255, st.reverse)))
  for (let i = 0; i < n; i++) {
    const v = values?.get(ids[i])
    if (!finite(v)) {
      css[i] = missing
      key[i] = -Infinity
      continue
    }
    const t = scalePos(v, range, st.log)
    css[i] = lut[Math.round((Number.isFinite(t) ? t : 0) * 255)]
    key[i] = st.highOnTop ? v : 0
  }
  return { css, key }
}

/** Categorical field: the app's category colours; categories greyed out in the pane → dark grey. */
export function categoryDotColors(ids: readonly string[], values: ReadonlyMap<string, CellValue> | null, field: CellField, hidden: readonly string[]): DotColors {
  const idx = categoryIndex(field, hidden, values?.values())
  const n = ids.length
  const css = new Array<string>(n)
  const key = new Float64Array(n)
  const memo = new Map<string, string>()
  const missing = rgbCss(MISSING_RGB)
  const off = rgbCss(HIDDEN_RGB)
  for (let i = 0; i < n; i++) {
    const v = values?.get(ids[i])
    const s = v === null || v === undefined ? null : String(v)
    const k = s === null ? undefined : idx.get(s)
    if (k === undefined || k < 0) {
      css[i] = k === undefined ? missing : off
      key[i] = -Infinity
      continue
    }
    let c = memo.get(s!)
    if (!c) memo.set(s!, (c = rgbCss(categoryColor(k, s!))))
    css[i] = c
    key[i] = 0
  }
  return { css, key }
}

/** One colour for every dot. */
export function solidDotColors(n: number, hex: string): DotColors {
  let rgb: RGB
  try {
    rgb = hexToRgb(hex)
  } catch {
    rgb = hexToRgb(DEFAULT_EMB_STYLE.solid)
  }
  const c = rgbCss(rgb)
  return { css: new Array<string>(n).fill(c), key: new Float64Array(n) }
}

/**
 * Draw order of the dots: by `key` (ascending, stable), and members of the
 * group in scope after everyone else.  Null when data order will do.
 */
export function drawOrder(n: number, key: ArrayLike<number> | null, member?: ((i: number) => boolean) | null): Uint32Array | null {
  let needed = !!member
  if (!needed && key) for (let i = 1; i < n && !needed; i++) needed = key[i] < key[i - 1]
  if (!needed) return null
  const idx = Array.from({ length: n }, (_, i) => i)
  const m = member ? Uint8Array.from(idx, (i) => (member(i) ? 1 : 0)) : null
  idx.sort((a, b) => (m ? m[a] - m[b] : 0) || (key ? key[a] - key[b] || 0 : 0))
  return Uint32Array.from(idx)
}

export interface LegendRow {
  value: string
  count: number
  color: string
  off: boolean
}

/** Legend of a categorical field in a pane: rows in the field's order with counts, and the missing count. */
export function categoryLegend(field: CellField, values: ReadonlyMap<string, CellValue> | null, hidden: readonly string[]): { rows: LegendRow[]; missing: number } {
  const idx = categoryIndex(field, [], values?.values())
  const counts = new Map<string, number>()
  let missing = 0
  if (values) {
    for (const v of values.values()) {
      if (v === null || v === undefined) missing++
      else counts.set(String(v), (counts.get(String(v)) ?? 0) + 1)
    }
  } else for (const c of field.categories ?? []) counts.set(c.value, c.count)
  const off = new Set(hidden)
  const rows = [...idx.entries()].map(([value, i]) => ({ value, count: counts.get(value) ?? 0, color: rgbCss(categoryColor(i, value)), off: off.has(value) }))
  return { rows, missing }
}
