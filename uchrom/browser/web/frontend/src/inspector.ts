/**
 * Side-bar semantics.  LEFT = what every open view shares (cells, focused
 * cell, the all-cells colouring); RIGHT = inspector of the active pane only.
 * Pure — the components render the sections these helpers pick.
 */

import { activePaneOf, PANE_LABEL, type Pane, type WorkspaceState } from './workspace'

/** What the active dataset offers (decides which sections are relevant). */
export interface DatasetFacts {
  hasCoords: boolean
  nCells: number
  nChroms: number
  nPointSets: number
}

export type LeftSection = 'cells' | 'groups' | 'cellInfo' | 'colour'
export type InspectorSection =
  | 'pin'
  | 'layers'
  | 'subset'
  | 'style'
  | 'chroms'
  | 'points'
  | 'noCoords'
  | 'genomeRows'
  | 'matrix'
  | 'embedding'
  | 'stats'

/** Left side bar: the same for every pane (it never looks at the workspace). */
export function leftSections(ds: DatasetFacts | null): LeftSection[] {
  if (!ds) return []
  const many = ds.nCells > 1
  // groups (cell types, lasso selections) only make sense with several cells
  return many ? ['cells', 'groups', 'cellInfo', 'colour'] : ['cellInfo']
}

/** Inspector sections of one pane, by its type; irrelevant ones left out. */
export function inspectorSections(pane: Pick<Pane, 'type'> | undefined, ds: DatasetFacts | null): InspectorSection[] {
  if (!pane || !ds) return []
  const out: InspectorSection[] = ds.nCells > 1 ? ['pin'] : []
  switch (pane.type) {
    case '3d':
      if (!ds.hasCoords) return [...out, 'noCoords']
      out.push('layers', 'subset', 'style')
      if (ds.nChroms > 1) out.push('chroms')
      if (ds.nPointSets > 0) out.push('points')
      return out
    case 'genome':
      return [...out, 'genomeRows']
    case 'matrix':
      return [...out, 'matrix']
    case 'embedding':
      return [...out, 'embedding']
    case 'stats':
      return [...out, 'stats']
  }
}

/** Both side bars for a workspace: the left one ignores which pane is active. */
export function sidebarSections(ws: WorkspaceState, ds: DatasetFacts | null) {
  const pane = activePaneOf(ws)
  return { left: leftSections(ds), right: inspectorSections(pane, ds), pane }
}

/** Inspector title of a pane: "3D · pane 3". */
export function paneTitle(ws: WorkspaceState, pane: Pane): string {
  return `${PANE_LABEL[pane.type]} · pane ${ws.panes.findIndex((p) => p.id === pane.id) + 1}`
}

/** A workspace whose activePane names no pane gets its first pane active (same object otherwise). */
export function ensureActivePane(ws: WorkspaceState): WorkspaceState {
  if (!ws.panes.length || ws.panes.some((p) => p.id === ws.activePane)) return ws
  return { ...ws, activePane: ws.panes[0].id }
}
