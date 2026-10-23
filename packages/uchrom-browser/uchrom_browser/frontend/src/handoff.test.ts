import { describe, expect, it } from 'vitest'
import { buildHandoffState, buildLocalHandoff, handoffCommand, handoffPrompt, handoffSummary, MAX_HANDOFF_BYTES } from './handoff'
import { DEFAULT_VIEW } from './store'
import { defaultWorkspace, workspaceOf } from './workspace'

describe('hosted handoff state', () => {
  it('serializes current semantic state without localhost or credentials', () => {
    const view = { ...DEFAULT_VIEW, focusCell: 'c2', selection: { id: 'g1', cells: ['c1', 'c2'] }, locus: { chrom: 'chr1', start: 10, end: 100 } }
    const workspace = defaultWorkspace(false)
    const state = buildHandoffState(view, workspace)
    expect(state.selection?.cells).toBeUndefined()
    expect(state.selection?.count).toBe(2)
    expect(state.selection?.source).toBe('lasso')
    expect(state.focus).toEqual({ cell: 'c2', group: null })
    expect(state.workspace.active_pane).toBe(workspace.activePane)
    expect(state.views[0]).toMatchObject({ id: workspace.panes[0].id, scope: { kind: 'focus' } })
    expect(JSON.stringify(state)).not.toMatch(/localhost|token|password|credential/i)
    expect(handoffSummary(state, { id: 'catalog-id', name: 'Toy dataset' }, '2026-10-22')).toContainEqual(['Selection', '2 cells · lasso · canonical IDs omitted'])
  })

  it('includes canonical cell IDs only when explicitly opted in', () => {
    const view = { ...DEFAULT_VIEW, selection: { id: 'g1', cells: ['c1', 'c2'] } }
    const workspace = defaultWorkspace(false)

    expect(buildHandoffState(view, workspace).selection).toEqual({ count: 2, source: 'lasso' })
    expect(buildHandoffState(view, workspace, { includeCellIds: true }).selection).toEqual({ count: 2, cells: ['c1', 'c2'], source: 'lasso' })
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

  it('captures all pane configuration and the complete workspace layout', () => {
    const workspace = {
      ...workspaceOf(['3d', 'stats'], 'grid'),
      activePane: 'P2',
      maximized: 'P1',
      gridCols: [0.4, 0.6],
      gridRows: [1],
      panes: [
        { ...workspaceOf(['3d']).panes[0], scope: { kind: 'cell' as const, cell: 'c1' } },
        { ...workspaceOf(['stats']).panes[0], id: 'P2', statsKind: 'rg' as const, chromScope: 'locus' as const, scope: { kind: 'group' as const, group: 'g2' }, compareGroups: ['g1', 'g2'] },
      ],
    }
    const state = buildHandoffState(DEFAULT_VIEW, workspace)

    expect(state.layout).toEqual({ kind: 'grid', maximized: 'P1', grid_cols: [0.4, 0.6], grid_rows: [1] })
    expect(state.workspace.active_pane).toBe('P2')
    expect(state.views).toEqual([
      { id: 'P1', type: '3d', embeddingKey: null, dims: [0, 1], scope: { kind: 'cell', cell: 'c1' } },
      { id: 'P2', type: 'stats', embeddingKey: null, dims: [0, 1], scope: { kind: 'group', group: 'g2' }, statsKind: 'rg', chromScope: 'locus', compareGroups: ['g1', 'g2'] },
    ])
  })

  it('builds a safely quoted local Python command from a public dataset URL', () => {
    expect(handoffCommand("https://atlas.example/data/it's a dataset.zarr")).toBe("python -m uchrom_browser 'https://atlas.example/data/it'\"'\"'s a dataset.zarr'")
  })

  it('includes the exact URL, question, and semantic snapshot in the local-agent prompt', () => {
    const state = buildHandoffState(
      { ...DEFAULT_VIEW, focusCell: 'c2', selection: { id: 'g1', cells: ['c1', 'c2'] }, locus: { chrom: 'chr1', start: 10, end: 100 } },
      { ...workspaceOf(['3d', 'stats'], 'grid'), panes: [
        { ...workspaceOf(['3d']).panes[0], scope: { kind: 'focus' as const } },
        { ...workspaceOf(['stats']).panes[0], id: 'P2', statsKind: 'rg' as const, chromScope: 'locus' as const, scope: { kind: 'group' as const, group: 'g1' } },
      ], activePane: 'P2', gridCols: [0.4, 0.6], gridRows: [1], maximized: null },
    )
    const prompt = handoffPrompt('https://atlas.example/data.zarr', 'Compare the selected cells', state)
    const input = prompt.match(/```json\n([\s\S]*?)\n```/)

    expect(prompt).toMatch(/already-configured U-Chrom MCP/i)
    expect(prompt).toContain('propose matching changes for approval in the local WebUI')
    expect(input).not.toBeNull()
    expect(JSON.parse(input![1])).toEqual({
      dataset_url: 'https://atlas.example/data.zarr',
      question: 'Compare the selected cells',
      semantic_snapshot: state,
    })
  })

  it('rejects state and prompt above the UTF-8 limit without truncating them', () => {
    const base = buildHandoffState(DEFAULT_VIEW, defaultWorkspace(false))
    const oversizedState = buildLocalHandoff('https://atlas.example/data.zarr', '', {
      ...base,
      selection: { count: 1, cells: ['细'.repeat(Math.ceil(MAX_HANDOFF_BYTES / 3))], source: 'lasso' },
    })
    const oversizedPrompt = buildLocalHandoff('https://atlas.example/data.zarr', '界'.repeat(Math.ceil(MAX_HANDOFF_BYTES / 3)), base)

    expect(oversizedState).toMatchObject({ ok: false, reason: 'state-too-large' })
    expect('prompt' in oversizedState).toBe(false)
    expect(oversizedPrompt).toMatchObject({ ok: false, reason: 'prompt-too-large' })
    expect('prompt' in oversizedPrompt).toBe(false)
  })

  it('does not create a local command for a localhost dataset URL', () => {
    const result = buildLocalHandoff('http://localhost:8765/data.zarr', '', buildHandoffState(DEFAULT_VIEW, defaultWorkspace(false)))

    expect(result).toMatchObject({ ok: false, reason: 'invalid-dataset-url' })
    expect('command' in result).toBe(false)
  })

  it('makes the default prompt explicit about omitted IDs and opt-in privacy', () => {
    const state = buildHandoffState(
      { ...DEFAULT_VIEW, selection: { id: 'g1', cells: ['c1', 'c2'] } },
      defaultWorkspace(false),
    )
    const prompt = handoffPrompt('https://atlas.example/data.zarr', 'Compare the selected cells', state)

    expect(prompt).toMatch(/canonical cell IDs are omitted by default/i)
    expect(prompt).toMatch(/only include them after explicit user opt-in/i)
    expect(prompt).not.toContain('"cells"')
  })
})
