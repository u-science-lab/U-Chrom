import { describe, expect, it } from 'vitest'
import { buildHandoffState, handoffCommand, handoffSummary } from './handoff'
import { DEFAULT_VIEW } from './store'
import { defaultWorkspace } from './workspace'

describe('hosted handoff state', () => {
  it('serializes current semantic state without localhost or credentials', () => {
    const view = { ...DEFAULT_VIEW, focusCell: 'c2', selection: { id: 'g1', cells: ['c1', 'c2'] }, locus: { chrom: 'chr1', start: 10, end: 100 } }
    const workspace = defaultWorkspace(false)
    const state = buildHandoffState(view, workspace)
    expect(state.selection?.cells).toEqual(['c1', 'c2'])
    expect(state.selection?.source).toBe('lasso')
    expect(state.focus).toEqual({ cell: 'c2', group: null })
    expect(state.workspace.active_pane).toBe(workspace.activePane)
    expect(state.views[0]).toMatchObject({ id: workspace.panes[0].id, scope: { kind: 'focus' } })
    expect(JSON.stringify(state)).not.toMatch(/localhost|token|password|credential/i)
    expect(handoffSummary(state, { id: 'catalog-id', name: 'Toy dataset' }, '2026-10-22')).toContainEqual(['Selection', '2 cells · canonical IDs'])
  })

  it('summarizes focus and the active pane', () => {
    const view = { ...DEFAULT_VIEW, focusGroup: 'g123' }
    const workspace = defaultWorkspace(false)
    const state = buildHandoffState(view, workspace)
    expect(handoffSummary(state, { id: 'catalog-id', name: 'Toy dataset' }, '2026-10-22')).toEqual(expect.arrayContaining([
      ['Focus', 'group · g123'],
      ['Active view', workspace.activePane],
    ]))
  })

  it('keeps the copied instruction as a non-navigable token command', () => {
    expect(handoffCommand('abc_token')).toBe('Use the U-Chrom local agent to continue this dataset. HANDOFF: abc_token')
    expect(handoffCommand('abc_token')).not.toContain('?token=')
  })
})
