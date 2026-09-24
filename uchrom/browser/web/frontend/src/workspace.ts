/**
 * Multi-pane workspace: views (3-D, embedding, …) are equal peers laid out
 * as tabs, columns, rows or a grid.  Pure functions — the store wraps them.
 */

import type { EmbeddingInfo } from './types'

export type PaneType = '3d' | 'embedding'
export type WsLayout = 'tabs' | 'columns' | 'rows' | 'grid'

export interface Pane {
  id: string
  type: PaneType
  /** embedding panes: cellm key (null → default UMAP > t-SNE > PCA) */
  embeddingKey: string | null
  /** embedding panes: the two components shown */
  dims: [number, number]
}

export interface WorkspaceState {
  layout: WsLayout
  panes: Pane[]
  activePane: string
  /** size fractions of the panes in 'columns' / 'rows' (sum 1) */
  sizes: number[]
  /** pane shown alone (all others kept mounted but hidden), or null */
  maximized: string | null
}

export const LAYOUTS: WsLayout[] = ['tabs', 'columns', 'rows', 'grid']
export const PANE_TYPES: PaneType[] = ['3d', 'embedding']
export const MIN_FRAC = 0.1

const pane = (id: string, type: PaneType): Pane => ({ id, type, embeddingKey: null, dims: [0, 1] })

/** Default: 3D | Embedding columns when the data has embeddings, else 3D alone. */
export function defaultWorkspace(hasEmbeddings: boolean): WorkspaceState {
  return hasEmbeddings
    ? { layout: 'columns', panes: [pane('P1', '3d'), pane('P2', 'embedding')], activePane: 'P1', sizes: [0.6, 0.4], maximized: null }
    : { layout: 'columns', panes: [pane('P1', '3d')], activePane: 'P1', sizes: [1], maximized: null }
}

/** Preferred default embedding: UMAP, then t-SNE, then PCA, then the first one. */
export function defaultEmbeddingKey(list: EmbeddingInfo[]): string | null {
  for (const m of ['umap', 'tsne', 'pca']) {
    const e = list.find((x) => x.method === m)
    if (e) return e.key
  }
  return list[0]?.key ?? null
}

/** Clamp every fraction to ≥ MIN_FRAC and rescale to sum 1 (length = n). */
export function normalizeSizes(sizes: number[], n: number): number[] {
  if (n <= 0) return []
  let s = sizes.length === n && sizes.every((x) => Number.isFinite(x) && x > 0) ? [...sizes] : Array(n).fill(1 / n)
  const total = s.reduce((a, b) => a + b, 0)
  s = s.map((x) => x / total)
  if (n * MIN_FRAC >= 1) return Array(n).fill(1 / n)
  // raise the small ones to MIN_FRAC, take the difference from the others
  for (let iter = 0; iter < 4; iter++) {
    const low = s.map((x) => x < MIN_FRAC)
    const deficit = s.reduce((a, x, i) => a + (low[i] ? MIN_FRAC - x : 0), 0)
    if (deficit <= 1e-12) break
    const spare = s.reduce((a, x, i) => a + (low[i] ? 0 : x - MIN_FRAC), 0)
    s = s.map((x, i) => (low[i] ? MIN_FRAC : x - ((x - MIN_FRAC) / spare) * deficit))
  }
  return s
}

function nextId(ws: WorkspaceState): string {
  const used = new Set(ws.panes.map((p) => p.id))
  let i = ws.panes.length + 1
  while (used.has(`P${i}`)) i++
  return `P${i}`
}

export function addPane(ws: WorkspaceState, type: PaneType): WorkspaceState {
  const id = nextId(ws)
  const n = ws.panes.length + 1
  // the new pane gets an equal share; the others shrink proportionally
  const sizes = normalizeSizes([...ws.sizes.map((x) => x * (1 - 1 / n)), 1 / n], n)
  return { ...ws, panes: [...ws.panes, pane(id, type)], sizes, activePane: id, maximized: null }
}

export function removePane(ws: WorkspaceState, id: string): WorkspaceState {
  const i = ws.panes.findIndex((p) => p.id === id)
  if (i < 0 || ws.panes.length <= 1) return ws
  const panes = ws.panes.filter((p) => p.id !== id)
  const sizes = normalizeSizes(ws.sizes.filter((_, k) => k !== i), panes.length)
  const activePane = ws.activePane === id ? panes[Math.max(0, i - 1)].id : ws.activePane
  return { ...ws, panes, sizes, activePane, maximized: ws.maximized === id ? null : ws.maximized }
}

export function updatePane(ws: WorkspaceState, id: string, patch: Partial<Omit<Pane, 'id'>>): WorkspaceState {
  return { ...ws, panes: ws.panes.map((p) => (p.id === id ? { ...p, ...patch } : p)) }
}

/** Change a pane's view type; the pane keeps its id and place. */
export function retypePane(ws: WorkspaceState, id: string, type: PaneType): WorkspaceState {
  return updatePane(ws, id, { type })
}

export function setLayout(ws: WorkspaceState, layout: WsLayout): WorkspaceState {
  return { ...ws, layout, maximized: null }
}

/**
 * Drag the splitter after pane `index` so that pane `index` ends at `frac`
 * of the container (0–1); only the two neighbouring panes change.
 */
export function moveSplitter(ws: WorkspaceState, index: number, frac: number): WorkspaceState {
  const s = normalizeSizes(ws.sizes, ws.panes.length)
  if (index < 0 || index >= s.length - 1) return ws
  const before = s.slice(0, index).reduce((a, b) => a + b, 0)
  const pair = s[index] + s[index + 1]
  const a = Math.min(pair - MIN_FRAC, Math.max(MIN_FRAC, frac - before))
  s[index] = a
  s[index + 1] = pair - a
  return { ...ws, sizes: s }
}

/** Parse a persisted workspace; anything malformed → null (caller uses a default). */
export function parseWorkspace(raw: unknown): WorkspaceState | null {
  if (!raw || typeof raw !== 'object') return null
  const w = raw as Partial<WorkspaceState>
  if (!LAYOUTS.includes(w.layout as WsLayout) || !Array.isArray(w.panes) || !w.panes.length) return null
  const panes: Pane[] = []
  for (const p of w.panes) {
    if (!p || typeof p.id !== 'string' || !PANE_TYPES.includes(p.type)) return null
    const dims: [number, number] =
      Array.isArray(p.dims) && p.dims.length === 2 && p.dims.every((d) => Number.isInteger(d) && d >= 0) ? [p.dims[0], p.dims[1]] : [0, 1]
    panes.push({ id: p.id, type: p.type, embeddingKey: typeof p.embeddingKey === 'string' ? p.embeddingKey : null, dims })
  }
  if (new Set(panes.map((p) => p.id)).size !== panes.length) return null
  const activePane = panes.some((p) => p.id === w.activePane) ? (w.activePane as string) : panes[0].id
  const maximized = panes.some((p) => p.id === w.maximized) ? (w.maximized as string) : null
  return { layout: w.layout as WsLayout, panes, activePane, sizes: normalizeSizes(Array.isArray(w.sizes) ? w.sizes : [], panes.length), maximized }
}

/**
 * Workspace-level keyboard shortcuts (registered once, not per pane):
 * ←/↑ previous cell, →/↓ next cell, Esc clears the pick, then the focus.
 * Returns true when the key was handled.
 */
export function handleWorkspaceKey(
  e: Pick<KeyboardEvent, 'key' | 'target'>,
  actions: { hasPick: boolean; clearPick(): void; clearFocus(): void; step(delta: number): void },
): boolean {
  const tag = (e.target as HTMLElement | null)?.tagName
  if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return false
  if (e.key === 'Escape') {
    if (actions.hasPick) actions.clearPick()
    else actions.clearFocus()
    return true
  }
  if (e.key === 'ArrowRight' || e.key === 'ArrowDown') {
    actions.step(1)
    return true
  }
  if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') {
    actions.step(-1)
    return true
  }
  return false
}
