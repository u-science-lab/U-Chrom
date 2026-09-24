/**
 * Multi-pane workspace: views (3-D, embedding, …) are equal peers laid out
 * as tabs, columns, rows or a grid.  Pure functions — the store wraps them.
 */

import { migrateRows, parseRows, type GenomeRow } from './genomeRows'
import { FOCUS, parseScopeSpec, type ScopeSpec } from './groups'
import type { EmbeddingInfo } from './types'

/** 'genome': combined tracks + matrix triangles on one axis (was 'tracks'). */
export type PaneType = '3d' | 'embedding' | 'genome' | 'matrix' | 'stats'
export type WsLayout = 'tabs' | 'columns' | 'rows' | 'grid'
export type StatsKind = 'rg' | 'scaling' | 'hist' | 'scatter'
export type TrackAgg = 'mean' | 'median' | 'max'
export type DistanceStat = 'median' | 'mean' | 'contact'

/** Per-pane settings of the genome-coordinate views (all optional). */
export interface PaneOptions {
  /** genome: rows of the combined view per dataset name (absent → defaults for that dataset) */
  genomeRows?: Record<string, GenomeRow[]>
  /** genome: preferred track names for the default rows (from old Tracks panes) */
  tracks?: string[] | null
  /** default aggregate of track rows that have none of their own (older layouts) */
  agg?: TrackAgg
  /** matrix: a contact-map key, or 'distance' (null → first contact map, else distance) */
  source?: string | null
  balance?: boolean
  resolution?: number | null
  stat?: DistanceStat
  threshold?: number | null
  /** stats */
  statsKind?: StatsKind
  fieldX?: string | null
  fieldY?: string | null
  /** stats rg / scaling: all chromosomes or only the locus chromosome */
  chromScope?: 'all' | 'locus'
  /** stats rg / scaling: groups overlaid in their colours (group refs) */
  compareGroups?: string[]
}

export interface Pane extends PaneOptions {
  id: string
  type: PaneType
  /** which cells the view shows (absent = follow the focus); see groups.ts ScopeSpec */
  scope?: ScopeSpec
  /** embedding panes: cellm key (null → default UMAP > t-SNE > PCA) */
  embeddingKey: string | null
  /** embedding panes: the two components shown */
  dims: [number, number]
}

/** What a dataset offers — decides the default views. */
export interface DataKind {
  hasEmbeddings: boolean
  hasCoords: boolean
  hasTracks: boolean
  hasContactMaps?: boolean
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
export const PANE_TYPES: PaneType[] = ['3d', 'embedding', 'genome', 'matrix', 'stats']
export const PANE_LABEL: Record<PaneType, string> = { '3d': '3D', embedding: 'Embedding', genome: 'Genome', matrix: 'Matrix', stats: 'Stats' }
export const MIN_FRAC = 0.1

const pane = (id: string, type: PaneType): Pane => ({ id, type, embeddingKey: null, dims: [0, 1] })

/**
 * Default views follow the data:
 * - 3-D coords + embeddings → 3D | Embedding
 * - 3-D coords, no embeddings → 3D | Genome (tracks / contact maps) else 3D | Matrix (distances)
 * - no 3-D coords → Matrix | Embedding (or Matrix alone)
 * A bare boolean means "has embeddings" with 3-D coords (older callers).
 */
export function defaultWorkspace(kind: boolean | DataKind): WorkspaceState {
  const k: DataKind = typeof kind === 'boolean' ? { hasEmbeddings: kind, hasCoords: true, hasTracks: false } : kind
  const two = (a: PaneType, b: PaneType, sizes: [number, number]): WorkspaceState => ({
    layout: 'columns',
    panes: [pane('P1', a), pane('P2', b)],
    activePane: 'P1',
    sizes,
    maximized: null,
  })
  if (!k.hasCoords) {
    return k.hasEmbeddings ? two('matrix', 'embedding', [0.55, 0.45]) : { layout: 'columns', panes: [pane('P1', 'matrix')], activePane: 'P1', sizes: [1], maximized: null }
  }
  if (k.hasEmbeddings) return two('3d', 'embedding', [0.6, 0.4])
  return k.hasTracks || k.hasContactMaps ? two('3d', 'genome', [0.5, 0.5]) : two('3d', 'matrix', [0.55, 0.45])
}

/** Pane types of a workspace, in order — to compare layouts. */
export const paneSignature = (ws: WorkspaceState) => ws.panes.map((p) => p.type).join(',')

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

export function addPane(ws: WorkspaceState, type: PaneType, opts: Partial<Omit<Pane, 'id' | 'type'>> = {}): WorkspaceState {
  const id = nextId(ws)
  const n = ws.panes.length + 1
  // the new pane gets an equal share; the others shrink proportionally
  const sizes = normalizeSizes([...ws.sizes.map((x) => x * (1 - 1 / n)), 1 / n], n)
  return { ...ws, panes: [...ws.panes, { ...pane(id, type), ...opts }], sizes, activePane: id, maximized: null }
}

/** Panes side by side (or stacked) before the layout switches to a grid. */
export const MAX_SPLIT_PANES = 3

/**
 * Open `cell` in a new view of `type` pinned to it.  Columns / rows turn
 * into a grid beyond MAX_SPLIT_PANES panes so views stay usable.
 */
export function addPinnedPane(ws: WorkspaceState, type: PaneType, cell: string): WorkspaceState {
  return addScopedPane(ws, type, { kind: 'cell', cell })
}

/** Open a new view of `type` showing a group. */
export function addGroupPane(ws: WorkspaceState, type: PaneType, group: string): WorkspaceState {
  return addScopedPane(ws, type, { kind: 'group', group })
}

function addScopedPane(ws: WorkspaceState, type: PaneType, scope: ScopeSpec): WorkspaceState {
  const next = addPane(ws, type, { scope })
  const split = next.layout === 'columns' || next.layout === 'rows'
  return split && next.panes.length > MAX_SPLIT_PANES ? { ...next, layout: 'grid' } : next
}

/** Set a pane's cells setting. */
export function setPaneScope(ws: WorkspaceState, id: string, scope: ScopeSpec): WorkspaceState {
  return updatePane(ws, id, { scope })
}

/** A pane's cells setting (absent = follow the focus). */
export const paneSpec = (pane: Pick<Pane, 'scope'> | undefined): ScopeSpec => pane?.scope ?? FOCUS

/** The cell a pane is pinned to, if any. */
export const pinnedCell = (pane: Pick<Pane, 'scope'> | undefined): string | null => (pane?.scope?.kind === 'cell' ? pane.scope.cell : null)

/** The group a pane is fixed to, if any. */
export const pinnedGroup = (pane: Pick<Pane, 'scope'> | undefined): string | null => (pane?.scope?.kind === 'group' ? pane.scope.group : null)

/**
 * Forget a deleted group everywhere: pane settings (→ follow focus), stats
 * overlays and genome row settings (→ same as view).  Same object when
 * nothing refers to it.
 */
export function dropGroupScope(ws: WorkspaceState, group: string): WorkspaceState {
  let changed = false
  const isIt = (s: { kind: string; group?: string } | undefined) => s?.kind === 'group' && s.group === group
  const panes = ws.panes.map((p) => {
    let q = p
    if (isIt(q.scope)) q = { ...q, scope: FOCUS }
    if (q.compareGroups?.includes(group)) q = { ...q, compareGroups: q.compareGroups.filter((g) => g !== group) }
    if (q.genomeRows && Object.values(q.genomeRows).some((rows) => rows.some((r) => isIt(r.scope)))) {
      const byDs: Record<string, GenomeRow[]> = {}
      for (const [k, rows] of Object.entries(q.genomeRows)) byDs[k] = rows.map((r) => (isIt(r.scope) ? { ...r, scope: { kind: 'view' as const } } : r))
      q = { ...q, genomeRows: byDs }
    }
    if (q !== p) changed = true
    return q
  })
  return changed ? { ...ws, panes } : ws
}

/** The active pane (falls back to the first). */
export function activePaneOf(ws: WorkspaceState): Pane | undefined {
  return ws.panes.find((p) => p.id === ws.activePane) ?? ws.panes[0]
}

/**
 * Whether the 3-D-only side panels (layers, subsets, 3-D style, chromosome
 * legend, point sets) apply: only while a 3-D pane is the active one.
 */
export function show3dPanels(ws: WorkspaceState): boolean {
  return activePaneOf(ws)?.type === '3d'
}

/**
 * Drop pane-level group scopes (the pane's group, Stats overlays) that the
 * active dataset cannot resolve, e.g. a lasso group of another dataset
 * after switching; genome rows are kept per dataset and left alone.
 * Same object when nothing changes.
 */
export function dropUnknownGroups(ws: WorkspaceState, known: (ref: string) => boolean): WorkspaceState {
  const g = pinnedGroup
  const bad = (p: Pane) => (g(p) !== null && !known(g(p)!)) || (p.compareGroups ?? []).some((x) => !known(x))
  if (!ws.panes.some(bad)) return ws
  return {
    ...ws,
    panes: ws.panes.map((p) =>
      bad(p) ? { ...p, scope: g(p) !== null && !known(g(p)!) ? FOCUS : p.scope, compareGroups: (p.compareGroups ?? []).filter(known) } : p,
    ),
  }
}

/** Unpin panes whose cell is not among `known` (e.g. after switching dataset); same object when nothing changes. */
export function dropUnknownPins(ws: WorkspaceState, known: ReadonlySet<string>): WorkspaceState {
  const bad = (p: Pane) => pinnedCell(p) !== null && !known.has(pinnedCell(p)!)
  if (!ws.panes.some(bad)) return ws
  return { ...ws, panes: ws.panes.map((p) => (bad(p) ? { ...p, scope: FOCUS } : p)) }
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

/** Pane fields of layouts saved before the explicit cells setting. */
interface LegacyPane {
  cell?: unknown
  group?: unknown
  followFocus?: unknown
}

/**
 * A pane's cells setting from a persisted pane.  Older layouts had a pinned
 * `cell`, a `group`, and a "focused cell only" flag (`followFocus`):
 * group → that group; matrix with the flag off → all cells; cell → that
 * cell; otherwise follow the focus.
 */
export function migratePaneScope(p: Partial<Pane> & LegacyPane): ScopeSpec {
  const spec = parseScopeSpec(p.scope)
  if (spec && spec.kind !== 'view') return spec
  if (typeof p.group === 'string' && p.group) return { kind: 'group', group: p.group }
  if (p.type === 'matrix' && p.followFocus === false) return { kind: 'all' }
  if (typeof p.cell === 'string' && p.cell) return { kind: 'cell', cell: p.cell }
  return FOCUS
}

/** Keep only well-formed pane options from a persisted pane (migrating old settings). */
function parseOptions(p: Partial<Pane> & LegacyPane): PaneOptions & { scope?: ScopeSpec } {
  const o: PaneOptions & { scope?: ScopeSpec } = {}
  const scope = migratePaneScope(p)
  if (scope.kind !== 'focus') o.scope = scope
  if (Array.isArray(p.compareGroups) && p.compareGroups.every((g) => typeof g === 'string')) o.compareGroups = [...p.compareGroups]
  const agg = p.agg === 'mean' || p.agg === 'median' || p.agg === 'max' ? p.agg : undefined
  if (agg) o.agg = agg // default of track rows without their own (e.g. default rows)
  if (p.genomeRows && typeof p.genomeRows === 'object' && !Array.isArray(p.genomeRows)) {
    const byDs: Record<string, GenomeRow[]> = {}
    for (const [k, v] of Object.entries(p.genomeRows)) {
      const rows = parseRows(v)
      // the old pane-level "cell only" box and track aggregate move onto the rows
      if (rows) byDs[k] = migrateRows(rows, v, { tracksCellOnly: typeof p.followFocus === 'boolean' ? p.followFocus : undefined, agg })
    }
    if (Object.keys(byDs).length) o.genomeRows = byDs
  }
  if (Array.isArray(p.tracks) && p.tracks.every((t) => typeof t === 'string')) o.tracks = p.tracks
  if (typeof p.source === 'string') o.source = p.source
  if (typeof p.balance === 'boolean') o.balance = p.balance
  if (typeof p.resolution === 'number' && p.resolution > 0) o.resolution = p.resolution
  if (p.stat === 'median' || p.stat === 'mean' || p.stat === 'contact') o.stat = p.stat
  if (typeof p.threshold === 'number' && p.threshold > 0) o.threshold = p.threshold
  if (p.statsKind === 'rg' || p.statsKind === 'scaling' || p.statsKind === 'hist' || p.statsKind === 'scatter') o.statsKind = p.statsKind
  if (typeof p.fieldX === 'string') o.fieldX = p.fieldX
  if (typeof p.fieldY === 'string') o.fieldY = p.fieldY
  if (p.chromScope === 'all' || p.chromScope === 'locus') o.chromScope = p.chromScope
  return o
}

/** Parse a persisted workspace; anything malformed → null (caller uses a default). */
export function parseWorkspace(raw: unknown): WorkspaceState | null {
  if (!raw || typeof raw !== 'object') return null
  const w = raw as Partial<WorkspaceState>
  if (!LAYOUTS.includes(w.layout as WsLayout) || !Array.isArray(w.panes) || !w.panes.length) return null
  const panes: Pane[] = []
  for (const raw of w.panes) {
    // saved before the combined view: a 'tracks' pane opens as a genome pane
    const p = raw && (raw.type as string) === 'tracks' ? { ...raw, type: 'genome' as PaneType } : raw
    if (!p || typeof p.id !== 'string' || !PANE_TYPES.includes(p.type)) return null
    const dims: [number, number] =
      Array.isArray(p.dims) && p.dims.length === 2 && p.dims.every((d) => Number.isInteger(d) && d >= 0) ? [p.dims[0], p.dims[1]] : [0, 1]
    panes.push({ ...parseOptions(p), id: p.id, type: p.type, embeddingKey: typeof p.embeddingKey === 'string' ? p.embeddingKey : null, dims })
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
