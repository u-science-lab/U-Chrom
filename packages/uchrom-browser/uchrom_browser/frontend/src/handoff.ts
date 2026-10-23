import type { DatasetView } from './store'
import type { ScopeSpec } from './groups'
import type { Pane, WorkspaceState } from './workspace'

export type HandoffPane = Omit<Pane, 'scope'> & { scope: ScopeSpec }

export interface HandoffState {
  selection?: { count?: number; cells?: string[]; source: string }
  locus?: DatasetView['locus']
  focus: { cell: string | null; group: string | null }
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
  | { ok: true; command: string; prompt: string; stateBytes: number; promptBytes: number }
  | { ok: false; reason: 'invalid-dataset-url'; stateBytes: 0 }
  | { ok: false; reason: 'state-too-large'; command: string; stateBytes: number }
  | { ok: false; reason: 'prompt-too-large'; command: string; stateBytes: number; promptBytes: number }

export function buildHandoffState(view: DatasetView, workspace: WorkspaceState, options: { includeCellIds?: boolean } = {}): HandoffState {
  const state: HandoffState = {
    focus: { cell: view.focusCell, group: view.focusGroup },
    views: workspace.panes.map((pane) => {
      const copy = JSON.parse(JSON.stringify(pane)) as Pane
      return { ...copy, scope: copy.scope ?? { kind: 'focus' } }
    }),
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
  const focus = state.focus.cell ? `cell · ${state.focus.cell}` : state.focus.group ? `group · ${state.focus.group}` : 'None'
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

export function handoffPrompt(datasetUrl: string, question: string, state: HandoffState): string {
  const input = JSON.stringify({ dataset_url: datasetUrl, question, semantic_snapshot: state }, null, 2)
  const privacy = !state.selection
    ? 'No selection is present, so no canonical cell IDs are included.'
    : state.selection.cells
      ? 'Canonical cell IDs are included in this snapshot. Review selection privacy before sharing this prompt.'
      : 'Canonical cell IDs are omitted by default; only include them after explicit user opt-in. Review selection privacy before sharing this prompt.'
  return `Use the already-configured U-Chrom MCP on the user’s computer. The user will run this command locally: ${handoffCommand(datasetUrl)}. After the local page is open, read its actual state through MCP, compare it with this reference snapshot, and propose matching changes for approval in the local WebUI. Do not claim the hosted snapshot has already been applied. Do not probe localhost or send this snapshot to any web service. ${privacy}\n\nExact handoff input:\n\`\`\`json\n${input}\n\`\`\``
}

function utf8ByteLength(value: string): number {
  return new TextEncoder().encode(value).byteLength
}

export function buildLocalHandoff(datasetUrl: string, question: string, state: HandoffState): LocalHandoffResult {
  if (!isPublicDatasetUrl(datasetUrl)) return { ok: false, reason: 'invalid-dataset-url', stateBytes: 0 }

  const command = handoffCommand(datasetUrl)
  const stateBytes = utf8ByteLength(JSON.stringify(state))
  if (stateBytes > MAX_HANDOFF_BYTES) return { ok: false, reason: 'state-too-large', command, stateBytes }

  const prompt = handoffPrompt(datasetUrl, question, state)
  const promptBytes = utf8ByteLength(prompt)
  if (promptBytes > MAX_HANDOFF_BYTES) return { ok: false, reason: 'prompt-too-large', command, stateBytes, promptBytes }

  return { ok: true, command, prompt, stateBytes, promptBytes }
}
