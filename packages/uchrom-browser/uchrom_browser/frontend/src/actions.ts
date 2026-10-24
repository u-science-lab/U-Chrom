/**
 * Browser actions — the one implementation behind every non-GUI caller: the control channel
 * (`control.ts`, used by `uchrom_browser.connect()`), WebMCP tools (`webmcp.ts`) and tests.
 * They call the same store functions as the GUI, so anything done here is something a researcher
 * could click.  Names and arguments are defined in `uchrom_browser/ui_tools.json`.
 */

import { fetchGroupCells, registerGroup } from './api'
import { CAPTURE_MIME, capturePane } from './capture'
import { FIELD_PREFIX, fieldGroupRef, SAME_AS_VIEW, type RowScopeSpec, type ScopeSpec } from './groups'
import type { GenomeRow } from './genomeRows'
import { clampLocus, datasetChroms } from './genome'
import { activeView, useStore } from './store'
import type { DatasetView } from './store'
import { resolveLocus } from './useLocus'
import { LAYOUTS, addPane, removePane, setLayout, type Pane, type PaneType, type StatsKind, type WsLayout } from './workspace'
import { agentMutationAllowed, runAsAgentMutation } from './mutationGate'
import toolDefs from '../../ui_tools.json'

export type ActionArgs = Record<string, unknown>
export type Action = (args: ActionArgs) => Promise<unknown>

export interface ToolDef {
  name: string
  description: string
  inputSchema: Record<string, unknown>
  annotations?: Record<string, unknown>
}
export const TOOLS: ToolDef[] = (toolDefs as { tools: ToolDef[] }).tools

function ctx() {
  const s = useStore.getState()
  const ds = s.datasets.find((d) => d.id === s.activeDatasetId)
  if (!ds) throw new Error('no dataset is open')
  return { s, ds, view: activeView(s) }
}

const str = (v: unknown, name: string): string => {
  if (typeof v !== 'string' || !v) throw new Error(`${name} must be a non-empty string`)
  return v
}
const optStr = (v: unknown): string | null => (typeof v === 'string' && v ? v : null)

/** A cells argument → a view scope: 'focus' | 'all' | a group reference | a cell id. */
export function parseCells(spec: unknown, cellIds: ReadonlySet<string>, groupIds: ReadonlySet<string>): ScopeSpec {
  const v = optStr(spec) ?? 'focus'
  if (v === 'focus') return { kind: 'focus' }
  if (v === 'all') return { kind: 'all' }
  if (v.startsWith(FIELD_PREFIX) || groupIds.has(v) || /^g[0-9a-f]{12}$/.test(v)) return { kind: 'group', group: v }
  if (cellIds.has(v)) return { kind: 'cell', cell: v }
  throw new Error(`unknown cells: ${v} (use 'focus', 'all', a cell id or a group reference)`)
}

function rowScope(spec: unknown, cellIds: ReadonlySet<string>, groupIds: ReadonlySet<string>): RowScopeSpec | undefined {
  if (spec === undefined || spec === null || spec === 'view') return spec === 'view' ? SAME_AS_VIEW : undefined
  return parseCells(spec, cellIds, groupIds)
}

/** open_view rows → Genome rows ({kind:'track'|'distance'|'contacts'|'intervals', …}). */
export function genomeRows(rows: unknown, cellIds: ReadonlySet<string>, groupIds: ReadonlySet<string>): Omit<GenomeRow, 'id'>[] {
  if (!Array.isArray(rows)) return []
  return rows.map((r, i) => {
    const o = (r ?? {}) as Record<string, unknown>
    const scope = rowScope(o.cells, cellIds, groupIds)
    const base = scope ? { scope } : {}
    switch (o.kind) {
      case 'track':
        return { kind: 'track', track: str(o.track, `rows[${i}].track`), ...base }
      case 'distance':
        return { kind: 'matrix', source: 'distance', stat: (optStr(o.stat) ?? 'median') as GenomeRow['stat'], ...base }
      case 'contacts': {
        const ratio = optStr(o.ratio_to)
        const smooth = typeof o.smooth === 'number' && o.smooth >= 1 && o.smooth % 2 === 1 ? o.smooth : undefined
        return { kind: 'matrix', source: str(o.source, `rows[${i}].source`), ...base, ...(ratio ? { ratioTo: ratio } : {}), ...(smooth ? { smooth } : {}) }
      }
      case 'intervals':
        return { kind: 'intervals', key: str(o.key, `rows[${i}].key`) }
      default:
        throw new Error(`rows[${i}].kind must be track, distance, contacts or intervals`)
    }
  }) as Omit<GenomeRow, 'id'>[]
}

function paneInfo(p: Pane) {
  return {
    pane: p.id,
    type: p.type,
    cells: p.scope ?? { kind: 'focus' },
    stats: p.statsKind ?? null,
    ...(p.type === 'stats' ? { chrom_scope: p.chromScope ?? 'all' } : {}),
    embedding: p.embeddingKey,
  }
}

async function toBase64(blob: Blob): Promise<string> {
  const buf = new Uint8Array(await blob.arrayBuffer())
  let s = ''
  for (let i = 0; i < buf.length; i += 0x8000) s += String.fromCharCode(...buf.subarray(i, i + 0x8000))
  return btoa(s)
}

export const ACTIONS: Record<string, Action> = {
  async describe_workspace() {
    const { s, ds, view } = ctx()
    return {
      dataset: {
        id: ds.id, name: ds.name, path: ds.path, n_cells: ds.n_cells, n_spots: ds.n_spots,
        cell_fields: (ds.cell_fields ?? []).map((f) => ({ name: f.name, kind: f.kind })),
        embeddings: (ds.embeddings ?? []).map((e) => e.key),
        tracks: (ds.tracks ?? []).map((t) => t.name),
        contact_maps: (ds.contact_maps ?? []).map((m) => m.key),
      },
      views: s.workspace.panes.map(paneInfo),
      workspace: structuredClone(s.workspace),
      view: structuredClone(view),
      active_view: s.workspace.activePane,
      layout: s.workspace.layout,
      focus: { cell: view.focusCell, group: view.focusGroup },
      selection: view.selection ? { group: view.selection.id, n_cells: view.selection.cells.length } : null,
      saved_groups: (s.savedGroups[ds.name] ?? []).map((g) => ({ group: g.id, name: g.name, n_cells: g.cells.length })),
      locus: resolveLocus(view.locus, datasetChroms(ds)),
    }
  },

  async get_selection() {
    const { s, ds, view } = ctx()
    if (view.selection) return { cells: view.selection.cells, group: view.selection.id, name: null, source: 'lasso' }
    if (view.focusGroup) {
      const saved = (s.savedGroups[ds.name] ?? []).find((g) => g.id === view.focusGroup)
      if (saved) return { cells: saved.cells, group: saved.id, name: saved.name, source: 'group' }
      const r = await fetchGroupCells(ds.id, view.focusGroup)
      return { cells: r.cells, group: view.focusGroup, name: r.name, source: 'group' }
    }
    if (view.focusCell) return { cells: [view.focusCell], group: null, name: null, source: 'cell' }
    return { cells: [], group: null, name: null, source: 'none' }
  },

  async select_cells(args) {
    const { s, ds } = ctx()
    const cells = args.cells
    if (!Array.isArray(cells) || !cells.length) throw new Error('cells must be a non-empty list of cell ids')
    const reg = await registerGroup(ds.id, cells.map(String), optStr(args.name))
    const canonical = await fetchGroupCells(ds.id, reg.id)
    s.setSelection({ id: reg.id, cells: canonical.cells })
    if (optStr(args.name)) useStore.getState().saveSelection(optStr(args.name)!)
    return { group: reg.id, cells: canonical.cells, n_cells: canonical.n_cells, n_unknown: reg.n_unknown }
  },

  async list_groups() {
    const { s, ds } = ctx()
    const auto = (ds.cell_fields ?? [])
      .filter((f) => f.kind === 'category')
      .flatMap((f) => (f.categories ?? []).map((c) => ({ group: fieldGroupRef(f.name, c.value), field: f.name, value: c.value, n_cells: c.count })))
    const saved = (s.savedGroups[ds.name] ?? []).map((g) => ({ group: g.id, name: g.name, n_cells: g.cells.length }))
    return { automatic: auto, saved }
  },

  async focus(args) {
    const { s } = ctx()
    const cell = optStr(args.cell)
    const group = optStr(args.group)
    if (cell && group) throw new Error('give cell or group, not both')
    if (group) s.focusGroup(group)
    else if (cell) {
      const { ds } = ctx()
      if (!(s.cells[ds.id] ?? []).some((c) => c.cell_id === cell)) throw new Error(`unknown cell: ${cell}`)
      s.focusCell(cell)
    }
    else {
      s.focusGroup(null)
      s.focusCell(null)
    }
    return { cell, group }
  },

  async set_locus(args) {
    const { s, ds } = ctx()
    const chrom = str(args.chrom, 'chrom')
    const c = datasetChroms(ds).find((x) => x.name === chrom)
    if (!c) throw new Error(`unknown chromosome: ${chrom}`)
    const start = typeof args.start === 'number' ? args.start : c.start
    const end = typeof args.end === 'number' ? args.end : c.end
    if (!(end > start)) throw new Error('end must be greater than start')
    const locus = clampLocus({ chrom, start, end }, c)
    s.setLocus(locus)
    return locus
  },

  async open_view(args) {
    const { s, ds } = ctx()
    const type = str(args.type, 'type') as PaneType
    if (!['3d', 'spatial', 'embedding', 'genome', 'matrix', 'stats'].includes(type)) throw new Error(`unknown view type: ${type}`)
    const cellIds = new Set((s.cells[ds.id] ?? []).map((c) => c.cell_id))
    const groupIds = new Set((s.savedGroups[ds.name] ?? []).map((g) => g.id))
    const opts: Partial<Omit<Pane, 'id' | 'type'>> = {}
    const scope = parseCells(args.cells, cellIds, groupIds)
    if (scope.kind !== 'focus') opts.scope = scope
    if (type === 'genome' && args.rows) {
      let rows: GenomeRow[] = []
      for (const r of genomeRows(args.rows, cellIds, groupIds)) rows = [...rows, { ...r, id: `R${rows.length + 1}` }]
      opts.genomeRows = { [ds.name]: rows }
    }
    if (type === 'stats') {
      opts.statsKind = (optStr(args.stats) ?? 'rg') as StatsKind
      if (args.chrom_scope !== undefined && args.chrom_scope !== 'all' && args.chrom_scope !== 'locus')
        throw new Error(`chrom_scope must be 'all' or 'locus'`)
      if (args.chrom_scope === 'all' || args.chrom_scope === 'locus') opts.chromScope = args.chrom_scope
      if (Array.isArray(args.compare_groups)) opts.compareGroups = args.compare_groups.map(String)
      if (optStr(args.field_x)) opts.fieldX = optStr(args.field_x)
      if (optStr(args.field_y)) opts.fieldY = optStr(args.field_y)
    }
    if (type === 'embedding' && optStr(args.embedding)) opts.embeddingKey = optStr(args.embedding)
    if (type === 'matrix' && optStr(args.source)) opts.source = optStr(args.source)
    if (type === 'spatial') {
      if (optStr(args.spatial)) opts.spatialKey = optStr(args.spatial)
      if (optStr(args.region)) opts.region = optStr(args.region)
      if (typeof args.image_opacity === 'number') opts.imageOpacity = Math.max(0, Math.min(1, args.image_opacity))
    }
    let id = ''
    s.setWorkspace((ws) => {
      const next = addPane(ws, type, opts)
      id = next.activePane
      return next
    })
    return { pane: id }
  },

  async show_view(args) {
    const { s } = ctx()
    const pane = str(args.pane, 'pane')
    if (!s.workspace.panes.some((p) => p.id === pane)) throw new Error(`no view ${pane}`)
    s.setWorkspace((ws) => ({ ...ws, activePane: pane, maximized: null }))
    return { pane }
  },

  async close_view(args) {
    const { s } = ctx()
    const pane = str(args.pane, 'pane')
    if (!s.workspace.panes.some((p) => p.id === pane)) throw new Error(`no view ${pane}`)
    s.setWorkspace((ws) => removePane(ws, pane))
    return { pane }
  },

  async arrange(args) {
    const { s } = ctx()
    const layout = str(args.layout, 'layout') as WsLayout
    if (!LAYOUTS.includes(layout)) throw new Error(`unknown layout: ${layout} (tabs or grid)`)
    s.setWorkspace((ws) => setLayout(ws, layout))
    return { layout }
  },

  async color_by(args) {
    const { s, ds } = ctx()
    const field = str(args.field, 'field')
    if (!(ds.cell_fields ?? []).some((f) => f.name === field)) throw new Error(`unknown cell field: ${field}`)
    s.setOverviewColor('field')
    useStore.getState().setCellField(field)
    return { field }
  },

  async capture_view(args) {
    const s = useStore.getState()
    const id = optStr(args.pane) ?? s.workspace.activePane
    const pane = s.workspace.panes.find((p) => p.id === id)
    const body = document.querySelector<HTMLElement>(`.pane-body[data-pane="${id}"]`)
    if (!pane || !body) throw new Error(`no view ${id}`)
    // let a just-opened view draw first
    await new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)))
    const format = optStr(args.format) ?? 'png'
    if (format !== 'png' && format !== 'svg' && format !== 'pdf') throw new Error(`format must be png, svg or pdf, not ${format}`)
    const { blob, filename, width, height, notes } = await capturePane(body, pane, format)
    const data = await toBase64(blob)
    return { data_base64: data, ...(format === 'png' ? { png_base64: data } : {}), mime: CAPTURE_MIME[format], format, width, height, filename, notes }
  },
}

/** Run one action by name (used by the control channel and WebMCP). */
export async function runAction(name: string, args: ActionArgs = {}, opts: { agentMutation?: boolean } = {}): Promise<unknown> {
  const f = ACTIONS[name]
  if (!f) throw new Error(`unknown action: ${name}`)
  const mutating = !['describe_workspace', 'get_selection', 'list_groups', 'capture_view'].includes(name)
  if (mutating && useStore.getState().agentLease && !opts.agentMutation && !agentMutationAllowed())
    throw new Error('agent lease active; page mutations are temporarily locked')
  return opts.agentMutation ? runAsAgentMutation(() => f(args ?? {})) : f(args ?? {})
}

/** Private control-channel snapshot used only for the local AgentPanel undo. */
export async function captureAgentUiState(): Promise<Record<string, unknown>> {
  const { s, ds } = ctx()
  return {
    dataset_id: ds.id,
    workspace: structuredClone(s.workspace),
    view: structuredClone(s.views[ds.id] ?? activeView(s)),
    canonical: await ACTIONS.describe_workspace({}),
  }
}

/** Restore a captured UI snapshot only if the page still matches the reviewed canonical state. */
export async function restoreAgentUiState(state: unknown, expectedCanonical: unknown): Promise<unknown> {
  const { s, ds } = ctx()
  if (!state || typeof state !== 'object') throw new Error('invalid agent UI snapshot')
  const snapshot = state as { dataset_id?: unknown; workspace?: unknown; view?: unknown }
  if (snapshot.dataset_id !== ds.id || !snapshot.workspace || !snapshot.view)
    throw new Error('the active dataset no longer matches the undo snapshot')
  const currentCanonical = await ACTIONS.describe_workspace({})
  if (JSON.stringify(currentCanonical) !== JSON.stringify(expectedCanonical))
    throw new Error('page changed before undo; refresh state and propose a new plan')
  s.setWorkspace(() => structuredClone(snapshot.workspace as typeof s.workspace))
  const current = useStore.getState()
  useStore.setState({
    views: { ...current.views, [ds.id]: structuredClone(snapshot.view as DatasetView) },
    flyToken: current.flyToken + 1,
  })
  return ACTIONS.describe_workspace({})
}
