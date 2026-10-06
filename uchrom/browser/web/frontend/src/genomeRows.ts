/**
 * Combined genome view (HiGlass / Juicebox style): a stack of rows sharing
 * one horizontal genomic axis.  Pure helpers — row list reducers, defaults
 * per dataset and the rotated-triangle (45°) matrix geometry.
 */

import { parseGenomicNumber } from './filters'
import { binAt } from './matrix'
import { defaultTrackSelection } from './tracks'
import type { DatasetSummary } from './types'
import { parseColorScale, type ColorScaleSetting } from './colormaps'
import { parseScopeSpec, type RowScopeSpec } from './groups'
import type { DistanceStat, TrackAgg } from './workspace'

export type GenomeRowKind = 'matrix' | 'track' | 'intervals'

/**
 * How a matrix row draws its map: `triangle` — the upper triangle of the window
 * rotated 45° (HiGlass); `window` — the same rotation filling the whole row with
 * contacts of loci beyond the window's edges (CoolBox "window"); `square` — the
 * window × window matrix unrotated, stretched to the row.
 */
export type MatrixShape = 'triangle' | 'window' | 'square'
export const MATRIX_SHAPES: MatrixShape[] = ['triangle', 'window', 'square']

export interface GenomeRow {
  id: string
  kind: GenomeRowKind
  /** row height in CSS px (null → default: matrix rows share the free height) */
  height?: number | null
  /** matrix: contact-map key or 'distance' */
  source?: string | null
  resolution?: number | null
  balance?: boolean
  stat?: DistanceStat
  threshold?: number | null
  /** matrix: deepest genomic separation shown across the row height (null → 45°, clipped by the height) */
  maxDist?: number | null
  /** matrix: diagonal at the top of the row (triangle pointing down) */
  flip?: boolean
  /** matrix: how the map is drawn (absent = triangle) */
  shape?: MatrixShape
  /** track: track name */
  track?: string | null
  /** intervals: results key */
  key?: string | null
  /** track / distance / per-cell matrix: which cells (absent = same as the view);
   *  stack e.g. Bergmann above Granule */
  scope?: RowScopeSpec
  /** track: aggregate of the spots in a bin over several cells (default mean) */
  agg?: TrackAgg
  /** matrix: colour scale changes from the defaults of its kind (absent = defaults) */
  color?: ColorScaleSetting
}

export const ROW_HEIGHT: Record<GenomeRowKind, number> = { matrix: 200, track: 44, intervals: 22 }
export const MIN_ROW_H = 16
export const MAX_ROW_H = 900

/** Smallest automatic height of a matrix row. */
export const MIN_AUTO_MATRIX_H = 120

/**
 * Row heights for a pane `avail` px tall: explicit heights as set, tracks /
 * intervals their default, and matrix rows without a height share what is
 * left (at least MIN_AUTO_MATRIX_H each — the stack scrolls beyond that —
 * and at most the height of the full triangle of a `width`-px axis).
 */
export function resolveHeights(rows: GenomeRow[], avail: number, width = Infinity): number[] {
  const fixed = rows.map((r) => r.height ?? (r.kind === 'matrix' ? null : ROW_HEIGHT[r.kind]))
  const nAuto = fixed.filter((h) => h === null).length
  // 1 px row separators
  const free = avail - rows.length - fixed.reduce<number>((a, h) => a + (h ?? 0), 0)
  // never taller than the whole 45° triangle (width / 2)
  const auto = nAuto ? Math.max(MIN_AUTO_MATRIX_H, Math.min(Math.ceil(width / 2), Math.floor(free / nAuto))) : 0
  return fixed.map((h) => h ?? auto)
}

function nextRowId(rows: GenomeRow[]): string {
  const used = new Set(rows.map((r) => r.id))
  let i = rows.length + 1
  while (used.has(`r${i}`)) i++
  return `r${i}`
}

/** Append a row (a fresh id is assigned). */
export function addRow(rows: GenomeRow[], row: Omit<GenomeRow, 'id'>): GenomeRow[] {
  return [...rows, { ...row, id: nextRowId(rows) }]
}

export function removeRow(rows: GenomeRow[], id: string): GenomeRow[] {
  return rows.filter((r) => r.id !== id)
}

/** Move a row up (delta < 0) or down; clamped to the ends. */
export function moveRow(rows: GenomeRow[], id: string, delta: number): GenomeRow[] {
  const i = rows.findIndex((r) => r.id === id)
  if (i < 0) return rows
  const j = Math.max(0, Math.min(rows.length - 1, i + delta))
  if (i === j) return rows
  const out = [...rows]
  const [r] = out.splice(i, 1)
  out.splice(j, 0, r)
  return out
}

export function updateRow(rows: GenomeRow[], id: string, patch: Partial<Omit<GenomeRow, 'id'>>): GenomeRow[] {
  return rows.map((r) => (r.id === id ? { ...r, ...patch } : r))
}

/** Set a row's height, clamped to [MIN_ROW_H, MAX_ROW_H]. */
export function resizeRow(rows: GenomeRow[], id: string, height: number): GenomeRow[] {
  return updateRow(rows, id, { height: Math.round(Math.max(MIN_ROW_H, Math.min(MAX_ROW_H, height))) })
}

/** Settings of a row edited in the inspector. */
export type RowSetting = 'source' | 'resolution' | 'balance' | 'stat' | 'threshold' | 'maxDist' | 'flip' | 'shape' | 'track' | 'key' | 'height' | 'agg'

/**
 * Row patch for one edited setting (text inputs arrive as strings, check
 * boxes as booleans); null when the input is not valid for that setting.
 * Empty text clears optional numbers (auto height, 45° depth, default
 * threshold / resolution).
 */
export function rowPatch(setting: RowSetting, value: string | boolean): Partial<Omit<GenomeRow, 'id'>> | null {
  if (typeof value === 'boolean') {
    return setting === 'balance' || setting === 'flip' ? { [setting]: value } : null
  }
  const text = value.trim()
  const num = (x: number) => (Number.isFinite(x) && x > 0 ? x : NaN)
  switch (setting) {
    case 'source':
      return text ? { source: text, resolution: null } : null // another map: its own resolutions
    case 'track':
    case 'key':
      return text ? { [setting]: text } : null
    case 'shape':
      return MATRIX_SHAPES.includes(text as MatrixShape) ? { shape: text as MatrixShape } : null
    case 'agg':
      return text === 'mean' || text === 'median' || text === 'max' ? { agg: text } : null
    case 'stat':
      return text === 'median' || text === 'mean' || text === 'contact' ? { stat: text } : null
    case 'resolution':
    case 'threshold': {
      if (!text) return { [setting]: null }
      const v = num(Number(text))
      return Number.isNaN(v) ? null : { [setting]: v }
    }
    case 'height': {
      if (!text) return { height: null }
      const v = num(Number(text))
      return Number.isNaN(v) ? null : { height: Math.round(Math.max(MIN_ROW_H, Math.min(MAX_ROW_H, v))) }
    }
    case 'maxDist': {
      if (!text) return { maxDist: null }
      try {
        const v = parseGenomicNumber(text)
        return v > 0 ? { maxDist: v } : null
      } catch {
        return null
      }
    }
    default:
      return null
  }
}

/** Apply one inspector edit to a row (unchanged rows when the input is invalid). */
export function applyRowSetting(rows: GenomeRow[], id: string, setting: RowSetting, value: string | boolean): GenomeRow[] {
  const patch = rowPatch(setting, value)
  return patch ? updateRow(rows, id, patch) : rows
}

type DsLike = Pick<DatasetSummary, 'has_coords' | 'n_spots' | 'contact_maps' | 'tracks' | 'intervals'>

/**
 * Default rows for a dataset: the first per-cell contact map (follows the
 * focused cell / group), the first bulk map, the 3-D distance triangle when there are
 * coordinates, then interval tables and up to six marks as tracks
 * (`tracks`: an earlier track selection, e.g. from an old Tracks pane).
 */
export function defaultRows(ds: DsLike | undefined, tracks?: string[] | null): GenomeRow[] {
  if (!ds) return []
  let rows: GenomeRow[] = []
  const maps = ds.contact_maps ?? []
  const bulk = maps.find((m) => !m.per_cell)
  const perCell = maps.find((m) => m.per_cell)
  // the per-cell map first: it follows the focused cell / group; the bulk map is fixed
  if (perCell) rows = addRow(rows, { kind: 'matrix', source: perCell.key })
  if (bulk) rows = addRow(rows, { kind: 'matrix', source: bulk.key })
  if (ds.has_coords !== false && ds.n_spots > 0) rows = addRow(rows, { kind: 'matrix', source: 'distance' })
  for (const iv of ds.intervals ?? []) rows = addRow(rows, { kind: 'intervals', key: iv.key })
  const names = (ds.tracks ?? []).map((t) => t.name)
  const have = new Set(names)
  const picked = (tracks ?? []).filter((t) => have.has(t))
  for (const t of picked.length ? picked : defaultTrackSelection(names)) rows = addRow(rows, { kind: 'track', track: t })
  return rows
}

/** Keep only well-formed rows of a persisted pane (null when absent / malformed). */
export function parseRows(raw: unknown): GenomeRow[] | null {
  if (!Array.isArray(raw)) return null
  const out: GenomeRow[] = []
  for (const r of raw) {
    if (!r || typeof r !== 'object') return null
    const x = r as Partial<GenomeRow>
    if (typeof x.id !== 'string' || !(x.kind === 'matrix' || x.kind === 'track' || x.kind === 'intervals')) return null
    const row: GenomeRow = { id: x.id, kind: x.kind }
    if (typeof x.height === 'number' && x.height >= MIN_ROW_H && x.height <= MAX_ROW_H) row.height = x.height
    if (typeof x.source === 'string') row.source = x.source
    if (typeof x.resolution === 'number' && x.resolution > 0) row.resolution = x.resolution
    if (typeof x.balance === 'boolean') row.balance = x.balance
    if (x.stat === 'median' || x.stat === 'mean' || x.stat === 'contact') row.stat = x.stat
    if (typeof x.threshold === 'number' && x.threshold > 0) row.threshold = x.threshold
    if (typeof x.maxDist === 'number' && x.maxDist > 0) row.maxDist = x.maxDist
    if (typeof x.flip === 'boolean') row.flip = x.flip
    if (x.shape && MATRIX_SHAPES.includes(x.shape)) row.shape = x.shape
    if (typeof x.track === 'string') row.track = x.track
    if (typeof x.key === 'string') row.key = x.key
    const scope = parseScopeSpec(x.scope, true)
    if (scope && scope.kind !== 'view') row.scope = scope
    if (x.agg === 'mean' || x.agg === 'median' || x.agg === 'max') row.agg = x.agg
    const color = parseColorScale(x.color)
    if (color) row.color = color
    out.push(row)
  }
  return new Set(out.map((r) => r.id)).size === out.length ? out : null
}

/**
 * Rows saved before the explicit cells setting: a row `group` → that
 * group; a distance row with "focused / pinned cell only" off → all cells;
 * track rows follow the pane's old "cell only" box (off → all cells) and
 * take its aggregate.  `raw` is the persisted list `rows` was parsed from.
 */
export function migrateRows(rows: GenomeRow[], raw: unknown, legacy: { tracksCellOnly?: boolean; agg?: TrackAgg } = {}): GenomeRow[] {
  const old = Array.isArray(raw) ? (raw as Record<string, unknown>[]) : []
  return rows.map((r, i) => {
    const o = old[i] ?? {}
    if (r.scope || 'scope' in o) return r.kind === 'track' && !r.agg && legacy.agg ? { ...r, agg: legacy.agg } : r
    let scope: RowScopeSpec | undefined
    if (typeof o.group === 'string' && o.group) scope = { kind: 'group', group: o.group }
    else if (r.kind === 'matrix' && r.source === 'distance' && o.followFocus === false) scope = { kind: 'all' }
    else if (r.kind === 'track' && legacy.tracksCellOnly === false) scope = { kind: 'all' }
    const out: GenomeRow = { ...r }
    if (scope) out.scope = scope
    if (r.kind === 'track' && !r.agg && legacy.agg) out.agg = legacy.agg
    return out
  })
}

/** Change a row's colour scale: `patch` fields with null / undefined go back to the default (auto for min / max). */
export function setRowColor(rows: GenomeRow[], id: string, color: ColorScaleSetting | undefined): GenomeRow[] {
  return rows.map((r) => {
    if (r.id !== id) return r
    const { color: _old, ...rest } = r // eslint-disable-line @typescript-eslint/no-unused-vars
    return color && Object.keys(color).length ? { ...rest, color } : rest
  })
}

/** Set a row's cells setting ("view" = same as the view: stored as absent). */
export function setRowScope(rows: GenomeRow[], id: string, scope: RowScopeSpec): GenomeRow[] {
  return rows.map((r) => {
    if (r.id !== id) return r
    const { scope: _old, ...rest } = r // eslint-disable-line @typescript-eslint/no-unused-vars
    return scope.kind === 'view' ? rest : { ...rest, scope }
  })
}

// ---- rotated-triangle geometry --------------------------------------------

/**
 * A matrix row: the upper triangle of a symmetric matrix rotated 45° so the
 * diagonal lies on the shared genomic axis.  A point at screen x (genomic
 * midpoint) and depth t below/above the diagonal shows the contact between
 * the loci x − t·k and x + t·k (k = axis px per depth px; 1 = true 45°).
 */
export interface TriangleGeom {
  /** genomic position of screen x = 0 */
  start: number
  /** bp per screen px along the axis */
  bpPerPx: number
  /** row height in the same px */
  height: number
  /** axis px per depth px */
  k: number
  /** diagonal at the top (true) or at the bottom (false) of the row */
  flip: boolean
  /** deepest separation drawn (bp), or null */
  maxDist: number | null
}

/**
 * Axis px per depth px so that `maxDist` spans the row height; null keeps
 * the true 45° aspect (k = 1).
 */
export function depthScale(maxDist: number | null | undefined, bpPerPx: number, height: number): number {
  if (!maxDist || !(bpPerPx > 0) || !(height > 0)) return 1
  return maxDist / bpPerPx / 2 / height
}

/**
 * Genomic positions [a, b] (a ≤ b) shown at row point (x, y) — the two loci
 * whose contact is drawn there — or null outside the triangle (outside the
 * row, or deeper than maxDist).
 */
export function trianglePos(x: number, y: number, g: TriangleGeom): [number, number] | null {
  if (y < 0 || y > g.height) return null
  const t = g.flip ? y : g.height - y
  const half = t * g.k
  const a = g.start + (x - half) * g.bpPerPx
  const b = g.start + (x + half) * g.bpPerPx
  if (g.maxDist !== null && b - a > g.maxDist * (1 + 1e-9)) return null
  return [a, b]
}

/** Bin pair (i ≤ j) of a matrix at row point (x, y), or null outside the triangle / the matrix. */
export function triangleBins(x: number, y: number, g: TriangleGeom, starts: readonly number[], ends: readonly number[]): [number, number] | null {
  const p = trianglePos(x, y, g)
  if (!p) return null
  const i = binAt(starts, ends, p[0])
  const j = binAt(starts, ends, p[1])
  return i < 0 || j < 0 ? null : [i, j]
}

/** Sub-pixel steps of the bin lookup table (positions are resolved to 1/LUT_SUB px). */
const LUT_SUB = 4

/**
 * RGBA pixels (width × height) of the rotated triangle: for every pixel
 * (centre) the inverse mapping gives the two loci, a lookup table the bins,
 * and `colors` (RGBA per matrix cell, n × n) the colour.  Pixels outside
 * the triangle or the matrix stay transparent.
 */
export function rasterTriangle(
  width: number,
  height: number,
  g: TriangleGeom,
  starts: readonly number[],
  ends: readonly number[],
  colors: Uint8ClampedArray,
  window = false,
): Uint8ClampedArray {
  const n = starts.length
  const out = new Uint8ClampedArray(4 * width * height)
  // window: loci up to the deepest half-separation beyond either edge
  const margin = window ? Math.ceil(height * g.k) + 1 : 0
  // bin at every 1/LUT_SUB px along the axis, from −margin (positions without a bin: −1)
  const lut = new Int32Array((width + 2 * margin) * LUT_SUB + 1)
  for (let q = 0; q < lut.length; q++) lut[q] = binAt(starts, ends, g.start + ((q + 0.5) / LUT_SUB - margin) * g.bpPerPx)
  for (let py = 0; py < height; py++) {
    const yc = py + 0.5
    const t = g.flip ? yc : height - yc
    const half = t * g.k
    if (g.maxDist !== null && 2 * half * g.bpPerPx > g.maxDist * (1 + 1e-9)) continue
    const row = 4 * width * py
    // triangle: columns whose two loci both fall inside [0, width); window: every column
    const x0 = window ? 0 : Math.max(0, Math.ceil(half - 0.5))
    const x1 = window ? width : Math.min(width, Math.floor(width - half - 0.5) + 1)
    for (let px = x0; px < x1; px++) {
      const xc = px + 0.5 + margin
      const qa = Math.floor((xc - half) * LUT_SUB)
      const qb = Math.floor((xc + half) * LUT_SUB)
      if (qa < 0 || qb >= lut.length) continue
      const i = lut[qa]
      const j = lut[qb]
      if (i < 0 || j < 0) continue
      const src = 4 * (i * n + j)
      const dst = row + 4 * px
      out[dst] = colors[src]
      out[dst + 1] = colors[src + 1]
      out[dst + 2] = colors[src + 2]
      out[dst + 3] = 255
    }
  }
  return out
}

/** Genomic span a window-shaped row needs beyond each edge of the axis (bp): the deepest
 *  half-separation it draws. */
export function windowMargin(g: TriangleGeom): number {
  const deepest = 2 * g.height * g.k * g.bpPerPx
  return (g.maxDist !== null ? Math.min(deepest, g.maxDist) : deepest) / 2
}

/**
 * RGBA pixels of an unrotated matrix view: column x shows the locus xStart + (x + ½)·xBpPerPx,
 * row y the locus yStart + (y + ½)·yBpPerPx.  Pixels without a bin stay transparent.
 */
export function rasterMatrix(
  width: number,
  height: number,
  v: { xStart: number; yStart: number; xBpPerPx: number; yBpPerPx: number },
  starts: readonly number[],
  ends: readonly number[],
  colors: Uint8ClampedArray,
): Uint8ClampedArray {
  const n = starts.length
  const out = new Uint8ClampedArray(4 * width * height)
  const col = new Int32Array(width)
  for (let x = 0; x < width; x++) col[x] = binAt(starts, ends, v.xStart + (x + 0.5) * v.xBpPerPx)
  for (let y = 0; y < height; y++) {
    const j = binAt(starts, ends, v.yStart + (y + 0.5) * v.yBpPerPx)
    if (j < 0) continue
    const row = 4 * width * y
    for (let x = 0; x < width; x++) {
      const i = col[x]
      if (i < 0) continue
      const src = 4 * (j * n + i)
      const dst = row + 4 * x
      out[dst] = colors[src]
      out[dst + 1] = colors[src + 1]
      out[dst + 2] = colors[src + 2]
      out[dst + 3] = 255
    }
  }
  return out
}

/** The `square` row shape: the window × window matrix (top = window start) stretched to the row. */
export function rasterSquare(
  width: number,
  height: number,
  start: number,
  bpPerPx: number,
  starts: readonly number[],
  ends: readonly number[],
  colors: Uint8ClampedArray,
): Uint8ClampedArray {
  return rasterMatrix(width, height, { xStart: start, yStart: start, xBpPerPx: bpPerPx, yBpPerPx: (width * bpPerPx) / height }, starts, ends, colors)
}

/** Bins (row j, column i) of the square shape at row point (x, y), or null outside the map. */
export function squareBins(x: number, y: number, width: number, height: number, start: number, bpPerPx: number, starts: readonly number[], ends: readonly number[]): [number, number] | null {
  if (x < 0 || y < 0 || x >= width || y >= height) return null
  const i = binAt(starts, ends, start + x * bpPerPx)
  const j = binAt(starts, ends, start + (y / height) * width * bpPerPx)
  return i < 0 || j < 0 ? null : [j, i]
}
