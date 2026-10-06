/**
 * Cell groups — aggregate views over several cells.  A group is referenced
 * by a string (API.md "Cell groups"):
 * - `field:<column>=<value>`: every cell with that category (e.g. a cell type);
 * - a server id `g…`: a registered cell list (a lasso selection, saved or not).
 * Pure helpers: references, lasso hit-testing, saved-group reducers, scopes.
 */

import { categoricalColor, categoryColor, rgbCss } from './colors'
import { palette } from './theme'
import type { CellField, CellValue } from './types'

export type GroupRef = string

/** A named cell list kept by the viewer (per dataset name, in localStorage). */
export interface SavedGroup {
  /** server id (hash of the sorted cells) */
  id: string
  name: string
  color: string
  cells: string[]
}

/** The current lasso selection: registered on the server, not saved yet. */
export interface Selection {
  id: string
  cells: string[]
}

export const FIELD_PREFIX = 'field:'

export const fieldGroupRef = (field: string, value: string): GroupRef => `${FIELD_PREFIX}${field}=${value}`

/** `field:cell_type=Bergmann` → {field: 'cell_type', value: 'Bergmann'} (null for other refs). */
export function parseFieldRef(ref: GroupRef): { field: string; value: string } | null {
  if (!ref.startsWith(FIELD_PREFIX)) return null
  const rest = ref.slice(FIELD_PREFIX.length)
  const i = rest.indexOf('=')
  return i <= 0 ? null : { field: rest.slice(0, i), value: rest.slice(i + 1) }
}

/** Cells of a categorical field group, from that field's per-cell values. */
export function fieldGroupCells(values: ReadonlyMap<string, CellValue> | undefined, value: string): string[] | null {
  if (!values) return null
  const out: string[] = []
  for (const [cell, v] of values) if (v !== null && String(v) === value) out.push(cell)
  return out
}

// ---- lasso ------------------------------------------------------------------

export type Pt = [number, number]

/** Even-odd rule: is (x, y) inside the closed polygon? */
export function pointInPolygon(x: number, y: number, poly: readonly Pt[]): boolean {
  let inside = false
  for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
    const [xi, yi] = poly[i]
    const [xj, yj] = poly[j]
    if (yi > y !== yj > y && x < ((xj - xi) * (y - yi)) / (yj - yi) + xi) inside = !inside
  }
  return inside
}

/** Ids of the points (px = x0,y0,x1,y1,… in the polygon's space; NaN = not drawn) inside the lasso. */
export function lassoSelect(px: ArrayLike<number>, ids: readonly string[], poly: readonly Pt[]): string[] {
  if (poly.length < 3) return []
  let [x0, y0, x1, y1] = [Infinity, Infinity, -Infinity, -Infinity]
  for (const [x, y] of poly) {
    x0 = Math.min(x0, x)
    y0 = Math.min(y0, y)
    x1 = Math.max(x1, x)
    y1 = Math.max(y1, y)
  }
  const out: string[] = []
  for (let i = 0; i < ids.length; i++) {
    const x = px[2 * i]
    const y = px[2 * i + 1]
    if (!(x >= x0 && x <= x1 && y >= y0 && y <= y1)) continue // also drops NaN
    if (pointInPolygon(x, y, poly)) out.push(ids[i])
  }
  return out
}

/** Drop lasso points closer than `minDist` px to the previous one (smaller payload, same shape). */
export function simplifyPath(pts: readonly Pt[], minDist = 2): Pt[] {
  const out: Pt[] = []
  for (const p of pts) {
    const q = out[out.length - 1]
    if (!q || Math.hypot(p[0] - q[0], p[1] - q[1]) >= minDist) out.push(p)
  }
  return out
}

// ---- saved groups -------------------------------------------------------------

/** Colour of the n-th saved group (categorical palette, starting past the vivid reds). */
export function groupColor(n: number): string {
  return rgbCss(categoricalColor(n + 3))
}

/** "selection 1", "selection 2", … — the first free default name. */
export function nextGroupName(groups: readonly SavedGroup[], base = 'selection'): string {
  const used = new Set(groups.map((g) => g.name))
  let i = 1
  while (used.has(`${base} ${i}`)) i++
  return `${base} ${i}`
}

/** Add (or replace, same id) a saved group. */
export function upsertGroup(groups: readonly SavedGroup[], g: SavedGroup): SavedGroup[] {
  return groups.some((x) => x.id === g.id) ? groups.map((x) => (x.id === g.id ? { ...x, ...g } : x)) : [...groups, g]
}

export function renameGroup(groups: readonly SavedGroup[], id: string, name: string): SavedGroup[] {
  const n = name.trim()
  return n ? groups.map((g) => (g.id === id ? { ...g, name: n } : g)) : [...groups]
}

export function removeGroup(groups: readonly SavedGroup[], id: string): SavedGroup[] {
  return groups.filter((g) => g.id !== id)
}

/** Keep the well-formed saved groups of persisted state ({dataset name: groups}). */
export function parseSavedGroups(raw: unknown): Record<string, SavedGroup[]> {
  const out: Record<string, SavedGroup[]> = {}
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return out
  for (const [ds, list] of Object.entries(raw as Record<string, unknown>)) {
    if (!Array.isArray(list)) continue
    const ok = list.filter(
      (g): g is SavedGroup =>
        !!g &&
        typeof g.id === 'string' &&
        typeof g.name === 'string' &&
        typeof g.color === 'string' &&
        Array.isArray(g.cells) &&
        g.cells.every((c: unknown) => typeof c === 'string'),
    )
    if (ok.length) out[ds] = ok.map((g) => ({ id: g.id, name: g.name, color: g.color, cells: [...g.cells] }))
  }
  return out
}

// ---- scopes -------------------------------------------------------------------

/** What a view aggregates over: every cell, one cell, or a group. */
export type Scope = { kind: 'all' } | { kind: 'cell'; cell: string } | { kind: 'group'; group: GroupRef }

export const ALL: Scope = { kind: 'all' }

/**
 * The persisted "cells" setting of a view or a genome row — one explicit
 * choice, resolved against the global focus when drawing:
 * - all: every cell, whatever is focused / selected;
 * - focus: the focused cell, else the focused group / lasso selection, else all;
 * - cell / group: fixed;
 * - view (genome rows only): the same as the view's setting.
 */
export type ScopeSpec = { kind: 'all' } | { kind: 'focus' } | { kind: 'cell'; cell: string } | { kind: 'group'; group: GroupRef }
export type RowScopeSpec = ScopeSpec | { kind: 'view' }

export const FOCUS: ScopeSpec = { kind: 'focus' }
export const SAME_AS_VIEW: RowScopeSpec = { kind: 'view' }

export interface FocusState {
  focusCell: string | null
  focusGroup?: string | null
}

/** What a setting shows right now. */
export function resolveScope(spec: ScopeSpec | undefined | null, focus: FocusState): Scope {
  const s = spec ?? FOCUS
  if (s.kind === 'all') return ALL
  if (s.kind === 'cell') return { kind: 'cell', cell: s.cell }
  if (s.kind === 'group') return { kind: 'group', group: s.group }
  if (focus.focusCell) return { kind: 'cell', cell: focus.focusCell }
  if (focus.focusGroup) return { kind: 'group', group: focus.focusGroup }
  return ALL
}

/** A row's setting: "same as view" (the default) takes the view's resolved scope. */
export function resolveRowScope(spec: RowScopeSpec | undefined | null, view: Scope, focus: FocusState): Scope {
  return !spec || spec.kind === 'view' ? view : resolveScope(spec, focus)
}

/** Keep a well-formed persisted setting (null when absent / malformed). */
export function parseScopeSpec(raw: unknown, allowView = false): RowScopeSpec | null {
  if (!raw || typeof raw !== 'object') return null
  const r = raw as Record<string, unknown>
  if (r.kind === 'all' || r.kind === 'focus') return { kind: r.kind }
  if (r.kind === 'view') return allowView ? { kind: 'view' } : null
  if (r.kind === 'cell' && typeof r.cell === 'string' && r.cell) return { kind: 'cell', cell: r.cell }
  if (r.kind === 'group' && typeof r.group === 'string' && r.group) return { kind: 'group', group: r.group }
  return null
}

export const sameSpec = (a: RowScopeSpec | undefined | null, b: RowScopeSpec | undefined | null) => JSON.stringify(a ?? null) === JSON.stringify(b ?? null)

/** Whether a resolved scope covers more than one cell (then an aggregate statistic applies). */
export const isMultiCell = (s: Scope) => s.kind !== 'cell'

/** Query parameters of a scope (API: cell_id / cell and group are exclusive). */
export function scopeParams(s: Scope): { cellId: string | null; group: string | null } {
  return { cellId: s.kind === 'cell' ? s.cell : null, group: s.kind === 'group' ? s.group : null }
}

export const scopeKey = (s: Scope) => (s.kind === 'all' ? 'all' : s.kind === 'cell' ? `cell:${s.cell}` : `group:${s.group}`)

/** Everything the UI needs to show a group: name, colour, cells (null = still loading). */
export interface GroupInfo {
  ref: GroupRef
  name: string
  color: string
  cells: string[] | null
  /** 'field': a category; 'saved': a named list; 'selection': the unsaved lasso */
  kind: 'field' | 'saved' | 'selection'
}

/**
 * Resolve a group reference against the dataset's fields, saved groups and
 * current selection.  Field groups take the category's legend colour.
 */
export function describeGroup(
  ref: GroupRef,
  ctx: {
    fields: readonly CellField[]
    saved: readonly SavedGroup[]
    selection: Selection | null
    values: (field: string) => ReadonlyMap<string, CellValue> | undefined
  },
): GroupInfo | null {
  const f = parseFieldRef(ref)
  if (f) {
    const field = ctx.fields.find((x) => x.name === f.field)
    if (!field) return null
    const i = (field.categories ?? []).findIndex((c) => c.value === f.value)
    return {
      ref,
      name: f.value,
      color: rgbCss(categoryColor(Math.max(0, i), f.value)),
      cells: fieldGroupCells(ctx.values(f.field), f.value),
      kind: 'field',
    }
  }
  const g = ctx.saved.find((x) => x.id === ref)
  if (g) return { ref, name: g.name, color: g.color, cells: g.cells, kind: 'saved' }
  if (ctx.selection?.id === ref) return { ref, name: 'selection', color: palette().strong, cells: ctx.selection.cells, kind: 'selection' }
  return null
}

/** Short label of a scope: "All cells (47)", "cell 1_0_34", "Bergmann (8 cells)". */
export function scopeLabel(s: Scope, info?: GroupInfo | null, nAll?: number): string {
  if (s.kind === 'all') return nAll ? `All cells (${nAll})` : 'All cells'
  if (s.kind === 'cell') return `cell ${s.cell}`
  const n = info?.cells?.length
  return `${info?.name ?? s.group}${n !== undefined ? ` (${n} cells)` : ''}`
}

/** On-canvas form: "All cells · 47", "cell 1_0_34", "selection · 10 cells". */
export function scopeText(s: Scope, info?: GroupInfo | null, nAll?: number): string {
  if (s.kind === 'all') return nAll ? `All cells · ${nAll}` : 'All cells'
  if (s.kind === 'cell') return `cell ${s.cell}`
  const n = info?.cells?.length
  return `${info?.name ?? s.group}${n !== undefined ? ` · ${n} cells` : ''}`
}

/** Reserved group reference of every cell (per-cell maps: the all-cell pseudo-bulk). */
export const ALL_CELLS_REF = 'all'

/** Label of a setting with what it resolves to: "Follow focus → selection (10 cells)". */
export function specLabel(spec: RowScopeSpec | undefined | null, resolved: Scope, info?: GroupInfo | null, nAll?: number, cellTypes?: ReadonlyMap<string, unknown>): string {
  const s = spec ?? FOCUS
  const now = scopeLabel(resolved, info, nAll)
  const typed = (cell: string) => {
    const t = cellTypes?.get(cell)
    return typeof t === 'string' ? ` · ${t}` : ''
  }
  if (s.kind === 'view') return `Same as view → ${resolved.kind === 'cell' ? now + typed(resolved.cell) : now}`
  if (s.kind === 'focus') return `Follow focus → ${resolved.kind === 'cell' ? now + typed(resolved.cell) : now}`
  if (s.kind === 'all') return now
  if (s.kind === 'cell') return `📌 ${now}${typed(s.cell)}`
  return `Group: ${now}`
}
