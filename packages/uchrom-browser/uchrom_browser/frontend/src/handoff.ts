import type { DatasetView } from './store'
import type { ScopeSpec } from './groups'
import type { Pane, WorkspaceState } from './workspace'

export interface HandoffPane {
  id: string
  type: Pane['type']
  scope: ScopeSpec
  stats_kind?: Pane['statsKind']
  chrom_scope?: Pane['chromScope']
}

export interface HandoffState {
  selection?: { cells: string[]; source: string }
  locus?: DatasetView['locus']
  focus: { cell: string | null; group: string | null }
  views: HandoffPane[]
  layout: WorkspaceState['layout']
  workspace: { active_pane: string }
}

export function buildHandoffState(view: DatasetView, workspace: WorkspaceState): HandoffState {
  const state: HandoffState = {
    focus: { cell: view.focusCell, group: view.focusGroup },
    views: workspace.panes.map((pane) => ({
      id: pane.id,
      type: pane.type,
      scope: pane.scope ?? { kind: 'focus' },
      ...(pane.statsKind ? { stats_kind: pane.statsKind } : {}),
      ...(pane.chromScope ? { chrom_scope: pane.chromScope } : {}),
    })),
    layout: workspace.layout,
    workspace: { active_pane: workspace.activePane },
  }
  if (view.selection) state.selection = { cells: [...view.selection.cells], source: 'lasso' }
  if (view.locus) state.locus = { ...view.locus }
  return state
}

export function handoffSummary(state: HandoffState, dataset: { id: string; name: string }, version: string): Array<[string, string]> {
  const selection = state.selection ? `${state.selection.cells.length.toLocaleString()} cells · canonical IDs` : 'None'
  const locus = state.locus ? `${state.locus.chrom}:${state.locus.start.toLocaleString()}–${state.locus.end.toLocaleString()}` : 'Default'
  const stats = state.views.find((view) => view.type === 'stats')
  const statsText = stats ? `Stats${stats.stats_kind ? ` · ${stats.stats_kind}` : ''}${stats.chrom_scope ? ` · ${stats.chrom_scope}` : ''}` : 'Not open'
  const views = state.views.map((view) => view.type).join(' · ') || 'None'
  const focus = state.focus.cell ? `cell · ${state.focus.cell}` : state.focus.group ? `group · ${state.focus.group}` : 'None'
  return [['Dataset', dataset.name], ['Dataset ID', dataset.id], ['Version', version], ['Selection', selection], ['Focus', focus], ['Locus', locus], ['Stats', statsText], ['Views', views], ['Active view', state.workspace.active_pane]]
}

export function handoffCommand(token: string): string {
  return `Use the U-Chrom local agent to continue this dataset. HANDOFF: ${token}`
}
