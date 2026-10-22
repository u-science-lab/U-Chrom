import type { DatasetView } from './store'
import type { Pane, WorkspaceState } from './workspace'

export interface HandoffState {
  selection?: { cells: string[]; source: string }
  locus?: DatasetView['locus']
  views: Array<{ type: Pane['type']; stats_kind?: Pane['statsKind']; chrom_scope?: Pane['chromScope'] }>
  layout: WorkspaceState['layout']
}

export function buildHandoffState(view: DatasetView, workspace: WorkspaceState): HandoffState {
  const state: HandoffState = {
    views: workspace.panes.map((pane) => ({
      type: pane.type,
      ...(pane.statsKind ? { stats_kind: pane.statsKind } : {}),
      ...(pane.chromScope ? { chrom_scope: pane.chromScope } : {}),
    })),
    layout: workspace.layout,
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
  return [['Dataset', dataset.name], ['Dataset ID', dataset.id], ['Version', version], ['Selection', selection], ['Locus', locus], ['Stats', statsText], ['Views', views]]
}

export function handoffCommand(token: string): string {
  return `Use the U-Chrom local agent to continue this dataset. HANDOFF: ${token}`
}
