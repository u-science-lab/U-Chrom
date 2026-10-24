import type { DatasetView } from './store'
import type { ScopeSpec } from './groups'
import type { RowScopeSpec } from './groups'
import type { GenomeRow } from './genomeRows'
import type { Pane, WorkspaceState } from './workspace'

export type HandoffScope = { kind: ScopeSpec['kind'] | Extract<RowScopeSpec, { kind: 'view' }>['kind']; cell?: string; group?: string }
export type HandoffGenomeRow = Omit<GenomeRow, 'scope' | 'ratioTo'> & {
  scope?: HandoffScope
  ratioTo?: string | null
  ratio_to_kind?: 'all' | 'group'
}
export type HandoffPane = Omit<Pane, 'scope' | 'compareGroups' | 'genomeRows'> & {
  scope: HandoffScope
  compareGroups?: string[]
  compare_groups_count?: number
  genomeRows?: Record<string, HandoffGenomeRow[]>
}

export interface HandoffFocus {
  cell: string | null
  group: string | null
  kind: 'cell' | 'group' | 'none'
}

export interface HandoffState {
  selection?: { count?: number; cells?: string[]; source: string }
  locus?: DatasetView['locus']
  focus: HandoffFocus
  views: HandoffPane[]
  layout: {
    kind: WorkspaceState['layout']
    maximized: WorkspaceState['maximized']
    grid_cols?: number[]
    grid_rows?: number[]
  }
  workspace: { active_pane: string }
}

export const MAX_HANDOFF_BYTES = 1024 * 1024

export type LocalHandoffResult =
  | { ok: true; installCommand: string; command: string; prompt: string; stateBytes: number; promptBytes: number }
  | { ok: false; reason: 'invalid-dataset-url'; stateBytes: 0 }
  | { ok: false; reason: 'state-too-large'; installCommand: string; command: string; stateBytes: number }
  | { ok: false; reason: 'prompt-too-large'; installCommand: string; command: string; stateBytes: number; promptBytes: number }

function handoffFocus(view: DatasetView, includeCellIds: boolean): HandoffFocus {
  const kind: HandoffFocus['kind'] = view.focusCell ? 'cell' : view.focusGroup ? 'group' : 'none'
  return {
    cell: includeCellIds ? view.focusCell : null,
    group: includeCellIds ? (view.focusGroup ?? null) : null,
    kind,
  }
}

function handoffPane(pane: Pane, includeCellIds: boolean): HandoffPane {
  const copy = JSON.parse(JSON.stringify(pane)) as Pane
  const scope = copy.scope ?? { kind: 'focus' as const }
  const result: HandoffPane = {
    ...copy,
    scope: includeCellIds ? { ...scope } : { kind: scope.kind },
  }
  if (copy.genomeRows) {
    result.genomeRows = Object.fromEntries(Object.entries(copy.genomeRows).map(([dataset, rows]) => [dataset, rows.map((row) => {
      const next = { ...row } as HandoffGenomeRow
      if (row.scope) next.scope = includeCellIds ? { ...row.scope } : { kind: row.scope.kind }
      if (!includeCellIds && row.ratioTo) {
        next.ratio_to_kind = row.ratioTo === 'all' ? 'all' : 'group'
        delete next.ratioTo
      }
      return next
    })]))
  }
  if (includeCellIds) {
    if (copy.compareGroups) result.compareGroups = [...copy.compareGroups]
  } else if (copy.compareGroups) {
    result.compare_groups_count = copy.compareGroups.length
  }
  delete (result as Partial<HandoffPane>).compareGroups
  if (includeCellIds && copy.compareGroups) result.compareGroups = [...copy.compareGroups]
  return result
}

export function buildHandoffState(view: DatasetView, workspace: WorkspaceState, options: { includeCellIds?: boolean } = {}): HandoffState {
  const includeCellIds = options.includeCellIds === true
  const state: HandoffState = {
    focus: handoffFocus(view, includeCellIds),
    views: workspace.panes.map((pane) => handoffPane(pane, includeCellIds)),
    layout: {
      kind: workspace.layout,
      maximized: workspace.maximized,
      ...(workspace.gridCols ? { grid_cols: [...workspace.gridCols] } : {}),
      ...(workspace.gridRows ? { grid_rows: [...workspace.gridRows] } : {}),
    },
    workspace: { active_pane: workspace.activePane },
  }
  if (view.selection) {
    state.selection = {
      count: view.selection.cells.length,
      source: 'lasso',
      ...(options.includeCellIds ? { cells: [...view.selection.cells] } : {}),
    }
  }
  if (view.locus) state.locus = { ...view.locus }
  return state
}

export function handoffSummary(state: HandoffState, dataset: { id: string; name: string }, version: string): Array<[string, string]> {
  const selection = state.selection
    ? `${(state.selection.count ?? state.selection.cells?.length ?? 0).toLocaleString()} cells · ${state.selection.source}${state.selection.cells ? ' · canonical IDs' : ' · canonical IDs omitted'}`
    : 'None'
  const locus = state.locus ? `${state.locus.chrom}:${state.locus.start.toLocaleString()}–${state.locus.end.toLocaleString()}` : 'Default'
  const stats = state.views.find((view) => view.type === 'stats')
  const statsText = stats ? `Stats${stats.statsKind ? ` · ${stats.statsKind}` : ''}${stats.chromScope ? ` · ${stats.chromScope}` : ''}` : 'Not open'
  const views = state.views.map((view) => view.type).join(' · ') || 'None'
  const focus = state.focus.cell
    ? `cell · ${state.focus.cell}`
    : state.focus.group
      ? `group · ${state.focus.group}`
      : state.focus.kind === 'cell'
        ? 'cell · canonical ID omitted'
        : state.focus.kind === 'group'
          ? 'group · canonical ID omitted'
          : 'None'
  const layout = `${state.layout.kind}${state.layout.maximized ? ` · maximized ${state.layout.maximized}` : ''}`
  return [['Dataset', dataset.name], ['Dataset ID', dataset.id], ['Version', version], ['Selection', selection], ['Focus', focus], ['Locus', locus], ['Stats', statsText], ['Views', views], ['Layout', layout], ['Active view', state.workspace.active_pane]]
}

function isPublicDatasetUrl(datasetUrl: string): boolean {
  try {
    const parsed = new URL(datasetUrl)
    const hostname = parsed.hostname.replace(/\.$/, '').toLowerCase()
    return parsed.protocol === 'https:'
      && !parsed.username
      && !parsed.password
      && hostname !== 'localhost'
      && !hostname.endsWith('.localhost')
      && !hostname.startsWith('127.')
      && hostname !== '0.0.0.0'
      && hostname !== '[::1]'
  } catch {
    return false
  }
}

export function handoffCommand(datasetUrl: string): string {
  const shellQuotedUrl = `'${datasetUrl.split("'").join("'\"'\"'")}'`
  return `python -m uchrom_browser ${shellQuotedUrl}`
}

export function handoffInstallCommand(): string {
  return 'uv pip install -e packages/chromdata -e packages/uchrom-browser -e packages/uchrom-agent'
}

export function handoffPrompt(datasetUrl: string, question: string, state: HandoffState): string {
  const input = JSON.stringify({ dataset_url: datasetUrl, question, semantic_snapshot: state }, null, 2)
  const hasCanonicalIds = Boolean(
    state.selection?.cells?.length
      || state.focus.cell
      || state.focus.group
      || state.views.some((view) => Boolean(view.scope.cell || view.scope.group || view.compareGroups?.length)),
  )
  const privacy = hasCanonicalIds
    ? 'Canonical cell and group IDs are included in this snapshot. Review selection privacy before sharing this prompt.'
    : state.selection
      ? 'Canonical cell and group IDs are omitted by default; only include them after explicit user opt-in. Review selection privacy before sharing this prompt.'
      : 'No selection is present, so no canonical cell IDs are included and no canonical group IDs are included.'
  return `From a U-Chrom checkout, install the source packages if needed with: ${handoffInstallCommand()}. Then run this local browser command: ${handoffCommand(datasetUrl)}. After the page opens, paste this prompt into the already-configured U-Chrom MCP. First run uchrom_setup_status, inspect the connected pages, and have the user pin the selected page in the local WebUI Agent panel. Then read the local canonical state with uchrom_workspace_snapshot and uchrom_get_selection, compare the hosted reference snapshot with the local canonical state, and only after that analyze the question. Call uchrom_propose_ui_changes with the explicit pinned page_id and expected_revision to propose matching changes for approval in the local WebUI, and wait for the user to Apply the pending plan. Do not claim the hosted snapshot has already been applied. Do not probe localhost or send this snapshot to any web service. ${privacy}\n\nExact handoff input:\n\`\`\`json\n${input}\n\`\`\``
}

function utf8ByteLength(value: string): number {
  return new TextEncoder().encode(value).byteLength
}

export function buildLocalHandoff(datasetUrl: string, question: string, state: HandoffState): LocalHandoffResult {
  if (!isPublicDatasetUrl(datasetUrl)) return { ok: false, reason: 'invalid-dataset-url', stateBytes: 0 }

  const command = handoffCommand(datasetUrl)
  const installCommand = handoffInstallCommand()
  const stateBytes = utf8ByteLength(JSON.stringify(state))
  if (stateBytes > MAX_HANDOFF_BYTES) return { ok: false, reason: 'state-too-large', installCommand, command, stateBytes }

  const prompt = handoffPrompt(datasetUrl, question, state)
  const promptBytes = utf8ByteLength(prompt)
  if (promptBytes > MAX_HANDOFF_BYTES) return { ok: false, reason: 'prompt-too-large', installCommand, command, stateBytes, promptBytes }

  return { ok: true, installCommand, command, prompt, stateBytes, promptBytes }
}
